"""
Peptide Annotation Agent.

Determines whether the intervention is a peptide (True/False).

v2 changes (from 70-trial concordance analysis):
  - Enhanced prompt with additional disambiguation rules for edge cases
    observed in concordance disagreements (nutritional products, large
    biologics, multi-drug trials).
  - Added two-pass design: Pass 1 extracts molecular facts, Pass 2 applies
    decision tree. This mirrors the classification agent's approach and
    reduces the 8B model's tendency to shortcut on surface-level keywords.
"""

import re
import logging
from typing import Optional

from agents.base import BaseAnnotationAgent
from app.models.research import ResearchResult, SourceCitation
from app.models.annotation import FieldAnnotation

logger = logging.getLogger("agent_annotate.annotation.peptide")

VALID_VALUES = ["True", "False"]

# Pass 1: Extract molecular facts about the intervention
PASS1_SYSTEM = """You are a biochemistry fact-extraction specialist. Your job is to extract ONLY factual information about whether ANY intervention in this trial is a peptide. Do NOT make a determination — just extract facts.

IMPORTANT: If this trial has MULTIPLE interventions (e.g., a peptide vaccine + a chemotherapy drug + an adjuvant), you MUST extract facts for EACH intervention separately. Do NOT focus on just one.

For the clinical trial intervention(s) below, answer these questions using ONLY the provided evidence. If the evidence does not answer a question, write "No evidence found."

1. INTERVENTION NAME: List ALL drugs/interventions being tested (not just the first one).

2. MOLECULAR CLASS: For EACH intervention, what type of molecule is it? Options:
   - Short peptide chain (2-50 amino acids)
   - Longer polypeptide (50-100+ amino acids, but single chain)
   - Monoclonal antibody or antibody fragment (~150 kDa, multi-chain)
   - Small molecule (non-peptide chemical compound, typically <900 Da)
   - Nutritional product/dietary supplement (food, formula, hydrolyzed protein)
   - Large multi-subunit protein (engineered scaffold, fusion protein)
   - Unknown

3. DATABASE CONFIRMATION: For EACH intervention, was it found in any peptide/protein databases?
   - UniProt: entry found? Amino acid length?
   - DRAMP/DBAASP: antimicrobial peptide database entry?
   - ChEMBL: molecule type? (peptide, small molecule, protein, antibody)
   - PDB: structural data available?
   - List specific hits or "not found in [database]"

4. PRODUCT DESCRIPTION: How is this product described in the trial or literature?
   - Is it described as a "drug", "therapeutic", "vaccine", "antibiotic"?
   - OR is it described as a "nutritional formula", "dietary supplement", "tube feeding",
     "enteral nutrition", "medical food", "protein supplement"?

5. ACTIVE INGREDIENT: Is the peptide the ACTIVE therapeutic agent, or is it:
   - A food ingredient (hydrolyzed protein for easier digestion)?
   - A targeting vector (carries another drug to a target)?
   - Part of a brand name but not the actual drug mechanism?

Format your response EXACTLY as:
Intervention: [name]
Molecular Class: [class from list above]
Database Confirmation: [hits or none]
Product Description: [how described]
Active Ingredient Role: [active drug / food ingredient / targeting vector / brand name only]"""

# Pass 2: Apply decision tree to extracted facts
PASS2_SYSTEM = """You are a peptide identification specialist. You have been given EXTRACTED FACTS about a clinical trial intervention. Use ONLY these facts to determine if the intervention is a peptide therapeutic.

DECISION TREE:

STEP 1 — Is the Molecular Class a peptide?
  - "Short peptide chain" or "Longer polypeptide" → proceed to Step 2
  - "Monoclonal antibody" → False (antibodies are a separate drug class)
  - "Small molecule" → False
  - "Nutritional product/dietary supplement" → False
  - "Large multi-subunit protein" → False (unless single-chain <100kDa)
  - "Unknown" → check database confirmation in Step 2

STEP 2 — Is the peptide the ACTIVE DRUG?
  - Active Ingredient Role = "active drug" → proceed to Step 3
  - Active Ingredient Role = "food ingredient" → False (nutritional product)
  - Active Ingredient Role = "targeting vector" → False (peptide is delivery mechanism, not the drug)
  - Active Ingredient Role = "brand name only" → False (word "peptide" in name ≠ peptide drug)

STEP 3 — Final confirmation
  - Database confirmation shows UniProt/DRAMP/DBAASP/ChEMBL peptide entry → True
  - Literature describes it as a peptide therapeutic → True
  - No database hits but molecular class is clearly peptide → True
  - Conflicting evidence → weigh database entries > literature descriptions > product names

CRITICAL RULES:
- The question is whether ANY active drug is a peptide, not whether the formulation contains peptides
- Brand names containing "peptide" do NOT make the product a peptide drug
- Nutritional formulas with hydrolyzed proteins are NOT peptide drugs
- Monoclonal antibodies are NOT peptides (different drug class)
- MULTI-DRUG TRIALS: If a trial tests MULTIPLE drugs and ANY ONE of them is a peptide, answer True.
  You MUST evaluate ALL interventions listed in the extracted facts, not just the first one.
  Example: a trial testing "decitabine (small molecule) + NY-ESO-1 peptide vaccine" → True
  because the peptide vaccine is among the interventions.

Format your response EXACTLY as:
Peptide: [True or False]
Reasoning: [Walk through Steps 1 → 2 → 3 using the extracted facts]"""


class PeptideAgent(BaseAnnotationAgent):
    """Determines if the intervention is a peptide using two-pass investigation."""

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

        # --- Pass 1: Extract molecular facts ---
        try:
            logger.info(f"  peptide: Pass 1 — extracting molecular facts for {nct_id}")
            pass1_response = await ollama_client.generate(
                model=primary_model,
                prompt=evidence_text,
                system=PASS1_SYSTEM,
                temperature=config.ollama.temperature,
            )
            pass1_text = pass1_response.get("response", "")
        except Exception as e:
            logger.error(f"  peptide: Pass 1 failed: {e}")
            return FieldAnnotation(
                field_name=self.field_name,
                value="False",
                confidence=0.0,
                reasoning=f"Pass 1 LLM call failed: {e}",
                evidence=[],
                model_name=primary_model,
            )

        # --- Pass 2: Apply decision tree ---
        try:
            logger.info(f"  peptide: Pass 2 — applying decision tree for {nct_id}")
            pass2_prompt = f"Trial: {nct_id}\n\nEXTRACTED FACTS:\n{pass1_text}\n"
            pass2_response = await ollama_client.generate(
                model=primary_model,
                prompt=pass2_prompt,
                system=PASS2_SYSTEM,
                temperature=config.ollama.temperature,
            )
            pass2_text = pass2_response.get("response", "")
        except Exception as e:
            # Fallback: infer from Pass 1 facts
            value = self._infer_from_pass1(pass1_text)
            return FieldAnnotation(
                field_name=self.field_name,
                value=value,
                confidence=0.3,
                reasoning=f"Pass 2 failed ({e}), inferred from pass 1: {pass1_text[:300]}",
                evidence=cited_sources[:10],
                model_name=primary_model,
            )

        value = self._parse_value(pass2_text)
        reasoning = f"[Pass 1 extraction] {pass1_text[:400]}\n[Pass 2 decision] {pass2_text[:400]}"
        quality = sum(c.quality_score for c in cited_sources[:10]) / max(len(cited_sources[:10]), 1)

        return FieldAnnotation(
            field_name=self.field_name,
            value=value,
            confidence=quality,
            reasoning=reasoning,
            evidence=cited_sources[:10],
            model_name=primary_model,
        )

    def _infer_from_pass1(self, pass1_text: str) -> str:
        """Fallback: infer peptide status from Pass 1 facts if Pass 2 fails."""
        lower = pass1_text.lower()

        # Check molecular class
        class_match = re.search(r"molecular class:\s*(.+?)(?:\n|$)", lower)
        if class_match:
            mol_class = class_match.group(1).strip()
            if "small molecule" in mol_class:
                return "False"
            if "antibody" in mol_class:
                return "False"
            if "nutritional" in mol_class or "dietary" in mol_class:
                return "False"
            if "multi-subunit" in mol_class:
                return "False"

        # Check active ingredient role
        role_match = re.search(r"active ingredient role:\s*(.+?)(?:\n|$)", lower)
        if role_match:
            role = role_match.group(1).strip()
            if "food" in role or "brand name" in role or "targeting" in role:
                return "False"

        # Check product description for nutritional keywords
        if any(kw in lower for kw in ["nutritional formula", "tube feeding",
                                       "enteral nutrition", "dietary supplement"]):
            return "False"

        # Check for database hits suggesting peptide
        if any(kw in lower for kw in ["dramp", "dbaasp", "peptide chain",
                                       "amino acid"]):
            return "True"

        return "False"

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
