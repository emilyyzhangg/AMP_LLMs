#!/usr/bin/env python3
"""Build the full-corpus slices for end-state annotation.

After the production gate passes (Job #101), the user wants to
"annotate everything" — run the validated agent on the full 630-NCT
training universe (680 in CSV minus 50-NCT test_batch reservation).

API constraint: MAX_BATCH_SIZE=500 NCTs per job (app/routers/jobs.py:24).
So 630 NCTs → split into 2 batches of ~315 each.

Output:
  scripts/full_corpus_batch_1.json (NCT01... range, ~315 NCTs)
  scripts/full_corpus_batch_2.json (NCT04... range, ~315 NCTs)

Cost estimate: ~10-16 min/trial on prod (Mac Mini, qwen3:14b). Total
105-168 hours = 4-7 days for full corpus. Both batches run sequentially
on prod (only one job at a time).

Usage:
    python3 scripts/build_full_corpus_slices.py
"""
from __future__ import annotations

import csv
import json
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

BATCH_SIZE = 315  # half of 630, well under API's 500 limit


def main() -> int:
    test_batch = set()
    if TEST_BATCH.exists():
        test_batch = {l.strip().upper() for l in TEST_BATCH.open() if l.strip()}
    print(f"Test_batch reservation: {len(test_batch)} NCTs (excluded by API)", file=sys.stderr)

    all_ncts: list[str] = []
    with CSV_PATH.open() as f:
        for row in csv.DictReader(f):
            nct = (row.get("nct_id") or "").upper().strip()
            if not nct:
                continue
            if nct in test_batch:
                continue
            all_ncts.append(nct)

    # Sort for stable batch composition
    all_ncts = sorted(set(all_ncts))
    print(f"Full corpus (training_csv minus test_batch): {len(all_ncts)} NCTs", file=sys.stderr)

    # Split into batches
    batches: list[list[str]] = []
    for i in range(0, len(all_ncts), BATCH_SIZE):
        batches.append(all_ncts[i:i + BATCH_SIZE])

    for i, batch in enumerate(batches, 1):
        out_path = HERE / f"full_corpus_batch_{i}.json"
        out_path.write_text(json.dumps(batch))
        first = batch[0] if batch else "-"
        last = batch[-1] if batch else "-"
        print(
            f"  batch {i}: {len(batch)} NCTs → {out_path.name} "
            f"({first} to {last})",
            file=sys.stderr,
        )

    total_minutes_lo = len(all_ncts) * 10
    total_minutes_hi = len(all_ncts) * 16
    print(
        f"\nCost estimate: {total_minutes_lo // 60}-{total_minutes_hi // 60}h "
        f"({total_minutes_lo // 60 // 24}-{total_minutes_hi // 60 // 24} days) "
        f"on prod (Mac Mini, qwen3:14b, sequential)",
        file=sys.stderr,
    )

    print(json.dumps({
        "total_ncts": len(all_ncts),
        "batches": len(batches),
        "batch_size": BATCH_SIZE,
        "files": [f"full_corpus_batch_{i}.json" for i in range(1, len(batches) + 1)],
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
