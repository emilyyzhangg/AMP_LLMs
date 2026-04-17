"""
Outcome agent — Tier 1b Per-Publication Atomic Assessor (v42, Phase 2).

One focused LLM call per publication. Five atomic Y/N/Unclear questions answered
from the publication text alone. JSON-only response, strict parser with graceful
fallback to INDETERMINATE on malformed output.

Design (from ATOMIC_EVIDENCE_DECOMPOSITION.md §1.3):
  Q1. Does this publication report RESULTS from the trial?
  Q2. Was the primary endpoint met? (YES/NO/PARTIALLY/NOT_REPORTED/NA)
  Q3. Does it describe clinical EFFICACY (not safety-only)?
  Q4. Does it report the trial FAILED or showed futility?
  Q5. Does it mention advancement to a later phase or approval?
  + evidence_quote (forcing Q2/Q4 to be grounded in literal text)

Verdict from deterministic rules:
  q4=YES                                   → FAILED
  q2 in (YES, PARTIALLY)                   → POSITIVE
  q3=YES                                   → POSITIVE
  q5=YES                                   → POSITIVE
  q1=YES and q2=NO                         → FAILED
  else                                     → INDETERMINATE

The LLM never sees the verdict rules and never sees an "outcome" label. It
answers reading-comprehension questions. The verdict function is 6 lines of
Python — anyone can reason about when it fires.

On-disk cache keyed on (NCT id, PMID or title hash, publication text hash) so
re-runs don't re-call the LLM for unchanged publications.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal, Optional

from .outcome_pub_classifier import PubCandidate

logger = logging.getLogger("agent_annotate.annotation.outcome_pub_assessor")


# ---- Response schema ------------------------------------------------------ #

Verdict = Literal["POSITIVE", "FAILED", "INDETERMINATE"]
Q_TRI = ("YES", "NO", "UNCLEAR")
Q2_VALUES = ("YES", "NO", "PARTIALLY", "NOT_REPORTED", "NA")


@dataclass
class PubAnswers:
    """Raw atomic answers from the LLM for one publication."""
    q1_reports_results: str = "UNCLEAR"      # YES / NO / UNCLEAR
    q2_primary_met: str = "NA"               # YES / NO / PARTIALLY / NOT_REPORTED / NA
    q3_efficacy: str = "NA"                  # YES / NO / UNCLEAR / NA
    q4_failure: str = "NA"                   # YES / NO / UNCLEAR / NA
    q5_advanced: str = "UNCLEAR"             # YES / NO / UNCLEAR
    evidence_quote: str = ""

    @staticmethod
    def normalize_tri(v: str, allowed: tuple[str, ...]) -> str:
        """Normalize a single LLM-returned answer to the allowed enum or a fallback."""
        if not isinstance(v, str):
            return "UNCLEAR" if "UNCLEAR" in allowed else allowed[-1]
        v = v.strip().upper().replace("-", "_").replace(" ", "_")
        return v if v in allowed else ("UNCLEAR" if "UNCLEAR" in allowed else allowed[-1])


@dataclass
class PubVerdict:
    """Full per-publication assessment record (answers + verdict + audit trail)."""
    nct_id: str
    pmid: str
    source: str
    specificity: str                         # trial_specific | ambiguous | general
    answers: PubAnswers = field(default_factory=PubAnswers)
    verdict: Verdict = "INDETERMINATE"
    model: str = ""
    error: str = ""
    cached: bool = False


# ---- Deterministic verdict function (no LLM) ----------------------------- #

def compute_verdict(a: PubAnswers) -> Verdict:
    """Map atomic answers → POSITIVE | FAILED | INDETERMINATE.

    Order matters: q4=YES takes precedence over any positive signal because an
    explicit failure claim in a trial-specific pub outweighs tangential
    positive mentions elsewhere in the same paper.
    """
    if a.q4_failure == "YES":
        return "FAILED"
    if a.q2_primary_met in ("YES", "PARTIALLY"):
        return "POSITIVE"
    if a.q3_efficacy == "YES":
        return "POSITIVE"
    if a.q5_advanced == "YES":
        return "POSITIVE"
    if a.q1_reports_results == "YES" and a.q2_primary_met == "NO":
        return "FAILED"
    return "INDETERMINATE"


# ---- Prompt ---------------------------------------------------------------- #

PUB_ASSESSOR_PROMPT = """You are reading a single publication to answer atomic questions about a clinical trial. Answer each question based ONLY on what this publication's text says. Do not infer beyond what is written. If the publication does not contain the information, answer UNCLEAR, NOT_REPORTED, or NA as appropriate.

Trial identifier: {nct_id}
Drug / intervention name(s): {drug_names}

Publication:
---
{pub_text}
---

Questions:
Q1. Does this publication report RESULTS from the trial identified above (not just a protocol, design description, or passing mention)?
Q2. If Q1=YES, was the trial's PRIMARY endpoint met?
    Answer: YES | NO | PARTIALLY | NOT_REPORTED | NA (if Q1=NO)
Q3. Does the publication describe clinical EFFICACY outcomes (e.g. tumor response, symptom reduction, survival, endpoint achievement)? Safety or tolerability reports without an efficacy finding → NO.
    Answer: YES | NO | UNCLEAR | NA (if Q1=NO)
Q4. Does the publication report that the trial FAILED or that the drug demonstrated futility or lack of efficacy?
    Answer: YES | NO | UNCLEAR | NA (if Q1=NO)
Q5. Does the publication mention that this drug ADVANCED to a later-phase trial or received regulatory approval?
    Answer: YES | NO | UNCLEAR

Return ONLY a single JSON object in this exact shape, no prose before or after:
{{
  "q1_reports_results": "YES|NO|UNCLEAR",
  "q2_primary_met":     "YES|NO|PARTIALLY|NOT_REPORTED|NA",
  "q3_efficacy":        "YES|NO|UNCLEAR|NA",
  "q4_failure":         "YES|NO|UNCLEAR|NA",
  "q5_advanced":        "YES|NO|UNCLEAR",
  "evidence_quote":     "<ONE verbatim quote from the publication supporting Q2 or Q4, ≤30 words. Empty string if no such quote exists.>"
}}"""


# ---- JSON parser (lenient but strict-schema) ------------------------------ #

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_llm_json(text: str) -> Optional[dict]:
    """Extract the first JSON object from LLM output. None if unparseable."""
    if not text:
        return None
    # Try whole-text parse first
    t = text.strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    # Fall back to first {...} block. Non-greedy would miss nested; we want the
    # largest reasonable span here.
    m = _JSON_OBJECT_RE.search(t)
    if not m:
        return None
    candidate = m.group(0)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def answers_from_json(payload: dict) -> PubAnswers:
    """Build a PubAnswers with each field normalized to allowed enum."""
    a = PubAnswers(
        q1_reports_results=PubAnswers.normalize_tri(payload.get("q1_reports_results", ""), Q_TRI),
        q2_primary_met=PubAnswers.normalize_tri(payload.get("q2_primary_met", ""), Q2_VALUES),
        q3_efficacy=PubAnswers.normalize_tri(payload.get("q3_efficacy", ""), Q_TRI + ("NA",)),
        q4_failure=PubAnswers.normalize_tri(payload.get("q4_failure", ""), Q_TRI + ("NA",)),
        q5_advanced=PubAnswers.normalize_tri(payload.get("q5_advanced", ""), Q_TRI),
        evidence_quote=str(payload.get("evidence_quote", "") or "")[:300],
    )
    return a


# ---- Cache ---------------------------------------------------------------- #

def _cache_key(nct_id: str, pub: PubCandidate) -> str:
    """Stable per-(trial, publication, text) key.

    Includes a hash of the publication text so edits to snippet/title invalidate
    the cache — important because we want atomic answers to trace to exactly the
    text the LLM saw.
    """
    body = (pub.title + "\n" + pub.snippet).encode("utf-8", "ignore")
    text_hash = hashlib.sha1(body).hexdigest()[:10]
    pmid_bare = pub.pmid_bare or "no-pmid"
    return f"{nct_id}__{pmid_bare}__{text_hash}"


class PubAssessmentCache:
    """Disk-backed JSON-lines cache of PubVerdict, keyed by _cache_key."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def get(self, key: str) -> Optional[PubVerdict]:
        p = self.path(key)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        ans = PubAnswers(**data.get("answers", {}))
        return PubVerdict(
            nct_id=data.get("nct_id", ""),
            pmid=data.get("pmid", ""),
            source=data.get("source", ""),
            specificity=data.get("specificity", "ambiguous"),
            answers=ans,
            verdict=data.get("verdict", "INDETERMINATE"),
            model=data.get("model", ""),
            error=data.get("error", ""),
            cached=True,
        )

    def put(self, key: str, verdict: PubVerdict) -> None:
        data = asdict(verdict)
        data["cached"] = False  # Don't persist the flag itself.
        self.path(key).write_text(json.dumps(data, indent=2))


# ---- Text preparation ----------------------------------------------------- #

def _truncate_pub_text(pub: PubCandidate, max_chars: int = 1800) -> str:
    """Build the publication body the LLM sees. Title separated from snippet so
    both are visible even when the snippet dominates."""
    title = pub.title.strip()
    snippet = pub.snippet.strip()
    if title and title in snippet:
        body = snippet
    elif title and snippet:
        body = title + "\n\n" + snippet
    else:
        body = title or snippet
    if len(body) > max_chars:
        body = body[:max_chars].rstrip() + " …"
    return body


# ---- Assessor ------------------------------------------------------------- #

class PubAssessor:
    """Runs the atomic Q1-Q5 assessment per publication.

    The constructor takes a client+model so tests can inject a fake client and
    production code passes the real ollama_client. This avoids a hard import
    dependency at module load and keeps this file testable offline.
    """

    def __init__(
        self,
        model: str,
        ollama_client,  # duck-typed: must expose async generate(model, prompt, temperature)
        cache: Optional[PubAssessmentCache] = None,
        temperature: float = 0.0,
    ):
        self.model = model
        self.ollama = ollama_client
        self.cache = cache
        self.temperature = temperature

    async def assess(
        self,
        nct_id: str,
        pub: PubCandidate,
        specificity: str,
        drug_names: list[str],
    ) -> PubVerdict:
        """Return a PubVerdict for one publication. Never raises — errors land
        in PubVerdict.error with verdict=INDETERMINATE."""
        cache_key = _cache_key(nct_id, pub) if self.cache else None
        if self.cache and cache_key:
            hit = self.cache.get(cache_key)
            if hit is not None:
                hit.specificity = specificity  # refresh in case Tier 1a rules changed
                return hit

        pub_text = _truncate_pub_text(pub)
        drug_str = ", ".join(sorted(drug_names)[:5]) if drug_names else "(unknown)"
        prompt = PUB_ASSESSOR_PROMPT.format(
            nct_id=nct_id,
            drug_names=drug_str,
            pub_text=pub_text,
        )

        verdict_record = PubVerdict(
            nct_id=nct_id,
            pmid=pub.pmid,
            source=pub.source,
            specificity=specificity,
            model=self.model,
        )

        try:
            resp = await self.ollama.generate(
                model=self.model,
                prompt=prompt,
                temperature=self.temperature,
            )
            raw = resp.get("response", "") if isinstance(resp, dict) else str(resp)
        except Exception as e:
            verdict_record.error = f"llm_call_failed: {e}"
            logger.warning("assess %s pmid=%s: LLM call failed: %s", nct_id, pub.pmid, e)
            return verdict_record

        payload = parse_llm_json(raw)
        if payload is None:
            verdict_record.error = "malformed_json"
            logger.warning(
                "assess %s pmid=%s: malformed JSON (first 200 chars): %s",
                nct_id, pub.pmid, raw[:200].replace("\n", " "),
            )
            return verdict_record

        verdict_record.answers = answers_from_json(payload)
        verdict_record.verdict = compute_verdict(verdict_record.answers)

        if self.cache and cache_key:
            try:
                self.cache.put(cache_key, verdict_record)
            except OSError as e:
                logger.warning("cache write failed %s: %s", cache_key, e)

        return verdict_record
