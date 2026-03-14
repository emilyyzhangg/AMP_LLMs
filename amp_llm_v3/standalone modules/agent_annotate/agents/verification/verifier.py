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
FIELD_PROMPTS = {
    "classification": {
        "instruction": (
            "Classify this clinical trial into one of three categories:\n"
            "- AMP(infection): Trial involves an antimicrobial peptide targeting infection/pathogens\n"
            "- AMP(other): Trial involves an antimicrobial peptide but for non-infection purposes "
            "(e.g., wound healing, immunomodulation, cancer)\n"
            "- Other: Not an AMP trial"
        ),
        "valid_values": ["AMP(infection)", "AMP(other)", "Other"],
        "parse_pattern": r"Classification:\s*(.+?)(?:\n|$)",
    },
    "delivery_mode": {
        "instruction": (
            "Determine the specific delivery mode. Choose exactly one:\n"
            "Injection/Infusion - Intramuscular, Injection/Infusion - Other/Unspecified, "
            "Injection/Infusion - Subcutaneous/Intradermal, IV, Intranasal, "
            "Oral - Tablet, Oral - Capsule, Oral - Food, Oral - Drink, Oral - Unspecified, "
            "Topical - Cream/Gel, Topical - Powder, Topical - Spray, Topical - Strip/Covering, "
            "Topical - Wash, Topical - Unspecified, Other/Unspecified, Inhalation"
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
            "Recruiting, Unknown, Active, not recruiting"
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
            "Business Reason, Ineffective for purpose, Toxic/Unsafe, Due to covid, Recruitment issues\n"
            "If the trial is active, recruiting, positive, or unknown, return EMPTY."
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
        "instruction": "Determine if the intervention is a peptide: True or False.",
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
        """Extract the field value from verifier response."""
        pattern = field_config["parse_pattern"]
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            return None

        raw = match.group(1).strip()
        lower = raw.lower()

        # Handle EMPTY / N/A for failure reason
        if lower in ("empty", "n/a", "not applicable", "none", ""):
            if "" in field_config["valid_values"]:
                return ""
            return None

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

        return raw

    def _parse_reasoning(self, text: str) -> str:
        match = re.search(r"Reasoning:\s*(.+?)(?:\n\n|$)", text, re.DOTALL)
        if match:
            return match.group(1).strip()[:500]
        return text[:500]
