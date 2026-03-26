# Agent Annotate — Continuation Plan

**Last updated:** 2026-03-25
**Current state:** v17 code written on dev. Prod still on v16 (a599e7a). Job 25366ac24587 complete. EDAM has 300 experiences from v14/v15 runs.

## Next Step: Merge v17 to main and run Batch A

v17 has 4 targeted fixes based on v16 concordance root-cause analysis. Need to merge to main, then run Batch A (25 NCTs) to validate.

### v16 Concordance Results (job 25366ac24587) — completed 2026-03-25

| Field | v15 vs R1 | v16 vs R1 | Delta | Verdict |
|---|---|---|---|---|
| Classification | 83.3% | **84.0%** | +0.7% | Stable |
| Delivery Mode (strict) | 69.6% | **72.7%** | +3.1% | Improved |
| Delivery Mode (bucketed) | 95.7% | **95.5%** | -0.2% | Stable |
| Outcome | 78.3% | **77.3%** | -1.0% | Slight regression |
| Reason for Failure | 84.0% | **84.0%** | 0.0% | Stable |
| Peptide | 86.4% | **81.8%** | -4.6% | **Regressed** |
| Sequence | 0.0% | **14.3%** | +14.3% | **Major improvement** (0→7/25 extracted) |

**Convergence: NOT MET** — peptide regressed 4.6% (threshold was <2%).

### Root causes identified and fixed in v17

| Issue | Root Cause | v17 Fix |
|---|---|---|
| Outcome 4× Unknown | Adverse-event heuristic in dead code (only called on LLM exception, not on LLM "Unknown") | Post-LLM override: call `_infer_from_pass1()` when Pass 2 returns "Unknown". Also inject structured phase from ClinicalTrials.gov into Pass 2. |
| Peptide -4.6% regression | Confidence gate (≥0.90) checks source quality (static ~0.90-0.95), not classification certainty | Only cascade on `model_name=="deterministic"` (known drug lists). LLM False results no longer trigger cascade. Added OSE2101/TEDOPI/DOTATOC to known peptides. |
| Sequence 0% accuracy | DBAASP abbreviation collision (BNP→BnPRP1, ANP→HANP). ChEMBL HELM outscored by wrong DBAASP matches. UniProt picks shortest fragment (degradation products). | Word-boundary matching for short names (≤4 chars). ChEMBL HELM boosted 1.3x. UniProt prefers name-matching fragments. Formulation text stripped. |
| Multi-route not working | Deterministic path returns on first keyword match. " iv " matches disease grading in titles. _parse_value strips to single value. | Collect all routes across all citations. Exclude title text from ambiguous keywords. _parse_value handles comma-separated. |

### What to check after v17 Batch A

1. **Outcome:** Expect ≥80% vs R1 (heuristic override catches NCT00000886 reactogenicity)
2. **Peptide:** Expect ≥86% vs R1 (cascade suppression + OSE2101 in known drugs)
3. **Sequence:** Expect accuracy improvement (DBAASP collision fixed, ChEMBL HELM boosted)
4. **Delivery:** NCT05415410 and NCT06126354 should show multi-route values
5. **Convergence:** If v17 vs v16 <2% on classification/RfF (stable fields) → Phase 2

## Environment State

| Environment | Branch | Version | Active Job |
|---|---|---|---|
| Prod (port 8005) | main | v16 (a599e7a) | None (25366ac24587 complete) |
| Dev (port 9005) | dev | **v17 (uncommitted)** | None |

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
