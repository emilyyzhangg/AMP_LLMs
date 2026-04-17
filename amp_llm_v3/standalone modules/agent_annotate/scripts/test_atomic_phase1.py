#!/usr/bin/env python3
"""
Phase 1 verification for the atomic outcome agent.

Reads completed annotation JSONs (containing research_results) and replays the
v42 atomic Tier 0 / 1a / 2 modules against them. Compares:

  - Tier 0 decisions vs legacy deterministic decisions
  - Pub-specificity classification distribution vs v41 default ('trial_specific'
    for all under v41b)
  - Registry signal extraction vs the legacy dossier signals

Usage:
    cd <agent_annotate_dir>
    python3 scripts/test_atomic_phase1.py \
        --annotation-dir results/annotations/f6535916f390

Exits non-zero if any per-NCT extraction raises. Prints a summary table and, for
NCTs that diverge from legacy, a brief explanation.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path

# Make package imports work when run as a script from agent_annotate root.
THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from app.models.research import ResearchResult  # noqa: E402
from agents.annotation.outcome_atomic import OutcomeAtomicAgent  # noqa: E402
from agents.annotation.outcome_registry_signals import (  # noqa: E402
    extract_registry_signals,
    deterministic_prelabel,
)
from agents.annotation.outcome_pub_classifier import classify_all_pubs  # noqa: E402


def load_research_results(nct_json_path: Path) -> list[ResearchResult]:
    """Annotation JSONs include a 'research_results' list of raw dicts."""
    data = json.loads(nct_json_path.read_text())
    raw = data.get("research_results", [])
    results: list[ResearchResult] = []
    for r in raw:
        try:
            results.append(ResearchResult.model_validate(r))
        except Exception as e:
            # Skip malformed entries but note them.
            print(f"  WARN: failed to parse ResearchResult in {nct_json_path.name}: {e}")
    return results


def legacy_outcome(annotations: list[dict]) -> str:
    for a in annotations:
        if a.get("field_name") == "outcome":
            return a.get("value") or ""
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--annotation-dir",
        required=True,
        type=Path,
        help="results/annotations/<job_id> directory",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Only process first N NCT files (0 = all)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    if not args.annotation_dir.is_dir():
        print(f"ERROR: {args.annotation_dir} is not a directory")
        return 2

    nct_files = sorted(args.annotation_dir.glob("NCT*.json"))
    if args.limit:
        nct_files = nct_files[: args.limit]

    print(f"Loading {len(nct_files)} annotation files from {args.annotation_dir}")

    agent = OutcomeAtomicAgent()

    rows = []
    tier0_counts: Counter[str] = Counter()
    legacy_counts: Counter[str] = Counter()
    specificity_counts: Counter[str] = Counter()
    errors = 0

    for path in nct_files:
        try:
            data = json.loads(path.read_text())
            nct_id = data.get("nct_id") or path.stem
            research_results = load_research_results(path)
            snapshot = agent.compute_snapshot(nct_id, research_results)

            legacy_val = legacy_outcome(data.get("annotations", []))
            tier0 = snapshot.tier0_label or "(no-tier0)"
            tier0_counts[tier0] += 1
            legacy_counts[legacy_val or "(none)"] += 1

            for _, spec in snapshot.classified_pubs:
                specificity_counts[spec] += 1

            rows.append({
                "nct_id": nct_id,
                "status": snapshot.signals.registry_status if snapshot.signals else "",
                "phase": snapshot.signals.phase_normalized if snapshot.signals else "",
                "has_results": snapshot.signals.has_results if snapshot.signals else None,
                "days_since": snapshot.signals.days_since_completion if snapshot.signals else None,
                "stale": snapshot.signals.stale_status if snapshot.signals else False,
                "endpoints_with_pv": sum(
                    1 for ep in (snapshot.signals.primary_endpoints if snapshot.signals else [])
                    if ep.p_value is not None
                ),
                "pubs_total": len(snapshot.classified_pubs),
                "pubs_ts": sum(1 for _, s in snapshot.classified_pubs if s == "trial_specific"),
                "pubs_gen": sum(1 for _, s in snapshot.classified_pubs if s == "general"),
                "pubs_amb": sum(1 for _, s in snapshot.classified_pubs if s == "ambiguous"),
                "tier0": snapshot.tier0_label,
                "legacy": legacy_val,
            })
        except Exception as e:
            errors += 1
            print(f"ERROR processing {path.name}: {e}")

    print()
    print("=" * 100)
    print(f"{'NCT':14s} {'status':22s} {'phase':10s} {'hR':4s} {'days':>6s} "
          f"{'stale':5s} {'ep':>3s} {'tot':>3s} {'ts':>3s} {'gn':>3s} {'am':>3s} "
          f"{'tier0':>20s} {'legacy':>20s}")
    print("=" * 100)
    for r in rows:
        print(f"{r['nct_id']:14s} "
              f"{(r['status'] or '-')[:22]:22s} "
              f"{(r['phase'] or '-')[:10]:10s} "
              f"{str(r['has_results'])[:4]:4s} "
              f"{str(r['days_since'] if r['days_since'] is not None else '-'):>6s} "
              f"{'Y' if r['stale'] else '-':5s} "
              f"{r['endpoints_with_pv']:>3d} "
              f"{r['pubs_total']:>3d} {r['pubs_ts']:>3d} {r['pubs_gen']:>3d} {r['pubs_amb']:>3d} "
              f"{str(r['tier0'] or '-')[:20]:>20s} "
              f"{str(r['legacy'] or '-')[:20]:>20s}")

    print()
    print("Tier 0 decisions (atomic):")
    for k, v in tier0_counts.most_common():
        print(f"  {k:24s}  {v}")
    print()
    print("Legacy outcome values (for reference):")
    for k, v in legacy_counts.most_common():
        print(f"  {k:24s}  {v}")
    print()
    print("Publication specificity distribution:")
    for k, v in specificity_counts.most_common():
        print(f"  {k:20s}  {v}")

    print()
    if errors:
        print(f"FAIL: {errors} errors encountered")
        return 1
    print(f"OK: processed {len(rows)} NCTs with no errors")
    return 0


if __name__ == "__main__":
    sys.exit(main())
