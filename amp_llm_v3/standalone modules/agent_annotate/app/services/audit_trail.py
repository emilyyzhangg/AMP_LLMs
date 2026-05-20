"""
Per-trial LLM audit trail.

Why this exists
---------------
Until now the only thing persisted about an annotation decision was the *parsed*
reasoning string on each FieldAnnotation. The exact prompt the reasoning model
was shown (the dossier + full research evidence) and its raw, unparsed reply were
local variables thrown away after each call. That made it impossible to answer
"why did the model decide X for this trial?" after the fact, and impossible to
tell whether a bad annotation came from bad *evidence* or bad *reasoning*.

This module captures, for every LLM call made while annotating a trial, the full
input (system + prompt) and the full output, attributed to the right trial / field
/ stage, and renders a human-readable Markdown audit document per trial.

Design
------
- Single chokepoint: ``OllamaAnnotationClient.generate`` (the one place every
  annotation, verification and reconciliation call funnels through) calls
  ``audit_recorder.record(...)`` after each successful generation.
- A ``contextvars.ContextVar`` carries the current ``(nct_id, field, stage)`` so
  records attribute themselves without threading audit args through every agent.
  The orchestrator sets this context at NCT / field boundaries.
- When a trial is finalized, the orchestrator pops that trial's records and writes
  ``<nct_id>.audit.md`` next to the annotation JSON.

Everything here is exception-safe: auditing must never break annotation. If a
record or render fails it is logged at debug level and dropped.
"""

from __future__ import annotations

import contextvars
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

logger = logging.getLogger("agent_annotate.audit")

# Current audit context for the running task. A dict so we can layer
# nct_id (set per-trial) and field/stage (set per-call) independently.
_ctx: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar(
    "audit_ctx", default=None
)


@dataclass
class LLMCall:
    """One captured LLM input/output pair."""

    nct_id: str
    field: str
    stage: str
    model: str
    temperature: float
    system: str
    prompt: str
    response: str
    prompt_chars: int
    response_chars: int
    timestamp: str


class AuditRecorder:
    """Collects LLM call records keyed by NCT and renders Markdown audit docs."""

    def __init__(self) -> None:
        self._enabled = True
        self._calls: dict[str, list[LLMCall]] = {}

    # -- toggling -----------------------------------------------------------
    def set_enabled(self, value: bool) -> None:
        self._enabled = bool(value)

    def is_enabled(self) -> bool:
        return self._enabled

    # -- context ------------------------------------------------------------
    def set_context(
        self,
        nct_id: Optional[str] = None,
        field: Optional[str] = None,
        stage: Optional[str] = None,
    ):
        """Layer values onto the current audit context. Returns a reset token.

        Only the keys passed are changed; everything else is inherited so that
        setting the field inside ``annotate_field`` keeps the trial's nct_id.
        """
        cur = _ctx.get() or {}
        new = dict(cur)
        if nct_id is not None:
            new["nct_id"] = nct_id
        if field is not None:
            new["field"] = field
        if stage is not None:
            new["stage"] = stage
        return _ctx.set(new)

    def reset(self, token) -> None:
        try:
            _ctx.reset(token)
        except Exception:  # token from a different context — best-effort
            pass

    # -- recording ----------------------------------------------------------
    def record(
        self,
        model: str,
        prompt: str,
        response: str,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> None:
        """Capture one LLM call. Never raises."""
        if not self._enabled:
            return
        try:
            ctx = _ctx.get() or {}
            nct = ctx.get("nct_id")
            # Only capture calls bound to a trial. Batched cross-trial
            # verification runs without a per-trial context; skipping those
            # keeps the buffer from growing unbounded and keeps each trial's
            # document focused on its own annotation reasoning.
            if not nct:
                return
            call = LLMCall(
                nct_id=nct,
                field=ctx.get("field") or "",
                stage=ctx.get("stage") or "annotation",
                model=model or "",
                temperature=(
                    float(temperature) if temperature is not None else -1.0
                ),
                system=system or "",
                prompt=prompt or "",
                response=response or "",
                prompt_chars=len(prompt or ""),
                response_chars=len(response or ""),
                timestamp=datetime.utcnow().isoformat(),
            )
            self._calls.setdefault(nct, []).append(call)
        except Exception as e:  # auditing must never break annotation
            logger.debug("audit record failed: %s", e)

    def pop_calls(self, nct_id: str) -> list[LLMCall]:
        """Return and clear the records for one trial."""
        return self._calls.pop(nct_id, [])

    def discard(self, nct_id: str) -> None:
        self._calls.pop(nct_id, None)

    # -- rendering ----------------------------------------------------------
    def render_markdown(
        self,
        nct_id: str,
        trial_output: Optional[dict] = None,
        calls: Optional[list[LLMCall]] = None,
    ) -> str:
        """Render a per-trial audit document. Never raises (returns best-effort)."""
        try:
            return self._render(nct_id, trial_output or {}, calls or [])
        except Exception as e:
            logger.debug("audit render failed for %s: %s", nct_id, e)
            return f"# Audit trail for {nct_id}\n\n_(render error: {e})_\n"

    @staticmethod
    def _fence(text: str) -> str:
        """Wrap text in a fenced block, escaping any backtick fences inside."""
        safe = (text or "").replace("```", "ʼʼʼ")
        return f"```\n{safe}\n```"

    def _render(self, nct_id: str, trial_output: dict, calls: list[LLMCall]) -> str:
        md = trial_output.get("metadata", {}) if isinstance(trial_output, dict) else {}
        title = md.get("title") or md.get("brief_title") or ""
        status = md.get("overall_status") or md.get("status") or ""

        lines: list[str] = []
        lines.append(f"# LLM audit trail — {nct_id}")
        lines.append("")
        lines.append(f"- Generated: {datetime.utcnow().isoformat()}Z")
        if title:
            lines.append(f"- Title: {title}")
        if status:
            lines.append(f"- Registry status: {status}")
        lines.append(f"- LLM calls captured: {len(calls)}")
        lines.append("")

        # Final annotations summary table
        anns = trial_output.get("annotations", []) if isinstance(trial_output, dict) else []
        if anns:
            lines.append("## Final annotations")
            lines.append("")
            lines.append("| Field | Value | Confidence | Model |")
            lines.append("|---|---|---|---|")
            for a in anns:
                if not isinstance(a, dict):
                    continue
                conf = a.get("confidence")
                conf_s = f"{conf:.2f}" if isinstance(conf, (int, float)) else "—"
                lines.append(
                    f"| {a.get('field_name','')} | {a.get('value','')} | "
                    f"{conf_s} | {a.get('model_name','') or '—'} |"
                )
            lines.append("")

        # Per-call input/output, in capture order
        lines.append("## LLM calls (input → output)")
        lines.append("")
        if not calls:
            lines.append(
                "_No LLM calls were captured for this trial — every field was "
                "decided by deterministic logic (no model was invoked)._"
            )
            lines.append("")
        for i, c in enumerate(calls, 1):
            label = c.field or c.stage or "call"
            temp = "" if c.temperature < 0 else f", temp={c.temperature:g}"
            lines.append(
                f"### {i}. {label} — `{c.model}`{temp} "
                f"({c.stage})"
            )
            lines.append("")
            lines.append(
                f"_input: {c.prompt_chars:,} chars · output: "
                f"{c.response_chars:,} chars · {c.timestamp}Z_"
            )
            lines.append("")
            if c.system:
                lines.append("**System**")
                lines.append("")
                lines.append(self._fence(c.system))
                lines.append("")
            lines.append("**Input (prompt + evidence)**")
            lines.append("")
            lines.append(self._fence(c.prompt))
            lines.append("")
            lines.append("**Output (raw model reply)**")
            lines.append("")
            lines.append(self._fence(c.response))
            lines.append("")

        return "\n".join(lines)


# Module-level singleton — imported by ollama_client and the orchestrator.
audit_recorder = AuditRecorder()
