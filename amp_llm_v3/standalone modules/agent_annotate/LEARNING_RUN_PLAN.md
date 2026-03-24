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

| Set | Count | Status | Notes |
|---|---|---|---|
| Human-annotated (total) | 964 | Target for single-version run | Phase 3 |
| Batch A (v9, job #1) | 25 | Complete | Baseline reference (do not re-run) |
| Batch B (v9, job #2) | 25 | Complete | |
| Batch A repeat (v10, job #3) | 25 | Complete | Same NCTs as job #1 |
| Batch C (v10, job #5) | 200 | Complete | Will be superseded by Phase 3 |
| Batch D (v10, job #6) | 200 | Complete | Will be superseded by Phase 3 |
| Batch A test (v11+eff, job #10c) | 25 | Complete (wrong batch) | Different NCTs — not comparable |
| **Remaining** | **964** | **Pending** | **All will be re-run fresh in Phase 3 single-version run** |
| Unannotated (no human ref) | 884 | Phase 5 | |

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

## EDAM Database State (2026-03-24)

| Table | Count | Notes |
|---|---|---|
| experiences | 2,840 | epoch 1: v9 (375), epoch 2: v10 (2,340), epoch 3: v11+eff (125) |
| corrections | 43 | 28 peptide True→False (may need purge), 10 delivery_mode, 4 outcome, 1 classification |
| stability_index | 2,590 | Cross-run consistency — unreliable (runs on different code versions) |
| embeddings | 3,409 | |
| prompt_variants | 0 | |
| config_epochs | 3 | v9 (epoch 1), v10 (epoch 2), v11+eff (epoch 3) |

### EDAM effectiveness assessment

**EDAM has NOT been the primary driver of improvement.** All major accuracy changes (positive or negative) have come from code changes — deterministic rules, prompt engineering, model selection, confidence formulas. EDAM's 43 corrections across 964+ trials have uncertain marginal impact, and the peptide correction pattern (True→False) has already been shown to be harmful once (128 purged in v11).

**EDAM's role going forward:** Supplementary edge-case memory, NOT the primary improvement loop. Code changes are primary. EDAM experiences from older epochs (v9, v10) may teach patterns that newer code contradicts — epoch decay helps but doesn't fully prevent this.

**Known EDAM risks:**
- 28 remaining peptide True→False corrections may repeat the v11 purge problem
- v11 epoch 3 experiences include wrong Unknowns from Phase I guard (now removed in v12)
- Stability index tracks consistency across runs on DIFFERENT code versions — misleading signal

## Plan

### Approach: Code-first iteration, EDAM supplementary

**Key principle:** Agents improve primarily through code changes (prompts, rules, models, logic) analyzed via concordance after each run. EDAM captures edge-case patterns the code can't handle deterministically. Do NOT run large batches until the code is stable — each code change invalidates prior runs and wastes compute.

**Convergence criteria for "code stable":** Two consecutive Batch A runs (25 NCTs) with <2% concordance change between them across all fields.

### Phase 1: Iterate on Batch A until stable (NEXT)

**Run v12 Batch A** on correct NCTs (`fast_learning_batch_25.txt`):
```bash
cd "/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/amp_llm_v3/standalone modules/agent_annotate"
NCT_IDS=$(python3 -c "
with open('scripts/fast_learning_batch_25.txt') as f:
    ncts = [l.strip() for l in f if l.strip()]
import json; print(json.dumps(ncts))
")
curl -s -X POST http://localhost:8005/api/jobs \
  -H 'Content-Type: application/json' \
  -d "{\"nct_ids\": $NCT_IDS}"
```

After each run:
1. **3-way concordance** vs v9 (#1) + v10 (#3) on same 25 NCTs
2. **Error analysis**: categorize each disagreement as code-fixable vs edge-case
3. **If code-fixable**: implement fix, bump version, re-run Batch A (~3h/cycle)
4. **If edge-case only**: EDAM is handling it, move to Phase 2
5. **Expected v12 targets on Batch A:**
   - Outcome: ≥80% vs R1 (was 80% in v9, 52% in v11 — Phase I guard removed)
   - Delivery mode: ≥60% vs R1 (was 64% in v11+eff — model improvement retained)
   - Reason for failure: ≥60% vs R1 (cascade errors resolve with outcome fix)
   - Classification: ≥90% vs R1 (stable across versions)
   - Peptide: ≥75% vs R1 (v10 was 82%, check if v12 retains)

### Phase 2: Expand to Batch A+B (50 NCTs)

Once Batch A meets targets:
1. Run on 50 NCTs (`fast_learning_batch_50.txt`) to confirm improvements generalize
2. Minor code tweaks only — no major rewrites
3. If concordance holds, proceed to Phase 3

### Phase 3: Full 964-NCT single-version run

**Run ALL 964 human-annotated NCTs in one version** — no piecemeal batches across different code versions.
- Submit 4-5 jobs (200 NCTs each) sequentially
- ~40h total (~460s/trial)
- This gives a clean, single-version concordance across the entire dataset
- **No selective re-annotation** — everything is fresh on the same code

**Targets (full 964):**
- Outcome: >70% vs R1 (human R1↔R2 = 56.2%)
- Peptide: >75% vs R1 (human R1↔R2 = 83.4%)
- Classification: AC₁ > 0.88
- Delivery mode: >60% vs R1 (human R1↔R2 = 71.3%)
- Reason for failure: >80% vs R1 (v10 already hit 89.4%)

### Phase 4: EDAM cleanup + final calibration

After Phase 3 concordance:
1. **Purge EDAM:** Remove all experiences/corrections from epochs 1-3 (v9/v10/v11). These were generated by inferior code and may teach wrong patterns.
2. **Seed EDAM fresh** from Phase 3 results — clean epoch with stable code
3. **Re-run Batch A** one more time to measure EDAM-only impact (code unchanged)
4. If EDAM helps: keep. If neutral or harmful: disable EDAM injection for Phase 5.

### Phase 5: Annotate 884 unannotated NCTs

Agent-only, no human counterpart. Final code version + clean EDAM (if validated).
- Submit 4-5 jobs (200 NCTs each)
- ~40h total
- No concordance possible (no human reference) — rely on review queue for quality

### What NOT to do anymore

- **Don't run 200+ NCT batches during active code iteration** — they'll be invalidated by the next fix
- **Don't selectively re-annotate** subsets from older versions — re-run everything fresh when stable
- **Don't trust EDAM corrections from pre-v12 epochs** — the code they learned from had known bugs
- **Don't add EDAM experiences for fields with deterministic outcomes** (Recruiting, Withdrawn, Terminated) — the code handles these perfectly, EDAM noise can only hurt

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
