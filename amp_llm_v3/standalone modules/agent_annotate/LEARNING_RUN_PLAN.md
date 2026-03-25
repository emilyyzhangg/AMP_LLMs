# EDAM Learning Run Plan

**Last updated:** 2026-03-25

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
| 10c | A test (wrong batch) | 1ff6092a499c | 25 | 25/25 | **Complete** | v11+eff | — | Wrong NCTs. Outcome 52%. Results wiped. |
| 11 | A (v12 baseline) | cdcfc68c191d | 25 | 25/25 | **Complete** | v12 | — | 5-field only (pre-sequence). Outcome 72%, RFR 80%, classification 92%. Results wiped. |
| 12 | A (v12+fixes) | 713c1c77385b | 25 | 5/25 | **Cancelled** | v12+fixes | — | Had Mode D, thresholds, AMP→peptide. Cancelled for reasoning-first upgrade. |
| 13 | A (v12+fixes) | 7b9d0f1fc270 | 25 | 5/25 | **Cancelled** | v12+fixes | — | Same. Cancelled for full reasoning-first stack. |
| 14 | A (v12+reasoning) | ba1689125a8f | 25 | ?/25 | **Lost** | v12+reasoning | — | Server restarted, results not saved. EDAM epoch 1. |
| 15 | A (v14) | 2c0c0d3a8a73 | 25 | 25/25 | **Complete** | v14 | — | v14 sequence overhaul. |
| 16 | A (v15) | c3fa1fbba5c2 | 25 | 25/25 | **Complete** | v15 | — | peptide=False→N/A cascade, investigational drug rename. 142 min. See concordance below. |
| **17** | **A (v16)** | **25366ac24587** | **25** | **—** | **Running** | **v16** | **TBD** | **Sequence fix, outcome heuristics, peptide gate, multi-route, RfF gate, AC1 docs.** |
| *18* | *A+B (50 NCTs)* | *TBD* | *50* | *—* | *Pending* | *v16+* | *—* | *Phase 2: expand to 50 after Batch A converges.* |
| *19* | *Full 964* | *TBD* | *964* | *—* | *Pending* | *v16+* | *—* | *Phase 3: single-version full run.* |
| *20* | *884 unannotated* | *TBD* | *884* | *—* | *Phase 5* | *v16+* | *—* | *Agent-only, no human reference.* |

### Agent version summary

| Version | Commit | Key changes |
|---|---|---|
| v9 | 8d6f236 | Two-pass annotation, deterministic bypass, EDAM system, verification personas |
| v10 | 272503c | delivery_mode: 31 keywords, all-source search, 14B model. clinical_protocol: detailedDescription + armGroups. self_audit: searches agent reasoning. |
| **v11** | **2a1ebba** | **Outcome: expanded deterministic (COMPLETED+hasResults, Phase I guard), confidence=min(quality, sufficiency), tightened prompt. Peptide: _KNOWN_PEPTIDE_DRUGS deterministic True. Self-audit: +outcome, +classification, rebalanced peptide. EDAM: purged 128 bad corrections.** |
| **v11+eff** | **710912f** | **Model-grouped verification (15→3 switches). Unified annotation_model (qwen2.5:14b for all fields). Enhanced progress (field/agent/model/timings in UI). Batched reconciliation.** |
| **v12** | **90fc475** | **Outcome: removed Phase I guard, removed confidence cap. Failure_reason: Withdrawn gets LLM. Self-audit: widened keywords. Bug fix: dedup.** |
| **v12+seq** | **30b7171** | **Sequence as 6th field (deterministic). Peptide 2-50 AA single-chain. Sequence→peptide cross-validation.** |
| v12+reasoning | bb2c6fb | Layer 1: Drug name resolution via LLM, cached in EDAM. Layer 2: Structured Pass 1→2 handoff, rebalanced prompts, per-field temperature. Layer 3: UniProt AA→peptide, AMP→peptide cross-validation. AMP Mode D re-added (pathogen vaccines). Mode A expanded (growth inhibition). Evidence thresholds 2→1. Multi-drug peptide bypass fixed. EDAM learns from consistency overrides, reconciliation, drug names, reasoning patterns. Grouped concordance toggle. Agreement Metrics (AC₁ primary). SerpAPI removed. |
| v14 | 2c412d5 | Sequence agent overhaul: structured-data-only extraction (no snippet parsing). Reads from DBAASP, APD, ChEMBL HELM, UniProt, EBI. Score/rank candidates, optional LLM adjudication. |
| v15 | 6240670 | peptide=False → N/A all fields cascade. "active drug" → "investigational drug" rename. Bucketed concordance (broad categories). |
| **v16** | **8223691** | **Sequence fix (critical): metadata passed to all agents, raw_data key fallback, prefix stripping. Outcome: adverse-event keyword detection, publications as H1 corroboration, negative valence→Failed. Peptide cascade requires conf≥0.90. Delivery: multi-route support. RfF: "Unknown" removed from skip list. AC₁ reporting in docs.** |

## NCT Coverage

**All prior results wiped on 2026-03-24.** Concordance numbers from v9/v10 preserved in Concordance History above for reference only.

| Set | Count | Status | Notes |
|---|---|---|---|
| Human-annotated (total) | 964 | Target for single-version run | Phase 3 |
| Batch A (`fast_learning_batch_25.txt`) | 25 | **Next: v12 run** | Phase 1 iteration target |
| Batch A+B (`fast_learning_batch_50.txt`) | 50 | Pending | Phase 2 expansion |
| Full 964 | 964 | Pending | Phase 3 single-version run |
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

### v15 Concordance (Batch A, 25 NCTs, job c3fa1fbba5c2) — 2026-03-25

| Field | vs R1 | κ(R1) | vs R2 | κ(R2) | R1↔R2 | Target | Status |
|---|---|---|---|---|---|---|---|
| Classification | 83.3% | -0.04 | 87.5% | 0.35 | 88.0% | ≥90% | AC₁=0.82; prevalence paradox |
| Delivery Mode | 69.6% | 0.56 | 73.9% | 0.62 | 76.0% | ≥60% | **Exceeded.** Bucketed: 95.7% |
| Outcome | 78.3% | 0.72 | 69.6% | 0.62 | 80.0% | ≥80% | Close. 4 Unknown errors. |
| Reason for Failure | 84.0% | 0.77 | 80.0% | 0.72 | 88.0% | ≥60% | **Exceeded significantly** |
| Peptide | 86.4% | 0.33 | 75.0% | 0.00 | 83.3% | ≥75% | **Exceeded vs R1** |
| Sequence | 0.0% | N/A | 0.0% | N/A | 70.6% | TBD | **Broken — fixed in v16** |

**Root cause analysis:**
- **Sequence 0%:** Agent received `metadata=None` → zero intervention names → zero candidates. Fixed in v16: pass shared_metadata to all agents, add raw_data key fallback, strip BIOLOGICAL:/DRUG: prefixes.
- **Outcome 4× Unknown:** NCT00000886 (paper shows toxicity but agent missed), NCT00972569, NCT02660736, NCT02665377. v16 adds adverse-event keyword detection in fallback heuristic.
- **Peptide 2× false-negative cascade:** NCT02624518 and NCT02654587 incorrectly False'd → N/A wiped all fields. v16 requires confidence ≥0.90 for cascade.
- **Classification low kappa:** Prevalence paradox — 20/25 trials are "Other". AC₁=0.82 confirms strong agreement. No code fix needed.
- **Delivery sub-category splits:** Most disagreements are IV vs SC/IM within injection family. Bucketed agreement is 95.7%. v16 adds multi-route support for combination trials.

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

## EDAM Database State (2026-03-25)

| Table | Count | Notes |
|---|---|---|
| experiences | 300 | From v14/v15 runs (jobs 2c0c0d3a8a73 + c3fa1fbba5c2) |
| corrections | 23 | Consistency overrides + reconciliation |
| drug_names | 87 | Cached drug name resolutions |
| stability_index | 125 | Cross-run comparisons |
| config_epochs | 1 | |

### EDAM History

EDAM was wiped clean on 2026-03-24 (all prior v9-v11 data discarded due to known code bugs). Current data is from v14/v15 runs on Batch A. v16 code changes may invalidate some corrections (especially peptide and outcome patterns), but drug_names and stability_index remain valid.

**EDAM's role going forward:** Supplementary edge-case memory, NOT the primary improvement loop. Code changes are primary. EDAM will learn ONLY from v12+ runs on stable code.

## v16 Validation Keys to Watch (job 25366ac24587)

When this job completes, check these specific items in order of priority:

### 1. Sequence — was it fixed? (Critical)
- v15: 0/25 sequences extracted (completely broken)
- v16 fix: metadata now passed to sequence agent, raw_data key fallback, prefix stripping
- **Pass if:** ≥10/25 trials have a non-empty sequence (human R1 had 17/25, R2 had 21/25)
- **Check specific NCTs:** NCT00972569 (BNP — DBAASP has 3 sequences + ChEMBL HELM), NCT02665377 (Angiotensin — UniProt has entries)
- **If still 0:** raw_data keys are changing format again, or research agents aren't populating structured data

### 2. Outcome — do adverse-event heuristics help? (High)
- v15: 4 trials returned "Unknown" where humans said "Failed" or "Positive"
- v16 fix: adverse-event keyword detection, publications as H1 corroboration, negative valence→Failed
- **Pass if:** ≥80% vs R1 (v15 was 78.3%)
- **Check specific NCTs:** NCT00000886 (PubMed paper about "unacceptable reactogenicity" — should now trigger "Failed"), NCT02660736 (should be "Positive")

### 3. Peptide — does confidence gate prevent false-negative wipeout? (High)
- v15: NCT02624518 and NCT02654587 incorrectly False'd, wiping all fields via N/A cascade
- v16 fix: require confidence ≥0.90 for cascade
- **Pass if:** These two trials now have non-N/A annotations for classification/delivery/outcome
- **Regression risk:** If the peptide agent still returns False with conf≥0.90, the cascade will still fire. Check the actual confidence values.

### 4. Reason for Failure — does Unknown-gate removal help? (Medium)
- v15: Agent missed "Toxic/Unsafe" (NCT00000886) and "Ineffective" (NCT00972569, NCT02665377)
- v16 fix: "Unknown" removed from pre-check skip list
- **Pass if:** ≥84% vs R1 (v15 was 84.0% — should hold or improve)
- **Regression risk:** If outcome still returns "Unknown" for these trials, the fix won't help. But if outcome correctly returns "Failed", RfF should investigate and find the failure reason.

### 5. Delivery Mode — does multi-route help? (Low)
- v15: 69.6% strict, 95.7% bucketed
- v16 fix: multi-route support in Pass 2 prompt
- **Pass if:** ≥70% strict (slight improvement from multi-route trials)
- **Check:** NCT05415410 and NCT06126354 — do they now list multiple routes?

### 6. Convergence check
- Compare v16 concordance vs v15 for all fields except sequence
- **If <2% change on all non-sequence fields:** code is stable → proceed to Phase 2 (50 NCTs)
- **If any field regresses >3%:** investigate, fix, re-run Batch A

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
5. **v16 targets on Batch A** (updated from v15 concordance analysis):
   - Outcome: ≥80% vs R1 (v15 was 78.3% — v16 adverse-event heuristics should close gap)
   - Delivery mode: ≥70% strict, ≥95% bucketed vs R1 (v15 was 69.6%/95.7%)
   - Reason for failure: ≥84% vs R1 (v15 was 84.0% — v16 Unknown-gate removal may improve)
   - Classification: AC₁ ≥0.85 (v15 was AC₁=0.82 — kappa unreliable due to prevalence)
   - Peptide: ≥85% vs R1 (v15 was 86.4% — v16 confidence gate protects against false-neg cascade)
   - **Sequence: >0%** (v15 was 0% — v16 fixes the root cause, expect first real sequences)

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
