"""
Reconciliation Agent.

Uses a larger model (qwen2.5:14b) to resolve disagreements between
the primary annotator and verifiers. Sees ALL opinions and evidence,
then makes a final determination or flags for manual review.


When the reconciler defers to MANUAL_REVIEW, a majority-vote fallback
populates final_value so the review queue has a pre-filled best guess.
"""

import re
import logging
from collections import Counter

from app.models.verification import ModelOpinion, ConsensusResult
from agents.verification.consensus import _normalize

logger = logging.getLogger("agent_annotate.verification.reconciler")

SYSTEM_PROMPT = """You are a senior clinical trial data reconciliation specialist. Multiple AI models have independently analyzed the same trial data and produced DIFFERENT answers for the same field. Your job is to examine all opinions and the underlying evidence, then determine the correct answer.

You will see:
1. The original evidence (research data)
2. Each model's answer and reasoning
3. The field being evaluated and its valid values
4. The primary annotator's confidence score (0-1)

Rules:
- Base your decision ONLY on the evidence, not on which model said what
- If the evidence genuinely supports multiple interpretations, choose the most conservative/supported answer
- If the evidence is truly insufficient to determine the answer, respond with "MANUAL_REVIEW" as the value
- Cite the specific evidence that supports your final decision
- IMPORTANT: If the primary annotator has HIGH confidence (>0.85) and cites specific published evidence, and the verifiers only show baseline reasoning without citing contradicting evidence, the primary annotator's answer should be preferred.
- VERIFIER MAJORITY: If 2 or more verifiers AGREE with each other but DISAGREE with the primary annotator, and the verifiers cite specific database facts or structured evidence in their reasoning, give strong weight to the verifier majority. The verifiers are independent blind reviewers — when multiple agree on the same answer with evidence-based reasoning, that is a strong signal.
- For UniProt entries: the MATURE form length is what matters for peptide classification — NOT the precursor length. The precursor includes signal peptides and propeptides that are cleaved off before the drug is administered.

Respond EXACTLY in this format:
Final Answer: [your answer OR "MANUAL_REVIEW"]
Evidence: [cite the specific data supporting your decision]
Reasoning: [explain why you chose this answer over the alternatives]"""


class ReconciliationAgent:
    """Resolves disagreements using a larger, more capable model."""

    async def reconcile(
        self,
        field_name: str,
        consensus_result: ConsensusResult,
        research_results: list,
        reconciler_model: str,
        primary_confidence: float = 0.0,
    ) -> ConsensusResult:
        """
        Attempt to resolve a disagreement between primary and verifiers.

        Args:
            field_name: The annotation field in dispute
            consensus_result: The failed consensus result with all opinions
            research_results: Raw research data for evidence
            reconciler_model: Ollama model name for the reconciler (e.g., qwen2.5:14b)

        Returns:
            Updated ConsensusResult with reconciler's decision
        """
        # Build the reconciliation prompt with all opinions
        prompt = self._build_prompt(field_name, consensus_result, research_results,
                                    primary_confidence=primary_confidence)

        from app.services.ollama_client import ollama_client
        from app.services.config_service import config_service
        config = config_service.get()

        try:
            response = await ollama_client.generate(
                model=reconciler_model,
                prompt=prompt,
                system=SYSTEM_PROMPT,
                temperature=config.ollama.temperature,
            )
            raw_text = response.get("response", "")
        except Exception as e:
            logger.error(f"Reconciler failed for {field_name}: {e}")
            # Can't reconcile — use majority vote as fallback
            fallback = self._majority_vote(consensus_result)
            consensus_result.final_value = fallback
            consensus_result.reconciler_used = True
            consensus_result.reconciler_reasoning = f"Reconciliation failed: {e}"
            consensus_result.flag_reason = "reconciler_error"
            return consensus_result

        # Parse reconciler's answer
        final_value = self._parse_final_answer(raw_text)
        reasoning = self._parse_reasoning(raw_text)

        consensus_result.reconciler_used = True
        consensus_result.reconciler_reasoning = reasoning

        if final_value == "MANUAL_REVIEW" or not final_value:
            # Reconciler couldn't decide — use majority vote as fallback
            fallback = self._majority_vote(consensus_result)
            consensus_result.final_value = fallback
            consensus_result.consensus_reached = False
            consensus_result.flag_reason = "reconciler_deferred"
            logger.warning(
                f"  {field_name}: Reconciler deferred to MANUAL_REVIEW, "
                f"majority-vote fallback='{fallback}'"
            )
        else:
            # Reconciler made a decision — normalize to canonical value
            normalized = _normalize(final_value, field_name)
            # Map normalized back to canonical casing
            from agents.verification.verifier import FIELD_PROMPTS
            field_config = FIELD_PROMPTS.get(field_name, {})
            valid_values = field_config.get("valid_values", [])
            canonical = final_value  # default to raw
            for vv in valid_values:
                if vv.lower() == normalized:
                    canonical = vv
                    break
            # Handle empty string for reason_for_failure
            if normalized == "" and "" in valid_values:
                canonical = ""
            consensus_result.final_value = canonical
            consensus_result.consensus_reached = True
            logger.info(
                f"  {field_name}: Reconciler resolved to '{canonical}'"
            )

        return consensus_result

    def _build_prompt(
        self,
        field_name: str,
        consensus_result: ConsensusResult,
        research_results: list,
        primary_confidence: float = 0.0,
    ) -> str:
        lines = [f"FIELD: {field_name}", f"PRIMARY ANSWER: {consensus_result.original_value}"]
        if primary_confidence > 0:
            lines.append(f"PRIMARY CONFIDENCE: {primary_confidence:.2f}")
        lines.append("")

        # All model opinions
        lines.append("MODEL OPINIONS:")
        lines.append(f"  Primary annotator: {consensus_result.original_value}")
        # v27e: Count verifier votes to flag majority disagreement
        dissenting_values: dict[str, int] = {}
        for opinion in consensus_result.opinions:
            agree_str = "AGREES" if opinion.agrees else "DISAGREES"
            lines.append(
                f"  {opinion.model_name} ({agree_str}): {opinion.suggested_value}"
            )
            if opinion.reasoning:
                lines.append(f"    Reasoning: {opinion.reasoning[:300]}")
            if not opinion.agrees and opinion.suggested_value is not None:
                sv = str(opinion.suggested_value).strip()
                dissenting_values[sv] = dissenting_values.get(sv, 0) + 1
        # Flag when 2+ verifiers agree on a different answer
        for val, count in dissenting_values.items():
            if count >= 2:
                lines.append(
                    f"\n  ** NOTE: {count} of {len(consensus_result.opinions)} "
                    f"independent verifiers agree on '{val}' — this is a "
                    f"verifier majority that disagrees with the primary. **"
                )
        lines.append("")

        # Raw evidence
        lines.append("EVIDENCE:")
        for result in research_results:
            if hasattr(result, "error") and result.error:
                continue
            citations = getattr(result, "citations", [])
            for citation in citations[:8]:
                lines.append(
                    f"  [{citation.source_name}] {citation.identifier or ''}: "
                    f"{citation.snippet[:200]}"
                )
        lines.append("")
        lines.append("Based on the evidence above, what is the correct answer?")

        return "\n".join(lines)

    @staticmethod
    def _majority_vote(consensus_result: ConsensusResult) -> str:
        """Pick the most common value across primary + all verifiers.

        Uses normalized values for counting to prevent format differences
        (e.g., "IV" vs "Intravenous") from splitting the vote.
        """
        from agents.verification.consensus import _normalize

        raw_votes: list[str] = []
        # v18: Always include primary vote for reason_for_failure, even when empty.
        # Previously empty strings were silently dropped (falsy), meaning the
        # primary's deliberate "no failure" assessment never counted in the vote.
        # Guard against None: None means "no value returned", not "empty string".
        ov = consensus_result.original_value
        if ov is not None and (ov or consensus_result.field_name == "reason_for_failure"):
            raw_votes.append(ov)
        for opinion in consensus_result.opinions:
            sv = opinion.suggested_value
            if sv is not None and (sv or consensus_result.field_name == "reason_for_failure"):
                raw_votes.append(sv)
        if not raw_votes:
            return ""
        # Normalize for counting, return the first raw value matching the winner
        norm_to_raw: dict[str, str] = {}
        norm_votes: list[str] = []
        for rv in raw_votes:
            nv = _normalize(rv, consensus_result.field_name)
            norm_votes.append(nv)
            if nv not in norm_to_raw:
                norm_to_raw[nv] = rv
        counter = Counter(norm_votes)
        winner_norm, _ = counter.most_common(1)[0]
        return norm_to_raw[winner_norm]

    def _parse_final_answer(self, text: str) -> str:
        match = re.search(r"Final Answer:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
        if match:
            value = match.group(1).strip().strip('"').strip("'")
            if value.upper() == "MANUAL_REVIEW":
                return "MANUAL_REVIEW"
            return value
        return ""

    def _parse_reasoning(self, text: str) -> str:
        match = re.search(r"Reasoning:\s*(.+?)(?:\n\n|$)", text, re.DOTALL)
        if match:
            return match.group(1).strip()[:500]
        return text[:500]
