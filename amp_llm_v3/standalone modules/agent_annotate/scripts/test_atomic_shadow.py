#!/usr/bin/env python3
"""
Phase 4 shadow-mode integration test for the v42 atomic outcome pipeline.

Loads completed annotation JSONs and runs OutcomeAtomicAgent.annotate()
end-to-end against the real ollama_client. Unlike scripts/test_atomic_phase2_live.py
this covers the *entire* atomic stack: Tier 0 → Tier 1a → Tier 1b per pub →
Tier 3 aggregator. Prints each NCT's legacy outcome next to the atomic rule +
value so divergences are visible immediately.

Usage:
    cd <agent_annotate_dir>
    python3 scripts/test_atomic_shadow.py \
        --annotation-dir /path/to/results/annotations/<job_id> \
        --nct NCT01661192 NCT02660008 NCT03559413 \
        [--limit-pubs 5]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from app.models.research import ResearchResult  # noqa: E402
from agents.annotation.outcome_atomic import OutcomeAtomicAgent  # noqa: E402


def load_research_results(path: Path) -> list[ResearchResult]:
    data = json.loads(path.read_text())
    out: list[ResearchResult] = []
    for r in data.get("research_results", []):
        try:
            out.append(ResearchResult.model_validate(r))
        except Exception as e:
            print(f"  WARN: skipping malformed ResearchResult in {path.name}: {e}")
    return out


def legacy_outcome_value(annotations: list[dict]) -> str:
    for a in annotations:
        if a.get("field_name") == "outcome":
            return a.get("value") or ""
    return ""


async def run(args) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    agent = OutcomeAtomicAgent()

    results = []
    diverges = 0

    for nct in args.nct:
        path = Path(args.annotation_dir) / f"{nct}.json"
        if not path.exists():
            print(f"\n=== {nct} === NOT FOUND at {path}")
            continue

        print(f"\n========== {nct} ==========")
        data = json.loads(path.read_text())
        research_results = load_research_results(path)
        legacy = legacy_outcome_value(data.get("annotations", []))

        # Optional pub limit — snip research_results' literature citations.
        if args.limit_pubs:
            for r in research_results:
                if r.agent_name == "literature" and r.citations:
                    r.citations = r.citations[: args.limit_pubs]

        annotation = await agent.annotate(nct, research_results)

        rule = "unknown"
        for line in (annotation.reasoning or "").splitlines():
            if line.startswith("[ATOMIC "):
                rule = line.split(" ", 2)[1].rstrip("]")
                break

        diverged = (legacy or "") != (annotation.value or "")
        if diverged:
            diverges += 1

        print(f"  legacy outcome: {legacy or '(none)'}")
        print(f"  atomic verdict: {annotation.value}   rule={rule}   "
              f"conf={annotation.confidence:.2f}   "
              f"diverges={'YES' if diverged else 'no'}")
        print(f"  model: {annotation.model_name}")
        # Print the compact head of reasoning
        for line in (annotation.reasoning or "").splitlines()[:4]:
            print(f"    {line}")

        results.append({
            "nct": nct, "legacy": legacy, "atomic": annotation.value, "rule": rule,
            "diverges": diverged,
        })

    print("\n========= shadow-mode summary =========")
    print(f"  NCTs processed: {len(results)}")
    print(f"  divergences vs legacy: {diverges}")
    print(f"  {'NCT':<14}  {'legacy':<30}  {'atomic':<30}  rule")
    for r in results:
        print(f"  {r['nct']:<14}  {r['legacy']:<30}  {r['atomic']:<30}  {r['rule']}")

    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--annotation-dir", required=True)
    p.add_argument("--nct", nargs="+", required=True)
    p.add_argument("--limit-pubs", type=int, default=0,
                   help="Cap literature citations per NCT (0 = no cap)")
    args = p.parse_args()
    sys.exit(asyncio.run(run(args)))
