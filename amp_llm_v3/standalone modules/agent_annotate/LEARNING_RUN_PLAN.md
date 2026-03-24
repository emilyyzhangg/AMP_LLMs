# EDAM Learning Run Plan

**Last updated:** 2026-03-24 ~session

## Job Registry

| # | Batch | Job ID | NCTs | Completed | Status | Agent Ver | EDAM Corrections | Notes |
|---|---|---|---|---|---|---|---|---|
| 1 | A | c7e666682865 | 25 | 25/25 | **Complete** | v9 | 0 | Richest 25 NCTs. Baseline. |
| 2 | B | ae1ece9d4e0a | 25 | 25/25 | **Complete** | v9 | 0 | Next richest 25. |
| 3 | A repeat | 5d207b30f11c | 25 | 25/25 | **Complete** | v9 | 0 | EDAM bootstrap. |
| 4 | C (v9) | 49ac8fdd9e90 | 200 | 36/200 | **Cancelled** | v9 | N/A | Cancelled for v10. |
| 5 | C (v10) | 92fb568c1b96 | 200 | 200/200 | **Complete** | v10 | 27 | 12.2h total. |
| 6 | D (v10) | 829124f16fd5 | 200 | 200/200 | **Complete** | v10 | 28 | First with EDAM corrections. |
| 7 | E (v10) | 5ab9fa09b1fa | 200 | 68/200 | **Cancelled** | v10 | — | Cancelled for v11. |
| 8-9 | F-G | various | 314 | 0 | **Cancelled** | — | — | Cancelled for v11. |
| 10a | A test (wrong batch) | 19a39aa475a3 | 25 | 10/25 | **Cancelled** | v11+eff | — | Cancelled after 10. |
| 10b | A test (wrong batch) | 8352a3ea84aa | 25 | 0/25 | **Cancelled** | v11+eff | — | Cancelled immediately. |
| **10c** | **A test (wrong batch)** | **1ff6092a499c** | **25** | **25/25** | **Complete** | **v11+eff** | **TBD** | **Had 5 duplicate NCTs (bug fixed). Used WRONG NCTs (not fast_learning_batch_25.txt). Outcome regressed to 52% vs R1 — Phase I guard caused 9/9 wrong Unknowns.** |
| *11* | *A test (correct batch)* | *TBD* | *25* | *—* | *Pending* | *v12* | *—* | *Re-run on correct Batch A NCTs (fast_learning_batch_25.txt) for valid 3-way comparison.* |
| *12* | *E (v12)* | *TBD* | *200* | *—* | *Pending* | *v12* | *—* | *Submit after Batch A v12 validated.* |
| *13* | *F (v12)* | *TBD* | *200* | *—* | *Pending* | *v12* | *—* | |
| *14* | *G (v12)* | *TBD* | *114* | *—* | *Pending* | *v12* | *—* | *Final batch. Completes all 964.* |
| *15* | *Selective re-ann* | *TBD* | *~120* | *—* | *Planned* | *v12* | *—* | *v10 trials where deterministic rules change the result.* |

### Agent version summary

| Version | Commit | Key changes |
|---|---|---|
| v9 | 8d6f236 | Two-pass annotation, deterministic bypass, EDAM system, verification personas |
| v10 | 272503c | delivery_mode: 31 keywords, all-source search, 14B model. clinical_protocol: detailedDescription + armGroups. self_audit: searches agent reasoning. |
| **v11** | **2a1ebba** | **Outcome: expanded deterministic (COMPLETED+hasResults, Phase I guard), confidence=min(quality, sufficiency), tightened prompt. Peptide: _KNOWN_PEPTIDE_DRUGS deterministic True. Self-audit: +outcome, +classification, rebalanced peptide. EDAM: purged 128 bad corrections.** |
| **v11+eff** | **710912f** | **Model-grouped verification (15→3 switches). Unified annotation_model (qwen2.5:14b for all fields). Enhanced progress (field/agent/model/timings in UI). Batched reconciliation.** |
| **v12** | **TBD** | **Outcome: removed Phase I guard (caused 9/9 wrong Unknowns), removed confidence source_sufficiency cap (/2 too aggressive). Failure_reason: removed Withdrawn from skip list (withdrawn trials can have reasons). Self-audit: widened evidence keywords for Positive check. Bug fix: dedup in orchestrator (5 NCTs appeared twice in results JSON), dedup safety net in output_service, concordance/results endpoints derive trial count from actual data.** |

## NCT Coverage

| Set | Count | Status |
|---|---|---|
| Human-annotated (total) | 964 | Target for Phase 1 |
| Batch A+B (v9) | 50 | Complete |
| Batch C+D (v10, jobs #5-6) | 400 | Complete — 120 need selective re-annotation |
| **Batch A test (v11+eff, job #10)** | **25** | **Running — validation job** |
| Remaining (v11, jobs #11-13) | 514 | Pending — submit after Batch A validated |
| Selective re-annotation (job #14) | ~120 | Planned |
| Unannotated (no human ref) | 884 | Phase 5 |

## Concordance History

### v9 Concordance (Batch A, 25 NCTs, job #1)

| Field | vs R1 | vs R2 |
|---|---|---|
| Classification | 91.7% / AC₁ 0.91 | — |
| Peptide | 78.9% / κ 0.41 | — |
| Outcome | 81.8% / κ 0.76 | — |
| Delivery mode | 45.0% / κ 0.34 | — |
| Reason for failure | 60.9% / κ 0.43 | — |

### v10 Concordance (400 NCTs, jobs #5+6)

| Field | vs R1 | vs R2 | Human R1↔R2 | Status |
|---|---|---|---|---|
| Classification | 89.0% / AC₁ 0.883 | 85.2% / AC₁ 0.839 | 91.6% | 0/14 AMP subtypes |
| Reason for failure | **89.4%** / AC₁ 0.891 | **91.5%** / AC₁ 0.912 | 87.2% | **Exceeds human** |
| Peptide | 65.0% / κ 0.274 | 74.2% / κ 0.421 | 83.4% | Under-calling True |
| Delivery mode | 57.3% / κ 0.472 | 63.3% / κ 0.539 | 71.3% | Improved from v9 |
| Outcome | 47.3% / κ 0.287 | 57.7% / κ 0.373 | 56.2% | **Regressed** |

### v11+eff Concordance (job 1ff6092a499c, 25 NCTs — WRONG BATCH)

**CAUTION:** This job used different NCTs than fast_learning_batch_25.txt — only 12/25 overlap with v9 Batch A. Not valid for 3-way comparison.

| Field | vs R1 | vs R2 | vs v9 R1 | Trend |
|---|---|---|---|---|
| Classification | 88.0% / κ -0.06 | 88.0% / κ 0.36 | 92.0% | Stable |
| **Outcome** | **52.0% / κ 0.41** | **60.0% / κ 0.49** | **80.0%** | **Regressed: 9/9 Unknowns wrong. Phase I guard disaster.** |
| Peptide | 76.0% / κ 0.00 | 75.0% / κ 0.00 | 68.2% | Mixed |
| **Delivery mode** | **64.0% / κ 0.48** | **84.0% / κ 0.77** | **44.0%** | **Improved significantly** |
| Reason for failure | 48.0% / κ 0.27 | 60.0% / κ 0.49 | 56.0% | Regressed (cascade from outcome) |

**Root cause analysis (outcome regression):**
- 6/9 wrong Unknowns from Phase I guard deterministic rule (COMPLETED Phase I without hasResults → Unknown)
- 3/9 from LLM also defaulting Unknown (confidence cap too harsh: single-source / 2 = 0.5)
- hasResults is frequently unpopulated even when publications exist
- All 9 Unknowns disagree with BOTH human annotators unanimously

**Root cause analysis (reason_for_failure regression):**
- 5/14 errors are cascade from outcome: Unknown → consistency rule blanks RFR
- 3/14 from Withdrawn trials getting blank RFR (humans annotated real reasons)
- Remaining are legitimate R1/R2 disagreements

**v12 fixes applied:** Phase I guard removed, confidence cap removed, Withdrawn removed from RFR skip list, self-audit evidence keywords widened.

## v11 Efficiency Improvements

| Change | Before | After | Savings |
|---|---|---|---|
| Verification model switches | ~15/trial | ~3/trial | ~30% trial time |
| Annotation model switches | 2-3/trial | 0/trial | ~60-90s/trial |
| Reconciliation | per-field inline | batched (1 load) | Variable |
| Progress reporting | NCT + stage only | Field/agent/model/timings | Visibility |

**Answered:** qwen2.5:14b delivery_mode improved significantly (64% vs 44%). Outcome regression was NOT model-related — caused by deterministic rules and confidence formula.

## v10 → v11 Deterministic Impact Analysis (400 NCTs)

| Fix | NCTs Affected | % |
|-----|---------------|---|
| Phase I guard (Positive→Unknown) | 107 | 27% |
| Known peptide drugs (False→True) | 13 | 3% |
| Total would change | 120 | 30% |

## EDAM Database State (2026-03-23 post-purge)

| Table | Count | Notes |
|---|---|---|
| experiences | 2,715 | v9 epoch 1 (375), v10 epoch 2 (2,340) |
| corrections | 42 | Post-purge |
| stability_index | 2,590 | |
| embeddings | 3,065 | |
| prompt_variants | 0 | |
| config_epochs | 2 → 3 | v11 creates epoch 3 |

### Epoch decay on v11

| Data | Distance | Weight | Floor |
|------|----------|--------|-------|
| v10 experiences | 1 | 75% | 5% |
| v10 corrections | 1 | 80% | 10% |
| v9 experiences | 2 | 56% | 5% |

## Plan

### Phase 1: Validate v12 fixes (NEXT)

v12 fixes applied (Phase I guard removed, confidence cap removed, Withdrawn RFR fix, dedup bug fix).

1. **Commit v12 to dev**, test locally
2. **Re-run Batch A** on correct NCTs (`fast_learning_batch_25.txt`) — job #11
3. **3-way concordance:** v9 (#1) vs v10 (#3) vs v12 (#11) on same 25 NCTs
4. **Expected improvements:**
   - Outcome: should recover to ≥v9 levels (80%+) — Phase I guard was sole cause of 9/9 errors
   - Reason for failure: 5 cascade errors resolve automatically; Withdrawn fix adds ~3 more
   - Delivery mode: should retain v11+eff improvement (64%+)

### Phase 2: Complete 514 remaining NCTs

Submit 3 jobs after v12 validation:
- Job #12: 200 NCTs (batch E)
- Job #13: 200 NCTs (batch F)
- Job #14: 114 NCTs (batch G)

Estimated: ~20h total

### Phase 3: Selective v10 re-annotation

Job #15: ~120 NCTs where v12 deterministic rules change the result

### Phase 4: Full concordance on all 964

Compare across v9/v10/v12 batches. Targets:
- Outcome: >75% (human R1↔R2 = 56.2%)
- Peptide: >80% (human R1↔R2 = 83.4%)
- Classification: AC₁ > 0.90
- Delivery mode: >65%
- Reason for failure: >70%

### Phase 5: Annotate 884 unannotated NCTs

Agent-only, no human counterpart. Full EDAM guidance from 964 validated trials.

## Key Files

| Path | Purpose |
|---|---|
| `CONTINUATION_PLAN.md` | Session pickup instructions |
| `results/edam.db` | EDAM learning database |
| `results/jobs/{job_id}.json` | Job status files |
| `results/annotations/{job_id}/{nct_id}.json` | Per-trial results |
| `results/json/{job_id}.json` | Consolidated output |
| `scripts/human_annotated_ncts.txt` | All 964 NCTs |
| `scripts/fast_learning_batch_50.txt` | Batches A+B (50 NCTs) |
