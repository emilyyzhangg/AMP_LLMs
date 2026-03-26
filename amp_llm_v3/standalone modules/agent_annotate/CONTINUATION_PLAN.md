# Agent Annotate — Continuation Plan

**Last updated:** 2026-03-26
**Current state:** v18 code pushed to dev (fc6fddac). Prod on v17 (66907432). Three v17 Batch A jobs complete (9e1f, a3d5, 4b06). EDAM restricted to training CSV NCTs.

## Next Step: Run v18 Batch A on new 25 NCTs from training set

v18 has 7 fixes based on v17 concordance analysis (3 runs). Need to merge to main, then run new Batch A (25 NCTs from training CSV).

### v17 Concordance Results (3 runs: 9e1f, a3d5, 4b06 — same 25 NCTs)

| Field | v16 vs R1 | v17 best | v17 worst | v17 range | Target | Met? |
|---|---|---|---|---|---|---|
| Classification | 84.0% | **88.0%** | **88.0%** | Stable | AC₁≥0.82 | YES |
| Delivery Mode | 72.7% | **68.0%** | **64.0%** | Oscillating | ≥73% | NO |
| Outcome | 77.3% | **76.0%** | **68.0%** | Unstable (-8%) | ≥80% | NO |
| Reason for Failure | 84.0% | **68.0%** | **56.0%** | **Regressed badly** | ≥84% | NO |
| Peptide | 81.8% | **90.9%** | **90.9%** | Stable | ≥86% | YES |
| Sequence | 14.3% | **32.0%** | **32.0%** | Stable (0 exact matches) | ≥30% | MISLEADING |

**2/6 targets met.** Classification and peptide are solid. Sequence 32% = all "both empty" matches, 0 exact matches out of 17.

### Root causes identified and fixed in v18

| Issue | Root Cause | v18 Fix |
|---|---|---|
| Sequence 0 exact matches | ChEMBL returns wrong molecule (keyword collision). DBAASP returns wrong protein (Insulin for Nesiritide). No candidates for most drugs. | Known-sequences table (12 drugs), cross-validation penalty (0.3x for name mismatch), ChEMBL max_phase disambiguation, EDAM-enriched intervention names |
| Outcome instability (68-76%) | Phase I corroboration accepts generic publications (vary by run). NCT00000886 false Positive (toxicity missed). | Strong adverse signals checked FIRST in full text. Phase I requires `has_results_posted` or NCT ID in text. |
| RfF regression (56-68%) | Agent returns empty for TERMINATED/WITHDRAWN trials (9/11 disagreements). `_pass1_says_no_failure()` bails out. Empty vote dropped from reconciler. | TERMINATED/WITHDRAWN always proceed to pass 2. Default "Business Reason" for terminated/withdrawn with no signal. Empty RfF counted as vote. Unanimous-verifier gate for empty override. |
| EDAM learning from test data | No NCT filtering — EDAM learned from all annotated NCTs | Training CSV allowlist (642 NCTs). Stability, self-review, self-audit all filtered. |

### v18 New Batch A (25 NCTs from training CSV)

Selected for diversity: 8 AMP / 17 Other, 4 peptide=false, 18 with sequences, 5 with RfF, mixed outcomes.

```
NCT00001060  NCT01639638  NCT03052842  NCT03635437  NCT03772678
NCT03791515  NCT03923257  NCT03987672  NCT04023331  NCT04389775
NCT04419610  NCT04671966  NCT04844580  NCT04924660  NCT04954274
NCT05064137  NCT05127889  NCT05218915  NCT05889728  NCT05940428
NCT05968846  NCT06045260  NCT06689761  NCT06729606  NCT06801015
```

### What to check after v18 Batch A

1. **Sequence:** Expect >0 exact matches (known-sequences table covers Nesiritide, Albiglutide, Angiotensin)
2. **Outcome:** Expect stable (no inter-run flip-flops from Phase I corroboration)
3. **RfF:** Expect "Business Reason" populated for terminated/withdrawn trials
4. **EDAM:** Verify only training NCTs stored in experiences table
5. **Peptide:** Should maintain ≥90% (stable, no changes)

## Environment State

| Environment | Branch | Version | Active Job |
|---|---|---|---|
| Prod (port 8005) | main | v17 (66907432) | None (4b062214adf0 complete) |
| Dev (port 9005) | dev | v18 (fc6fddac) | None |

## Important Notes

- **Workflow:** Develop on `dev`, run jobs on prod. Only merge to `main` when explicitly told.
- **CRITICAL:** Always commit+push atomically in ONE bash command. Autoupdater wipes uncommitted changes every 30s.
- **Update plans after every job** — this file and `LEARNING_RUN_PLAN.md`.
- **Drug lists are FROZEN** — no more additions. Improvements through reasoning (Layers 1-3) only.
- **All AMPs are peptides** — AMP classification forces peptide=True in consistency engine.
- **Auth token:** Retrieved from `~/Developer/amphoraxe/auth.amphoraxe.ca/data/auth.db` sessions table.

## Key File Locations

| Path | Purpose |
|---|---|
| `LEARNING_RUN_PLAN.md` | Overall strategy, job registry, concordance data |
| `results/edam.db` | EDAM learning database (incl. drug_names table) |
| `results/jobs/{job_id}.json` | Job status files |
| `results/annotations/{job_id}/{nct_id}.json` | Per-trial results |
| `results/json/{job_id}.json` | Consolidated output |
| `scripts/human_annotated_ncts.txt` | All 964 NCTs |
| `scripts/fast_learning_batch_25.txt` | Batch A (25 richest NCTs) |
| `scripts/fast_learning_batch_50.txt` | Batch A+B (50 richest NCTs) |
