"""
EDAM Loop 2: Correction Learner.

Processes two types of learning signals:
1. Human review decisions (approve/override) — highest-quality corrections
2. Self-review — premium model re-evaluates flagged items autonomously

Corrections are stored with mandatory evidence citations. The system
generates reflections explaining WHY the original annotation was wrong,
which become retrievable guidance for future annotations.

Self-review corrections are weighted lower than human corrections because
the reviewing model may have its own biases. All corrections require
at least one concrete evidence citation — no ungrounded self-corrections.
"""

import json
import logging
from typing import Optional

from app.services.memory.memory_store import MemoryStore
from app.services.memory.edam_config import SELF_REVIEW_ENABLED, SELF_REVIEW_MAX_ITEMS

logger = logging.getLogger("agent_annotate.edam.corrections")

SELF_REVIEW_SYSTEM = """You are a senior clinical trial data quality reviewer. You are reviewing a FLAGGED annotation where the primary annotator and verifiers disagreed.

You will see:
1. The trial's research evidence
2. The primary annotator's answer and reasoning
3. Each verifier's independent answer and reasoning

Your job is to determine the CORRECT answer based solely on the evidence. You must:
- Cite specific evidence for your decision (PMID, database name, or source URL)
- If you cannot find evidence to support a clear answer, respond with "INSUFFICIENT_EVIDENCE" as the value
- Explain WHY the incorrect answer was wrong (what was misinterpreted?)

CRITICAL: You MUST cite at least one specific piece of evidence. If you cannot cite evidence, you CANNOT make a correction. Respond with INSUFFICIENT_EVIDENCE instead.

Respond EXACTLY in this format:
Correct Value: [your answer or INSUFFICIENT_EVIDENCE]
Evidence Citations: [specific sources — PMID:X, database:Y, etc.]
Reflection: [2-3 sentences explaining why the original was wrong and what the evidence shows]"""

REFLECTION_SYSTEM = """You are an annotation quality analyst. An annotation was corrected. Based on the evidence provided, explain in 2-3 sentences:
1. Why the original annotation was incorrect
2. What specific evidence supports the correction
3. What pattern should be watched for in future annotations

Be specific and cite evidence. Do NOT make vague statements."""


class CorrectionLearner:
    """Loop 2: Self-review and human feedback integration."""

    def __init__(self, memory: MemoryStore):
        self._memory = memory

    async def process_human_review(self, review_item: dict,
                                   config_hash: str, git_commit: str) -> Optional[dict]:
        """
        Called when a human submits a review decision.

        For 'overridden' items: generates a reflection and stores a correction.
        For 'approved' items: marks the experience as human-validated.

        Returns the stored correction dict, or None if not applicable.
        """
        status = review_item.get("status", "")
        if status not in ("approved", "overridden"):
            return None

        nct_id = review_item.get("nct_id", "")
        field_name = review_item.get("field_name", "")
        job_id = review_item.get("job_id", "")

        if status == "approved":
            # The original annotation was correct — no correction needed,
            # but this is a positive signal (human confirmed correctness)
            logger.info("EDAM: human approved %s/%s — positive signal", nct_id, field_name)
            return None

        # Status is "overridden" — generate correction
        original_value = review_item.get("original_value", "")
        corrected_value = review_item.get("reviewer_value", "")
        reviewer_note = review_item.get("reviewer_note", "")

        if not corrected_value or corrected_value == original_value:
            return None

        # Build evidence summary from the review item's opinions
        evidence_citations = self._extract_citations_from_review(review_item)

        # Generate a reflection
        reflection = await self._generate_reflection(
            nct_id, field_name, original_value, corrected_value,
            reviewer_note=reviewer_note,
        )

        if not evidence_citations:
            # Use reviewer note as citation if available
            if reviewer_note:
                evidence_citations = [{"source": "human_reviewer", "text": reviewer_note}]
            else:
                logger.warning(
                    "EDAM: human override for %s/%s has no evidence citations — "
                    "storing with reviewer attribution only", nct_id, field_name
                )
                evidence_citations = [{"source": "human_reviewer", "text": f"Overridden to '{corrected_value}'"}]

        corr_id = self._memory.store_correction(
            nct_id=nct_id, field_name=field_name, job_id=job_id,
            original_value=original_value, corrected_value=corrected_value,
            source="human_review", reflection=reflection,
            evidence_citations=evidence_citations,
            config_hash=config_hash, git_commit=git_commit,
            reviewer_note=reviewer_note,
        )

        # Store embedding for similarity search
        embed_text = (
            f"Trial {nct_id}, field {field_name}: "
            f"corrected from '{original_value}' to '{corrected_value}'. "
            f"Reason: {reflection[:300]}"
        )
        try:
            await self._memory.store_embedding("corrections", corr_id, embed_text)
        except Exception as e:
            logger.debug("Embedding failed for correction %d: %s", corr_id, e)

        logger.info(
            "EDAM: stored human correction %s/%s: '%s' → '%s'",
            nct_id, field_name, original_value, corrected_value,
        )
        return {
            "id": corr_id, "nct_id": nct_id, "field_name": field_name,
            "original_value": original_value, "corrected_value": corrected_value,
            "source": "human_review", "reflection": reflection,
        }

    async def self_review_flagged(self, job_id: str,
                                  flagged_results: list[dict],
                                  config_hash: str, git_commit: str) -> list[dict]:
        """
        Run self-review on flagged items using a premium model.

        Returns list of correction dicts that were stored.
        """
        if not SELF_REVIEW_ENABLED:
            return []

        from app.services.ollama_client import ollama_client
        from app.services.config_service import config_service
        config = config_service.get()

        # Select the premium model for self-review
        if config.orchestrator.hardware_profile == "server":
            model = getattr(config.orchestrator, "server_premium_model", "qwen2.5:14b")
        else:
            # On Mac Mini, use the reconciler model (largest available)
            model = "qwen2.5:14b"
            for key, m in config.verification.models.items():
                if m.role == "reconciler":
                    model = m.name
                    break

        corrections = []
        items_reviewed = 0

        for trial_result in flagged_results:
            if items_reviewed >= SELF_REVIEW_MAX_ITEMS:
                break

            nct_id = trial_result.get("nct_id", "")
            verification = trial_result.get("verification") or {}
            if not verification.get("flagged_for_review"):
                continue

            annotations = trial_result.get("annotations", [])
            ann_by_field = {a.get("field_name", ""): a for a in annotations}
            research_results = trial_result.get("research_results", [])

            for field_obj in verification.get("fields", []):
                if field_obj.get("consensus_reached"):
                    continue

                field_name = field_obj.get("field_name", "")
                original_value = field_obj.get("original_value", "")
                ann = ann_by_field.get(field_name, {})

                # Build evidence text for self-review
                evidence_parts = [f"Trial: {nct_id}\nField: {field_name}\n"]
                evidence_parts.append(f"\nPRIMARY ANNOTATION: {original_value}")
                evidence_parts.append(f"Primary reasoning: {ann.get('reasoning', '')[:300]}")
                evidence_parts.append(f"Primary confidence: {ann.get('confidence', 0):.2f}\n")

                evidence_parts.append("VERIFIER OPINIONS:")
                for opinion in field_obj.get("opinions", []):
                    agree_str = "AGREES" if opinion.get("agrees") else "DISAGREES"
                    evidence_parts.append(
                        f"  {opinion.get('model_name', '?')} ({agree_str}): "
                        f"{opinion.get('suggested_value', '?')} — "
                        f"{opinion.get('reasoning', '')[:200]}"
                    )

                evidence_parts.append("\nRESEARCH EVIDENCE:")
                for rr in research_results[:5]:
                    if isinstance(rr, dict):
                        citations = rr.get("citations", [])
                        for c in citations[:3]:
                            evidence_parts.append(
                                f"  [{c.get('source_name', '?')}] "
                                f"{c.get('identifier', '')}: "
                                f"{c.get('snippet', '')[:200]}"
                            )

                evidence_text = "\n".join(evidence_parts)

                # Call premium model for self-review
                try:
                    response = await ollama_client.generate(
                        model=model,
                        prompt=evidence_text,
                        system=SELF_REVIEW_SYSTEM,
                        temperature=config.ollama.temperature,
                    )
                    raw_text = response.get("response", "")
                except Exception as e:
                    logger.warning("Self-review LLM call failed for %s/%s: %s",
                                   nct_id, field_name, e)
                    continue

                items_reviewed += 1

                # Parse self-review response
                correct_value = self._parse_correct_value(raw_text)
                if not correct_value or correct_value == "INSUFFICIENT_EVIDENCE":
                    logger.info("EDAM self-review: %s/%s — insufficient evidence", nct_id, field_name)
                    continue

                if correct_value == original_value:
                    logger.info("EDAM self-review: %s/%s — agrees with original", nct_id, field_name)
                    continue

                evidence_citations = self._parse_evidence_citations(raw_text)
                reflection = self._parse_reflection(raw_text)

                if not self.validate_correction(evidence_citations):
                    logger.info(
                        "EDAM self-review: %s/%s — correction rejected (no valid citations)",
                        nct_id, field_name,
                    )
                    continue

                # Store the self-review correction
                try:
                    corr_id = self._memory.store_correction(
                        nct_id=nct_id, field_name=field_name, job_id=job_id,
                        original_value=original_value, corrected_value=correct_value,
                        source="self_review", reflection=reflection,
                        evidence_citations=evidence_citations,
                        config_hash=config_hash, git_commit=git_commit,
                    )

                    embed_text = (
                        f"Trial {nct_id}, field {field_name}: "
                        f"corrected from '{original_value}' to '{correct_value}'. "
                        f"Reason: {reflection[:300]}"
                    )
                    try:
                        await self._memory.store_embedding("corrections", corr_id, embed_text)
                    except Exception:
                        pass

                    corrections.append({
                        "id": corr_id, "nct_id": nct_id, "field_name": field_name,
                        "original_value": original_value, "corrected_value": correct_value,
                        "source": "self_review", "reflection": reflection,
                    })
                    logger.info(
                        "EDAM self-review: %s/%s corrected '%s' → '%s'",
                        nct_id, field_name, original_value, correct_value,
                    )
                except ValueError as e:
                    logger.warning("EDAM self-review: correction storage failed: %s", e)

        logger.info("EDAM self-review: %d items reviewed, %d corrections stored",
                     items_reviewed, len(corrections))
        return corrections

    async def _generate_reflection(self, nct_id: str, field_name: str,
                                   original_value: str, corrected_value: str,
                                   evidence_text: str = "",
                                   reviewer_note: str = "") -> str:
        """Generate a reflection explaining WHY the original was wrong."""
        prompt = (
            f"Trial: {nct_id}\nField: {field_name}\n"
            f"Original annotation: {original_value}\n"
            f"Corrected to: {corrected_value}\n"
        )
        if reviewer_note:
            prompt += f"Reviewer note: {reviewer_note}\n"
        if evidence_text:
            prompt += f"\nEvidence:\n{evidence_text[:1000]}\n"

        try:
            from app.services.ollama_client import ollama_client
            from app.services.config_service import config_service
            config = config_service.get()

            model = "qwen2.5:14b"
            for key, m in config.verification.models.items():
                if m.role == "reconciler":
                    model = m.name
                    break

            response = await ollama_client.generate(
                model=model, prompt=prompt, system=REFLECTION_SYSTEM,
                temperature=config.ollama.temperature,
            )
            return response.get("response", "")[:500]
        except Exception as e:
            logger.warning("Reflection generation failed: %s", e)
            return f"Corrected from '{original_value}' to '{corrected_value}'. {reviewer_note}"

    @staticmethod
    def validate_correction(evidence_citations: list[dict]) -> bool:
        """Ensure a correction has at least one concrete evidence citation."""
        if not evidence_citations:
            return False
        for c in evidence_citations:
            text = str(c.get("text", c.get("source", "")))
            # Reject generic/empty citations
            if len(text.strip()) < 10:
                continue
            # Must have some identifier or URL
            if any(marker in text.upper() for marker in
                   ["PMID", "PMC", "NCT", "DOI", "HTTP", "UNIPROT", "DRAMP",
                    "DBAASP", "CHEMBL", "PDB", "IUPHAR", "CLINICALTRIALS"]):
                return True
            # Accept if it's substantive text (>50 chars, not just a label)
            if len(text.strip()) > 50:
                return True
        return False

    @staticmethod
    def _extract_citations_from_review(review_item: dict) -> list[dict]:
        """Extract evidence citations from review item opinions."""
        citations = []
        for opinion in review_item.get("opinions", []):
            reasoning = opinion.get("reasoning", "")
            # Look for PMID, PMC, NCT references in reasoning
            import re
            pmids = re.findall(r"PMID[:\s]*(\d+)", reasoning, re.IGNORECASE)
            for pmid in pmids:
                citations.append({"source": "pubmed", "text": f"PMID:{pmid}"})
            ncts = re.findall(r"NCT\d{8}", reasoning)
            for nct in ncts:
                citations.append({"source": "clinicaltrials_gov", "text": nct})
        return citations

    @staticmethod
    def _parse_correct_value(text: str) -> Optional[str]:
        """Extract 'Correct Value: ...' from self-review response."""
        import re
        match = re.search(r"Correct Value:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
        if match:
            value = match.group(1).strip().strip('"').strip("'")
            return value
        return None

    @staticmethod
    def _parse_evidence_citations(text: str) -> list[dict]:
        """Extract evidence citations from self-review response."""
        import re
        match = re.search(r"Evidence Citations?:\s*(.+?)(?:\n(?:Reflection|$))", text,
                          re.IGNORECASE | re.DOTALL)
        if not match:
            return []
        raw = match.group(1).strip()
        # Split on common delimiters
        parts = re.split(r"[,;]\s*", raw)
        citations = []
        for part in parts:
            part = part.strip()
            if len(part) > 5:
                citations.append({"source": "self_review", "text": part})
        return citations

    @staticmethod
    def _parse_reflection(text: str) -> str:
        """Extract 'Reflection: ...' from self-review response."""
        import re
        match = re.search(r"Reflection:\s*(.+?)(?:\n\n|$)", text,
                          re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()[:500]
        return text[:500]
