# EDAM Learning Run Plan

**Last updated:** 2026-04-28

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
| 66 | v38 94-NCT validation | b02042a06db6+87bc38d018b8 | 94 | 94/94 | **Complete** | v38 (31eee3a) | — | Classification 92.2%, delivery 76.5%, outcome 51.5%, RfF 92.1%, peptide 88.3%, sequence 58.3%. **REGRESSION**: skip_verification bug (see v39). |
| 67 | v39 94-NCT validation | 14c1d56cc92d+0e182f29b35e | 94 | 94/94 | **Complete** | v39 (ad99b9d) | — | Classification 89.7%, delivery 80.4%, outcome 52.6%, RfF 93.8%, peptide 88.3%, sequence 58.3%. **MISSED TARGETS**: skip_verification protected wrong Positive calls too. |
| 68 | v40 94-NCT validation | e4858a2904b3+f9689ebdb4ee | 94 | 94/94 | **Complete** | v40 (cd73e874) | — | Classification 91.4%, delivery 85.4%, outcome 60.5%, RfF 92.4%, peptide 88.3%, sequence 58.3%. qwen3:14b model swap. |
| **70** | **v41b 94-NCT validation** | **f6535916f390+99c9c0f0b3e5** | **94** | **—/94** | **Running** | **v41b (144bd8f2)** | — | **Fix overcorrection: pub classifier default + active guard. Target: outcome 78-86%.** |
| 69 | v41 94-NCT validation | 509eb8b4b732+74083c235d96 | 94 | 94/94 | **Complete** | v41 (7964c040) | — | Classification 91.4%, delivery 85.4%, outcome 55.3%, RfF 93.9%, peptide 90.4%, sequence 58.3%. **OVERCORRECTED**: 0 overcalls but 13 undercalls. Pub classifier default "general" too aggressive + Active guard <=180 too broad. |
| **71** | **v42 Phase 6 94-NCT cut-over test** | **85154945fadf** | **94** | **94/94** | **Complete** | **v42 (5f2d5d86)** | — | **First end-to-end prod run post-Phase-6. 8.45h / 324s/trial avg. 0 final warnings / 0 errors. Classification atomic (primary, Phase 6 cut-over): 93.3% vs R1 (56/60 scoreable); legacy shadow: 80%. **AMP recall: 86% (6/7)** vs Phase 5 shadow 75%. peptide=False cascade: 25/94 (27%). outcome_atomic: 40% scoreable (R8 fall-through floor 30% on 46 trials); legacy outcome: 50%. delivery_mode: 79% (6/11 disagreements are multi-intervention route-list issue, pre-existing). bioRxiv citations on only 3/94 trials — metadata-shape bug fixed post-run (see commit for bioRxiv fallback interventions parser). Phase 6 swap confirmed: 69 NCTs with classification=atomic value + classification_legacy shadow.** |
| **72** | **v42.6 100-NCT efficiency batch A** | **85910ab88f41** | **100** | **—/100** | **Running** | **v42.6 (275fb791)** | — | **First job with v42.6 efficiency pack fully on (skip_legacy_when_atomic + deterministic_peptide_pregate + skip_amp_research_for_non_peptides) and bioRxiv metadata fix. Fresh 100-NCT slice (NCT03315507–NCT03929029) from training CSV minus Job #71 and test_batch. Expected wall time ~3-4h (40-50% reduction vs Job #71's 324s/trial extrapolated to 100 trials).** |
| **73** | **v42.6 100-NCT efficiency batch B** | **bd559656f678** | **100** | **—/100** | **Queued** | **v42.6 (275fb791)** | — | **Sequential continuation, NCT03930927–NCT04917458. Queue position 1 behind job 72.** |
| **74** | **v42.6 100-NCT efficiency batch C** | **73a6485e63f0** | **100** | **0/100** | **Cancelled** | **v42.6 (275fb791)** | — | **Cancelled during v42.6.5 bugfix cycle — never started. Case-mismatch bug in Eff #2/#3 meant it would have contributed no efficiency data beyond #72.** |
| **73b** | **v42.6 100-NCT batch B (cancelled partial)** | **bd559656f678** | **100** | **35/100** | **Cancelled** | **v42.6 (275fb791)** | — | **Cancelled during v42.6.5 bugfix cycle. 35 NCTs annotated before cancel. Results preserved: peptide 89%, classification 88%, delivery 64%, outcome 54%. 16/35 bioRxiv citations (46%). BioRxiv citations in these 35 were NOT consumed by outcome_atomic due to v42.6.5 pub classifier bug (only 'literature' agent was merged; biorxiv ignored) — fixed in commit 6e932325.** |
| **75** | **v42.6.5 50-NCT validation** | **068f3e183135** | **50** | **15/50** | **Cancelled** | **v42.6.5 (6e932325)** | — | **Killed mid-run when autoupdater restarted the service (see v42.6.6 incident doc). 15 annotations preserved on disk: 10 AMPs (first segment) + 5 Others. Cross-branch gate deadlock after restart required cancel-and-resubmit. Telemetry confirmed working: amp_skip fired 4× before crash.** |
| **75b** | **v42.6.6 remaining 35-NCT continuation** | **0645863555d3** | **35** | **0/35** | **Cancelled** | **v42.6.6 (e034d674)** | — | **Cancelled immediately — wrong scope. 35-NCT split would mix 15 NCTs annotated under v42.6.5 (port bug) with 35 under v42.6.6 (fixed), giving an incoherent dataset. Resubmitted as Job #75c with all 50 NCTs under consistent v42.6.6 code.** |
| **75c** | **v42.6.6 50-NCT clean validation** | **25dd30f19e7d** | **50** | **50/50** | **Complete** | **v42.6.6 (e034d674)** | — | **2.5h / 178s/trial (45% faster than Job #71). But pregate REGRESSION: fired 20/50 with 50% FN rate — wrongly gated Thymalfasin/Albuvirtide/Apraglutide/Lutathera (all DRUG-typed peptides) as False. Classification collapsed 93%→59%, AMP recall 86%→0/7. DRUG type was unsafe to gate. Fixed in v42.6.8 with bidirectional INN-suffix pregate.** |
| **76** | **v42.6.8 50-NCT validation** | **23443979931d** | **50** | **50/50** | **Complete** | **v42.6.8 (472a58d9)** | — | **2.3h / 168s/trial (~6% faster than #75c). Pregate fired 43/50. Peptide accuracy 63.9%→77.8% (+14pt) vs #75c. Classification 92.5% (flat). AMP recall 0/11→1/11 — pregate FN regression mostly fixed but **classification chain still misses AMP** when peptide=True. Pregate spurious-match issues: "NS"/"Curodont" matched as known peptide sequences. ChEMBL=Small molecule still wrongly gates Liver-enriched antimicrobial peptide (NCT04897984) and Neoantigen Peptides (NCT04509167) as False.** |
| **77** | **v42.6.8 100-NCT generalization** | **440f19adef5e** | **100** | **100/100** | **Complete** | **v42.6.8 (472a58d9)** | — | **3.7h / 134s/trial (24% faster than #71's 178s). Pregate fired 90/100 (high — Other-heavy stratification). Peptide 62.0%, Classification 90.5%, Delivery 50.6%, Outcome 17%. AMP recall 60% (6/10), precision 75%. Same systemic issue as #76: peptide=True correctly gated for ~14 AMP candidates but classification returned "Other" for 8 of them — root cause is in classification chain, not pregate. failure_reason field 0/7 (completely empty — only fires on outcome="Failed", not "Terminated"/"N/A"). sequence field 0/27 (formatting drift between LLM output and GT).** |
| **78** | **v42.6.9 50-NCT recovery validation** | **c05f049fef32** | **50** | **50/50** | **FAILED gate** | **v42.6.9 (257810da)** | — | **4.2h / 305s/trial. Peptide 86.1% (close), classification 87.5% (close), **delivery 53.3% (-27)**, **outcome 7.1% (-53)**, **RfF 0% (-85)**, sequence 10.3%. Regression NOT fully config-gated. Root causes (per cascade/outcome diagnosis 2026-04-23): (a) peptide=False cascade unconditionally N/As every field; GT annotators give non-peptide trials specific delivery/outcome — cost ~27pp delivery + ~30pp outcome. (b) v41b removal of ANR Active guard too broad — past-completion ANR with no pubs defaults to Unknown. (c) classification legacy (87.5%) > atomic shadow (52.5%) on this set — Phase 5's 93% atomic claim not replicated. v42.6.10 fix pending.** |
| **79** | **v42.6.10 50-NCT fix validation** | **fce16457226f** | **50** | **50/50** | **Partial win** | **v42.6.10 (a6d45b9e)** | — | **5.5h / 394s/trial. Re-scored with production concordance_service normalization (my original raw-string analysis was wrong): peptide 86.1%, classification 97.5% (+0.3 vs #78 normalized), delivery 84.2% (above target, tiny dip from #78's 88.9% normalized), outcome 21.4% (-1 vs #78), RfF 0/0 (mostly GT-blank on this 50-NCT set). Cascade narrowing did help (unlocked N/A-blank predictions and confirmed classification=Other emission for non-peptide trials), but the original "27pp delivery regression" was a scoring-script bug, not an agent regression. OUTCOME is the one real remaining problem: v41-era `_dossier_publication_override` fires on loose efficacy keywords in review articles → 9 of 11 Positive over-calls. v42.6.11 fix pending.** |
| **80** | **v42.6.11 50-NCT outcome over-call fix** | **25cdead94bcc** | **50** | **50/50** | **Partial — missed gate** | **v42.6.11 (c5cdcc91)** | — | **7.2h / 519s/trial (slower than #79's 394s — longer prompt + more verification). Normalized: peptide 86.1%, classification 97.5%, delivery 87.2%, outcome 25.0%, RfF 0/0. Positive over-calls: 11 → 3 (fix landed). But prompt over-corrected: 11 of 13 GT="active" trials now flip to "Unknown" instead of "Active, not recruiting". Root cause: rule 1 "stale ANR → Unknown" clause, plus no safety net mapping LLM=Unknown + status=ANR back to canonical label. v42.6.12 fix pending.** |
| **81** | **v42.6.12+13 50-NCT status safety net + diagnostic fixes** | **c0f32e3ea9b8** | **50** | **50/50** | **Partial — diagnostic win, accuracy flat** | **v42.6.12+13 (3305eaa2)** | — | **6.2h / 443s/trial. Normalized: peptide 86.1%, classification 97.5%, delivery 73.3% (honest, down from #80's 87.2% because crashed-trial sentinels now count in denominator), outcome 25.0% (flat — safety net fired for 6 ANR trials but Positive over-calls rose 2→4 due to bare "approved" strong-efficacy match), RfF 0/0. Warnings 59→21 (50 atomic-fr-gated false positives silenced). 10 real CRASH warnings expose root cause of the delivery failures: `UnboundLocalError: not_specified_override` in delivery_mode.annotate() when Pass 2 returns "Other" directly. v42.6.14 fix pending.** |
| **82** | **v42.6.14 50-NCT (CANCELLED)** | **2d95bb200da9** | **50** | **0/50** | **Cancelled** | **v42.6.14 (36511366)** | — | **Cancelled mid-queue: validation scope mismatched the change scope. v42.6.14 was 2 narrow fixes already proven by unit tests; a full 50-NCT prod re-baseline (6h) is wasteful for that. Resubmitted as Job #82s targeted smoke (11 NCTs, ~1h).** |
| **82s** | **v42.6.14 11-NCT targeted smoke** | **6e835a3e41a1** | **11** | **11/11** | **PASS — all gates** | **v42.6.14 (36511366)** | — | **103 min / 564s/trial. Targeted exactly the trials where v42.6.14 changed behavior: 10 NCTs that crashed delivery_mode in #81 + NCT04527575 (the EpiVacCorona "approved" over-call). GATE 1 — 0 CRASH warnings. GATE 2 — NCT04527575 outcome=Unknown (was Positive). GATE 3 — 10/10 delivery_mode annotations now real qwen3:14b calls, all returned "Other" (no agent-crashed sentinels). Both fixes landed. Per-trial accuracy not measured (smoke scope) — next full re-baseline rolls in v42.6.14 alongside future fixes.** |
| **82b** | **v42.6.15 pub classifier 3-NCT smoke** | **1796b3a3b35f** | **3** | **3/3** | **PASS — all gates** | **v42.6.15 (f02d75da)** | — | **26 min. 3 NCTs that had review-article Positive over-calls in #81: NCT04449926 (BCG/dementia), NCT04461795 (CGRP monoclonal), NCT04527575 (peptide-vaccine). All 3 now outcome=Unknown; 0 CRASH warnings. NCT04527575 dossier shows 15 of 50 pubs tagged reviews/general (new 'and other', 'monoclonal antibodies', 'vaccines against', 'narrative review' patterns working).** |
| **83** | **47-NCT outcome-clean slice** | **51a6c2a308f8** | **47** | **47/47** | **PASS — true baseline established** | **v42.6.15 (f02d75da)** | — | **7.2h / 552s/trial / 2 warnings. Production-normalized: peptide 81.1% (different drug mix), classification 90.7%, delivery 91.7%, **outcome 61.7%** (vs 25.0% on old divergent slice — +36.7pp), sequence 75.0% (canonical-set compare). Outcome confusion: Terminated 12/12 (100%), Unknown 12/13 (92%), Positive 6/13 (46% — under-calls Unknown), Failed 2/9 (22% — scattered). Confirms the earlier 25% was ~75% measurement artifact (GT/registry divergence). Real agent ceiling is ~62%, close to v34 historical 65%. Remaining outcome gap is Positive under-call (v42.6.11 strong-efficacy too strict on legitimate positives) + Failed under-detection (whyStopped not flowing to outcome path).** |
| **84s** | **v42.6.16 6-NCT Positive recovery smoke** | **13e1c621d762** | **6** | **6/6** | **PASS — gate met** | **v42.6.16 (712fb3cc)** | — | **55 min / 549s/trial. Targeted exactly the 6 GT=positive trials that under-called Unknown in #83. Result: NCT03272269 Unknown → **Positive** (correct GT match) — the new "first-in-human, double-blind, randomized" Phase 1b report contained one of the new primary-anchored phrases. NCT06081322 flipped Unknown → Recruiting (LLM nondeterminism on UNKNOWN-status trial, not driven by strong-efficacy change). Other 4 stayed Unknown. 0 CRASH warnings, 0 over-calls. Implied outcome lift on full #83 slice: 61.7% → ~63.8%. Failed-trial whyStopped flow not implemented — Job #83's 9 failed trials had no whyStopped signal to wire (5 COMPLETED-no-whyStopped, 2 low-enrollment-already-handled, 2 GT/registry divergence).** |
| **85** | **v42.6.16 20-NCT RfF-rich slice** | **d1ab2634377e** | **20** | **20/20** | **PASS — first honest RfF measurement** | **v42.6.16 (712fb3cc)** | — | **2.9h / 515s/trial / 1 warning. **RfF overall: 8/20 = 40.0%** (using correct `reason_for_failure` field name — earlier `failure_reason` lookup gave false 0%). Per-category: Business 5/8 (62.5%), Recruitment 3/4 (75%), Toxic/Unsafe 0/1, Ineffective for purpose 0/6, Due to covid 0/1. Outcome on this slice: 7/7 = 100% on scoreable (3 terminated, 3 withdrawn, 1 unknown). **Root cause of Ineffective 0%: not an RfF bug.** All 6 trials have CT.gov status=COMPLETED + whyStopped='', so outcome calls Unknown/Positive (correctly per available evidence), and RfF gates to empty since outcome != Failed/Terminated. GT annotators used out-of-band judgment to call these Ineffective. Same Phase-1/Positive-overcall structural limit as #83. Field-name pitfall recorded in roadmap.** |
| **86s** | **v42.6.17+18 combined 3-NCT smoke** | **925f4dfc3b54** | **3** | **3/3** | **PARTIAL — 2/3 gates pass** | **v42.6.15 (stale memory)** | — | **22.8 min. NCT05269381 delivery=Injection/Infusion ✓ (was Other). NCT03196219 classification=AMP ✓ (was Other). NCT01689051 sequence=HSQG... glucagon ✗ (expected HAEG GLP-1). Discovery: smoke ran on stale in-memory code despite v42.6.17/18 being on disk, because the autoupdater correctly skips annotate restart while jobs are active (Job #85 was running through both merges). v42.6.18 part-2 commit identified a SECOND known-sequence loop in sequence.py:595 that bypassed resolve_known_sequence(). Same root bug, two call sites — only one fixed in original v42.6.18.** |
| **86c** | **v42.6.18 part 2 GLP-1 smoke** | **3d8862f2dcd6** | **1** | **1/1** | **PASS** | **v42.6.18 part 2 (542767b7)** | — | **11.5 min / 0 warnings. NCT01689051 sequence = HAEGTFTSDVSSYLEGQAAKEFIAWLVKGR (GLP-1, 30 aa, correct GT match). Reasoning: "[Known sequence] glucagon-like peptide 1 → HAEG... Matched intervention 'human glucagon-like peptide 1 (7-36)amide'." Both v42.6.18 call sites now use longest-first iteration. All 3 audit-uncovered Job #83 bugs (imaging detector, DBAASP evidence, GLP-1 sequence) validated.** |
| **87** | **v42.6.19 drug_cache 40-NCT validation** | **4f5243d0360e** | **40** | **40/40** | **STALE — code-on-disk vs in-memory** | **v42.6.19 (efa69660)** | — | **7.6h / 688s/trial / 0 warnings / 13 manual_review. Ran on stale memory image (autoupdater skipped restart while #85+#86c were processing); `drug_cache` key absent from saved diagnostics. Cache stats unmeasured. 13/40 manual_review high — outcome+RfF flagged on COMPLETED-with-no-whyStopped trials, exactly the bucket SEC EDGAR + FDA Drugs target. Will re-validate via Smoke #87s on fresh code.** |
| **87s** | **v42.7.0+v42.6.19 10-NCT integration smoke** | **2d4651f2965c** | **10** | **10/10** | **3/4 gates PASS** | **v42.7.0 (518ec6b1)** | — | **1.8h / 635s/trial / 0 warnings / 6 manual_review. Validated 17 research agents end-to-end. **GATE 1 PASS** SEC EDGAR fires 10/10, 1 citation: "IO Biotech 8-K (2022-03-31) references NCT03047928" — real sponsor disclosure on a real trial. **GATE 2 partial** FDA Drugs fires 10/10, 0 citations (all trials are early-stage/experimental drugs not FDA-approved; agent works but had nothing to find on this slice). **GATE 3 PASS** drug_cache stats present: size=157, hits=28, misses=157, hit_rate=15.1% (lower than expected because slice is drug-diverse; would be 50%+ on a single-drug slice). **GATE 4 PASS** 0 errors. Confirms the 17-agent pipeline runs cleanly. SEC EDGAR is operational; FDA Drugs is operational but mostly silent on the experimental-drug-heavy training set.** |
| **87t** | **v42.7.1 5-tier evidence_grade smoke** | **0bb2598b5cc6** | **5** | **5/5** | **PASS — gate met** | **v42.7.1 (835381f6)** | — | **54 min / 647s/trial / 0 warnings / 3 manual_review. **diagnostics.evidence_grades populated correctly.** Per-field distribution: peptide 4 db_confirmed + 1 deterministic; outcome 3 db_confirmed + 2 pub_trial_specific (zero bare-llm — every commit grounded); delivery_mode 5 deterministic; classification 2 deterministic + 2 llm + 1 pub_trial_specific; reason_for_failure 4 llm + 1 deterministic; sequence 5 deterministic. 0 inconclusive across 45 annotations (phase-1 inconclusive only fires on empty-value-no-reasoning; LLM always reasons). drug_cache hit_rate 7.3% on this 5-NCT slice (cache size 89, hits 7, misses 89). SEC EDGAR + FDA Drugs both fire on every trial; 0 citations because slice has no approved/disclosed drugs (same as #87s). Phase 1 scaffolding fully in place; phase 2 (commit_accuracy in scoring) starts now.** |
| **88** | **v42.7.3 47-NCT clean slice (pub-classifier expansion + per-field DB grading)** | **3d629acc8f65** | **47** | **47/47** | **PARTIAL — RfF win, outcome regression** | **v42.7.3 (5e548125)** | — | **Re-run of #83's 47-NCT slice with v42.7.2 pub-classifier expansion (5 agents instead of 1) and v42.7.3 per-field DB-keyword dispatch. Production-normalized: peptide 81.1%, classification 90.7%, delivery 91.7% (all flat vs #83), **outcome 28/47=59.6% (-2.1pp)**, **RfF 10/11=90.9% (+7.6pp vs #83's 83.3%)**. Total dossier publications jumped 281 → 809 (4.7x — pub-classifier expansion working). Outcome regression: 4 new under-calls vs 3 new recoveries — the broad keyword scan added preprint/aggregator noise on COMPLETED-no-results trials. Diagnosed: keyword scan must use only peer-reviewed sources (literature + openalex), not preprints/aggregators. Fixed in v42.7.4.** |
| **89** | **v42.7.4 47-NCT clean slice (source-weighted keyword scan)** | **85df1973e0bc** | **47** | **47/47** | **PASS — outcome recovered, RfF retained** | **v42.7.4 (0c0a7471)** | — | **Two-tier source weighting: publication-list-build branch (LLM-visible) keeps the broad 5-agent set; keyword-scan branch (deterministic outcome override) restricts to high-quality (literature + openalex). Production-normalized: peptide 30/37=81.1% (flat), classification 39/43=90.7% (flat), **delivery 34/36=94.4% (+2.8pp vs #83)**, **outcome 29/47=61.7% (recovered to baseline)**, **RfF 11/12=91.7% (+8.3pp vs #83)**. Total dossier publications 838 (kept 4.7x expansion). v42.7.4 thesis validated: peer-reviewed-only keyword scan recovers the noise-induced regression while LLM-visible context retains the RfF gain. v42.7 cycle now NET POSITIVE on the 47-NCT clean slice (outcome flat, delivery +2.8, RfF +8.3, all deltas vs Job #83 baseline; 116+ unit tests across 17 v42.6/v42.7 test files all passing).** |
| **90** | **v42.7.4 47-NCT stability run (LLM noise floor)** | **482100ef270a** | **47** | **47/47** | **Complete** | **v42.7.4 (0916e05f)** | — | **6h 37m. Same 47 NCTs as #89, same code commit. Production-normalized: peptide 81.1% / classification 90.7% / delivery 91.7% / **outcome 29/47=61.7% (identical to #89)** / RfF 10/16=62.5% / sequence 75%. Outcome had **4 per-trial flips out of 47 = ~8.5% noise floor** (net zero on raw count: 2 wins, 2 losses). Conclusion: anything under ~10pp on this slice is run-to-run jitter, not signal.** |
| **91** | **v42.7.6 prod 10-NCT smoke (post-merge gate)** | **5a3ff88bcbb2** | **10** | **10/10** | **PASS — gates met** | **v42.7.6 (f574536f)** | — | **1h 41m / 844s/trial / 0 errors / 0 warnings. Code-sync gate passed at submit (boot=disk=f574536f). Smoke surfaced empirical confirmation of the v42.7.0 silent regression: SEC EDGAR / FDA Drugs / NIH RePORTER returned **0 citations on all 10 trials** despite NCT00002228 (enfuvirtide DRUG) and NCT03272269 (peptide-immunotherapy BIOLOGICAL) being clear targets. The "No interventions to search" message in v42.7.0+ agents was caused by the orchestrator dropping intervention `type` field. Fix landed as v42.7.10. No outcome regression vs v42.6.15 baseline. Smoke validated v42.7.5 (code-sync diagnostic) + v42.7.6 (NIH RePORTER) prod plumbing.** |
| **94** | **v42.7.13 NCT01673217 hallucination fix spot-check** | **d444ec2a521a** | **1** | **1/1** | **PASS** | **v42.7.13 (0e137a1a)** | — | **41 min. NCT01673217 outcome=Unknown (matches GT, was Positive in Job #92/93). LLM reasoning explicitly quoted the new dossier line: "Registered Trial Publications: 0... the exception for Phase I trials requiring ≥1 registered trial-specific publication... is not satisfied. Therefore, the outcome remains 'Unknown'." v42.7.13 hallucination fix EMPIRICALLY CONFIRMED — the dossier zero-count line + Rule 7 restructuring successfully prevent the LLM from conflating heuristic [TRIAL-SPECIFIC] tag with sponsor registration.** |
| **97** | **v42.7.17 25-NCT held-out-C** | **c9da523f4913** | **25** | **25/25** | **PASS — over-correction recovered** | **v42.7.17 (fdd6859b)** | — | **5h 12m / 0 errors. **outcome 17/25 = 68.0% (+32pp vs Job #96's 36% on the same positive-heavy distribution; +8pp vs Job #92's 60%)**. peptide 24/24=100%, classification 25/25=100% (perfect again), delivery 17/20=85%, sequence 2/10=20% (small-N; mostly N/A predictions on peptide=True trials = sequence agent under-extraction, not regression). Research agents firing: NIH RePORTER 68%, FDA Drugs 28%, SEC EDGAR 44% — all healthy. v42.7.17 PASSES — alternative pub-title-pattern path correctly recovers the under-calls without recreating the over-call class. v42.7 cycle now design-complete on outcome. Held-out-C retired post-#97. Sequence under-extraction (8/10 N/A on peptide=True trials) targeted by v42.7.18 _KNOWN_SEQUENCES expansion (solnatide/io103/apraglutide).** |
| **98** | **v42.7.18 20-NCT held-out-D** | **29cd761c1bce** | **20** | **20/20** | **Complete** | **v42.7.18 (5875b4a8)** | — | **3h 16m / 0 errors / 1 quality warning. peptide 17/18 = 94.4% (+13pp vs Job #83), classification 19/19 = 100%, delivery_mode 14/18 = 77.8% (-14pp; 5 misses, no v42.7.19 spurious-oral pattern), outcome 7/20 = 35.0% (-27pp; 12/13 misses are positive→unknown — slice-specific positive-recall variance vs #97's 68% on similarly positive-heavy slice), sequence 2/11 = 18.2% (v42.7.18 dict didn't fire — 0 target NCTs in slice-D, as predicted). v42.7.18 NO REGRESSIONS. Cross-slice analysis confirmed positive→unknown is the dominant systemic miss class (12/22 in #83 baseline through 11/13 in #98 — not v42.7.x-specific). Investigation of misses (NCT01677676, NCT05137314, NCT05898763) revealed _classify_publication was over-tagging field-review pubs as [TRIAL-SPECIFIC], systematically confusing the LLM. Triggered v42.7.20 (classifier default flipped to general). Also surfaced NCT03481400 wrong-sequence (calcitonin instead of CGRP) → v42.7.22, and NCT01681290 + NCT04440956 sequence-N/A → v42.7.21. Held-out-D RETIRED post-#98.** |
| **99** | **v42.7.22 20-NCT held-out-E (combined v42.7.19/.20/.21/.22 stack)** | **87aece73b9ef** | **20** | **—/20** | **Running (submitted 2026-04-28)** | **v42.7.22 (096edcd3)** | — | **First validation of v42.7.20 (classifier tightening) + v42.7.21 (CBX129801/SARTATE sequences) + v42.7.22 (CGRP disambiguation). Held-out-E = seed 8484, residual pool excluding all prior held-out + tune-set NCTs. Code-sync gate PASSED at submit (boot=disk=096edcd3, active_jobs=0). Predictions: outcome should improve modestly via cleaner [TRIAL-SPECIFIC] dossier tags (LLM less confused); sequence may gain 1-2 hits if any held-out-E trials use CBX129801/SARTATE/CGRP-class drugs.** |
| **96** | **v42.7.16 25-NCT held-out-B baseline** | **b38959d9db37** | **25** | **25/25** | **REVEALED v42.7.13 over-correction** | **v42.7.16 (102fe921)** | — | **4h 48m / 0 errors. Outcome 9/25 = 36% — DRAMATIC drop from Job #92's 60%. peptide 95.2%, classification 100% (perfect). 12 GT=positive trials under-called Unknown — agent following v42.7.13's strict FALLBACK ("default to Unknown if Registered Trial Publications: 0") even when pub titles like "Randomized phase I/II clinical trial of [vaccine]" are clearly trial reports. v42.7.13 went too far. Triggered v42.7.17 fix that restructures Rule 7 condition (ii) to accept pub-title-pattern as alternative trial-specificity evidence (drug name + phase/first-in-human/trial descriptor in title; generic field reviews still excluded). Validates the user's a-priori prediction that a fresh slice would surface different failure patterns from the tune-set; held-out-B is now itself the tune-set for v42.7.17, future validation needs held-out-C.** |
| **95** | **v42.7.13 30-NCT held-out re-run** | **6810225e0993** | **30** | **30/30** | **WASH — design correct, accuracy at noise floor** | **v42.7.13 (0e137a1a)** | — | **4h 17m / 0 errors / 1 warning. Outcome 18/30 = 60.0% — IDENTICAL to Job #92's 60.0% but with DIFFERENT per-trial mistakes. The v42.7.12-13 fixes worked as designed: 4 of 4 targeted over-calls flipped Positive→Unknown (NCT01673217 / NCT03342001 / NCT03456687 / NCT03597893). But 4 new losses appeared: NCT03091673 + NCT06061315 (LLM noise on identical dossier — falls under the 8.5% noise floor measured Job #89↔#90), NCT03042793 (research variability — lit search returned different pubs between runs), NCT03784040 (intended v42.7.13 design — vaccine without registered PMIDs no longer auto-Positive; trade-off cost). Other fields: peptide 24/27=88.9% (+3.7pp vs #92's 85.2%), classification 27/27=100%, sequence 7/14=50%, delivery 25/28=89.3%, RfF 3/5=60%. **Empirical confirmation of held-out-A retirement decision** — the slice's noise floor exceeds the marginal effect of v42.7.12-13 prompt tightening, so re-runs can't distinguish design wins from per-trial jitter. Future cycle validation moves to held-out-B (25 NCTs, seed 5252).** |
| **93** | **v42.7.12 4-NCT over-call validation smoke** | **5bd9c3f28df6** | **4** | **4/4** | **PASS — 3/4 flipped (with one LLM hallucination)** | **v42.7.12 (88716f64)** | — | **51 min / 0 errors. **3 of 4 over-calls flipped Positive→Unknown** as designed: NCT03456687 (exenatide for Parkinson's), NCT03597893 (peptide trial), NCT03342001 (calcitonin Phase 4). NCT01673217 STAYED Positive — LLM hallucinated "PMC:12563070 is CT.gov-registered" though the trial has 0 registered PMIDs. Root cause: dossier formatter only printed the "Registered Trial Publications" line when count > 0; LLM never saw an explicit "0" and conflated heuristic [TRIAL-SPECIFIC] with sponsor-registered. Fixed in v42.7.13: always print the line (with strong fallback wording when 0) + Rule 7 restructured to numbered conditions with explicit heuristic-vs-registered distinction. Surprise: NCT03342001 — which I called the "candidate GT-error" case — DID flip, suggesting the trial really was inconclusive. Notable validation: my a-priori prediction was 3/4 wrong on the specific NCT (predicted NCT01673217 to flip, NCT03342001 to stay; reality was opposite).** |
| **92** | **v42.7.11 30-NCT held-out outcome validation** | **f12c09b79b76** | **30** | **30/30** | **MIXED — plumbing wins, accuracy flat** | **v42.7.11 (401806ab)** | — | **4h 37m. First independent measurement of v42.7.7-11 stack on unseen trials. **Per-field**: peptide 23/27=85.2%, **classification 27/27=100%**, delivery 25/28=89.3%, **outcome 18/30=60.0%** (vs Job #83's 61.7% — within noise floor), RfF 3/5=60% (small sample), **sequence 7/14=50.0%** (vs Job #83's 35.3% with v42.7.16 set-containment scoring — +14.7pp; the earlier "+26.5pp" was an analysis-tool artefact, see commit 2aad90b4). **v42.7.10 fix empirically validated**: NIH RePORTER 20/30 (66.7%), FDA Drugs 12/30 (40%) with 12 FDA-approved hits, SEC EDGAR 15/30 (50%) — vs Job #89's 0/0/4.3%. **Vaccine override fired 3/30**. Outcome flat is explained by 4 over-calls (Positive when GT=Unknown) that canceled the v42.7.7+8 gains: NCT01673217 (decitabine immunotherapy, vaccine override fired), NCT03342001 (calcitonin, FDA-approved for osteoporosis but trial tested thyroid), NCT03456687 (exenatide for Parkinson's, approved for diabetes), NCT03597893 (peptide trial). All four are "drug FDA-approved for indication X, trial tests indication Y" — the override doesn't disambiguate indications. Next cycle (v42.7.12+) needs to tighten the override with indication-matching, OR require strong-efficacy keywords in addition to FDA-approval flag.** |

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
| **v39** | **ad99b9d** | **CRITICAL BUG FIX: `.isdigit()` on `PMC:xxx`/`PMID:xxx` identifiers always returned False — publication-anchored skip_verification was completely non-functional since v38. Added `_has_publication_id()` helper. Added mixed-evidence guard (both pos+neg keywords → don't skip). Delivery: not-specified override now sets skip_verification=True. v39 94-NCT results: outcome 52.6% (+1.1pp, MISSED 75% target), delivery 80.4% (+3.9pp, MISSED 88% target). skip_verification backfired — protected 10 wrong Positive calls from reconciler.** |
| **v40** | **a2a34de** | **Model swap qwen2.5:14b → qwen3:14b. Added `"think": False` to ollama_client payload (disables 270+ token thinking overhead, 27s→0.4s per call). 14 files updated. think=false safely ignored by non-qwen3 models. Qwen3 produces better-quality answers (correct "Failed - completed trial" vs qwen2.5 truncated "Failed").** |
| **v41** | **7964c040** | **Fix outcome Positive overcalling (3 fixes). Fix 2: Active guard. Fix 3: Publication quality classification. Fix 1: Prompt rewrite + keyword split. Eliminated ALL overcalls (0 false pos) but OVERCORRECTED — pub classifier default "general" too aggressive (20/20 pubs tagged general), Active guard <=180 too broad. Outcome 55.3% (worse than v40 60.5%).** |
| **v41b** | **144bd8f2** | **Fix v41 overcorrection: (a) `_classify_publication()` default "general" → "trial_specific" (only explicit review signals tag as general). (b) Remove Active guard days_since<=180 block (only future completion forces Active). All other v41 changes preserved.** |
| **v42.7.0** | **2cd0378a** | **Two new free research agents: SEC EDGAR (10-K/10-Q/8-K filings via efts.sec.gov full-text search; required UA "Amphoraxe Annotation Pipeline amphoraxe@amphoraxe.ca") + FDA Drugs (openFDA Drugs@FDA via api.fda.gov/drug/drugsfda.json with literal-space Lucene queries). 17 research agents total. Both fire on every trial; 0 citations on early-stage slices, real disclosures (e.g. IO Biotech 8-K) on approved-drug slices.** |
| **v42.7.1** | **f1c57e08** | **Calibrated-decline phase 1: 5-tier `evidence_grade` taxonomy (db_confirmed > deterministic > pub_trial_specific > llm > inconclusive) plus per-job `diagnostics.evidence_grades` aggregate. INCONCLUSIVE is a final state for downstream filtering — no human-review loop (per user direction).** |
| **v42.7.2** | **ed380774** | **Calibrated-decline phase 2: `scripts/commit_accuracy_report.py` joins job JSON + GT and stratifies coverage × commit_accuracy by evidence_grade. Pub-classifier branch expansion: deterministic outcome override now consumes citations from all 5 publication agents (literature, openalex, semantic_scholar, crossref, biorxiv) instead of literature only. 4.7x dossier expansion observed in Job #88.** |
| **v42.7.3** | **5e548125** | **Per-field `_DB_KEYWORDS_BY_FIELD` dispatch in evidence-grading. Fixes commit-accuracy report inversion where ChEMBL/UniProt hits triggered db_confirmed for AMP classification (db_confirmed registered 71% accuracy vs llm at 100%; UniProt only confirms peptide-ness, not AMP-ness). After fix: classification db_confirmed = {dramp, dbaasp, apd}; outcome db_confirmed = {fda_drugs, sec_edgar}; peptide/sequence db_confirmed = {uniprot, dramp, dbaasp, apd, chembl, rcsb, ebi_proteins, pdbe}.** |
| **v42.7.4** | **0c0a7471** | **Two-tier publication source weighting. `_PUB_AGENTS` (broad — all 5 sources) feeds the LLM-visible publication list; `_PUB_AGENTS_HIGH_QUALITY` (literature + openalex only, peer-reviewed) feeds the deterministic keyword-scan override. Recovered Job #88's -2.1pp outcome regression to #83 baseline (61.7%) while retaining +8.3pp RfF gain. v42.7 cycle net positive on the 47-NCT clean slice (Job #89).** |
| **v42.7.5** | **b4daf954** | **Code-sync diagnostic for the memory-vs-disk autoupdater pitfall. Captures BOOT_COMMIT_SHORT/_FULL once at module load in `app/services/version_service.py`; new `/api/diagnostics/code_sync` endpoint reports boot vs disk; `scripts/check_code_sync.sh` smoke harness exits 1 on drift. VersionInfo gains `boot_commit_short/full` + `code_in_sync`. NOT YET MERGED TO MAIN (dev only).** |
| **v42.7.6** | **a609d683** | **NIH RePORTER as 19th research agent (`agents/research/nih_reporter_client.py`). Federal-grants context for the dossier, orthogonal to SEC EDGAR (sponsor) and FDA Drugs (regulator). Discovery: api.reporter.nih.gov's documented `clinical_trial_ids` criterion silently no-ops — only `advanced_text_search` actually filters. Searches by drug intervention name, caps at 3 interventions/trial. Live test 5/5 (liraglutide → 325 projects, 3 citations). Merged to main as f574536f.** |
| **v42.7.22** | **59c0be20** | **CGRP / calcitonin disambiguation. NCT03481400 (CGRP migraine trial) emitted the WRONG sequence (32aa calcitonin instead of 37aa alpha-CGRP) because the intervention name "Calcitonin Gene-Related Peptide" matched the shorter "calcitonin" key in `_KNOWN_SEQUENCES`. Same v42.6.18 root cause (longest-first iteration is in place; longer key was missing). Added `"calcitonin gene-related peptide"` and `"cgrp"` aliases mapping to alpha-CGRP `ACDTATCVTHRLAGLLSRSGGVVKNNFVPTNVGSKAF`. 5 unit tests + trip-wire.** |
| **v42.7.21** | **59c0be20** | **`_KNOWN_SEQUENCES` expansion from Job #98 held-out-D misses. CBX129801 = Long-Acting C-Peptide (Cebix Inc.), the canonical 31-aa proinsulin C-peptide → `EAEDLQVGQVELGGGPGAGSLQPLALEGSLQ` (NCT01681290 Type 1 Diabetes neuropathy trial). SARTATE = (Sar)0,Tyr3-octreotate, the canonical TATE octapeptide with D-Phe1, D-Trp4 → `fCYwKTCT` (lowercase preserves D-isomer info; NCT04440956 64Cu-SARTATE PET imaging). Includes "long-acting c-peptide" + "octreotate" aliases. 7 unit tests + trip-wire. Other Job #98 N/A trials (FP-01.1, GT-001, PLG0206, EPO alpha) deferred pending more sequence verification.** |
| **v42.7.20** | **cb984ba7** | **`_classify_publication` default flipped from `trial_specific` to `general`. Cross-job analysis of Jobs #95/#96/#97/#98 showed `positive → unknown` is the dominant outcome miss class; spot inspection (NCT01677676 / NCT05137314 / NCT05898763) showed 7-9 pubs per trial defaulting to [TRIAL-SPECIFIC] under v41b's rule, leading the LLM to systematically discount them. v42.7.20 requires an EXPLICIT trial signal (NCT match, "phase X", "randomized", "first-in-human", "clinical trial", "primary endpoint", etc. — see _TRIAL_SIGNALS) for trial_specific tagging. Otherwise default to `general`. _TRIAL_SIGNALS extended: combined phase markers ("phase 1/2", "phase 2/3"), "phase 1b"/"phase 2a", "clinical trial"/"clinical study". 6 unit tests + trip-wire. Will validate on held-out-E (Job #99).** |
| **v42.7.19** | **2d3c0b28** | **`delivery_mode` ambiguous-keyword relevance gate. Job #92/#95/#96/#97 surfaced 6 distinct NCTs (NCT01673217, NCT01704781, NCT03018665, NCT05096481, NCT05965908, NCT05995704) where ambiguous keywords (tablet/capsule from `_AMBIGUOUS_KEYWORDS`) matched on FDA Drugs / OpenAlex / placebo-comparator citations that didn't describe the experimental arm — typically FDA-approved oral formulations of similarly-named drugs (INQOVI for decitabine IV, TEMOZOLOMIDE on a peptide vaccine trial, Metformin on a biologic trial), or OpenAlex publications about tangentially-related topics. Adds a `citation_mentions_experimental` flag and skips ambiguous-keyword matches when the citation snippet doesn't mention any experimental intervention name. Non-ambiguous keywords (subcutaneous, intravenous, intradermal, etc.) remain unaffected — those are specific enough that any citation mention is signal. The OpenFDA citation path (lines 343-356) and OpenFDA raw_data path (357-377) already had this gate; v42.7.19 extends it to the broader protocol-keyword scan (lines 386-403). 5 unit tests + trip-wire. Will validate on next held-out cycle (Job #99 or later, slice E).** |
| **v42.7.18** | **9d5ec33d** | **`_KNOWN_SEQUENCES` expansion to fill Job #97 held-out-C peptide=True / sequence=N/A misses. 5 entries added in `agents/annotation/sequence.py`: `solnatide` → `CGQRETPEGAEAKPWYC` (17-aa cyclic AP301, NCT03567577); `ap301` and `tip peptide` aliases mapping to the same sequence; `io103` alias for the existing `pd-l1 peptide` entry → `FMTYWHLLNAFTVTVPKDL` (19-aa); `apraglutide` → `HGDGSFSDELSTILDLLAARDFINWLIQTKITD` (33-aa GLP-2 analog backbone, NCT04964986). Sequences-only — `_KNOWN_PEPTIDE_DRUGS` deliberately untouched per `feedback_frozen_drug_lists.md`. 5 unit tests + trip-wire. Will validate via held-out-D (Job #98).** |
| **v42.7.17** | **fdd6859b** | **Soften Rule 7 over-correction. v42.7.13's strict FALLBACK ("default to Unknown if Registered Trial Publications: 0") was too literal — Job #96 held-out-B revealed 12 GT=positive trials systematically under-called when pubs like "Randomized phase I/II clinical trial of [vaccine]" were clearly trial reports but lacked CT.gov registration. Restructured Rule 7 condition (ii) to accept EQUIVALENT alternative: ≥1 pub whose TITLE contains drug name + phase/first-in-human/clinical-trial descriptor. Generic field reviews excluded. Structural override (`_dossier_publication_override`) still gated on registered_trial_pubs_count >= 1 as a deterministic safety net. 23 test files, 167 tests pass. Will validate via future held-out-C run.** |
| **v42.7.16** | **b044769c** | **Sequence canonicalizer strips terminal -OH / -NH2 / -NH₂ chemistry suffixes BEFORE general hyphen removal. Job #92 NCT03522792 was a false sequence miss because GT "(glp)lyenkprrpyil-oh" canonicalized "OH" as the AA pair Ornithine-Histidine (the agent's "(Glp)LYENKPRRPYIL" stayed at "LYENKPRRPYIL"). Scoring-side fix at `app/services/concordance_service.py:_canonicalise_single_sequence` — agent output unchanged. 7/7 tests + trip-wire.** |
| **v42.7.15** | **095812aa** | **Tighten _NEGATIVE_KW: remove bare "failed" (over-fires on "treatment-failed patients" cohort descriptions) and bare "negative" (over-fires on "negative control" / "negative regulator" mechanistic terms). Add outcome-specific replacements: "primary endpoint not met", "primary endpoint was not met", "primary outcome not met", "trial failed". Qualified phrases retained ("failed to meet", "failed primary", etc.). 7/7 tests + trip-wire.** |
| **v42.7.14** | **3728acfe** | **Gate the "trial-specific + neg + no efficacy → Failed" path on registry status. Job #92 NCT03018665 (status=UNKNOWN, GLP-1 Phase 4) got mis-called Failed because the path fired regardless of status — UNKNOWN means the registry itself doesn't know, so deferring to LLM is correct. Now requires status in (COMPLETED, TERMINATED, WITHDRAWN). 5/5 tests + trip-wire.** |
| **v42.7.13** | **0df738dd** | **LLM hallucination fix (Job #93's NCT01673217). Dossier formatter now always prints the "Registered Trial Publications: N" line (explicit "0" when none). DOSSIER_PROMPT Rule 7 EXCEPTION restructured to 4 numbered conditions with explicit "[TRIAL-SPECIFIC] is HEURISTIC ≠ registered" distinction and "default to Unknown" fallback. Job #93 LLM had hallucinated "PMC:12563070 is CT.gov-registered" because the line was missing for count=0 trials. EMPIRICALLY VALIDATED in Job #94 (NCT01673217 spot-check flipped to Unknown matching GT).** |
| **v42.7.12** | **3f18b321** | **Fix Job #92's over-call class. Two robust gates: (a) FDA Drugs client now fetches `drug/label.json` indications_and_usage and surfaces "{drug} approved for: ..." in the dossier; DOSSIER_PROMPT Rule 3.c rewritten to require trial-condition vs FDA-indication overlap (LLM applies the check, not brittle string matching). FDA-approved structural override now requires _has_strong_efficacy keywords too (multiplier, not sole trigger). (b) Outcome dossier captures CT.gov-registered PMIDs from protocolSection.referencesModule — proven trial-specific signal that can't be faked by the heuristic [TRIAL-SPECIFIC] classifier. Vaccine override (v42.7.7) now also requires ≥1 registered PMID. Validated against Job #92's 4 over-calls: blocks 3/4 (NCT01673217 / NCT03456687 / NCT03597893 all have 0 registered refs); preserves both good cases (NCT03199872 has 1, NCT03272269 has 5). 13 unit tests + trip-wire. Full sweep: 20 test files, 148 tests, all pass. NOT YET MERGED TO MAIN (dev only).** |
| **v42.7.11** | **60c9ff72** | **Surface intervention names ("Trial Drugs: X, Y, Z") in the LLM-visible outcome dossier so the model can correlate the trial's intervention with publication titles when titles use chemical names instead of brand names (e.g. T-20 ↔ Enfuvirtide / Fuzeon). Backed by the same intervention_names list v42.7.7 builds for the vaccine detector. Capped at 5 names. NOT YET MERGED TO MAIN (dev only).** |
| **v42.7.10** | **7ff3e10d** | **CRITICAL silent bug fix: orchestrator dropped intervention `type` field when building research-agent metadata. Since v42.7.0 (2026-04-25) all 3 new research agents (SEC EDGAR / FDA Drugs / NIH RePORTER) had been firing with empty intervention lists — they searched only by NCT ID (and only SEC EDGAR's NCT search was wired). Jobs #88/89/90/87s/87t all ran with v42.7.0+ agents silently no-op-ing on drug-name search. Discovered while validating v42.7.7+8+9 on dev smoke `e46797571504`: NCT00002228 (Enfuvirtide DRUG) and NCT03199872 (RV001V BIOLOGICAL) both reported "No interventions to search". Fix: 2-line change at orchestrator.py:1183 to include `type` in the dict. 3 unit tests + trip-wire. NOT YET MERGED TO MAIN (dev only).** |
| **v42.7.9** | **7733dcf9** | **Extend FDA Drugs Lucene query to also match `products.brand_name` and `products.active_ingredients.name`. v42.7.0 restricted to `openfda.*` fields, but pre-2010 approvals (e.g. NDA021481 Fuzeon/enfuvirtide, 2003) have empty `openfda` blocks while populating `products[]`. Recovers Job #83's NCT00002228 under-call. Live test 5/5. NOT YET MERGED TO MAIN (dev only).** |
| **v42.7.8** | **3e912f3c** | **Wire FDA Drugs + SEC EDGAR raw_data into the outcome dossier. v42.7.0 added the agents but the outcome dossier never consumed `fda_drugs_<x>_approved` (the structured FDA-approval flag is the strongest Positive signal — regulator already approved the drug). New `fda_approved_drugs` + `sec_edgar_disclosed` dossier fields, FDA-approved Positive override (gated on no-negatives + not-already-set), LLM-visible "FDA Approved" + "SEC EDGAR" lines. 8 unit tests + trip-wire. NOT YET MERGED TO MAIN (dev only).** |
| **v42.7.7** | **35b88e19** | **Phase 1 outcome reasoning push: vaccine-immunogenicity Positive override. Job #83 confusion matrix showed 7/13 GT-positive trials under-called to Unknown — 5+ are vaccine/immunotherapy trials whose pubs report immunogenicity (induces immune response, antibody titers, T-cell response, seroconversion) but don't say "primary endpoint met" verbatim. For Phase I vaccine trials, immunogenicity IS the primary endpoint by design. New `is_vaccine_trial` dossier flag + `_IMMUNOGENICITY_KW` keyword set + override branch in `_dossier_publication_override` (gated tightly on is_vaccine_trial to prevent v41-era over-calls) + DOSSIER_PROMPT Rule 7 vaccine exception. 10 unit tests + trip-wire. NOT YET MERGED TO MAIN (dev only).** |

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

<!-- v42.6.17/18 redeploy trigger 2026-04-25 — autoupdater skipped restart while Job #85 was running; in-memory code was stale (v42.6.15-era). Force pull+restart by touching this file. No semantic change. -->

<!-- v42.7.2 redeploy trigger 2026-04-26 — autoupdater skipped restart between v42.7.1 and v42.7.2 merges; running service had stale memory. v72_smoke (9515627521d9) showed identical pub_count to v71 baseline. Force restart. -->
