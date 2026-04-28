#!/usr/bin/env python3
"""Select held-out-D for v42.7.18+ validation.

Per per-cycle held-out separation: each slice is used at most once for
the cycle that produced it. Held-out-A retired post-#95, B post-#96,
C post-#97. Held-out-D is the next slice (single-use).

Random seed 7373 (A/B/C used 4242/5252/6262).
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
EXISTING_A = HERE / "holdout_outcome_slice_v42_7_5.json"
EXISTING_B = HERE / "holdout_outcome_slice_b_v42_7_14.json"
EXISTING_C = HERE / "holdout_outcome_slice_c_v42_7_17.json"

PRIOR_JOBS = [
    "c05f049fef32", "fce16457226f", "25cdead94bcc",
    "c0f32e3ea9b8", "6e835a3e41a1",
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
    slice_a = load_slice(EXISTING_A)
    slice_b = load_slice(EXISTING_B)
    slice_c = load_slice(EXISTING_C)
    print(
        f"Excluding: {len(prior)} prior + {len(test_batch)} test-batch + "
        f"{len(slice_83)} #83 + {len(slice_a)} A + {len(slice_b)} B + "
        f"{len(slice_c)} C",
        file=sys.stderr,
    )
    excluded = prior | test_batch | slice_83 | slice_a | slice_b | slice_c

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

    print("\nResidual candidate pool (held-out-D):", file=sys.stderr)
    total_candidates = 0
    for k, v in candidates_by_outcome.items():
        print(f"  {k}: {len(v)}", file=sys.stderr)
        total_candidates += len(v)
    print(f"  total: {total_candidates}", file=sys.stderr)

    random.seed(7373)
    targets = {
        "terminated": 5,
        "failed - completed trial": 0,
        "positive": 14,
        "unknown": 6,
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

    print(f"\nSelected {len(picks)} held-out-D NCTs:", file=sys.stderr)
    for o, t in targets.items():
        pool = candidates_by_outcome[o]
        taken = min(t, len(pool))
        print(f"  {o}: {taken}", file=sys.stderr)
    print(
        "\nNote: positive+unknown only (terminated/failed pools exhausted "
        "by exclusions). All-positive-bias intentional — outcome positive "
        "recall is the main remaining gap.",
        file=sys.stderr,
    )

    print(json.dumps(picks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
