"""
Outcome Annotation Agent (v2 — investigative).

Determines trial outcome using a two-pass strategy:
  Pass 1: Extract ClinicalTrials.gov status as a starting point
  Pass 2: Investigate published literature to confirm, update, or override

This design addresses the common failure mode where agents see "UNKNOWN" or
"COMPLETED" in ClinicalTrials.gov and stop investigating. Human annotators
found that 15+ UNKNOWN-status trials actually had positive results in
published literature, and 61 COMPLETED trials had no published results
(correctly annotated as Unknown).

Key insight from human annotation data:
  - ClinicalTrials.gov status is often STALE or INCOMPLETE
  - Published literature (PubMed, PMC) is the authoritative source for actual results
  - Even TERMINATED trials can have positive published results (5 cases in dataset)
  - UNKNOWN status requires active investigation, not a default "Unknown" answer
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

# Pass 1: Extract the registry status and what we know so far
PASS1_PROMPT = """You are a clinical trial status extraction specialist.

Your task: Extract the FACTUAL STATUS of this trial from the ClinicalTrials.gov data, then summarize what published literature says about its results.

From the evidence below, extract:

1. REGISTRY STATUS: The overallStatus from ClinicalTrials.gov (e.g., COMPLETED, TERMINATED, RECRUITING, UNKNOWN, WITHDRAWN, ACTIVE_NOT_RECRUITING, NOT_YET_RECRUITING, ENROLLING_BY_INVITATION, SUSPENDED). If not found, say "NOT FOUND".

2. PUBLISHED RESULTS: Search the PubMed, PMC, and web evidence for ANY mention of trial results, outcomes, findings, efficacy, or conclusions. Quote the relevant excerpts. If there are multiple publications, list each one.

3. RESULTS POSTED: Does ClinicalTrials.gov indicate results have been posted? (hasResults field)

4. COMPLETION DATE: When did/will the trial complete?

5. WHY STOPPED: If terminated or withdrawn, what reason was given?

Format your response EXACTLY as:
Registry Status: [status from ClinicalTrials.gov]
Published Results: [summary of any published findings, or "None found"]
Results Posted: [Yes/No/Unknown]
Completion Date: [date or Unknown]
Why Stopped: [reason or N/A]"""

# Pass 2: Make the outcome determination with all facts in hand
PASS2_PROMPT = """You are a clinical trial outcome assessment specialist. You have already extracted the facts about this trial. Now you must determine the outcome.

CRITICAL RULES:
1. Published literature OVERRIDES ClinicalTrials.gov status. A trial with UNKNOWN or TERMINATED status in the registry can still have a Positive outcome if published papers show efficacy.
2. ClinicalTrials.gov status is often outdated. Do NOT default to "Unknown" just because the registry says UNKNOWN.
3. Only use "Unknown" when you have EXHAUSTIVELY checked all evidence sources AND found NO published results AND the trial status is ambiguous.

The facts you extracted:
{pass1_output}

Based on these facts, choose EXACTLY ONE outcome:
- Positive: Published results demonstrate efficacy or positive findings. This can apply even if the registry status is UNKNOWN, TERMINATED, or COMPLETED — what matters is whether published literature reports positive results.
- Failed - completed trial: Trial completed but published results show it FAILED to meet endpoints. Negative results published.
- Terminated: Trial was stopped early AND no positive published results exist. If it was terminated but published positive results anyway, choose Positive instead.
- Withdrawn: Trial was withdrawn before meaningful enrollment.
- Recruiting: Trial is actively recruiting (RECRUITING, NOT_YET_RECRUITING, ENROLLING_BY_INVITATION status) and no results exist yet.
- Active, not recruiting: Trial is ongoing but no longer enrolling (ACTIVE_NOT_RECRUITING) and no results exist yet.
- Unknown: You checked ALL available evidence (registry, publications, web) and genuinely cannot determine the outcome. This is a LAST RESORT, not a default.

IMPORTANT: Format your response EXACTLY as:
Outcome: [one of the 7 values above]
Evidence: [cite the specific source that determined your decision]
Reasoning: [explain your chain of thought, especially if overriding the registry status]"""


class OutcomeAgent(BaseAnnotationAgent):
    """Determines trial outcome using two-pass investigation."""

    field_name = "outcome"

    async def annotate(
        self,
        nct_id: str,
        research_results: list[ResearchResult],
        metadata: Optional[dict] = None,
    ) -> FieldAnnotation:
        # Gather all citations, prioritizing clinical_protocol and literature
        all_citations = []
        for result in research_results:
            weight = self.relevance_weight(result.agent_name)
            for citation in result.citations:
                all_citations.append((citation, weight))

        all_citations.sort(key=lambda x: x[1], reverse=True)

        # Build evidence text — include MORE citations than other agents
        # because outcome determination requires thorough investigation
        evidence_text = f"Trial: {nct_id}\n\nAll available evidence:\n"
        cited_sources = []
        for citation, weight in all_citations[:30]:  # More than the usual 20
            evidence_text += (
                f"[{citation.source_name}] {citation.identifier or ''}: "
                f"{citation.snippet}\n"
            )
            cited_sources.append(citation)

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

        quality = sum(c.quality_score for c in cited_sources[:10]) / max(len(cited_sources[:10]), 1)

        return FieldAnnotation(
            field_name=self.field_name,
            value=value,
            confidence=quality,
            reasoning=full_reasoning,
            evidence=cited_sources[:10],
            model_name=primary_model,
        )

    def _infer_from_pass1(self, pass1_text: str) -> str:
        """Fallback: infer outcome from pass 1 extraction if pass 2 fails."""
        lower = pass1_text.lower()

        # Check for published results first (most important signal)
        has_results = "published results:" in lower
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
        if status_match:
            status = status_match.group(1).strip()
            if "withdrawn" in status:
                return "Withdrawn"
            if "terminated" in status:
                return "Terminated"
            if "recruiting" in status and "not" not in status and "active" not in status:
                return "Recruiting"
            if "active_not_recruiting" in status:
                return "Active, not recruiting"

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
