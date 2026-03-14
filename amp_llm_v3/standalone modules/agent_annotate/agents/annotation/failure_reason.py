"""
Failure Reason Annotation Agent.

Determines why a trial failed, was terminated, or was withdrawn.
"""

import re
from typing import Optional

from agents.base import BaseAnnotationAgent
from app.models.research import ResearchResult, SourceCitation
from app.models.annotation import FieldAnnotation

VALID_VALUES = ["Business Reason", "Ineffective for purpose", "Toxic/Unsafe", "Due to covid", "Recruitment issues"]

SYSTEM_PROMPT = """You are a clinical trial failure analysis specialist.

Your task: Determine the reason a clinical trial was terminated, withdrawn, or failed.

IMPORTANT: This field only applies to trials with a negative outcome (Withdrawn, Terminated, or Failed - completed trial). If the trial outcome is Positive, Recruiting, Active, or Unknown, return an EMPTY value — do NOT provide a reason.

Valid reasons (use these exact strings):
- Business Reason: Funding withdrawn, sponsor decision, company acquired/dissolved, strategic pivot, regulatory pathway changed, manufacturing issues, administrative reasons
- Ineffective for purpose: Trial failed to show efficacy, did not meet primary endpoints, futility analysis led to stopping
- Toxic/Unsafe: Safety concerns, unacceptable adverse events, toxicity findings, DSMB recommendation to stop for safety
- Due to covid: Trial disrupted by COVID-19 pandemic (enrollment, site access, supply chain)
- Recruitment issues: Unable to recruit sufficient participants, slow enrollment, site closures unrelated to COVID

Key data:
- whyStopped field from ClinicalTrials.gov is the primary indicator
- Published literature may explain failure reasons
- Web sources may have press releases about termination

Decision rules:
1. If trial outcome is Positive, Recruiting, Active, or Unknown -> leave EMPTY (no reason)
2. If whyStopped mentions funding, business, sponsor, administrative -> Business Reason
3. If whyStopped mentions efficacy, futility, endpoint, ineffective -> Ineffective for purpose
4. If whyStopped mentions safety, toxicity, adverse events -> Toxic/Unsafe
5. If whyStopped mentions COVID, pandemic, coronavirus -> Due to covid
6. If whyStopped mentions enrollment, recruitment, accrual -> Recruitment issues
7. If no whyStopped and trial is terminated/withdrawn -> check literature for the reason

IMPORTANT: Format your response EXACTLY as:

Reason for Failure: [Business Reason, Ineffective for purpose, Toxic/Unsafe, Due to covid, Recruitment issues, or EMPTY]
Evidence: [Cite the specific source and excerpt]
Reasoning: [Brief explanation]

If not applicable (trial is active/positive/unknown), respond:

Reason for Failure: EMPTY
Evidence: Not applicable — trial outcome does not indicate failure.
Reasoning: This field only applies to failed/terminated/withdrawn trials."""


class FailureReasonAgent(BaseAnnotationAgent):
    """Determines reason for trial failure/termination."""

    field_name = "reason_for_failure"

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
                value="",
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
        match = re.search(r"Reason for Failure:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
        if match:
            raw = match.group(1).strip()
            lower = raw.lower()

            # Empty / not applicable
            if lower in ("empty", "n/a", "not applicable", "none", ""):
                return ""

            # Exact match first (case-insensitive)
            for valid in VALID_VALUES:
                if valid.lower() == lower:
                    return valid

            # Fuzzy matching
            if "business" in lower or "funding" in lower or "sponsor" in lower or "administrative" in lower:
                return "Business Reason"
            if "ineffective" in lower or "efficacy" in lower or "futility" in lower or "endpoint" in lower:
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
