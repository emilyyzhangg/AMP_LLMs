#!/usr/bin/env python3
"""Build the 250-NCT production-gate slice from the 680-NCT training CSV.

Composition (per CONTINUATION_PLAN's path-to-production):
  - 147 NCTs from milestone slice (Job #83 baseline + retired A/B/C/D)
  - 20 NCTs from retired slice-E (Job #99 PASS)
  - 20 NCTs from reserved slice-F (still unused as of cron creation)
  - ~63 NCTs from remaining residual + test-batch reservation that are
    GT-scoreable for outcome (consensus exists, not "active")

Total target: 250 NCTs unique.

Per CONTINUATION_PLAN's Data Discipline rule: ALL 250 NCTs must come
from docs/human_ground_truth_train_df.csv (680 universe).

The 250-NCT production gate is the FINAL accuracy certification:
  - 95% CI half-width ±6pp at p=0.5 (worst case), ±5pp at p=0.7
  - Cost: ~28h overnight
  - Triggered: only when 147-NCT milestone confirms outcome ≥65% AND
    no field regresses below per-field target

Usage:
    python3 scripts/pick_production_gate_250.py
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
TEST_BATCH = Path(
    "/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/amp_llm_v3/"
    "standalone modules/agent_annotate/scripts/fast_learning_batch_50.txt"
)
HERE = Path(__file__).resolve().parent

MILESTONE = HERE / "milestone_validation_v42_7_22.json"
SLICE_E = HERE / "holdout_outcome_slice_e_v42_7_19.json"
SLICE_F = HERE / "holdout_outcome_slice_f_v42_7_23.json"

PRIOR_JOBS = [
    "c05f049fef32", "fce16457226f", "25cdead94bcc",
    "c0f32e3ea9b8", "6e835a3e41a1",
]


def norm(s: str) -> str:
    return (s or "").strip().lower()


def consensus(a: str, b: str) -> str | None:
    a, b = norm(a), norm(b)
    if a and b:
        return a if a == b else None
    return a or b or None


def load_slice(p: Path) -> set[str]:
    if not p.exists():
        return set()
    return {n.upper() for n in json.load(p.open())}


def main() -> int:
    milestone = load_slice(MILESTONE)
    slice_e = load_slice(SLICE_E)
    slice_f = load_slice(SLICE_F)

    # API contract: TRAINING_NCTS = full_csv MINUS test_batch (50 NCTs
    # reserved for concordance measurement). Any slice containing
    # test_batch NCTs will be rejected at submit time. Exclude from
    # BOTH base and candidates.
    test_batch = set()
    if TEST_BATCH.exists():
        test_batch = {l.strip().upper() for l in TEST_BATCH.open() if l.strip()}

    # Start with the union of milestone + E + F, then drop any test_batch
    base = (milestone | slice_e | slice_f) - test_batch
    base_pre_filter = milestone | slice_e | slice_f
    if base != base_pre_filter:
        dropped = base_pre_filter - base
        print(
            f"WARN: dropped {len(dropped)} test_batch NCTs from base "
            f"(milestone or slice-E/F included them)",
            file=sys.stderr,
        )
    print(f"Base composition (milestone + E + F, filtered): {len(base)} unique NCTs", file=sys.stderr)
    print(f"  milestone: {len(milestone)}  slice-E: {len(slice_e)}  slice-F: {len(slice_f)}  (test_batch removed)", file=sys.stderr)

    target = 250
    needed = max(0, target - len(base))
    print(f"\nNeed {needed} more NCTs to reach {target}", file=sys.stderr)

    candidates: list[str] = []
    with CSV_PATH.open() as f:
        for row in csv.DictReader(f):
            nct = (row["nct_id"] or "").upper().strip()
            if not nct or nct in base:
                continue
            # IMPORTANT: exclude test_batch (50 NCTs reserved for
            # concordance measurement). The API's TRAINING_NCTS check
            # subtracts test_batch from the valid universe, so any
            # production-gate slice that includes test_batch NCTs will
            # be rejected at submit time. PRIOR_JOBS NCTs are still OK.
            if nct in test_batch:
                continue
            o = consensus(row.get("Outcome_ann1", ""), row.get("Outcome_ann2", ""))
            if not o or o == "active":
                continue
            candidates.append(nct)

    print(f"\nGT-scoreable candidates outside base: {len(candidates)}", file=sys.stderr)

    if needed == 0:
        # Base is already ≥250
        picks = sorted(base)[:target]
    elif len(candidates) >= needed:
        random.seed(99999)
        extras = random.sample(candidates, needed)
        picks = sorted(base | set(extras))
    else:
        # Pool exhausted — return all candidates + base (best effort)
        print(
            f"  WARN: only {len(candidates)} candidates available — "
            f"slice will be {len(base) + len(candidates)} NCTs (under target {target})",
            file=sys.stderr,
        )
        picks = sorted(base | set(candidates))

    n = len(picks)
    sqrt_n = n ** 0.5
    hw_05 = 1.96 * 0.5 / sqrt_n
    hw_07 = 1.96 * (0.7 * 0.3) ** 0.5 / sqrt_n
    print(f"\nProduction-gate slice: {n} unique NCTs", file=sys.stderr)
    print(
        f"95% CI half-width:\n"
        f"  at p=0.5: ±{hw_05*100:.1f}pp (worst case)\n"
        f"  at p=0.7: ±{hw_07*100:.1f}pp (typical)\n"
        f"Cost estimate: {int(n*10/60)}h ({n} trials × ~10 min each)",
        file=sys.stderr,
    )

    print(json.dumps(picks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
