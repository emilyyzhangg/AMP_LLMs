"""
Outcome agent — Atomic Evidence Decomposition (v42).

Top-level orchestrator. Runs four tiers:

  Tier 0: deterministic pre-check from registry signals (Recruiting/Withdrawn/
          COMPLETED+p<0.05)
  Tier 1: per-publication atomic assessment
     1a: Trial-specificity classifier (deterministic, structural)
     1b: Per-publication LLM call (gemma3:12b, 5 atomic Y/N/UNCLEAR questions)
  Tier 2: registry signal extraction (deterministic)
  Tier 3: deterministic aggregator R1-R8

Phase 4 wires all four tiers end-to-end. `field_name = "outcome_atomic"` so the
agent runs alongside (not in place of) the legacy dossier outcome agent during
shadow mode. The orchestrator skips this agent unless
`config.orchestrator.outcome_atomic_shadow` is True.

See docs/ATOMIC_EVIDENCE_DECOMPOSITION.md for the full design.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from agents.base import BaseAnnotationAgent
from app.config import RESULTS_DIR
from app.models.annotation import FieldAnnotation
from app.models.research import ResearchResult

from .outcome_aggregator import AggregatorResult, aggregate
from .outcome_pub_assessor import (
    PubAssessmentCache,
    PubAssessor,
    PubVerdict,
)
from .outcome_pub_classifier import (
    PubCandidate,
    Specificity,
    classify_all_pubs,
    extract_drug_names,
)
from .outcome_registry_signals import (
    RegistrySignals,
    deterministic_prelabel,
    extract_registry_signals,
)

logger = logging.getLogger("agent_annotate.annotation.outcome_atomic")


# Canonical label list — mirrors outcome.VALID_VALUES so downstream analysis
# can treat "outcome_atomic" values with the same enumeration as "outcome".
VALID_VALUES = [
    "Positive",
    "Withdrawn",
    "Terminated",
    "Failed - completed trial",
    "Recruiting",
    "Unknown",
    "Active, not recruiting",
]


# Default model for the Tier 1b LLM assessor. Gemma 3 12B is a natural fit for
# focused reading-comprehension tasks and keeps qwen3:14b free for the legacy
# dossier pipeline during shadow mode. Overridable via config.
_DEFAULT_ATOMIC_MODEL = "gemma3:12b"

# Per-(NCT, PMID, text-hash) cache lives alongside other job artifacts so runs
# are reproducible and replayable without re-spending LLM calls.
_ATOMIC_CACHE_DIR = RESULTS_DIR / "atomic_pub_cache"


@dataclass
class AtomicSnapshot:
    """Full pre-aggregation state. Serialized into the annotation reasoning for
    audit trail and shadow-mode comparison with the legacy dossier pipeline."""
    nct_id: str
    tier0_label: Optional[str] = None
    signals: Optional[RegistrySignals] = None
    classified_pubs: list[tuple[PubCandidate, Specificity]] = field(default_factory=list)
    pub_verdicts: list[dict] = field(default_factory=list)
    aggregator_rule: str = ""
    final_value: Optional[str] = None


class OutcomeAtomicAgent(BaseAnnotationAgent):
    """v42 atomic redesign of the outcome agent — Phase 4 shadow-mode wiring.

    Runs all four tiers end-to-end. Stores under ``field_name="outcome_atomic"``
    so the legacy ``outcome`` annotation remains authoritative downstream. The
    orchestrator conditionally skips this agent via
    ``config.orchestrator.outcome_atomic_shadow`` — default OFF to avoid
    unexpected LLM spend on prod.
    """

    field_name = "outcome_atomic"

    async def annotate(
        self,
        nct_id: str,
        research_results: list[ResearchResult],
        metadata: Optional[dict] = None,
    ) -> FieldAnnotation:
        # Tier 0/1a/2: pure, deterministic snapshot
        snapshot = self.compute_snapshot(nct_id, research_results)

        # Tier 0 short-circuit — aggregator honors the pre-label.
        if snapshot.tier0_label is not None:
            agg = aggregate(snapshot.signals, [], tier0_label=snapshot.tier0_label)
            return self._to_annotation(snapshot, agg, pub_verdicts=[])

        # Tier 1b: LLM-assess each trial_specific or ambiguous pub.
        drug_names = extract_drug_names(research_results)
        pub_verdicts = await self._assess_pubs(
            nct_id, snapshot.classified_pubs, drug_names
        )

        # Tier 3: deterministic aggregator over verdicts + registry signals.
        pubs_for_agg = [
            (pub, pv) for (pub, _spec), pv in zip(snapshot.classified_pubs, pub_verdicts)
        ]
        agg = aggregate(snapshot.signals, pubs_for_agg, tier0_label=None)
        snapshot.pub_verdicts = [self._verdict_to_dict(pv) for pv in pub_verdicts]
        snapshot.aggregator_rule = agg.rule_name
        snapshot.final_value = agg.value
        return self._to_annotation(snapshot, agg, pub_verdicts=pub_verdicts)

    # --- Tier 0/1a/2 snapshot (pure; reused by tests) --------------------- #
    def compute_snapshot(
        self,
        nct_id: str,
        research_results: list[ResearchResult],
    ) -> AtomicSnapshot:
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
        )

    # --- Tier 1b: LLM assessor loop --------------------------------------- #
    async def _assess_pubs(
        self,
        nct_id: str,
        classified_pubs: list[tuple[PubCandidate, Specificity]],
        drug_names,
    ) -> list[PubVerdict]:
        """Return a PubVerdict per input pub (INDETERMINATE placeholder for
        confident-general pubs — they don't get LLM cycles).

        Applies a hard cap via orchestrator.outcome_atomic_max_voting_pubs on
        the number of LLM calls per NCT. Overflow pubs get an INDETERMINATE
        placeholder with error='skipped_over_cap' so the aggregator still
        sees a 1:1 pub/verdict mapping.
        """
        # Import here to avoid requiring ollama at module load (keeps the
        # module testable offline).
        from app.services.ollama_client import ollama_client
        from app.services.config_service import config_service

        # Model + cache + cap
        config = config_service.get()
        model = getattr(config.orchestrator, "outcome_atomic_model", None) or _DEFAULT_ATOMIC_MODEL
        cap = int(getattr(config.orchestrator, "outcome_atomic_max_voting_pubs", 0) or 0)
        cache = PubAssessmentCache(_ATOMIC_CACHE_DIR)
        assessor = PubAssessor(
            model=model,
            ollama_client=ollama_client,
            cache=cache,
            temperature=0.0,
        )

        drug_list = sorted(drug_names) if drug_names else []
        voting_idxs = self._select_voting_indices(classified_pubs, cap)

        verdicts: list[PubVerdict] = []
        for idx, (pub, spec) in enumerate(classified_pubs):
            if spec == "general":
                # Confident-general pubs don't vote — synthesize a placeholder
                # so the aggregator still sees a 1:1 pub/verdict mapping.
                verdicts.append(
                    PubVerdict(
                        nct_id=nct_id,
                        pmid=pub.pmid,
                        source=pub.source,
                        specificity=spec,
                        verdict="INDETERMINATE",
                        error="skipped_general",
                    )
                )
                continue
            if idx not in voting_idxs:
                # Over cap — synthesize placeholder, no LLM call.
                verdicts.append(
                    PubVerdict(
                        nct_id=nct_id,
                        pmid=pub.pmid,
                        source=pub.source,
                        specificity=spec,
                        verdict="INDETERMINATE",
                        error="skipped_over_cap",
                    )
                )
                continue
            try:
                pv = await assessor.assess(nct_id, pub, spec, drug_list)
            except Exception as e:
                # Never raise out of annotate; record and continue.
                logger.warning("atomic assess %s pmid=%s crashed: %s", nct_id, pub.pmid, e)
                pv = PubVerdict(
                    nct_id=nct_id,
                    pmid=pub.pmid,
                    source=pub.source,
                    specificity=spec,
                    verdict="INDETERMINATE",
                    error=f"assessor_exception: {e}",
                )
            verdicts.append(pv)
        return verdicts

    @staticmethod
    def _select_voting_indices(
        classified_pubs: list[tuple[PubCandidate, Specificity]],
        cap: int,
    ) -> set[int]:
        """Pick which pub indices get Tier 1b LLM calls when a cap is set.

        Priority (desc): trial_specific > ambiguous; then year desc (most
        recent wins); then snippet length desc (richer text wins). `general`
        pubs never get LLM cycles and are excluded from the cap entirely.
        Returns the set of indices in `classified_pubs` that are allowed to
        call the assessor. Cap of 0 means unlimited.
        """
        # Import here to avoid a circular at module import time.
        from .outcome_aggregator import _year_hint

        candidates: list[tuple[int, int, int, int]] = []
        for idx, (pub, spec) in enumerate(classified_pubs):
            if spec == "general":
                continue
            spec_rank = 1 if spec == "trial_specific" else 0
            year = _year_hint(pub) or 0
            length = len(pub.snippet or "")
            candidates.append((spec_rank, year, length, idx))

        if cap <= 0 or cap >= len(candidates):
            return {c[3] for c in candidates}

        candidates.sort(key=lambda t: (t[0], t[1], t[2]), reverse=True)
        return {c[3] for c in candidates[:cap]}

    # --- FieldAnnotation builder ------------------------------------------ #
    def _to_annotation(
        self,
        snapshot: AtomicSnapshot,
        agg: AggregatorResult,
        pub_verdicts: list[PubVerdict],
    ) -> FieldAnnotation:
        reasoning = self._format_reasoning(snapshot, agg, pub_verdicts)
        # Model name identifies which path produced the verdict for audit.
        model_name = (
            "atomic-deterministic"
            if agg.rule_name == "TIER0" or not pub_verdicts
            else f"atomic-{_DEFAULT_ATOMIC_MODEL}"
        )
        return FieldAnnotation(
            field_name=self.field_name,
            value=agg.value,
            confidence=agg.confidence,
            reasoning=reasoning,
            evidence=[],
            model_name=model_name,
            skip_verification=True,  # Shadow-mode: don't burn the verifier pool.
            evidence_grade="deterministic" if not pub_verdicts else "llm",
        )

    @staticmethod
    def _verdict_to_dict(pv: PubVerdict) -> dict:
        """Flatten a PubVerdict into the reasoning-serializable form."""
        a = pv.answers
        return {
            "pmid": pv.pmid,
            "source": pv.source,
            "specificity": pv.specificity,
            "verdict": pv.verdict,
            "model": pv.model,
            "error": pv.error,
            "cached": pv.cached,
            "answers": {
                "q1": a.q1_reports_results,
                "q2": a.q2_primary_met,
                "q3": a.q3_efficacy,
                "q4": a.q4_failure,
                "q5": a.q5_advanced,
                "evidence_quote": a.evidence_quote,
            },
        }

    @staticmethod
    def _format_reasoning(
        snapshot: AtomicSnapshot,
        agg: AggregatorResult,
        pub_verdicts: list[PubVerdict],
    ) -> str:
        header = [
            f"[ATOMIC {agg.rule_name}] {agg.value} (conf={agg.confidence:.2f})",
            f"  rule: {agg.rule_description}",
        ]
        s = snapshot.signals
        if s is not None:
            header.append(
                f"  registry: status={s.registry_status or '(none)'} "
                f"phase={s.phase_normalized or s.phase or '(none)'} "
                f"has_results={s.has_results} completion={s.completion_date or '(none)'} "
                f"days_since={s.days_since_completion} stale={s.stale_status} "
                f"drug_max_phase={s.drug_max_phase}"
            )
            header.append(
                f"  pubs: {len(snapshot.classified_pubs)} total "
                f"({sum(1 for _, sp in snapshot.classified_pubs if sp == 'trial_specific')} ts, "
                f"{sum(1 for _, sp in snapshot.classified_pubs if sp == 'general')} gen, "
                f"{sum(1 for _, sp in snapshot.classified_pubs if sp == 'ambiguous')} amb)"
            )
        if pub_verdicts:
            voting = [pv for pv in pub_verdicts if pv.verdict in ("POSITIVE", "FAILED")]
            header.append(
                f"  voting: {len(voting)} pub(s) "
                f"({sum(1 for pv in voting if pv.verdict == 'POSITIVE')} POS, "
                f"{sum(1 for pv in voting if pv.verdict == 'FAILED')} FAIL)"
            )
            for pv in voting[:6]:
                a = pv.answers
                quote = f' "{a.evidence_quote[:80]}"' if a.evidence_quote else ""
                header.append(
                    f"    - {pv.verdict:<13s} {pv.pmid or '(no-pmid)'} ({pv.specificity}) "
                    f"q1={a.q1_reports_results} q2={a.q2_primary_met} "
                    f"q3={a.q3_efficacy} q4={a.q4_failure} q5={a.q5_advanced}{quote}"
                )
            if len(voting) > 6:
                header.append(f"    - (+{len(voting) - 6} more)")
        if agg.trace:
            header.append("  aggregator trace:")
            header.extend(f"    {line}" for line in agg.trace)
        return "\n".join(header)
