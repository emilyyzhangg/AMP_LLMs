"""
Peptide Annotation Agent.

Determines whether the intervention is a peptide (True/False).

v2 changes (from 70-trial concordance analysis):
  - Added KNOWN_PEPTIDE_DRUGS and KNOWN_NON_PEPTIDE_DRUGS dicts for deterministic
    lookup before invoking the LLM. This addresses both over-identification
    (Agent=True, Human=False) and under-identification (Agent=False, Human=True).
  - Enhanced prompt with more edge cases from the concordance disagreements.
"""

import re
import logging
from typing import Optional

from agents.base import BaseAnnotationAgent
from app.models.research import ResearchResult, SourceCitation
from app.models.annotation import FieldAnnotation

logger = logging.getLogger("agent_annotate.annotation.peptide")

# Known peptide drugs — if any of these appear as the primary intervention,
# the answer is True regardless of LLM output.
KNOWN_PEPTIDE_DRUGS = {
    # GLP-1/GLP-2 analogues
    "semaglutide", "liraglutide", "dulaglutide", "exenatide", "lixisenatide",
    "apraglutide", "teduglutide", "tirzepatide",
    # Antimicrobial peptides
    "colistin", "polymyxin", "daptomycin", "vancomycin", "telavancin",
    "nisin", "gramicidin", "bacitracin",
    # Host defense peptides
    "ll-37", "cathelicidin", "defensin",
    # Hormones and analogues
    "insulin", "insulin glargine", "insulin degludec", "insulin lispro",
    "insulin aspart", "insulin detemir",
    "oxytocin", "vasopressin", "desmopressin", "terlipressin",
    "octreotide", "lanreotide", "pasireotide",
    "leuprolide", "goserelin", "triptorelin", "buserelin", "nafarelin",
    "cetrorelix", "ganirelix", "degarelix",
    "teriparatide", "abaloparatide", "calcitonin",
    "pramlintide", "glucagon",
    "vosoritide",
    # HIV peptides
    "enfuvirtide", "t-20", "fuzeon", "peptide t",
    # Other therapeutic peptides
    "aviptadil", "icatibant", "nesiritide", "ziconotide",
    "bortezomib", "carfilzomib", "romiplostim",
    "cyclosporine", "ciclosporin",
    "bleomycin",  # glycopeptide antibiotic
    "teicoplanin", "dalbavancin", "oritavancin",
    "bivalirudin", "eptifibatide",
    "lutetium lu 177 dotatate", "dotatate", "dotatoc",
    "thymalfasin", "thymosin",
    "streptincor",
}

# Known NON-peptide drugs — if these appear as the primary intervention,
# the answer is False. Prevents over-identification.
KNOWN_NON_PEPTIDE_DRUGS = {
    # Small molecule antibiotics
    "amoxicillin", "ciprofloxacin", "metronidazole", "rifampicin",
    "isoniazid", "ethambutol", "pyrazinamide", "doxycycline",
    "azithromycin", "clarithromycin", "fluconazole", "acyclovir",
    "oseltamivir", "tenofovir", "emtricitabine", "efavirenz",
    "lopinavir", "ritonavir", "atazanavir", "darunavir",
    "etoposide", "paclitaxel", "vincristine",
    # Monoclonal antibodies
    "pembrolizumab", "nivolumab", "atezolizumab", "ipilimumab",
    "trastuzumab", "bevacizumab", "rituximab", "adalimumab",
    "infliximab", "tocilizumab",
    # Nutritional products
    "kate farm", "peptamen", "peptide 1.5", "ensure", "jevity",
    "nutren", "isosource", "vivonex",
}

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

Example 11: "Peptide 1.5" (tube feeding formula for ICU patients)
→ Peptide: False
Why: "Peptide 1.5" is a BRAND NAME for a nutritional formula. The word "peptide" in the name refers to hydrolyzed protein for easier digestion. This is a dietary supplement, NOT a peptide drug.

Example 12: Peptamen (semi-elemental nutritional formula)
→ Peptide: False
Why: Peptamen is a nutritional formula containing peptide-based protein for enteral feeding. Not a peptide drug.

CRITICAL RULES:
1. The question is whether the ACTIVE DRUG is a peptide, not whether the formulation contains peptides.
2. Brand names containing the word "peptide" do NOT make the product a peptide drug. "Peptide 1.5", "Peptamen", "Kate Farms Peptide" are all nutritional formulas — answer False.
3. Nutritional formulas and dietary supplements containing hydrolyzed proteins or peptide-based formulations are NOT peptide drugs. These are food/nutrition products where proteins are broken down into peptides for easier absorption.
4. If the product is described as a "nutritional formula", "tube feeding", "enteral nutrition", "dietary supplement", "medical food", or "nutritional shake" → False, regardless of whether "peptide" appears in the name.

EVIDENCE SOURCES: Look for peptide confirmation in these databases (provided in the evidence):
- UniProt / EBI Proteins: protein entries with amino acid sequences
- DRAMP / DBAASP: antimicrobial peptide database entries with activity data
- ChEMBL: bioactivity data, molecule type, HELM sequences
- RCSB PDB: 3D structure data confirming peptide nature
- PubMed/PMC: published literature describing the intervention

A confirmed entry in UniProt, DBAASP, DRAMP, ChEMBL (as peptide type), or PDB is strong evidence for True. Absence from these databases does NOT mean False — use other evidence.

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

        # Cross-check against known drug lists as a safety net
        drug_lookup = self._lookup_known_drug(evidence_text)
        if drug_lookup is not None and drug_lookup != value:
            logger.info(
                f"  peptide: known drug lookup override '{value}' → '{drug_lookup}' for {nct_id}"
            )
            value = drug_lookup
            reasoning = f"[Known drug lookup override] {reasoning}"

        quality = sum(c.quality_score for c in cited_sources[:10]) / max(len(cited_sources[:10]), 1)

        return FieldAnnotation(
            field_name=self.field_name,
            value=value,
            confidence=quality,
            reasoning=reasoning,
            evidence=cited_sources[:10],
            model_name=primary_model,
        )

    def _lookup_known_drug(self, evidence_text: str) -> Optional[str]:
        """Check if any known peptide or non-peptide drug names appear.

        Returns "True" if a known peptide drug is found, "False" if a known
        non-peptide is found. Returns None if no match (defer to LLM).
        Non-peptide check takes priority to prevent over-identification.
        """
        lower = evidence_text.lower()

        # Check non-peptide drugs first (higher priority to prevent over-ID)
        for drug in sorted(KNOWN_NON_PEPTIDE_DRUGS, key=len, reverse=True):
            if drug in lower:
                # Make sure it's the PRIMARY intervention, not just mentioned
                # Simple heuristic: check if it appears in the first 500 chars
                # (which contains the trial title and primary intervention)
                if drug in lower[:500]:
                    return "False"

        # Check known peptide drugs
        for drug in sorted(KNOWN_PEPTIDE_DRUGS, key=len, reverse=True):
            if drug in lower:
                return "True"

        return None

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
