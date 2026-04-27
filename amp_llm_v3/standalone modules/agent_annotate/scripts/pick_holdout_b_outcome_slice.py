#!/usr/bin/env python3
"""Select 30 held-out NCTs (held-out-B) for v42.7.14+ cycle validation.

The original held-out (`scripts/holdout_outcome_slice_v42_7_5.json`) has
been run twice as Job #92 (v42.7.11) and Job #95 (v42.7.13). Per the
standard ML pattern (tune-set → held-out → fresh-held-out for each
iteration), the original 30 are now retired as a tuning set. This
picker generates an independent slice for measuring v42.7.14/15+
without prompt-tuning bleed.

Selection criteria (same as pick_holdout_outcome_slice.py, with
extended exclusions):
  1. Both annotators agree on Outcome.
  2. GT outcome is NOT 'active' (GT/registry divergence trap).
  3. Excluded:
     - All 47 NCTs in outcome_clean_slice_job83.json
     - All 30 NCTs in holdout_outcome_slice_v42_7_5.json
       (the original held-out, retired)
     - Prior-jobs NCTs (#78–#82s)
     - Test-batch NCTs

Stratification (capped at residual supply):
  Same shape as the first held-out (positive-heavy because positive
  recall is still the hardest class). Targets re-balanced based on
  what's available in the residual pool.

Random seed 5252 (different from 4242 used in the first held-out).
"""
from __future__ import annotations

import csv
import json
import random
import sys
from pathlib import Path

CSV_PATH = Path(
    "/Users/amphoraxe/Developer/amphoraxe/dev-llm.amphoraxe.ca/amp_llm_v3/"
    "standalone modules/agent_annotate/docs/human_ground_truth_train_df.csv"
)
JSON_BASE = Path(
    "/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/amp_llm_v3/"
    "standalone modules/agent_annotate/results/json"
)
TEST_BATCH = Path(
    "/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/amp_llm_v3/"
    "standalone modules/agent_annotate/scripts/fast_learning_batch_50.txt"
)
HERE = Path(__file__).resolve().parent
EXISTING_83 = HERE / "outcome_clean_slice_job83.json"
EXISTING_HELDOUT_A = HERE / "holdout_outcome_slice_v42_7_5.json"

PRIOR_JOBS = [
    "c05f049fef32",  # #78
    "fce16457226f",  # #79
    "25cdead94bcc",  # #80
    "c0f32e3ea9b8",  # #81
    "6e835a3e41a1",  # #82s
]


def load_test_batch() -> set[str]:
    if not TEST_BATCH.exists():
        return set()
    return {line.strip().upper() for line in TEST_BATCH.open() if line.strip()}


def load_prior_ncts() -> set[str]:
    used: set[str] = set()
    for jid in PRIOR_JOBS:
        p = JSON_BASE / f"{jid}.json"
        if not p.exists():
            continue
        try:
            d = json.load(p.open())
        except Exception:
            continue
        for t in d.get("trials", []):
            used.add((t.get("nct_id") or "").upper())
    return used


def load_slice(p: Path) -> set[str]:
    if not p.exists():
        return set()
    return {n.upper() for n in json.load(p.open())}


def norm(s: str) -> str:
    return (s or "").strip().lower()


def consensus(a: str, b: str) -> str | None:
    a, b = norm(a), norm(b)
    if a and b:
        return a if a == b else None
    return a or b or None


def main() -> int:
    prior = load_prior_ncts()
    test_batch = load_test_batch()
    slice_83 = load_slice(EXISTING_83)
    slice_a = load_slice(EXISTING_HELDOUT_A)
    print(
        f"Excluding: {len(prior)} prior-jobs + {len(test_batch)} test-batch "
        f"+ {len(slice_83)} #83-slice + {len(slice_a)} held-out-A",
        file=sys.stderr,
    )
    excluded = prior | test_batch | slice_83 | slice_a

    candidates_by_outcome: dict[str, list[str]] = {
        "terminated": [],
        "failed - completed trial": [],
        "positive": [],
        "unknown": [],
    }
    total_seen = 0
    total_active = 0

    with CSV_PATH.open() as f:
        for row in csv.DictReader(f):
            nct = (row["nct_id"] or "").upper().strip()
            if not nct:
                continue
            total_seen += 1
            if nct in excluded:
                continue
            o_cons = consensus(
                row.get("Outcome_ann1", ""), row.get("Outcome_ann2", "")
            )
            if not o_cons:
                continue
            if o_cons == "active":
                total_active += 1
                continue
            if o_cons not in candidates_by_outcome:
                continue
            candidates_by_outcome[o_cons].append(nct)

    print("\nResidual candidate pool (held-out-B):", file=sys.stderr)
    total_candidates = 0
    for k, v in candidates_by_outcome.items():
        print(f"  {k}: {len(v)}", file=sys.stderr)
        total_candidates += len(v)
    print(f"  total: {total_candidates}", file=sys.stderr)
    print(
        f"  ({total_seen} CSV rows seen, {total_active} GT=active excluded)",
        file=sys.stderr,
    )

    random.seed(5252)
    # Re-balance based on residual: positive class still the under-call
    # target so weighted toward it; terminated may be very thin.
    targets = {
        "terminated": 5,
        "failed - completed trial": 0,
        "positive": 16,
        "unknown": 9,
    }
    picks: list[str] = []
    for outcome, target in targets.items():
        pool = candidates_by_outcome[outcome]
        take = min(target, len(pool))
        if take < target:
            print(
                f"  warn: only {take} {outcome} available (wanted {target})",
                file=sys.stderr,
            )
        picks.extend(random.sample(pool, take))
    picks.sort()

    print(f"\nSelected {len(picks)} held-out-B NCTs:", file=sys.stderr)
    for o, t in targets.items():
        pool = candidates_by_outcome[o]
        taken = min(t, len(pool))
        print(f"  {o}: {taken}", file=sys.stderr)

    print(json.dumps(picks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
