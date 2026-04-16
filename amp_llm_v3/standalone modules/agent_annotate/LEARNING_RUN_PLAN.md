# EDAM Learning Run Plan

**Last updated:** 2026-04-14

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
| **19** | **A (v18, new NCTs)** | **TBD** | **25** | **—** | **Next** | **v18** | **TBD** | **New 25 from training CSV. Known-sequences, RfF TERMINATED fix, outcome adverse-first, EDAM restricted.** |
| *20* | *A+B (50 NCTs)* | *TBD* | *50* | *—* | *Pending* | *v18+* | *—* | *Phase 2: expand to 50 after Batch A converges.* |
| *21* | *Full training (642)* | *TBD* | *642* | *—* | *Pending* | *v18+* | *—* | *Phase 3: full training set run.* |
| *22* | *Test set (remaining)* | *TBD* | *TBD* | *—* | *Phase 4* | *v18+* | *—* | *Held-out evaluation. EDAM frozen.* |
| 36 | Concordance v22 | 6657f8896238 | 50 | 50/50 | **Complete** | v22 (fc02b08) | — | 94.3% classification, 88.6% delivery, 80% outcome. Sequence 40%. |
| 37 | Batch G R1 | 55826cb5853a | 25 | 25/25 | **Complete** | v22 | — | 151-175. Classification 100%. Delivery 66.7%. Sequence 0%. |
| 38 | Batch G R2 | 799905fee5c4 | 25 | 25/25 | **Complete** | v22 | — | 151-175. Delivery 73.3%. Peptide 70.8%. Sequence 0%. |
| 39 | Batch H R1 | 6ae5c0fb0de1 | 25 | 25/25 | **Complete** | v22 | 14 timeouts | 176-200. Delivery 46.2%. Sequence 57.1% (4 exact). |
| 40 | Batch H R2 | 4953bff0b240 | 25 | 25/25 | **Complete** | v22 | 14 timeouts | 176-200. Delivery 46.2%. Outcome 69.2%. |
| 41 | Concordance v25 | bb302bc7b077 | 50 | 4/50 | **Cancelled** | v25 (904180a) | — | Cancelled to pick up quality checker fix. |
| 42 | Concordance v25 | b7c5c4fe7a17 | 50 | —/50 | **Running** | v25 (3595d06) | — | Resubmitted with quality checker N/A fix. Same 50 NCTs. | | — | Baseline: same 50 NCTs as v22 concordance. First run with simplified categories + all fixes. |
| 43 | v28 test | 27c0f2ef1732 | 10 | 10/10 | **Complete** | v28 (4e81071) | — | First v28 test. Peptide 100% (9/9). RfF 29% (negation bug). NCT00000435 crashed (dict .lower()). |
| 44 | v28+fix retest | 5d8ed86f257c | 10 | 10/10 | **Complete** | v28+fix (26b6c0d) | — | Crash fixed. RfF 57% (up from 29%). NCT00000435 peptide=False (name mismatch). |
| 45 | v28 concordance | 3e8c4848fe74 | 50 | 50/50 | **Complete** | v28+fix (26b6c0d) | — | **Peptide 90% (pre-verif) / 96% (verified)**. RfF 50% (pre-verif) / 82.6% (verified). Classification 84.8%. Delivery 93.5% (verified). Outcome 73.9%. |
| 46 | v29 validation | cee652e301c8 | 50 | 50/50 | **Complete** | v29 (f9ec75a) | — | Same 50 NCTs as v28. Verified: peptide 92%, RfF 80.9%, outcome 74.5%. 7 values changed vs v28 (LLM nondeterminism). |
| 47 | v29 generalization A | 11ca8845fe89 | 50 | 50/50 | **Complete** | v29 (f9ec75a) | — | Unseen batch A. Peptide 82% vs R1, classification 94.1%, RfF 100% vs R1. 100% verification consensus. |
| 48 | v29 generalization B | 4a7f6a167cb3 | 50 | 50/50 | **Complete** | v29 (f9ec75a) | — | Unseen batch B. Peptide 79.6% vs R1, 3 AMP classifications (all correct deterministic). NCT06675917 data loss (logger bug). 96% consensus (2 flagged). |
| 49 | v30 validation | 148bb10f1333 | 50 | 50/50 | **Complete** | v30 (92d18b7) | — | Same 50 NCTs. Peptide 96%, RfF 85.1% (best ever). Delivery 80.9% (corrected CSV). 0 warnings/timeouts. |
| 50 | v30 generalization C | 3ff867be90e1 | 50 | 50/50 | **Complete** | v30 (92d18b7) | — | Unseen batch C. Classification 90.3%, peptide 88%, RfF 91.7%. Delivery 85.7% (corrected CSV). |
| 51 | v30 generalization D | 790c4a15793b | 50 | 50/50 | **Complete** | v30 (92d18b7) | — | Unseen batch D. Classification 97.1%, peptide 84%, RfF 94.6%. Delivery 87.5% (corrected CSV). |
| 52 | v31 smoke A | 37547b9fc3c9 | 10 | 10/10 | **Complete** | v31 (4906908) | — | Verification fixes confirmed: insulin True, glucagon True. OpenAlex working (1-5 cites). SS/CrossRef 0 (title metadata missing). |
| 53 | v31 smoke B | 47a37e7d97fe | 10 | 10/10 | **Complete** | v31 (f9150a7) | — | Fresh NCTs. Peptide 90%, classification 90%, delivery 100% (on evaluated). CrossRef 3-4 cites/trial (title fix worked). SS 2-5 on 3/10. |
| 54 | v31 validation | 510e619f5f88 | 50 | 50/50 | **Complete** | v31 (f9150a7) | — | Peptide 96%, classification 84%, delivery 77.3% (regression from 93.5%), outcome 61.4%. 12 terminated→unknown errors, 7 AMP→Other definitional disagreements. |
| 55 | v32 validation A | 01b7a54efd1a | 50 | 50/50 | **Complete** | v32 (458edbf) | — | Peptide 96%, classification 81.8% (kappa=0), delivery 77.3%, outcome 61.4%, RfF 76.6%. Terminated/withdrawn 100% (v32 safety nets working). |
| 56 | v32 validation B | 9583e6660ebd | 50 | 50/50 | **Complete** | v32 (458edbf) | — | Peptide 86%, classification 90.3%, delivery 93.3%, outcome 67.7%, RfF 97.2%, sequence 23.1%. Different NCT set from 55. Combined 100-NCT: peptide 91%, outcome 64% (=human), RfF 85.5%. |
| 57 | v32 prior run | db7d3f85e6f8 | 50 | 50/50 | **Complete** | v32 (2fb4750) | — | Pre-outcome-fix v32. Peptide 98%, delivery 79.5%, outcome 59.1%. |
| 58 | v33 smoke | 543c5f11fafd | 10 | 10/10 | **Complete** | v33b (bf38085) | — | 87 min. Peptide 100%, delivery 100%, outcome 50% (5 still Unknown), RfF 80%. Outcome fixes had limited impact on old trials. |
| 59 | v33 validation (new 50) | ae42b7b27600 | 50 | 50/50 | **Complete** | v33b (bf38085) | — | 286 min. Peptide 92% (+8pp human), outcome 58.1% (+9.3pp human), RfF 84%. Classification 70.5%, delivery 66.7%, sequence 15.4% — cascade N/A dominant error. 0 warnings/timeouts. |
| 60 | v35 validation | TBD | 50 | —/50 | **Cancelled** | v35 | — | 9 code changes: peptide word-boundary, outcome keyword rescue, delivery multi-intervention, verifier tuning. |
| 61 | v35 smoke test | 16e46a1d1492 | 9 | 9/9 | **Complete** | v35 (c4a1175) | — | Status injection 7x, confidence floor 1x, pub-priority override 1x. No errors. |
| 62 | v36 validation | TBD | 50 | —/50 | **Cancelled** | v36 | — | 56 GT corrections + research-aware outcome rescue + delivery topical/nasal fixes. |
| 63 | v34 250-NCT baseline | 0af180b09402+bb545136cfa7 | 250 | 250/250 | **Complete** | v34 (1c17bfc) | — | Classification 91.5%, delivery 82.4%, outcome 59.7%, RfF 95.4%, peptide 82.8%, sequence 41.7%. |
| 64 | v34 630-NCT full run | 9fa9dfbd3013+4fddbd329286 | 630 | 630/630 | **Complete** | v34 (bb9a4d3) | — | Classification 91.2%, delivery 85.3%, outcome 65.2%, RfF 94.9%, peptide 82.2%, sequence 48.1%. |
| 65 | v37b 94-NCT validation | 89ae1f9f8c1f+3f971ba3bd97 | 94 | 94/94 | **Complete** | v37b (09e84e0) | — | Classification 92.3%, delivery 82.4%, outcome 59.4%, RfF 95.2%, peptide 86.2%, sequence 47.4%. 295s/trial avg. 0 warnings/timeouts. |
| **66** | **v38 94-NCT validation** | **b02042a06db6+87bc38d018b8** | **94** | **—/94** | **Running** | **v38 (31eee3a)** | — | **Dossier redesign, delivery Other fix, sequence expansion. Same 94 NCTs as v37b for direct comparison.** |

> **Note:** Jobs 36-40 are the last jobs run with old categories (v22 code). v24 is now merged to main (9db9e33) with simplified categories (binary AMP/Other, 4-category delivery mode). All future jobs use v24+ categories. Training CSV re-bucketed from Excel source on 2026-04-07 (v31) — delivery mode 145 injection annotations recovered from "other".

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
| v24 | TBD | Binary classification (AMP/Other), 4-category delivery mode, full peptide=False cascade, CSV data source, order-agnostic sequence agreement, agreement API rename |
| v25 | 904180a | Delivery dedup fix, DRVYIHP word-boundary matching, 15 known peptide drugs, 9 known sequences, outcome publication-priority override, frontend agreement rename |
| v26 | e04e458 | TERMINATED outcome override fix, RfF empty default fix |
| **v27b** | **pending** | **AA boundary 50→100 in all prompts. "Peptide / peptide hormone" molecular class. Peptide-conjugate INCLUDES. Insulin True worked example. Consistency cross-validation 2-50→2-100. CSV migration for concordance scripts. Batch files fixed (non-training NCTs replaced).** |
| **v27c** | **pending** | **self_audit AA range 2-50→2-100. memory_store learning patterns 2-50→2-100, multi-chain excludes peptide hormones. UniProt snippet fix: report mature chain lengths from CHAIN/PEPTIDE features (insulin 51 aa, not precursor 110 aa). Consensus threshold stays 1.0.** |
| **v27d** | **tested** | **Structured data injection: STRUCTURED FACTS block for verifier + primary. Test c5de1e0049b0: insulin verifiers 1+2 failed to follow response format (None), CV-MG01 verifiers 1+2 correctly said True citing structured facts but primary+reconciler still False. Partial success — format compliance and reconciler logic need work.** |
| **v27e** | **8456a66** | **Fix v27d regression: restore v26 system template, facts at END of evidence with format reminder, reconciler verifier-majority awareness. Test 05f80bba8946: BOTH FIXED — insulin True (primary override), CV-MG01 True (reconciler flipped using verifier majority). qwen2.5:7b still produces summaries, phi4-mini still times out on CV-MG01. Prod job c00a1eef (50 NCTs): peptide 80%, delivery 93.1%, outcome 75.9%.** |
| **v28** | **2679eaf** | **Pre-cascade _KNOWN_SEQUENCES check, phi4-mini→llama3.1:8b, verifier evidence 30→15, fallback parser, smart retry, parse-failed exclusion, broadened peptide definition, "empt" RfF truncation fix, COVID keywords. First test (job 27c0f2ef1732, 10 NCTs): peptide 100% (+20pp) but RfF regressed to 29% and NCT00000435 crashed.** |
| **v28+fix** | **f0a4dba** | **Fixed two bugs from v28 test: (1) _pass1_says_no_failure checked LLM's "Is This A Failure: No" before terminated/withdrawn override → moved status check to top. (2) Pre-cascade .lower() on EDAM-resolved dict interventions → handles both types. Deployed to prod+dev.** |
| **v29** | **dce4466d** | **Three fixes: (1) _infer_from_pass1 negation filter + section boundary regex [A-Z]→section headers. (2) _KNOWN_SEQUENCE_ALIASES + resolve_known_sequence() for pre-cascade. (3) NCBI retry 3→5 + literature_unavailable flag. 150-NCT test (3 jobs on prod f9ec75a): negation fix works (+16pp annotation-layer RfF) but verification already caught those → net pipeline flat. Generalization strong: classification 88.9%, RfF 97.1% vs R1.** |
| **v30** | **92d18b7** | **Five fixes from v29 test analysis: (1) whyStopped negation filter (failure_reason.py). (2) Post-verification sequence consistency Rule 3 (orchestrator.py). (3) Literature logger NameError fix (literature.py). (4) Cell therapy/dietary supplement peptide guidance in verifier+reconciler prompts. (5) DBAASP-only classification hits go through verification (skip_verification=False, confidence 0.80). Outcome conservatism explored and rejected. Results (150 NCTs): Peptide 96% restored, RfF 85.1% best ever, 4/6 fields at/above human ceiling.** |
| **v31** | **f9150a7** | **3 new literature APIs (OpenAlex 250M+ works, Semantic Scholar TLDRs, CrossRef non-PubMed). 15 agents total, 20+ databases. Identifier-based evidence dedup. Confidence-weighted majority vote. Low-confidence dissent gate. Evidence grade propagation (db_confirmed). Per-field verifier evidence budgets (peptide 25, outcome 20). Reconciler override (weighted vote > reconciler when primary conf > 0.85). Delivery mode: radiotracer detection, intervention desc oral/topical scan, removed injection default bias, tightened topical keywords. Training CSV re-bucketed from Excel (145 injection annotations recovered). Smoke: peptide 90-100%, delivery 80-100%, CrossRef producing 3-4 citations/trial.** |
| **v32** | **458edbf** | **Outcome fixes: (1) Section boundary regex — ported _SECTION_BOUNDARY from failure_reason.py, \n[A-Z] never matched on lowered text. (2) Terminated safety net — Unknown + TERMINATED + no results → force Terminated. (3) hasResults override — Unknown + COMPLETED + results posted → force Positive. Delivery: (4) Expanded oral keywords. (5) Injection priority guard 2-route only. Validation (50 NCTs): Peptide 96%, Classification 81.8%, Delivery 77.3%, Outcome 61.4%, RfF 76.6%.** |
| **v33b** | **062a7fd** | **9 fixes across 8 files. Critical: (1) consensus.py removed `"amp":"other"` alias blocking AMP since v24. (2) orchestrator.py delivery normalization to v24 values. Outcome: (3) structured status+hasResults injection from CT.gov metadata. (4) generic publication filter in _infer_from_pass1. (5) H3b backstop Phase II/III >10yr. (6) generic publication filter in _publication_priority_override. Delivery: (7) topical injection priority >= to > (strict). RfF: (8) expanded keywords. Peptide: (9) glucagon in _KNOWN_SEQUENCES. v32 100-NCT baseline: outcome 64% (=human), peptide 91% (+5pp human), delivery 83.8%, RfF 85.5%.** |
| v34 | fc6f41c/1c17bfc | Generic pub filter fix, 3 GT peptide corrections, cascade-aware concordance, NCT training CSV validation gate. |
| v35 | de5dd87/c4a1175 | Peptide word-boundary, outcome evidence rescue, delivery multi-intervention, verifier tuning, concordance CSV auto-reload. |
| v36 | c470c56 | Delivery topical/nasal, outcome research-aware keyword rescue. GT CSV corrections reverted (586361d). |
| v37 | 63daaea | Classification host-defense fallback, peptide non-peptide word-boundary, outcome stale-status. |
| v37b | 09e84e0 | Sequence concordance fix, outcome keyword expansion, classification post-LLM consistency check for AMP override. |
| **v38** | **31eee3a** | **Major outcome redesign: 3-tier structured evidence dossier replaces 9-layer cascade. ACTIVE_NOT_RECRUITING removed from deterministic. Publication-anchored skip_verification. Delivery: post-LLM not-specified override, radiotracer skip_verification=True, 71 EDAM corrections cleaned. Sequence: ~70 known drugs (was ~30), ~40 aliases, cross-validation, multi-chain UniProt.** |
| **v39** | **pending** | **CRITICAL BUG FIX: `.isdigit()` on `PMC:xxx`/`PMID:xxx` identifiers always returned False — publication-anchored skip_verification was completely non-functional since v38. Added `_has_publication_id()` helper. Added mixed-evidence guard (both pos+neg keywords → don't skip). Delivery: not-specified override now sets skip_verification=True. v38 94-NCT results: outcome 51.5% (29/43 Positive overridden by reconciler), delivery 76.5% (10 Other overridden). Expected v39: outcome ~75%, delivery ~88%.** |

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

> **Note:** All prior concordance numbers used old categories (3 classification, 18 delivery mode). v24 establishes a new baseline with simplified categories (binary AMP/Other, 4-category delivery mode).

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

### Phase 1: Iterate on Batch A until stable (NEXT — run v24 baseline)

**Run v24 Batch A** on correct NCTs (`fast_learning_batch_25.txt`) to establish new baseline with simplified categories:
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
