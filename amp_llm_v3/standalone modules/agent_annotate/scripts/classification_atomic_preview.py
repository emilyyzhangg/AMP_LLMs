#!/usr/bin/env python3
"""
v42 B2 classification_atomic shadow-mode preview runner.

Takes an existing completed annotation directory and replays the v42 atomic
classification pipeline end-to-end against the persisted research_results.

Writes one result JSON per NCT plus _summary.json. Resume-safe (skips NCTs
with valid existing records). See scripts/atomic_preview.py for the outcome
variant.

Usage:
    cd <agent_annotate_dir>
    python3 scripts/classification_atomic_preview.py \\
        --annotation-dir /path/to/results/annotations/<job_id> \\
        --limit 94 \\
        --run-id phase5_classification_94nct
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
from agents.annotation.classification_atomic import ClassificationAtomicAgent  # noqa: E402


PREVIEW_ROOT = RESULTS_DIR / "atomic_preview_classification"


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
    m = re.search(r"\[ATOMIC-CLS\s+(R\d+|TIER0)\]", reasoning or "")
    return m.group(1) if m else "?"


async def run(args) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    annotation_dir = Path(args.annotation_dir)
    if not annotation_dir.is_dir():
        print(f"ERROR: {annotation_dir} is not a directory")
        return 2

    run_id = args.run_id or f"preview_cls_{int(time.time())}"
    out_dir = PREVIEW_ROOT / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    nct_files = sorted(annotation_dir.glob("NCT*.json"))
    if args.limit:
        nct_files = nct_files[: args.limit]

    print(f"Classification atomic preview run: {run_id}")
    print(f"  reading from: {annotation_dir}")
    print(f"  writing to:   {out_dir}")
    print(f"  NCTs:         {len(nct_files)}")
    print()

    agent = ClassificationAtomicAgent()

    rule_counts: Counter[str] = Counter()
    legacy_counts: Counter[str] = Counter()
    atomic_counts: Counter[str] = Counter()
    per_nct: list[dict] = []
    errors = 0
    resumed = 0
    t0 = time.monotonic()

    def _write_summary(final: bool) -> None:
        elapsed = round(time.monotonic() - t0, 1)
        summary = {
            "run_id": run_id,
            "annotation_dir": str(annotation_dir),
            "n_ncts": len(nct_files),
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
                if (existing.get("atomic") or {}).get("value"):
                    rule = existing["atomic"].get("rule", "?")
                    rule_counts[rule] += 1
                    atomic_counts[existing["atomic"]["value"]] += 1
                    legacy_counts[existing.get("legacy_value") or "(none)"] += 1
                    per_nct.append({
                        "nct": nct,
                        "legacy": existing.get("legacy_value"),
                        "atomic": existing["atomic"]["value"],
                        "rule": rule,
                        "confidence": existing["atomic"].get("confidence"),
                        "model": existing["atomic"].get("model_name"),
                        "elapsed_sec": existing.get("elapsed_sec", 0.0),
                        "resumed": True,
                    })
                    resumed += 1
                    print(f"  [{i:3d}/{len(nct_files)}] {nct}  RESUMED "
                          f"atomic={existing['atomic']['value']:<8s}  rule={rule}")
                    _write_summary(final=False)
                    continue
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

        t_nct = time.monotonic()
        try:
            src = json.loads(path.read_text())
            research_results = _load_research_results(path)
            legacy = _legacy_value(src.get("annotations", []), "classification")
            annotation = await agent.annotate(nct, research_results)
            rule = _extract_rule(annotation.reasoning or "")
            elapsed = round(time.monotonic() - t_nct, 1)
            rule_counts[rule] += 1
            legacy_counts[legacy or "(none)"] += 1
            atomic_counts[annotation.value or "(none)"] += 1
            per_nct.append({
                "nct": nct, "legacy": legacy, "atomic": annotation.value,
                "rule": rule, "confidence": annotation.confidence,
                "model": annotation.model_name, "elapsed_sec": elapsed,
            })
            record = {
                "run_id": run_id, "nct": nct,
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
            print(f"  [{i:3d}/{len(nct_files)}] {nct}  legacy={legacy or '(none)':<10s}  "
                  f"atomic={annotation.value or '(none)':<10s}  rule={rule:<5s}  "
                  f"t={elapsed:.1f}s  {diverge}")
        except Exception as e:
            errors += 1
            print(f"  [{i:3d}/{len(nct_files)}] {nct}  ERROR: {e}")
        _write_summary(final=False)

    _write_summary(final=True)
    summary = json.loads((out_dir / "_summary.json").read_text())
    total = round(time.monotonic() - t0, 1)
    print()
    print("=" * 80)
    print(f"CLASSIFICATION ATOMIC PREVIEW SUMMARY  ({total:.1f}s total)")
    print("=" * 80)
    print(f"  NCTs: {len(nct_files)} ({errors} errors, {resumed} resumed)")
    print()
    print("  rule distribution:")
    for r, n in sorted(rule_counts.items()):
        print(f"    {r:<7s}  {n:>3d}")
    print()
    print("  atomic value counts:")
    for v, n in atomic_counts.most_common():
        print(f"    {v:<10s}  {n}")
    print()
    print(f"Saved: {out_dir}/_summary.json")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--annotation-dir", required=True)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--run-id", default="")
    p.add_argument("--no-resume", action="store_true")
    args = p.parse_args()
    sys.exit(asyncio.run(run(args)))
