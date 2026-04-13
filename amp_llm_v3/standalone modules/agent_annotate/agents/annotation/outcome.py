"""
Outcome Annotation Agent (v4 — v11 accuracy fixes, v17 heuristic override, v21 TERMINATED fix, v25 publication-priority, v26 TERMINATED override fix, v32 regex + safety nets).

Determines trial outcome using a two-pass strategy:
  Pass 1: Extract ClinicalTrials.gov status, phase, and published results
  Pass 2: Determine outcome using calibrated decision tree

v4/v11 changes (from 400-trial concordance — outcome regressed from 80% to 47%):
  - Expanded deterministic pass: COMPLETED+hasResults→Positive, Phase I+no pubs→Unknown
  - Fixed confidence calculation: now min(citation_quality, source_sufficiency)
  - Tightened Pass 2 prompt: explicit H1 prohibition with negative examples
  - Root cause: 8B model was calling "Positive" for Phase I completions without
    corroboration, and "Recruiting" was under-detected (17.6% recall)

v17 changes:
  - Post-LLM heuristic override: when Pass 2 returns "Unknown", apply _infer_from_pass1()
    as a safety net. Previously this was only called on Pass 2 LLM exceptions — dead code
    for the normal path. Now catches adverse-event keywords in publications.
  - Inject trial phase from structured ClinicalTrials.gov data into Pass 2 prompt so the
    LLM doesn't rely on Pass 1 extraction (which sometimes returns "NOT FOUND").

v21 changes:
  - TERMINATED removed from _DETERMINISTIC_STATUSES: trials stopped early for efficacy
    or with positive published results were being blindly mapped to "Terminated". Now falls
    through to the 2-pass LLM pipeline which checks evidence before deciding.
  - PASS2_PROMPT item 4: evidence-based decision tree for TERMINATED (Positive if positive
    evidence, Failed if safety/futility, Terminated if business reason or no signal).
  - PASS2_PROMPT heuristics: added H1b (Phase I >5yr, no Phase II -> Unknown) and
    H3b (Phase II/III >10yr, no pubs, no negative evidence -> lean Positive).

v25 changes (publication-priority — fixes 37% of outcome disagreements):
  - PASS2_PROMPT: Added EVIDENCE PRIORITY ladder — published results override CT.gov
    registry status. Previously agent defaulted to "Unknown" when status was ambiguous
    even when publications reported clear results.
  - PASS2_PROMPT: Added rules for "Active" with published results (registry may be
    outdated) and "Terminated" not implying failure.
  - _infer_from_pass1: Added publication-priority override — when Pass 2 returns Unknown
    but publications with result valence exist, use the publication signal.
"""

import re
import logging
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

# --------------------------------------------------------------------------- #
#  Deterministic outcome mapping (v11)
# --------------------------------------------------------------------------- #

_DETERMINISTIC_STATUSES = {
    "RECRUITING": "Recruiting",
    "NOT_YET_RECRUITING": "Recruiting",
    "ENROLLING_BY_INVITATION": "Recruiting",
    "WITHDRAWN": "Withdrawn",
    "ACTIVE_NOT_RECRUITING": "Active, not recruiting",
    "SUSPENDED": "Unknown",
    # v21: TERMINATED removed from deterministic — some TERMINATED trials have
    # positive published results (stopped early for efficacy) and should not be
    # blindly mapped to "Terminated". Let the 2-pass LLM pipeline decide.
}


def _deterministic_outcome(research_results: list) -> FieldAnnotation | None:
    """Map clear-cut registry statuses deterministically.

    v11: Also handles COMPLETED trials with hasResults and Phase I without publications.
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
                reasoning=f"[Deterministic v11] Registry status '{overall_status}' → '{value}'",
                evidence=[], model_name="deterministic", skip_verification=True,
            )

        # v11: COMPLETED with hasResults=true → Positive (results were posted)
        if overall_status == "COMPLETED":
            has_results = status_mod.get("hasResults", False)
            if has_results is True or str(has_results).lower() == "true":
                logger.info(f"  outcome: deterministic → Positive (COMPLETED + hasResults=true)")
                return FieldAnnotation(
                    field_name="outcome", value="Positive", confidence=0.90,
                    reasoning="[Deterministic v11] COMPLETED + hasResults=true → Positive",
                    evidence=[], model_name="deterministic", skip_verification=False,
                )

            # v11 had a Phase I guard here (COMPLETED Phase I without hasResults → Unknown)
            # but it caused massive regression: hasResults is often unpopulated even when
            # publications exist. Removed in v12 — let the LLM pipeline + H1 heuristics
            # handle Phase I trials with access to full research evidence.

    return None

# Pass 1: Extract the registry status and what we know so far
PASS1_PROMPT = """You are a clinical trial status extraction specialist.

Your task: Extract the FACTUAL STATUS of this trial from the ClinicalTrials.gov data, then summarize what published literature says about its results.

From the evidence below, extract:

1. REGISTRY STATUS: The overallStatus from ClinicalTrials.gov (e.g., COMPLETED, TERMINATED, RECRUITING, UNKNOWN, WITHDRAWN, ACTIVE_NOT_RECRUITING, NOT_YET_RECRUITING, ENROLLING_BY_INVITATION, SUSPENDED). If not found, say "NOT FOUND".

2. PUBLISHED RESULTS: Search the PubMed, PMC, and web evidence for ANY mention of trial results, outcomes, findings, efficacy, or conclusions. Quote the relevant excerpts. If there are multiple publications, list each one.

3. RESULTS POSTED: Does ClinicalTrials.gov indicate results have been posted? (hasResults field)

4. COMPLETION DATE: When did/will the trial complete?

5. WHY STOPPED: If terminated or withdrawn, what reason was given?

6. TRIAL PHASE: The phase from ClinicalTrials.gov (PHASE1, PHASE2, PHASE3, PHASE4, EARLY_PHASE1, N/A). This is critical for interpreting outcome — Phase I success = safety/tolerability shown.

7. RESULT VALENCE: Based on all evidence, were the results POSITIVE, NEGATIVE, MIXED, or NOT AVAILABLE? Pay special attention to: Were primary endpoints met? For Phase I, was the drug safe/tolerable? Did the drug progress to subsequent phases?

Format your response EXACTLY as:
Registry Status: [status from ClinicalTrials.gov]
Trial Phase: [phase]
Published Results: [summary of any published findings, or "None found"]
Result Valence: [Positive/Negative/Mixed/Not available]
Results Posted: [Yes/No/Unknown]
Completion Date: [date or Unknown]
Why Stopped: [reason or N/A]"""

# Pass 2: Make the outcome determination with all facts in hand
PASS2_PROMPT = """You are a clinical trial outcome assessment specialist. You have already extracted the facts about this trial. Now you must determine the outcome.

The facts you extracted:
{pass1_output}

EVIDENCE PRIORITY (highest to lowest — follow this order strictly):
1. Published results (peer-reviewed publications, press releases with efficacy data)
   → If publications report clear positive or negative results, USE THEM regardless of CT.gov status.
2. ClinicalTrials.gov results section (has_results_posted = true)
3. ClinicalTrials.gov overall status field
4. Trial phase and design (Phase I safety = limited outcome signal)

CRITICAL RULE: Published results in literature OVERRIDE the ClinicalTrials.gov registry status.
- If publications report efficacy/positive results → "Positive", even if CT.gov says Active/Terminated/Unknown
- If publications report failed/negative results → "Failed - completed trial", even if CT.gov says Active/Terminated
- CT.gov status should only be the PRIMARY signal when NO publications with results are found
- Do NOT default to "Unknown" just because the registry status is ambiguous — check publications first.

DECISION TREE (follow in order):

0. PUBLICATION OVERRIDE (check this FIRST, before registry status):
   EXCEPTION: If the trial is TERMINATED or WITHDRAWN, skip this step and go directly to
   step 3 (WITHDRAWN) or step 4 (TERMINATED). Terminated/Withdrawn trials have their own
   decision logic that accounts for publications in context.
   For all OTHER statuses: if published literature reports completed results (positive or
   negative), use those results regardless of what ClinicalTrials.gov says. Registry status
   may be outdated or incomplete.
   a. Published results show POSITIVE findings → "Positive"
   b. Published results show NEGATIVE findings → "Failed - completed trial"
   If no publications with results exist, continue to step 1.

1. Is the trial RECRUITING, NOT_YET_RECRUITING, or ENROLLING_BY_INVITATION? -> "Recruiting"
2. Is the trial ACTIVE_NOT_RECRUITING with no results yet?
   BUT: If ClinicalTrials.gov says Active or Recruiting but published literature reports completed
   results (positive or negative), use the published results. Registry status may be outdated.
   Only use "Active, not recruiting" if there are genuinely NO published results.
3. Was the trial WITHDRAWN before enrollment? -> "Withdrawn"
4. Was the trial TERMINATED?
   IMPORTANT: Terminated does NOT mean failed. A terminated trial may have published positive
   interim results. ALWAYS check literature before concluding.
   First check the evidence for this TERMINATED trial:
   a. Published results show POSITIVE findings OR the drug advanced to later-phase trials OR the drug
      was approved → "Positive" (trial was stopped early for efficacy or succeeded despite termination)
   b. Published results show safety failure, futility, or termination due to lack of efficacy → "Failed - completed trial"
   c. Termination was for business/operational reasons (funding, sponsor decision, strategic) with no
      efficacy evidence either way → "Terminated"
   d. No publications, no results posted, reason unclear → "Terminated" (default for TERMINATED)
   (The specific REASON for termination goes in reason_for_failure, not here.)
5. For COMPLETED or UNKNOWN status, check published literature:
   a. Published results show POSITIVE findings (met endpoints, efficacy shown, favorable safety) -> "Positive"
   b. Published results show NEGATIVE findings (failed endpoints, no efficacy, futility) -> "Failed - completed trial"
   c. NO published results found -> apply COMPLETION HEURISTICS below

COMPLETION HEURISTICS (when no published results are found for COMPLETED trials):

These rules help determine outcome for older trials (pre-2010) where publications may not be indexed:

H1. PHASE I COMPLETION: Phase I/Early Phase I trials that completed normally (not terminated/withdrawn)
    are typically "Positive". Phase I success = acceptable safety, tolerability, pharmacokinetics established.
    Completing a Phase I trial IS the success criterion. → "Positive"
    BUT: H1 requires at least ONE corroborating signal: results posted on ClinicalTrials.gov,
    a publication mentioning the trial (even without detailed results), or a subsequent later-phase trial.
    If Phase I completed but ZERO publications were found and Results Posted = No/Unknown,
    → "Unknown" (not enough evidence to confirm success). Do NOT apply H1 without corroboration.

    *** CRITICAL: DO NOT say "lean towards Positive" or "likely Positive" for Phase I trials
    without corroboration. This is the #1 error in previous annotations. If you have ZERO
    publications AND Results Posted = No/Unknown, the answer MUST be "Unknown". ***

H1b. PHASE I COMPLETED LONG AGO (>5 years, no Phase II found, no publications):
    If the trial completed >5 years ago, is Phase I, and there is NO evidence of a subsequent
    Phase II trial for the same drug and NO publications at all → "Unknown". The absence of any
    follow-on development suggests the drug did not advance, but "Failed" requires positive evidence.

H2. PHASE II/III COMPLETION WITH hasResults=Yes: If ClinicalTrials.gov indicates results were posted
    (hasResults field), the trial produced data. Lean toward "Positive" unless evidence says otherwise.

H3. LONG-COMPLETED TRIALS: If the trial completed more than 10 years ago and led to subsequent
    later-phase trials of the same drug → the earlier trial was likely "Positive" (the drug advanced).

H3b. PHASE II/III COMPLETED LONG AGO (>10 years, no publications, no negative evidence):
    If the trial is Phase II/III, completed >10 years ago, no publications found, and no evidence
    of failure → lean "Positive". Phase II/III trials that produced no indexed publications and no
    negative signal likely completed successfully (common for older industry-sponsored trials).

H4. COMPLETED + RESULTS POSTED: If Results Posted = Yes but you couldn't find specific
    result descriptions, lean "Positive" (the act of posting results for a completed trial
    typically happens for trials with reportable outcomes).

H5. DEFAULT: If truly no signals exist → "Unknown". But exhaust H1-H4 first.

CRITICAL RULES:
- "Failed - completed trial" REQUIRES EVIDENCE OF FAILURE. You MUST cite a specific publication showing negative results, failure to meet primary endpoints, or futility. If you cannot cite such evidence, the answer is NOT "Failed".
- COMPLETED status alone does NOT mean failure.
- Phase I trials that complete with published safety/tolerability results → "Positive".
- Phase I completion alone (no publications, no results posted) → "Unknown".
- BUT: Phase I completion WITH results posted on ClinicalTrials.gov → "Positive" (the act of posting results confirms the trial produced data).
- Phase II trials that complete with results posted → lean "Positive".
- If the Result Valence you extracted says "Positive" or "Mixed" -> "Positive".
- If the Result Valence says "Not available" AND no publications found AND Results Posted = No/Unknown → "Unknown".
- If the Result Valence says "Not available" BUT Results Posted = Yes → lean "Positive" (results were posted, indicating reportable outcomes).
- RECENCY: If multiple publications exist with conflicting conclusions, the MOST RECENT publication takes priority.
- COMPLETED + no published results + Results Posted = No/Unknown → "Unknown".
- COMPLETED + Results Posted = Yes (even without findable publications) → lean "Positive".

NEGATIVE EXAMPLE (DO NOT make this mistake):
  Registry Status: COMPLETED
  Trial Phase: PHASE1
  Published Results: None found
  Results Posted: Unknown
  → WRONG: "Outcome: Positive" (reasoning: "lean towards Positive given Phase I completion")
  → CORRECT: "Outcome: Unknown" (no corroboration for H1: zero publications, no results posted)

IMPORTANT: Format your response EXACTLY as:
Outcome: [one of the 7 values above]
Evidence: [cite the specific source that determined your decision]
Reasoning: [explain your chain of thought, noting which heuristic you applied if applicable]"""


# Hardware profile → model selection for outcome
# Outcome benefits from a larger model because the decision tree
# requires nuanced interpretation of published results and status.
# On server, uses the configurable server_premium_model (kimi-k2 or minimax-m2.7)
# because outcome is the most unstable field across runs.


class OutcomeAgent(BaseAnnotationAgent):
    """Determines trial outcome using two-pass investigation."""

    field_name = "outcome"

    def _get_model(self, config) -> str:
        """Select model based on hardware profile."""
        profile = config.orchestrator.hardware_profile
        if profile == "server":
            # Use the configurable premium model for outcome (most unstable field)
            return getattr(config.orchestrator, "server_premium_model", "kimi-k2-thinking")
        # v11: Use unified annotation_model (eliminates model switches)
        annotation_model = getattr(config.orchestrator, "annotation_model", None)
        if annotation_model:
            return annotation_model
        # Fallback: use primary annotator model
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
        # v11: Try deterministic status mapping first
        det_result = _deterministic_outcome(research_results)
        if det_result is not None:
            return det_result

        from app.services.config_service import config_service

        config = config_service.get()
        # Server profile with larger models can digest more evidence
        is_server = config.orchestrator.hardware_profile == "server"
        max_cites = 50 if is_server else 30
        max_snippet = 500 if is_server else 250

        # Build structured evidence — sections help the LLM locate
        # trial status, published results, and drug data efficiently
        evidence_text, cited_sources = self.build_structured_evidence(
            nct_id, research_results,
            max_citations=max_cites,
            max_snippet_chars=max_snippet,
        )

        # --- EDAM guidance injection ---
        edam_guidance = await self.get_edam_guidance(nct_id, evidence_text)
        if edam_guidance:
            evidence_text = edam_guidance + "\n\n" + evidence_text

        from app.services.ollama_client import ollama_client
        from app.services.config_service import config_service

        config = config_service.get()
        primary_model = self._get_model(config)

        # --- PASS 1: Extract facts ---
        try:
            logger.info(f"  outcome: Pass 1 — extracting facts for {nct_id}")
            pass1_response = await ollama_client.generate(
                model=primary_model,
                prompt=evidence_text,
                system=PASS1_PROMPT,
                temperature=config.ollama.field_temperatures.get("outcome", config.ollama.temperature),
            )
            pass1_output = pass1_response.get("response", "")
        except Exception as e:
            return FieldAnnotation(
                field_name=self.field_name,
                value="Unknown",
                confidence=0.0,
                reasoning=f"Pass 1 LLM call failed: {e}",
                evidence=[],
                model_name=primary_model,
            )

        # --- v17: Extract structured phase from ClinicalTrials.gov data ---
        # The Pass 1 LLM sometimes returns "Trial Phase: NOT FOUND" even when
        # the phase is in the structured data. Inject it directly into Pass 2.
        structured_phase = self._extract_structured_phase(research_results)
        if structured_phase:
            # Append structured phase to Pass 1 output so Pass 2 always has it
            phase_check = re.search(r"Trial Phase:\s*(.+?)(?:\n|$)", pass1_output, re.IGNORECASE)
            if not phase_check or "not found" in phase_check.group(1).lower():
                pass1_output += f"\nTrial Phase: {structured_phase} [from ClinicalTrials.gov structured data]"
                logger.info(f"  outcome: injected structured phase '{structured_phase}' into Pass 2 input")

        # --- v33: Extract structured registry status from ClinicalTrials.gov ---
        # Same pattern as phase injection. The LLM frequently returns
        # "Registry Status: NOT FOUND" even though the status IS in the
        # clinical_protocol raw data. This causes _infer_from_pass1 to miss
        # the status-based heuristics (COMPLETED/TERMINATED/WITHDRAWN fallbacks).
        # v35: All valid ClinicalTrials.gov overallStatus values
        _VALID_CT_STATUSES = {
            "recruiting", "not_yet_recruiting", "enrolling_by_invitation",
            "withdrawn", "active_not_recruiting", "suspended",
            "completed", "terminated", "unknown_status",
            "active, not recruiting", "not yet recruiting",
            "enrolling by invitation",
        }
        structured_status, structured_has_results = self._extract_structured_status(research_results)
        if structured_status:
            status_check = re.search(r"Registry Status:\s*(.+?)(?:\n|$)", pass1_output, re.IGNORECASE)
            llm_status = status_check.group(1).strip().lower() if status_check else ""
            is_not_found = not status_check or "not found" in llm_status
            is_unrecognized = (
                not is_not_found
                and llm_status.replace(" ", "_") not in _VALID_CT_STATUSES
                and llm_status not in _VALID_CT_STATUSES
            )
            if is_not_found or is_unrecognized:
                suffix = " [corrected from unrecognized]" if is_unrecognized else ""
                pass1_output += f"\nRegistry Status: {structured_status} [from ClinicalTrials.gov structured data]{suffix}"
                logger.info(f"  outcome: v35 injected structured status '{structured_status}' (was: '{llm_status}') into Pass 2 input")
            if structured_has_results is not None:
                hr_check = re.search(r"Results Posted:\s*(.+?)(?:\n|$)", pass1_output, re.IGNORECASE)
                if not hr_check or "unknown" in hr_check.group(1).lower() or "not found" in hr_check.group(1).lower():
                    hr_val = "Yes" if structured_has_results else "No"
                    pass1_output += f"\nResults Posted: {hr_val} [from ClinicalTrials.gov structured data]"
                    logger.info(f"  outcome: v33 injected hasResults={hr_val} into Pass 2 input")

        # --- PASS 2: Determine outcome with facts in hand ---
        try:
            logger.info(f"  outcome: Pass 2 — determining outcome for {nct_id}")
            pass2_prompt = PASS2_PROMPT.format(pass1_output=pass1_output)
            pass2_response = await ollama_client.generate(
                model=primary_model,
                prompt=pass2_prompt + "\n\nOriginal evidence:\n" + evidence_text,
                temperature=config.ollama.field_temperatures.get("outcome", config.ollama.temperature),
            )
            pass2_output = pass2_response.get("response", "")
        except Exception as e:
            # Fall back to pass 1 data if pass 2 fails
            value = self._infer_from_pass1(pass1_output)
            return FieldAnnotation(
                field_name=self.field_name,
                value=value,
                confidence=0.3,
                reasoning=f"Pass 2 failed ({e}), inferred from pass 1: {pass1_output[:300]}",
                evidence=cited_sources[:10],
                model_name=primary_model,
            )

        value = self._parse_value(pass2_output)
        reasoning = self._parse_reasoning(pass2_output)

        # v25: Publication-priority override — when Pass 2 returns "Unknown",
        # check if Pass 1 found published results with a clear valence. This is
        # the #1 disagreement pattern: agent=Unknown when publications exist.
        # v26: Removed "Terminated" — human annotators keep "Terminated" as outcome
        # regardless of published results. PASS2_PROMPT step 4 handles TERMINATED
        # nuance; overriding here caused 4/12 outcome disagreements.
        if value in ("Unknown", "Active, not recruiting"):
            pub_override = self._publication_priority_override(pass1_output, value)
            if pub_override and pub_override != value:
                logger.info(f"  outcome: v25 publication-priority override {value} → {pub_override}")
                value = pub_override
                reasoning = f"[v25 publication-priority override: Pass 2 returned {value}, publications indicate {pub_override}] " + reasoning

        # v17: Post-LLM heuristic override — when Pass 2 returns "Unknown",
        # apply the adverse-event and completion heuristics against Pass 1 output.
        # Previously _infer_from_pass1 was only called on LLM exceptions (dead code
        # in the normal path), so adverse-event keywords never fired.
        if value == "Unknown":
            heuristic_value = self._infer_from_pass1(pass1_output, nct_id=nct_id)
            if heuristic_value != "Unknown":
                logger.info(f"  outcome: heuristic override {value} → {heuristic_value}")
                value = heuristic_value
                reasoning = f"[Heuristic override: Pass 2 returned Unknown, _infer_from_pass1 → {heuristic_value}] " + reasoning

        # v32: Terminated safety net — if we still have "Unknown" but the trial
        # is TERMINATED with no results posted, default to "Terminated". Catches
        # cases where generic drug publications (from v31 literature APIs) cause
        # has_publications=True in _infer_from_pass1 and a keyword false-match
        # returns early before reaching the registry status fallback.
        if value == "Unknown":
            lower_p1 = pass1_output.lower()
            status_match = re.search(r"registry status:\s*(\S+)", lower_p1)
            if status_match and "terminated" in status_match.group(1):
                results_posted = (
                    "results posted: yes" in lower_p1
                    or "hasresults: true" in lower_p1
                )
                if not results_posted:
                    logger.info("  outcome: v32 Terminated safety net activated")
                    value = "Terminated"
                    reasoning = (
                        "[v32 Terminated safety net: TERMINATED with no results posted] "
                        + reasoning
                    )

        # v32: hasResults override — COMPLETED trial with results posted but LLM
        # said Unknown. H4 in the prompt says "lean Positive" but the LLM may not
        # follow. _infer_from_pass1 has this at H2/H4 but only when has_publications
        # is False. This backstop catches the remaining cases.
        if value == "Unknown":
            lower_p1 = pass1_output.lower()
            results_posted = (
                "results posted: yes" in lower_p1
                or "hasresults: true" in lower_p1
            )
            if results_posted:
                status_match = re.search(r"registry status:\s*(\S+)", lower_p1)
                status = status_match.group(1) if status_match else ""
                if "completed" in status or "complete" in status:
                    logger.info("  outcome: v32 hasResults override activated (COMPLETED + results posted)")
                    value = "Positive"
                    reasoning = (
                        "[v32 hasResults override: COMPLETED with results posted] "
                        + reasoning
                    )

        # Include pass 1 extraction in the reasoning for audit trail
        full_reasoning = f"[Pass 1 facts] {pass1_output[:500]}\n[Pass 2 decision] {reasoning}"

        # v12: Confidence based on citation quality. The v11 source_sufficiency
        # divisor (/2) was too aggressive — single-source evidence (ClinicalTrials.gov)
        # is often sufficient and shouldn't be capped at 0.5.
        citation_quality = sum(c.quality_score for c in cited_sources[:10]) / max(len(cited_sources[:10]), 1)
        confidence = citation_quality

        return FieldAnnotation(
            field_name=self.field_name,
            value=value,
            confidence=confidence,
            reasoning=full_reasoning,
            evidence=cited_sources[:10],
            model_name=primary_model,
        )

    def _infer_from_pass1(self, pass1_text: str, nct_id: str = "") -> str:
        """Fallback: infer outcome from pass 1 extraction if pass 2 fails.

        Applies completion heuristics for older trials where publications
        may not be found but the trial clearly completed normally.
        """
        lower = pass1_text.lower()

        # Check for published results first (most important signal)
        # v32: fixed section boundary — was \n[A-Z] on lowercased text (never matched)
        results_section = ""
        match = re.search(r"published results?:\s*(.+?)(?:" + _SECTION_BOUNDARY + r"|\Z)", lower, re.DOTALL)
        if match:
            results_section = match.group(1).strip()

        has_publications = (
            results_section
            and results_section not in ("none found", "none", "no results", "not found")
        )

        # v33: Generic publication filter — v31 literature APIs (OpenAlex,
        # Semantic Scholar, CrossRef) often return drug-class publications that
        # discuss the molecule but NOT this trial's results. When has_publications
        # is True but publications are generic, keyword matching produces false
        # positives/negatives and blocks the registry status fallback. Require
        # trial-specific language before trusting keyword matching.
        _TRIAL_SPECIFIC_MARKERS = [
            "primary endpoint", "our study", "this study", "this trial",
            "met the", "failed to meet", "results showed", "results demonstrated",
            "phase i ", "phase ii ", "phase iii ", "phase 1 ", "phase 2 ", "phase 3 ",
            "enrolled", "randomized", "patients were",
        ]
        if nct_id:
            _TRIAL_SPECIFIC_MARKERS.append(nct_id.lower())
        is_trial_specific = has_publications and any(
            m in results_section for m in _TRIAL_SPECIFIC_MARKERS
        )

        if has_publications and is_trial_specific:
            # v18: Check strong adverse-event signals in FULL pass1 text first.
            # These override any positive heuristics — a trial with positive
            # immunogenicity but unacceptable toxicity is still Failed.
            # Multi-word patterns reduce false positives from scanning full text.
            _STRONG_ADVERSE = [
                "unacceptable", "not tolerated", "dose-limiting",
                "reactogenicity", "sterile abscess", "safety concern",
                "serious adverse event", "discontinued due to",
            ]
            if any(kw in lower for kw in _STRONG_ADVERSE):
                return "Failed - completed trial"
            # Then check positive/negative keywords in results_section only
            if any(kw in results_section for kw in ["efficacy", "effective", "positive", "significant", "met primary"]):
                return "Positive"
            if any(kw in results_section for kw in [
                "failed", "negative", "not effective", "did not meet",
                "did not demonstrate", "did not achieve", "did not show",
                "no significant", "no benefit", "no improvement",
                "failed to demonstrate", "failed to meet", "failed primary",
                "lack of efficacy", "ineffective", "no efficacy",
            ]):
                return "Failed - completed trial"
            # v16: Additional adverse signals (single-word, scoped to results_section)
            if any(kw in results_section for kw in [
                "toxicity", "toxic", "adverse", "abscess",
            ]):
                return "Failed - completed trial"
        elif has_publications and not is_trial_specific:
            # v33: Generic publication — don't trust keyword matching.
            # v34: But DO trust the LLM's result_valence — it's a holistic
            # judgment, not a keyword match, so less prone to false positives
            # from drug-class publications. This fixes NCT03482648 and similar
            # COMPLETED trials where generic pubs blocked all outcome evidence.
            valence_match = re.search(r"result valence:\s*(.+?)(?:\n|$)", lower)
            if valence_match:
                valence = valence_match.group(1).strip()
                if "positive" in valence or "mixed" in valence:
                    logger.info(f"  outcome: v34 generic pub + LLM valence='{valence}' → Positive for {nct_id}")
                    return "Positive"
                if "negative" in valence:
                    logger.info(f"  outcome: v34 generic pub + LLM valence='{valence}' → Failed for {nct_id}")
                    return "Failed - completed trial"
            # v35: Before falling to Unknown, scan full pass1 text for
            # efficacy/failure keywords. Less precise than trial-specific
            # matching, but better than giving up entirely.
            _EFFICACY_MARKERS = [
                "improved", "improvement", "efficacy", "effective",
                "favorable", "benefit", "promising", "successful",
                "well-tolerated", "safe and effective",
            ]
            _FAILURE_MARKERS = [
                "failed", "negative", "did not meet",
                "did not demonstrate", "no efficacy", "futility",
                "insufficient",
            ]
            if any(kw in lower for kw in _EFFICACY_MARKERS):
                logger.info(f"  outcome: v35 generic pub + efficacy keyword in full text → Positive for {nct_id}")
                return "Positive"
            if any(kw in lower for kw in _FAILURE_MARKERS):
                logger.info(f"  outcome: v35 generic pub + failure keyword in full text → Failed for {nct_id}")
                return "Failed - completed trial"
            logger.info(f"  outcome: v35 skipping keyword match — publications appear generic, no clear signal for {nct_id}")

        # Fall back to registry status
        status_match = re.search(r"registry status:\s*(\S+)", lower)
        status = status_match.group(1).strip() if status_match else ""

        if "withdrawn" in status:
            return "Withdrawn"
        if "terminated" in status:
            return "Terminated"
        if "recruiting" in status and "not" not in status and "active" not in status:
            return "Recruiting"
        if "active_not_recruiting" in status:
            return "Active, not recruiting"

        # Completion heuristics for COMPLETED trials without publications
        if "completed" in status or "complete" in status:
            # H2/H4: Results posted = lean Positive (strongest signal)
            has_results_posted = (
                "results posted: yes" in lower or "hasresults: true" in lower
            )
            if has_results_posted:
                return "Positive"

            # H3: Check result valence from Pass 1
            valence_match = re.search(r"result valence:\s*(.+?)(?:\n|$)", lower)
            if valence_match:
                valence = valence_match.group(1).strip()
                if "positive" in valence or "mixed" in valence:
                    return "Positive"
                # v16: Negative valence → Failed
                if "negative" in valence:
                    return "Failed - completed trial"

            # H1: Phase I completion = Positive, BUT requires corroboration
            # v18: Require trial-specific evidence (NCT ID in text or results_posted).
            # Generic publications that mention the drug but not this trial are
            # insufficient — they cause inter-run instability when search results vary.
            phase_match = re.search(r"trial phase:\s*(.+?)(?:\n|$)", lower)
            if phase_match:
                phase = phase_match.group(1).strip()
                is_phase1 = (
                    "phase1" in phase or "phase 1" in phase
                    or "early_phase" in phase or "early phase" in phase
                )
                if is_phase1 and has_results_posted:
                    return "Positive"
                if is_phase1 and has_publications and nct_id and nct_id.lower() in lower:
                    return "Positive"
                # Phase I without trial-specific evidence → Unknown

                # v33: H3b backstop — Phase II/III completed >10 years ago
                # without negative evidence → lean Positive. The PASS2_PROMPT
                # has this heuristic but the LLM often ignores it. This code
                # backstop ensures it fires reliably.
                is_phase23 = (
                    "phase2" in phase or "phase 2" in phase
                    or "phase3" in phase or "phase 3" in phase
                    or "phase ii" in phase or "phase iii" in phase
                    or "phase_2" in phase or "phase_3" in phase
                )
                if is_phase23 and not has_publications:
                    # Check completion date for age
                    date_match = re.search(r"completion date:\s*(.+?)(?:\n|$)", lower)
                    if date_match:
                        date_str = date_match.group(1).strip()
                        # Simple year extraction — look for 4-digit year
                        year_match = re.search(r"((?:19|20)\d{2})", date_str)
                        if year_match:
                            from datetime import datetime
                            try:
                                comp_year = int(year_match.group(1))
                                years_ago = datetime.now().year - comp_year
                                if years_ago > 10:
                                    logger.info(
                                        f"  outcome: v33 H3b backstop — Phase II/III completed {years_ago} years ago, no negative evidence"
                                    )
                                    return "Positive"
                            except (ValueError, TypeError):
                                pass

        return "Unknown"

    @staticmethod
    def _publication_priority_override(pass1_text: str, current_value: str) -> str | None:
        """v25: Check if Pass 1 found published results that should override the current value.

        This catches the dominant error pattern where the agent defaults to Unknown/Active/Terminated
        based on CT.gov registry status, but published literature reports clear results.

        Returns the overridden value, or None if no override applies.
        """
        lower = pass1_text.lower()

        # Extract published results section
        # v32: fixed section boundary — was \n[A-Z] on lowercased text (never matched)
        results_match = re.search(r"published results?:\s*(.+?)(?:" + _SECTION_BOUNDARY + r"|\Z)", lower, re.DOTALL)
        results_section = results_match.group(1).strip() if results_match else ""
        has_publications = (
            results_section
            and results_section not in ("none found", "none", "no results", "not found", "n/a")
        )

        if not has_publications:
            return None

        # v33: Generic publication filter — same as _infer_from_pass1.
        # v31 literature APIs return drug-class publications that aren't
        # about this specific trial. Only trust keyword matching when
        # publications contain trial-specific language.
        _TRIAL_SPECIFIC_MARKERS = [
            "primary endpoint", "our study", "this study", "this trial",
            "met the", "failed to meet", "results showed", "results demonstrated",
            "phase i ", "phase ii ", "phase iii ", "phase 1 ", "phase 2 ", "phase 3 ",
            "enrolled", "randomized", "patients were",
        ]
        is_trial_specific = any(m in results_section for m in _TRIAL_SPECIFIC_MARKERS)
        if not is_trial_specific:
            # v34: Generic publication — don't trust keyword matching, but DO
            # trust the LLM's result_valence (holistic judgment, not keywords).
            valence_match = re.search(r"result valence:\s*(.+?)(?:\n|$)", lower)
            if valence_match:
                valence = valence_match.group(1).strip()
                if "positive" in valence or "mixed" in valence:
                    return "Positive"
                if "negative" in valence:
                    return "Failed - completed trial"
            # v35: Same keyword rescue as _infer_from_pass1 — scan full text
            # for efficacy/failure keywords before giving up.
            _EFFICACY_MARKERS = [
                "improved", "improvement", "efficacy", "effective",
                "favorable", "benefit", "promising", "successful",
                "well-tolerated", "safe and effective",
            ]
            _FAILURE_MARKERS = [
                "failed", "negative", "did not meet",
                "did not demonstrate", "no efficacy", "futility",
                "insufficient",
            ]
            if any(kw in lower for kw in _EFFICACY_MARKERS):
                return "Positive"
            if any(kw in lower for kw in _FAILURE_MARKERS):
                return "Failed - completed trial"
            return None

        # Extract result valence from Pass 1
        valence_match = re.search(r"result valence:\s*(.+?)(?:\n|$)", lower)
        valence = valence_match.group(1).strip() if valence_match else ""

        # Strong adverse signals always win (same list as _infer_from_pass1)
        _STRONG_ADVERSE = [
            "unacceptable", "not tolerated", "dose-limiting",
            "reactogenicity", "sterile abscess", "safety concern",
            "serious adverse event", "discontinued due to",
        ]
        if any(kw in lower for kw in _STRONG_ADVERSE):
            return "Failed - completed trial"

        # Publications report positive results → Positive
        if "positive" in valence or "mixed" in valence:
            return "Positive"
        if any(kw in results_section for kw in [
            "efficacy", "effective", "positive", "significant",
            "met primary", "well-tolerated", "well tolerated",
            "safe and effective", "favorable", "promising",
            "immunogenic", "approved", "granted approval",
        ]):
            return "Positive"

        # Publications report negative results → Failed
        if "negative" in valence:
            return "Failed - completed trial"
        if any(kw in results_section for kw in [
            "failed", "negative", "not effective", "did not meet",
            "did not demonstrate", "did not achieve", "did not show",
            "no significant", "no benefit", "no improvement",
            "failed to demonstrate", "failed to meet", "failed primary",
            "lack of efficacy", "ineffective", "no efficacy",
            "futility", "inferior",
        ]):
            return "Failed - completed trial"

        # Publications exist but valence is unclear — don't override
        return None

    @staticmethod
    def _extract_structured_phase(research_results: list) -> str:
        """Extract trial phase directly from ClinicalTrials.gov structured data.

        v17: Ensures Pass 2 always has the trial phase even when Pass 1
        extraction fails (returns "NOT FOUND").
        """
        for result in research_results:
            if result.error or result.agent_name != "clinical_protocol":
                continue
            if not result.raw_data:
                continue
            proto = result.raw_data.get("protocol_section", result.raw_data.get("protocolSection", {}))
            design_mod = proto.get("designModule", {})
            phases = design_mod.get("phases", [])
            if isinstance(phases, list) and phases:
                return ", ".join(phases)
            # Some records use "phase" as a string
            phase_str = design_mod.get("phase", "")
            if phase_str:
                return phase_str
        return ""

    @staticmethod
    def _extract_structured_status(research_results: list) -> tuple:
        """Extract registry status and hasResults from ClinicalTrials.gov data.

        v33: Same pattern as _extract_structured_phase. The LLM frequently
        returns "Registry Status: NOT FOUND" even when the status IS in the
        clinical_protocol raw data, causing _infer_from_pass1 to miss
        COMPLETED/TERMINATED/WITHDRAWN heuristics.

        Returns:
            (status_str, has_results_bool) — e.g. ("COMPLETED", True)
        """
        for result in research_results:
            if result.error or result.agent_name != "clinical_protocol":
                continue
            if not result.raw_data:
                continue
            proto = result.raw_data.get("protocol_section", result.raw_data.get("protocolSection", {}))
            status_mod = proto.get("statusModule", {})
            overall_status = status_mod.get("overallStatus", "")
            has_results = status_mod.get("hasResults", None)
            if has_results is not None:
                has_results = has_results is True or str(has_results).lower() == "true"
            if overall_status:
                return overall_status, has_results
        return "", None

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
