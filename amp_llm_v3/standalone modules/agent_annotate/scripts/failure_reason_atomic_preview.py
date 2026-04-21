#!/usr/bin/env python3
"""
v42 B3 reason_for_failure_atomic shadow-mode preview runner.

Reads a completed atomic_preview/<run-id>/ (outcome) to obtain
outcome_atomic per NCT, then runs the reason_for_failure_atomic agent
against the source annotation data for NCTs whose outcome is Terminated
or Failed - completed trial. Non-failure NCTs are skipped (the agent
short-circuits anyway, but we skip for efficiency).

Usage:
    cd <agent_annotate_dir>
    python3 scripts/failure_reason_atomic_preview.py \\
        --annotation-dir /path/to/results/annotations/<job_id> \\
        --outcome-preview results/atomic_preview/<run-id>/_summary.json \\
        --run-id phase5_fr_94nct
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
import time
from collections import Counter
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from app.config import RESULTS_DIR  # noqa: E402
from app.models.research import ResearchResult  # noqa: E402
from agents.annotation.failure_reason_atomic import FailureReasonAtomicAgent  # noqa: E402


PREVIEW_ROOT = RESULTS_DIR / "atomic_preview_failure_reason"


def _load_research_results(path: Path) -> list[ResearchResult]:
    data = json.loads(path.read_text())
    out: list[ResearchResult] = []
    for r in data.get("research_results", []):
        try:
            out.append(ResearchResult.model_validate(r))
        except Exception as e:
            print(f"  WARN: malformed ResearchResult in {path.name}: {e}")
    return out


def _legacy_value(annotations: list[dict], field: str) -> str:
    for a in annotations:
        if a.get("field_name") == field:
            return a.get("value") or ""
    return ""


def _extract_rule(reasoning: str) -> str:
    m = re.search(r"\[ATOMIC-FR\s+(R\d+|gated)\]", reasoning or "")
    return m.group(1) if m else "?"


async def run(args) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    annotation_dir = Path(args.annotation_dir)
    outcome_preview = Path(args.outcome_preview)
    if not annotation_dir.is_dir():
        print(f"ERROR: {annotation_dir} is not a directory")
        return 2
    if not outcome_preview.is_file():
        print(f"ERROR: {outcome_preview} not found")
        return 2

    outcome_summary = json.loads(outcome_preview.read_text())
    outcome_by_nct = {
        (r.get("nct") or ""): (r.get("atomic") or "")
        for r in outcome_summary.get("per_nct", [])
    }

    run_id = args.run_id or f"preview_fr_{int(time.time())}"
    out_dir = PREVIEW_ROOT / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    nct_files = sorted(annotation_dir.glob("NCT*.json"))
    if args.limit:
        nct_files = nct_files[: args.limit]

    print(f"Failure-reason atomic preview run: {run_id}")
    print(f"  reading from: {annotation_dir}")
    print(f"  outcome ref:  {outcome_preview}")
    print(f"  writing to:   {out_dir}")
    print(f"  NCTs:         {len(nct_files)}")
    print()

    agent = FailureReasonAtomicAgent()

    rule_counts: Counter[str] = Counter()
    legacy_counts: Counter[str] = Counter()
    atomic_counts: Counter[str] = Counter()
    per_nct: list[dict] = []
    gated_out = 0
    errors = 0
    resumed = 0
    t0 = time.monotonic()

    def _write_summary(final: bool) -> None:
        elapsed = round(time.monotonic() - t0, 1)
        summary = {
            "run_id": run_id,
            "annotation_dir": str(annotation_dir),
            "outcome_preview": str(outcome_preview),
            "n_ncts": len(nct_files),
            "gated_out": gated_out,
            "errors": errors,
            "resumed_from_cache": resumed,
            "total_elapsed_sec": elapsed,
            "final": final,
            "rule_counts": dict(rule_counts),
            "atomic_value_counts": dict(atomic_counts),
            "legacy_value_counts": dict(legacy_counts),
            "per_nct": per_nct,
        }
        (out_dir / "_summary.json").write_text(json.dumps(summary, indent=2))

    for i, path in enumerate(nct_files, 1):
        nct = path.stem
        out_path = out_dir / f"{nct}.json"

        if not args.no_resume and out_path.exists():
            try:
                existing = json.loads(out_path.read_text())
                if existing.get("atomic"):  # value may be empty; rule is what matters
                    rule = existing["atomic"].get("rule", "?")
                    rule_counts[rule] += 1
                    atomic_counts[existing["atomic"]["value"] or "(empty)"] += 1
                    legacy_counts[existing.get("legacy_value") or "(none)"] += 1
                    if rule == "gated":
                        gated_out += 1
                    per_nct.append({
                        "nct": nct,
                        "outcome_atomic": existing.get("outcome_atomic"),
                        "legacy": existing.get("legacy_value"),
                        "atomic": existing["atomic"]["value"],
                        "rule": rule,
                        "confidence": existing["atomic"].get("confidence"),
                        "elapsed_sec": existing.get("elapsed_sec", 0.0),
                        "resumed": True,
                    })
                    resumed += 1
                    _write_summary(final=False)
                    continue
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

        t_nct = time.monotonic()
        outcome_atomic = outcome_by_nct.get(nct) or outcome_by_nct.get(nct.upper()) or ""
        try:
            src = json.loads(path.read_text())
            research_results = _load_research_results(path)
            legacy = _legacy_value(src.get("annotations", []), "reason_for_failure")
            annotation = await agent.annotate(
                nct, research_results,
                metadata={"outcome_atomic_result": outcome_atomic},
            )
            rule = _extract_rule(annotation.reasoning or "")
            elapsed = round(time.monotonic() - t_nct, 1)
            if rule == "gated":
                gated_out += 1
            rule_counts[rule] += 1
            legacy_counts[legacy or "(none)"] += 1
            atomic_counts[annotation.value or "(empty)"] += 1
            per_nct.append({
                "nct": nct,
                "outcome_atomic": outcome_atomic,
                "legacy": legacy, "atomic": annotation.value,
                "rule": rule, "confidence": annotation.confidence,
                "elapsed_sec": elapsed,
            })
            record = {
                "run_id": run_id, "nct": nct,
                "outcome_atomic": outcome_atomic,
                "legacy_value": legacy,
                "atomic": {
                    "value": annotation.value,
                    "confidence": annotation.confidence,
                    "rule": rule,
                    "reasoning": annotation.reasoning,
                    "model_name": annotation.model_name,
                },
                "source_annotation_path": str(path),
                "elapsed_sec": elapsed,
            }
            out_path.write_text(json.dumps(record, indent=2))
            diverge = "DIV" if (legacy or "") != (annotation.value or "") else "   "
            print(f"  [{i:3d}/{len(nct_files)}] {nct}  oc={outcome_atomic or '(none)':<12s}  "
                  f"legacy={legacy or '(none)':<26s}  "
                  f"atomic={annotation.value or '(empty)':<26s}  rule={rule:<5s}  "
                  f"t={elapsed:.1f}s  {diverge}")
        except Exception as e:
            errors += 1
            print(f"  [{i:3d}/{len(nct_files)}] {nct}  ERROR: {e}")
        _write_summary(final=False)

    _write_summary(final=True)
    total = round(time.monotonic() - t0, 1)
    print()
    print("=" * 80)
    print(f"FAILURE-REASON ATOMIC PREVIEW SUMMARY  ({total:.1f}s total)")
    print("=" * 80)
    print(f"  NCTs: {len(nct_files)} ({errors} errors, {resumed} resumed, {gated_out} gated)")
    print()
    print("  rule distribution:")
    for r, n in sorted(rule_counts.items()):
        print(f"    {r:<7s}  {n:>3d}")
    print()
    print("  atomic value counts:")
    for v, n in atomic_counts.most_common():
        print(f"    {v:<28s}  {n}")
    print()
    print(f"Saved: {out_dir}/_summary.json")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--annotation-dir", required=True)
    p.add_argument("--outcome-preview", required=True,
                   help="Path to outcome atomic_preview <run-id>/_summary.json")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--run-id", default="")
    p.add_argument("--no-resume", action="store_true")
    args = p.parse_args()
    sys.exit(asyncio.run(run(args)))
