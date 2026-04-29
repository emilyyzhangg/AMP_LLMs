#!/usr/bin/env python3
"""Build a 100+ NCT milestone validation slice from retired held-out slices.

Per CONTINUATION_PLAN's production goals: iteration cycles use 20-25 NCT
slices (fast regression detection), milestone validation needs 100+ NCTs
(±10pp CI half-width — usable for accuracy certification).

This picker COMBINES retired held-out slices + the 47-NCT Job #83
baseline slice into one validation set. The composition matters less
than the size — we're measuring "current code's accuracy on a known
GT-scoreable set," not generalization to unseen trials. Once a slice
is retired, its ground truth is fixed; re-running current code against
it produces a stable accuracy datapoint.

Output: JSON list of NCTs to scripts/milestone_validation_v42_7_22.json
(100+ NCTs from A+B+C+D+E ∪ Job #83 47-NCT baseline ∪ slice-F).

Per-cycle exclusion discipline does NOT apply here — this is a
milestone validation against a fixed canonical set, not iteration.

Cost: ~100 NCTs × 10 min/trial ≈ 17h. Overnight run.

Usage:
    python3 scripts/pick_milestone_validation_100.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

SLICES_TO_COMBINE = [
    HERE / "outcome_clean_slice_job83.json",      # 47 NCTs (Job #83 baseline)
    HERE / "holdout_outcome_slice_v42_7_5.json",  # 30 NCTs (held-out-A)
    HERE / "holdout_outcome_slice_b_v42_7_14.json",  # 25 NCTs (held-out-B)
    HERE / "holdout_outcome_slice_c_v42_7_17.json",  # 25 NCTs (held-out-C)
    HERE / "holdout_outcome_slice_d_v42_7_18.json",  # 20 NCTs (held-out-D)
    # held-out-E intentionally excluded — Job #99 currently in flight on it
    # held-out-F intentionally excluded — reserved for next iteration cycle
]


def main() -> int:
    all_ncts: list[str] = []
    seen: set[str] = set()
    for path in SLICES_TO_COMBINE:
        if not path.exists():
            print(f"  WARN: missing {path.name}", file=sys.stderr)
            continue
        try:
            data = json.load(path.open())
        except Exception as e:
            print(f"  ERROR loading {path.name}: {e}", file=sys.stderr)
            continue
        added = 0
        for nct in data:
            n = nct.upper()
            if n not in seen:
                seen.add(n)
                all_ncts.append(n)
                added += 1
        print(f"  + {path.name}: {added} new NCTs ({len(data)} total)", file=sys.stderr)

    all_ncts.sort()
    print(f"\nMilestone validation set: {len(all_ncts)} unique NCTs", file=sys.stderr)
    print(
        f"\nExpected cost: {len(all_ncts)} × ~10 min/trial ≈ "
        f"{int(len(all_ncts) * 10 / 60)}h overnight run",
        file=sys.stderr,
    )
    n = len(all_ncts)
    sqrt_n = n ** 0.5
    # 95% CI half-width = 1.96 × sqrt(p(1-p)/n)
    hw_at_05 = 1.96 * (0.5 * 0.5) ** 0.5 / sqrt_n  # at p=0.5 (worst case)
    hw_at_07 = 1.96 * (0.7 * 0.3) ** 0.5 / sqrt_n  # at p=0.7 (typical accuracy)
    hw_at_09 = 1.96 * (0.9 * 0.1) ** 0.5 / sqrt_n  # at p=0.9 (high-accuracy fields)
    print(
        f"Expected CI half-width on accuracy proportion p (95% confidence):\n"
        f"  at p=0.5: ±{hw_at_05*100:.1f}pp (worst case)\n"
        f"  at p=0.7: ±{hw_at_07*100:.1f}pp (typical for outcome/sequence)\n"
        f"  at p=0.9: ±{hw_at_09*100:.1f}pp (high-accuracy fields)",
        file=sys.stderr,
    )

    print(json.dumps(all_ncts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
