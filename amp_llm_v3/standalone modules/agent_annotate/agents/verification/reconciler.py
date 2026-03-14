"""
Reconciliation Agent.

Uses a larger model (qwen2.5:14b) to resolve disagreements between
the primary annotator and verifiers. Sees ALL opinions and evidence,
then makes a final determination or flags for manual review.
"""

import re
import logging

from app.models.verification import ModelOpinion, ConsensusResult

logger = logging.getLogger("agent_annotate.verification.reconciler")

SYSTEM_PROMPT = """You are a senior clinical trial data reconciliation specialist. Multiple AI models have independently analyzed the same trial data and produced DIFFERENT answers for the same field. Your job is to examine all opinions and the underlying evidence, then determine the correct answer.

You will see:
1. The original evidence (research data)
2. Each model's answer and reasoning
3. The field being evaluated and its valid values

Rules:
- Base your decision ONLY on the evidence, not on which model said what
- If the evidence genuinely supports multiple interpretations, choose the most conservative/supported answer
- If the evidence is truly insufficient to determine the answer, respond with "MANUAL_REVIEW" as the value
- Cite the specific evidence that supports your final decision

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
        prompt = self._build_prompt(field_name, consensus_result, research_results)

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
            # Can't reconcile — flag for manual review
            consensus_result.final_value = ""
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
            # Reconciler couldn't decide — manual review
            consensus_result.final_value = ""
            consensus_result.consensus_reached = False
            logger.warning(f"  {field_name}: Reconciler deferred to MANUAL_REVIEW")
        else:
            # Reconciler made a decision
            consensus_result.final_value = final_value
            consensus_result.consensus_reached = True
            logger.info(
                f"  {field_name}: Reconciler resolved to '{final_value}'"
            )

        return consensus_result

    def _build_prompt(
        self,
        field_name: str,
        consensus_result: ConsensusResult,
        research_results: list,
    ) -> str:
        lines = [f"FIELD: {field_name}", f"PRIMARY ANSWER: {consensus_result.original_value}", ""]

        # All model opinions
        lines.append("MODEL OPINIONS:")
        lines.append(f"  Primary annotator: {consensus_result.original_value}")
        for opinion in consensus_result.opinions:
            agree_str = "AGREES" if opinion.agrees else "DISAGREES"
            lines.append(
                f"  {opinion.model_name} ({agree_str}): {opinion.suggested_value}"
            )
            if opinion.reasoning:
                lines.append(f"    Reasoning: {opinion.reasoning[:300]}")
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
