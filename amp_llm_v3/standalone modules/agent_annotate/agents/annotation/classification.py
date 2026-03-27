"""
Classification Annotation Agent — Two-Pass Investigative Design.

Determines whether a clinical trial involves an Antimicrobial Peptide (AMP)
and its purpose. Uses a two-pass approach:
  Pass 1: Extract antimicrobial evidence (database hits, mechanism, target)
  Pass 2: Apply the AMP decision tree to extracted facts

Uses a larger model (14B on Mac Mini, 70B+ on server) because the 8B model
has demonstrated inability to follow the multi-step decision tree reliably.
"""

import logging
import re
from typing import Optional

from agents.base import BaseAnnotationAgent, FIELD_RELEVANCE
from app.models.research import ResearchResult, SourceCitation
from app.models.annotation import FieldAnnotation

logger = logging.getLogger("agent_annotate.annotation.classification")

VALID_VALUES = ["AMP(infection)", "AMP(other)", "Other"]

# --------------------------------------------------------------------------- #
#  Known AMP drugs — deterministic classification bypass (v9)
# --------------------------------------------------------------------------- #

_KNOWN_AMP_DRUGS = {
    "colistin", "colistimethate", "polymyxin b", "polymyxin e",
    "daptomycin", "nisin", "gramicidin", "tyrothricin", "bacitracin",
    "vancomycin", "teicoplanin", "telavancin", "dalbavancin", "oritavancin",
    "ramoplanin", "surotomycin", "friulimicin",
    "ll-37", "ll37", "cathelicidin", "defensin", "hbd-1", "hbd-2", "hbd-3",
    "hnp-1", "hnp-2", "hnp-3", "hd-5", "hd-6",
    "thymosin alpha-1", "thymosin alpha 1", "thymalfasin", "zadaxin",
    "melittin", "magainin", "cecropin", "lactoferricin", "lactoferrin",
    "pexiganan", "msrdn-1", "omiganan", "iseganan",
    "djk-5", "idr-1018",
}

_INFECTION_KEYWORDS = {
    "infection", "infectious", "bacterial", "viral", "fungal", "sepsis",
    "septic", "pneumonia", "meningitis", "endocarditis", "bacteremia",
    "urinary tract", "uti", "skin and soft tissue", "sssi", "absssi",
    "peritonitis", "osteomyelitis", "wound infection", "surgical site",
    "cystic fibrosis", "ventilator-associated", "hospital-acquired",
    "nosocomial", "multidrug-resistant", "mdr", "xdr", "drug-resistant",
    "mrsa", "vre", "esbl", "carbapenem-resistant", "clostridium difficile",
    "c. difficile", "clostridioides", "pseudomonas", "acinetobacter",
    "klebsiella", "tuberculosis", "tb", "malaria", "hiv", "hepatitis",
    "herpes", "influenza", "covid", "sars-cov", "anthrax", "plague",
    "cholera", "typhoid", "gonorrhea", "chlamydia", "mastitis",
}

_KNOWN_NON_AMP_DRUGS = {
    "enfuvirtide", "t-20", "fuzeon", "ibalizumab", "maraviroc",
    "semaglutide", "liraglutide", "exenatide", "dulaglutide", "tirzepatide",
    "apraglutide", "teduglutide", "glepaglutide",
    "insulin", "insulin glargine", "insulin lispro", "insulin aspart",
    "insulin detemir", "insulin degludec",
    "leuprolide", "leuprorelin", "goserelin", "triptorelin", "buserelin",
    "nafarelin", "degarelix", "cetrorelix", "ganirelix",
    "octreotide", "lanreotide", "pasireotide", "vapreotide",
    "aviptadil", "vip", "vasoactive intestinal peptide",
    "vosoritide", "cnp",
    "calcitonin", "teriparatide", "abaloparatide",
    "oxytocin", "vasopressin", "desmopressin", "terlipressin", "carbetocin",
    "peptide t", "dapta",
    "rada16", "p11-4", "curodont",
    "lutetium lu 177 dotatate", "lutathera", "177lu-dotatate",
    "gallium ga 68 dotatate", "68ga-dotatate",
    "neoantigen", "personalized neoantigen",
    "peptide 1.5", "peptamen", "kate farms peptide",
    "vital peptide", "nutri peptide",
}


def _deterministic_classify(
    nct_id: str,
    research_results: list,
    metadata: dict | None,
) -> FieldAnnotation | None:
    """Attempt deterministic classification before LLM passes.
    Returns a FieldAnnotation with skip_verification=True if matched, or None."""
    intervention_names: list[str] = []
    conditions: list[str] = []
    has_dramp = False
    has_dbaasp = False
    has_apd = False

    for result in research_results:
        if result.error:
            continue
        if result.agent_name == "clinical_protocol" and result.raw_data:
            proto = result.raw_data.get(
                "protocol_section",
                result.raw_data.get("protocolSection", {}),
            )
            arms_mod = proto.get("armsInterventionsModule", {})
            for interv in arms_mod.get("interventions", []):
                name = interv.get("name", "")
                if name:
                    intervention_names.append(name.lower().strip())
            cond_mod = proto.get("conditionsModule", {})
            for cond in cond_mod.get("conditions", []):
                conditions.append(cond.lower().strip())
        if result.agent_name in ("peptide_identity", "dbaasp", "apd", "dbamp"):
            for citation in result.citations:
                src = citation.source_name.lower()
                if "dramp" in src:
                    has_dramp = True
                if "dbaasp" in src:
                    has_dbaasp = True
                if "apd" in src:
                    has_apd = True

    if not intervention_names:
        return None

    for name in intervention_names:
        for non_amp in _KNOWN_NON_AMP_DRUGS:
            if non_amp in name or name in non_amp:
                logger.info(f"  classification: deterministic → Other (known non-AMP: '{name}' matched '{non_amp}')")
                return FieldAnnotation(
                    field_name="classification", value="Other", confidence=0.95,
                    reasoning=f"[Deterministic v9] Known non-AMP drug: '{name}' matched '{non_amp}'",
                    evidence=[], model_name="deterministic", skip_verification=True,
                )

    for name in intervention_names:
        for amp_drug in _KNOWN_AMP_DRUGS:
            if amp_drug in name or name in amp_drug:
                all_text = " ".join(conditions + intervention_names)
                is_infection = any(kw in all_text for kw in _INFECTION_KEYWORDS)
                value = "AMP(infection)" if is_infection else "AMP(other)"
                logger.info(f"  classification: deterministic → {value} (known AMP: '{name}' matched '{amp_drug}')")
                return FieldAnnotation(
                    field_name="classification", value=value, confidence=0.95,
                    reasoning=f"[Deterministic v9] Known AMP drug: '{name}' matched '{amp_drug}'. Infection context: {is_infection}",
                    evidence=[], model_name="deterministic", skip_verification=True,
                )

    if has_dramp or has_dbaasp or has_apd:
        all_text = " ".join(conditions + intervention_names)
        is_infection = any(kw in all_text for kw in _INFECTION_KEYWORDS)
        value = "AMP(infection)" if is_infection else "AMP(other)"
        db_names = []
        if has_dramp: db_names.append("DRAMP")
        if has_dbaasp: db_names.append("DBAASP")
        if has_apd: db_names.append("APD")
        logger.info(f"  classification: deterministic → {value} (database hits: {', '.join(db_names)})")
        return FieldAnnotation(
            field_name="classification", value=value, confidence=0.95,
            reasoning=f"[Deterministic v9] AMP database hits: {', '.join(db_names)}. Infection context: {is_infection}",
            evidence=[], model_name="deterministic", skip_verification=True,
        )

    return None

# Hardware profile → model selection for classification
# Classification uses a larger model because 8B ignores worked examples
# On server, uses the configurable server_premium_model (kimi-k2 or minimax-m2.7)
MODEL_OVERRIDES = {
    "mac_mini": "qwen2.5:14b",
    "server_fallback": "qwen2.5:72b",
}

# --------------------------------------------------------------------------- #
#  Pass 1: Extract antimicrobial evidence from research data
# --------------------------------------------------------------------------- #

PASS1_SYSTEM = """You are a biochemistry fact-extraction specialist. Your job is to extract ONLY factual evidence about whether a peptide has antimicrobial or host defense properties. Do NOT classify — just extract facts.

For the clinical trial intervention below, answer these 5 questions using ONLY the provided evidence. If the evidence does not answer a question, write "No evidence found."

1. PEPTIDE IDENTITY: What is the intervention? Is it confirmed as a peptide? What is its amino acid length or molecular class?

2. DATABASE MATCHES: Was this peptide found in any antimicrobial peptide databases (DRAMP, DBAASP, APD3, UniProt with "antimicrobial" annotation)? Also check ChEMBL for bioactivity data and mechanism of action, RCSB PDB for structural data, and EBI Proteins for domain annotations. List specific database hits.

3. MECHANISM OF ACTION: What is the peptide's known or proposed mechanism? Specifically:
   - Does it directly kill or inhibit microorganisms (bacteria, viruses, fungi)?
   - Does it stimulate INNATE immune defense (recruit immune cells, enhance phagocytosis, activate dendritic cells)?
   - Does it disrupt biofilms?
   - Does it work via a non-antimicrobial mechanism (metabolic hormone, bone growth, vasodilation, immunosuppression, vaccine/antibody induction, physical/chemical)?

4. THERAPEUTIC TARGET: What disease or condition is the trial treating? Is it an infection, infectious disease, or pathogen-specific condition? Or is it cancer, autoimmune, metabolic, structural, or other?

5. IMMUNE DIRECTION: Does this peptide PROMOTE immune defense (stimulate, recruit, activate) or SUPPRESS immune responses (tolerize, inhibit, dampen)? Or is it immune-neutral (metabolic/structural)?

Format your response EXACTLY as:
Peptide Identity: [answer]
Database Matches: [answer]
Mechanism: [answer]
Therapeutic Target: [answer]
Immune Direction: [answer]"""

# --------------------------------------------------------------------------- #
#  Pass 2: Apply AMP decision tree to extracted facts
# --------------------------------------------------------------------------- #

PASS2_SYSTEM = """You are a clinical trial classification specialist. AMP stands for Antimicrobial Peptide.

You have been given EXTRACTED FACTS about a peptide intervention. Use ONLY these facts to classify the trial. Do NOT add information not present in the facts.

THREE-STEP DECISION TREE:

STEP 1 — Is the intervention a peptide?
  Check the Peptide determination. If Peptide = False → STOP → answer "Other".

STEP 2 — Is this peptide an AMP (Antimicrobial Peptide / Host Defense Peptide)?

  THE CORE TEST: Does this peptide contribute to pathogen defense — by directly
  killing, inhibiting the growth of, or disrupting bacteria, fungi, viruses, or
  other pathogens (or activating INNATE immune cells to do so)?

  An AMP must contribute to pathogen defense through ONE of these modes:
  A) Direct antimicrobial: kills, inhibits growth of, or disrupts microorganisms — includes both bactericidal (killing) AND bacteriostatic (growth inhibition) mechanisms. Examples: colistin (membrane disruption), nisin (pore formation), daptomycin (membrane depolarization), gramicidin (ion channel disruption).
  B) Immunostimulatory HOST DEFENSE peptide: recruits or activates INNATE immune cells to kill pathogens at infection sites — cathelicidins (LL-37), defensins. This is INNATE immunity (direct cellular killing), NOT adaptive immunity (antibody/T-cell induction).
  C) Anti-biofilm: disrupts microbial biofilms through biochemical interaction

  CHECK THE EXTRACTED FACTS:
  - Database Matches: DRAMP or APD3 hit → evidence FOR AMP, but not sufficient alone. The peptide
    MUST also have a direct antimicrobial mechanism confirmed in the facts.
  - Mechanism: "kills/inhibits growth of/disrupts microorganisms" or "recruits INNATE immune
    cells to fight pathogens directly" qualifies. Vaccine/antibody induction does NOT qualify.
    General "immunomodulation" does NOT qualify.
  - Immune Direction: "PROMOTE" alone is NOT enough. Many peptides promote immune responses but
    are NOT antimicrobial (e.g., vaccines, adjuvants). The immune promotion must be
    SPECIFICALLY through INNATE defense mechanisms, not adaptive immunity.

  CRITICAL — NOT AMPs. The following are NEVER AMPs regardless of context:

  ANTIRETROVIRAL DRUGS (NOT AMPs — viral entry inhibitors, not antimicrobial):
  - Enfuvirtide (T-20/Fuzeon): blocks HIV viral FUSION with host cells. This is a VIRAL ENTRY
    INHIBITOR, not an antimicrobial peptide. It does NOT kill HIV — it prevents cell entry.
    Classification: Other.
  - Peptide T (DAPTA): binds CCR5 chemokine receptor, blocks HIV entry. It does NOT kill HIV
    or any pathogen. Classification: Other.

  ALL VACCINES ARE NOT AMPs:
  Vaccines work through ADAPTIVE immunity (antibody/T-cell induction). AMPs work through DIRECT
  antimicrobial action or INNATE immune defense. These are fundamentally different mechanisms.
  - HIV peptide vaccines (gp120, gp41): induce antibodies against HIV but do NOT directly kill/disrupt the virus. Classification: Other.
  - Malaria, hepatitis, influenza, bacterial peptide vaccines: induce adaptive immune responses, NOT direct antimicrobial action. Classification: Other.
  - Cancer neoantigen vaccines: target tumor cells, not pathogens. Classification: Other.
  - Autoimmune peptide vaccines: suppress immune responses. Classification: Other.

  OTHER NON-AMP PEPTIDES:
  - Neuropeptides and vasodilators: VIP/Aviptadil, substance P, CGRP
  - Metabolic hormones: GLP-1, GLP-2, GnRH, somatostatin, GIP, insulin, oxytocin
  - Bone growth regulators: vosoritide/CNP
  - Immunosuppressive peptides: suppress T-cells for autoimmune disease
  - Self-assembling/structural peptides: physical mechanism, not biological
  - Radiolabeled peptide conjugates: peptide is targeting vector, not the drug
  - Collagen/nutritional peptides: structural/metabolic

  DECISIVE RULE: If the peptide's mechanism is ANY of the following, it is "Other":
  - Viral entry inhibition (blocks receptor binding, fusion inhibition)
  - Vasodilation, immunosuppression, tolerance induction
  - Metabolic regulation, hormone signaling
  - Receptor blocking/agonism (unless the receptor is on a pathogen)
  - Vaccine/antibody induction (adaptive immune response, NOT direct antimicrobial action)
  - General immunomodulation without direct killing/disruption of pathogens

  BUT these ARE AMPs:
  - Any peptide that directly kills, inhibits growth of, or disrupts bacteria/fungi/viruses
  - Peptides that recruit or activate INNATE immune cells to fight pathogens at the site of infection (cathelicidins, defensins)

  If NOT an AMP → STOP → answer "Other".

STEP 3 — Does this AMP target infection?
  AMP(infection): Trial treats active infection, infectious disease, AMR, sepsis, or pathogen-specific conditions.
  AMP(other): AMP used for wound healing, cancer immunotherapy, anti-inflammatory, or non-infectious biofilm.

WORKED EXAMPLES — study these before answering:

Example A: Colistin for drug-resistant bacterial infection
→ AMP(infection). Direct antimicrobial peptide that disrupts bacterial membranes, treating infection.

Example B: LL-37 for diabetic wound healing
→ AMP(other). LL-37 is a confirmed AMP (in DRAMP, directly kills bacteria) but the trial targets wound healing, not infection.

Example C: Aviptadil (VIP) for COVID-19 ARDS
→ Other. VIP/Aviptadil is a neuropeptide vasodilator. It does NOT kill pathogens. Testing in COVID patients does NOT make it an AMP.

Example D: Enfuvirtide (T-20) for HIV
→ Other. Enfuvirtide blocks HIV fusion with host cells — it is a VIRAL ENTRY INHIBITOR. It does NOT directly kill or lyse HIV. It is NOT an AMP.

Example E: HIV gp120 peptide vaccine
→ Other. Induces adaptive immune responses (antibodies) against HIV, but does NOT directly kill or disrupt the virus. Vaccine peptides work through adaptive immunity — not direct antimicrobial action. Classification: Other.

Example F: Semaglutide for diabetes
→ Other. GLP-1 analogue — metabolic hormone, not antimicrobial.

Example G: Cancer neoantigen peptide vaccine
→ Other. Targets tumor cells, NOT pathogens. Cancer vaccines are not AMPs.

Example G: Nisin for bacterial mastitis
→ AMP(infection). Nisin directly kills bacteria through membrane pore formation.

Example H: Peptide T (DAPTA) for HIV-associated cognitive impairment
→ Other. Peptide T blocks CCR5 receptor. It does NOT directly kill HIV or any pathogen. It is NOT an AMP.

Example I: Daptomycin for MRSA bacteremia
→ AMP(infection). Daptomycin is a lipopeptide that directly disrupts bacterial cell membranes.

Example J: Influenza peptide vaccine
→ Other. Induces immune response against influenza. The peptide does NOT directly kill the virus.

CRITICAL RULES:
- If Database Matches says "No evidence found" AND Mechanism shows no direct antimicrobial activity → "Other"
- If Immune Direction says "SUPPRESS" → always "Other"
- If mechanism is viral entry inhibition, receptor blocking, vaccine/antibody induction, or adaptive immunostimulation → "Other"
- A peptide being USED IN an infectious disease trial does NOT make it an AMP
- A peptide being DERIVED FROM a pathogen does NOT make it an AMP
- A peptide that TREATS infection but works by a non-antimicrobial mechanism → "Other"
- VACCINE PEPTIDES ARE NEVER AMPs — regardless of whether they target pathogens, cancer, or anything else
- When in doubt, default to "Other" — false AMP classification is worse than missing a true AMP

Format your response EXACTLY as:
Classification: [AMP(infection), AMP(other), or Other]
Reasoning: [Walk through Step 1 → 2 → 3 using the extracted facts. Explicitly state the mechanism and why it is/isn't direct antimicrobial action.]"""

# --------------------------------------------------------------------------- #
#  Deterministic fallback if Pass 2 fails
# --------------------------------------------------------------------------- #

def _fallback_classify(pass1_text: str, peptide_value: str) -> str:
    """Keyword-based fallback if Pass 2 LLM call fails."""
    if peptide_value == "False":
        return "Other"

    lower = pass1_text.lower()

    # Strong AMP signals from database matches
    has_dramp = "dramp" in lower and "no evidence" not in lower.split("database matches")[1][:100] if "database matches" in lower else False
    has_antimicrobial_mechanism = any(kw in lower for kw in [
        "kills bacteria", "inhibits bacteria", "membrane disruption",
        "pore formation", "bactericidal", "bacteriostatic", "antimicrobial activity"
    ])
    has_immunostim = "promote" in lower and "immune" in lower
    has_suppress = "suppress" in lower and "immune" in lower

    # Immune suppression → always Other
    if has_suppress:
        return "Other"

    # NOT-AMP mechanism signals (from Pass 1 extracted evidence, NOT drug names)
    not_amp_keywords = [
        # Non-antimicrobial mechanisms
        "metabolic hormone", "vasodilat", "neuropeptide",
        "bone growth", "self-assembling", "remineralization",
        "neoantigen", "radiolabeled", "nutritional", "collagen",
        "immune-neutral", "tolerance", "tolerogenic",
        # Mechanism-based exclusions
        "viral entry", "fusion inhibit", "receptor block",
        "receptor agonist", "adaptive immun",
        "induce antibod", "antibody response",
        "immunosuppress", "autoimmune",
    ]
    if any(kw in lower for kw in not_amp_keywords):
        return "Other"

    if has_dramp or has_antimicrobial_mechanism or has_immunostim:
        # Check if infection target
        infection_keywords = ["infection", "bacterial", "viral", "fungal",
                              "sepsis", "antimicrobial resistance", "pathogen"]
        if any(kw in lower for kw in infection_keywords):
            return "AMP(infection)"
        return "AMP(other)"

    return "Other"


class ClassificationAgent(BaseAnnotationAgent):
    """Two-pass AMP classification with hardware-aware model selection."""

    field_name = "classification"

    def _get_model(self, config) -> str:
        """Select model based on hardware profile. Classification uses a
        larger model because 8B models ignore the multi-step decision tree."""
        profile = config.orchestrator.hardware_profile
        if profile == "server":
            # Use the configurable premium model (kimi-k2 or minimax-m2.7)
            return getattr(config.orchestrator, "server_premium_model", "kimi-k2-thinking")
        override = MODEL_OVERRIDES.get(profile)
        if override:
            return override
        # Fallback: use reconciler model (largest available)
        for model_key, model_cfg in config.verification.models.items():
            if model_cfg.role == "reconciler":
                return model_cfg.name
        return "qwen2.5:14b"

    async def annotate(
        self,
        nct_id: str,
        research_results: list[ResearchResult],
        metadata: Optional[dict] = None,
    ) -> FieldAnnotation:
        # v9: Try deterministic classification first
        det_result = _deterministic_classify(nct_id, research_results, metadata)
        if det_result is not None:
            return det_result

        from app.services.ollama_client import ollama_client
        from app.services.config_service import config_service

        config = config_service.get()
        model = self._get_model(config)

        # Server profile with larger models can digest more evidence
        is_server = config.orchestrator.hardware_profile == "server"
        max_cites = 50 if is_server else 30
        max_snippet = 500 if is_server else 250

        # Build structured evidence with section grouping
        structured_text, cited_sources = self.build_structured_evidence(
            nct_id, research_results,
            max_citations=max_cites,
            max_snippet_chars=max_snippet,
        )

        # Prepend peptide determination and key database highlights
        peptide_value = metadata.get("peptide_result", "Unknown") if metadata else "Unknown"
        header = f"Trial: {nct_id}\nPeptide determination: {peptide_value}\n"

        # Highlight DRAMP/UniProt matches above the structured sections
        # so the LLM sees AMP-specific signals first
        dramp_hits = []
        uniprot_hits = []
        for result in research_results:
            if result.agent_name == "peptide_identity" and not result.error:
                for citation in result.citations:
                    if citation.source_name == "dramp":
                        dramp_hits.append(citation)
                    elif citation.source_name == "uniprot":
                        uniprot_hits.append(citation)

        if dramp_hits:
            header += "\nDRAMP (Antimicrobial Peptide Database) MATCHES:\n"
            for c in dramp_hits:
                header += f"  {c.identifier}: {c.snippet}\n"
        if uniprot_hits:
            header += "\nUniProt MATCHES:\n"
            for c in uniprot_hits:
                header += f"  {c.identifier}: {c.snippet}\n"

        evidence_text = header + "\n" + structured_text

        # --- EDAM guidance injection ---
        edam_guidance = await self.get_edam_guidance(nct_id, evidence_text)
        if edam_guidance:
            evidence_text = edam_guidance + "\n\n" + evidence_text

        # --- Pass 1: Extract antimicrobial evidence ---
        logger.info(f"  classification: Pass 1 — extracting AMP evidence for {nct_id}")
        try:
            pass1_response = await ollama_client.generate(
                model=model,
                prompt=evidence_text,
                system=PASS1_SYSTEM,
                temperature=config.ollama.field_temperatures.get("classification", config.ollama.temperature),
            )
            pass1_text = pass1_response.get("response", "")
        except Exception as e:
            logger.error(f"  classification: Pass 1 failed: {e}")
            return FieldAnnotation(
                field_name=self.field_name,
                value="Other",
                confidence=0.0,
                reasoning=f"Pass 1 LLM call failed: {e}",
                evidence=[],
                model_name=model,
            )

        # --- Pass 2: Apply decision tree to extracted facts ---
        logger.info(f"  classification: Pass 2 — applying decision tree for {nct_id}")
        pass2_prompt = f"Trial: {nct_id}\n"
        pass2_prompt += f"Peptide determination: {peptide_value}\n\n"
        pass2_prompt += f"EXTRACTED FACTS FROM EVIDENCE:\n{pass1_text}\n"

        try:
            pass2_response = await ollama_client.generate(
                model=model,
                prompt=pass2_prompt,
                system=PASS2_SYSTEM,
                temperature=config.ollama.field_temperatures.get("classification", config.ollama.temperature),
            )
            pass2_text = pass2_response.get("response", "")
        except Exception as e:
            logger.warning(f"  classification: Pass 2 failed, using fallback: {e}")
            value = _fallback_classify(pass1_text, peptide_value)
            return FieldAnnotation(
                field_name=self.field_name,
                value=value,
                confidence=0.3,
                reasoning=f"[Pass 2 failed, fallback used] Pass 1: {pass1_text[:400]}",
                evidence=cited_sources[:10],
                model_name=model,
            )

        # Parse Pass 2 response
        value = self._parse_value(pass2_text)
        # Combine both passes in reasoning for audit trail
        reasoning = f"[Pass 1 extraction] {pass1_text[:400]}\n[Pass 2 decision] {pass2_text[:400]}"

        quality = sum(c.quality_score for c in cited_sources[:10]) / max(len(cited_sources[:10]), 1)

        return FieldAnnotation(
            field_name=self.field_name,
            value=value,
            confidence=quality,
            reasoning=reasoning,
            evidence=cited_sources[:10],
            model_name=model,
        )

    def _parse_value(self, text: str) -> str:
        match = re.search(r"Classification:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
        raw = match.group(1).strip().lower() if match else text.lower()

        # Check infection subtype with various separators
        if any(pat in raw for pat in [
            "amp(infection)", "amp (infection)", "amp-infection",
            "amp - infection", "amp: infection",
        ]):
            return "AMP(infection)"
        # Check other subtype with various separators
        if any(pat in raw for pat in [
            "amp(other)", "amp (other)", "amp-other",
            "amp - other", "amp: other",
        ]):
            return "AMP(other)"
        # "amp" present but no recognized subtype — infer from context
        if "amp" in raw and "other" not in raw.replace("amp", ""):
            if "infection" in raw:
                return "AMP(infection)"
            return "AMP(other)"
        return "Other"
