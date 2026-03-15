"""
Classification Annotation Agent.

Determines whether a clinical trial involves an Antimicrobial Peptide (AMP) and its purpose.
"""

import re
from typing import Optional

from agents.base import BaseAnnotationAgent, FIELD_RELEVANCE
from app.models.research import ResearchResult, SourceCitation
from app.models.annotation import FieldAnnotation

VALID_VALUES = ["AMP(infection)", "AMP(other)", "Other"]

SYSTEM_PROMPT = """You are a clinical trial classification specialist focused on antimicrobial peptides (AMPs).

Your task: Classify a clinical trial into one of exactly three categories.

Valid classifications:
- AMP(infection): The trial involves an antimicrobial peptide and the primary purpose is targeting infection or pathogens (bacterial, fungal, viral). This includes trials where the AMP is used to treat, prevent, or manage infectious disease.
- AMP(other): The trial involves an antimicrobial peptide but the primary purpose is NOT treating infection. Instead it targets other conditions such as wound healing, immunomodulation, cancer, inflammation, or other non-infection applications.
- Other: The trial does NOT involve an antimicrobial peptide. The intervention is a small molecule drug, antibody, vaccine (unless peptide-based), gene therapy, device, or any non-AMP intervention.

Step 1 — Is the intervention an AMP?
Key indicators for AMP:
- Intervention names containing: peptide, antimicrobial peptide, AMP, defensin, cathelicidin, LL-37, melittin, nisin, polymyxin, colistin, daptomycin, gramicidin, magainin, cecropin, protegrin, indolicidin, lactoferricin
- UniProt/DRAMP matches for the intervention
- Keywords mentioning antimicrobial peptide activity
- Brief summary describing peptide-based antimicrobial therapy

If NOT an AMP -> classify as "Other".

Step 2 — If it IS an AMP, what is the primary purpose?
- Treating/preventing infection or targeting pathogens -> AMP(infection)
- Wound healing, immunomodulation, cancer, anti-inflammatory, or any non-infection purpose -> AMP(other)

Key indicators for Other (not AMP):
- Small molecule drugs (named with -ib, -mab suffixes that aren't peptides)
- Monoclonal antibodies (large proteins, not peptides)
- Vaccines, gene therapies, medical devices
- No peptide-related terms in interventions or descriptions

IMPORTANT: You must cite the specific evidence for your decision. Format your response EXACTLY as:

Classification: [AMP(infection), AMP(other), or Other]
Evidence: [Cite the specific source, identifier, and excerpt that supports your decision]
Reasoning: [Brief chain-of-thought explanation]"""


class ClassificationAgent(BaseAnnotationAgent):
    """Determines AMP vs Other classification."""

    field_name = "classification"

    async def annotate(
        self,
        nct_id: str,
        research_results: list[ResearchResult],
        metadata: Optional[dict] = None,
    ) -> FieldAnnotation:
        # Gather all relevant citations from research
        all_citations = []
        for result in research_results:
            weight = self.relevance_weight(result.agent_name)
            for citation in result.citations:
                all_citations.append((citation, weight))

        # Sort by relevance weight descending
        all_citations.sort(key=lambda x: x[1], reverse=True)

        # Build evidence text for the LLM prompt
        evidence_text = f"Trial: {nct_id}\n\n"
        cited_sources = []
        for citation, weight in all_citations[:20]:
            evidence_text += f"[{citation.source_name}] {citation.identifier or ''}: {citation.snippet}\n"
            cited_sources.append(citation)

        # Call LLM
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

        # Parse response
        value = self._parse_value(raw_text)
        reasoning = self._parse_reasoning(raw_text)

        # Compute quality score from citations
        unique_sources = set(c.source_name for c in cited_sources)
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
        # Try to match the full classification line
        match = re.search(r"Classification:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
        if match:
            raw = match.group(1).strip().lower()
            if "amp(infection)" in raw or "amp (infection)" in raw:
                return "AMP(infection)"
            if "amp(other)" in raw or "amp (other)" in raw:
                return "AMP(other)"
            if raw == "other":
                return "Other"
            # Fallback: if they just said "AMP" without subtype, check context
            if "amp" in raw and "other" not in raw:
                # Check if infection-related context is present
                lower_text = text.lower()
                if any(kw in lower_text for kw in ["infection", "pathogen", "antibacterial", "antifungal", "antiviral", "antimicrobial resistance"]):
                    return "AMP(infection)"
                return "AMP(other)"
            return "Other"
        # Fallback: scan early text for AMP mentions
        lower_text = text.lower()
        if "amp(infection)" in lower_text or "amp (infection)" in lower_text:
            return "AMP(infection)"
        if "amp(other)" in lower_text or "amp (other)" in lower_text:
            return "AMP(other)"
        return "Other"

    def _parse_reasoning(self, text: str) -> str:
        match = re.search(r"Reasoning:\s*(.+?)(?:\n\n|$)", text, re.DOTALL)
        if match:
            return match.group(1).strip()[:500]
        return text[:500]
