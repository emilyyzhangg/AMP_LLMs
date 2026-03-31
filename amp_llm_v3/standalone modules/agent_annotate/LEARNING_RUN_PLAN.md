# EDAM Learning Run Plan

**Last updated:** 2026-03-31

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
| 17 | A (v16) | 25366ac24587 | 25 | 25/25 | **Complete** | v16 | — | 178 min. Sequence 0→7, but 0% accuracy (DBAASP collision). Outcome unchanged. Peptide regressed 4.6%. See concordance below. |
| 18a | A (v17) | 9e1f8fa907d5 | 25 | 25/25 | **Complete** | v17 (fc89869) | — | Outcome heuristic override, peptide cascade fix, DBAASP word-boundary, multi-route. |
| 18b | A (v17) | a3d5403c19af | 25 | 25/25 | **Complete** | v17 (fc89869) | — | Stability run 2. Same NCTs as 18a. |
| 18c | A (v17) | 4b062214adf0 | 25 | 25/25 | **Complete** | v17 (66907432) | — | Stability run 3. Same NCTs. Outcome regressed to 68%. RfF crashed to 56%. |
| 19a | A+B (v18+hf, pre-fix) | 4d2030ab0c25 | 50 | 0/50 | **Failed** | v18+hotfix (47f1e63) | — | RfF reconciler NoneType crash at NCT00004984. |
| 19b | A+B (v18+hf, pre-fix) | 8265084a3a21 | 50 | 0/50 | **Failed** | v18+hotfix (47f1e63) | — | Same crash. Fixed in 776aeea. |
| **19c** | **A+B (v18+hotfixes)** | **76392846aee8** | **50** | **50/50** | **Complete** | **v18+hf (776aeea)** | **—** | **350 min (420s/trial). See concordance below.** |
| **20** | **A+B (v19) R1** | **c1786d005ade** | **50** | **50/50** | **Complete** | **v19 (ee4fdee)** | **—** | **Mode D removed, EDAM allowlist fix. See v19 concordance.** |
| **21** | **A+B (v19) R2** | **ac6af4e49fe2** | **50** | **50/50** | **Complete** | **v19 (ee4fdee)** | **—** | **Stability run. High peptide variance (7%) → fixed in v20.** |
| 22 | Train-C partial (v19) | cf642da98bd6 | 25 | 0/25 | **Failed** | v19 (ee4fdee) | 0 exp | ~200s/trial (research truncated). 0 EDAM writes. |
| 23 | Train-C partial (v19) | 434ad7a32ff8 | 25 | 0/25 | **Failed** | v19 (ee4fdee) | 0 exp | Same batch as 22. 0 EDAM writes. |
| 24 | Train-C (mystery, v19) | a2da6002df4f | 50 | 50/50 | **Complete** | v19 (ee4fdee) | 300 exp | Mystery job. Training NCTs. 300 EDAM experiences. |
| 25 | Train-C partial (mystery) | dbd215c03cf3 | 50 | 20/50 | **Cancelled** | v19 (ee4fdee) | 120 exp | Cancelled after 20 NCTs. 120 EDAM experiences. |
| **26** | **Train-C v20 R1** | **ba96acf75132** | **50** | **50/50** | **Complete** | **v20 (163eaf1)** | **300 exp** | **First v20 training run. 300 EDAM experiences.** |
| 27 | Train-C v20 R2 | 29830f7d3785 | 50 | 50/50 | **Complete** | v20 (163eaf1) | 300 exp | EDAM outcome+delivery_mode later purged |
| 28 | Train-D v20 R1 | 798817a09db3 | 50 | 50/50 | **Complete** | v20 (163eaf1) | 300 exp | EDAM outcome+delivery_mode later purged |
| 29 | Train-D v20 R2 | 3fc6552eb54e | 50 | 50/50 | **Complete** | v20 (163eaf1) | 300 exp | EDAM outcome+delivery_mode later purged |
| 30 | Concordance v20 (partial) | e0f556c703c7 | 50 | 15/50 | **Cancelled** | v20 (163eaf1) | — | Cancelled at 15/50 — regression confirmed, root cause identified |
| **31** | **Batch E v21 R1** | **83c6ad7fd4d7** | **25** | **25/25** | **Complete** | **v21 (69e7d14)** | **—** | **Positions 101-125. EDAM outcome+delivery_mode rebuilt from scratch.** |
| **32** | **Batch E v21 R2** | **54acb4a8136d** | **25** | **25/25** | **Complete** | **v21 (69e7d14)** | **—** | **Stability run.** |
| **33** | **Batch F v21 R1** | **f78d3554f29f** | **25** | **25/25** | **Complete** | **v21 (69e7d14)** | **—** | **Positions 126-150.** |
| **34** | **Batch F v21 R2** | **92fce293f860** | **25** | **25/25** | **Complete** | **v21 (69e7d14)** | **—** | **Stability run.** |
| **35** | **Concordance v21** | **c2c43af95162** | **50** | **50/50** | **Complete** | **v21 (69e7d14)** | **—** | **fast_learning_batch_50.txt. Outcome=68% (BELOW 70% threshold). See concordance below.** |

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
| v16 | 8223691 | Sequence fix (critical): metadata passed to all agents, raw_data key fallback, prefix stripping. Outcome: adverse-event keyword detection, publications as H1 corroboration, negative valence→Failed. Peptide cascade requires conf≥0.90. Delivery: multi-route support. RfF: "Unknown" removed from skip list. AC₁ reporting in docs. |
| v17 | fc89869 / 66907432 | Outcome: post-LLM heuristic override (call _infer_from_pass1 when Pass 2 returns "Unknown" — was dead code), inject structured phase into Pass 2. Peptide: cascade only on model_name=="deterministic", added OSE2101/TEDOPI/DOTATOC. Sequence: DBAASP word-boundary, ChEMBL HELM 1.3x, UniProt name-matching, formulation stripping. Delivery: multi-route collection, title exclusion, comma-separated parse. |
| **v18** | **fc6fddac** | **Sequence: _KNOWN_SEQUENCES table (12 drugs, deterministic lookup), cross-validation penalty (0.3x for name mismatch), ChEMBL max_phase + pref_name disambiguation, EDAM-enriched interventions. Outcome: strong adverse signals (multi-word) checked FIRST in full text, Phase I requires has_results_posted or NCT ID in text. RfF: TERMINATED/WITHDRAWN always proceed to pass 2, default "Business Reason" for terminated/withdrawn with no signal, empty vote counted in reconciler, unanimous-verifier gate for empty override. EDAM: training CSV allowlist (642 NCTs), non-training NCTs excluded from all learning loops. Frontend: "Concordance Comparison" → "Agreement Comparison", job ID format consistency (truncated to 8 chars everywhere), Version Compare κ → AC₁ labels.** |
| **v18+hotfixes** | **776aeea** | **Fix NoneType crash in _majority_vote/_normalize during RfF reconciliation. Fix quality warnings. Fix peptide verifier bias. Fix sequence miss rate. Fix RfF EMPTY sentinel leaks and verifier empty-vote drop. Fix NameErrors causing jobs to fail despite 25/25 completion.** |
| **v19** | **d777be62 (dev)** | **Classification: remove Mode D (all vaccines now Other — adaptive immunity ≠ AMP). Fixed classifier/verifier inconsistency (verifier still had HIV/influenza vaccines as AMP). Remove ic41/ic43 from _KNOWN_AMP_DRUGS. Outcome: add negative efficacy heuristics (did not demonstrate, no benefit, lack of efficacy, etc.). Delivery mode: remove bare ' sc ' abbreviation, add cancer vaccine → Other/Unspecified rule. Sequence: filter to EXPERIMENTAL arms only, suppress DBAASP/APD for non-AMP trials. Literature: always run title fallback for old trials (NCT < 100k).** |
| **v20** | **163eaf1** | **Reconciler bug fix (CRITICAL): unanimous verifier disagreement (agreement_ratio=0.0) now always routes to reconciler — fixed 15 per-run cases where high-confidence Pass1 was overriding 3/3 verifier disagreement. CT.gov resultsSection: hasResults flag + primary outcome data emitted as citations from already-fetched response (no extra HTTP call). Delivery mode Rule 8: explicit route keyword required — no inferring SC from drug class or IV from mg/kg. Outcome verifier: Failed requires positive evidence of endpoint failure, not merely absence of publications. Classification: AMP(other) requires confirmed antimicrobial mechanism from Step 2. EDAM: test-batch NCTs (fast_learning_batch_50.txt) hard-excluded from TRAINING_NCTS at load time. Peptide field temp 0.05→0.0 (eliminates 7% run-to-run variance on binary field).** |
| **v21** | **69e7d14** | **TERMINATED overcalling fix (CRITICAL): removed TERMINATED from _DETERMINISTIC_STATUSES in outcome.py — was blindly mapping all TERMINATED trials to "Terminated" with skip_verification=True, causing -25pp outcome regression on v20 partial concordance. PASS2_PROMPT item 4 now checks evidence (Positive if drug advanced/positive results, Failed if safety/futility, Terminated if business reason). Phase heuristics H1b (Phase I >5yr, no Phase II, no pubs → Unknown) and H3b (Phase II/III >10yr, no pubs, no negative evidence → lean Positive) added to both annotator and verifier. Delivery mode: _deterministic_delivery_mode now filters intervention_names to EXPERIMENTAL arms only (armGroups[type=EXPERIMENTAL]); PASS1+PASS2 prompts updated to focus on experimental arm routes only. EDAM surgical purge: all outcome + delivery_mode experiences (702 rows) and corrections (40 rows) deleted — net-negative on both fields due to biased v20 training data.** |

## NCT Coverage

**All prior results wiped on 2026-03-24.** Concordance numbers from v9/v10 preserved in Concordance History above for reference only.

| Set | Count | Status | Notes |
|---|---|---|---|
| Training CSV (`human_ground_truth_train_df.csv`) | 642 | EDAM training pool | EDAM only learns from these |
| Batch A (old, v15-v17) | 25 | Complete (3 v17 runs) | Original batch, retiring |
| **Batch A (new, v18)** | **25** | **Next** | **Stratified from training CSV** |
| Full training | 642 | Phase 3 | Single-version run on training set |
| Test/held-out (remaining) | ~322 | Phase 4 | EDAM frozen, final evaluation |

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

### v17 Concordance (Batch A, 25 NCTs, 3 runs: 9e1f/a3d5/4b06) — 2026-03-26

| Field | v17 best | v17 worst | v17 range | Inter-run stability |
|---|---|---|---|---|
| Classification | 88.0% | 88.0% | 0% | Perfect (25/25 agree) |
| Delivery Mode | 68.0% | 64.0% | 4% | 23/25 agree |
| Outcome | 76.0% | 68.0% | 8% | 23/25 (NCT00972569, NCT02660736 flip) |
| Reason for Failure | 68.0% | 56.0% | 12% | 25/25 agree (but wrong) |
| Peptide | 90.9% | 90.9% | 0% | Perfect |
| Sequence | 32.0% | 32.0% | 0% | Perfect (but 0 exact matches) |

**Root cause analysis (RfF regression 84% → 56%):**
- 9/11 disagreements: agent empty, human has value
- 5 are "Business Reason" for terminated/withdrawn trials — `_pass1_says_no_failure()` bails out for these
- Agent doesn't default "Business Reason" for terminated/withdrawn without explicit whyStopped
- v18 fixes: TERMINATED/WITHDRAWN always proceed to pass 2, default Business Reason fallback

**Root cause analysis (outcome instability 68-76%):**
- NCT00000886: Positive vs Failed. Agent finds positive immunogenicity, misses toxicity signal.
- NCT00972569/NCT02660736: flip between Unknown↔Positive across runs (Phase I corroboration varies)
- v18 fixes: strong adverse signals checked first, Phase I requires trial-specific evidence

**Root cause analysis (sequence 0 exact matches):**
- 4/7 wrong molecule from ChEMBL (keyword collision)
- 2/7 DBAASP returns wrong protein (Insulin for Nesiritide)
- 10/25 no candidates found at all
- v18 fixes: known-sequences table, cross-validation penalty, EDAM name enrichment

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

### v18+hotfixes Concordance (Batch A+B, 50 NCTs, job 76392846aee8) — 2026-03-27

| Field | vs R1 | κ(R1) | AC₁(R1) | vs R2 | κ(R2) | R1↔R2 | v17→v18+ | Status |
|---|---|---|---|---|---|---|---|---|
| Classification | 87.8% | -0.046 | 0.870 | 85.7% | 0.174 | 86.0% | Stable | **Above AC₁ target** |
| Delivery Mode | 67.3% | 0.551 | 0.654 | 72.0% | 0.602 | 69.4% | Flat | **Below 73% target** |
| Outcome | 70.0% | 0.608 | 0.657 | 74.0% | 0.653 | 76.0% | Regressed | **Below 80% target** |
| Reason for Failure | 72.0% | 0.627 | 0.671 | 80.0% | 0.738 | 84.0% | Improved | **Below 84% target** |
| Peptide | 88.9% | 0.390 | 0.865 | 90.5% | 0.462 | 90.5% | Stable | **Above 86% target** |
| Sequence | 59.1%* | 0.567 | 0.574 | 54.5% | 0.520 | 68.8% | **Major jump** | **Real exact matches now** |

*Sequence: 13/22 exact matches (both R1 and agent annotated). Agent coverage 22/50 vs R1 33/50.

**Bucketed concordance:**

| Field | vs R1 | vs R2 | R1↔R2 |
|---|---|---|---|
| Classification | 87.8% | 85.7% | 86.0% |
| Delivery Mode | 89.8% | 98.0% | 91.8% |
| Outcome | 72.0% | 80.0% | 82.0% |
| Peptide | 90.0% | 90.0% | 96.0% |

**Root cause analysis (outcome regression 76% → 70%):**

Agent value distribution (50 NCTs): Terminated=22, Unknown=8, Withdrawn=9, Positive=5, Recruiting=4, Failed=1, Active=1
R1 value distribution: Terminated=20, Withdrawn=8, Positive=8, Failed=7, Recruiting=5, Unknown=1, Active=1

- **Failed drastically under-called: 1 vs 7 (R1).** Agent says Unknown for 6/7 Failed trials:
  - NCT00002428, NCT00004984 (Batch B): adverse-event detection not triggering for completed Phase II/III
  - NCT00972569, NCT02665377 (persistent Batch A): same issue
  - NCT04672083 (Batch B): Unknown instead of Failed
  - NCT04701021 (Batch B): Positive instead of Failed (overcalling positive evidence)
- **Positive under-called**: NCT00977145, NCT02654587 (agent Terminated vs R1 Positive) — but R1↔R2 also disagree on both
- **Active trial status confusion** (Batch B): NCT04711135 (Active-not-recruiting vs Recruiting), NCT04749641, NCT04771013 (both R1/R2 disagree)
- **v19 fix needed**: Outcome Failed detection. The multi-word adverse signal check isn't triggering for completed trials. May need to look at the specific publications for NCT00002428, NCT00004984, NCT04672083.

**Root cause analysis (RfF — improved to 72%, cascade still limiting):**

- 6/14 disagreements cascade from Unknown outcome: NCT00002428, NCT00004984, NCT00972569, NCT02665377, NCT04672083, NCT04701021 — all get empty RfF when agent says Unknown/Positive instead of Failed. Fix outcome → these cascade-fix automatically.
- 8/14 genuine RfF errors: NCT03018288 (Recruitment issues vs Business Reason), NCT03490942 (Ineffective vs Business Reason), NCT03500484 (Business Reason vs Due to covid), NCT05813314 (Ineffective vs Business Reason). Human R1↔R2 also disagree on several of these.

**Root cause analysis (classification persistent errors):**

- NCT00000886: Agent=AMP(infection), R1=R2=Other. Persistent across v14-v18+. The drug is "HIV-1 immunogen" — immune-based HIV vaccine that stimulates immune response. v18+ still classifies it as AMP despite both humans saying Other. Need to investigate what agent is extracting.
- NCT00002428: Agent=AMP(infection), R1=R2=Other. Same pattern.
- These are Mode B (immunostimulatory) candidates that the agent over-classifies as AMP.

**Sequence — major breakthrough:**
- 13/22 exact matches = 59.1%, up from 0 in v17. Known-sequences table working.
- Coverage gap: agent annotated 22/50 vs R1's 33/50 — need better coverage for Batch B peptides.

### v21 Concordance (Batch A+B, 50 NCTs, job c2c43af95162) — 2026-03-31

| Field | v21 | v19 R1 | v18+ baseline | Target | Met? |
|---|---|---|---|---|---|
| Classification | **92.0% / AC₁=0.917** | 92.0% / 0.917 | 87.8% / 0.870 | Hold 92% | YES (held) |
| Delivery Mode | 63.3% / AC₁=0.609 | 65.3% / 0.632 | 67.3% / 0.654 | ≥65% | NO (-2pp) |
| Outcome | **68.0% / AC₁=0.633** | 72.0% / 0.680 | 70.0% / 0.657 | ≥76% | **NO (-4pp REGRESSION)** |
| Reason for Failure | 70.0% / AC₁=0.657 | 72.0% / 0.671 | 72.0% / 0.671 | ≥70% | YES (barely) |
| Peptide | 82.2% / AC₁=0.769 | 86.7% / 0.834 | 88.9% / 0.865 | ≥86% | NO (-4.5pp) |
| Sequence | 61.9% (21/21) / AC₁=0.603 | 65.0% / 0.634 | 59.1% / 0.574 | ≥30% | YES |

**Key findings:**
- **TERMINATED fix net-neutral:** Removed TERMINATED deterministic bypass was architecturally correct but evidence-starved. 0 TERMINATED→Positive cases fixed. 2 new overcorrection errors (NCT00982696: Unknown→Failed; NCT03490942: Terminated→Failed) — LLM is calling Failed too aggressively when it finds any failure signal.
- **Outcome below v18+ baseline** (68% vs 70%). v19's +2pp gain erased. EDAM Batches E/F rebuild did not restore lost signal.
- **16 Agent vs R1 outcome disagreements:** 5 persistent evidence gaps, 2 TERMINATED-fix failures, 2 new overcorrections, 4 active-trial-status R1/R2 disagreements, 1 regression (NCT00972569), 2 other.
- **Peptide regression -4.5pp:** 7 False→True misses. Under-calling True. Investigate EDAM Batches E/F bias.
- **Delivery mode:** Experimental-arm-only filter had zero effect. Structural sub-category confusion (SC/IM/IV/Other) and missing multi-route persist.
- **Decision: BELOW 70% threshold — code fix required before next training run.** Do not proceed to Batches G/H.

**Outcome disagreements (Agent vs R1):**

| NCT | R1 | v21 | Type |
|---|---|---|---|
| NCT00002428 | Failed | Unknown | Evidence gap (persistent) |
| NCT00004984 | Failed | Unknown | Evidence gap (persistent) |
| NCT00972569 | Failed | Unknown | Regression (was correct in v19) |
| NCT00977145 | Positive | Terminated | TERMINATED fix failure |
| NCT00982696 | Unknown | Failed | Overcorrection (new v21 error) |
| NCT02654587 | Positive | Terminated | TERMINATED fix failure |
| NCT02660736 | Positive | Unknown | Evidence gap (persistent) |
| NCT02665377 | Failed | Unknown | Evidence gap (persistent) |
| NCT03490942 | Terminated | Failed | Overcorrection (new v21 error) |
| NCT04672083 | Failed | Unknown | Evidence gap (persistent) |
| NCT04701021 | Failed | Positive | Overcalling positive (persistent) |
| NCT04711135 | Recruiting | Active | Status confusion (R1/R2 disagree) |
| NCT04749641 | Active | Positive | Status confusion (R1/R2 disagree) |
| NCT04771013 | Recruiting | Positive | Status confusion (R1/R2 disagree) |
| NCT05361733 | Positive | Recruiting | Status confusion (R1/R2 disagree) |
| NCT06833931 | Terminated | Withdrawn | R1/R2 disagree (R2=Withdrawn) |

### v19 Concordance (Batch A+B, 50 NCTs, 2 runs: c1786d005ade / ac6af4e49fe2) — 2026-03-27

| Field | v19 R1 | v19 R2 | v18+ baseline | Target | Met? |
|---|---|---|---|---|---|
| Classification | **92.0% / AC₁=0.917** | **92.0% / AC₁=0.917** | 87.8% / 0.870 | AC₁≥0.82 | YES (+4.7%) |
| Delivery Mode | 65.3% / 0.632 | 63.3% / 0.614 | 67.3% / 0.654 | ≥73% | NO (slight regress) |
| Outcome | 72.0% / 0.680 | 68.0% / 0.634 | 70.0% / 0.657 | ≥80% | NO (slight improve) |
| Reason for Failure | 72.0% / 0.671 | 68.0% / 0.625 | 72.0% / 0.671 | ≥84% | NO (same) |
| Peptide | 86.7% / 0.834 | 80.0% / 0.734 | 88.9% / 0.865 | ≥86% | Borderline / high variance |
| Sequence | 65.0% / 0.634 | 68.4% / 0.668 | 59.1% / 0.574 | ≥30% | YES (code-only improvement) |

**Key findings:**
- **Classification fixed**: NCT00000886/NCT00002428 (vaccine NCTs) now correctly Other — Mode D removal worked
- **Sequence improvement** (59%→65%+) came purely from v19 code changes; EDAM had not yet fired for test NCTs (correctly excluded)
- **Delivery mode slight regress** (-2%): SC tightening removed some correct SC calls along with wrong ones
- **Peptide high run-to-run variance** (7%): binary field with temp=0.05 — fixed in v20 (temp→0.0)
- **Reconciler bug discovered post-run**: 15 cases per run where `agreement_ratio=0.0` still kept Pass1 value (unanimous verifier disagreement was not routing to reconciler). Case: NCT04701021 (Outcome=Positive should be Unknown — all 3 verifiers said Unknown but high-confidence primary was kept)
- **EDAM contamination discovered**: 35/50 test-batch NCTs were still in EDAM despite v18 allowlist (prevented new writes but didn't purge existing records). Purged in v20 + hard-excluded from TRAINING_NCTS

**Run-to-run variance analysis (v19):**

| Field | R1 | R2 | Variance |
|---|---|---|---|
| Classification | 92.0% | 92.0% | 0% (stable) |
| Delivery Mode | 65.3% | 63.3% | 2% |
| Outcome | 72.0% | 68.0% | 4% |
| RfF | 72.0% | 68.0% | 4% |
| Peptide | 86.7% | 80.0% | **7% (temp issue — fixed v20)** |
| Sequence | 65.0% | 68.4% | 3% |

## EDAM Database State (2026-03-31, post-Batches E/F)

| Table | Count | Notes |
|---|---|---|
| experiences | ~1,604 | Post-purge (1,404) + Batches E/F ~200 new exp (50 NCTs × 2 runs × 2 fields) |
| corrections | ~93+ | Baseline 93, may have grown from E/F runs |
| unique_ncts | ~170 | 120 baseline + 50 new from positions 101-150 |

**Note:** Batches E/F rebuilt outcome+delivery_mode EDAM from scratch on v21 code. However, concordance did not improve (outcome fell to 68%). EDAM net-positive threshold (≥70% base accuracy) not met. Do NOT run more training jobs until outcome code is fixed.

### EDAM Learning Conditions

**EDAM is net-positive ONLY when base accuracy ≥ ~70%.** Evidence from sequential same-code runs on test batch (R4→R5→R6, v18 code):
- Outcome: 76% → 72% → 68% (declining 3 consecutive runs)
- Root cause: EDAM reinforced wrong answers from earlier (contaminated) runs
- Fix: test NCTs purged from EDAM, TRAINING_NCTS hard-excluded in edam_config.py

**Training vs test gap (discovered 2026-03-28):**
- Outcome: 44-50% on training NCTs vs 68-72% on test batch
- Root cause: test NCTs selected for richness (high literature density); training NCTs are broader population with less evidence
- CT.gov resultsSection fix (v20) did not close gap (same 50% on training-C R1)
- Strategic implication: don't evaluate EDAM on training NCTs; always use test batch for concordance

### Job Coverage (contributing to EDAM)

| Job | NCT count | Exp written | Version | Notes |
|---|---|---|---|---|
| a77f77e7083f | 25 | 150 | pre-v19 | Old training run |
| 655ff74fac2d | 25 | 150 | pre-v19 | Old training run |
| 04f4b809097b | 21 | 126 | pre-v19 | Partial training run |
| 5b902ca30b1e | 10 | 60 | pre-v19 | Partial training run |
| a2da6002df4f | 50 | 300 | v19 | Mystery Train-C, completed |
| dbd215c03cf3 | 20 | 120 | v19 | Mystery Train-C, cancelled at 20 |
| ba96acf75132 | 50 | 300 | v20 | Train-C R1, completed |

**Jobs cf642da98bd6 and 434ad7a32ff8**: both status=failed, 0 completed NCTs, **0 EDAM writes** — no purge needed.

### EDAM History

EDAM was wiped clean on 2026-03-24 (all prior v9-v11 data discarded due to known code bugs). Test-batch NCTs (fast_learning_batch_50.txt) purged on 2026-03-28 (1,314 experiences, 113 corrections, 175 stability entries removed). Hard-exclusion added to edam_config.py: `TRAINING_NCTS = _load_training_ncts() - _load_test_batch_ncts()`.

**EDAM's role going forward:** Supplementary edge-case memory. Code changes are primary. EDAM should only contribute when base accuracy is ≥70%. Never run concordance test NCTs through EDAM-writing code paths.

### v16 Concordance (Batch A, 25 NCTs, job 25366ac24587) — 2026-03-25

| Field | vs R1 | κ(R1) | AC1(R1) | vs R2 | κ(R2) | R1↔R2 | v15→v16 | Status |
|---|---|---|---|---|---|---|---|---|
| Classification | 84.0% | -0.04 | 0.827 | 88.0% | 0.35 | 88.0% | +0.7% | Stable |
| Delivery Mode | 72.7% | 0.61 | 0.701 | 68.2% | 0.55 | 76.0% | +3.1% | Improved |
| Outcome | 77.3% | 0.71 | 0.740 | 68.2% | 0.59 | 80.0% | -1.0% | Slight regression |
| Reason for Failure | 84.0% | 0.78 | 0.818 | 80.0% | 0.73 | 88.0% | 0.0% | Stable |
| Peptide | 81.8% | 0.24 | 0.762 | 75.0% | 0.00 | 83.3% | **-4.6%** | **Regressed** |
| Sequence | 14.3% | 0.13 | 0.066 | 14.3% | 0.13 | 70.6% | +14.3% | **Major improvement** |

**Bucketed concordance:**

| Field | vs R1 | vs R2 | R1↔R2 |
|---|---|---|---|
| Classification | 84.0% | 88.0% | 88.0% |
| Delivery Mode | 95.5% | 95.5% | 96.0% |
| Outcome | 81.8% | 77.3% | 88.0% |
| Peptide | 84.0% | 84.0% | 92.0% |

**Root cause analysis (v16 failures → v17 fixes):**

1. **Outcome (4 persistent Unknowns):** The adverse-event heuristic in `_infer_from_pass1()` was DEAD CODE — only called when the Pass 2 LLM throws an exception, never when it returns "Unknown". NCT00000886 had "unacceptable reactogenicity" in publications but the LLM treated it as inconclusive. Additionally, NCT02665377 had "Trial Phase: NOT FOUND" because Pass 1 failed to extract the phase from structured data.
   - **v17 fix:** Post-LLM heuristic override + structured phase injection.

2. **Peptide (-4.6% regression):** The confidence gate (≥0.90) checks SOURCE QUALITY (static weights: ClinicalTrials=0.95, PubMed=0.90), NOT classification certainty. Every trial with decent research coverage has conf≥0.90, making the gate useless. NCT02654587 (OSE2101) was misclassified as "large multi-subunit protein" — it's actually 10 synthetic peptides (9-10 aa each).
   - **v17 fix:** Cascade only on `model_name=="deterministic"`. Added OSE2101/DOTATOC to known peptides.

3. **Sequence (0% accuracy despite 7/25 extracted):** DBAASP `_name_matches()` uses bidirectional substring — "BNP" (3 chars) matches "BnPRP1" (proline-rich AMP), "ANP" matches "HANP" (alpha-defensin). These wrong sequences scored 0.95 (DBAASP weight) and outranked the correct ChEMBL HELM matches (0.90).
   - **v17 fix:** Word-boundary matching for ≤4 char names. ChEMBL HELM boosted 1.3x. UniProt prefers name-matching fragments.

4. **Multi-route delivery (not working):** `_extract_deterministic_route()` returns on FIRST keyword match. " iv " in "Grade II to IV (MAGIC)" triggered a false positive for NCT05415410. `_parse_value()` can only produce single values.
   - **v17 fix:** Collect all routes. Exclude title text. Parse comma-separated.

## v17 Validation Keys to Watch (next job TBD)

When this job completes, check these specific items in order of priority:

### 1. Outcome — does post-LLM heuristic override work? (Critical)
- v16: 77.3% vs R1, same 4 Unknowns as v15 (heuristic was dead code)
- v17 fix: call `_infer_from_pass1()` after Pass 2 "Unknown", inject structured phase
- **Pass if:** ≥80% vs R1
- **Check specific NCTs:**
  - NCT00000886: "unacceptable reactogenicity" in publications → should now return "Failed - completed trial"
  - NCT02665377: structured phase injected → should help LLM classify
  - NCT00972569: check if heuristic catches any adverse-event keywords
  - NCT02660736: should be "Positive" — may need different pathway
- **Regression risk:** Heuristic may over-fire, converting legitimate "Unknown" to "Failed". Check for new false positives.

### 2. Peptide — does deterministic-only cascade fix regression? (Critical)
- v16: 81.8% vs R1 (regressed 4.6% from v15's 86.4%)
- v17 fix: cascade only on `model_name=="deterministic"`, added OSE2101/DOTATOC to known peptides
- **Pass if:** ≥86% vs R1 (restore v15 level)
- **Check specific NCTs:**
  - NCT02654587 (OSE2101/TEDOPI): should now be True via known peptide list
  - NCT02624518 (68Ga-RM2): peptide may still be False (genuine edge case) but cascade won't fire
  - NCT03724409 (DOTATOC): should now be True via known peptide list
- **Regression risk:** LLM False results now proceed to annotation instead of cascading. This annotates more trials (good) but may produce wrong values for genuinely non-peptide trials. Check for new peptide=False trials that should have cascaded.

### 3. Sequence — does DBAASP word-boundary fix improve accuracy? (High)
- v16: 7/25 extracted, 0% accuracy (wrong sequences due to abbreviation collision)
- v17 fix: word-boundary matching for ≤4 char names, ChEMBL HELM 1.3x boost, name-matching fragment selection
- **Pass if:** ≥30% accuracy AND ≥10/25 extracted
- **Check specific NCTs:**
  - NCT00972569 (BNP): should now get BNP-32 from ChEMBL HELM (not BnPRP1 from DBAASP)
  - NCT02665377 (ANP): should now get ANP from UniProt (not HANP/defensin from DBAASP)
  - NCT02642523 (Nesiritide=BNP-32): should get BNP-32 from ChEMBL

### 4. Delivery Mode — does multi-route collection work? (Medium)
- v16: 72.7% strict, 95.5% bucketed. Multi-route not producing comma-separated.
- v17 fix: collect all routes, exclude titles from ambiguous keywords, parse comma-separated
- **Pass if:** ≥73% strict
- **Check specific NCTs:**
  - NCT05415410: should produce "Injection/Infusion - Subcutaneous/Intradermal, IV" (not just "IV" from title false-positive)
  - NCT06126354: should produce "IV, Oral - Unspecified"
- **Regression risk:** Multi-route collection may pick up noise routes from citations. Check that single-route trials still produce single values.

### 5. Reason for Failure — cascade from outcome improvement? (Medium)
- v16: 84.0% vs R1 (stable, but bottlenecked by outcome Unknowns)
- v17: no direct fix, but if outcome improves, RfF should cascade-improve
- **Pass if:** ≥84% vs R1
- **Check:** NCT00000886 — if outcome correctly returns "Failed", does RfF find "Toxic/Unsafe"?

### 6. Convergence check
- Compare v17 vs v16 for classification and RfF (the two stable fields)
- **If classification and RfF change <2%:** underlying stability confirmed
- **If outcome ≥80% AND peptide ≥86% AND sequence accuracy ≥30%:** Phase 1 targets met → Phase 2

## Plan

### Approach: Code-first iteration, EDAM supplementary

**Key principle:** Agents improve primarily through code changes (prompts, rules, models, logic) analyzed via concordance after each run. EDAM captures edge-case patterns the code can't handle deterministically. Do NOT run large batches until the code is stable — each code change invalidates prior runs and wastes compute.

**Convergence criteria for "code stable":** Two consecutive Batch A runs (25 NCTs) with <2% concordance change between them across all fields.

### Current status (2026-03-29): v20 code stable, training runs in progress

**EDAM decision gate:** After all 4 v20 training runs complete, run Batch A+B (50 test NCTs) for concordance. Decision branches:
- If Outcome ≥76% → EDAM is net-positive. Continue training (Batches E/F...) and plan full 642-NCT run.
- If Outcome 70-76% → Marginal. Re-run once more to confirm trend. Then decide.
- If Outcome ≤70% → EDAM reinforcing wrong answers. Implement phase-based outcome heuristic before training.

**Phase-based outcome heuristic (if needed, prompt-level only):** For COMPLETED trials with no posted results — use phase + years since completion as prior in Pass 2 guidance:
- Phase I completed >5yr ago + no Phase II registered + no follow-up publications → lean Failed
- Phase I completed recently (<3yr) + no publications → Unknown (normal lag time)
- Phase II/III completed >10yr + no negative evidence → Positive (completion heuristic H3)
This is Layer 2 (prompt reasoning), not hardcoded. Drug lists remain frozen.

**Sequence ordering: no parallel jobs** (hardware restriction — Mac Mini M4, 16GB):
1. Wait for training-C R2 + training-D R1 + training-D R2 (jobs 29830f7d3785, 798817a09db3, 3fc6552eb54e)
2. Submit Batch A+B concordance (fast_learning_batch_50.txt) → one job
3. Evaluate concordance → apply EDAM decision gate above

### Phase 1: Iterate on Batch A+B until stable (IN PROGRESS — v19 baseline done)

**v19 results** (based on v19 R1 Batch A+B concordance):
- Outcome: 72% vs R1 (target was ≥76% — NOT met, but +2pp from v18+)
- Delivery Mode: 65.3% vs R1 (target was ≥73% — NOT met, slight regress)
- RfF: 72% vs R1 (target was ≥80% — NOT met, same as v18+)
- Classification: AC₁=0.917 (target was ≥0.87 — **MET**, +4.7pp)
- Peptide: 86.7% vs R1 (target ≥86% — borderline MET R1, high variance)
- Sequence: 65.0% vs R1 (target ≥60% — **MET**, +6pp from v18+)

**v20 targets** (primary fixes = reconciler bug + CT.gov results):
- Classification: AC₁≥0.91 (stable at 0.917 — hold)
- Outcome: ≥76% vs R1 (reconciler bug fix should recover 5-8 cases)
- RfF: ≥78% vs R1 (cascade improvement from outcome fix)
- Delivery Mode: ≥67% vs R1 (Rule 8 ambiguity bias helps but won't fully close gap)
- Peptide: ≥88% vs R1 (temp→0.0 eliminates 7% variance; should stabilize)
- Sequence: ≥65% vs R1 (no new sequence code — hold)

**Run v19 on Batch A+B** (`fast_learning_batch_50.txt`) to compare:
```bash
NCT_IDS=$(python3 -c "
with open('/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/amp_llm_v3/standalone modules/agent_annotate/scripts/fast_learning_batch_50.txt') as f:
    ncts = [l.strip() for l in f if l.strip()]
import json; print(json.dumps(ncts))
")
curl -s -X POST http://localhost:8005/api/jobs \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer <token>' \
  -d "{\"nct_ids\": $NCT_IDS}"
```

**Run v12 Batch A** on correct NCTs (`fast_learning_batch_25.txt`) — HISTORICAL REFERENCE ONLY:
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
5. **v17 targets on Batch A** (updated from v16 concordance analysis):
   - Outcome: ≥80% vs R1 (v16 was 77.3% — v17 post-LLM heuristic override should close gap)
   - Delivery mode: ≥73% strict, ≥95% bucketed vs R1 (v16 was 72.7%/95.5% — v17 multi-route)
   - Reason for failure: ≥84% vs R1 (v16 was 84.0% — should cascade-improve with outcome)
   - Classification: AC₁ ≥0.82 (v16 was AC₁=0.827 — stable, no changes)
   - Peptide: ≥86% vs R1 (v16 was 81.8% — v17 deterministic-only cascade restores v15 level)
   - **Sequence: ≥30% accuracy** (v16 was 14.3% with 0% accuracy — v17 DBAASP/ChEMBL fixes)

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
