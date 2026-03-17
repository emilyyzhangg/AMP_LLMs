"""
Blind Verification Agent.

Receives ONLY raw research data — never the primary annotator's answer.
Independently annotates the field and returns its opinion.
"""

import re
import logging
from typing import Optional

from app.models.verification import ModelOpinion
from app.models.research import ResearchResult

logger = logging.getLogger("agent_annotate.verification.verifier")

# Per-field prompts for blind verification (no knowledge of primary answer)
# These must match the quality and detail of the primary annotator prompts.
FIELD_PROMPTS = {
    "classification": {
        "instruction": (
            "Classify this clinical trial using a three-step decision tree. AMP = Antimicrobial Peptide.\n\n"
            "STEP 1: Is the intervention a peptide? If not → 'Other'.\n"
            "STEP 2: Is it an ANTIMICROBIAL peptide? The CORE TEST: does this peptide DIRECTLY KILL, "
            "LYSE, or PHYSICALLY DISRUPT pathogens through its own biochemical action? Or does it "
            "directly recruit innate immune cells to kill pathogens at infection sites (host defense peptides)?\n"
            "AMPs: colistin, defensins, LL-37, polymyxin, daptomycin, nisin — these physically disrupt/kill microorganisms.\n"
            "NOT AMPs (even if they are peptides):\n"
            "- HIV DRUGS: Enfuvirtide/T-20 (blocks viral fusion — entry inhibitor, NOT antimicrobial), "
            "Peptide T/DAPTA (blocks CCR5 receptor), HIV peptide vaccines (induce antibodies, NOT direct killing)\n"
            "- ALL VACCINE PEPTIDES: vaccines induce adaptive immunity — the peptide does NOT itself kill pathogens\n"
            "- Neuropeptides/vasodilators: VIP/Aviptadil — vasodilation, NOT antimicrobial\n"
            "- Metabolic hormones: GLP-1/GLP-2, GnRH, somatostatin, insulin, oxytocin\n"
            "- Immunosuppressive peptides, bone growth regulators, structural peptides\n"
            "- Viral entry inhibitors, receptor blockers/agonists\n"
            "DECISIVE RULE: If the peptide treats infection but works by blocking receptors, inducing "
            "antibodies, or any mechanism OTHER than directly killing/disrupting pathogens → 'Other'.\n"
            "If NOT an AMP → 'Other'.\n"
            "STEP 3: Does this AMP target infection? Yes → 'AMP(infection)'. No (wound healing, cancer) → 'AMP(other)'.\n\n"
            "EXAMPLES:\n"
            "- Colistin for UTI → AMP(infection) (membrane disruption kills bacteria)\n"
            "- LL-37 for wound healing → AMP(other) (directly kills bacteria, but trial is wound healing)\n"
            "- Enfuvirtide for HIV → Other (fusion inhibitor, does NOT kill virus)\n"
            "- HIV gp120 vaccine → Other (induces antibodies, peptide doesn't kill HIV)\n"
            "- Peptide T for HIV cognitive impairment → Other (blocks CCR5, NOT antimicrobial)\n"
            "- VIP/Aviptadil for COVID ARDS → Other (neuropeptide vasodilator)\n"
            "- Semaglutide for diabetes → Other (metabolic hormone)\n"
            "- Nisin for bacterial mastitis → AMP(infection) (pore formation kills bacteria)\n"
            "- Daptomycin for MRSA → AMP(infection) (disrupts bacterial membranes)\n"
            "- Influenza peptide vaccine → Other (vaccine, NOT direct killing)\n"
            "When in doubt → 'Other'. False AMP is worse than missing a true AMP."
        ),
        "valid_values": ["AMP(infection)", "AMP(other)", "Other"],
        "parse_pattern": r"Classification:\s*(.+?)(?:\n|$)",
    },
    "delivery_mode": {
        "instruction": (
            "Determine the specific delivery mode. Choose EXACTLY ONE value from this list:\n"
            "Injection/Infusion - Intramuscular, Injection/Infusion - Other/Unspecified, "
            "Injection/Infusion - Subcutaneous/Intradermal, IV, Intranasal, "
            "Oral - Tablet, Oral - Capsule, Oral - Food, Oral - Drink, Oral - Unspecified, "
            "Topical - Cream/Gel, Topical - Powder, Topical - Spray, Topical - Strip/Covering, "
            "Topical - Wash, Topical - Unspecified, Other/Unspecified, Inhalation\n\n"
            "CRITICAL — NEVER GUESS THE INJECTION ROUTE:\n"
            "- If the protocol says 'injection' WITHOUT specifying IM, SC, or IV → 'Injection/Infusion - Other/Unspecified'\n"
            "- If the protocol says 'administered by injection' without route → 'Injection/Infusion - Other/Unspecified'\n"
            "- If the protocol says 'vaccine injection' without route → 'Injection/Infusion - Other/Unspecified'\n"
            "- Do NOT guess Intramuscular or Subcutaneous based on drug class (e.g., 'vaccines are usually IM')\n"
            "- Only use Intramuscular if the words 'intramuscular' or 'IM' appear explicitly\n"
            "- Only use Subcutaneous if 'subcutaneous', 'SC', 'sub-Q', or 'intradermal' appear explicitly\n"
            "- If an FDA drug label says 'SUBCUTANEOUS', that overrides a generic 'injection' in the protocol\n"
            "- Nutritional formula/shake = Oral - Drink, NOT Oral - Food\n"
            "- Intravenous/IV infusion = 'IV' (not Injection/Infusion - Other)\n"
            "- Nasal spray = 'Intranasal' (not Topical - Spray)\n\n"
            "EXAMPLES:\n"
            "- 'IV infusion over 12 hours' → IV\n"
            "- 'subcutaneous injection once weekly' → Injection/Infusion - Subcutaneous/Intradermal\n"
            "- 'peptide vaccine injection' (no route) → Injection/Infusion - Other/Unspecified\n"
            "- 'administered by injection once daily' → Injection/Infusion - Other/Unspecified\n"
            "- 'nutritional formula' → Oral - Drink"
        ),
        "valid_values": [
            "Injection/Infusion - Intramuscular",
            "Injection/Infusion - Other/Unspecified",
            "Injection/Infusion - Subcutaneous/Intradermal",
            "IV",
            "Intranasal",
            "Oral - Tablet",
            "Oral - Capsule",
            "Oral - Food",
            "Oral - Drink",
            "Oral - Unspecified",
            "Topical - Cream/Gel",
            "Topical - Powder",
            "Topical - Spray",
            "Topical - Strip/Covering",
            "Topical - Wash",
            "Topical - Unspecified",
            "Other/Unspecified",
            "Inhalation",
        ],
        "parse_pattern": r"Delivery Mode:\s*(.+?)(?:\n|$)",
    },
    "outcome": {
        "instruction": (
            "Determine the trial outcome. Choose exactly one:\n"
            "Positive, Withdrawn, Terminated, Failed - completed trial, "
            "Recruiting, Unknown, Active, not recruiting\n\n"
            "CRITICAL RULES:\n"
            "- Registry says TERMINATED → 'Terminated', regardless of interim results.\n"
            "- Registry says WITHDRAWN → 'Withdrawn'.\n"
            "- Registry says COMPLETED → use published literature to decide:\n"
            "  * Positive: published results show the trial met its primary endpoints\n"
            "  * Failed - completed trial: published results show NEGATIVE outcomes (failed to meet endpoints)\n"
            "  * If no publications found, apply COMPLETION HEURISTICS:\n"
            "    - Phase I that completed normally → 'Positive' (safety trial completion IS success)\n"
            "    - Results posted on ClinicalTrials.gov → lean 'Positive'\n"
            "    - Old trial (pre-2010) completed normally, no negative evidence → lean 'Positive'\n"
            "    - Only use 'Unknown' after exhausting all heuristics\n"
            "- IMPORTANT: COMPLETED status alone does NOT mean 'Failed - completed trial'. "
            "COMPLETED is a registry STATUS, not an outcome. You MUST have PUBLISHED EVIDENCE of "
            "negative results to choose 'Failed - completed trial'.\n"
            "- RECRUITING / NOT_YET_RECRUITING / ENROLLING_BY_INVITATION → 'Recruiting'.\n"
            "- ACTIVE_NOT_RECRUITING → 'Active, not recruiting'.\n"
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
            "- Nutritional formulas with hydrolyzed proteins are NOT peptide drugs."
        ),
        "valid_values": ["True", "False"],
        "parse_pattern": r"Peptide:\s*(True|False)",
    },
}

SYSTEM_TEMPLATE = """You are an independent clinical trial data reviewer. You must evaluate the evidence below and provide your own assessment.

{instruction}

Respond EXACTLY in this format:
{field_label}: [your answer]
Evidence: [cite the specific data you based your decision on]
Reasoning: [brief explanation]"""


class BlindVerifier:
    """Performs blind verification — never sees the primary annotator's answer."""

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

        # Build evidence from research (raw data only, no primary answer)
        evidence_text = f"Trial: {nct_id}\n\nEvidence from research:\n"
        for result in research_results:
            if result.error:
                continue
            for citation in result.citations[:10]:
                evidence_text += (
                    f"[{citation.source_name}] {citation.identifier or ''}: "
                    f"{citation.snippet}\n"
                )

        # Build field-specific label for the prompt
        field_labels = {
            "classification": "Classification",
            "delivery_mode": "Delivery Mode",
            "outcome": "Outcome",
            "reason_for_failure": "Reason for Failure",
            "peptide": "Peptide",
        }
        field_label = field_labels.get(field_name, field_name)

        system_prompt = SYSTEM_TEMPLATE.format(
            instruction=field_config["instruction"],
            field_label=field_label,
        )

        from app.services.ollama_client import ollama_client
        from app.services.config_service import config_service
        config = config_service.get()

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

        # Parse the verifier's independent answer
        value = self._parse_value(raw_text, field_config)
        reasoning = self._parse_reasoning(raw_text)

        return ModelOpinion(
            model_name=model_name,
            agrees=False,  # Will be set by consensus checker
            suggested_value=value,
            reasoning=reasoning,
            confidence=0.7,  # Base confidence for successful verification
        )

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
