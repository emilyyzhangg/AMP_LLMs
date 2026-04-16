"""
Outcome Annotation Agent (v39 — fix publication-anchored skip_verification).

v38 redesign: replaces the fragile 9-layer cascade (deterministic → Pass 1 → Pass 2
→ pub override → heuristics → safety nets → keyword rescue → verification → reconciliation)
with a 3-tier system:

  Tier 1: Structured evidence dossier extraction (no LLM)
    - Extracts all machine-readable signals from ClinicalTrials.gov, publications,
      and drug databases into a structured dict before any LLM call.

  Tier 2: Expanded deterministic rules on dossier
    - RECRUITING/ENROLLING → Recruiting
    - WITHDRAWN → Withdrawn
    - COMPLETED + hasResults + primary endpoint met/failed → Positive/Failed
    - COMPLETED + hasResults + no parseable endpoints → Positive
    - TERMINATED + whyStopped efficacy/futility → appropriate value
    - ACTIVE_NOT_RECRUITING removed from deterministic — falls through to Tier 3
      where stale status detection and publications are checked.

  Tier 3: Single-pass LLM with dossier
    - Feeds the LLM the structured dossier (not raw evidence text)
    - Simple prompt with clear rules — 30 lines vs previous 275-line PASS2_PROMPT
    - Publication-anchored verification: when annotator's Positive call is backed
      by specific PMIDs, set skip_verification to prevent reconciler from
      overriding with "Unknown" (fixes 5/13 v37b disagreements).

Prior version history: v4/v11 accuracy fixes, v17 heuristic override, v21 TERMINATED fix,
v25 publication-priority, v26 TERMINATED override fix, v32 regex + safety nets,
v36 stale status detection, v37b keyword expansion.
"""

import re
import logging
from datetime import datetime
from typing import Optional

from agents.base import BaseAnnotationAgent
from app.models.research import ResearchResult, SourceCitation
from app.models.annotation import FieldAnnotation

logger = logging.getLogger("agent_annotate.annotation.outcome")

VALID_VALUES = [
    "Positive",
    "Withdrawn",
    "Terminated",
    "Failed - completed trial",
    "Recruiting",
    "Unknown",
    "Active, not recruiting",
]

# v32: Section headers produced by PASS1_PROMPT (lowercased).
# Used as regex boundary instead of \n[A-Z] which never matches on lowered text.
# Ported from failure_reason.py v29 fix (commit dce4466d).
_SECTION_BOUNDARY = (
    r"\n(?:registry status|trial phase|published results?"
    r"|result valence|results posted|completion date|why stopped)"
)


def _has_publication_id(identifier: str) -> bool:
    """Check if an identifier represents a real publication reference.

    v39: Literature agents return identifiers as 'PMC:12134401' or 'PMID:39938411',
    never pure numeric. The previous .isdigit() check always returned False,
    making publication-anchored skip_verification completely non-functional.
    """
    if not identifier:
        return False
    if identifier.upper().startswith(("PMID:", "PMC:", "DOI:")):
        return True
    if identifier.isdigit():
        return True
    return False


def _classify_publication(title_or_snippet: str, nct_id: str) -> str:
    """Classify a publication as 'trial_specific' or 'general'.

    v41: Prevents generic review articles from contributing valence keywords.
    Trial-specific = reports results from this specific trial.
    General = review articles, overviews, editorials, commentaries.
    """
    text = title_or_snippet.lower()
    nct_lower = nct_id.lower() if nct_id else ""

    _TRIAL_SIGNALS = [
        nct_lower,
        "randomized", "randomised",
        "phase i ", "phase ii ", "phase iii ", "phase 1 ", "phase 2 ", "phase 3 ",
        "primary endpoint", "primary outcome", "secondary endpoint",
        "placebo-controlled", "placebo controlled",
        "open-label", "open label", "double-blind", "double blind",
        "single-arm", "single arm",
        "dose-escalation", "dose escalation", "first-in-human", "first in human",
        "interim analysis", "interim results", "final results", "final analysis",
        "patients were enrolled", "subjects were enrolled",
        "intention-to-treat", "intent-to-treat", "per-protocol",
        "safety and efficacy of", "a study of", "a trial of",
        "our study", "this study", "we report", "we conducted",
    ]

    for signal in _TRIAL_SIGNALS:
        if signal and signal in text:
            return "trial_specific"

    _GENERAL_SIGNALS = [
        "review", "overview", "advances in", "current state", "state of the art",
        "emerging", "future directions", "future of", "perspective", "commentary",
        "editorial", "landscape", "pipeline", "next-generation", "next generation",
        "systematic review", "meta-analysis", "narrative review", "mini-review",
        "recent developments", "recent advances",
    ]

    for signal in _GENERAL_SIGNALS:
        if signal in text:
            return "general"

    return "general"


# --------------------------------------------------------------------------- #
#  Deterministic outcome mapping (v11)
# --------------------------------------------------------------------------- #

_DETERMINISTIC_STATUSES = {
    "RECRUITING": "Recruiting",
    "NOT_YET_RECRUITING": "Recruiting",
    "ENROLLING_BY_INVITATION": "Recruiting",
    "WITHDRAWN": "Withdrawn",
    "SUSPENDED": "Unknown",
    # v21: TERMINATED removed — some TERMINATED trials have positive published results.
    # v38: ACTIVE_NOT_RECRUITING removed — many trials with this status have stale
    # registry data and already completed/published. Let the dossier pipeline check
    # for publications and stale completion dates before deciding.
}


def _deterministic_outcome(research_results: list) -> FieldAnnotation | None:
    """Map clear-cut registry statuses deterministically.

    v11: Also handles COMPLETED trials with hasResults.
    v38: ACTIVE_NOT_RECRUITING removed — falls through to dossier pipeline.
    """
    for result in research_results:
        if result.error or result.agent_name != "clinical_protocol":
            continue
        if not result.raw_data:
            continue
        proto = result.raw_data.get("protocol_section", result.raw_data.get("protocolSection", {}))
        status_mod = proto.get("statusModule", {})
        overall_status = status_mod.get("overallStatus", "")

        # Simple status mappings (RECRUITING, WITHDRAWN, etc.)
        if overall_status in _DETERMINISTIC_STATUSES:
            value = _DETERMINISTIC_STATUSES[overall_status]
            logger.info(f"  outcome: deterministic → {value} (registry status: {overall_status})")
            return FieldAnnotation(
                field_name="outcome", value=value, confidence=0.95,
                reasoning=f"[Deterministic v38] Registry status '{overall_status}' → '{value}'",
                evidence=[], model_name="deterministic", skip_verification=True,
            )

    return None


# --------------------------------------------------------------------------- #
#  Structured Evidence Dossier (v38)
# --------------------------------------------------------------------------- #

def _build_evidence_dossier(research_results: list, nct_id: str = "") -> dict:
    """Extract all machine-readable signals into a structured dossier.

    This runs BEFORE any LLM call and captures every signal the LLM would
    need — but structurally, with no interpretation needed.
    """
    dossier = {
        "registry_status": "",
        "has_results": None,
        "completion_date": "",
        "days_since_completion": None,
        "phase": "",
        "why_stopped": "",
        "primary_endpoints": [],     # list of {title, met, p_value, description}
        "publications": [],          # list of {pmid, title, year, source, classification}
        "publication_count": 0,
        "trial_specific_count": 0,   # v41: publications classified as trial-specific
        "drug_max_phase": None,      # from ChEMBL
        "positive_keywords": [],     # all positive keywords (efficacy + safety)
        "negative_keywords": [],     # failure keywords found in publication snippets
        "efficacy_keywords": [],     # v41: efficacy-only subset of positive
        "safety_keywords": [],       # v41: safety-only subset of positive
        "stale_status": False,       # completion date >180 days ago but status says Active
    }

    # v41: Split positive keywords into efficacy (supports Positive) and safety (does NOT).
    _EFFICACY_KW = [
        "efficacy", "effective", "safe and effective",
        "improved", "improvement", "benefit", "successful",
        "clinical benefit", "objective response", "complete response",
        "partial response", "clinical activity", "antitumor activity",
        "met primary", "met the primary", "results showed", "results demonstrated",
        "approved", "granted approval",
    ]
    _SAFETY_KW = [
        "well-tolerated", "well tolerated", "favorable", "promising",
        "immunogenic", "safe and immunogenic",
        "immune response", "t cell response", "cd8+", "cd4+",
        "enhanced immune", "immune activation",
    ]
    _POSITIVE_KW = _EFFICACY_KW + _SAFETY_KW
    _NEGATIVE_KW = [
        "failed", "did not meet", "did not demonstrate", "did not achieve",
        "did not show", "no significant", "no benefit", "no improvement",
        "failed to demonstrate", "failed to meet", "failed primary",
        "lack of efficacy", "ineffective", "no efficacy", "futility",
        "inferior", "not effective", "negative",
        "unacceptable", "not tolerated", "dose-limiting", "safety concern",
        "serious adverse event", "discontinued due to",
    ]

    for result in research_results:
        if result.error:
            continue

        # --- ClinicalTrials.gov structured data ---
        if result.agent_name == "clinical_protocol" and result.raw_data:
            proto = result.raw_data.get("protocol_section", result.raw_data.get("protocolSection", {}))
            status_mod = proto.get("statusModule", {})
            design_mod = proto.get("designModule", {})

            if not dossier["registry_status"]:
                dossier["registry_status"] = status_mod.get("overallStatus", "")

            hr = status_mod.get("hasResults", None)
            if hr is not None:
                dossier["has_results"] = hr is True or str(hr).lower() == "true"

            # Completion date
            for date_key in ("primaryCompletionDateStruct", "completionDateStruct"):
                ds = status_mod.get(date_key, {})
                if isinstance(ds, dict) and ds.get("date") and not dossier["completion_date"]:
                    dossier["completion_date"] = ds["date"]

            # Phase
            phases = design_mod.get("phases", [])
            if isinstance(phases, list) and phases and not dossier["phase"]:
                dossier["phase"] = ", ".join(phases)
            elif design_mod.get("phase") and not dossier["phase"]:
                dossier["phase"] = design_mod["phase"]

            # Why stopped
            dossier["why_stopped"] = status_mod.get("whyStopped", "") or ""

            # Results section: primary endpoints
            results_section = result.raw_data.get("resultsSection", {})
            if results_section:
                om_module = results_section.get("outcomeMeasuresModule", {})
                for om in om_module.get("outcomeMeasures", []):
                    ep = {"title": om.get("title", ""), "met": None,
                          "p_value": None, "description": om.get("description", "")}
                    # Check for statistical analyses
                    for analysis in om.get("analyses", []):
                        pval = analysis.get("pValue", "")
                        if pval:
                            try:
                                ep["p_value"] = float(pval.replace("<", "").replace(">", "").strip())
                            except (ValueError, TypeError):
                                pass
                        stat_comment = analysis.get("statisticalComment", "")
                        if stat_comment:
                            ep["description"] += " " + stat_comment
                    # Check groups for result values
                    for group in om.get("groups", []):
                        ep["description"] += f" [{group.get('title','')}: {group.get('value','')}]"
                    dossier["primary_endpoints"].append(ep)

        # --- Publication data ---
        if result.agent_name == "literature":
            for citation in getattr(result, "citations", []):
                pmid = getattr(citation, "identifier", "") or ""
                title = getattr(citation, "snippet", "") or ""
                pub = {
                    "pmid": pmid,
                    "title": title[:300],
                    "year": getattr(citation, "year", None),
                    "source": getattr(citation, "source_name", ""),
                    "classification": _classify_publication(title, nct_id),
                }
                dossier["publications"].append(pub)

        # --- v41: Scan ONLY trial-specific literature for valence keywords ---
        # Generic reviews from OpenAlex/CrossRef contain drug-class keywords
        # ("well-tolerated", "favorable") that don't describe this trial's results.
        if result.agent_name == "literature":
            for citation in getattr(result, "citations", []):
                snippet_text = (getattr(citation, "snippet", "") or "")
                if _classify_publication(snippet_text, nct_id) != "trial_specific":
                    continue
                combined = f"{snippet_text.lower()} {(getattr(citation, 'identifier', '') or '').lower()}"
                for kw in _POSITIVE_KW:
                    if kw in combined and kw not in dossier["positive_keywords"]:
                        dossier["positive_keywords"].append(kw)
                for kw in _NEGATIVE_KW:
                    if kw in combined and kw not in dossier["negative_keywords"]:
                        dossier["negative_keywords"].append(kw)
                for kw in _EFFICACY_KW:
                    if kw in combined and kw not in dossier["efficacy_keywords"]:
                        dossier["efficacy_keywords"].append(kw)
                for kw in _SAFETY_KW:
                    if kw in combined and kw not in dossier["safety_keywords"]:
                        dossier["safety_keywords"].append(kw)

        # --- ChEMBL drug advancement ---
        if result.agent_name == "chembl" and result.raw_data:
            for mol in result.raw_data.get("molecules", []):
                max_phase = mol.get("max_phase")
                if max_phase and (dossier["drug_max_phase"] is None
                                  or max_phase > dossier["drug_max_phase"]):
                    dossier["drug_max_phase"] = max_phase

    # Compute derived fields
    dossier["publication_count"] = len(dossier["publications"])
    dossier["trial_specific_count"] = sum(
        1 for p in dossier["publications"] if p.get("classification") == "trial_specific"
    )

    if dossier["completion_date"]:
        try:
            # CT.gov dates are YYYY-MM-DD or YYYY-MM
            date_str = dossier["completion_date"]
            if len(date_str) == 7:  # YYYY-MM
                date_str += "-01"
            comp_dt = datetime.strptime(date_str, "%Y-%m-%d")
            dossier["days_since_completion"] = (datetime.now() - comp_dt).days
        except (ValueError, TypeError):
            pass

    # Stale status detection
    status_upper = dossier["registry_status"].upper()
    if status_upper in ("ACTIVE_NOT_RECRUITING", "ACTIVE, NOT RECRUITING"):
        if dossier["days_since_completion"] is not None and dossier["days_since_completion"] > 180:
            dossier["stale_status"] = True

    return dossier


def _dossier_deterministic(dossier: dict) -> FieldAnnotation | None:
    """Apply expanded deterministic rules on the structured dossier.

    Handles cases where the outcome can be determined without any LLM call.
    """
    status = dossier["registry_status"].upper()
    has_results = dossier["has_results"]
    phase = dossier["phase"].upper() if dossier["phase"] else ""
    endpoints = dossier["primary_endpoints"]
    days_since = dossier["days_since_completion"]
    why_stopped = dossier["why_stopped"].lower()

    # v41: ACTIVE_NOT_RECRUITING with future/recent completion → deterministic Active
    status_normalized = status.replace(",", "").replace(" ", "_").upper()
    if status_normalized == "ACTIVE_NOT_RECRUITING":
        if days_since is not None and days_since <= 0:
            logger.info(f"  outcome: v41 Active guard — completion in future, returning Active")
            return FieldAnnotation(
                field_name="outcome", value="Active, not recruiting",
                confidence=0.95, reasoning=f"[v41 Active guard] completion date in future ({dossier['completion_date']})",
                evidence=[], model_name="deterministic", skip_verification=True,
            )
        if days_since is not None and days_since <= 180:
            logger.info(f"  outcome: v41 Active guard — completion {days_since}d ago (<180), returning Active")
            return FieldAnnotation(
                field_name="outcome", value="Active, not recruiting",
                confidence=0.90, reasoning=f"[v41 Active guard] completion {days_since} days ago (<180 threshold)",
                evidence=[], model_name="deterministic", skip_verification=True,
            )
        # days_since > 180 or None → stale or unknown, fall through to LLM

    # COMPLETED + hasResults + primary endpoints parseable
    if status == "COMPLETED" and has_results is True and endpoints:
        # Check if any endpoint has a p-value we can interpret
        for ep in endpoints:
            if ep.get("p_value") is not None:
                if ep["p_value"] < 0.05:
                    logger.info(f"  outcome: v38 dossier deterministic → Positive (primary endpoint met, p={ep['p_value']})")
                    return FieldAnnotation(
                        field_name="outcome", value="Positive", confidence=0.95,
                        reasoning=f"[Dossier v38] COMPLETED + hasResults + primary endpoint met (p={ep['p_value']:.4f}): {ep['title'][:100]}",
                        evidence=[], model_name="deterministic", skip_verification=True,
                    )
                else:
                    logger.info(f"  outcome: v38 dossier deterministic → Failed (primary endpoint not met, p={ep['p_value']})")
                    return FieldAnnotation(
                        field_name="outcome", value="Failed - completed trial", confidence=0.90,
                        reasoning=f"[Dossier v38] COMPLETED + hasResults + primary endpoint not met (p={ep['p_value']:.4f}): {ep['title'][:100]}",
                        evidence=[], model_name="deterministic", skip_verification=False,
                    )

    # COMPLETED + hasResults=true + no parseable endpoints → Positive (H4: results were posted)
    if status == "COMPLETED" and has_results is True:
        logger.info("  outcome: v38 dossier deterministic → Positive (COMPLETED + hasResults=true)")
        return FieldAnnotation(
            field_name="outcome", value="Positive", confidence=0.90,
            reasoning="[Dossier v38] COMPLETED + hasResults=true → Positive (results posted confirms data)",
            evidence=[], model_name="deterministic", skip_verification=False,
        )

    # TERMINATED + clear reason
    if status == "TERMINATED":
        _FUTILITY_REASONS = ["futility", "lack of efficacy", "ineffective", "no benefit",
                             "did not meet", "unmet primary"]
        _EFFICACY_REASONS = ["efficacy", "early positive", "stopped early for"]
        _BUSINESS_REASONS = ["funding", "business", "sponsor", "strategic", "administrative",
                             "organizational", "slow enrollment", "low enrollment",
                             "slow accrual", "enrollment", "recruitment"]
        if any(r in why_stopped for r in _FUTILITY_REASONS):
            logger.info(f"  outcome: v38 dossier deterministic → Failed (TERMINATED for: {why_stopped[:80]})")
            return FieldAnnotation(
                field_name="outcome", value="Failed - completed trial", confidence=0.90,
                reasoning=f"[Dossier v38] TERMINATED for futility/lack of efficacy: {why_stopped[:100]}",
                evidence=[], model_name="deterministic", skip_verification=False,
            )
        if any(r in why_stopped for r in _EFFICACY_REASONS):
            logger.info(f"  outcome: v38 dossier deterministic → Positive (TERMINATED early for efficacy)")
            return FieldAnnotation(
                field_name="outcome", value="Positive", confidence=0.85,
                reasoning=f"[Dossier v38] TERMINATED early for efficacy: {why_stopped[:100]}",
                evidence=[], model_name="deterministic", skip_verification=False,
            )
        if any(r in why_stopped for r in _BUSINESS_REASONS):
            logger.info(f"  outcome: v38 dossier deterministic → Terminated (business/operational: {why_stopped[:80]})")
            return FieldAnnotation(
                field_name="outcome", value="Terminated", confidence=0.90,
                reasoning=f"[Dossier v38] TERMINATED for business/operational reason: {why_stopped[:100]}",
                evidence=[], model_name="deterministic", skip_verification=True,
            )

    return None


def _format_dossier_for_llm(dossier: dict, nct_id: str) -> str:
    """Format the structured dossier as a concise text block for the LLM."""
    lines = [f"Trial: {nct_id}"]
    lines.append(f"Registry Status: {dossier['registry_status'] or 'UNKNOWN'}")
    if dossier["phase"]:
        lines.append(f"Phase: {dossier['phase']}")
    if dossier["completion_date"]:
        age = ""
        if dossier["days_since_completion"] is not None:
            days = dossier["days_since_completion"]
            if days > 0:
                age = f" ({days} days ago)"
            else:
                age = f" (in {-days} days)"
        lines.append(f"Completion Date: {dossier['completion_date']}{age}")
    lines.append(f"Results Posted: {'Yes' if dossier['has_results'] is True else 'No' if dossier['has_results'] is False else 'Unknown'}")
    if dossier["stale_status"]:
        lines.append("WARNING: Registry status may be outdated — completion date was >6 months ago")
    if dossier["why_stopped"]:
        lines.append(f"Why Stopped: {dossier['why_stopped']}")

    if dossier["primary_endpoints"]:
        lines.append(f"Primary Endpoints ({len(dossier['primary_endpoints'])} measures):")
        for i, ep in enumerate(dossier["primary_endpoints"][:3]):
            pval = f", p={ep['p_value']}" if ep.get("p_value") is not None else ""
            lines.append(f"  {i+1}. {ep['title'][:120]}{pval}")

    if dossier["publications"]:
        ts = dossier.get("trial_specific_count", 0)
        gen = dossier["publication_count"] - ts
        lines.append(f"Publications Found: {dossier['publication_count']} ({ts} trial-specific, {gen} reviews/general)")
        for i, pub in enumerate(dossier["publications"][:5]):
            year = f" ({pub['year']})" if pub.get("year") else ""
            pmid = f" {pub['pmid']}" if _has_publication_id(pub.get("pmid", "")) else ""
            tag = " [TRIAL-SPECIFIC]" if pub.get("classification") == "trial_specific" else " [GENERAL]"
            lines.append(f"  {i+1}. {pub['title'][:140]}{year}{pmid}{tag}")
    else:
        lines.append("Publications Found: 0")

    if dossier["drug_max_phase"]:
        lines.append(f"Drug Advanced To: Phase {dossier['drug_max_phase']}")

    if dossier.get("efficacy_keywords"):
        lines.append(f"Efficacy Signals: {', '.join(dossier['efficacy_keywords'][:6])}")
    if dossier.get("safety_keywords"):
        lines.append(f"Safety-Only Signals: {', '.join(dossier['safety_keywords'][:6])}")
    if dossier["negative_keywords"]:
        lines.append(f"Negative Signals in Evidence: {', '.join(dossier['negative_keywords'][:8])}")

    return "\n".join(lines)

# v38: Single-pass dossier-based LLM prompt (replaces 2-pass PASS1+PASS2)
DOSSIER_PROMPT = """You are a clinical trial outcome specialist. You have a structured evidence summary for this trial. Determine the outcome.

{dossier_text}

RULES (follow in order):
1. REGISTRY STATUS for ongoing trials:
   - If status is ACTIVE_NOT_RECRUITING and completion date is in the future or recent → "Active, not recruiting"
   - Only if completion date is stale (>6 months past) should you consider other evidence.
2. PUBLICATION QUALITY:
   - Only [TRIAL-SPECIFIC] publications report actual results from this trial.
   - [GENERAL] publications are reviews or overviews — they are NOT trial results.
   - Safety-Only Signals (well-tolerated, immunogenic, favorable) do NOT indicate Positive outcome.
3. "Positive" requires EFFICACY evidence from trial-specific publications:
   - Primary endpoint met, clinical benefit demonstrated, regulatory approval, phase advancement based on efficacy.
   - Safety/tolerability alone is NOT sufficient. A well-tolerated drug that did not show efficacy is NOT Positive.
4. "Failed - completed trial" requires evidence of failure (endpoints not met, futility, no efficacy).
5. TERMINATED with no publications and no results posted → "Terminated"
6. COMPLETED with no trial-specific publications and no results posted → "Unknown"
7. Phase I: safety AND biological activity/efficacy signals → "Positive". Safety/tolerability alone → "Unknown".
8. Default → "Unknown"

CRITICAL: "Positive" REQUIRES efficacy evidence. Safety/tolerability alone is NEVER sufficient.
CRITICAL: Do NOT base your decision on [GENERAL] review articles.

VALID VALUES: Positive, Withdrawn, Terminated, Failed - completed trial, Recruiting, Unknown, Active, not recruiting

Format your response EXACTLY as:
Outcome: [one value from above]
Evidence: [cite the specific source]
Reasoning: [brief chain of thought]"""

class OutcomeAgent(BaseAnnotationAgent):
    """v38: Determines trial outcome using structured evidence dossier."""

    field_name = "outcome"

    def _get_model(self, config) -> str:
        """Select model based on hardware profile."""
        profile = config.orchestrator.hardware_profile
        if profile == "server":
            return getattr(config.orchestrator, "server_premium_model", "kimi-k2-thinking")
        annotation_model = getattr(config.orchestrator, "annotation_model", None)
        if annotation_model:
            return annotation_model
        for model_key, model_cfg in config.verification.models.items():
            if model_cfg.role == "annotator":
                return model_cfg.name
        return "llama3.1:8b"

    async def annotate(
        self,
        nct_id: str,
        research_results: list[ResearchResult],
        metadata: Optional[dict] = None,
    ) -> FieldAnnotation:
        # Tier 0: Simple deterministic statuses (RECRUITING, WITHDRAWN, SUSPENDED)
        det_result = _deterministic_outcome(research_results)
        if det_result is not None:
            return det_result

        # --- Tier 1: Build structured evidence dossier ---
        dossier = _build_evidence_dossier(research_results, nct_id)
        logger.info(
            f"  outcome: v38 dossier for {nct_id} — status={dossier['registry_status']}, "
            f"hasResults={dossier['has_results']}, pubs={dossier['publication_count']}, "
            f"endpoints={len(dossier['primary_endpoints'])}, "
            f"pos_kw={len(dossier['positive_keywords'])}, neg_kw={len(dossier['negative_keywords'])}, "
            f"stale={dossier['stale_status']}"
        )

        # --- Tier 2: Expanded deterministic rules on dossier ---
        dossier_det = _dossier_deterministic(dossier)
        if dossier_det is not None:
            return dossier_det

        # --- Tier 3: LLM with structured dossier ---
        from app.services.config_service import config_service
        from app.services.ollama_client import ollama_client

        config = config_service.get()
        is_server = config.orchestrator.hardware_profile == "server"
        max_cites = 50 if is_server else 30
        max_snippet = 500 if is_server else 250
        primary_model = self._get_model(config)

        # Build evidence text for LLM context (publications, trial data)
        evidence_text, cited_sources = self.build_structured_evidence(
            nct_id, research_results,
            max_citations=max_cites,
            max_snippet_chars=max_snippet,
        )

        # EDAM guidance injection
        edam_guidance = await self.get_edam_guidance(nct_id, evidence_text)
        if edam_guidance:
            evidence_text = edam_guidance + "\n\n" + evidence_text

        # Format dossier for LLM
        dossier_text = _format_dossier_for_llm(dossier, nct_id)
        llm_prompt = DOSSIER_PROMPT.format(dossier_text=dossier_text)

        try:
            logger.info(f"  outcome: v38 LLM pass for {nct_id}")
            response = await ollama_client.generate(
                model=primary_model,
                prompt=llm_prompt + "\n\nFull research evidence:\n" + evidence_text,
                temperature=config.ollama.field_temperatures.get("outcome", config.ollama.temperature),
            )
            llm_output = response.get("response", "")
        except Exception as e:
            logger.warning(f"  outcome: LLM call failed for {nct_id}: {e}")
            # Fallback: use dossier signals directly
            value = self._infer_from_dossier(dossier)
            return FieldAnnotation(
                field_name=self.field_name, value=value, confidence=0.3,
                reasoning=f"LLM failed ({e}), inferred from dossier: {dossier_text[:300]}",
                evidence=cited_sources[:10], model_name=primary_model,
            )

        value = self._parse_value(llm_output)
        reasoning = self._parse_reasoning(llm_output)

        # --- Post-LLM safety nets ---

        # If LLM said Unknown/Active but dossier has strong publication signals, override
        if value in ("Unknown", "Active, not recruiting"):
            override = self._dossier_publication_override(dossier, value)
            if override and override != value:
                logger.info(f"  outcome: v38 dossier publication override {value} → {override}")
                reasoning = f"[v38 dossier pub override: {value} → {override}] " + reasoning
                value = override

        # Terminated safety net: Unknown + TERMINATED + no results → Terminated
        if value == "Unknown" and dossier["registry_status"].upper() == "TERMINATED":
            if not dossier["has_results"]:
                logger.info("  outcome: v38 Terminated safety net")
                value = "Terminated"
                reasoning = "[v38 Terminated safety net] " + reasoning

        # hasResults override: Unknown + COMPLETED + results posted → Positive
        if value == "Unknown" and dossier["registry_status"].upper() == "COMPLETED":
            if dossier["has_results"] is True:
                logger.info("  outcome: v38 hasResults override (COMPLETED + results posted)")
                value = "Positive"
                reasoning = "[v38 hasResults override] " + reasoning

        # --- Determine if verification should be skipped (publication-anchored) ---
        # v39: Fixed identifier check — PMC:xxx/PMID:xxx formats now recognized.
        # Added mixed-evidence guard: skip only when valence is unambiguous.
        skip_verification = False
        has_pmid_evidence = any(
            _has_publication_id(p.get("pmid", "")) for p in dossier["publications"]
        )
        # v41: Use efficacy keywords (not safety-only) for skip_verification
        if value == "Positive" and has_pmid_evidence and dossier.get("efficacy_keywords") and not dossier["negative_keywords"]:
            skip_verification = True
            logger.info(f"  outcome: v41 publication-anchored Positive (efficacy) — skip_verification=True")
        if value == "Failed - completed trial" and has_pmid_evidence and dossier["negative_keywords"] and not dossier.get("efficacy_keywords", dossier["positive_keywords"]):
            skip_verification = True
            logger.info(f"  outcome: v39 publication-anchored Failed — skip_verification=True")

        full_reasoning = f"[Dossier] {dossier_text[:400]}\n[LLM decision] {reasoning}"
        citation_quality = sum(c.quality_score for c in cited_sources[:10]) / max(len(cited_sources[:10]), 1)

        return FieldAnnotation(
            field_name=self.field_name,
            value=value,
            confidence=citation_quality,
            reasoning=full_reasoning,
            evidence=cited_sources[:10],
            model_name=primary_model,
            skip_verification=skip_verification,
        )

    @staticmethod
    def _infer_from_dossier(dossier: dict) -> str:
        """Fallback: infer outcome from dossier when LLM fails."""
        status = dossier["registry_status"].upper()
        if status == "TERMINATED":
            return "Terminated"
        if status in ("ACTIVE_NOT_RECRUITING", "ACTIVE, NOT RECRUITING"):
            if not dossier["stale_status"]:
                return "Active, not recruiting"
            # v41: stale Active — use efficacy keywords only (not safety)
            if dossier["stale_status"] and dossier.get("efficacy_keywords", dossier["positive_keywords"]):
                return "Positive"
        if status == "COMPLETED":
            if dossier["has_results"] is True:
                return "Positive"
            if dossier.get("efficacy_keywords", dossier["positive_keywords"]) and not dossier["negative_keywords"]:
                return "Positive"
        return "Unknown"

    @staticmethod
    def _dossier_publication_override(dossier: dict, current_value: str) -> str | None:
        """v41: Override Unknown/Active when dossier has clear publication signals.

        Uses efficacy keywords (not safety-only) and trial-specific publication counts.
        """
        efficacy = dossier.get("efficacy_keywords", [])
        neg = dossier["negative_keywords"]
        trial_specific = dossier.get("trial_specific_count", dossier["publication_count"])
        stale = dossier["stale_status"]
        status = dossier["registry_status"].upper()

        # Strong negative signals always override
        _STRONG_ADVERSE = ["unacceptable", "not tolerated", "dose-limiting",
                           "safety concern", "serious adverse event", "discontinued due to"]
        if any(kw in neg for kw in _STRONG_ADVERSE):
            return "Failed - completed trial"

        # v41: Trial-specific publications with EFFICACY signals → Positive
        if trial_specific > 0 and efficacy and not neg:
            return "Positive"

        # Trial-specific publications with negative signals → Failed
        if trial_specific > 0 and neg and not efficacy:
            return "Failed - completed trial"

        # Stale Active status — use efficacy keywords only
        if current_value == "Active, not recruiting" and stale:
            if efficacy:
                return "Positive"
            if neg:
                return "Failed - completed trial"

        # COMPLETED with results posted but LLM said Unknown
        if status == "COMPLETED" and dossier["has_results"] is True:
            return "Positive"

        # v41: Removed Phase I auto-positive (any pub = Positive was too broad)
        # v41: Removed Phase II/III >10yr backstop (absence of evidence ≠ positive)

        return None

    def _parse_value(self, text: str) -> str:
        match = re.search(r"Outcome:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
        if match:
            raw = match.group(1).strip()
            lower = raw.lower()

            # Exact match first
            for valid in VALID_VALUES:
                if valid.lower() == lower:
                    return valid

            # Fuzzy matching
            if "positive" in lower:
                return "Positive"
            if "withdrawn" in lower:
                return "Withdrawn"
            if "terminated" in lower:
                return "Terminated"
            if "failed" in lower or "negative" in lower:
                return "Failed - completed trial"
            if "active" in lower and "not recruiting" in lower:
                return "Active, not recruiting"
            if "recruiting" in lower or "enrolling" in lower or "not yet" in lower:
                return "Recruiting"
            if "active" in lower:
                return "Active, not recruiting"
        return "Unknown"

    def _parse_reasoning(self, text: str) -> str:
        match = re.search(r"Reasoning:\s*(.+?)(?:\n\n|$)", text, re.DOTALL)
        if match:
            return match.group(1).strip()[:500]
        return text[:500]
