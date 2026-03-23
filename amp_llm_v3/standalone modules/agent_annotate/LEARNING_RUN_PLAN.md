# EDAM Learning Run Plan

**Last updated:** 2026-03-23 ~16:00

## Job Registry

This is the canonical list of every annotation job run. Update after every job.

| # | Batch | Job ID | NCTs | Completed | Status | Agent Ver | Git Commit | EDAM Corrections | Started | Finished | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | A | c7e666682865 | 25 | 25/25 | **Complete** | v9 | 8d6f236 | 0 | 2026-03-19 12:20 | 2026-03-19 15:21 | Richest 25 NCTs (4-5 fields both R1+R2). First prod run. |
| 2 | B | ae1ece9d4e0a | 25 | 25/25 | **Complete** | v9 | 8d6f236 | 0 | 2026-03-19 ~17:00 | 2026-03-19 ~20:00 | Next richest 25. No NCT overlap with A. |
| 3 | A repeat | 5d207b30f11c | 25 | 25/25 | **Complete** | v9 | 8d6f236 | 0 | 2026-03-19 20:34 | 2026-03-19 23:31 | EDAM bootstrap — same 25 as batch A. Differences are stochastic noise only. |
| 4 | C (v9) | 49ac8fdd9e90 | 200 | 36/200 | **Cancelled** | v9 | c1d6599 | N/A | 2026-03-20 05:59 | 2026-03-20 ~11:00 | Cancelled to merge v10 agents. 36 per-trial annotations saved. No consolidated JSON. |
| 5 | C (v10) | 92fb568c1b96 | 200 | 200/200 | **Complete** | v10 | 272503c | 27 | 2026-03-20 ~11:15 | 2026-03-21 19:18 | Same 200 NCTs as job #4. Resumed twice at 143. 12.2h total. |
| 6 | D (v10) | 829124f16fd5 | 200 | 200/200 | **Complete** | v10 | ca50c09 | 28 | 2026-03-22 ~00:00 | 2026-03-22 23:59 | First batch with EDAM corrections from job #5. |
| 7 | E (v10) | 5ab9fa09b1fa | 200 | 63/200 | **Cancelled** | v10 | ca50c09 | — | 2026-03-23 00:02 | 2026-03-23 ~16:00 | Cancelled for v11 upgrade. 63 annotations saved. |
| 8 | F | ccb0a26f0057 | 200 | 0/200 | **Cancelled** | — | — | — | — | — | Cancelled for v11 upgrade. |
| 9 | G | 70387dbfdde7 | 114 | 0/114 | **Cancelled** | — | — | — | — | — | Cancelled for v11 upgrade. |

### Agent version summary

| Version | Commit | Key changes |
|---|---|---|
| v9 | 8d6f236 | Two-pass annotation, deterministic bypass, EDAM system, verification personas |
| v10 | 272503c (main), f041f84d (dev) | delivery_mode: expanded keywords (31), all-source search, 14B model on mac_mini. clinical_protocol: detailedDescription + armGroups. classification: _parse_value fix. self_audit: searches agent reasoning for contradictions. |
| v10+queue | 1112528 (main), 84118cdc (dev) | Job queue: multiple jobs submitted and run sequentially. Cross-branch gatekeeper in worker. |
| **v11** | **TBD (dev)** | **Outcome: expanded deterministic (COMPLETED+hasResults, Phase I guard), confidence=min(quality, sufficiency), tightened Pass 2 prompt. Peptide: known peptide drug list for deterministic True, snippet 400 chars. Self-audit: +outcome audit, +classification audit, rebalanced peptide (2+ signals for True→False, DB hit guard). EDAM: purged 128 bad peptide True→False corrections, field-specific snippet overrides, definition keywords for outcome/classification.** |

## NCT Coverage

| Set | Count | Status |
|---|---|---|
| Human-annotated (total) | 964 | Target for Phase 1 |
| Batch A+B (richest 50) | 50 | Complete (v9), 25 have 2 runs |
| Batch C (200) | 200 | Complete (v10, job #5) |
| Batch D (200) | 200 | Complete (v10, job #6) |
| Batch E partial (63) | 63 | Partial (v10, job #7 cancelled for v11) |
| Remaining | 451 | To be re-queued with v11 agents |
| Unannotated (no human ref) | 884 | Phase 6 — agent-only |

## v10 → v11 Concordance Comparison (400 NCTs)

### v10 Concordance (jobs #5+#6, 400 NCTs)

| Field | vs R1 (N) | vs R2 (N) | Human R1↔R2 | Status |
|---|---|---|---|---|
| Classification | 89.0% / AC₁ 0.883 (326) | 85.2% / AC₁ 0.839 (257) | 91.6% | OK but 0/14 AMP subtypes |
| Reason for failure | **89.4%** / AC₁ 0.891 (378) | **91.5%** / AC₁ 0.912 (318) | 87.2% | **Exceeds human** |
| Peptide | 65.0% / κ 0.274 (371) | 74.2% / κ 0.421 (93) | 83.4% | Under-calling True |
| Delivery mode | 57.3% / κ 0.472 (314) | 63.3% / κ 0.539 (245) | 71.3% | Improved from v9 (was 44%) |
| Outcome | 47.3% / κ 0.287 (300) | 57.7% / κ 0.373 (248) | 56.2% | **Regressed from 80%** |

### Key Issues Fixed in v11

| Issue | Root Cause | v11 Fix |
|---|---|---|
| Outcome 80%→47% | H1 violated (Positive w/o pubs), Recruiting 17% recall, confidence always 0.85+ | Deterministic COMPLETED+hasResults, Phase I guard, confidence cap, outcome self-audit |
| Peptide 65% (83% human) | 130 True→False EDAM corrections, self-audit asymmetry, 8B model bias | Purged bad corrections, known peptide drugs, rebalanced self-audit, 400ch snippets |
| Classification 0/14 AMP | Agent defaults to Other, existing lists not used in decision path | Classification self-audit, definition-weighted EDAM corrections |

## EDAM Database State (2026-03-23 post-purge)

| Table | Count | Notes |
|---|---|---|
| experiences | 2,375 | Jobs #1-6 |
| corrections | **19** | Purged 128 bad peptide True→False. Remaining: 4 pep F→T, 2 pep T→F (self_review), delivery_mode, outcome |
| stability_index | 2,250 | |
| embeddings | 3,065 | 128 removed with corrections |
| prompt_variants | 0 | |
| config_epochs | 2 → 3 | v11 will create epoch 3 |

## Plan going forward

### Phase 1: Validate v11 (immediate)

1. Merge v11 to main
2. Submit validation job: Batch A (25 NCTs) — direct comparison to v9/v10
3. Run concordance: compare v9 (batch A) vs v10 (batch A EDAM) vs v11
4. If improvement confirmed → re-queue remaining 451 NCTs

### Phase 2: Complete 964 human-annotated NCTs with v11

Submit 3 jobs:
- Job #10: 200 NCTs (batch E — includes 63 from cancelled job #7, re-annotated with v11)
- Job #11: 200 NCTs (batch F)
- Job #12: 51 NCTs (batch G — remainder, was 114 minus 63 already done)

Wait — actually all 451 remaining need fresh v11 annotation. The 63 from job #7 were v10.

- Job #10: 200 NCTs
- Job #11: 200 NCTs
- Job #12: 51 NCTs (final batch)

Estimated: ~3 days from submission.

### Phase 3: Full concordance on all 964

Run concordance_jobs.py across all completed v11 jobs.

### Phase 4: Decision — re-annotate or proceed?

**Targets (must exceed human inter-rater baseline):**
- Outcome: human R1 vs R2 = 56.2% → agent target: >65%
- Peptide: human R1 vs R2 = 83.4% → agent target: >80%
- Classification: AC₁ > 0.90
- Delivery mode: > 65%

### Phase 5: Annotate 884 unannotated NCTs

Agent-only, no human counterpart. Full EDAM guidance from 964 validated trials.

## Key Files

| Path | Purpose |
|---|---|
| `CONTINUATION_PLAN.md` | Step-by-step pickup instructions for next session |
| `results/edam.db` | EDAM learning database |
| `results/jobs/{job_id}.json` | Job status files |
| `results/annotations/{job_id}/{nct_id}.json` | Per-trial annotation results |
| `results/research/{job_id}/{nct_id}.json` | Cached research per job |
| `results/json/{job_id}.json` | Consolidated output (completed jobs only) |
| `results/review_queue.json` | Flagged items for manual review |
| `scripts/human_annotated_ncts.txt` | All 964 NCTs with human annotations |
| `scripts/fast_learning_batch_50.txt` | Batches A+B NCTs (50) |
| `app/services/memory/self_audit.py` | Self-audit (v11: +outcome, +classification, rebalanced peptide) |
| `agents/annotation/outcome.py` | v11: expanded deterministic, confidence fix, prompt tightening |
| `agents/annotation/peptide.py` | v11: known peptide drugs, snippet override |
| `app/services/memory/edam_config.py` | v11: field snippet overrides, definition keywords |
