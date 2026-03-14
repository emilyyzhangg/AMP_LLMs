"""
Failure Reason Annotation Agent.

Determines why a trial failed, was terminated, or was withdrawn.
"""

import re
from typing import Optional

from agents.base import BaseAnnotationAgent
from app.models.research import ResearchResult, SourceCitation
from app.models.annotation import FieldAnnotation

VALID_VALUES = ["Business reasons", "Ineffective", "Toxic/unsafe", "COVID", "Recruitment issues", "N/A"]

SYSTEM_PROMPT = """You are a clinical trial failure analysis specialist.

Your task: Determine the reason a clinical trial was terminated, withdrawn, or failed.

Valid reasons:
- Business reasons: Funding withdrawn, sponsor decision, company acquired/dissolved, strategic pivot, regulatory pathway changed, manufacturing issues
- Ineffective: Trial failed to show efficacy, did not meet primary endpoints, futility analysis led to stopping
- Toxic/unsafe: Safety concerns, unacceptable adverse events, toxicity findings, DSMB recommendation to stop for safety
- COVID: Trial disrupted by COVID-19 pandemic (enrollment, site access, supply chain)
- Recruitment issues: Unable to recruit sufficient participants, slow enrollment, site closures unrelated to COVID
- N/A: Trial is active, completed successfully, or the reason cannot be determined. Use this when the trial has a Positive or Active outcome.

Key data:
- whyStopped field from ClinicalTrials.gov is the primary indicator
- overallStatus: if COMPLETED with positive results -> N/A
- Published literature may explain failure reasons
- Web sources may have press releases about termination

Decision rules:
1. If trial is Active or Positive outcome -> N/A
2. If whyStopped mentions funding, business, sponsor -> Business reasons
3. If whyStopped mentions efficacy, futility, endpoint -> Ineffective
4. If whyStopped mentions safety, toxicity, adverse -> Toxic/unsafe
5. If whyStopped mentions COVID, pandemic -> COVID
6. If whyStopped mentions enrollment, recruitment -> Recruitment issues
7. If no whyStopped and trial is terminated/withdrawn -> check literature, else N/A

IMPORTANT: Format your response EXACTLY as:

Reason for Failure: [Business reasons, Ineffective, Toxic/unsafe, COVID, Recruitment issues, or N/A]
Evidence: [Cite the specific source and excerpt]
Reasoning: [Brief explanation]"""


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
                value="N/A",
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
            raw = match.group(1).strip().lower()
            if "business" in raw or "funding" in raw or "sponsor" in raw:
                return "Business reasons"
            if "ineffective" in raw or "efficacy" in raw or "futility" in raw:
                return "Ineffective"
            if "toxic" in raw or "safety" in raw or "unsafe" in raw or "adverse" in raw:
                return "Toxic/unsafe"
            if "covid" in raw or "pandemic" in raw:
                return "COVID"
            if "recruit" in raw or "enrollment" in raw:
                return "Recruitment issues"
            if "n/a" in raw or "not applicable" in raw:
                return "N/A"
        return "N/A"

    def _parse_reasoning(self, text: str) -> str:
        match = re.search(r"Reasoning:\s*(.+?)(?:\n\n|$)", text, re.DOTALL)
        if match:
            return match.group(1).strip()[:500]
        return text[:500]
