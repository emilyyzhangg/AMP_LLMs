"""
Failure-Reason Annotation Agent — Atomic decomposition (v42, B3).

Shadow-mode sibling of FailureReasonAgent. Gated on the atomic outcome label:
runs only when ``outcome_atomic`` ∈ {Terminated, Failed - completed trial}.
For non-failed trials the field returns empty (mirrors legacy behavior).

Pipeline:

  Tier 0 (deterministic registry text):
    Look at whyStopped from clinical_protocol. A clear-language match wins
    directly — the registry text is the canonical source when it exists.

  Tier 1b (one LLM call, only if Tier 0 didn't decide):
    Five atomic YES/NO questions on the pooled evidence (whyStopped + failed
    pub snippets). Binary answers, each grounded in a verbatim quote.

  Tier 3 (priority aggregator):
    Priority: Toxic/Unsafe > Ineffective for purpose > Due to covid
             > Recruitment issues > Business Reason.
    Reason: safety disclosures are the most specific; efficacy is next; the
    rest are external/organizational reasons that could coexist with the
    real cause. Rationale documented in the design doc §3.

No drug lists, no category cheat sheets in the prompt. The LLM sees raw
evidence and answers Y/N — the Python aggregator picks the category.

Stored as field_name="reason_for_failure_atomic". Gated by
``config.orchestrator.failure_reason_atomic_shadow`` (default OFF).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from agents.base import BaseAnnotationAgent
from app.models.annotation import FieldAnnotation
from app.models.research import ResearchResult

logger = logging.getLogger("agent_annotate.annotation.failure_reason_atomic")

VALID_VALUES = [
    "Business Reason",
    "Ineffective for purpose",
    "Toxic/Unsafe",
    "Due to covid",
    "Recruitment issues",
]

_DEFAULT_ATOMIC_MODEL = "qwen3:14b"

# Outcome values that trigger this agent. Mirrors outcome_atomic VALID_VALUES.
_FAILED_OUTCOMES = {"Terminated", "Failed - completed trial"}


# ---- Tier 0: whyStopped registry text ------------------------------------ #

# Keyword → category mapping for the deterministic Tier 0 parse. These match
# token groups that appear verbatim in CT.gov whyStopped text. NOT drug-name
# or trial-name cheat sheets — generic English phrases describing each
# category. Order matters: first match wins in _parse_why_stopped.
_WHY_KEYWORDS: list[tuple[str, list[str]]] = [
    ("Due to covid", [
        "covid", "sars-cov", "coronavirus", "pandemic",
    ]),
    ("Toxic/Unsafe", [
        "toxicity", "toxic effect", "adverse event", "serious adverse",
        "safety concern", "safety signal", "unacceptable toxicity",
        "liver toxicity", "hepatotoxicity", "cardiotoxicity",
    ]),
    ("Recruitment issues", [
        "enrollment", "enrolment", "recruitment", "accrual",
        "could not enroll", "slow accrual", "failure to recruit",
        "low enrollment", "low enrolment", "failure to accrue",
    ]),
    ("Ineffective for purpose", [
        "lack of efficacy", "did not meet", "failed to demonstrate",
        "futility", "interim analysis", "no significant",
        "insufficient efficacy", "ineffective", "no efficacy",
    ]),
    ("Business Reason", [
        "business", "sponsor decision", "strategic", "funding",
        "portfolio", "commercial", "company decision", "development halted",
        "discontinued development", "decision of the sponsor",
    ]),
]


def _extract_why_stopped(research_results: list[ResearchResult]) -> str:
    """Pull whyStopped field from clinical_protocol raw_data."""
    for result in research_results:
        if result.error or result.agent_name != "clinical_protocol" or not result.raw_data:
            continue
        proto = result.raw_data.get(
            "protocol_section",
            result.raw_data.get("protocolSection", {}),
        )
        status_mod = proto.get("statusModule", {})
        why = (status_mod.get("whyStopped") or "").strip()
        if why:
            return why
    return ""


def _parse_why_stopped(text: str) -> Optional[str]:
    """Scan whyStopped text for any category's keyword set.

    Returns the first category that matches, in _WHY_KEYWORDS priority order.
    None if no keyword matches or text is empty.
    """
    if not text:
        return None
    lower = text.lower()
    for category, keywords in _WHY_KEYWORDS:
        for kw in keywords:
            if kw in lower:
                return category
    return None


# ---- Tier 1b: LLM atomic questions -------------------------------------- #

ATOMIC_PROMPT = """You are reading clinical-trial evidence to answer atomic questions about WHY this trial failed or was terminated. Answer each question based ONLY on the evidence below. Do not infer beyond the text.

Trial identifier: {nct_id}

Evidence:
---
{evidence_text}
---

Questions:
Q1. Does the evidence explicitly cite safety problems, adverse events, or toxicity as a reason the trial was stopped or changed?
    Answer: YES | NO | UNCLEAR
Q2. Does the evidence explicitly cite failure to meet efficacy endpoints, futility, or lack of therapeutic benefit?
    Answer: YES | NO | UNCLEAR
Q3. Does the evidence explicitly cite COVID-19 or the pandemic as an impact on the trial?
    Answer: YES | NO | UNCLEAR
Q4. Does the evidence explicitly cite enrollment, accrual, or recruitment difficulties?
    Answer: YES | NO | UNCLEAR
Q5. Does the evidence explicitly cite a sponsor/business/funding/strategic decision (not safety, not efficacy) as the reason the trial ended?
    Answer: YES | NO | UNCLEAR

Return ONLY a single JSON object in this exact shape, no prose before or after:
{{
  "q1_safety": "YES|NO|UNCLEAR",
  "q2_efficacy_failure": "YES|NO|UNCLEAR",
  "q3_covid": "YES|NO|UNCLEAR",
  "q4_recruitment": "YES|NO|UNCLEAR",
  "q5_business": "YES|NO|UNCLEAR",
  "evidence_quote": "<ONE verbatim quote from the evidence supporting the strongest YES, ≤30 words. Empty string if no YES.>"
}}"""


@dataclass
class AtomicAnswers:
    q1_safety: str = "UNCLEAR"
    q2_efficacy_failure: str = "UNCLEAR"
    q3_covid: str = "UNCLEAR"
    q4_recruitment: str = "UNCLEAR"
    q5_business: str = "UNCLEAR"
    evidence_quote: str = ""


_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_answers(text: str) -> AtomicAnswers:
    if not text:
        return AtomicAnswers()
    t = text.strip()
    payload: Optional[dict] = None
    try:
        payload = json.loads(t)
    except json.JSONDecodeError:
        m = _JSON_OBJ_RE.search(t)
        if m:
            try:
                payload = json.loads(m.group(0))
            except json.JSONDecodeError:
                payload = None
    if not payload:
        return AtomicAnswers()

    def norm(v):
        if not isinstance(v, str):
            return "UNCLEAR"
        v = v.strip().upper().replace(" ", "_").replace("-", "_")
        return v if v in ("YES", "NO", "UNCLEAR") else "UNCLEAR"

    return AtomicAnswers(
        q1_safety=norm(payload.get("q1_safety", "")),
        q2_efficacy_failure=norm(payload.get("q2_efficacy_failure", "")),
        q3_covid=norm(payload.get("q3_covid", "")),
        q4_recruitment=norm(payload.get("q4_recruitment", "")),
        q5_business=norm(payload.get("q5_business", "")),
        evidence_quote=str(payload.get("evidence_quote", "") or "")[:300],
    )


# ---- Evidence assembly -------------------------------------------------- #

def _assemble_evidence(
    why_stopped: str,
    research_results: list[ResearchResult],
    max_chars: int = 2800,
) -> str:
    """Concatenate whyStopped + web_context + literature snippets for the LLM.

    Composition (in priority order):
      1. whyStopped from the clinical_protocol registry
      2. web_context snippets (press releases, news) — primary source for
         business/funding/strategic reasons the registry doesn't disclose
      3. Top literature snippets

    web_context is surfaced before literature because business-reason
    terminations are rarely quotable from peer-reviewed pubs but often
    explicit in press releases / SEC filings / company news.
    """
    parts: list[str] = []
    if why_stopped:
        parts.append(f"whyStopped (ClinicalTrials.gov): {why_stopped}")

    web_count = 0
    for result in research_results:
        if result.error or result.agent_name != "web_context":
            continue
        for citation in (result.citations or [])[:20]:
            title = (citation.title or "").strip()
            snippet = (citation.snippet or "").strip()
            if not (title or snippet):
                continue
            parts.append(f"[web] {title}\n  {snippet[:500]}")
            web_count += 1
            if web_count >= 4:
                break
        if web_count >= 4:
            break

    lit_count = 0
    for result in research_results:
        if result.error or result.agent_name != "literature":
            continue
        for citation in (result.citations or [])[:20]:
            title = (citation.title or "").strip()
            snippet = (citation.snippet or "").strip()
            if not (title or snippet):
                continue
            parts.append(f"[pub] {title}\n  {snippet[:500]}")
            lit_count += 1
            if lit_count >= 4:
                break
        if lit_count >= 4:
            break

    body = "\n\n".join(parts)
    if len(body) > max_chars:
        body = body[:max_chars].rstrip() + " …"
    return body


# ---- Priority aggregator ------------------------------------------------ #

@dataclass
class FailureReasonAgg:
    value: str
    rule_name: str
    rule_description: str
    confidence: float
    trace: list[str] = field(default_factory=list)


def aggregate(
    why_stopped: str,
    tier0_match: Optional[str],
    answers: AtomicAnswers,
) -> FailureReasonAgg:
    """Apply rules R1–R7 in order.

    R1. Tier 0 whyStopped keyword hit → that category (deterministic, 0.90)
    R2. Atomic Q1=YES → Toxic/Unsafe (0.85)
    R3. Atomic Q2=YES → Ineffective for purpose (0.85)
    R4. Atomic Q3=YES → Due to covid (0.85)
    R5. Atomic Q4=YES → Recruitment issues (0.80)
    R6. Atomic Q5=YES → Business Reason (0.70)
    R7. default (all UNCLEAR/NO) → empty (unknown failure reason)
    """
    trace = [
        f"whyStopped: {why_stopped[:80] + '…' if len(why_stopped) > 80 else why_stopped or '(empty)'}",
        f"tier0_match: {tier0_match or 'none'}",
        f"atomic: q1_safety={answers.q1_safety} q2_eff={answers.q2_efficacy_failure} "
        f"q3_covid={answers.q3_covid} q4_recruit={answers.q4_recruitment} "
        f"q5_business={answers.q5_business}",
    ]
    if tier0_match:
        return FailureReasonAgg(
            value=tier0_match, rule_name="R1",
            rule_description=f"whyStopped registry keyword match: {tier0_match}",
            confidence=0.90,
            trace=trace + [f"R1 fired: registry whyStopped → {tier0_match}"],
        )
    if answers.q1_safety == "YES":
        return FailureReasonAgg(
            value="Toxic/Unsafe", rule_name="R2",
            rule_description="atomic Q1 (safety) YES",
            confidence=0.85,
            trace=trace + ["R2 fired: safety signal (priority: safety > efficacy > other)"],
        )
    if answers.q2_efficacy_failure == "YES":
        return FailureReasonAgg(
            value="Ineffective for purpose", rule_name="R3",
            rule_description="atomic Q2 (efficacy failure) YES",
            confidence=0.85,
            trace=trace + ["R3 fired: efficacy failure"],
        )
    if answers.q3_covid == "YES":
        return FailureReasonAgg(
            value="Due to covid", rule_name="R4",
            rule_description="atomic Q3 (COVID) YES",
            confidence=0.85,
            trace=trace + ["R4 fired: COVID impact"],
        )
    if answers.q4_recruitment == "YES":
        return FailureReasonAgg(
            value="Recruitment issues", rule_name="R5",
            rule_description="atomic Q4 (recruitment) YES",
            confidence=0.80,
            trace=trace + ["R5 fired: recruitment/accrual problem"],
        )
    if answers.q5_business == "YES":
        return FailureReasonAgg(
            value="Business Reason", rule_name="R6",
            rule_description="atomic Q5 (business decision) YES",
            confidence=0.70,
            trace=trace + ["R6 fired: business/sponsor/funding decision"],
        )
    return FailureReasonAgg(
        value="", rule_name="R7",
        rule_description="no atomic signal; reason not determinable",
        confidence=0.40,
        trace=trace + ["R7 fired: default empty — no keyword, no atomic YES"],
    )


# ---- Agent -------------------------------------------------------------- #

class FailureReasonAtomicAgent(BaseAnnotationAgent):
    """v42 atomic sibling of FailureReasonAgent.

    Runs only when metadata["outcome_atomic_result"] indicates a failed trial.
    If outcome_atomic says the trial is not failed, returns empty immediately
    (mirrors the legacy agent's short-circuit on non-failure outcomes).
    """

    field_name = "reason_for_failure_atomic"

    async def annotate(
        self,
        nct_id: str,
        research_results: list[ResearchResult],
        metadata: Optional[dict] = None,
    ) -> FieldAnnotation:
        outcome = (metadata or {}).get("outcome_atomic_result") or ""
        if outcome not in _FAILED_OUTCOMES:
            return FieldAnnotation(
                field_name=self.field_name,
                value="",
                confidence=0.0,
                reasoning=f"[ATOMIC-FR gated] outcome_atomic={outcome or '(none)'} not in {sorted(_FAILED_OUTCOMES)}",
                evidence=[],
                model_name="atomic-fr-gated",
                skip_verification=True,
                evidence_grade="deterministic",
            )

        why_stopped = _extract_why_stopped(research_results)
        tier0_match = _parse_why_stopped(why_stopped)

        answers = AtomicAnswers()
        model_used = ""
        llm_error = ""
        if not tier0_match:
            from app.services.ollama_client import ollama_client
            from app.services.config_service import config_service

            config = config_service.get()
            model = (
                getattr(config.orchestrator, "failure_reason_atomic_model", None)
                or _DEFAULT_ATOMIC_MODEL
            )
            model_used = model
            evidence_text = _assemble_evidence(why_stopped, research_results)
            if evidence_text:
                prompt = ATOMIC_PROMPT.format(
                    nct_id=nct_id, evidence_text=evidence_text,
                )
                try:
                    resp = await ollama_client.generate(
                        model=model,
                        prompt=prompt,
                        temperature=0.0,
                    )
                    raw = resp.get("response", "") if isinstance(resp, dict) else str(resp)
                    answers = _parse_answers(raw)
                except Exception as e:
                    llm_error = f"assessor_exception: {e}"
                    logger.warning("failure_reason_atomic %s LLM failed: %s", nct_id, e)

        agg = aggregate(why_stopped, tier0_match, answers)

        reasoning_lines = [
            f"[ATOMIC-FR {agg.rule_name}] {agg.value or '(empty)'} (conf={agg.confidence:.2f})",
            f"  rule: {agg.rule_description}",
        ]
        reasoning_lines.extend(f"  {line}" for line in agg.trace)
        if answers.evidence_quote:
            reasoning_lines.append(f"  quote: \"{answers.evidence_quote[:120]}\"")
        if llm_error:
            reasoning_lines.append(f"  llm_error: {llm_error}")

        return FieldAnnotation(
            field_name=self.field_name,
            value=agg.value,
            confidence=agg.confidence,
            reasoning="\n".join(reasoning_lines),
            evidence=[],
            model_name=f"atomic-fr-{model_used}" if model_used else "atomic-fr-deterministic",
            skip_verification=True,
            evidence_grade="deterministic" if agg.rule_name == "R1" else "llm",
        )
