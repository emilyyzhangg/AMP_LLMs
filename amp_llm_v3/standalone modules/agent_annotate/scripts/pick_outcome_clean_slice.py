#!/usr/bin/env python3
"""Select ~50 NCTs from the training CSV with clean outcome signal.

Criteria (all must hold):
  1. Both annotators agree on Outcome (consensus exists)
  2. GT outcome is NOT 'active' when CT.gov status is COMPLETED/UNKNOWN
     (that's the GT/registry divergence bucket — 10 of 20 in the #78/#81 set)
  3. Exclude NCTs already used in Job #78/#79/#80/#81/#82s to get a fresh slice

We can't read CT.gov status from the CSV alone, but we CAN exclude the
divergence bucket indirectly by preferring outcome values with clear
registry-status anchors:
  - 'terminated' — always has a CT.gov TERMINATED status
  - 'failed - completed trial' — has COMPLETED+results posted
  - 'positive' — has COMPLETED+results+positive signal
  - 'unknown' with agent agreement — genuine uncertainty
  - 'active' EXCLUDED from this slice (that's the divergence bucket)
"""
from __future__ import annotations

import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path

CSV_PATH = Path("/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/amp_llm_v3/standalone modules/agent_annotate/docs/human_ground_truth_train_df.csv")
JSON_BASE = Path("/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/amp_llm_v3/standalone modules/agent_annotate/results/json")
TEST_BATCH = Path("/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/amp_llm_v3/standalone modules/agent_annotate/scripts/fast_learning_batch_50.txt")

# Prior-test NCTs (to exclude from fresh slice)
PRIOR_JOBS = ["c05f049fef32", "fce16457226f", "25cdead94bcc", "c0f32e3ea9b8", "6e835a3e41a1"]


def load_test_batch() -> set[str]:
    """NCTs listed in the test batch file are excluded from TRAINING_NCTS at
    the prod API, so we must not pick them either."""
    if not TEST_BATCH.exists():
        return set()
    return {line.strip().upper() for line in TEST_BATCH.open() if line.strip()}


def load_prior_ncts() -> set[str]:
    used: set[str] = set()
    for jid in PRIOR_JOBS:
        p = JSON_BASE / f"{jid}.json"
        if not p.exists():
            continue
        d = json.load(p.open())
        for t in d.get("trials", []):
            used.add(t["nct_id"].upper())
    return used


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
    print(f"Excluding {len(prior)} NCTs from prior jobs + {len(test_batch)} from test batch", file=sys.stderr)
    excluded = prior | test_batch

    # Load CSV, filter to clean-outcome, non-overlap NCTs
    candidates_by_outcome: dict[str, list[str]] = {
        "terminated": [], "failed - completed trial": [],
        "positive": [], "unknown": [],
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
            o_cons = consensus(row.get("Outcome_ann1", ""), row.get("Outcome_ann2", ""))
            if not o_cons:
                continue
            if o_cons == "active":
                total_active += 1
                continue  # skip the divergence bucket
            if o_cons not in candidates_by_outcome:
                continue
            candidates_by_outcome[o_cons].append(nct)

    print(f"\nCandidate pool (excluding prior + excluding GT=active):", file=sys.stderr)
    total_candidates = 0
    for k, v in candidates_by_outcome.items():
        print(f"  {k}: {len(v)}", file=sys.stderr)
        total_candidates += len(v)
    print(f"  total: {total_candidates}", file=sys.stderr)
    print(f"  (compared to {total_seen} CSV rows, {total_active} GT=active excluded)", file=sys.stderr)

    # Stratified pick: aim for balanced outcome distribution
    # Target ~50 total, weighted by available
    random.seed(42)  # deterministic pick
    picks: list[str] = []
    targets = {
        "terminated": 12, "failed - completed trial": 12,
        "positive": 13, "unknown": 13,
    }
    for outcome, target in targets.items():
        pool = candidates_by_outcome[outcome]
        take = min(target, len(pool))
        picks.extend(random.sample(pool, take))
    picks.sort()

    print(f"\nSelected {len(picks)} NCTs (stratified):", file=sys.stderr)
    for o, t in targets.items():
        pool = candidates_by_outcome[o]
        taken = min(t, len(pool))
        print(f"  {o}: {taken}", file=sys.stderr)

    # Emit JSON to stdout (for job submission)
    print(json.dumps(picks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
