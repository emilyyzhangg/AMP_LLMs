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

Your task: Determine whether the primary intervention in this clinical trial is a peptide THERAPEUTIC (True or False).

DEFINITION: A peptide therapeutic is a chain of amino acids (typically 2-100 residues, though some are larger) used AS THE ACTIVE DRUG.

WORKED EXAMPLES — study these carefully before answering:

Example 1: Aviptadil (VIP analogue, 28 amino acids, IV infusion for COVID-19)
→ Peptide: True
Why: VIP/Aviptadil is a 28-amino-acid peptide hormone used as the active drug.

Example 2: Kate Farm Peptide 1.5 (nutritional formula for gastroparesis)
→ Peptide: False
Why: "Peptide" in the product name refers to hydrolyzed protein for digestion. The peptides are food ingredients, NOT the active drug. This is a nutritional product.

Example 3: Semaglutide (GLP-1 receptor agonist, 31 amino acids, for diabetes)
→ Peptide: True
Why: Semaglutide is a 31-amino-acid synthetic peptide hormone analogue.

Example 4: Pembrolizumab (monoclonal antibody, ~150 kDa, for cancer)
→ Peptide: False
Why: Monoclonal antibodies are too large (~1300 amino acids) and are a different drug class from peptides.

Example 5: StreptInCor (synthetic peptide vaccine, 55 amino acids, for S. pyogenes)
→ Peptide: True
Why: StreptInCor is a designed synthetic polypeptide vaccine — the active agent IS a peptide.

Example 6: Colistin (cyclic lipopeptide antibiotic, for bacterial infections)
→ Peptide: True
Why: Colistin is a cyclic lipopeptide — a classic antimicrobial peptide drug.

Example 7: Amoxicillin (small molecule antibiotic)
→ Peptide: False
Why: Small molecule drug, not a peptide chain.

Example 8: Apraglutide (GLP-2 analogue, for GvHD)
→ Peptide: True
Why: GLP-2 analogues are synthetic peptide hormone therapeutics.

Example 9: GSK3732394 (multi-subunit engineered protein, for HIV)
→ Peptide: False
Why: Large engineered multi-subunit protein scaffold — functionally closer to an antibody than a peptide.

Example 10: Hydrolyzed whey protein formula (for infant nutrition)
→ Peptide: False
Why: Nutritional product. The protein is broken into peptides for easier digestion, but the peptides are food, not a drug.

KEY RULE: The question is whether the ACTIVE DRUG is a peptide, not whether the formulation contains peptides. If the product name includes "peptide" but the product is a nutritional formula, shake, or tube feeding product → False.

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
