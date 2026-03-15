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
            "STEP 2: Is it an ANTIMICROBIAL peptide? AMPs kill/inhibit microorganisms: colistin, defensins, "
            "LL-37, polymyxin, daptomycin, nisin. Peptide vaccines against pathogens also count.\n"
            "NOT AMPs: GLP-1/GLP-2 (semaglutide, apraglutide), VIP/Aviptadil, GnRH, somatostatin — these are "
            "peptide hormones, not antimicrobial. If NOT an AMP → 'Other'.\n"
            "STEP 3: Does this AMP target infection? Yes → 'AMP(infection)'. No (wound healing, cancer) → 'AMP(other)'.\n\n"
            "EXAMPLES:\n"
            "- Colistin for UTI → AMP(infection)\n"
            "- LL-37 for wound healing → AMP(other)\n"
            "- VIP/Aviptadil for headaches → Other (peptide but NOT an AMP)\n"
            "- Semaglutide for diabetes → Other (peptide but NOT an AMP)\n"
            "- StreptInCor vaccine vs S. pyogenes → AMP(infection)\n"
            "- Amoxicillin → Other (small molecule, not peptide)"
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
            "CRITICAL: NEVER guess the injection subtype. If the protocol says 'injection' without "
            "specifying IM, SC, or IV, use 'Injection/Infusion - Other/Unspecified'. "
            "Only use Intramuscular if explicitly stated as 'intramuscular' or 'IM'.\n"
            "If an FDA drug label says 'SUBCUTANEOUS', that overrides a generic 'injection' in the protocol.\n"
            "Nutritional formula/shake = Oral - Drink, NOT Oral - Food.\n"
            "Intravenous/IV infusion = 'IV' (not Injection/Infusion - Other).\n"
            "Nasal spray = 'Intranasal' (not Topical - Spray).\n\n"
            "EXAMPLES:\n"
            "- 'IV infusion over 12 hours' → IV\n"
            "- 'subcutaneous injection once weekly' → Injection/Infusion - Subcutaneous/Intradermal\n"
            "- 'peptide vaccine injection' (no route) → Injection/Infusion - Other/Unspecified\n"
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
            "- Registry says COMPLETED → use published literature: Positive (met endpoints), "
            "Failed - completed trial (negative results), or Unknown (no publications).\n"
            "- RECRUITING / NOT_YET_RECRUITING / ENROLLING_BY_INVITATION → 'Recruiting'.\n"
            "- ACTIVE_NOT_RECRUITING → 'Active, not recruiting'.\n"
            "- If multiple publications conflict, prefer the most recent one.\n"
            "- Do NOT use 'Active' alone — use the full value 'Active, not recruiting'."
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
            "Determine the reason for failure/withdrawal/termination. Choose exactly one:\n"
            "Business Reason, Ineffective for purpose, Toxic/Unsafe, Due to covid, Recruitment issues\n\n"
            "If the trial is active, recruiting, positive, or truly unknown → return EMPTY.\n"
            "Published literature overrides whyStopped. COMPLETED trials CAN have failure reasons if "
            "published results show negative outcomes.\n"
            "If multiple publications conflict, prefer the most recent one."
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
            "- Hydrolyzed protein formula (nutrition) → False\n"
            "- Engineered multi-subunit protein (biologic scaffold) → False\n\n"
            "KEY: Is the ACTIVE DRUG a peptide? If 'peptide' is in the product name but it's a "
            "nutritional formula or food → False."
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

        # Handle EMPTY / N/A for failure reason
        if lower in ("empty", "n/a", "not applicable", "none", "no failure", "no reason", ""):
            if "" in field_config["valid_values"]:
                return ""
            return None

        # Normalize common aliases before matching
        alias_map = {
            "intravenous": "IV",
            "active": "Active, not recruiting",
        }
        if lower in alias_map:
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
