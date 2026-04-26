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
        # v42.6.15 (2026-04-24): review-shape patterns that Job #81 missed
        # and caused 2 Positive over-calls (NCT04449926 BCG vaccines for
        # dementia; NCT04461795 CGRP monoclonal antibodies). These titles
        # lacked the word "review" but are structurally reviews — they
        # describe drug CLASSES, list multiple drugs, or cover a treatment
        # topic without reporting from a specific trial.
        "and other",            # "BCG and Other Vaccines Against Dementia"
        "monoclonal antibodies", "receptor antagonists",  # drug-class plurals
        "inhibitors in",        # e.g. "XX inhibitors in migraine prevention"
        "agonists in", "agonists for",
        " in prevention", " in treatment",  # topic-review framing
        " in migraine prevention", " in dementia",  # condition-level
        "part i:", "part ii:", "part iii:",  # series/book format
        "vaccines against", "therapy for",  # overview framing
    ]

    # v42.6.15: Drug-class plural-form detection. Review titles usually
    # discuss a CLASS of drugs ("CGRP monoclonal antibodies", "peptide-based
    # vaccines") whereas trial reports name a SPECIFIC drug and trial design.
    # Treat as review if the title uses a class term AND has no explicit
    # trial marker (no "randomized", "phase", NCT ID etc. caught above).
    _CLASS_PLURALS = (
        "peptide-based vaccines", "peptide based vaccines",
        "vaccines against", "antibodies against",
    )
    for cp in _CLASS_PLURALS:
        if cp in text:
            return "general"

    for signal in _GENERAL_SIGNALS:
        if signal in text:
            return "general"

    # v41b: Default to trial_specific — only explicit review signals → general.
    # Literature agent searches by NCT ID, so most results ARE about the trial.
    return "trial_specific"


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
        # v42.7.2 (2026-04-26): expand from literature-only to all publication-
        # shaped agents (OpenAlex, Semantic Scholar, CrossRef, bioRxiv).
        # Previously only `literature` agent's citations contributed to the
        # dossier's publication list — meaning ~4 agents' worth of citation
        # signal was discarded by the outcome dossier. Pub classifier already
        # has v42.6.15 review-shape detection, so adding more pubs is safe.
        #
        # v42.7.4 (2026-04-26): two-tier source weighting. The publication-list
        # gets all 5 agents (the LLM benefits from broader context). The
        # keyword scan (which feeds efficacy_keywords/negative_keywords used
        # by the deterministic override) is restricted to peer-reviewed
        # sources only — bioRxiv preprints + Semantic Scholar/CrossRef
        # aggregators added noise to the keyword tally, costing -2.1pp on
        # outcome accuracy in Job #88. RfF retained the +7.6pp gain because
        # it primarily uses the LLM-visible pub list.
        _PUB_AGENTS = ("literature", "openalex", "semantic_scholar",
                       "crossref", "biorxiv")
        # High-quality peer-reviewed sources only — used for valence keyword
        # extraction where false positives matter (override fires deterministically).
        _PUB_AGENTS_HIGH_QUALITY = ("literature", "openalex")
        if result.agent_name in _PUB_AGENTS:
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
        # v42.7.2: same agent expansion as publication-data block above.
        # v42.7.4: REVERTED to high-quality-only for keyword scan. Outcome
        # regressions in #88 traced to noisy bioRxiv/CrossRef/SS keyword hits.
        if result.agent_name in _PUB_AGENTS_HIGH_QUALITY:
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
        # v42.6.10 (2026-04-23, Job #78 analysis): Restore narrow ANR Active guard.
        # v41's broad days_since<=180 block was removed in v41b because it masked
        # trials with real published positive results. But the removal swung too
        # far: past-completion ANR trials with NO publications default to "Unknown"
        # from the LLM, when they're clearly still Active, not recruiting.
        #
        # Compromise: if ANR + not stale + zero trial-specific publications + no
        # hasResults signal, apply deterministic Active. The presence of any
        # trial-specific pub falls through to the LLM/aggregator, preserving the
        # v41b win where publication-priority override correctly finds Positive
        # for trials with published efficacy data.
        if (not dossier["stale_status"]
                and dossier.get("trial_specific_count", 0) == 0
                and not dossier["has_results"]):
            logger.info(
                f"  outcome: v42.6.10 ANR guard — no pubs, not stale → Active, not recruiting"
            )
            return FieldAnnotation(
                field_name="outcome", value="Active, not recruiting",
                confidence=0.85,
                reasoning=(
                    f"[v42.6.10 ANR guard] status=ACTIVE_NOT_RECRUITING, "
                    f"days_since_completion={days_since}, not stale, "
                    f"0 trial-specific publications, no hasResults — trial is still "
                    f"actively running without published outcomes"
                ),
                evidence=[], model_name="deterministic", skip_verification=True,
            )
        # Otherwise (stale OR has publications OR hasResults): fall through to LLM
        # so dossier/publication-priority override can rule.

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
1. REGISTRY STATUS is the default anchor for ongoing trials:
   - If CT.gov status is ACTIVE_NOT_RECRUITING → "Active, not recruiting" (default) UNLESS a publication explicitly states the primary endpoint was met (→ "Positive") or the trial failed (→ "Failed - completed trial"). Staleness alone does NOT flip to "Unknown" — CT.gov is still reporting the trial as active.
   - If CT.gov status is RECRUITING / NOT_YET_RECRUITING / ENROLLING_BY_INVITATION → "Recruiting".
   - If status is WITHDRAWN → "Withdrawn".
2. PUBLICATION QUALITY:
   - Only [TRIAL-SPECIFIC] publications report actual results from this trial.
   - [GENERAL] publications are reviews or overviews — they are NOT trial results.
   - Safety-Only Signals (well-tolerated, immunogenic, favorable) do NOT indicate Positive outcome.
3. "Positive" requires ONE OF these specific signals from a trial-specific publication:
   (a) Explicit statement that the PRIMARY ENDPOINT was met / achieved.
   (b) Statistically significant result on the primary endpoint (p-value < 0.05 reported).
   (c) Regulatory approval (FDA/EMA/etc.) of the drug for this specific indication.
   (d) Explicit phase advancement citing the trial's positive results.
   DO NOT mark Positive based on:
   - "Efficacy signals" or "clinical benefit" language without a primary-endpoint statement.
   - "Immunogenic", "T cell response", "immune activation" — these are biomarkers, not efficacy.
   - Phase I safety + biological activity alone.
   - Review articles describing the drug class.
   - Abstract titles that use efficacy words without detailed results.
4. "Failed - completed trial" requires evidence of failure (primary endpoint not met, futility declared, no efficacy demonstrated).
5. TERMINATED with no publications and no results posted → "Terminated"
6. COMPLETED with no trial-specific publications and no results posted → "Unknown"
7. Phase I: only mark Positive with an explicit primary-endpoint-met statement. Safety + biological activity without that statement → "Unknown".
8. Default when evidence is inconclusive → "Unknown" (not "Positive").

CRITICAL: "Positive" REQUIRES a specific primary-endpoint-met / p<0.05 / approval / phase-advancement signal. Vague "efficacy" or "benefit" language is NOT sufficient.
CRITICAL: If in doubt, choose "Unknown". Over-calling Positive is a more harmful error than under-calling it.
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

        # v42.6.12 (2026-04-24) — Registry-status safety net.
        # Job #80 revealed that the v42.6.11 tightened prompt was under-calling
        # stale ANR trials as "Unknown" (11 of 13 such miscalls). When CT.gov
        # still reports an active/recruiting status, that IS the trial's current
        # state regardless of staleness — GT annotators use the CT.gov status,
        # not "Unknown". The strong-efficacy override above still promotes to
        # Positive when trial-specific evidence actually exists; remaining
        # Unknowns here have no such evidence and should fall back to the
        # canonical status.
        _STATUS_TO_CANONICAL_OUTCOME = {
            "ACTIVE_NOT_RECRUITING": "Active, not recruiting",
            "ACTIVE, NOT RECRUITING": "Active, not recruiting",
            "RECRUITING": "Recruiting",
            "NOT_YET_RECRUITING": "Recruiting",
            "ENROLLING_BY_INVITATION": "Recruiting",
        }
        status_upper = dossier["registry_status"].upper()
        if value == "Unknown" and status_upper in _STATUS_TO_CANONICAL_OUTCOME:
            canonical = _STATUS_TO_CANONICAL_OUTCOME[status_upper]
            logger.info(f"  outcome: v42.6.12 registry-status safety net Unknown → {canonical}")
            reasoning = f"[v42.6.12 registry-status safety net: Unknown → {canonical} (CT.gov status={status_upper})] " + reasoning
            value = canonical

        # --- Determine if verification should be skipped (publication-anchored) ---
        # v39: Fixed identifier check — PMC:xxx/PMID:xxx formats now recognized.
        # Added mixed-evidence guard: skip only when valence is unambiguous.
        skip_verification = False
        has_pmid_evidence = any(
            _has_publication_id(p.get("pmid", "")) for p in dossier["publications"]
        )
        # v42.6.11: Skip verification for Positive only with STRONG efficacy signals.
        # Previously any efficacy keyword would short-circuit verification, locking
        # in over-called Positives without the verifier pool getting a look.
        if (value == "Positive" and has_pmid_evidence
                and self._has_strong_efficacy(dossier.get("efficacy_keywords", []))
                and not dossier["negative_keywords"]):
            skip_verification = True
            logger.info(f"  outcome: v42.6.11 publication-anchored Positive (STRONG efficacy) — skip_verification=True")
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

    @classmethod
    def _infer_from_dossier(cls, dossier: dict) -> str:
        """Fallback: infer outcome from dossier when LLM fails.

        v42.6.11: tightened — loose efficacy keywords no longer produce Positive
        inferences. Must see a STRONG signal (primary endpoint met, p<0.05,
        approval) to infer Positive from keyword bag alone. Structural signals
        like hasResults=True still promote to Positive.
        """
        status = dossier["registry_status"].upper()
        if status == "TERMINATED":
            return "Terminated"
        if status in ("ACTIVE_NOT_RECRUITING", "ACTIVE, NOT RECRUITING"):
            # v42.6.12: CT.gov ANR → Active regardless of staleness, unless
            # STRONG efficacy signal → Positive. Previous code (v42.6.11)
            # dropped stale ANR to Unknown implicitly via the next branch;
            # restore Active as the default.
            if cls._has_strong_efficacy(dossier.get("efficacy_keywords", [])):
                return "Positive"
            return "Active, not recruiting"
        if status == "COMPLETED":
            if dossier["has_results"] is True:
                return "Positive"
            # v42.6.11: require STRONG efficacy (not any keyword) for Positive
            if (cls._has_strong_efficacy(dossier.get("efficacy_keywords", []))
                    and not dossier["negative_keywords"]):
                return "Positive"
        return "Unknown"

    # v42.6.11 (2026-04-24): Strong-efficacy subset required to override LLM
    # Unknown → Positive. Previous override fired on ANY efficacy keyword
    # from any trial-specific pub (including review-like "clinical benefit"
    # and "antitumor activity" language), producing 9 of 11 Positive over-calls
    # seen in Job #79. These terms are verbatim signals that actually imply
    # the primary endpoint was met; loose efficacy words are NOT sufficient.
    #
    # v42.6.14 (2026-04-24): narrowed the "approved" family. Bare "approved"
    # caught review-article language like "EpiVacCorona was approved for
    # emergency use in Russia" and over-called NCT04527575 in Job #81. Require
    # a regulatory qualifier ("FDA approved", "EMA approved", "regulatory
    # approval") or explicit approval/authorization for this indication.
    _STRONG_EFFICACY = [
        "primary endpoint was met", "primary endpoint met",
        "primary endpoint achieved", "met the primary endpoint",
        "met primary", "met the primary",
        # v42.6.16 (2026-04-25): expand primary-endpoint-anchored phrases.
        # Job #83 had 6 Positive under-calls where pubs reported the trial
        # met its endpoint but used a different verb pattern than the v42.6.11
        # list. Require "primary" anchor to keep noise low.
        "achieved primary endpoint", "achieved its primary endpoint",
        "primary outcome was met", "primary outcome achieved",
        "demonstrated efficacy in primary", "demonstrated efficacy on primary",
        "significant improvement in the primary",
        "significantly improved the primary",
        "statistically significant", "p < 0.05", "p<0.05",
        "fda approved", "fda-approved", "ema approved", "ema-approved",
        "regulatory approval", "marketing authorization", "marketing authorisation",
        "received approval",
    ]

    @classmethod
    def _has_strong_efficacy(cls, efficacy_keywords: list[str]) -> bool:
        """Strong = explicit primary-endpoint-met / p<0.05 / approval signal."""
        if not efficacy_keywords:
            return False
        joined = " ; ".join(str(k).lower() for k in efficacy_keywords)
        return any(kw in joined for kw in cls._STRONG_EFFICACY)

    @classmethod
    def _dossier_publication_override(cls, dossier: dict, current_value: str) -> str | None:
        """v42.6.11: Override Unknown/Active only with STRONG publication evidence.

        v41 fired on any efficacy keyword from any trial-specific pub — too loose,
        produced systemic Positive over-calls on trials with review-like "clinical
        benefit" / "antitumor activity" language in titles. v42.6.11 requires:
          - ≥2 trial-specific publications (singletons are often noisy), AND
          - at least one STRONG efficacy signal (primary endpoint met, p<0.05,
            regulatory approval, explicit phase advancement).

        Negative overrides are unchanged — strong adverse signals still flip the
        outcome. "Unknown" is now the default when evidence is ambiguous.
        """
        efficacy = dossier.get("efficacy_keywords", [])
        neg = dossier["negative_keywords"]
        trial_specific = dossier.get("trial_specific_count", dossier["publication_count"])
        stale = dossier["stale_status"]
        status = dossier["registry_status"].upper()

        # Strong negative signals always override — unchanged from v41
        _STRONG_ADVERSE = ["unacceptable", "not tolerated", "dose-limiting",
                           "safety concern", "serious adverse event", "discontinued due to"]
        if any(kw in neg for kw in _STRONG_ADVERSE):
            return "Failed - completed trial"

        # v42.6.11: STRONG-evidence gate for Unknown → Positive
        if (trial_specific >= 2
                and cls._has_strong_efficacy(efficacy)
                and not neg):
            return "Positive"

        # Trial-specific publications with negative signals → Failed (unchanged)
        if trial_specific > 0 and neg and not efficacy:
            return "Failed - completed trial"

        # Stale Active: respect the LLM's Unknown unless strong evidence overrides
        if current_value == "Active, not recruiting" and stale:
            if cls._has_strong_efficacy(efficacy):
                return "Positive"
            if neg:
                return "Failed - completed trial"
            # no override — let the LLM's Unknown stand

        # COMPLETED with results posted but LLM said Unknown — results posting
        # is a verifiable structural signal, not a keyword match, so keep this
        # override. Confidence is still the LLM's; only the label flips.
        if status == "COMPLETED" and dossier["has_results"] is True:
            return "Positive"

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
