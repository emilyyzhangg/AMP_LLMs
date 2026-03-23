"""
Outcome Annotation Agent (v4 — v11 accuracy fixes).

Determines trial outcome using a two-pass strategy:
  Pass 1: Extract ClinicalTrials.gov status, phase, and published results
  Pass 2: Determine outcome using calibrated decision tree

v4/v11 changes (from 400-trial concordance — outcome regressed from 80% to 47%):
  - Expanded deterministic pass: COMPLETED+hasResults→Positive, Phase I+no pubs→Unknown
  - Fixed confidence calculation: now min(citation_quality, source_sufficiency)
  - Tightened Pass 2 prompt: explicit H1 prohibition with negative examples
  - Root cause: 8B model was calling "Positive" for Phase I completions without
    corroboration, and "Recruiting" was under-detected (17.6% recall)
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
    "TERMINATED": "Terminated",
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

            # v11: COMPLETED Phase I without hasResults → Unknown (prevent H1 violation)
            design_mod = proto.get("designModule", {})
            phases = design_mod.get("phases", [])
            if isinstance(phases, str):
                phases = [phases]
            phase_str = " ".join(phases).upper() if phases else ""
            is_phase1 = "PHASE1" in phase_str or "EARLY_PHASE1" in phase_str
            if is_phase1 and not has_results:
                logger.info(f"  outcome: deterministic → Unknown (COMPLETED Phase I, no hasResults)")
                return FieldAnnotation(
                    field_name="outcome", value="Unknown", confidence=0.85,
                    reasoning="[Deterministic v11] COMPLETED Phase I without hasResults → Unknown (H1 requires corroboration)",
                    evidence=[], model_name="deterministic", skip_verification=False,
                )

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

DECISION TREE (follow in order):

1. Is the trial RECRUITING, NOT_YET_RECRUITING, or ENROLLING_BY_INVITATION? -> "Recruiting"
2. Is the trial ACTIVE_NOT_RECRUITING with no results yet? -> "Active, not recruiting"
3. Was the trial WITHDRAWN before enrollment? -> "Withdrawn"
4. Was the trial TERMINATED? -> "Terminated"
   (The REASON for termination goes in reason_for_failure, not here.)
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

H2. PHASE II/III COMPLETION WITH hasResults=Yes: If ClinicalTrials.gov indicates results were posted
    (hasResults field), the trial produced data. Lean toward "Positive" unless evidence says otherwise.

H3. LONG-COMPLETED TRIALS: If the trial completed more than 10 years ago and led to subsequent
    later-phase trials of the same drug → the earlier trial was likely "Positive" (the drug advanced).

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
        # Default: use primary annotator model
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
                temperature=config.ollama.temperature,
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

        # --- PASS 2: Determine outcome with facts in hand ---
        try:
            logger.info(f"  outcome: Pass 2 — determining outcome for {nct_id}")
            pass2_prompt = PASS2_PROMPT.format(pass1_output=pass1_output)
            pass2_response = await ollama_client.generate(
                model=primary_model,
                prompt=pass2_prompt + "\n\nOriginal evidence:\n" + evidence_text,
                temperature=config.ollama.temperature,
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

        # Include pass 1 extraction in the reasoning for audit trail
        full_reasoning = f"[Pass 1 facts] {pass1_output[:500]}\n[Pass 2 decision] {reasoning}"

        # v11: Confidence = min(citation quality, source sufficiency).
        # If only 1 source (e.g., just ClinicalTrials.gov), cap confidence at 0.5.
        citation_quality = sum(c.quality_score for c in cited_sources[:10]) / max(len(cited_sources[:10]), 1)
        num_distinct_sources = len({c.source_name for c in cited_sources[:10]})
        source_sufficiency = min(1.0, num_distinct_sources / 2)
        confidence = min(citation_quality, source_sufficiency)

        return FieldAnnotation(
            field_name=self.field_name,
            value=value,
            confidence=confidence,
            reasoning=full_reasoning,
            evidence=cited_sources[:10],
            model_name=primary_model,
        )

    def _infer_from_pass1(self, pass1_text: str) -> str:
        """Fallback: infer outcome from pass 1 extraction if pass 2 fails.

        Applies completion heuristics for older trials where publications
        may not be found but the trial clearly completed normally.
        """
        lower = pass1_text.lower()

        # Check for published results first (most important signal)
        results_section = ""
        match = re.search(r"published results?:\s*(.+?)(?:\n[A-Z]|\Z)", lower, re.DOTALL)
        if match:
            results_section = match.group(1).strip()

        if results_section and results_section not in ("none found", "none", "no results"):
            if any(kw in results_section for kw in ["efficacy", "effective", "positive", "significant", "met primary"]):
                return "Positive"
            if any(kw in results_section for kw in ["failed", "negative", "not effective", "did not meet"]):
                return "Failed - completed trial"

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

            # H1: Phase I completion = Positive, BUT requires corroboration
            # Without results posted or publications, Phase I completion
            # alone is insufficient — return Unknown instead.
            phase_match = re.search(r"trial phase:\s*(.+?)(?:\n|$)", lower)
            if phase_match:
                phase = phase_match.group(1).strip()
                is_phase1 = (
                    "phase1" in phase or "phase 1" in phase
                    or "early_phase" in phase or "early phase" in phase
                )
                if is_phase1 and has_results_posted:
                    return "Positive"
                # Phase I without corroboration → Unknown (v7 calibration)

        return "Unknown"

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
