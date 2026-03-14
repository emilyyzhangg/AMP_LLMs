"""
Outcome Annotation Agent.

Determines the trial outcome status.
"""

import re
from typing import Optional

from agents.base import BaseAnnotationAgent
from app.models.research import ResearchResult, SourceCitation
from app.models.annotation import FieldAnnotation

VALID_VALUES = [
    "Positive",
    "Withdrawn",
    "Terminated",
    "Failed - completed trial",
    "Recruiting",
    "Unknown",
    "Active, not recruiting",
]

SYSTEM_PROMPT = """You are a clinical trial outcome assessment specialist.

Your task: Determine the outcome of this clinical trial.

You must choose EXACTLY ONE of these outcomes:
- Positive: Trial completed and met its primary endpoint(s). Published results show efficacy/positive findings.
- Withdrawn: Trial was withdrawn before enrollment or very early, often for administrative/funding reasons.
- Terminated: Trial was stopped early due to safety concerns, futility, lack of enrollment, or sponsor decision.
- Failed - completed trial: Trial completed enrollment and follow-up but FAILED to meet primary endpoint(s). Negative results.
- Recruiting: Trial is currently recruiting participants, or is not yet recruiting, or enrolling by invitation. Any pre-completion active status.
- Unknown: Insufficient data to determine outcome. Status is ambiguous or completed with no available results.
- Active, not recruiting: Trial is ongoing but no longer enrolling new participants.

Key data points to evaluate:
- overallStatus field: COMPLETED, TERMINATED, WITHDRAWN, RECRUITING, ACTIVE_NOT_RECRUITING, NOT_YET_RECRUITING, ENROLLING_BY_INVITATION, etc.
- whyStopped field: Reason for early termination
- hasResults: Whether results have been posted
- Published literature describing trial results
- Primary/secondary outcome measures and their results

Decision logic:
1. If overallStatus is WITHDRAWN -> Withdrawn
2. If overallStatus is TERMINATED -> Terminated
3. If overallStatus is RECRUITING, NOT_YET_RECRUITING, ENROLLING_BY_INVITATION -> Recruiting
4. If overallStatus is ACTIVE_NOT_RECRUITING -> Active, not recruiting
5. If overallStatus is COMPLETED:
   a. Check published results: positive findings -> Positive
   b. Check published results: negative/failed -> Failed - completed trial
   c. No results available -> Unknown (do NOT guess)
6. If unclear -> Unknown

IMPORTANT: Format your response EXACTLY as:

Outcome: [Positive, Withdrawn, Terminated, Failed - completed trial, Recruiting, Unknown, or Active, not recruiting]
Evidence: [Cite the specific source and excerpt]
Reasoning: [Brief explanation]"""


class OutcomeAgent(BaseAnnotationAgent):
    """Determines trial outcome."""

    field_name = "outcome"

    async def annotate(
        self,
        nct_id: str,
        research_results: list[ResearchResult],
        metadata: Optional[dict] = None,
    ) -> FieldAnnotation:
        all_citations = []
        for result in research_results:
            weight = self.relevance_weight(result.agent_name)
            for citation in result.citations:
                all_citations.append((citation, weight))

        all_citations.sort(key=lambda x: x[1], reverse=True)

        evidence_text = f"Trial: {nct_id}\n\n"
        cited_sources = []
        for citation, weight in all_citations[:20]:
            evidence_text += f"[{citation.source_name}] {citation.identifier or ''}: {citation.snippet}\n"
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

        try:
            response = await ollama_client.generate(
                model=primary_model,
                prompt=evidence_text,
                system=SYSTEM_PROMPT,
                temperature=config.ollama.temperature,
            )
            raw_text = response.get("response", "")
        except Exception as e:
            return FieldAnnotation(
                field_name=self.field_name,
                value="Unknown",
                confidence=0.0,
                reasoning=f"LLM call failed: {e}",
                evidence=[],
                model_name=primary_model,
            )

        value = self._parse_value(raw_text)
        reasoning = self._parse_reasoning(raw_text)
        quality = sum(c.quality_score for c in cited_sources[:10]) / max(len(cited_sources[:10]), 1)

        return FieldAnnotation(
            field_name=self.field_name,
            value=value,
            confidence=quality,
            reasoning=reasoning,
            evidence=cited_sources[:10],
            model_name=primary_model,
        )

    def _parse_value(self, text: str) -> str:
        match = re.search(r"Outcome:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
        if match:
            raw = match.group(1).strip()
            lower = raw.lower()

            # Exact match first (case-insensitive)
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
