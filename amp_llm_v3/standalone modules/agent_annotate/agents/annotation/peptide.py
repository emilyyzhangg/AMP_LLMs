"""
Peptide Annotation Agent (v11).

Determines whether the intervention is a peptide (True/False).

v11 changes (from 400-trial concordance — peptide at 65% vs 83% human baseline):
  - Added _KNOWN_PEPTIDE_DRUGS for deterministic True bypass
  - Field-specific snippet length override (250→400 chars on Mac Mini)
  - Root cause: 130 True→False EDAM corrections + 8B model defaulting to False
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
PASS1_SYSTEM = """DEFINITION: A peptide therapeutic is a molecule consisting of 2-100 amino acid residues that serves as the ACTIVE therapeutic drug in the clinical trial. The peptide must be the primary pharmacological agent — not a carrier, adjuvant, nutritional component, or targeting vector.

INCLUDES as peptide (True):
- Antimicrobial peptides: colistin, daptomycin, nisin, polymyxin B, LL-37, defensins
- Hormone analogues: semaglutide (GLP-1), octreotide (somatostatin), leuprolide (GnRH)
- Cyclic peptides: vancomycin (glycopeptide), gramicidin, bacitracin
- Peptide vaccines where the peptide IS the active immunogen (e.g., StreptInCor)
- Neuropeptides used as drugs: aviptadil (VIP), substance P antagonists
- Insulin and insulin analogues (51 amino acids, single-chain polypeptide)

EXCLUDES as peptide (False):
- Monoclonal antibodies (>100 amino acids, distinct drug class): pembrolizumab, trastuzumab
- Small molecule drugs: amoxicillin, metformin, ciprofloxacin
- Nutritional formulas containing hydrolyzed proteins: "Peptide 1.5", Peptamen, Kate Farms
- Heat shock protein-peptide complexes: HSPPC-96/Oncophage (the HSP is the drug, not the peptide)
- Exosome/dexosome vehicles loaded with peptides (the vehicle is the drug)
- Gene therapies, cell therapies, medical devices
- Whole proteins >100 amino acids (e.g., interferons, erythropoietin) unless specifically described as peptide fragments

You are a biochemistry fact-extraction specialist. Your job is to extract ONLY factual information about whether ANY intervention in this trial is a peptide. Do NOT make a determination — just extract facts.

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

DEFINITION: A peptide therapeutic is a molecule consisting of 2-100 amino acid residues that serves as the ACTIVE therapeutic drug in the clinical trial. The peptide must be the primary pharmacological agent — not a carrier, adjuvant, nutritional component, or targeting vector.

INCLUDES as peptide (True):
- Antimicrobial peptides: colistin, daptomycin, nisin, polymyxin B, LL-37, defensins
- Hormone analogues: semaglutide (GLP-1), octreotide (somatostatin), leuprolide (GnRH)
- Cyclic peptides: vancomycin (glycopeptide), gramicidin, bacitracin
- Peptide vaccines where the peptide IS the active immunogen (e.g., StreptInCor)
- Neuropeptides used as drugs: aviptadil (VIP), substance P antagonists
- Insulin and insulin analogues (51 amino acids, single-chain polypeptide)

EXCLUDES as peptide (False):
- Monoclonal antibodies (>100 amino acids, distinct drug class): pembrolizumab, trastuzumab
- Small molecule drugs: amoxicillin, metformin, ciprofloxacin
- Nutritional formulas containing hydrolyzed proteins: "Peptide 1.5", Peptamen, Kate Farms
- Heat shock protein-peptide complexes: HSPPC-96/Oncophage (the HSP is the drug, not the peptide)
- Exosome/dexosome vehicles loaded with peptides (the vehicle is the drug)
- Gene therapies, cell therapies, medical devices
- Whole proteins >100 amino acids (e.g., interferons, erythropoietin) unless specifically described as peptide fragments

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
- MULTI-DRUG TRIALS: If the PRIMARY study drug is a peptide → True. If a peptide is co-administered
  as background therapy but the primary experimental drug is non-peptide → evaluate the primary drug.
  You MUST evaluate ALL interventions listed in the extracted facts, not just the first one.
  Example: a trial testing "decitabine (small molecule) + NY-ESO-1 peptide vaccine" → True
  because the peptide vaccine is among the interventions.
- Heat shock protein-peptide complexes (HSPPC-96, Oncophage): the peptide is antigenic cargo, not the active mechanism → False
- Autologous dexosomes/exosomes loaded with peptides: the vehicle is the drug, not the peptide cargo → False

Format your response EXACTLY as:
Peptide: [True or False]
Reasoning: [Walk through Steps 1 → 2 → 3 using the extracted facts]"""


# --------------------------------------------------------------------------- #
#  Known non-peptide drugs (v9)
# --------------------------------------------------------------------------- #

_KNOWN_NON_PEPTIDE_DRUGS = {
    "hsppc-96", "oncophage", "vitespen", "hsppc", "heat shock protein peptide complex",
    "dexosome", "exosome", "autologous dexosome",
    "amdoxovir", "tenofovir", "emtricitabine", "lamivudine", "zidovudine",
    "abacavir", "stavudine", "didanosine", "entecavir", "sofosbuvir",
    "pembrolizumab", "nivolumab", "atezolizumab", "durvalumab",
    "ipilimumab", "trastuzumab", "bevacizumab", "rituximab",
    "adalimumab", "infliximab", "cetuximab",
    "gsk3732394",
    "peptide 1.5", "peptamen", "kate farms peptide", "vital peptide",
    "kate farm peptide", "nutri peptide",
    "hydrolyzed whey", "hydrolyzed protein", "hydrolysed whey",
}

# --------------------------------------------------------------------------- #
#  Known peptide drugs — deterministic True bypass (v11)
# --------------------------------------------------------------------------- #
# These are unambiguously peptide therapeutics. Catches false negatives
# from the LLM which was under-calling True (65% vs 83% human baseline).
_KNOWN_PEPTIDE_DRUGS = {
    # GLP-1 / metabolic peptides
    "semaglutide", "liraglutide", "exenatide", "dulaglutide", "tirzepatide",
    "apraglutide", "teduglutide", "glepaglutide",
    # Insulin analogues (51 AA, single-chain polypeptide)
    "insulin", "insulin glargine", "insulin lispro", "insulin aspart",
    "insulin detemir", "insulin degludec",
    # GnRH analogues
    "leuprolide", "leuprorelin", "goserelin", "triptorelin", "buserelin",
    "nafarelin", "degarelix", "cetrorelix", "ganirelix",
    # Somatostatin analogues
    "octreotide", "lanreotide", "pasireotide", "vapreotide",
    # Antimicrobial peptides
    "colistin", "colistimethate", "polymyxin b", "polymyxin e",
    "daptomycin", "nisin", "gramicidin", "tyrothricin", "bacitracin",
    "vancomycin", "teicoplanin", "telavancin", "dalbavancin", "oritavancin",
    "ramoplanin", "surotomycin", "friulimicin",
    "pexiganan", "omiganan", "iseganan",
    # Neuropeptides / vasopeptides
    "aviptadil", "calcitonin", "teriparatide", "abaloparatide",
    "oxytocin", "vasopressin", "desmopressin", "terlipressin", "carbetocin",
    "vosoritide",
    # Host defense peptides
    "ll-37", "ll37", "cathelicidin", "thymosin alpha-1", "thymalfasin",
    # Peptide vaccines (peptide IS the active immunogen)
    "streptincor",
    # HIV peptides (still peptides even though not AMPs)
    "enfuvirtide", "t-20", "fuzeon", "peptide t", "dapta",
    # Other peptide therapeutics
    "melittin", "magainin", "cecropin", "lactoferricin",
    "bivalirudin", "ziconotide", "eptifibatide", "icatibant",
    "nesiritide", "pramlintide", "romiplostim",
}


def _check_known_peptide(research_results: list) -> FieldAnnotation | None:
    """v11: Check if the intervention is a known peptide drug → True deterministically."""
    intervention_names: list[str] = []
    for result in research_results:
        if result.error or result.agent_name != "clinical_protocol":
            continue
        if not result.raw_data:
            continue
        proto = result.raw_data.get("protocol_section", result.raw_data.get("protocolSection", {}))
        arms_mod = proto.get("armsInterventionsModule", {})
        for interv in arms_mod.get("interventions", []):
            name = interv.get("name", "")
            if name:
                intervention_names.append(name.lower().strip())
    for name in intervention_names:
        for pep_drug in _KNOWN_PEPTIDE_DRUGS:
            if pep_drug in name or name in pep_drug:
                logger.info(f"  peptide: deterministic → True (known peptide: '{name}' matched '{pep_drug}')")
                return FieldAnnotation(
                    field_name="peptide", value="True", confidence=0.95,
                    reasoning=f"[Deterministic v11] Known peptide drug: '{name}' matched '{pep_drug}'",
                    evidence=[], model_name="deterministic", skip_verification=True,
                )
    return None


def _check_known_non_peptide(research_results: list) -> FieldAnnotation | None:
    """Check if the intervention is a known non-peptide drug."""
    intervention_names: list[str] = []
    for result in research_results:
        if result.error or result.agent_name != "clinical_protocol":
            continue
        if not result.raw_data:
            continue
        proto = result.raw_data.get("protocol_section", result.raw_data.get("protocolSection", {}))
        arms_mod = proto.get("armsInterventionsModule", {})
        for interv in arms_mod.get("interventions", []):
            name = interv.get("name", "")
            if name:
                intervention_names.append(name.lower().strip())
    for name in intervention_names:
        for non_pep in _KNOWN_NON_PEPTIDE_DRUGS:
            if non_pep in name or name in non_pep:
                logger.info(f"  peptide: deterministic → False (known non-peptide: '{name}' matched '{non_pep}')")
                return FieldAnnotation(
                    field_name="peptide", value="False", confidence=0.95,
                    reasoning=f"[Deterministic v9] Known non-peptide drug: '{name}' matched '{non_pep}'",
                    evidence=[], model_name="deterministic", skip_verification=True,
                )
    return None


class PeptideAgent(BaseAnnotationAgent):
    """Determines if the intervention is a peptide using two-pass investigation."""

    field_name = "peptide"

    async def annotate(
        self,
        nct_id: str,
        research_results: list[ResearchResult],
        metadata: Optional[dict] = None,
    ) -> FieldAnnotation:
        # v11: Check known peptide drugs first (deterministic True)
        det_true = _check_known_peptide(research_results)
        if det_true is not None:
            return det_true

        # v9: Check known non-peptide drugs
        det_result = _check_known_non_peptide(research_results)
        if det_result is not None:
            return det_result

        from app.services.config_service import config_service
        from app.services.memory.edam_config import FIELD_SNIPPET_OVERRIDES

        config = config_service.get()
        profile = config.orchestrator.hardware_profile
        is_server = profile == "server"
        max_cites = 35 if is_server else 20
        # v11: Use field-specific snippet override if available
        default_snippet = 500 if is_server else 250
        max_snippet = FIELD_SNIPPET_OVERRIDES.get(profile, {}).get("peptide", default_snippet)

        # Build structured evidence — drug/peptide data and structural
        # sections are most important for peptide determination
        evidence_text, cited_sources = self.build_structured_evidence(
            nct_id, research_results,
            max_citations=max_cites,
            max_snippet_chars=max_snippet,
        )

        # --- EDAM guidance injection ---
        edam_guidance = await self.get_edam_guidance(nct_id, evidence_text)
        if edam_guidance:
            evidence_text = edam_guidance + "\n\n" + evidence_text

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

        # v9.1: Server profile uses larger model for better accuracy
        if config.orchestrator.hardware_profile == "server":
            primary_model = "qwen2.5:14b"

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
