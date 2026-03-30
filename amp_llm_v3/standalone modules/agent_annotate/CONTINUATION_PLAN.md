# Agent Annotate — Continuation Plan

**Last updated:** 2026-03-30
**Current state:** v21 (69e7d14) on main. Batch E R1 running (83c6ad7fd4d7, 25 NCTs). EDAM: 1,404 experiences / 93 corrections / 120 unique NCTs — outcome + delivery_mode fully purged (net-negative), classification/peptide/RfF/sequence retained. Jobs 54acb4a8136d / f78d3554f29f / 92fce293f860 queued. Next: wait for all 4 Batch E/F jobs, then run v21 concordance (50 test NCTs).

## Latest Concordance

### v20 partial (15/50 NCTs, job e0f556c703c7) — 2026-03-30 (cancelled at 15/50)

| Field | v20 partial (15 NCTs) | v19 R1 baseline (50 NCTs) | Change |
|---|---|---|---|
| Classification | 100% | 92.0% / AC₁=0.917 | +8pp (small N) |
| Delivery Mode | 60.0% | 63.3% / 0.614 | -3pp |
| Outcome | 46.7% | 72.0% / 0.680 | **-25pp regression** |
| Reason for Failure | 66.7% | 68.0% / 0.625 | -1pp |
| Peptide | 100% | 80.0% / 0.734 | +20pp |

Key finding: Outcome regression confirmed at 15/50 NCTs. Root cause identified as `[Deterministic v11]` mapping `TERMINATED → "Terminated"` in `outcome.py`, bypassing LLM entirely. Trials stopped early for efficacy (positive published results, drug advanced) were blindly labelled "Terminated". Fixed in v21. Concordance cancelled — enough data to confirm regression and root cause.

### v19 (50 NCTs, 2 runs: c1786d005ade / ac6af4e49fe2) — 2026-03-27

| Field | v19 R1 | v19 R2 | v18+ baseline | Target | Met? |
|---|---|---|---|---|---|
| Classification | **92.0% / AC₁=0.917** | **92.0% / AC₁=0.917** | 87.8% / 0.870 | AC₁≥0.82 | YES (+4.2%) |
| Delivery Mode | 65.3% / 0.632 | 63.3% / 0.614 | 67.3% / 0.654 | ≥73% | NO (slight regress) |
| Outcome | 72.0% / 0.680 | 68.0% / 0.634 | 70.0% / 0.657 | ≥80% | NO (slight improve) |
| Reason for Failure | 72.0% / 0.671 | 68.0% / 0.625 | 72.0% / 0.671 | ≥84% | NO (same) |
| Peptide | 86.7% / 0.834 | 80.0% / 0.734 | 88.9% / 0.865 | ≥86% | Borderline / high variance |
| Sequence | 65.0% / 0.634 | 68.4% / 0.668 | 59.1% / 0.574 | ≥30% | YES (from code only) |

## v21 Changes (merged to main, commit 69e7d14)

**1. TERMINATED overcalling fix (CRITICAL)**
- `outcome.py`: removed `"TERMINATED"` from `_DETERMINISTIC_STATUSES`. Was blindly mapping all TERMINATED trials to outcome="Terminated" with `skip_verification=True`, bypassing LLM entirely.
- Root cause of -25pp outcome regression on v20 partial concordance.
- Trials stopped early for efficacy (positive published results, drug advanced to later phases) were annotated "Terminated" instead of "Positive".
- Fix: TERMINATED now falls through to the 2-pass LLM pipeline. PASS2_PROMPT item 4 checks evidence: Positive if positive results/drug advanced, Failed if safety/futility, Terminated if business reason or no signal.
- `verifier.py`: updated TERMINATED rule from "always Terminated" to evidence-based decision tree.

**2. Phase-based completion heuristics (HIGH)**
- `outcome.py` PASS2_PROMPT H1b: Phase I completed >5yr ago + no Phase II found + no publications → "Unknown" (drug likely didn't advance, but "Failed" requires positive evidence)
- `outcome.py` PASS2_PROMPT H3b: Phase II/III completed >10yr ago + no publications + no negative evidence → lean "Positive" (common for older industry-sponsored trials that didn't publish)
- `verifier.py`: H1b and H3b added to verifier instruction.

**3. Delivery mode: EXPERIMENTAL arm only (MEDIUM)**
- `delivery_mode.py` `_deterministic_delivery_mode()`: filter `intervention_names` to arms where `armGroups[type=EXPERIMENTAL]`. Falls back to all interventions if no arm type data available (older CT.gov records).
- PASS1_SYSTEM: explicit instruction to focus on EXPERIMENTAL arm route only, ignore placebo/comparator/background arms.
- PASS2_SYSTEM Rule 6: clarified multi-route applies to experimental drugs only.

**4. EDAM surgical purge (Option C)**
- Deleted ALL outcome + delivery_mode experiences (351 each) and corrections (10 outcome, 30 delivery_mode).
- Rationale: outcome experiences contaminated by biased TERMINATED→Terminated mappings from v20 code; delivery_mode experiences contaminated by comparator arm routes + 25+ contradictory corrections.
- Retained: classification (351 exp, 18 corr), peptide (351 exp, 52 corr), reason_for_failure (351 exp, 23 corr), sequence (351 exp, 0 corr).
- EDAM post-purge: 1,404 experiences / 93 corrections / 120 unique NCTs.
- New training (Batches E/F) on v21 code will rebuild outcome + delivery_mode from scratch with correct annotations.

## Strategic Plan: Post-v21 Concordance

**After all 4 Batch E/F jobs complete → run v21 concordance (50 test NCTs):**

| v21 outcome concordance | Action |
|---|---|
| ≥76% vs v19 R1 (72%) | TERMINATED fix confirmed. EDAM E/F providing good signal. Continue training. |
| 70-76% | Marginal improvement. Re-run once more. Investigate remaining failures. |
| ≤70% | Fix not sufficient. Examine failed cases in detail before more training. |

**v21 targets:**
- Outcome: ≥76% (TERMINATED fix expected to recover most of the regression)
- Delivery mode: ≥65% (experimental-arm-only filter expected to reduce false multi-route)
- Classification: hold at 92%
- RfF: ≥70%

**EDAM strategy going forward:**
- Batches E/F (50 new NCTs, positions 101-150 of training pool) run ×2 each for EDAM stability
- outcome + delivery_mode EDAM will rebuild from scratch on v21 code
- After v21 concordance confirms improvement → Batches G/H (positions 151-200), then full 642-NCT run

**EDAM net-positive threshold:** Base field accuracy must be ≥~70% for EDAM to improve rather than harm. outcome and delivery_mode were below this threshold with contaminated data. Now reset.

**Training vs test gap:** Outcome 44-50% on training NCTs vs 68-72% on test NCTs. Test NCTs selected for literature richness. Do NOT use training-NCT concordance to evaluate model quality — always use test batch (fast_learning_batch_50.txt).

**Hardware constraint:** No parallel jobs. Mac Mini M4, 16GB. Submit jobs one at a time (API queues them).

## Current: v21 Batch E/F Training

### Training Queue (2026-03-30)
| Job | Batch | NCTs | Status |
|---|---|---|---|
| 83c6ad7fd4d7 | Batch E run 1 | 25 (positions 101-125) | **running** |
| 54acb4a8136d | Batch E run 2 | 25 (positions 101-125) | queued |
| f78d3554f29f | Batch F run 1 | 25 (positions 126-150) | queued |
| 92fce293f860 | Batch F run 2 | 25 (positions 126-150) | queued |

50 unique training NCTs (positions 101-150 of training pool, excl. test batch), each run twice for EDAM stability.
After all 4 complete: run concordance on fast_learning_batch_50.txt (50 test NCTs).

### v20 Training (completed, EDAM outcome+delivery_mode purged)
| Job | Batch | NCTs | EDAM exp written | Notes |
|---|---|---|---|---|
| ba96acf75132 | Train-C run 1 | 50 | 300 | First clean training run |
| 29830f7d3785 | Train-C run 2 | 50 | 300 | |
| 798817a09db3 | Train-D run 1 | 50 | 300 | |
| 3fc6552eb54e | Train-D run 2 | 50 | 300 | |

All 1,200 outcome + delivery_mode experiences from these jobs were purged (see v21 EDAM purge above).

## Environment State

| Environment | Branch | Version | Active Job |
|---|---|---|---|
| Prod (port 8005) | main | v21 (69e7d14) | 83c6ad7fd4d7 running (Batch E run 1) |
| Dev (port 9005) | dev | v21 (6ce9aff) | None |

## Important Notes

- **Workflow:** Develop on `dev`, run jobs on prod. Only merge to `main` when explicitly told.
- **CRITICAL:** Always commit+push atomically in ONE bash command. Autoupdater wipes uncommitted changes every 30s. Use: `git checkout dev && git cherry-pick <hash> && git push origin dev && git checkout main` for dev changes.
- **Autoupdater behavior:** Runs every 30s, does `git checkout main` then `git reset --hard origin/main`. Never work directly on main — dev only.
- **Update plans after every job** — this file and `LEARNING_RUN_PLAN.md`.
- **Drug lists are FROZEN** — no more additions. Improvements through reasoning (Layers 1-3) only.
- **All AMPs are peptides** — AMP classification forces peptide=True in consistency engine.
- **Auth token:** Retrieved from `~/Developer/amphoraxe/auth.amphoraxe.ca/data/auth.db` sessions table.
- **EDAM allowlist:** Only 642 training CSV NCTs stored in EDAM. Test NCTs (fast_learning_batch_50.txt) hard-excluded by subtraction in edam_config.py.
- **Hardware:** No parallel jobs. Mac Mini M4, 16GB. API queues jobs automatically.
- **EDAM net-positive threshold:** Base accuracy must be ≥~70% for EDAM to help. Below threshold it reinforces wrong answers.
- **Failed jobs (cf642da98bd6, 434ad7a32ff8):** Both status=failed, 0 EDAM writes. No purge needed.
- **Training vs test gap:** Outcome 44-50% on training NCTs vs 68-72% on test NCTs. Don't evaluate EDAM effectiveness on training concordance.

## How to Run v21 Concordance (after Batch E/F complete)

```bash
TOKEN=$(sqlite3 ~/Developer/amphoraxe/auth.amphoraxe.ca/data/auth.db "SELECT token FROM sessions ORDER BY created_at DESC LIMIT 1;")
NCT_IDS=$(python3 -c "
with open('/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/amp_llm_v3/standalone modules/agent_annotate/scripts/fast_learning_batch_50.txt') as f:
    ncts = [l.strip() for l in f if l.strip()]
import json; print(json.dumps(ncts))
")
curl -s -X POST http://localhost:8005/api/jobs \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $TOKEN" \
  -d "{\"nct_ids\": $NCT_IDS}"
```

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
