# Master xlsx NCT inventory (beyond `ALL_GT_NCTS`)

Generated 2026-06-03 from `/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/docs/clinical_trials-with-sequences.xlsx` (the human-annotation master file, 1844 unique NCTs).

## Files

| File | NCTs | What it is |
|---|---|---|
| `master_unannotated_576.json` | 576 | NCTs in the master xlsx with **zero human annotation** across all 6 annotation columns. No human counterpart exists for these trials. |
| `master_partial_outside_gt_423.json` | 423 | NCTs with **1–5 of 6 columns** filled by R1/R2 but **not included in the formal train/val/test cohorts** (`ALL_GT_NCTS`). Human annotation is incomplete; the trial was not curated into a scoreable cohort. |

The remaining 850 NCTs (1844 − 576 − 423 + small overlap) are already in `ALL_GT_NCTS` (629 train + 86 val + 85 test + 50 legacy `test_batch`).

## Distribution of fields-filled per master row

| Fields filled | Count | Note |
|---|---|---|
| 0 | 576 | `master_unannotated_576.json` |
| 1 | 427 | mostly `Peptide?`-only or `Delivery Mode`-only triage |
| 2 | 131 | |
| 3 | 153 | |
| 4 | 259 | |
| 5 | 262 | usually missing `Reason for Failure` (only relevant when outcome=fail) |
| 6 | 38 | fully annotated rows |

Of the 1268 partially-annotated rows (1–5 fields), most are already in `ALL_GT_NCTS`; only 423 are outside. Those 423 are in `master_partial_outside_gt_423.json`.

## Infrastructure note (2026-06-03)

The current `/api/jobs` endpoint (`app/routers/jobs.py:84`) rejects any NCT not in `ALL_GT_NCTS` even with `allow_test_batch=true`. To annotate the 576 or 423 NCTs above, one of the following is needed:

1. **Add a `MASTER_NCTS` set** in `app/services/memory/edam_config.py` (loaded from these JSON files) and widen the router's `allowed` set when a new `allow_external=true` flag is set. EDAM gating on `TRAINING_NCTS` is unchanged.
2. **Bypass NCT validation** when `allow_external=true` — simpler, but loses the safety rail.

Either change is small (~10 lines in `app/routers/jobs.py` + ~5 lines in `edam_config.py`) and reversible. Until then, the NCT lists are staged here for any future tooling.

## ETA at v42.11 prod pace (6.29 min/trial)

| Pool | NCTs | Wall clock |
|---|---|---|
| zero-annotation only | 576 | ~60h (~2.5 days) |
| zero + partial-outside-GT | 999 | ~105h (~4.4 days) |
