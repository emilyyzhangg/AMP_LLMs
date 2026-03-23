# EDAM Learning Run Plan

**Last updated:** 2026-03-23 ~18:30

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
| **10** | **A test** | **19a39aa475a3** | **25** | **0/25** | **Running** | **v11+eff** | **TBD** | **3-way comparison: v9 vs v10 vs v11. Tests model-grouped verification + unified annotation_model.** |
| *11* | *E (v11)* | *TBD* | *200* | *—* | *Pending* | *v11+eff* | *—* | *Submit after Batch A results confirmed.* |
| *12* | *F (v11)* | *TBD* | *200* | *—* | *Pending* | *v11+eff* | *—* | |
| *13* | *G (v11)* | *TBD* | *114* | *—* | *Pending* | *v11+eff* | *—* | *Final batch. Completes all 964.* |
| *14* | *Selective re-ann* | *TBD* | *~120* | *—* | *Planned* | *v11+eff* | *—* | *v10 trials where v11 deterministic rules change the result.* |

### Agent version summary

| Version | Commit | Key changes |
|---|---|---|
| v9 | 8d6f236 | Two-pass annotation, deterministic bypass, EDAM system, verification personas |
| v10 | 272503c | delivery_mode: 31 keywords, all-source search, 14B model. clinical_protocol: detailedDescription + armGroups. self_audit: searches agent reasoning. |
| **v11** | **2a1ebba** | **Outcome: expanded deterministic (COMPLETED+hasResults, Phase I guard), confidence=min(quality, sufficiency), tightened prompt. Peptide: _KNOWN_PEPTIDE_DRUGS deterministic True. Self-audit: +outcome, +classification, rebalanced peptide. EDAM: purged 128 bad corrections.** |
| **v11+eff** | **710912f** | **Model-grouped verification (15→3 switches). Unified annotation_model (qwen2.5:14b for all fields). Enhanced progress (field/agent/model/timings in UI). Batched reconciliation.** |

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

### v11+eff Concordance (Batch A, 25 NCTs, job #10) — PENDING

Will be compared directly against v9 Batch A results on the same 25 NCTs.

## v11 Efficiency Improvements

| Change | Before | After | Savings |
|---|---|---|---|
| Verification model switches | ~15/trial | ~3/trial | ~30% trial time |
| Annotation model switches | 2-3/trial | 0/trial | ~60-90s/trial |
| Reconciliation | per-field inline | batched (1 load) | Variable |
| Progress reporting | NCT + stage only | Field/agent/model/timings | Visibility |

**Open question:** Does qwen2.5:14b (unified annotation_model) perform the same as llama3.1:8b for outcome and failure_reason? Batch A test will answer this.

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

### Phase 1: Validate v11+efficiency (in progress)

Batch A test job running (`19a39aa475a3`). When complete:
1. Run 3-way concordance: v9 (#1) vs v10 (#3) vs v11 (#10) on same 25 NCTs
2. Compare timing (v9 was 180s/trial avg)
3. Evaluate qwen2.5:14b impact on outcome/failure_reason
4. Decision: proceed or adjust annotation_model config

### Phase 2: Complete 514 remaining NCTs

Submit 3 jobs after validation:
- Job #11: 200 NCTs (batch E)
- Job #12: 200 NCTs (batch F)
- Job #13: 114 NCTs (batch G)

Estimated: ~20h total (was ~31h before efficiency improvements)

### Phase 3: Selective v10 re-annotation

Job #14: ~120 NCTs where v11 deterministic rules change the result

### Phase 4: Full concordance on all 964

Compare across v9/v10/v11 batches. Targets:
- Outcome: >65% (human R1↔R2 = 56.2%)
- Peptide: >80% (human R1↔R2 = 83.4%)
- Classification: AC₁ > 0.90
- Delivery mode: >65%

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
