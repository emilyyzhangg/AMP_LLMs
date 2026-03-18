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

# Hardware profile → model selection for classification
# Classification uses a larger model because 8B ignores worked examples
MODEL_OVERRIDES = {
    "mac_mini": "qwen2.5:14b",
    "server": "kimi-k2-thinking",
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
   - Does it stimulate immune defense (recruit immune cells, enhance phagocytosis, activate dendritic cells)?
   - Does it disrupt biofilms?
   - Does it work via a non-antimicrobial mechanism (metabolic hormone, bone growth, vasodilation, immunosuppression, physical/chemical)?

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

  THE CORE TEST: Does this peptide DIRECTLY kill, inhibit, or disrupt bacteria, fungi,
  viruses, or other pathogens through its OWN biochemical action? Does it directly
  stimulate immune DEFENSE specifically against pathogens through antimicrobial mechanisms
  (membrane disruption, pore formation, pathogen lysis)?

  An AMP must have DIRECT antimicrobial activity through ONE of these specific modes:
  A) Direct antimicrobial: physically kills/lyses microorganisms (e.g., colistin disrupts bacterial membranes, nisin forms pores)
  B) Immunostimulatory HOST DEFENSE peptide: DIRECTLY recruits immune cells to kill pathogens at infection sites (e.g., LL-37, defensins, cathelicidins)
  C) Anti-biofilm: DIRECTLY disrupts microbial biofilms through biochemical interaction

  IMPORTANT: Mode D (pathogen-targeting vaccines) was REMOVED. Peptide vaccines that induce
  antibodies against pathogens are NOT AMPs — they work through adaptive immunity, not through
  direct antimicrobial action. A vaccine peptide does not itself kill pathogens.

  CHECK THE EXTRACTED FACTS:
  - Database Matches: DRAMP or APD3 hit → evidence FOR AMP, but not sufficient alone. The peptide
    MUST also have a direct antimicrobial mechanism confirmed in the facts.
  - Mechanism: ONLY "directly kills/inhibits microorganisms" or "directly recruits immune cells to
    kill pathogens" qualifies. General "immunomodulation" does NOT qualify.
  - Immune Direction: "PROMOTE" alone is NOT enough. Many peptides promote immune responses but
    are NOT antimicrobial (e.g., cancer vaccines, adjuvants). The immune promotion must be
    SPECIFICALLY directed at killing/clearing pathogens through innate defense mechanisms.

  CRITICAL — NOT AMPs. The following are NEVER AMPs regardless of context:

  ANTIRETROVIRALS AND HIV DRUGS — these are the most common misclassification:
  - Enfuvirtide (T-20/Fuzeon): blocks HIV viral FUSION with host cells. This is a VIRAL ENTRY
    INHIBITOR, not an antimicrobial peptide. It does NOT kill HIV — it prevents cell entry.
    Classification: Other.
  - HIV peptide vaccines (gp120 peptides, gp41 peptides, HIV envelope peptides): these induce
    antibody responses against HIV. They do NOT directly kill the virus. Classification: Other.
  - Peptide T (DAPTA): binds CCR5 chemokine receptor, blocks HIV entry. It does NOT kill HIV
    or any pathogen. Classification: Other.
  - ANY peptide used in HIV/AIDS trials that works by blocking viral entry, inducing antibodies,
    or modulating immune response → Other. HIV drugs are NOT AMPs unless they physically lyse
    or disrupt viral particles (which is extremely rare).

  VACCINE PEPTIDES — NOT AMPs even if targeting pathogens:
  - Peptide vaccines (hepatitis, influenza, malaria, HPV, etc.): induce adaptive immune
    responses. The peptide itself does NOT kill pathogens. Classification: Other.
  - StreptInCor: prevents autoimmune rheumatic heart disease. Classification: Other.
  - Cancer neoantigen vaccines: target tumor cells, NOT pathogens. Classification: Other.

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
  - Vaccine/antibody induction (adaptive immune response)
  - Vasodilation, immunosuppression, tolerance induction
  - Metabolic regulation, hormone signaling
  - Receptor blocking/agonism (unless the receptor is on a pathogen)
  - General immunomodulation without direct pathogen killing

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
→ Other. Induces antibodies against HIV envelope protein. The peptide itself does NOT kill HIV. Vaccines are NOT AMPs.

Example F: Semaglutide for diabetes
→ Other. GLP-1 analogue — metabolic hormone, not antimicrobial.

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
- If mechanism is viral entry inhibition, receptor blocking, or vaccine/antibody induction → "Other"
- A peptide being USED IN an infectious disease trial does NOT make it an AMP
- A peptide being DERIVED FROM a pathogen does NOT make it an AMP
- A peptide that TREATS infection but works by a non-antimicrobial mechanism (e.g., blocking viral entry) → "Other"
- ONLY peptides that DIRECTLY KILL or PHYSICALLY DISRUPT pathogens qualify as AMPs
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

        # --- Pass 1: Extract antimicrobial evidence ---
        logger.info(f"  classification: Pass 1 — extracting AMP evidence for {nct_id}")
        try:
            pass1_response = await ollama_client.generate(
                model=model,
                prompt=evidence_text,
                system=PASS1_SYSTEM,
                temperature=config.ollama.temperature,
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
                temperature=config.ollama.temperature,
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
        if match:
            raw = match.group(1).strip().lower()
            if "amp(infection)" in raw or "amp (infection)" in raw:
                return "AMP(infection)"
            if "amp(other)" in raw or "amp (other)" in raw:
                return "AMP(other)"
            if "other" in raw:
                return "Other"
            if "amp" in raw:
                return "Other"
            return "Other"
        lower_text = text.lower()
        if "amp(infection)" in lower_text or "amp (infection)" in lower_text:
            return "AMP(infection)"
        if "amp(other)" in lower_text or "amp (other)" in lower_text:
            return "AMP(other)"
        return "Other"
