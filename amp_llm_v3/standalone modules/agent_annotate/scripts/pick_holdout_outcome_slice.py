#!/usr/bin/env python3
"""Select 30 held-out NCTs for v42.7 cycle next-round validation.

The v42.7 cycle (Jobs #83/#88/#89) has been validated against the same
47-NCT outcome-clean slice three times. Iterating against a fixed slice
risks overfitting; the next code change should validate on a slice the
agents have NOT seen.

Selection criteria (same shape as pick_outcome_clean_slice.py):
  1. Both annotators agree on Outcome (consensus exists).
  2. GT outcome is NOT 'active' (that bucket is the GT/registry
     divergence trap — see §9 decision-log entry 2026-04-25).
  3. Excluded:
     - All 47 NCTs in outcome_clean_slice_job83.json (the v42.7 trio's
       cumulative test set).
     - Prior-jobs NCTs that pick_outcome_clean_slice.py already excluded
       (#78–#82s).
     - Test-batch NCTs (`fast_learning_batch_50.txt`).

Stratification (capped at residual supply):
  terminated: 7 (only 7 left after excluding prior jobs + #83 slice +
    test batch — accept the cap)
  failed - completed trial: 0 (exhausted; 0 left in residual pool)
  positive: 14 (intentional emphasis — Job #83's confusion matrix
    showed positive recall at 46%, the worst-performing class. Loading
    the held-out set toward the under-called class gives the next cycle
    the most signal on whether prompt/dossier changes lift it.)
  unknown: 9 (regression check; #83 unknown was already 92%)
  = 30 NCTs total

Random seed 4242 (different from the 42 used for the original slice —
gives genuinely independent picks even on the same residual pool).
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
EXISTING_SLICE = Path(__file__).resolve().parent / "outcome_clean_slice_job83.json"

# Same prior-jobs list as pick_outcome_clean_slice.py (#78–#82s).
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
        except Exception as e:
            print(f"  warn: could not parse {jid}.json: {e}", file=sys.stderr)
            continue
        for t in d.get("trials", []):
            used.add((t.get("nct_id") or "").upper())
    return used


def load_existing_slice() -> set[str]:
    if not EXISTING_SLICE.exists():
        return set()
    return {n.upper() for n in json.load(EXISTING_SLICE.open())}


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
    existing = load_existing_slice()
    print(
        f"Excluding: {len(prior)} prior-job NCTs + "
        f"{len(test_batch)} test-batch NCTs + "
        f"{len(existing)} #83-slice NCTs",
        file=sys.stderr,
    )
    excluded = prior | test_batch | existing

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

    print("\nResidual candidate pool:", file=sys.stderr)
    total_candidates = 0
    for k, v in candidates_by_outcome.items():
        print(f"  {k}: {len(v)}", file=sys.stderr)
        total_candidates += len(v)
    print(f"  total: {total_candidates}", file=sys.stderr)
    print(
        f"  ({total_seen} CSV rows seen, {total_active} GT=active excluded)",
        file=sys.stderr,
    )

    random.seed(4242)
    targets = {
        "terminated": 7,
        "failed - completed trial": 0,
        "positive": 14,
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

    print(f"\nSelected {len(picks)} held-out NCTs (stratified):", file=sys.stderr)
    for o, t in targets.items():
        pool = candidates_by_outcome[o]
        taken = min(t, len(pool))
        print(f"  {o}: {taken}", file=sys.stderr)

    print(json.dumps(picks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
