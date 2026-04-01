# Agent Annotate — Continuation Plan

**Last updated:** 2026-04-01
**Current state:** v24 merged to main (9db9e33). Frontend renamed to Agreement. 5 jobs reviewed.

## v24 Changes

- **Classification:** Binary AMP/Other (was AMP(infection)/AMP(other)/Other)
- **Delivery mode:** 4 categories — Injection/Infusion, Oral, Topical, Other (was 18 granular sub-categories)
- **Peptide cascade:** ALL False cascades N/A (was deterministic-only)
- **Data source:** CSV `human_ground_truth_train_df.csv` (was Excel)
- **Agreement:** Order-agnostic sequence comparison, RfF blank+failure=Unknown, N/A treated as blank
- **API:** `/api/agreement/` (was `/api/concordance/`)

### v22-era Job Performance (old code, mapped to v24 categories)

All jobs ran on v22 code (old categories). Results mapped through v24 aliases for comparison against training CSV.

**Human baseline (R1 vs R2, training CSV, 682 NCTs):**
| Field | n | Agreement | AC₁ |
|---|---|---|---|
| Classification | 454 | 93.2% | 0.919 |
| Delivery Mode | 488 | 88.3% | 0.864 |
| Outcome | 269 | 64.3% | 0.583 |
| Reason for Failure | 387 | 88.6% | 0.881 |
| Peptide | 680 | 86.0% | 0.790 |
| Sequence | 227 | 52.0% | 0.518 |

**Agent vs R1 per job:**
| Field | Conc v22 (n=39) | G R1 (n=24) | G R2 (n=24) | H R1 (n=19) | H R2 (n=19) |
|---|---|---|---|---|---|
| Classification | 94.3% | 100% | 100% | 92.3% | 92.3% |
| Delivery Mode | 88.6% | 66.7% | 73.3% | 46.2% | 46.2% |
| Outcome | 80.0% | 71.4% | 57.1% | 76.9% | 69.2% |
| RfF | 82.9% | 100% | 100% | 92.3% | 92.3% |
| Peptide | 92.3% | 79.2% | 70.8% | 78.9% | 78.9% |
| Sequence | 40.0% | 0.0% | 0.0% | 57.1% | 57.1% |

### Key Findings

1. **Classification**: Excellent (92-100%), consistently meets/beats human baseline (93.2%). No action needed.

2. **Delivery Mode**: Highly variable. Concordance v22 = 88.6% (matches human baseline), but Batches G/H drop to 46-73%. Root cause: these batch NCTs have fewer overlapping NCTs with the training CSV, so comparison is on a smaller/different population. Also, v22 code used old granular categories — mapping may lose precision.

3. **Outcome**: Concordance v22 = 80.0% (well above human 64.3%). Batches vary 57-77%. Still above human baseline on most runs.

4. **Peptide**: 70-92% across jobs, below human baseline (86%). The concordance v22 job (92.3%) is strong but batches regress. Needs investigation — may be population-dependent.

5. **Sequence**: Worst performing field. 0% on Batch G, 40% on concordance, 57% on Batch H. Mismatches are predominantly:
   - Agent finds nothing, human has a sequence (agent empty, human filled)
   - Agent defaults to DRVYIHP (angiotensin) for unrelated trials (wrong _KNOWN_SEQUENCES match)
   - Agent finds a different/partial sequence than human (different peptide picked)
   - Human annotations include non-standard formatting ((Ac), (NH2), modified residues) that the agent can't match

### Next Steps

1. **Run v24 concordance job**: Submit the concordance v22 NCTs on dev (port 9005) with v24 code to see if simplified categories improve results
2. **Fix sequence DRVYIHP over-matching**: The known-sequences table matches "angiotensin" too broadly — agent returns DRVYIHP for trials that mention angiotensin in any context
3. **Investigate delivery mode batch regression**: Compare the specific NCTs in Batches G/H where delivery mode disagrees
4. **Absorb Batches G+H into EDAM**: Now that they're complete, run edam_learning_cycle
5. **Queue Batches I/J**: positions 201-250

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
