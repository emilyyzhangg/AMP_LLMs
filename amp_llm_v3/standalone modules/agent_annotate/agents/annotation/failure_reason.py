"""
Failure Reason Annotation Agent (v2 — investigative).

Determines why a trial failed using a two-pass strategy:
  Pass 1: Extract whyStopped, trial status, and search literature
          for any discussion of failure, adverse events, or futility
  Pass 2: Determine the specific reason with all evidence in hand

Key insight from human annotation data:
  - 49 out of 99 failure reasons came from COMPLETED/UNKNOWN/ACTIVE trials
    where whyStopped is usually blank
  - "Ineffective for purpose" often found only in published papers
    describing negative results or failure to meet endpoints
  - "Toxic/Unsafe" sometimes found only in adverse event publications
  - "Business Reason" sometimes revealed in press releases or web sources
  - Humans actively searched literature — the agent must do the same
"""

import re
import logging
from typing import Optional

from agents.base import BaseAnnotationAgent
from app.models.research import ResearchResult, SourceCitation
from app.models.annotation import FieldAnnotation

logger = logging.getLogger("agent_annotate.annotation.failure_reason")

VALID_VALUES = [
    "Business Reason",
    "Ineffective for purpose",
    "Toxic/Unsafe",
    "Due to covid",
    "Recruitment issues",
]

# Pass 1: Extract all facts about why the trial may have failed
PASS1_PROMPT = """You are a clinical trial failure investigation specialist.

Your task: Investigate ALL available evidence to determine whether this trial failed, and if so, WHY. Do not stop at the ClinicalTrials.gov whyStopped field — dig deeper.

From the evidence below, extract:

1. TRIAL STATUS: The overallStatus from ClinicalTrials.gov (COMPLETED, TERMINATED, WITHDRAWN, etc.)

2. WHY STOPPED: The whyStopped field from ClinicalTrials.gov. If blank, say "Not provided".

3. PUBLISHED FINDINGS: Search PubMed, PMC, and web evidence for ANY mention of:
   - Trial results (positive OR negative)
   - Whether primary endpoints were met or not
   - Adverse events, toxicity, or safety concerns
   - Reasons for discontinuation mentioned in papers
   - Futility analyses
   Quote relevant excerpts.

4. OUTCOME SIGNALS: Does the evidence suggest the trial succeeded or failed?
   - "met primary endpoint" / "significant improvement" = success
   - "did not meet" / "no significant difference" / "failed to demonstrate" = failure
   - "adverse events led to" / "safety concerns" / "toxicity" = safety issue
   - "enrollment challenges" / "recruitment" = recruitment problem
   - "sponsor decision" / "business" / "funding" / "strategic" = business reason
   - "COVID" / "pandemic" = covid impact

5. IS THIS A FAILURE? Based on all evidence, does this trial appear to have failed, been terminated for cause, or been withdrawn?

Format your response EXACTLY as:
Trial Status: [status]
Why Stopped: [field value or "Not provided"]
Published Findings: [summary of findings from literature]
Outcome Signals: [what the evidence suggests]
Is This A Failure: [Yes/No/Unclear]"""

# Pass 2: Determine the specific reason
PASS2_PROMPT = """You are a clinical trial failure classification specialist. You have investigated a trial and extracted the following facts:

{pass1_output}

Based on ALL the evidence above, determine the reason for failure.

CRITICAL RULES:
1. Published literature is MORE RELIABLE than the whyStopped field. A trial with whyStopped="Sponsor decision" might actually have failed due to toxicity if papers report adverse events.
2. COMPLETED trials CAN have failure reasons — BUT ONLY if there is PUBLISHED EVIDENCE of negative outcomes (e.g., paper says "failed to meet primary endpoint", "no significant difference"). Do NOT assume failure just because a trial completed.
3. If the trial did NOT fail (positive results, still recruiting, etc.), return EMPTY.
4. Look beyond surface labels — "sponsor decision" often masks the real reason.
5. RECENCY: If multiple publications exist with conflicting findings, the most recent publication takes priority. Newer evidence supersedes older evidence.
6. DEFAULT FOR COMPLETED TRIALS: If status is COMPLETED and there is NO published evidence of negative outcomes, the answer is EMPTY. You MUST have POSITIVE evidence of failure (a paper, a press release, a data report showing negative results) to assign a failure reason to a completed trial. Absence of published results ≠ failure.
7. NEVER invent or assume a failure reason. If the evidence does not explicitly demonstrate failure, return EMPTY.

Choose EXACTLY ONE:
- Business Reason: Funding withdrawn, sponsor decision (with no efficacy/safety cause), company dissolved, strategic pivot, regulatory changes, manufacturing issues
- Ineffective for purpose: PUBLISHED results show trial FAILED to meet primary endpoints, no significant difference found, futility analysis. Requires EXPLICIT negative outcome data — not speculation.
- Toxic/Unsafe: Safety concerns, adverse events, toxicity findings, DSMB stopped for safety, published adverse event reports
- Due to covid: Trial specifically disrupted by COVID-19 pandemic
- Recruitment issues: Slow enrollment, unable to recruit, site closures (not COVID-related)
- EMPTY: Trial did not fail, OR no evidence of failure exists. This is the DEFAULT for COMPLETED trials without published negative results.

IMPORTANT: Format your response EXACTLY as:
Reason for Failure: [Business Reason, Ineffective for purpose, Toxic/Unsafe, Due to covid, Recruitment issues, or EMPTY]
Evidence: [cite the specific source that reveals the reason]
Reasoning: [explain your chain of thought, especially if the reason differs from whyStopped]"""


class FailureReasonAgent(BaseAnnotationAgent):
    """Determines reason for trial failure using two-pass investigation."""

    field_name = "reason_for_failure"

    async def annotate(
        self,
        nct_id: str,
        research_results: list[ResearchResult],
        metadata: Optional[dict] = None,
    ) -> FieldAnnotation:
        # --- PRE-CHECK: Skip if outcome is non-failure ---
        # If the outcome agent already determined this trial didn't fail,
        # don't bother running the LLM — return empty immediately.
        # This prevents the dominant error pattern where the 8B model
        # hallucinates "Ineffective for purpose" for non-failed trials.
        outcome_result = metadata.get("outcome_result", "") if metadata else ""
        if outcome_result in ("Positive", "Recruiting", "Active, not recruiting", "Unknown"):
            logger.info(
                f"  failure_reason: skipping — outcome='{outcome_result}' is non-failure"
            )
            return FieldAnnotation(
                field_name=self.field_name,
                value="",
                confidence=0.9,
                reasoning=f"[Pre-check skip] Outcome is '{outcome_result}' — no failure to explain.",
                evidence=[],
                model_name="deterministic",
            )

        from app.services.config_service import config_service

        _config = config_service.get()
        is_server = _config.orchestrator.hardware_profile == "server"
        max_cites = 50 if is_server else 30
        max_snippet = 500 if is_server else 250

        # Build structured evidence — sections help the LLM locate
        # termination reasons, published negative results, and safety data
        evidence_text, cited_sources = self.build_structured_evidence(
            nct_id, research_results,
            max_citations=max_cites,
            max_snippet_chars=max_snippet,
        )

        from app.services.ollama_client import ollama_client
        from app.services.config_service import config_service

        config = config_service.get()
        primary_model = None
        for model_key, model_cfg in config.verification.models.items():
            if model_cfg.role == "annotator":
                primary_model = model_cfg.name
                break
        if not primary_model:
            primary_model = "llama3.1:8b"

        # --- PASS 1: Investigate ---
        try:
            logger.info(f"  failure_reason: Pass 1 — investigating {nct_id}")
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
                value="",
                confidence=0.0,
                reasoning=f"Pass 1 LLM call failed: {e}",
                evidence=[],
                model_name=primary_model,
            )

        # Quick check: if pass 1 says "not a failure", skip pass 2
        if self._pass1_says_no_failure(pass1_output):
            return FieldAnnotation(
                field_name=self.field_name,
                value="",
                confidence=0.8,
                reasoning=f"[Pass 1] No failure detected. {pass1_output[:300]}",
                evidence=cited_sources[:10],
                model_name=primary_model,
            )

        # --- PASS 2: Classify the reason ---
        try:
            logger.info(f"  failure_reason: Pass 2 — classifying reason for {nct_id}")
            pass2_prompt = PASS2_PROMPT.format(pass1_output=pass1_output)
            pass2_response = await ollama_client.generate(
                model=primary_model,
                prompt=pass2_prompt + "\n\nOriginal evidence:\n" + evidence_text,
                temperature=config.ollama.temperature,
            )
            pass2_output = pass2_response.get("response", "")
        except Exception as e:
            value = self._normalize_failure_value(self._infer_from_pass1(pass1_output))
            return FieldAnnotation(
                field_name=self.field_name,
                value=value,
                confidence=0.3,
                reasoning=f"Pass 2 failed ({e}), inferred from pass 1: {pass1_output[:300]}",
                evidence=cited_sources[:10],
                model_name=primary_model,
            )

        value = self._parse_value(pass2_output)
        # Normalize through canonical mapper in case LLM returned a variant
        value = self._normalize_failure_value(value)
        reasoning = self._parse_reasoning(pass2_output)
        full_reasoning = f"[Pass 1 investigation] {pass1_output[:500]}\n[Pass 2 classification] {reasoning}"
        quality = sum(c.quality_score for c in cited_sources[:10]) / max(len(cited_sources[:10]), 1)

        return FieldAnnotation(
            field_name=self.field_name,
            value=value,
            confidence=quality,
            reasoning=full_reasoning,
            evidence=cited_sources[:10],
            model_name=primary_model,
        )

    def _pass1_says_no_failure(self, pass1_text: str) -> bool:
        """Check if Pass 1 clearly says this is not a failure.

        v4: Added COMPLETED-without-negative-evidence rule. If a trial
        is COMPLETED and there is no published evidence of negative outcomes,
        treat it as no failure. The agent must require POSITIVE evidence of
        failure, not assume failure from completion.

        v3: More robust detection — also catches positive signals,
        recruiting/active trials, and malformed Pass 1 output.
        Previously only matched exact "No" answer, missing cases where
        Pass 1 didn't format correctly or said "Unclear" despite positive
        evidence.
        """
        lower = pass1_text.lower()

        # Check the explicit "Is This A Failure" field
        match = re.search(r"is this a failure:?\s*(.+?)(?:\n|$)", lower)
        if match:
            answer = match.group(1).strip()
            if answer.startswith("no"):
                return True

        # Check for positive signals that override an "Unclear" answer
        has_positive = any(kw in lower for kw in [
            "met primary endpoint", "positive results", "efficacy demonstrated",
            "well tolerated", "safe and effective", "progressed to phase",
            "successful", "favorable",
        ])
        # Check for active/recruiting status
        is_active = any(kw in lower for kw in [
            "recruiting", "active_not_recruiting", "active, not recruiting",
            "enrolling_by_invitation", "not_yet_recruiting",
        ])
        # Check for PUBLISHED evidence of negative outcomes (required to call it a failure)
        has_failure = any(kw in lower for kw in [
            "terminated", "withdrawn", "failed to meet", "did not meet",
            "no significant difference", "futility", "adverse events led",
            "safety concerns", "stopped early", "discontinued",
            "negative results", "did not demonstrate", "failed to demonstrate",
        ])

        # Extract trial status
        status_match = re.search(r"trial status:?\s*(.+?)(?:\n|$)", lower)
        status = status_match.group(1).strip() if status_match else ""

        # If clearly active/recruiting and no failure evidence → not a failure
        if any(s in status for s in ["recruiting", "active", "enrolling"]):
            if not has_failure:
                return True

        # COMPLETED trials without published negative evidence → no failure
        # This is the key rule: COMPLETED + no published negative results = no failure reason.
        # The agent must find POSITIVE evidence of failure to assign a reason.
        if "completed" in status or "complete" in status:
            if not has_failure:
                return True

        # If positive signals and no failure evidence → not a failure
        if has_positive and not has_failure:
            return True

        return False

    def _infer_from_pass1(self, pass1_text: str) -> str:
        """Fallback: infer reason from Pass 1 if Pass 2 fails."""
        lower = pass1_text.lower()

        # Check published findings for signals
        findings_match = re.search(r"published findings?:\s*(.+?)(?:\n[A-Z]|\Z)", lower, re.DOTALL)
        findings = findings_match.group(1) if findings_match else ""

        signals_match = re.search(r"outcome signals?:\s*(.+?)(?:\n[A-Z]|\Z)", lower, re.DOTALL)
        signals = signals_match.group(1) if signals_match else ""

        combined = findings + " " + signals

        if any(kw in combined for kw in ["toxicity", "adverse", "safety", "unsafe", "dsmb"]):
            return "Toxic/Unsafe"
        if any(kw in combined for kw in ["did not meet", "no significant", "failed to", "ineffective", "futility"]):
            return "Ineffective for purpose"
        if any(kw in combined for kw in ["covid", "pandemic"]):
            return "Due to covid"
        if any(kw in combined for kw in ["recruit", "enrollment", "accrual"]):
            return "Recruitment issues"
        if any(kw in combined for kw in ["sponsor", "funding", "business", "strategic"]):
            return "Business Reason"

        # Check whyStopped field
        why_match = re.search(r"why stopped:\s*(.+?)(?:\n|$)", lower)
        if why_match:
            why = why_match.group(1).strip()
            if why != "not provided" and why:
                if any(kw in why for kw in ["toxic", "safety", "adverse"]):
                    return "Toxic/Unsafe"
                if any(kw in why for kw in ["efficacy", "futility", "endpoint"]):
                    return "Ineffective for purpose"
                if any(kw in why for kw in ["covid", "pandemic"]):
                    return "Due to covid"
                if any(kw in why for kw in ["recruit", "enrollment"]):
                    return "Recruitment issues"
                return "Business Reason"

        return ""

    def _parse_value(self, text: str) -> str:
        match = re.search(r"Reason for Failure:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
        if match:
            raw = match.group(1).strip()
            return self._normalize_failure_value(raw)
        return ""

    @staticmethod
    def _normalize_failure_value(raw: str) -> str:
        """Normalize any failure reason string to a canonical value.

        v7: All output paths route through this method to prevent
        non-canonical values (INEFFECTIVE_FOR_PURPOSE, INEFFECIVE_FOR_PURPOSE,
        EMPTY) from reaching the output.
        """
        lower = raw.strip().lower()

        # Empty/no-failure indicators
        if lower in ("empty", "n/a", "not applicable", "none", "",
                      "no failure", "no reason", "completed", "unknown",
                      "active", "recruiting", "positive"):
            return ""

        for valid in VALID_VALUES:
            if valid.lower() == lower:
                return valid

        # Fuzzy matching — catches typos and uppercase sentinel values
        if "business" in lower or "funding" in lower or "sponsor" in lower or "administrative" in lower:
            return "Business Reason"
        if "ineffect" in lower or "efficacy" in lower or "futility" in lower or "endpoint" in lower:
            return "Ineffective for purpose"
        if "toxic" in lower or "safety" in lower or "unsafe" in lower or "adverse" in lower:
            return "Toxic/Unsafe"
        if "covid" in lower or "pandemic" in lower or "coronavirus" in lower:
            return "Due to covid"
        if "recruit" in lower or "enrollment" in lower or "accrual" in lower:
            return "Recruitment issues"
        return ""

    def _parse_reasoning(self, text: str) -> str:
        match = re.search(r"Reasoning:\s*(.+?)(?:\n\n|$)", text, re.DOTALL)
        if match:
            return match.group(1).strip()[:500]
        return text[:500]
