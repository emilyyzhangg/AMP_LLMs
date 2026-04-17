"""
Outcome agent — Atomic Evidence Decomposition (v42).

Top-level orchestrator. Runs four tiers:

  Tier 0: deterministic pre-check from registry signals (Recruiting/Withdrawn/
          COMPLETED+p<0.05)
  Tier 1: per-publication atomic assessment
     1a: Trial-specificity classifier (deterministic, structural)
     1b: Result-Reporter LLM call per trial-specific publication (Phase 2)
  Tier 2: registry signal extraction (deterministic)
  Tier 3: deterministic aggregator R1-R8 (Phase 3)

Phase 1 (current): Tiers 0, 1a, 2 only. Tier 1b and 3 are stubs that return
AtomicDecision(value=None) so the outer annotate() fall back to marking the
trial as PENDING until Phases 2-3 land.

See docs/ATOMIC_EVIDENCE_DECOMPOSITION.md for the full design.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from agents.base import BaseAnnotationAgent
from app.models.annotation import FieldAnnotation
from app.models.research import ResearchResult, SourceCitation

from .outcome_registry_signals import (
    RegistrySignals,
    deterministic_prelabel,
    extract_registry_signals,
)
from .outcome_pub_classifier import (
    PubCandidate,
    Specificity,
    classify_all_pubs,
)

logger = logging.getLogger("agent_annotate.annotation.outcome_atomic")


VALID_VALUES = [
    "Positive",
    "Withdrawn",
    "Terminated",
    "Failed - completed trial",
    "Recruiting",
    "Unknown",
    "Active, not recruiting",
]


@dataclass
class AtomicSnapshot:
    """Full pre-aggregation state. Serialized into the annotation reasoning for
    audit trail and shadow-mode comparison with the legacy dossier pipeline."""
    nct_id: str
    tier0_label: Optional[str] = None
    signals: Optional[RegistrySignals] = None
    classified_pubs: list[tuple[PubCandidate, Specificity]] = field(default_factory=list)
    pub_verdicts: list[dict] = field(default_factory=list)   # populated in Phase 2
    aggregator_rule: str = ""                                 # populated in Phase 3
    final_value: Optional[str] = None                         # populated in Phase 3


class OutcomeAtomicAgent(BaseAnnotationAgent):
    """v42 atomic redesign of the outcome agent.

    Phase 1: runs Tier 0, builds Tier 2 signals, classifies Tier 1a pub
    specificity. Returns PENDING placeholder until Phases 2-3 implement LLM
    assessment and aggregation. Safe to instantiate but NOT yet wired into
    production — the shadow-mode orchestrator will import this class in Phase 4.
    """

    field_name = "outcome"

    async def annotate(
        self,
        nct_id: str,
        research_results: list[ResearchResult],
        metadata: Optional[dict] = None,
    ) -> FieldAnnotation:
        snapshot = self.compute_snapshot(nct_id, research_results)

        if snapshot.tier0_label is not None:
            return FieldAnnotation(
                field_name=self.field_name,
                value=snapshot.tier0_label,
                confidence=0.95,
                reasoning=self._format_reasoning(snapshot, tier="Tier 0"),
                evidence=[],
                model_name="atomic-deterministic",
                skip_verification=True,
                evidence_grade="deterministic",
            )

        # Phase 1 placeholder: LLM assessment & aggregation not yet implemented.
        # Return Unknown with snapshot so shadow-mode analysis can still inspect
        # Tier 0/1a/2 results without affecting any real annotation.
        return FieldAnnotation(
            field_name=self.field_name,
            value="Unknown",
            confidence=0.0,
            reasoning=(
                "[ATOMIC-PHASE-1 PENDING] Tiers 0/1a/2 computed; Tier 1b LLM "
                "assessor + Tier 3 aggregator not yet implemented.\n"
                + self._format_reasoning(snapshot, tier="Pre-aggregation")
            ),
            evidence=[],
            model_name="atomic-phase1",
            skip_verification=False,
            evidence_grade="llm",
        )

    def compute_snapshot(
        self,
        nct_id: str,
        research_results: list[ResearchResult],
    ) -> AtomicSnapshot:
        """Run Tiers 0, 1a, and 2. Pure — no LLM, no I/O. Reusable by tests
        and by the Phase 4 shadow-mode orchestrator."""
        signals = extract_registry_signals(research_results)
        tier0 = deterministic_prelabel(signals)
        classified = classify_all_pubs(research_results, nct_id)

        logger.info(
            "  outcome-atomic snapshot %s — status=%s tier0=%s pubs=%d "
            "(ts=%d / gen=%d / amb=%d) stale=%s max_phase=%s endpoints=%d",
            nct_id,
            signals.status_normalized or "(none)",
            tier0 or "(none)",
            len(classified),
            sum(1 for _, s in classified if s == "trial_specific"),
            sum(1 for _, s in classified if s == "general"),
            sum(1 for _, s in classified if s == "ambiguous"),
            signals.stale_status,
            signals.drug_max_phase,
            len(signals.primary_endpoints),
        )

        return AtomicSnapshot(
            nct_id=nct_id,
            tier0_label=tier0,
            signals=signals,
            classified_pubs=classified,
            final_value=tier0,  # Until Phase 3, tier0 is the only decisive path.
        )

    @staticmethod
    def _format_reasoning(snapshot: AtomicSnapshot, tier: str) -> str:
        s = snapshot.signals
        if s is None:
            return f"[{tier}] (no signals)"
        pubs = snapshot.classified_pubs
        lines = [
            f"[{tier}] NCT={snapshot.nct_id}",
            f"  status={s.registry_status or '(unknown)'} (norm={s.status_normalized or '(none)'})",
            f"  has_results={s.has_results} phase={s.phase_normalized or s.phase or '(unknown)'}",
            f"  completion_date={s.completion_date or '(unknown)'} "
            f"days_since={s.days_since_completion} stale={s.stale_status}",
            f"  primary_endpoints={len(s.primary_endpoints)} "
            f"(with p-value: {sum(1 for ep in s.primary_endpoints if ep.p_value is not None)})",
            f"  drug_max_phase={s.drug_max_phase} "
            f"ctgov_references={len(s.ctgov_reference_pmids)}",
            f"  pubs: {len(pubs)} total "
            f"({sum(1 for _, sp in pubs if sp == 'trial_specific')} trial-specific, "
            f"{sum(1 for _, sp in pubs if sp == 'general')} general, "
            f"{sum(1 for _, sp in pubs if sp == 'ambiguous')} ambiguous)",
        ]
        return "\n".join(lines)
