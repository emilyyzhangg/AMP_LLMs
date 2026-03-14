"""
Delivery Mode Annotation Agent.

Determines how the drug/intervention is administered.
"""

import re
from typing import Optional

from agents.base import BaseAnnotationAgent
from app.models.research import ResearchResult, SourceCitation
from app.models.annotation import FieldAnnotation

VALID_VALUES = ["Injection/Infusion", "Topical", "Oral", "Other"]

SYSTEM_PROMPT = """You are a clinical trial delivery mode specialist.

Your task: Determine the route of administration for the primary intervention in this clinical trial.

Valid delivery modes:
- Injection/Infusion: Intravenous (IV), intramuscular (IM), subcutaneous (SC), intrathecal, intraperitoneal, or any injection/infusion route
- Topical: Applied to skin, wounds, mucous membranes, or body surfaces. Includes creams, ointments, gels, sprays, rinses, eye drops, ear drops, nasal sprays
- Oral: Taken by mouth — tablets, capsules, liquids, lozenges, sublingual
- Other: Inhalation, rectal, vaginal, implanted devices, or routes not covered above

Look for these indicators:
- Intervention type field (DRUG, BIOLOGICAL, DEVICE)
- Route descriptions in intervention details or arm group descriptions
- Drug labels from OpenFDA showing approved routes
- Keywords: IV, intravenous, subcutaneous, SC, IM, topical, cream, ointment, oral, tablet, capsule

IMPORTANT: Format your response EXACTLY as:

Delivery Mode: [Injection/Infusion, Topical, Oral, or Other]
Evidence: [Cite the specific source and excerpt]
Reasoning: [Brief explanation]"""


class DeliveryModeAgent(BaseAnnotationAgent):
    """Determines drug delivery mode."""

    field_name = "delivery_mode"

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
                value="Other",
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
        match = re.search(r"Delivery Mode:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
        if match:
            raw = match.group(1).strip()
            lower = raw.lower()
            if "injection" in lower or "infusion" in lower or "intravenous" in lower or "subcutaneous" in lower:
                return "Injection/Infusion"
            if "topical" in lower or "cream" in lower or "ointment" in lower:
                return "Topical"
            if "oral" in lower or "tablet" in lower or "capsule" in lower:
                return "Oral"
            return "Other"
        return "Other"

    def _parse_reasoning(self, text: str) -> str:
        match = re.search(r"Reasoning:\s*(.+?)(?:\n\n|$)", text, re.DOTALL)
        if match:
            return match.group(1).strip()[:500]
        return text[:500]
