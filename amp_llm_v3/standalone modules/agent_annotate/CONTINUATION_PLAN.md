# Agent Annotate — Continuation Plan

**Last updated:** 2026-03-23 ~15:00
**Current state:** Job #7 (`5ab9fa09b1fa`) running on prod — 63/200 NCTs. v11 fix plan in progress on dev.

## Session Log (2026-03-23)

### What happened (chronological)

1. **Job #5 completed** (`92fb568c1b96`) — 200 NCTs, v10, finished 2026-03-21 19:18. 12.2h elapsed.
2. **Job #6 completed** (`829124f16fd5`) — 200 NCTs, v10, finished 2026-03-22 23:59.
3. **Job #7 running** (`5ab9fa09b1fa`) — 63/200 as of 2026-03-23, batch E.
4. **Ran concordance on 400 v10 NCTs** (jobs #5+#6) — results below.
5. **Identified 3 critical issues** — outcome regression, peptide under-calling, AMP subtype blindness.
6. **v11 fix plan created** — see Fix Plan section below.

### Concordance: 400 v10 NCTs (jobs #5+#6 combined)

| Field | vs R1 (378 overlap) | vs R2 (318 overlap) | Human R1↔R2 | Status |
|---|---|---|---|---|
| Classification | 89.0% / AC₁ 0.883 | 85.2% / AC₁ 0.839 | 91.6% | OK but misses all AMP subtypes |
| Reason for failure | **89.4%** / AC₁ 0.891 | **91.5%** / AC₁ 0.912 | 87.2% | **Exceeds human baseline** |
| Peptide | 65.0% / κ 0.274 | 74.2% / κ 0.421 | 83.4% | Under-calling True (-18 pts) |
| Delivery mode | 57.3% / κ 0.472 | 63.3% / κ 0.539 | 71.3% | Improved from v9 (was 44%) |
| Outcome | 47.3% / κ 0.287 | 57.7% / κ 0.373 | 56.2% | **Regressed from 80% (batch A)** |

### EDAM State (2026-03-23)

| Table | Count | Notes |
|---|---|---|
| experiences | 2,375 | Jobs #1-6 |
| corrections | 147 | self_audit=139, self_review=8. **130 are peptide True→False** |
| stability_index | 2,250 | |
| embeddings | 3,193 | |
| prompt_variants | 0 | |
| config_epochs | 2 | |

## v11 Fix Plan

### Priority 1: Outcome Regression (47.3% → target >70%)

**Root causes:** H1 heuristic violated by 8B model (calls Positive without corroboration), Recruiting under-detected (17.6% recall), confidence decoupled from source count, no EDAM self-audit for outcome.

| Fix | File | What | EDAM Impact |
|---|---|---|---|
| 1a | outcome.py | Expand deterministic pass: COMPLETED+hasResults→Positive, Phase1+no pubs→Unknown | None |
| 1b | outcome.py | Fix confidence: min(citation_quality, source_sufficiency) | None |
| 1c | self_audit.py | Add outcome audit rules (Positive w/o pubs, missed Recruiting, Unknown w/ hasResults) | Additive corrections |
| 1d | outcome.py | Tighten Pass 2 prompt: explicit H1 prohibition, negative examples | New epoch (desired) |

### Priority 2: Peptide Under-calling (65% → target >80%)

**Root causes:** 130 True→False EDAM corrections reinforcing bias, self-audit asymmetry, 8B model defaults to False, token truncation.

| Fix | File | What | EDAM Impact |
|---|---|---|---|
| 2a | SQL on edam.db | Purge 130 peptide True→False self_audit corrections + embeddings | **Deletes bad corrections** |
| 2b | self_audit.py | Rebalance: more False→True patterns, require 2+ signals for True→False, guard on DB hits | New corrections |
| 2c | edam_config.py | Increase Mac Mini snippet to 400 chars for peptide | Config change → new epoch |
| 2d | peptide.py | Add known peptide drug list (GLP-1 agonists, insulin analogs, AMPs) for deterministic True | None |

### Priority 3: AMP Classification (0/14 infection, 0/14 other → target >70%)

**Root causes:** Agent defaults everything to "Other", existing keyword lists not used in decision path.

| Fix | File | What | EDAM Impact |
|---|---|---|---|
| 3a | classification.py | Deterministic rules: AMP drug + infection keyword → AMP(infection), AMP drug alone → AMP(other) | None |
| 3b | classification.py | Add worked examples of AMP(infection) and AMP(other) to Pass 2 prompt | New epoch |
| 3c | self_audit.py | Add classification audit: AMP drug in evidence but output="Other" → correct | Additive corrections |

### Execution Order

1. **Fix 2a** — purge bad peptide corrections (SQL only, immediate)
2. **Fixes 1a + 2d + 3a** — deterministic rules (no EDAM impact, safest)
3. **Fixes 1b + 2c** — confidence + config (low risk)
4. **Fixes 1c + 2b + 3c** — self-audit additions (additive EDAM)
5. **Fixes 1d + 3b** — prompt changes (new epochs, last)

All changes on **dev branch first**. Test with Batch A (25 NCTs) for comparison. Then merge to main.

## What to do next

### After v11 implementation

1. Run validation job on dev (port 9005) with Batch A (25 NCTs) — direct comparison to v9/v10
2. Compare concordance: v9 (batch A) vs v10 (batch A EDAM) vs v11 (batch A dev)
3. If improvement confirmed → merge to main, re-queue remaining NCTs

### Job #7 status

Job #7 is running on prod with v10 agents. Do NOT push to main until it completes or is cancelled.
v11 development happens on dev branch only.

## Environment State

| Environment | Branch | Agent Version | Active Job |
|---|---|---|---|
| Prod (port 8005) | main | v10 (ca50c09) | Job #7: 5ab9fa09b1fa (63/200 running) |
| Dev (port 9005) | dev | v10 → v11 in progress | None |

## Key File Locations

| Path | Purpose |
|---|---|
| `LEARNING_RUN_PLAN.md` | Overall strategy, job registry, concordance data |
| `results/edam.db` | EDAM learning database |
| `results/jobs/{job_id}.json` | Job status files |
| `results/annotations/{job_id}/{nct_id}.json` | Per-trial annotation results |
| `results/research/{job_id}/{nct_id}.json` | Cached research per job |
| `results/json/{job_id}.json` | Consolidated output (completed jobs only) |
| `scripts/human_annotated_ncts.txt` | All 964 NCTs |
| `scripts/fast_learning_batch_50.txt` | Batches A+B (50 NCTs) |

## Important Notes

- **Workflow:** Develop on `dev`, run jobs on prod. Only merge to `main` when explicitly told.
- **Update plans after every job** — this file and `LEARNING_RUN_PLAN.md` job registry.
- Prod autoupdater pulls from `main` every 30s. Do NOT push to main while a job is running.
- Dev autoupdater pulls from `dev` every 30s.
- EDAM is non-fatal: if it errors, the pipeline still runs.
- Human annotations: `dev-llm.amphoraxe.ca/docs/clinical_trials-with-sequences.xlsx`
