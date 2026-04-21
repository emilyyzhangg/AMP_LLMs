"""
Outcome agent — Tier 2 Registry Signal Extractor (v42 atomic redesign).

Pure data extraction from ClinicalTrials.gov + ChEMBL + cross-trial research
results. No LLM, no keyword matching, no interpretation. Output is a structured
RegistrySignals object consumed by the atomic aggregator (Tier 3).

Also provides a Tier 0 deterministic pre-labeller for trivial registry statuses
(RECRUITING, WITHDRAWN) and for COMPLETED+hasResults+p-value-met cases.

Design principle (per ATOMIC_EVIDENCE_DECOMPOSITION.md §1.4): every field here
must be derivable from raw structured API data — nothing that could be ambiguous
or model-dependent. If a field needs interpretation, it belongs in Tier 1 (LLM
per-publication) or Tier 3 (aggregator rules).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.models.research import ResearchResult

logger = logging.getLogger("agent_annotate.annotation.outcome_registry")


# Registry status → Tier 0 deterministic outcome label. Only statuses where the
# meaning is unambiguous regardless of publications. TERMINATED and
# ACTIVE_NOT_RECRUITING intentionally absent — they defer to Tier 1+3.
_TIER0_STATUS_MAP: dict[str, str] = {
    "RECRUITING": "Recruiting",
    "NOT_YET_RECRUITING": "Recruiting",
    "ENROLLING_BY_INVITATION": "Recruiting",
    "WITHDRAWN": "Withdrawn",
    "SUSPENDED": "Unknown",
}


@dataclass
class PrimaryEndpoint:
    """A single primary endpoint with optional statistical result."""
    title: str = ""
    p_value: Optional[float] = None
    description: str = ""

    @property
    def met(self) -> Optional[bool]:
        """True if p<0.05, False if p>=0.05, None if no p-value parsed."""
        if self.p_value is None:
            return None
        return self.p_value < 0.05


@dataclass
class RegistrySignals:
    """All deterministic signals about a trial needed for outcome aggregation.

    Populated entirely from structured API responses — no text parsing, no
    keyword lookup, no LLM involvement.
    """

    # Core CT.gov fields
    registry_status: str = ""
    status_normalized: str = ""            # Upper-cased, underscore-separated
    has_results: Optional[bool] = None
    completion_date: str = ""
    days_since_completion: Optional[int] = None
    phase: str = ""
    phase_normalized: str = ""             # "PHASE1" / "PHASE2" / "PHASE3" / ""
    why_stopped: str = ""
    primary_endpoints: list[PrimaryEndpoint] = field(default_factory=list)

    # Cross-system signals
    drug_max_phase: Optional[int] = None   # ChEMBL max_phase (highest across molecules)
    ctgov_reference_pmids: set[str] = field(default_factory=set)

    # Derived flags
    stale_status: bool = False             # ACTIVE_* but completion date >180d past

    def is_phase1(self) -> bool:
        return self.phase_normalized == "PHASE1" or "PHASE1" in self.phase_normalized.split(",")

    def has_endpoint_with_pvalue(self) -> bool:
        return any(ep.p_value is not None for ep in self.primary_endpoints)


def _normalize_status(status: str) -> str:
    """CT.gov uses UPPER_SNAKE_CASE. Normalize variants like 'Active, not recruiting'."""
    if not status:
        return ""
    return status.strip().upper().replace(",", "").replace(" ", "_")


def _normalize_phase(phase: str) -> str:
    """Normalize phase strings to the CT.gov enum form (PHASE1..PHASE4, EARLY_PHASE1)."""
    if not phase:
        return ""
    # Already a list from designModule.phases — join with comma
    return phase.upper().replace(" ", "_")


def _parse_completion_date(date_str: str) -> Optional[int]:
    """Return days since completion. Negative = completion in the future. None if unparseable."""
    if not date_str:
        return None
    try:
        if len(date_str) == 7:          # YYYY-MM
            date_str = date_str + "-01"
        comp_dt = datetime.strptime(date_str, "%Y-%m-%d")
        return (datetime.now() - comp_dt).days
    except (ValueError, TypeError):
        return None


def _extract_ctgov_references(proto: dict) -> set[str]:
    """Pull PMIDs listed in CT.gov's referencesModule for this trial.

    These are authoritative "this publication is about this trial" evidence —
    used by the Tier 1a classifier to mark pubs as trial_specific without any
    keyword heuristic.
    """
    refs: set[str] = set()
    refs_mod = proto.get("referencesModule", {})
    for ref in refs_mod.get("references", []) or []:
        pmid = ref.get("pmid")
        if pmid:
            refs.add(str(pmid).strip())
    return refs


def extract_registry_signals(
    research_results: list[ResearchResult],
) -> RegistrySignals:
    """Build a RegistrySignals from raw research agent outputs.

    Reads clinical_protocol for CT.gov fields and chembl for drug advancement.
    """
    signals = RegistrySignals()

    for result in research_results:
        if result.error:
            continue

        if result.agent_name == "clinical_protocol" and result.raw_data:
            proto = result.raw_data.get(
                "protocol_section",
                result.raw_data.get("protocolSection", {}),
            )
            status_mod = proto.get("statusModule", {})
            design_mod = proto.get("designModule", {})

            if not signals.registry_status:
                signals.registry_status = status_mod.get("overallStatus", "") or ""
                signals.status_normalized = _normalize_status(signals.registry_status)

            hr = status_mod.get("hasResults", None)
            if hr is not None and signals.has_results is None:
                signals.has_results = (hr is True) or (str(hr).lower() == "true")

            for date_key in ("primaryCompletionDateStruct", "completionDateStruct"):
                ds = status_mod.get(date_key, {})
                if isinstance(ds, dict) and ds.get("date") and not signals.completion_date:
                    signals.completion_date = ds["date"]

            phases = design_mod.get("phases", [])
            if isinstance(phases, list) and phases and not signals.phase:
                signals.phase = ", ".join(phases)
                signals.phase_normalized = _normalize_phase(signals.phase)
            elif design_mod.get("phase") and not signals.phase:
                signals.phase = design_mod["phase"]
                signals.phase_normalized = _normalize_phase(signals.phase)

            if not signals.why_stopped:
                signals.why_stopped = status_mod.get("whyStopped", "") or ""

            signals.ctgov_reference_pmids |= _extract_ctgov_references(proto)

            results_section = result.raw_data.get("resultsSection", {})
            om_module = results_section.get("outcomeMeasuresModule", {}) if results_section else {}
            for om in om_module.get("outcomeMeasures", []) or []:
                ep = PrimaryEndpoint(
                    title=om.get("title", "") or "",
                    description=om.get("description", "") or "",
                )
                for analysis in om.get("analyses", []) or []:
                    pval_raw = analysis.get("pValue", "")
                    if pval_raw:
                        try:
                            ep.p_value = float(
                                str(pval_raw).replace("<", "").replace(">", "").strip()
                            )
                        except (ValueError, TypeError):
                            pass
                    stat_comment = analysis.get("statisticalComment", "")
                    if stat_comment:
                        ep.description = (ep.description + " " + stat_comment).strip()
                for group in om.get("groups", []) or []:
                    ep.description += f" [{group.get('title', '')}: {group.get('value', '')}]"
                signals.primary_endpoints.append(ep)

        elif result.agent_name == "chembl" and result.raw_data:
            # The chembl research agent stores molecules under per-drug keys
            # like "chembl_<drug>_molecules", not at top-level "molecules".
            # max_phase arrives as a string such as "3.0" or "-1.0" (ChEMBL's
            # "unknown" sentinel). Walk every *_molecules list and take the
            # highest non-negative integer phase across all molecules.
            for key, val in (result.raw_data or {}).items():
                if not key.endswith("_molecules") or not isinstance(val, list):
                    continue
                for mol in val:
                    raw = mol.get("max_phase") if isinstance(mol, dict) else None
                    if raw is None:
                        continue
                    try:
                        mp = int(float(raw))  # "3.0" → 3
                    except (ValueError, TypeError):
                        continue
                    if mp < 0:              # -1 = ChEMBL "unknown"
                        continue
                    if signals.drug_max_phase is None or mp > signals.drug_max_phase:
                        signals.drug_max_phase = mp

    signals.days_since_completion = _parse_completion_date(signals.completion_date)

    # Stale = registry claims Active but completion date is far past.
    # This is a factual calendar check, not a judgment — still safe for Tier 2.
    if signals.status_normalized in ("ACTIVE_NOT_RECRUITING",):
        if signals.days_since_completion is not None and signals.days_since_completion > 180:
            signals.stale_status = True

    return signals


def deterministic_prelabel(signals: RegistrySignals) -> Optional[str]:
    """Tier 0: return a canonical outcome if registry data alone determines it.

    Covers only truly unambiguous cases:
      - Simple enrollment-state statuses (RECRUITING, WITHDRAWN, SUSPENDED)
      - COMPLETED with hasResults=True AND a primary endpoint with p<0.05
        (stat-sig primary met is the clearest Positive signal in all of CT.gov)

    Everything else falls through to Tier 1+3.
    """
    if signals.status_normalized in _TIER0_STATUS_MAP:
        label = _TIER0_STATUS_MAP[signals.status_normalized]
        logger.info(
            "  outcome-atomic Tier 0 → %s (status=%s)",
            label, signals.registry_status,
        )
        return label

    if (
        signals.status_normalized == "COMPLETED"
        and signals.has_results is True
        and signals.primary_endpoints
    ):
        for ep in signals.primary_endpoints:
            if ep.met is True:
                logger.info(
                    "  outcome-atomic Tier 0 → Positive (COMPLETED + primary endpoint met, p=%s)",
                    ep.p_value,
                )
                return "Positive"

    return None
