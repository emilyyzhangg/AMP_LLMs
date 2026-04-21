#!/usr/bin/env python3
"""
v42 atomic shadow-mode preview runner (Phase 4.5).

Takes an existing completed annotation directory (e.g. a v41b job's results),
replays the v42 atomic outcome pipeline end-to-end against the same research
data, and writes one result JSON per NCT plus a consolidated summary. No job
submission, no annotation service dependency — pure offline replay against
already-persisted research_results.

Use this to:
  - Validate the shadow pipeline works at realistic multi-NCT scale before
    committing the full 94-NCT Phase 5 run.
  - Get a first look at atomic-vs-dossier rule distributions and divergences.
  - Spot pipeline issues (malformed JSON, LLM timeouts, cache bugs) on a
    small sample first.

Usage:
    cd <agent_annotate_dir>
    python3 scripts/atomic_preview.py \
        --annotation-dir /path/to/results/annotations/<job_id> \
        --limit 10 \
        [--run-id preview_2026_04_17] \
        [--limit-pubs 0]            # 0 = no cap

Saves to:
    results/atomic_preview/<run-id>/<NCT>.json   — per-NCT atomic record
    results/atomic_preview/<run-id>/_summary.json — aggregate stats
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Optional

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from app.config import RESULTS_DIR  # noqa: E402
from app.models.research import ResearchResult  # noqa: E402
from agents.annotation.outcome_atomic import OutcomeAtomicAgent  # noqa: E402


PREVIEW_ROOT = RESULTS_DIR / "atomic_preview"


def _load_research_results(path: Path) -> list[ResearchResult]:
    data = json.loads(path.read_text())
    out: list[ResearchResult] = []
    for r in data.get("research_results", []):
        try:
            out.append(ResearchResult.model_validate(r))
        except Exception as e:
            print(f"  WARN: malformed ResearchResult in {path.name}: {e}")
    return out


def _legacy_outcome(annotations: list[dict]) -> str:
    for a in annotations:
        if a.get("field_name") == "outcome":
            return a.get("value") or ""
    return ""


def _extract_rule(reasoning: str) -> str:
    if not reasoning:
        return "?"
    for line in reasoning.splitlines():
        if line.startswith("[ATOMIC "):
            # "[ATOMIC R1]" → "R1"
            tok = line.split(" ", 2)[1]
            return tok.rstrip("]")
    return "?"


async def run(args) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    annotation_dir = Path(args.annotation_dir)
    if not annotation_dir.is_dir():
        print(f"ERROR: {annotation_dir} is not a directory")
        return 2

    run_id = args.run_id or f"preview_{int(time.time())}"
    out_dir = PREVIEW_ROOT / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # B1 bake-off: allow per-run override of Tier 1b model without editing YAML.
    if args.atomic_model:
        from app.services.config_service import config_service
        config_service.get()  # force load
        config_service.update({
            "orchestrator": {
                **(config_service._raw.get("orchestrator") or {}),
                "outcome_atomic_model": args.atomic_model,
            }
        })
        print(f"  atomic model override: {args.atomic_model}")

    nct_files = sorted(annotation_dir.glob("NCT*.json"))
    if args.limit:
        nct_files = nct_files[: args.limit]

    print(f"Preview run: {run_id}")
    print(f"  reading from: {annotation_dir}")
    print(f"  writing to:   {out_dir}")
    print(f"  NCTs:         {len(nct_files)}")
    print()

    agent = OutcomeAtomicAgent()

    rule_counts: Counter[str] = Counter()
    legacy_counts: Counter[str] = Counter()
    atomic_counts: Counter[str] = Counter()
    divergences: list[dict] = []
    per_nct: list[dict] = []
    errors = 0
    skipped_resumed = 0
    t0 = time.monotonic()

    def _write_summary(final: bool) -> None:
        elapsed = round(time.monotonic() - t0, 1)
        summary = {
            "run_id": run_id,
            "annotation_dir": str(annotation_dir),
            "n_ncts": len(nct_files),
            "errors": errors,
            "resumed_from_cache": skipped_resumed,
            "total_elapsed_sec": elapsed,
            "final": final,
            "rule_counts": dict(rule_counts),
            "atomic_value_counts": dict(atomic_counts),
            "legacy_value_counts": dict(legacy_counts),
            "divergences": divergences,
            "divergence_rate": round(len(divergences) / max(len(per_nct), 1), 3),
            "per_nct": per_nct,
        }
        (out_dir / "_summary.json").write_text(json.dumps(summary, indent=2))

    for i, path in enumerate(nct_files, 1):
        nct = path.stem
        out_path = out_dir / f"{nct}.json"

        # A3 resume: skip NCTs that already have a valid atomic record.
        if not args.no_resume and out_path.exists():
            try:
                existing = json.loads(out_path.read_text())
                if (existing.get("atomic") or {}).get("value"):
                    legacy_existing = existing.get("legacy_outcome") or ""
                    atomic_existing = existing["atomic"]["value"]
                    rule_existing = existing["atomic"].get("rule", "?")
                    diverges = (legacy_existing or "") != (atomic_existing or "")
                    rule_counts[rule_existing] += 1
                    legacy_counts[legacy_existing or "(none)"] += 1
                    atomic_counts[atomic_existing or "(none)"] += 1
                    if diverges:
                        divergences.append({
                            "nct": nct, "legacy": legacy_existing,
                            "atomic": atomic_existing, "rule": rule_existing,
                        })
                    per_nct.append({
                        "nct": nct, "legacy": legacy_existing,
                        "atomic": atomic_existing, "rule": rule_existing,
                        "confidence": existing["atomic"].get("confidence"),
                        "model": existing["atomic"].get("model_name"),
                        "elapsed_sec": existing.get("elapsed_sec", 0.0),
                        "diverges": diverges, "resumed": True,
                    })
                    skipped_resumed += 1
                    print(f"  [{i:3d}/{len(nct_files)}] {nct}  RESUMED "
                          f"legacy={legacy_existing or '(none)':<25s}  "
                          f"atomic={atomic_existing:<25s}  rule={rule_existing}")
                    _write_summary(final=False)
                    continue
            except (json.JSONDecodeError, KeyError, TypeError):
                pass  # fall through and recompute

        t_nct = time.monotonic()
        try:
            src = json.loads(path.read_text())
            research_results = _load_research_results(path)
            if args.limit_pubs:
                for r in research_results:
                    if r.agent_name == "literature" and r.citations:
                        r.citations = r.citations[: args.limit_pubs]

            legacy = _legacy_outcome(src.get("annotations", []))
            annotation = await agent.annotate(nct, research_results)
            rule = _extract_rule(annotation.reasoning or "")
            elapsed = round(time.monotonic() - t_nct, 1)

            rule_counts[rule] += 1
            legacy_counts[legacy or "(none)"] += 1
            atomic_counts[annotation.value or "(none)"] += 1
            diverges = (legacy or "") != (annotation.value or "")
            if diverges:
                divergences.append({
                    "nct": nct, "legacy": legacy, "atomic": annotation.value, "rule": rule,
                })
            per_nct.append({
                "nct": nct, "legacy": legacy, "atomic": annotation.value,
                "rule": rule, "confidence": annotation.confidence,
                "model": annotation.model_name,
                "elapsed_sec": elapsed, "diverges": diverges,
            })

            record = {
                "run_id": run_id, "nct": nct,
                "legacy_outcome": legacy,
                "atomic": {
                    "value": annotation.value,
                    "confidence": annotation.confidence,
                    "rule": rule,
                    "reasoning": annotation.reasoning,
                    "model_name": annotation.model_name,
                    "skip_verification": annotation.skip_verification,
                },
                "source_annotation_path": str(path),
                "elapsed_sec": elapsed,
            }
            out_path.write_text(json.dumps(record, indent=2))

            print(f"  [{i:3d}/{len(nct_files)}] {nct}  legacy={legacy or '(none)':<25s}  "
                  f"atomic={annotation.value or '(none)':<25s}  rule={rule:<6s}  "
                  f"t={elapsed:.1f}s  {'DIV' if diverges else '   '}")
        except Exception as e:
            errors += 1
            print(f"  [{i:3d}/{len(nct_files)}] {nct}  ERROR: {e}")

        # A4: flush summary after every NCT so mid-run kill yields readable output.
        _write_summary(final=False)

    total_elapsed = round(time.monotonic() - t0, 1)
    _write_summary(final=True)
    summary = json.loads((out_dir / "_summary.json").read_text())

    print()
    print("=" * 80)
    print(f"PREVIEW SUMMARY  ({total_elapsed:.1f}s total)")
    print("=" * 80)
    print(f"  NCTs processed:   {len(nct_files)} ({errors} errors)")
    print(f"  atomic wall time: {total_elapsed / max(len(nct_files), 1):.1f}s/NCT avg")
    print()
    print("  rule distribution:")
    for rule, n in sorted(rule_counts.items()):
        print(f"    {rule:<7s}  {n:>4d}")
    print()
    print("  atomic vs legacy outcome:")
    print(f"    divergences:  {len(divergences)} / {len(nct_files) - errors} "
          f"({summary['divergence_rate']:.1%})")
    if divergences:
        for d in divergences[:20]:
            print(f"    - {d['nct']}: legacy={d['legacy'] or '(none)':<25s} "
                  f"atomic={d['atomic']:<25s} rule={d['rule']}")
        if len(divergences) > 20:
            print(f"    - (+{len(divergences) - 20} more)")
    print()
    print(f"Saved: {out_dir}/_summary.json (plus one file per NCT)")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--annotation-dir", required=True,
                   help="Source job's annotations dir (contains NCT*.json)")
    p.add_argument("--limit", type=int, default=10,
                   help="Only process first N NCT files (0 = all)")
    p.add_argument("--limit-pubs", type=int, default=0,
                   help="Cap literature citations per NCT (0 = no cap)")
    p.add_argument("--run-id", default="",
                   help="Output dir name (default preview_<unix-ts>)")
    p.add_argument("--no-resume", action="store_true",
                   help="Recompute even if <NCT>.json already exists in out dir")
    p.add_argument("--atomic-model", default="",
                   help="Override Tier 1b model at runtime (e.g. qwen3:14b). "
                        "Does not modify default_config.yaml.")
    args = p.parse_args()
    sys.exit(asyncio.run(run(args)))
