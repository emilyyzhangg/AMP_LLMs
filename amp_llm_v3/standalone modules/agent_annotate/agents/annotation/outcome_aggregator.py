"""
Outcome agent — Tier 3 Deterministic Aggregator (v42, Phase 3).

Maps Tier 0 pre-label + Tier 2 RegistrySignals + Tier 1b PubVerdicts to a single
outcome label drawn from VALID_VALUES, using a fixed ordered rule set R1–R8.

No LLM involvement. No prompt tuning can change what this module decides. Every
verdict carries a named rule and the atomic inputs that fired it, so any R1/R2
annotator disagreement can be diagnosed as either an evidence gap (Tier 1 didn't
see the right pub), a question gap (atomic Q1–Q5 didn't ask the right thing), or
an aggregator gap (rule order/body wrong) — per the design doc §4.

Rule order (first match wins):

  TIER0 — short-circuit if Tier 0 already assigned a label (RECRUITING,
          WITHDRAWN, or COMPLETED+p<0.05→Positive).
  R1 — any POSITIVE pub-verdict AND no FAILED pub-verdict → "Positive"
  R2 — any FAILED pub-verdict AND no POSITIVE pub-verdict → "Failed - completed trial"
  R3 — both POSITIVE and FAILED present → verdict of most-recent pub
       (year from snippet text; trial_specific beats ambiguous as a tiebreaker;
       original list order as final tiebreaker)
  R4 — no trial_specific pubs AND registry status COMPLETED AND drug_max_phase ≥ 3
       (drug advanced to Phase III or beyond, OR ChEMBL max_phase 4 = approved) → "Positive"
  R5 — no trial_specific pubs AND registry status COMPLETED AND phase PHASE1
       AND ≥1 pub of any specificity exists → "Positive"
       (Phase I completion with any published mention is the Phase I success
       criterion per R1/R2 annotator consensus — completion itself is the win.)
  R6 — registry status ACTIVE_NOT_RECRUITING AND not stale → "Active, not recruiting"
  R7 — registry status TERMINATED AND no POSITIVE pub-verdict → "Terminated"
  R8 — otherwise → "Unknown"

The set of pub-verdicts considered by R1/R2/R3 is those with specificity
trial_specific or ambiguous AND verdict != INDETERMINATE — i.e. publications
where the Tier 1b LLM actually produced a usable signal. Purely general pubs
and INDETERMINATE verdicts don't vote.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from .outcome_pub_assessor import PubVerdict
from .outcome_pub_classifier import PubCandidate
from .outcome_registry_signals import RegistrySignals

logger = logging.getLogger("agent_annotate.annotation.outcome_aggregator")


# Canonical outcome labels (mirrors outcome_atomic.VALID_VALUES).
OUTCOME_POSITIVE = "Positive"
OUTCOME_FAILED = "Failed - completed trial"
OUTCOME_TERMINATED = "Terminated"
OUTCOME_ACTIVE = "Active, not recruiting"
OUTCOME_UNKNOWN = "Unknown"


@dataclass
class AggregatorResult:
    """Full aggregator output: the label plus the rule and inputs that chose it."""
    value: str
    rule_name: str                   # "TIER0" | "R1".."R8"
    rule_description: str            # one-liner suitable for UI / audit log
    confidence: float                # 0.95 TIER0, 0.90 R1/R2/R6/R7, 0.80 R3/R4, 0.70 R5, 0.50 R8
    trace: list[str] = field(default_factory=list)  # bullet lines for reasoning block


# ---- Year extraction for R3 ordering ------------------------------------- #

_YEAR_RE = re.compile(r"\b(19[89]\d|20[0-4]\d)\b")


def _year_hint(pub: PubCandidate) -> Optional[int]:
    """Best-effort publication year. Scans title + snippet for a 4-digit year in
    [1980, 2049]. Returns the largest match (papers often cite older references
    in their snippets; the latest year is typically the publication year)."""
    blob = f"{pub.title or ''} {pub.snippet or ''}"
    years = [int(m.group(0)) for m in _YEAR_RE.finditer(blob)]
    return max(years) if years else None


# ---- Verdict bookkeeping ------------------------------------------------- #

def _voting_pubs(
    pubs: list[tuple[PubCandidate, PubVerdict]],
) -> list[tuple[PubCandidate, PubVerdict]]:
    """The subset of pubs whose Tier 1b verdict actually counts for R1–R3.

    Rules:
      - specificity must be trial_specific or ambiguous (confident review →
        doesn't vote).
      - verdict must be POSITIVE or FAILED (INDETERMINATE doesn't vote — the
        LLM said nothing useful).
    """
    out: list[tuple[PubCandidate, PubVerdict]] = []
    for pub, pv in pubs:
        if pv.specificity in ("trial_specific", "ambiguous") and pv.verdict in ("POSITIVE", "FAILED"):
            out.append((pub, pv))
    return out


def _trial_specific_pubs(
    pubs: list[tuple[PubCandidate, PubVerdict]],
) -> list[tuple[PubCandidate, PubVerdict]]:
    """Only the strictly trial_specific pubs (Tier 1a Q1 or Q2 or Q3 fired)."""
    return [(pub, pv) for pub, pv in pubs if pv.specificity == "trial_specific"]


def _most_recent(
    pubs: list[tuple[PubCandidate, PubVerdict]],
) -> Optional[tuple[PubCandidate, PubVerdict]]:
    """Pick the 'most recent' pub for R3.

    Ordering (descending):
      1. year_hint desc (None sorts last)
      2. specificity (trial_specific beats ambiguous)
      3. original list index (later = more recent as a weak fallback)
    """
    if not pubs:
        return None

    def sort_key(ix_pub_pv):
        ix, (pub, pv) = ix_pub_pv
        year = _year_hint(pub) or -1
        spec_rank = 1 if pv.specificity == "trial_specific" else 0
        return (year, spec_rank, ix)

    indexed = list(enumerate(pubs))
    indexed.sort(key=sort_key, reverse=True)
    return indexed[0][1]


def _format_pub_ref(pub: PubCandidate, pv: PubVerdict, tag: str = "") -> str:
    """One-line trace entry for a pub, e.g. 'POSITIVE NCT:PMID=12345 q2=YES'."""
    pmid = pv.pmid or pub.pmid or "(no-pmid)"
    a = pv.answers
    detail_parts = []
    if a.q1_reports_results and a.q1_reports_results != "UNCLEAR":
        detail_parts.append(f"q1={a.q1_reports_results}")
    if a.q2_primary_met and a.q2_primary_met != "NA":
        detail_parts.append(f"q2={a.q2_primary_met}")
    if a.q3_efficacy and a.q3_efficacy not in ("NA", "UNCLEAR"):
        detail_parts.append(f"q3={a.q3_efficacy}")
    if a.q4_failure and a.q4_failure not in ("NA", "UNCLEAR"):
        detail_parts.append(f"q4={a.q4_failure}")
    if a.q5_advanced and a.q5_advanced != "UNCLEAR":
        detail_parts.append(f"q5={a.q5_advanced}")
    suffix = (" " + tag) if tag else ""
    detail = (" [" + " ".join(detail_parts) + "]") if detail_parts else ""
    return f"{pv.verdict:<13s} {pmid} ({pv.specificity}){detail}{suffix}"


# ---- Main aggregator ----------------------------------------------------- #

def aggregate(
    signals: RegistrySignals,
    pubs: list[tuple[PubCandidate, PubVerdict]],
    tier0_label: Optional[str] = None,
) -> AggregatorResult:
    """Run R1–R8 in order and return the first rule that fires."""
    voting = _voting_pubs(pubs)
    trial_specific = _trial_specific_pubs(pubs)
    has_positive = any(pv.verdict == "POSITIVE" for _, pv in voting)
    has_failed = any(pv.verdict == "FAILED" for _, pv in voting)

    base_trace = [
        f"registry: status={signals.status_normalized or '(none)'} "
        f"has_results={signals.has_results} phase={signals.phase_normalized or '(none)'} "
        f"days_since={signals.days_since_completion} stale={signals.stale_status} "
        f"drug_max_phase={signals.drug_max_phase}",
        f"pubs: total={len(pubs)} trial_specific={len(trial_specific)} "
        f"voting={len(voting)} pos={sum(1 for _, pv in voting if pv.verdict == 'POSITIVE')} "
        f"fail={sum(1 for _, pv in voting if pv.verdict == 'FAILED')}",
    ]

    # --- Tier 0 short-circuit -------------------------------------------- #
    if tier0_label:
        return AggregatorResult(
            value=tier0_label,
            rule_name="TIER0",
            rule_description=f"Tier 0 deterministic pre-label ({signals.status_normalized or 'statistical'})",
            confidence=0.95,
            trace=base_trace + [f"tier0 fired → {tier0_label}"],
        )

    # --- R1: POSITIVE without FAILED ------------------------------------- #
    if has_positive and not has_failed:
        positives = [(pub, pv) for pub, pv in voting if pv.verdict == "POSITIVE"]
        trace = base_trace + [
            f"R1 fired: {len(positives)} POSITIVE pub(s), 0 FAILED",
            *[f"  - {_format_pub_ref(pub, pv)}" for pub, pv in positives[:5]],
        ]
        if len(positives) > 5:
            trace.append(f"  - (+{len(positives) - 5} more)")
        return AggregatorResult(
            value=OUTCOME_POSITIVE,
            rule_name="R1",
            rule_description=f"{len(positives)} POSITIVE pub(s), 0 FAILED",
            confidence=0.90,
            trace=trace,
        )

    # --- R2: FAILED without POSITIVE ------------------------------------- #
    if has_failed and not has_positive:
        fails = [(pub, pv) for pub, pv in voting if pv.verdict == "FAILED"]
        trace = base_trace + [
            f"R2 fired: {len(fails)} FAILED pub(s), 0 POSITIVE",
            *[f"  - {_format_pub_ref(pub, pv)}" for pub, pv in fails[:5]],
        ]
        if len(fails) > 5:
            trace.append(f"  - (+{len(fails) - 5} more)")
        return AggregatorResult(
            value=OUTCOME_FAILED,
            rule_name="R2",
            rule_description=f"{len(fails)} FAILED pub(s), 0 POSITIVE",
            confidence=0.90,
            trace=trace,
        )

    # --- R3: mixed — most-recent-pub breaks tie -------------------------- #
    if has_positive and has_failed:
        winner = _most_recent(voting)
        if winner is not None:
            pub, pv = winner
            value = OUTCOME_POSITIVE if pv.verdict == "POSITIVE" else OUTCOME_FAILED
            year = _year_hint(pub)
            trace = base_trace + [
                f"R3 fired: mixed verdicts (POS + FAIL); most-recent pub wins",
                f"  winner: {_format_pub_ref(pub, pv, tag=f'year={year or 'unknown'}')}",
                *[f"  other: {_format_pub_ref(p, v, tag=f'year={_year_hint(p) or 'unknown'}')}"
                  for p, v in voting if (p, v) is not winner][:4],
            ]
            return AggregatorResult(
                value=value,
                rule_name="R3",
                rule_description=f"mixed POS/FAIL; most-recent pub ({pv.verdict})",
                confidence=0.80,
                trace=trace,
            )

    # --- R4: COMPLETED + no TS + drug advanced --------------------------- #
    if (
        signals.status_normalized == "COMPLETED"
        and len(trial_specific) == 0
        and signals.drug_max_phase is not None
        and signals.drug_max_phase >= 3
    ):
        return AggregatorResult(
            value=OUTCOME_POSITIVE,
            rule_name="R4",
            rule_description=(
                f"COMPLETED, no trial-specific pubs, drug_max_phase={signals.drug_max_phase} "
                f"(advanced to ≥Phase III / approved)"
            ),
            confidence=0.80,
            trace=base_trace + [
                f"R4 fired: ChEMBL max_phase={signals.drug_max_phase} implies drug advanced"
            ],
        )

    # --- R5: COMPLETED + no TS + PHASE1 + any pub ------------------------ #
    if (
        signals.status_normalized == "COMPLETED"
        and len(trial_specific) == 0
        and signals.is_phase1()
        and len(pubs) >= 1
    ):
        return AggregatorResult(
            value=OUTCOME_POSITIVE,
            rule_name="R5",
            rule_description=(
                f"COMPLETED Phase I, no trial-specific pubs, {len(pubs)} pub(s) "
                f"mention trial — Phase I completion with publication = success"
            ),
            confidence=0.70,
            trace=base_trace + [
                "R5 fired: Phase I + completed + any pub → Positive by annotator consensus"
            ],
        )

    # --- R6: ACTIVE_NOT_RECRUITING, not stale ---------------------------- #
    if signals.status_normalized == "ACTIVE_NOT_RECRUITING" and not signals.stale_status:
        return AggregatorResult(
            value=OUTCOME_ACTIVE,
            rule_name="R6",
            rule_description="registry status ACTIVE_NOT_RECRUITING, not stale",
            confidence=0.90,
            trace=base_trace + ["R6 fired: status=ACTIVE_NOT_RECRUITING, stale=False"],
        )

    # --- R7: TERMINATED + no POSITIVE ------------------------------------ #
    if signals.status_normalized == "TERMINATED" and not has_positive:
        return AggregatorResult(
            value=OUTCOME_TERMINATED,
            rule_name="R7",
            rule_description="registry status TERMINATED, no POSITIVE pub-verdict",
            confidence=0.90,
            trace=base_trace + ["R7 fired: status=TERMINATED, no positive pubs"],
        )

    # --- R8: fall-through ------------------------------------------------- #
    return AggregatorResult(
        value=OUTCOME_UNKNOWN,
        rule_name="R8",
        rule_description="no rule fired — insufficient evidence",
        confidence=0.50,
        trace=base_trace + ["R8 fired: default Unknown"],
    )
