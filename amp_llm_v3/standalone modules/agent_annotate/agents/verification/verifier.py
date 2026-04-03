"""
Blind Verification Agent.

Receives ONLY raw research data — never the primary annotator's answer.
Independently annotates the field and returns its opinion.

v10: Three verification personas (conservative, evidence-strict, adversarial)
     for cognitive diversity. Dynamic confidence parsing. Hardware-aware
     evidence budgets matching primary annotator limits.
"""

import re
import logging
from typing import Optional

from app.models.verification import ModelOpinion
from app.models.research import ResearchResult

logger = logging.getLogger("agent_annotate.verification.verifier")

# ---------------------------------------------------------------------------
# Verification Personas — each verifier gets a different cognitive lens
# so identical evidence doesn't produce identical reasoning patterns.
# Keyed by verifier model_name (verifier_1, verifier_2, verifier_3).
# ---------------------------------------------------------------------------
VERIFIER_PERSONAS = {
    "verifier_1": {
        "name": "Conservative",
        "prefix": (
            "APPROACH: You are a conservative reviewer. When evidence is ambiguous "
            "or insufficient, always choose the most cautious interpretation. "
            "Absence of evidence is NOT evidence of a result. If you cannot find "
            "direct published support for a claim, default to the safest answer "
            "(e.g., 'Unknown' for outcome, 'Other' for classification, EMPTY for "
            "failure reason). Do NOT assume positive outcomes from trial completion alone.\n\n"
        ),
    },
    "verifier_2": {
        "name": "Evidence-strict",
        "prefix": (
            "APPROACH: You are an evidence-strict reviewer. ONLY base your answer "
            "on facts you can directly cite from the provided data. Do not infer, "
            "assume, or extrapolate beyond what the evidence explicitly states. "
            "For every claim in your answer, you must be able to point to a specific "
            "citation. If no source directly states the answer, acknowledge the gap "
            "and choose the value that requires the least assumption.\n\n"
        ),
    },
    "verifier_3": {
        "name": "Adversarial",
        "prefix": (
            "APPROACH: You are a critical reviewer playing devil's advocate. "
            "Actively look for evidence that CONTRADICTS the most obvious or "
            "intuitive interpretation. Consider alternative explanations. "
            "Challenge assumptions — e.g., a completed trial doesn't mean positive, "
            "a peptide in the name doesn't mean peptide drug, an injection route "
            "in one source may be contradicted by another. If the obvious answer "
            "holds up under scrutiny, confirm it. If not, explain what contradicts it.\n\n"
        ),
    },
}

# Fallback persona for any additional verifiers (verifier_4, etc.)
_DEFAULT_PERSONA = {
    "name": "Standard",
    "prefix": "",
}

# Per-field prompts for blind verification (no knowledge of primary answer)
# These must match the quality and detail of the primary annotator prompts.
FIELD_PROMPTS = {
    "classification": {
        "instruction": (
            "Classify this clinical trial using a two-step decision tree. AMP = Antimicrobial Peptide.\n\n"
            "STEP 1: Is the intervention a peptide? If not → 'Other'.\n"
            "STEP 2: Is it an ANTIMICROBIAL peptide? The CORE TEST: does this peptide contribute to "
            "pathogen defense through any of these 3 modes?\n"
            "Mode A: Kills, inhibits growth of, or disrupts pathogens — bactericidal OR bacteriostatic (membrane disruption, pore formation, growth inhibition)\n"
            "Mode B: Recruits or activates INNATE immune cells to kill pathogens at infection sites — cathelicidins (LL-37), defensins. INNATE immunity only, NOT adaptive (antibody/T-cell induction).\n"
            "Mode C: Disrupts microbial biofilms\n\n"
            "If YES (any mode) → 'AMP'. If NOT an AMP → 'Other'.\n\n"
            "AMPs: colistin, defensins, LL-37, polymyxin, daptomycin, nisin.\n"
            "NOT AMPs (even if they are peptides):\n"
            "- Viral entry inhibitors: Enfuvirtide/T-20 (blocks viral fusion), Peptide T/DAPTA (blocks CCR5)\n"
            "- Neuropeptides/vasodilators: VIP/Aviptadil — vasodilation, NOT antimicrobial\n"
            "- Metabolic hormones: GLP-1/GLP-2, GnRH, somatostatin, insulin, oxytocin\n"
            "- ALL VACCINE PEPTIDES regardless of pathogen target: HIV gp120/gp41 vaccines, malaria "
            "vaccines, influenza vaccines, bacterial peptide vaccines — vaccines work through ADAPTIVE "
            "immunity (antibody induction), NOT direct antimicrobial action. Classification: Other.\n"
            "- Cancer neoantigen vaccines (target tumor cells)\n"
            "- Immunosuppressive peptides, bone growth regulators, structural peptides\n\n"
            "EXAMPLES:\n"
            "- Colistin for UTI → AMP (Mode A: membrane disruption kills bacteria)\n"
            "- LL-37 for wound healing → AMP (Mode A+B: antimicrobial peptide regardless of indication)\n"
            "- HIV gp120 peptide vaccine → Other (adaptive immune response, NOT direct antimicrobial)\n"
            "- Influenza peptide vaccine → Other (induces antibodies, does NOT directly kill virus)\n"
            "- Enfuvirtide for HIV → Other (fusion inhibitor, does NOT kill virus)\n"
            "- VIP/Aviptadil for COVID ARDS → Other (neuropeptide vasodilator)\n"
            "- Semaglutide for diabetes → Other (metabolic hormone)\n"
            "- Cancer neoantigen vaccine → Other (targets tumor, not pathogen)\n"
            "- Nisin for bacterial mastitis → AMP (Mode A: pore formation kills bacteria)\n"
            "- Daptomycin for MRSA → AMP (Mode A: disrupts bacterial membranes)\n"
            "When in doubt about mechanism → 'Other'. False AMP is worse than missing a true AMP."
        ),
        "valid_values": ["AMP", "Other"],
        "parse_pattern": r"Classification:\s*(.+?)(?:\n|$)",
    },
    "delivery_mode": {
        "instruction": (
            "Determine the delivery mode. Choose EXACTLY ONE value from this list:\n"
            "Injection/Infusion, Oral, Topical, Other\n\n"
            "CATEGORY DEFINITIONS:\n"
            "- Injection/Infusion: IV, intramuscular (IM), subcutaneous (SC), intradermal, intravitreal, "
            "any parenteral route\n"
            "- Oral: tablet, capsule, food, drink, nutritional formula, any route through the mouth\n"
            "- Topical: cream, gel, spray, wash, powder, strip/covering, any application to skin or mucosal surface\n"
            "- Other: inhalation, intranasal, or anything that does not fit the above categories\n\n"
            "EXAMPLES:\n"
            "- 'IV infusion over 12 hours' → Injection/Infusion\n"
            "- 'subcutaneous injection once weekly' → Injection/Infusion\n"
            "- 'peptide vaccine injection' → Injection/Infusion\n"
            "- 'intravitreal injection' → Injection/Infusion\n"
            "- 'oral capsule twice daily' → Oral\n"
            "- 'nutritional formula' → Oral\n"
            "- 'topical cream applied to wound' → Topical\n"
            "- 'nasal spray' → Other\n"
            "- 'inhaled via nebulizer' → Other"
        ),
        "valid_values": [
            "Injection/Infusion",
            "Oral",
            "Topical",
            "Other",
        ],
        "parse_pattern": r"Delivery Mode:\s*(.+?)(?:\n|$)",
    },
    "outcome": {
        "instruction": (
            "Determine the trial outcome. Choose exactly one:\n"
            "Positive, Withdrawn, Terminated, Failed - completed trial, "
            "Recruiting, Unknown, Active, not recruiting\n\n"
            "CRITICAL RULES:\n"
            "- Registry says TERMINATED → ONLY two outcomes are valid:\n"
            "  * Positive published results OR drug advanced to later phases/approval → 'Positive'\n"
            "  * ANY other case (safety failure, futility, efficacy failure, business reasons,\n"
            "    no publications, reason unclear) → 'Terminated'\n"
            "  CRITICAL: 'Failed - completed trial' is NEVER valid for TERMINATED trials.\n"
            "  That value is exclusively for COMPLETED trials with published negative results.\n"
            "- Registry says WITHDRAWN → 'Withdrawn'.\n"
            "- RECRUITING / NOT_YET_RECRUITING / ENROLLING_BY_INVITATION → 'Recruiting'.\n"
            "- ACTIVE_NOT_RECRUITING → 'Active, not recruiting'.\n"
            "- Registry says COMPLETED → use published literature to decide:\n"
            "  * Positive: published results show the trial met its primary endpoints\n"
            "  * Failed - completed trial: published results show NEGATIVE outcomes (failed to meet endpoints)\n"
            "  * If no publications found, apply COMPLETION HEURISTICS below.\n\n"
            "COMPLETION HEURISTICS (when no published results found for COMPLETED trials):\n"
            "H1. Phase I/Early Phase I that completed normally → 'Positive' (completing a safety trial IS success).\n"
            "    BUT: H1 requires at least ONE corroborating signal: results posted, a related publication,\n"
            "    or a subsequent later-phase trial. Phase I completion with ZERO publications and no results\n"
            "    posted → 'Unknown', not 'Positive'.\n"
            "H1b. Phase I completed >5 years ago, no Phase II found, no publications → 'Unknown'.\n"
            "H2. Results posted on ClinicalTrials.gov (hasResults=Yes) → lean 'Positive'.\n"
            "H3. Old trial (pre-2010) completed normally, led to subsequent trials → 'Positive'.\n"
            "H3b. Phase II/III completed >10 years ago, no publications, no negative evidence → lean 'Positive'.\n"
            "H4. Completed + Results Posted but no specific result descriptions → lean 'Positive'.\n"
            "H5. DEFAULT: Only use 'Unknown' after exhausting H1-H4.\n\n"
            "- IMPORTANT: COMPLETED status alone does NOT mean 'Failed - completed trial'. "
            "COMPLETED is a registry STATUS, not an outcome. You MUST have PUBLISHED EVIDENCE of "
            "negative results to choose 'Failed - completed trial'.\n"
            "- COMPLETED trials without published results or Results Posted=Yes → 'Unknown', NOT 'Positive'.\n"
            "- 'Failed - completed trial' requires POSITIVE EVIDENCE of failure: a publication or "
            "posted result that explicitly states the trial did NOT meet its primary endpoint, "
            "or results showing negative/null efficacy. Absence of publications is NOT evidence "
            "of failure — it is evidence of Unknown. Do NOT choose Failed just because you cannot "
            "find positive results.\n"
            "- You MUST have PUBLISHED EVIDENCE of positive results to choose 'Positive'.\n"
            "- If NO publications, NO results posted, NO subsequent trials → 'Unknown'.\n"
            "- If multiple publications conflict, prefer the most recent one.\n"
            "- Do NOT use 'Active' alone — use the full value 'Active, not recruiting'.\n"
            "- 'COMPLETED' is NOT a valid outcome value. Translate it using the rules above."
        ),
        "valid_values": [
            "Positive",
            "Withdrawn",
            "Terminated",
            "Failed - completed trial",
            "Recruiting",
            "Unknown",
            "Active, not recruiting",
        ],
        "parse_pattern": r"Outcome:\s*(.+?)(?:\n|$)",
    },
    "reason_for_failure": {
        "instruction": (
            "Determine the reason for failure/withdrawal/termination.\n\n"
            "VALID VALUES (choose EXACTLY one):\n"
            "- Business Reason: funding, sponsor decision, company dissolved, strategic, manufacturing\n"
            "- Ineffective for purpose: PUBLISHED results show trial failed to meet endpoints\n"
            "- Toxic/Unsafe: safety concerns, adverse events, toxicity, DSMB stopped for safety\n"
            "- Due to covid: trial disrupted by COVID-19 pandemic\n"
            "- Recruitment issues: slow enrollment, unable to recruit\n"
            "- EMPTY: no failure occurred, or no evidence of failure exists\n\n"
            "CRITICAL RULES:\n"
            "- 'COMPLETED' is a trial STATUS, NOT a failure reason. Never return 'COMPLETED' as the answer.\n"
            "- If the trial is active, recruiting, positive, or truly unknown → return EMPTY.\n"
            "- COMPLETED trials: ONLY assign a failure reason if there is PUBLISHED EVIDENCE of negative "
            "outcomes (e.g., a paper saying 'failed to meet primary endpoint'). If a trial COMPLETED "
            "but there are no published negative results, the answer is EMPTY.\n"
            "- Do NOT assume failure from completion. COMPLETED + no negative publications = EMPTY.\n"
            "- Published literature overrides whyStopped field.\n"
            "- If multiple publications conflict, prefer the most recent one.\n"
            "- Require POSITIVE evidence of failure. Absence of results ≠ failure."
        ),
        "valid_values": [
            "Business Reason",
            "Ineffective for purpose",
            "Toxic/Unsafe",
            "Due to covid",
            "Recruitment issues",
            "",
        ],
        "parse_pattern": r"Reason for Failure:\s*(.+?)(?:\n|$)",
    },
    "peptide": {
        "instruction": (
            "Determine if the primary intervention is a peptide therapeutic: True or False.\n\n"
            "DEFINITION: A peptide therapeutic is 2-100 amino acid residues serving as the ACTIVE drug. "
            "Includes: AMPs, hormone analogues, cyclic peptides, peptide vaccines, insulin. "
            "Excludes: monoclonal antibodies (>100 AA), small molecules, nutritional formulas "
            "(\"Peptide 1.5\", Peptamen), HSP-peptide complexes (peptide is cargo), exosome vehicles, "
            "whole proteins >100 AA.\n\n"
            "EXAMPLES:\n"
            "- Aviptadil (VIP, 28 amino acids) → True\n"
            "- Semaglutide (GLP-1 analogue, 31 AA) → True\n"
            "- Colistin (lipopeptide antibiotic) → True\n"
            "- StreptInCor (synthetic peptide vaccine) → True\n"
            "- Apraglutide (GLP-2 analogue) → True\n"
            "- Pembrolizumab (monoclonal antibody) → False\n"
            "- Amoxicillin (small molecule) → False\n"
            "- Kate Farm Peptide 1.5 (nutritional formula) → False\n"
            "- 'Peptide 1.5' tube feeding formula → False\n"
            "- Peptamen (semi-elemental nutritional formula) → False\n"
            "- Hydrolyzed protein formula (nutrition) → False\n"
            "- Engineered multi-subunit protein (biologic scaffold) → False\n\n"
            "CRITICAL RULES:\n"
            "- Is the ACTIVE DRUG a peptide? If 'peptide' is in the product name but it's a "
            "nutritional formula, dietary supplement, or food → False.\n"
            "- Brand names containing 'peptide' do NOT make the product a peptide drug. "
            "'Peptide 1.5', 'Peptamen', 'Kate Farms Peptide' are nutritional formulas → False.\n"
            "- Nutritional formulas with hydrolyzed proteins are NOT peptide drugs.\n"
            "- MULTI-DRUG TRIALS: evaluate the PRIMARY study drug. If a peptide is "
            "co-administered as background therapy but the primary experimental drug is "
            "non-peptide → False.\n"
            "- Heat shock protein-peptide complexes: the peptide is antigenic cargo, "
            "not the active mechanism → False.\n"
            "- Autologous dexosomes/exosomes loaded with peptides: the vehicle is the "
            "drug, not the peptide cargo → False.\n"
            "- CYCLIC PEPTIDES: ChEMBL and other databases often classify cyclic peptides "
            "as 'small molecules' — this does NOT make them non-peptides. If the drug name "
            "explicitly states 'cyclic peptide' or contains a named cyclic peptide (e.g. "
            "cpFT, Fertiline, cyclosporine backbone), classify as True.\n"
            "- RADIOLABELED PEPTIDES: Drugs like [68Ga]GA-NeoB or [177Lu]Lu-PSMA are "
            "radiolabeled peptides. The radioactive label ([68Ga], [177Lu], [99mTc] etc.) "
            "does NOT change the molecular class — classify by the PEPTIDE BACKBONE. "
            "If the backbone is a peptide chain (e.g. bombesin analog, PSMA ligand peptide, "
            "neurotensin), classify as True.\n\n"
            "ADDITIONAL EXAMPLES:\n"
            "- HSPPC-96/Oncophage (heat shock protein-peptide complex) → False\n"
            "- Autologous dexosomes loaded with peptides → False\n"
            "- Amdoxovir + enfuvirtide (nucleoside + peptide combo, primary = amdoxovir) → False\n"
            "- cpFT / cyclic peptide Fertiline (cyclic peptide, ChEMBL calls it small molecule) → True\n"
            "- [68Ga]GA-NeoB (radiolabeled bombesin analog, 14aa peptide backbone) → True\n"
            "- [177Lu]Lu-NeoB (radiolabeled bombesin analog) → True\n"
        ),
        "valid_values": ["True", "False"],
        "parse_pattern": r"Peptide:\s*(True|False)",
    },
}

# Response template — includes persona prefix and confidence self-assessment
SYSTEM_TEMPLATE = """You are an independent clinical trial data reviewer. You must evaluate the evidence below and provide your own assessment.

{persona_prefix}{instruction}

Respond EXACTLY in this format:
{field_label}: [your answer]
Confidence: [High, Medium, or Low]
Evidence: [cite the specific data you based your decision on]
Reasoning: [brief explanation]"""

# Confidence mapping from verifier self-assessment
_CONFIDENCE_MAP = {
    "high": 0.9,
    "medium": 0.7,
    "low": 0.4,
}
_DEFAULT_CONFIDENCE = 0.7


class BlindVerifier:
    """Performs blind verification — never sees the primary annotator's answer.

    Each verifier gets a different cognitive persona (conservative, evidence-strict,
    adversarial) to provide diverse perspectives on the same evidence.
    """

    async def verify(
        self,
        nct_id: str,
        field_name: str,
        research_results: list[ResearchResult],
        model_name: str,
        ollama_model: str,
    ) -> ModelOpinion:
        """
        Independently annotate a field using only raw research data.
        The verifier has NO knowledge of what the primary annotator concluded.
        """
        field_config = FIELD_PROMPTS.get(field_name)
        if not field_config:
            return ModelOpinion(
                model_name=model_name,
                agrees=False,
                suggested_value=None,
                reasoning=f"Unknown field: {field_name}",
            )

        from app.services.config_service import config_service
        config = config_service.get()

        # --- Evidence budget matches primary annotator ---
        is_server = config.orchestrator.hardware_profile == "server"
        max_citations = 50 if is_server else 30

        # Build structured evidence from research (raw data only, no primary answer)
        _SOURCE_TO_SECTION = {
            "clinicaltrials_gov": "TRIAL METADATA",
            "who_ictrp": "TRIAL METADATA",
            "openfda": "TRIAL METADATA",
            "pubmed": "PUBLISHED RESULTS",
            "pmc": "PUBLISHED RESULTS",
            "pmc_bioc": "PUBLISHED RESULTS",
            "europe_pmc": "PUBLISHED RESULTS",
            "semantic_scholar": "PUBLISHED RESULTS",
            "chembl": "DRUG/PEPTIDE DATA",
            "uniprot": "DRUG/PEPTIDE DATA",
            "dramp": "DRUG/PEPTIDE DATA",
            "iuphar": "DRUG/PEPTIDE DATA",
            "dbaasp": "ANTIMICROBIAL DATA",
            "apd": "ANTIMICROBIAL DATA",
            "rcsb_pdb": "STRUCTURAL DATA",
            "pdbe": "STRUCTURAL DATA",
            "ebi_proteins": "STRUCTURAL DATA",
            "duckduckgo": "WEB SOURCES",
        }
        sections: dict[str, list[str]] = {}
        seen: set[str] = set()
        total = 0
        for result in research_results:
            if result.error:
                continue
            for citation in result.citations[:8]:
                if total >= max_citations:
                    break
                key = (citation.snippet or "")[:60].lower()
                if key in seen:
                    continue
                seen.add(key)
                section = _SOURCE_TO_SECTION.get(citation.source_name, "WEB SOURCES")
                line = (
                    f"[{citation.source_name}] "
                    f"{citation.identifier or ''}: "
                    f"{citation.snippet}"
                )
                sections.setdefault(section, []).append(line)
                total += 1

        evidence_parts = [f"Trial: {nct_id}\n"]

        for sec_name in [
            "TRIAL METADATA", "PUBLISHED RESULTS", "DRUG/PEPTIDE DATA",
            "ANTIMICROBIAL DATA", "STRUCTURAL DATA", "WEB SOURCES",
        ]:
            if sec_name in sections:
                evidence_parts.append(f"\n=== {sec_name} ===")
                evidence_parts.extend(sections[sec_name])

        # v27e: Structured facts go AFTER evidence, not before.
        # Small models are primed by what they see first — putting facts
        # before evidence caused gemma2:9b and qwen2.5:7b to enter
        # "summary mode" instead of following the response format.
        # Placing facts last leverages recency bias: the last thing the
        # model reads before generating has the most influence.
        if field_name == "peptide":
            structured = self._extract_structured_facts(research_results)
            if structured:
                evidence_parts.append("\n=== KEY FACTS TO CONSIDER ===")
                evidence_parts.extend(structured)
                evidence_parts.append(
                    "\nRemember: respond EXACTLY as Peptide: True or False"
                )

        evidence_text = "\n".join(evidence_parts)

        # --- EDAM anomaly warnings (safe for verifiers — no answer leakage) ---
        try:
            from app.services.memory import memory_store
            anomaly_warning = await memory_store.get_anomaly_warnings(
                field_name, max_tokens=200
            )
            if anomaly_warning:
                evidence_text = anomaly_warning + "\n\n" + evidence_text
        except Exception:
            pass  # EDAM failure is never fatal

        # Build field-specific label for the prompt
        field_labels = {
            "classification": "Classification",
            "delivery_mode": "Delivery Mode",
            "outcome": "Outcome",
            "reason_for_failure": "Reason for Failure",
            "peptide": "Peptide",
        }
        field_label = field_labels.get(field_name, field_name)

        # Select persona for this verifier
        persona = VERIFIER_PERSONAS.get(model_name, _DEFAULT_PERSONA)
        persona_prefix = persona["prefix"]

        system_prompt = SYSTEM_TEMPLATE.format(
            persona_prefix=persona_prefix,
            instruction=field_config["instruction"],
            field_label=field_label,
        )

        from app.services.ollama_client import ollama_client

        try:
            response = await ollama_client.generate(
                model=ollama_model,
                prompt=evidence_text,
                system=system_prompt,
                temperature=config.ollama.temperature,
            )
            raw_text = response.get("response", "")
        except Exception as e:
            logger.error(f"Verifier {model_name} failed for {nct_id}/{field_name}: {e}")
            return ModelOpinion(
                model_name=model_name,
                agrees=False,
                suggested_value=None,
                reasoning=f"Verification call failed: {e}",
                confidence=0.0,
            )

        # v17: Check for empty or garbage responses before parsing
        if not raw_text or len(raw_text.strip()) < 5:
            logger.warning(
                f"Verifier {model_name} returned empty/trivial response for "
                f"{nct_id}/{field_name} ({len(raw_text)} chars)"
            )
            return ModelOpinion(
                model_name=model_name,
                agrees=False,
                suggested_value=None,
                reasoning=f"Empty response from {model_name} ({len(raw_text)} chars)",
                confidence=0.0,
            )

        # Parse the verifier's independent answer
        value = self._parse_value(raw_text, field_config)
        reasoning = self._parse_reasoning(raw_text)
        confidence = self._parse_confidence(raw_text)

        return ModelOpinion(
            model_name=model_name,
            agrees=False,  # Will be set by consensus checker
            suggested_value=value,
            reasoning=reasoning,
            confidence=confidence,
        )

    @staticmethod
    def _parse_confidence(text: str) -> float:
        """Extract confidence self-assessment from verifier response.

        Looks for 'Confidence: High/Medium/Low' in the response.
        Falls back to 0.7 (medium) if not found or unparseable.
        """
        match = re.search(r"Confidence:\s*(High|Medium|Low)", text, re.IGNORECASE)
        if match:
            level = match.group(1).strip().lower()
            return _CONFIDENCE_MAP.get(level, _DEFAULT_CONFIDENCE)
        return _DEFAULT_CONFIDENCE

    def _parse_value(self, text: str, field_config: dict) -> Optional[str]:
        """Extract the field value from verifier response.

        Returns None for unrecognizable values instead of passing through raw text.
        This prevents invalid values from entering the consensus check.
        """
        pattern = field_config["parse_pattern"]
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            return None

        raw = match.group(1).strip()
        lower = raw.lower()

        # Handle EMPTY / N/A / status-as-value for failure reason
        # Verifiers frequently return trial STATUSES instead of failure reasons.
        # All of these mean "no failure" → empty string.
        _NO_FAILURE_INDICATORS = (
            "empty", "n/a", "not applicable", "none", "no failure", "no reason",
            "completed", "active_not_recruiting", "active, not recruiting",
            "recruiting", "not_yet_recruiting", "not yet recruiting",
            "unknown", "",
        )
        if "" in field_config.get("valid_values", []):
            # This is the reason_for_failure field (empty is valid)
            stripped = lower.strip('"').strip("'").strip("*").strip()
            # Check direct match
            if stripped in _NO_FAILURE_INDICATORS:
                return ""
            # Check if it starts with a status keyword (handles verbose explanations
            # like "Unknown (as the trial has been completed)")
            for indicator in ("completed", "unknown", "active", "recruiting", "not_yet", "n/a"):
                if stripped.startswith(indicator):
                    return ""

        # Handle EMPTY for non-failure fields that don't have "" as valid
        if lower in ("empty", "n/a", "not applicable", "none", ""):
            return None

        # Normalize common aliases before matching
        alias_map = {
            "intravenous": "IV",
            "active": "Active, not recruiting",
            "active not recruiting": "Active, not recruiting",
            "completed": None,  # Not a valid outcome — parser should try harder
        }
        if lower in alias_map:
            if alias_map[lower] is None:
                return None  # Force re-evaluation
            return alias_map[lower]

        # Exact match first (case-insensitive)
        for valid in field_config["valid_values"]:
            if valid.lower() == lower:
                return valid

        # Substring containment match
        for valid in field_config["valid_values"]:
            if valid and valid.lower() in lower:
                return valid

        # Reverse containment (raw text is a substring of a valid value)
        for valid in field_config["valid_values"]:
            if valid and lower in valid.lower():
                return valid

        # If no match found, return None — do NOT pass through raw text
        logger.warning(f"Verifier produced unrecognizable value: '{raw}' — returning None")
        return None

    def _parse_reasoning(self, text: str) -> str:
        match = re.search(r"Reasoning:\s*(.+?)(?:\n\n|$)", text, re.DOTALL)
        if match:
            return match.group(1).strip()[:500]
        return text[:500]

    @staticmethod
    def _extract_structured_facts(
        research_results: list[ResearchResult],
    ) -> list[str]:
        """v27c: Extract key structured facts from research data for the peptide field.

        Pulls mature chain lengths from UniProt citations and peptide signals
        from arm group descriptions. These facts are prepended to the evidence
        so small models can't bury them in free-text noise.
        """
        facts: list[str] = []

        for result in research_results:
            if result.error:
                continue

            # 1. UniProt mature chain lengths from citations
            for citation in result.citations:
                if citation.source_name not in ("uniprot", "ebi_proteins"):
                    continue
                snippet = citation.snippet or ""
                if "Mature form:" in snippet:
                    # Extract the mature form line
                    for part in snippet.split(". "):
                        if "Mature form:" in part:
                            facts.append(f"- {citation.identifier or 'UniProt'}: {part.strip()}")
                        elif "Precursor length:" in part:
                            facts.append(
                                f"- {citation.identifier or 'UniProt'}: {part.strip()} "
                                f"(this is the PRECURSOR, not the administered drug)"
                            )

            # 2. Arm group descriptions mentioning peptides
            if result.agent_name != "clinical_protocol" or not result.raw_data:
                continue
            proto = result.raw_data.get(
                "protocol_section", result.raw_data.get("protocolSection", {})
            )
            arms_mod = proto.get("armsInterventionsModule", {})
            for arm in arms_mod.get("armGroups", []):
                desc = arm.get("description", "")
                label = arm.get("label", "")
                desc_lower = desc.lower()
                # Detect peptide-conjugate / synthetic peptide signals
                if any(
                    sig in desc_lower
                    for sig in [
                        "synthetic peptide",
                        "peptide conjugat",
                        "peptide-conjugat",
                        "short peptide",
                        "peptide vaccine",
                        "peptide immunother",
                    ]
                ):
                    facts.append(
                        f"- Arm '{label}': \"{desc[:200]}\""
                    )

        return facts
