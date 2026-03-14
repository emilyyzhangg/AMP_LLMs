"""
Peptide Annotation Agent.

Determines whether the intervention is a peptide (True/False).
"""

import re
from typing import Optional

from agents.base import BaseAnnotationAgent
from app.models.research import ResearchResult, SourceCitation
from app.models.annotation import FieldAnnotation

VALID_VALUES = ["True", "False"]

SYSTEM_PROMPT = """You are a peptide identification specialist for clinical trials.

Your task: Determine whether the primary intervention in this clinical trial is a peptide (True or False).

A peptide is:
- A chain of amino acids, typically 2-100 residues (though some therapeutic peptides are larger)
- Includes: antimicrobial peptides, hormone analogues (GnRH, somatostatin, GLP-1), cyclic peptides, peptide vaccines, cell-penetrating peptides, peptide-drug conjugates
- Includes known peptide drugs: colistin, daptomycin, polymyxin B, nisin, vancomycin (glycopeptide), gramicidin, bacitracin, tyrothricin, LL-37, defensins, melittin, magainin, cecropin, octreotide, leuprolide, goserelin, exenatide, liraglutide, semaglutide

NOT a peptide:
- Monoclonal antibodies (too large, different class — e.g., pembrolizumab, trastuzumab)
- Small molecule drugs (e.g., amoxicillin, ciprofloxacin, metformin)
- Gene therapies, cell therapies, medical devices
- Whole proteins (e.g., interferons, erythropoietin) — unless specifically described as peptide fragments

Key evidence sources:
- UniProt matches: if the intervention maps to a UniProt entry with "Antimicrobial" or peptide-related keywords -> True
- DRAMP/DBAASP matches: if found in antimicrobial peptide databases -> True
- Intervention description: look for "peptide", "amino acid", "sequence" terms
- Drug class: look for classification as peptide therapeutic

IMPORTANT: Format your response EXACTLY as:

Peptide: [True or False]
Evidence: [Cite the specific source and excerpt]
Reasoning: [Brief explanation]"""


class PeptideAgent(BaseAnnotationAgent):
    """Determines if the intervention is a peptide."""

    field_name = "peptide"

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
                value="False",
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
        match = re.search(r"Peptide:\s*(True|False)", text, re.IGNORECASE)
        if match:
            return "True" if match.group(1).lower() == "true" else "False"
        lower = text.lower()
        if "peptide: true" in lower or "is a peptide" in lower:
            return "True"
        return "False"

    def _parse_reasoning(self, text: str) -> str:
        match = re.search(r"Reasoning:\s*(.+?)(?:\n\n|$)", text, re.DOTALL)
        if match:
            return match.group(1).strip()[:500]
        return text[:500]
