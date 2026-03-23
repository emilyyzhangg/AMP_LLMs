# EDAM Learning Run Plan

**Last updated:** 2026-03-23 ~17:30

## Job Registry

This is the canonical list of every annotation job run. Update after every job.

| # | Batch | Job ID | NCTs | Completed | Status | Agent Ver | Git Commit | EDAM Corrections | Started | Finished | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | A | c7e666682865 | 25 | 25/25 | **Complete** | v9 | 8d6f236 | 0 | 2026-03-19 12:20 | 2026-03-19 15:21 | Richest 25 NCTs. First prod run. |
| 2 | B | ae1ece9d4e0a | 25 | 25/25 | **Complete** | v9 | 8d6f236 | 0 | 2026-03-19 ~17:00 | 2026-03-19 ~20:00 | Next richest 25. |
| 3 | A repeat | 5d207b30f11c | 25 | 25/25 | **Complete** | v9 | 8d6f236 | 0 | 2026-03-19 20:34 | 2026-03-19 23:31 | EDAM bootstrap. |
| 4 | C (v9) | 49ac8fdd9e90 | 200 | 36/200 | **Cancelled** | v9 | c1d6599 | N/A | 2026-03-20 05:59 | 2026-03-20 ~11:00 | Cancelled for v10. |
| 5 | C (v10) | 92fb568c1b96 | 200 | 200/200 | **Complete** | v10 | 272503c | 27 | 2026-03-20 ~11:15 | 2026-03-21 19:18 | 12.2h total. |
| 6 | D (v10) | 829124f16fd5 | 200 | 200/200 | **Complete** | v10 | ca50c09 | 28 | 2026-03-22 ~00:00 | 2026-03-22 23:59 | First with EDAM corrections. |
| 7 | E (v10) | 5ab9fa09b1fa | 200 | 68/200 | **Cancelled** | v10 | ca50c09 | — | 2026-03-23 00:02 | 2026-03-23 ~16:00 | Cancelled for v11. 68 annotations saved, no post-job hook. |
| 8 | F | ccb0a26f0057 | 200 | 0/200 | **Cancelled** | — | — | — | — | — | Cancelled for v11. |
| 9 | G | 70387dbfdde7 | 114 | 0/114 | **Cancelled** | — | — | — | — | — | Cancelled for v11. |
| **10** | **E (v11)** | **60aa4a590462** | **200** | **0/200** | **Running** | **v11** | **2a1ebba** | **TBD** | **2026-03-23 ~17:30** | **—** | **First v11 job. Same NCT pool as cancelled #7.** |
| **11** | **F (v11)** | **26baede0fdec** | **200** | **0/200** | **Queued** | **v11** | **2a1ebba** | **TBD** | **—** | **—** | **Second v11 batch.** |
| **12** | **G (v11)** | **b4536fa3e108** | **114** | **0/114** | **Queued** | **v11** | **2a1ebba** | **TBD** | **—** | **—** | **Final batch. Completes all 964 NCTs.** |
| *13* | *Selective re-ann* | *TBD* | *~120* | *—* | *Planned* | *v11* | *—* | *—* | *—* | *—* | *v10 trials where v11 deterministic rules change the result (107 outcome + 13 peptide)* |

### Agent version summary

| Version | Commit | Key changes |
|---|---|---|
| v9 | 8d6f236 | Two-pass annotation, deterministic bypass, EDAM system, verification personas |
| v10 | 272503c | delivery_mode: 31 keywords, all-source search, 14B model. clinical_protocol: detailedDescription + armGroups. self_audit: searches agent reasoning. |
| **v11** | **2a1ebba** | **Outcome: expanded deterministic (COMPLETED+hasResults, Phase I guard), confidence=min(quality, sufficiency), tightened prompt w/ negative example. Peptide: _KNOWN_PEPTIDE_DRUGS deterministic True (~60 drugs), snippet 400ch. Self-audit: +outcome, +classification, rebalanced peptide (2+ signals, DB guard). EDAM: purged 128 bad corrections, field snippet overrides, definition keywords for outcome/classification.** |

## NCT Coverage

| Set | Count | Status |
|---|---|---|
| Human-annotated (total) | 964 | Target for Phase 1 |
| Batch A+B (v9) | 50 | Complete |
| Batch C+D (v10, jobs #5-6) | 400 | Complete — 120 need selective re-annotation |
| Batch E+F+G (v11, jobs #10-12) | 514 | **Running/Queued** |
| Selective re-annotation (job #13) | ~120 | Planned — after v11 concordance confirms improvement |
| Unannotated (no human ref) | 884 | Phase 5 — agent-only |

## v10 Concordance (400 NCTs, jobs #5+#6)

| Field | vs R1 | vs R2 | Human R1↔R2 | Status |
|---|---|---|---|---|
| Classification | 89.0% / AC₁ 0.883 | 85.2% / AC₁ 0.839 | 91.6% | OK but 0/14 AMP subtypes |
| Reason for failure | **89.4%** / AC₁ 0.891 | **91.5%** / AC₁ 0.912 | 87.2% | **Exceeds human** |
| Peptide | 65.0% / κ 0.274 | 74.2% / κ 0.421 | 83.4% | Under-calling True |
| Delivery mode | 57.3% / κ 0.472 | 63.3% / κ 0.539 | 71.3% | Improved from v9 |
| Outcome | 47.3% / κ 0.287 | 57.7% / κ 0.373 | 56.2% | **Regressed from 80%** |

### v10 → v11 Deterministic Impact Analysis (400 NCTs)

| Fix | NCTs Affected | % | What Changes |
|-----|---------------|---|-------------|
| Phase I guard (Positive→Unknown) | 107 | 27% | COMPLETED Phase I w/o hasResults → now deterministic Unknown |
| Known peptide drugs (False→True) | 13 | 3% | Known peptide drug was called False → now deterministic True |
| Known peptide drugs (already True) | 53 | 13% | No value change, now deterministic (faster) |
| COMPLETED+hasResults | 0 | 0% | Already correct in v10 |
| **Total would change** | **120** | **30%** | — |

## EDAM Database State (2026-03-23 post-purge)

| Table | Count | Notes |
|---|---|---|
| experiences | 2,715 | v9 epoch 1 (375), v10 epoch 2 (2,340) |
| corrections | 42 | Post-purge: 20 pep T→F, 5 pep F→T, 7 dm, 4 outcome, 6 misc |
| stability_index | 2,590 | 2,205 medium, 378 none, 7 weak |
| embeddings | 3,065 | |
| prompt_variants | 0 | Will fire after job #12 (every 3rd job) |
| config_epochs | 2 → 3 | v11 creates epoch 3 on first job |

### Epoch decay

| Data | Epoch 1→3 | Epoch 2→3 |
|------|-----------|-----------|
| Experiences | 56% (floor 5%) | 75% (floor 5%) |
| Corrections | — | 80% (floor 10%) |
| Definition-grounded | — | 90% (floor 35%) |

## Plan going forward

### Phase 1: Complete 514 remaining NCTs with v11 (in progress)

Jobs #10-12 running autonomously. No intervention required.

```
Job #10: 200 NCTs (RUNNING)  — ~12h
Job #11: 200 NCTs (QUEUED)   — ~12h
Job #12: 114 NCTs (QUEUED)   — ~7h
                        Total: ~31h → ~2026-03-25 00:30
```

EDAM post-job hook fires between each job, storing v11 corrections that feed into the next job. Prompt optimization fires after job #12 (every 3rd job).

### Phase 2: v11 Concordance + Selective Re-annotation

After jobs #10-12 complete:

1. Run concordance on 514 v11 NCTs vs human annotations
2. Compare v11 concordance vs v10 concordance (400 NCTs) to measure improvement
3. If v11 shows improvement → submit Job #13: selective re-annotation of ~120 v10 NCTs
4. If v11 does NOT show improvement → investigate before proceeding

### Phase 3: Full Concordance on all 964

Run `concordance_jobs.py` across all completed jobs:
- v9: jobs #1-2 (50 NCTs)
- v10: jobs #5-6 (400 NCTs, 280 unchanged + 120 re-annotated)
- v11: jobs #10-12 (514 NCTs)

### Phase 4: Decision — targets met?

**Targets (must exceed human inter-rater baseline):**
- Outcome: human R1↔R2 = 56.2% → agent target: **>65%**
- Peptide: human R1↔R2 = 83.4% → agent target: **>80%**
- Classification: AC₁ > **0.90**
- Delivery mode: > **65%**

If met → Phase 5. If not → analyze errors, potentially fix agents, re-run worst batches.

### Phase 5: Annotate 884 unannotated NCTs

Agent-only, no human counterpart. Full EDAM guidance from 964 validated trials.

## Key Files

| Path | Purpose |
|---|---|
| `CONTINUATION_PLAN.md` | Step-by-step pickup instructions for next session |
| `results/edam.db` | EDAM learning database |
| `results/jobs/{job_id}.json` | Job status files |
| `results/annotations/{job_id}/{nct_id}.json` | Per-trial annotation results |
| `results/json/{job_id}.json` | Consolidated output (completed jobs only) |
| `results/review_queue.json` | Flagged items for manual review |
| `scripts/human_annotated_ncts.txt` | All 964 NCTs |
| `scripts/fast_learning_batch_50.txt` | Batches A+B (50 NCTs) |
