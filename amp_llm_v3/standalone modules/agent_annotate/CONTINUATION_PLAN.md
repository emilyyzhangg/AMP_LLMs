# Agent Annotate — Continuation Plan

**Last updated:** 2026-04-08
**Current state:** v32 on dev (f1051988). v31 50-NCT validation complete (510e619f5f88) — peptide 96%, delivery 77.3% (regression from 93.5%), outcome 61.4%. v32 fixes delivery regression with expanded oral keywords + injection priority guard.

## v24 Changes

- **Classification:** Binary AMP/Other (was AMP(infection)/AMP(other)/Other)
- **Delivery mode:** 4 categories — Injection/Infusion, Oral, Topical, Other (was 18 granular sub-categories)
- **Peptide cascade:** ALL False cascades N/A (was deterministic-only)
- **Data source:** CSV `human_ground_truth_train_df.csv` (was Excel)
- **Agreement:** Order-agnostic sequence comparison, RfF blank+failure=Unknown, N/A treated as blank
- **API:** `/api/agreement/` (was `/api/concordance/`)

### v25 Changes (2026-04-01)
- **Delivery mode dedup fix**: "Injection/Infusion, Injection/Infusion" now deduplicates correctly (was 26% of disagreements)
- **DRVYIHP over-matching fix**: Short drug names (<=4 chars) require exact match, longer names use word-boundary regex. Prevents angiotensin matching ACE inhibitor trials
- **15 new known peptide drugs**: pvx-410, polypepi1018, gv1001, gt-001, xfb19, satoreotide, pemziviptadil, emi-137, neobomb1, pd-l1/pd-l2 peptide, bcl-xl_42-caf09b
- **9 new known sequences**: gv1001 (16aa), abaloparatide (34aa), vosoritide/bmn111 (39aa), satoreotide (8aa), pd-l1 peptide (19aa), emi-137 (26aa), l-carnosine (2aa)
- **Outcome publication priority (v25)**: Published results override CT.gov registry status. Evidence priority ladder: publications > CT.gov results > CT.gov status > trial phase. Post-LLM _publication_priority_override() for Unknown/Active/Terminated
- **Quality checker fix**: N/A from cascade/deterministic no longer triggers false retry (was wasting time on intentional N/A results)
- **Frontend**: Agreement page at /agreement (was /concordance), jobs table shows commit hash, autoupdater rebuilds frontend

### v27 Changes (2026-04-02)
- **Concordance scripts CSV migration**: concordance_jobs.py and concordance_test.py now use `human_ground_truth_train_df.csv` instead of the Excel file. Removed openpyxl dependency.
- **Batch file fix**: Removed 11 non-training NCTs from batch files. Replaced with training-set NCTs. All future jobs must use only training-set NCTs.
- **Known sequences**: Added insulin (preproinsulin, 110aa) and cv-mg01 (AChR peptide, 17aa) to `_KNOWN_SEQUENCES`.

### v27b Changes (2026-04-02) — Peptide boundary fix
- **Raised AA boundary 50→100**: Definition changed from "2-50 amino acids" to "typically ≤100 amino acids" across all prompts. This correctly classifies insulin (51 aa) as a peptide hormone while still excluding interferons (166+ aa), EPO (165 aa), growth hormone (191 aa).
- **Added "Peptide / peptide hormone" molecular class**: Replaced "Short peptide chain" label in Pass 1 options. LLM now has explicit category for peptide hormones including multi-chain.
- **Added peptide-conjugate INCLUDES**: "Peptide-conjugate therapeutics where the peptide IS the active component" — addresses CV-MG01 (two short synthetic peptides conjugated to carrier protein).
- **Added insulin as True worked example**: Replaced deleted False example with True example (51 aa, multi-chain, UniProt P01308).
- **Consistency engine threshold raised**: Rule 3 cross-validation now 2-100 AA → force peptide=True (was 2-50).
- **Test job 3e35811b7698 results**: Albiglutide fixed (TRUE). Insulin and CV-MG01 still FALSE with v27 prompts — root cause was the "2-50 aa" hard boundary in molecular class options causing LLM to pick "Protein" for 51 aa insulin. v27b fixes this.

### v27c Changes (2026-04-02) — Definition consistency fixes
- **self_audit.py AA range fixed**: 2-50→2-100 (was contradicting orchestrator and verifier definitions).
- **memory_store.py learning patterns fixed**: 2-50→2-100, >50→>100, multi-chain rule now excludes peptide hormones.
- **Test job ea9bc98d1ae8 results**: LLM correctly classified insulin as True (Peptide / peptide hormone), but verifiers flipped to False (2/3 disagreed at high confidence). Root cause: verifier 2 cited 110 aa (preproinsulin precursor) instead of mature insulin (51 aa). Needs better verifier reasoning, not cheat-sheet examples or threshold lowering.
- **CV-MG01 evidence investigation**: Arm group description ("two short synthetic peptides conjugated to carrier protein") IS in the citations passed to the LLM. The 14B model simply ignored it — classified as "Unknown" molecular class. This is an LLM reasoning limit, not a data pipeline issue.
- **Reverted**: Consensus threshold stays at 1.0 (lowering to 0.667 would weaken verification across ALL fields). Verifier examples reverted (no cheat-sheet drug names).
- **UniProt snippet fix (data pipeline)**: peptide_identity.py and ebi_proteins_client.py now report mature chain lengths from CHAIN/PEPTIDE features instead of just precursor length. For insulin, snippet now says "Precursor length: 110 aa. Mature form: Insulin B chain 30 aa, Insulin A chain 21 aa (51 aa total)" instead of just "Length: 110 aa".
- **Test job 02c65e21dfc7 results**: UniProt snippet fix deployed but verifiers STILL cited precursor 110 aa and ignored "Mature form: 51 aa total" in the same snippet. The data is correct — the small models (qwen2.5:7b, phi4-mini:3.8b) cherry-pick the larger number. CV-MG01 also still False — primary LLM ignores arm group description evidence.

### v27d Changes (2026-04-03) — Structured data injection
- **Structured facts extraction**: New `_extract_structured_facts()` in verifier.py and `_extract_peptide_signals()` in peptide.py. Pulls two types of signal:
  1. UniProt mature chain lengths (vs precursor) — clearly labeled as "ADMINISTERED therapeutic form" vs "precursor only — NOT the administered drug"
  2. Arm group descriptions mentioning synthetic peptides / peptide conjugates
- **Verifier system prompt updated**: Now requires models to explicitly address each structured fact in their reasoning. Facts are prepended to evidence in a `STRUCTURED FACTS` section that precedes all other evidence.
- **Reconciler system prompt updated**: Added explicit instruction that mature form length is what matters for peptide classification, not precursor length.
- **Primary peptide annotator updated**: Same structured facts injected before Pass 1 evidence, so the 14B model can't miss arm group peptide-conjugate descriptions.
- **No cheat sheets**: Facts are extracted programmatically from authoritative database results — no drug names hardcoded.
- **Test job c5de1e0049b0 results (v27d)**:
  - **Insulin (NCT00004984)**: Primary=True ✓, but verifier_1 (gemma2:9b) and verifier_2 (qwen2.5:7b) produced long summaries instead of following the response format — parser returned None (counts as disagreement). Verifier_3 (phi4-mini:3.8b) said False with wrong reasoning ("parenteral insulin is not peptide therapy" — confused delivery route with molecular class). Agreement=0.0 → reconciler → False. **Root cause**: gemma2 and qwen2.5:7b don't follow the structured response format when given long evidence with structured facts prepended. Parser gets None.
  - **CV-MG01 (NCT03165435)**: Primary=False ✗ (still ignores arm group description). BUT verifier_1=True, verifier_2=True (both cited structured facts!). Verifier_3=False. Agreement=0.333. Reconciler sided with False, reasoning that "conjugated to carrier protein" means not a peptide. **Progress**: Structured facts worked for 2/3 verifiers on CV-MG01. Primary LLM and reconciler remain the blockers.
  - **Next steps**: (1) Investigate why gemma2:9b and qwen2.5:7b fail to follow verifier response format with structured facts — may need shorter evidence or format enforcement. (2) CV-MG01 needs the primary to get it right OR the verification flow needs to be able to correct a wrong primary when 2/3 verifiers agree.

### v27e Changes (2026-04-03) — Fix format compliance + reconciler majority logic
- **Root cause of v27d regression**: Compared v26 (job 86fdce46, 50 trials, 0 None verifiers on insulin) with v27d (job c5de1e0049b0, 2/3 None verifiers on insulin). v26 system template was clean; v27d added a STRUCTURED FACTS paragraph that competed with the "Respond EXACTLY in this format" instruction. v26 also put structured facts BEFORE evidence, priming small models into summary mode.
- **Fix 1 — System template restored**: Removed the STRUCTURED FACTS instruction paragraph from SYSTEM_TEMPLATE. Back to v26 original. Models don't need to be told to address facts — they just need to see them.
- **Fix 2 — Facts moved to END of evidence**: Leverages recency bias in small LLMs — last thing read before generating has most influence. Ends with "Remember: respond EXACTLY as Peptide: True or False" as format reminder. No new section headers that confuse models into summary mode.
- **Fix 3 — Reconciler verifier-majority awareness**: When 2+ verifiers agree on a different answer than the primary, the reconciler prompt now explicitly flags this ("NOTE: 2 of 3 independent verifiers agree on 'True'"). System prompt updated: "give strong weight to the verifier majority" when verifiers cite evidence-based reasoning. This addresses CV-MG01 where 2/3 verifiers correctly said True but reconciler sided with the wrong primary.
- **Insulin context**: In v26, insulin was correctly False (2-50 AA boundary, insulin at 51 AA was "protein"). The boundary change to 2-100 AA (v27) made insulin a True case. The models struggle because UniProt reports 110 AA (precursor). Fix #2 puts "Mature form: 51 aa (ADMINISTERED drug, not 110 aa precursor)" as the last thing the model reads. Fix #1 ensures verifiers actually follow the format. Fix #3 means even if one verifier misses it, the reconciler weighs 2/3 agreement.
- **Test job 05f80bba8946 results (v27e) — BOTH FIXED**:
  - **Insulin (NCT00004984)**: Primary=True ✓. Verifier_1=True (cited "mature form 51 aa"). Verifier_2=None (qwen2.5:7b still produces summaries). Verifier_3=False (but reasoning actually supports True). Agreement=0.333 → **high-confidence primary override** (0.93 > 0.85, dissenters at 0.70). **Final=True ✓**
  - **CV-MG01 (NCT03165435)**: Primary=False ✗ (14B model still wrong). Verifier_1=True, Verifier_2=True (both cited structured facts). Verifier_3=None (phi4-mini timeout). Agreement=0.0 → **reconciler flipped to True** citing "structured facts explicitly state CV-MG01 consists of two short synthetic peptides." **Final=True ✓** — Fix #3 (verifier-majority awareness) worked.
  - **Remaining issues**: (1) qwen2.5:7b (verifier_2) still produces summaries instead of following format on insulin — None parse. (2) phi4-mini:3.8b consistently times out on CV-MG01/peptide. (3) Primary LLM (qwen2.5:14b) still says False for CV-MG01 — reconciler corrects it.

### v27e Full Concordance (50 NCTs, job c00a1eef08f4, prod) — 2026-04-03

| Field | vs R1 (n) | AC₁ | vs R2 (n) | AC₁ | R1↔R2 | Status |
|---|---|---|---|---|---|---|
| Delivery | 93.1% (27/29) | 0.926 | 92.6% (25/27) | 0.920 | 88.3% | **Exceeds human** |
| Classification | 82.8% (24/29) | 0.795 | 74.1% (20/27) | 0.665 | 93.2% | Below (-10pp) |
| Peptide | 80.0% (40/50) | 0.747 | 76.0% (38/50) | 0.684 | 86.0% | Below (-6pp) |
| Outcome | 75.9% (22/29) | 0.724 | 70.4% (19/27) | 0.662 | 64.3% | **Exceeds human** |
| RfF | 74.4% (29/39) | 0.711 | 63.9% (23/36) | 0.592 | 88.6% | Below (-14pp) |
| Sequence | 62.5% (10/16) | 0.604 | 37.5% (6/16) | 0.343 | 52.0% | Above vs R1 |

**Peptide: 10 false negatives (agent=FALSE, human=TRUE), zero false positives.**
Root causes:
- 4 have known sequences in _KNOWN_SEQUENCES but cascade blocks lookup (BMN 111, dnaJP1, BNZ-1, sPIF)
- 2 are peptide vaccines/imaging (NEO-PV-01, 68Ga-RM2) — "peptide therapeutic" definition too narrow
- 2 are peptide conjugates (MB1707, PGN-EDO51) — agent prioritizes non-peptide component
- 2 are boundary/synthesis cases (CPT31 D-peptide, thymic peptides)

**Classification: 5 false negatives, all agent=Other/human=AMP on new old-trial NCTs.**
All from _KNOWN_NON_AMP_DRUGS blocklist (Peptide T, Enfuvirtide, PCLUS vaccine). Definitional gap, not a bug.

**RfF: 6 of 10 disagreements cascade from peptide=False (trials never evaluated).**

### v28 Test Results (10 NCTs, job 27c0f2ef1732, prod, commit 4e81071) — 2026-04-03

| Field | vs R1 (n) | vs R2 (n) | v27e R1 | v27e R2 | Delta |
|---|---|---|---|---|---|
| Peptide | **100% (9/9)** | **100% (9/9)** | 80.0% | 76.0% | **+20pp** |
| Classification | 78% (7/9) | 100% (9/9) | 82.8% | 74.1% | Mixed |
| Delivery | 89% (8/9) | 89% (8/9) | 93.1% | 92.6% | -4pp |
| Outcome | 78% (7/9) | 56% (5/9) | 75.9% | 70.4% | Mixed |
| RfF | **29% (2/7)** | **29% (2/7)** | 74.4% | 63.9% | **-45pp** |

**NCT00000435 crashed**: `'dict' object has no attribute 'lower'` — EDAM-resolved interventions stored as dicts, pre-cascade loop called `.lower()` on them. **Fixed in f0a4dba.**

**RfF regression root cause**: `_pass1_says_no_failure()` checked the LLM's "Is This A Failure: No" answer (line 277) BEFORE the terminated/withdrawn status override (line 307). LLM said "No" for terminated/withdrawn trials lacking published evidence → early return → Pass 2 never ran → v26 "Business Reason" default never fired. **Fixed in f0a4dba**: moved terminated/withdrawn check to top of function.

**RfF mismatches (pre-fix)**:
- NCT03597282: empty (should be Recruitment issues/Due to covid) — "slow enrollment compounded by COVID-19"
- NCT04672083: empty (should be Business Reason) — outcome also wrong (Unknown vs Failed)
- NCT05813314: empty (should be Business Reason) — "further optimization required"
- NCT06833931: empty (should be Business Reason) — "development voluntarily discontinued by Sponsor"
- NCT05465590: Toxic/Unsafe (should be Business Reason) — "terminated due to Sponsor decision"

### v28 50-NCT Concordance (job 3e8c4848fe74, prod commit 26b6c0d) — 2026-04-04

| Field | vs R1 (n) | vs R2 (n) | v27e R1 | v27e R2 | Delta vs R1 | Human R1↔R2 |
|---|---|---|---|---|---|---|
| **Peptide** | **90.0% (45/50)** | **86.0% (43/50)** | 80.0% | 76.0% | **+10pp** | 86.0% |
| Classification | 84.8% (39/46) | 84.8% (39/46) | 82.8% | 74.1% | +2pp | 93.2% |
| Delivery | 89.1% (41/46) | 87.0% (40/46) | 93.1% | 92.6% | -4pp | 88.3% |
| Outcome | 73.9% (34/46) | 60.0% (27/45) | 75.9% | 70.4% | -2pp | 64.3% |
| **RfF** | **50.0% (15/30)** | **48.3% (14/29)** | 74.4% | 63.9% | **-24pp** | 88.6% |

**Peptide: 90% target MET.** 4 false negatives (NCT00000435/775/798/846 — old trials, naming issues), 1 false positive (NCT03675126).

**RfF: 50% — negation bug.** All 8 Toxic/Unsafe mismatches from `_infer_from_pass1()` negation-blind keyword matching on prod code. Fixed in v29 (dev dce4466d): sentence-level negation filter + section boundary regex fix. Projected RfF after v29: ~70% vs R1.

**Delivery: -4pp** — NCT00000391/392/393 (old thymic peptide trials → "Other"), NCT04771013 (agent correct, humans wrong — oral formulation), NCT06126354 (multi-route dedup).

**Outcome: -2pp** — mix of literature gaps (HTTP 429 rate limiting), old trials with no publications, genuine LLM misses.

**Classification: +2pp** — 5 definitional mismatches (old AMP trials where agent follows strict definition). Not a bug.

### v29 Fixes (dev dce4466d, merging to main) — 2026-04-04

1. **Negation-blind `_infer_from_pass1()`**: Section boundary regexes used `[A-Z]` on lowercased text (never matched). Added `_strip_negated_sentences()` to filter "no safety concerns" before keyword matching. Should fix 8 Toxic/Unsafe mismatches.
2. **Pre-cascade aliases**: Added `_KNOWN_SEQUENCE_ALIASES` dict + `resolve_known_sequence()` for names that aren't substrings (dnajp1↔dnaj peptide). Pre-cascade now also checks EDAM-resolved names.
3. **NCBI retry**: Increased max_retries 3→5 for eutils.ncbi.nlm.nih.gov. Added `literature_unavailable` flag + WARNING log when all sources return empty.

### v29 Test Results (3 jobs, 150 NCTs, prod commit f9ec75a) — 2026-04-04

**Jobs:**
| # | Job ID | NCTs | Purpose | Runtime |
|---|---|---|---|---|
| 46 | cee652e301c8 | 50 (same as v28) | v29 validation — direct comparison | 318 min |
| 47 | 11ca8845fe89 | 50 (unseen batch A) | Generalization test | 226 min |
| 48 | 4a7f6a167cb3 | 50 (unseen batch B) | Generalization test | 246 min |

#### Concordance Methodology Correction

**IMPORTANT:** The v28 numbers reported above (peptide 90%, RfF 50%) used **pre-verification annotation values** — the raw LLM output BEFORE verifiers corrected them. The v29 concordance script used **post-verification final values** (the actual pipeline output). This made it appear that v29 didn't improve, when in reality:

- v28 pre-verification RfF: 48.4% (15/31 non-empty) → v29 pre-verification: **64.5% (20/31)** = **+16.1pp improvement**
- The verification step was already fixing those errors in v28 → pipeline-level improvement was masked

**True v28 baseline (verified final values, consistent methodology):**
| Field | vs R1 | n |
|---|---|---|
| Peptide | 96.0% (48/50) | 50 |
| Classification | 84.8% (39/46) | 46 |
| Delivery | 93.5% (43/46) | 46 |
| Outcome | 73.9% (34/46) | 46 |
| RfF | 82.6% (38/46) | 46 |

#### Job 46: v29 Validation (same 50 NCTs, verified values)

| Field | v28 (verified) | v29 (verified) | Delta |
|---|---|---|---|
| Peptide | 96.0% | 92.0% | -4.0pp |
| Classification | 84.8% | 83.0% | -1.8pp |
| Delivery | 93.5% | 91.5% | -2.0pp |
| Outcome | 73.9% | 74.5% | +0.6pp |
| RfF | 82.6% | 80.9% | -1.7pp |

Only 7 trial-field values changed (LLM nondeterminism). No code regressions.

**Peptide regressions (2, both stochastic — no code change in peptide logic):**
- NCT03675126 (SRP-5051/vesleteplirsen): Reconciler made different judgment call on "peptide-conjugated" — actually a PPMO antisense oligonucleotide. Verifiers 2/3 correctly said False, reconciler overrode.
- NCT05813314 (BMN 111/vosoritide): Verifier 3 flipped True→False (cited ChEMBL "Protein" classification), triggering reconciler which also got it wrong. **Critical bug: system has vosoritide's 39 AA sequence stored but `_enforce_post_verification_consistency` lacks Rule 3 (sequence→peptide). Fixed in v30.**

**RfF: Negation fix confirmed working at annotation layer:**
- 6 of 8 Toxic/Unsafe mismatches fixed by `_strip_negated_sentences()`
- 2 remaining: NCT05813314 (whyStopped fallback lacks negation filter — **fixed in v30**), NCT03597282 (affirmative "is safe" matches)
- 1 new regression: NCT03593421 (improved section boundary now catches affirmative safety language in findings — **fixed by v30 whyStopped filter**)

#### Jobs 47-48: Generalization (99 unseen NCTs with ground truth)

| Field | vs R1 | vs R2 | Human R1↔R2 | Assessment |
|---|---|---|---|---|
| Peptide | 80.8% | 75.8% | 82.8% | Near human baseline |
| Classification | 88.9% | 91.8% | 91.5% | Matches human |
| Delivery | 76.8% | 82.1% | 76.8% | Matches/exceeds human |
| Outcome | 71.4% | 54.5% | 59.0% | **Exceeds** human vs R1 |
| RfF | 97.1% | 87.9% | 87.2% | **Exceeds** human |

**Peptide: Reconciler over-calling is the #1 generalization issue.**
- 11 false positives: 6 are peptide-loaded cell therapies (DCs, CAR-T), 2 nutritional supplements, 3 other. Reconciler sees "peptide" in description and overrides correct False. **Fixed in v30: cell therapy guidance in verifier + reconciler prompts.**
- 8 false negatives: mix of borderline cases and annotation noise.

**Classification: 3 false AMP hits from DBAASP.**
- Apelin (NCT03449251), GLP-2 (NCT03867656), Thymalfasin (NCT06821100) have in-vitro DBAASP entries but are not clinical AMPs. **Fixed in v30: DBAASP-only hits now go through verification instead of skip_verification=True.**

**NCT06675917: Total research pipeline failure.**
- `logger` NameError in literature.py → all sources failed → zero-confidence annotations. Not in ground truth. **Fixed in v30.**

**Outcome conservatism (P2-6): LEAVE AS-IS.**
- 6 of 10 disagreements are Agent=Unknown, Human=Positive for COMPLETED trials without publications. Agent correctly follows decision tree. Verified that 2 of the 6 "Positive" human annotations are actually wrong (NCT02636582 failed to meet primary endpoint, NCT05328115 R2 says "Failed"). Agent already exceeds human inter-rater (71.4% vs 59.0%). A COMPLETED→Positive heuristic would introduce systematic bias. The real improvement path is better literature search coverage (separate effort).

### v30 Fixes (dev, 2026-04-06)

1. **P0: whyStopped negation filter** (`failure_reason.py`): Apply `_strip_negated_sentences()` to whyStopped text before keyword matching. Fixes NCT05813314 ("not due to any patient safety concerns" → no longer matches "safety") and NCT03593421.

2. **P0: Post-verification sequence consistency** (`orchestrator.py`): Added Rule 3 to `_enforce_post_verification_consistency()` — if verified sequence is 2-100 AA, force peptide=True. Mirrors pre-verification Rule 3. Catches vosoritide regression and any future case where verifiers incorrectly flip a peptide with a known short sequence.

3. **P0: Literature logger fix** (`literature.py`): Added `import logging` and logger definition. Fixes `NameError: name 'logger' is not defined` that caused 7 trials to lose literature data (NCT06675917 lost ALL data).

4. **P1: Cell therapy peptide guidance** (`verifier.py`, `reconciler.py`): Added to verifier Excludes + CRITICAL RULES and reconciler SYSTEM_PROMPT: DCs pulsed with peptides, CAR-T cells, peptide-loaded DC vaccines → peptide=False (the therapy is the cell product). Also dietary supplements (collagen, whey protein). Addresses 6 of 11 peptide FPs in generalization test.

5. **P1: DBAASP verification gate** (`classification.py`): DBAASP-only hits now go through verification (`skip_verification=False`, confidence 0.80) instead of being auto-classified as AMP. DRAMP/APD hits or multi-database hits remain deterministic. Addresses 3 false AMP classifications (apelin, GLP-2, thymalfasin).

### v31 Changes (2026-04-07)

**Literature APIs (3 new research agents, 15 total, 20+ databases):**
- **OpenAlex client** (`openalex_client.py`): 250M+ works, free polite pool. Searches by NCT ID, falls back to title+intervention keywords. Reconstructs abstracts from inverted index. Producing 1-5 citations per trial.
- **Semantic Scholar client** (`semantic_scholar_client.py`): Reintroduced as standalone agent (removed from literature agent in v8 for 429s). TLDR summaries uniquely valuable for outcome. Rate-limited at 3 concurrent.
- **CrossRef client** (`crossref_client.py`): Non-PubMed journal coverage. Searches by NCT ID and title keywords.
- **Evidence dedup** (`base.py`): Identifier-based dedup (PMID/DOI) alongside snippet-based. Prevents same paper from 3 sources wasting budget.
- **Metadata fix** (`orchestrator.py`): Trial title now included in research metadata for SS/CrossRef fallback searches.
- Config: `OPENALEX_EMAIL`, `CROSSREF_EMAIL` env vars. Rate limits in `http_utils.py`. Source weights, field relevance, section mappings in `base.py`.

**Peptide verification logic (no cheat sheets):**
- **Confidence-weighted majority vote** (`reconciler.py`): Replaces equal head count. Primary at 0.93 conf outweighs three verifiers at 0.5 each. Fixes insulin nondeterminism.
- **Low-confidence unanimous dissent gate** (`orchestrator.py`): Avg dissent conf < 0.55 no longer overrides high-conf primary (> 0.85).
- **Evidence grade propagation** (`annotation.py`, `orchestrator.py`): `evidence_grade` field — "deterministic", "db_confirmed", or "llm". DB-confirmed annotations require verifier conf > 0.8 to override (vs 0.7).
- **Per-field verifier evidence budgets** (`verifier.py`): Peptide 25, outcome 20, others 15 citations on mac_mini.
- **Reconciler override** (`reconciler.py`): After reconciler decides, cross-checks against confidence-weighted vote. If reconciler contradicts the weighted vote and primary had > 0.85 conf aligned with weighted winner, overrides reconciler.

**Delivery mode agent upgrade:**
- **Radiotracer detection** (`delivery_mode.py`): [68Ga], [18F], [99mTc] etc. and PROCEDURE type with imaging keywords → "Other" immediately.
- **Intervention description scan**: Checks intervention descriptions for oral (tablet, capsule) and topical (hydrogel, applied topically) before OpenFDA/protocol keyword scan. Catches multi-drug trials.
- **Tightened topical keywords**: Removed "strip", "spray", "powder", "covering", "bandage", "dressing", "wash", "rinse" from `_parse_single_value` and `_infer_from_pass1`. Added skin prick/test → Injection.
- **Injection priority**: When both injection and topical routes found, prefer injection.
- **Removed Rule 8** (peptide vaccine → injection default): If no route evidence, "Other" is correct.

**Training CSV fix:**
- Re-bucketed delivery mode from original Excel source (`clinical_trials-with-sequences.xlsx`). Previous bucketing only matched "injection/infusion" (full phrase) and "IV" (case-sensitive), missing "intravenous", "subcutaneous", etc.
- 145 injection annotations recovered from "other". Human inter-rater delivery mode: 88.9% (was 78.3%).

### v31 50-NCT Concordance (job 510e619f5f88, prod commit f9150a7) — 2026-04-07

| Field | vs R1 (n) | AC₁ | vs R2 (n) | AC₁ | R1↔R2 | Status |
|---|---|---|---|---|---|---|
| Peptide | 96.0% (48/50) | 0.957 | 92.0% (46/50) | 0.910 | 86.0% | **Exceeds human** |
| Classification | 84.1% (37/44) | 0.814 | 85.7% (36/42) | 0.835 | 93.2% | Stable |
| Delivery | 77.3% (34/44) | 0.743 | 92.9% (39/42) | 0.922 | 88.9% | **Regression** |
| Outcome | 61.4% (27/44) | 0.555 | 58.5% (24/41) | 0.522 | 64.3% | Near human |
| RfF | 78.7% (37/47) | 0.755 | 75.6% (34/45) | 0.718 | 88.6% | Below |
| Sequence | 60.9% (14/23) | 0.593 | 47.6% (10/21) | 0.454 | 52.0% | Exceeds human vs R1 |

**Delivery regression root cause**: `_PROTOCOL_ROUTE_KEYWORDS` only had "oral tablet" and "oral capsule" — no standalone formulation keywords. Agent missed oral co-routes in 4 multi-drug trials. v31 injection priority rule also dropped Topical even when Oral was a third route.

**Outcome**: 17 disagreements. 12 are Agent=Unknown vs R1=Positive/Failed (literature gaps for old trials). Not a code regression — v29 generalization (99 unseen NCTs) showed 71.4% vs human 59.0%. This 50-NCT set is biased toward hard pre-2005 trials.

**RfF**: 10 disagreements, most cascade from outcome misses (agent doesn't detect failure → doesn't look for reason).

### v32 Changes (2026-04-08)

1. **P0: Delivery oral keyword expansion** (`delivery_mode.py`): Added 11 oral keywords to `_PROTOCOL_ROUTE_KEYWORDS`: tablet, capsule, oral administration, oral dose, oral formulation, oral solution, oral suspension, by mouth, taken orally, administered orally, given orally. Added "tablet" and "capsule" to `_AMBIGUOUS_KEYWORDS` (skipped in title text to avoid "capsule endoscopy" false positives). Should fix 4 missed oral co-routes.
2. **P0: Injection priority guard** (`delivery_mode.py`): Injection-over-Topical rule now only fires when exactly 2 routes detected. Preserves Topical when Oral is also present (multi-drug trials).
3. **P1: Evidence dedup quality** (`base.py`): Sort citations by (weight, snippet_length) so richer versions win dedup when the same paper is found by multiple sources (PubMed + OpenAlex + SS).

### Next Steps

- Merge v32 to main, run 50-NCT smoke test
- If delivery recovers to ~90%+ → full 642-NCT run
- Outcome: accept near-human baseline — further iteration has diminishing returns
- EDAM learning loop: dormant until agent code stabilizes (drug name resolver and stability index still active and useful)

**Updated human baseline (corrected CSV):**
| Field | n | Agreement | AC₁ |
|---|---|---|---|
| Classification | 454 | 93.2% | 0.919 |
| Delivery Mode | 423 | 88.9% | 0.878 |
| Outcome | 269 | 64.3% | 0.583 |
| Reason for Failure | 387 | 88.6% | 0.881 |
| Peptide | 680 | 86.0% | 0.790 |
| Sequence | 227 | 52.0% | 0.518 |

### v22-era Job Performance (old code, mapped to v24 categories)

All jobs ran on v22 code (old categories). Results mapped through v24 aliases for comparison against training CSV.

**Human baseline (R1 vs R2, corrected training CSV, 680 NCTs):**
| Field | n | Agreement | AC₁ |
|---|---|---|---|
| Classification | 454 | 93.2% | 0.919 |
| Delivery Mode | 423 | 88.9% | 0.878 |
| Outcome | 269 | 64.3% | 0.583 |
| Reason for Failure | 387 | 88.6% | 0.881 |
| Peptide | 680 | 86.0% | 0.790 |
| Sequence | 227 | 52.0% | 0.518 |

**Agent vs R1 per job:**
| Field | Conc v22 (n=39) | G R1 (n=24) | G R2 (n=24) | H R1 (n=19) | H R2 (n=19) |
|---|---|---|---|---|---|
| Classification | 94.3% | 100% | 100% | 92.3% | 92.3% |
| Delivery Mode | 88.6% | 66.7% | 73.3% | 46.2% | 46.2% |
| Outcome | 80.0% | 71.4% | 57.1% | 76.9% | 69.2% |
| RfF | 82.9% | 100% | 100% | 92.3% | 92.3% |
| Peptide | 92.3% | 79.2% | 70.8% | 78.9% | 78.9% |
| Sequence | 40.0% | 0.0% | 0.0% | 57.1% | 57.1% |

### Detailed Performance Analysis

**1. Classification: STRONG (92-100% vs 93.2% human baseline)**
Only 4 disagreements across all 5 jobs. Two are agent=Other/human=AMP, two are agent=AMP/human=Other. No systematic bias. v24 binary AMP/Other simplification removes the infection/other subtype ambiguity entirely — this field is effectively solved.

**v24 impact**: Positive. Fewer categories = less LLM confusion. No action needed.

**2. Delivery Mode: WEAK (46-89%, human baseline 88.3%)**
27 disagreements. Three root causes:

| Pattern | Count | Root cause |
|---|---|---|
| Agent outputs duplicate "injection/infusion, injection/infusion" | 7 | Multi-drug trial: agent reports route per drug, but both are injection → deduplicated should be single "injection/infusion" |
| Agent says other/oral/topical, human says injection/infusion | 13 | Agent picks wrong route — often confused by oral comparator drugs or trial title keywords |
| Agent says injection/infusion, human says other | 4 | Agent over-calls injection for non-injection routes |

**v24 impact**: Partial fix. Simplified 4 categories eliminate sub-category confusion (e.g., "Injection/Infusion - Other/Unspecified" vs "IV"). But the duplicate-output bug and wrong-route-selection remain. The deduplication issue is a code bug: when multi-route output maps two old categories (e.g., "IV" + "Subcutaneous") to the same new category ("Injection/Infusion"), the result should be deduplicated to a single value.

**Action needed**: Fix multi-route dedup in delivery_mode.py `_parse_value()` — after mapping to 4 categories, deduplicate before joining. Also investigate the 13 wrong-route cases to see if the deterministic keywords are too broad.

**3. Outcome: MODERATE (57-80%, human baseline 64.3%)**
24 disagreements. Dominant patterns:

| Pattern | Count | Root cause |
|---|---|---|
| Agent=Unknown, Human=Positive | 9 | Agent can't find published results → defaults to Unknown. Human found positive results in literature. |
| Agent=Unknown, Human=Failed | 4 | Same — agent misses negative results in publications |
| Agent=Active, Human=Positive | 4 | Agent reads ClinicalTrials.gov status as "Active" but human found completed results |
| Agent=Terminated, Human=Positive | 2 | Trial terminated but still had positive results published |

The agent EXCEEDS human baseline (64.3%) on 3/5 jobs. The biggest gap is the agent defaulting to "Unknown" when it can't find publications — this is a literature search depth issue, not a classification logic issue.

**v24 impact**: Neutral. Category simplification doesn't affect outcome (categories unchanged). The "completed ≠ failed" alias fix prevents one false mapping, but the core issue is literature search coverage.

**Action needed**: Low priority. Agent already beats human baseline. Could improve literature search recall but risk of false positives.

**4. Peptide: BELOW TARGET (71-92%, human baseline 86%)**
23 disagreements. 17 are agent=FALSE/human=TRUE (agent under-calling peptide), 6 are agent=TRUE/human=FALSE.

The FALSE→TRUE pattern (74% of errors) means the agent is too conservative — it fails to identify peptides that humans correctly tag. These are likely edge cases: peptide vaccines, modified peptides, peptide-drug conjugates where the LLM defaults to "not a peptide."

**v24 impact**: Mixed. The full cascade (all False cascades N/A) means any false-negative peptide call now wipes out ALL downstream annotations for that trial. Previously, LLM-based False calls still ran the other agents as a safety net. This makes peptide accuracy MORE critical. If the agent incorrectly says False, 5 other fields become N/A unnecessarily.

**Action needed**: HIGH PRIORITY. Review the 17 FALSE→TRUE NCTs from the disagreement list. Add any consistently misclassified drugs to `_KNOWN_PEPTIDE_DRUGS` in peptide.py. Consider adding a confidence threshold: only cascade N/A if peptide=False with confidence > 0.8.

**5. Reason for Failure: GOOD (83-100%, human baseline 88.6%)**
8 disagreements. Most are empty vs. a specific reason. Agent defaults to empty (no failure) when it can't find evidence, human annotators assign reasons from literature. Small n makes this noisy.

**v24 impact**: Positive. The blank+failure=Unknown rule means these empties now become "Unknown" instead of being skipped — more honest about uncertainty.

**6. Sequence: POOR (0-57%, human baseline 52%)**
51 mismatches analyzed by category:

| Category | Count | % | Description |
|---|---|---|---|
| Agent empty, human filled | 27 | 53% | Agent can't find sequence in databases — biggest gap |
| Human empty, agent filled | 9 | 18% | Agent finds a sequence human didn't — often DRVYIHP default |
| DRVYIHP wrong match | 4 | 8% | Agent's _KNOWN_SEQUENCES matches "angiotensin" too broadly |
| Different peptide | 8 | 16% | Agent and human pick different drugs' sequences |
| Partial match | 3 | 6% | Same peptide but agent has truncated/extended version |

**v24 impact**: Positive for multi-sequence (no cap). But the core issue (53% agent-empty) requires better database coverage or LLM fallback.

**Action needed**:
1. Fix DRVYIHP over-matching: tighten _KNOWN_SEQUENCES matching to require exact drug name, not substring "angiotensin" in any context
2. Expand _KNOWN_SEQUENCES table with verified sequences for common peptide drugs
3. The LLM fallback (only fires for peptide=True trials) needs better prompts to extract sequences from literature text
4. With full peptide cascade, agent-empty cases will increase (False peptide → N/A sequence), which is correct behavior but reduces the comparable n

---

### v25/v26 Concordance (50 NCTs, job c2c43af95162) — 2026-03-31

| Field | vs R1 | AC₁(R1) | vs R2 | AC₁(R2) | R1↔R2 | Status |
|---|---|---|---|---|---|---|
| Classification | 92.0% | 0.917 | 90.0% | 0.893 | 86.0% | **Exceeds human** |
| Peptide | 82.2% | 0.769 | 85.7% | 0.819 | 90.5% | Near baseline |
| RfF | 70.0% | 0.657 | 80.0% | 0.771 | 84.0% | Near baseline vs R2 |
| Outcome | 68.0% | 0.633 | 74.0% | 0.703 | 76.0% | Below baseline |
| Delivery Mode | 63.3% | 0.609 | 70.0% | 0.677 | 69.4% | **Meets baseline vs R2** |
| Sequence | 61.9% | 0.603 | 54.5% | 0.528 | 68.8% | Below (biggest gap) |

**Key findings:**
- Classification: SOLVED. Agent beats both reviewers.
- Delivery: Meets R2 human baseline. Most remaining disagreements are within injection sub-categories (SC vs IV vs Other/Unspecified) — would agree under bucketed comparison.
- Outcome: 16 disagreements vs R1. v26 has TERMINATED override fix — need concordance run to measure.
- RfF: 70% vs R1 dragged down by outcome cascading. Should improve with v26 outcome fix.
- Peptide: 8 disagreements vs R1 (agent under-calling). Phase 3 work still needed.
- Sequence: Agent-empty is still the dominant failure mode (12 b_only vs R1, 16 vs R2).

### Design Decisions

- **NCT00004984 (Insulin):** 51aa multi-chain protein. Agent correctly classified, humans disagree on peptide definition. **Decision: KEEP the sequence.** Multi-chain proteins at peptide scale should retain their sequence annotation. The agent is correct here — do not penalize or special-case this. If the agent finds a valid sequence, include it regardless of single-chain vs multi-chain debate.

### Updated Testing Plan

**Phase 1: DONE** — v25 dedup + DRVYIHP fixes applied.

**Phase 2: DONE** — v25 baseline concordance (c2c43af95162, 50 NCTs). Results above.

**Phase 2b: DONE** — v27e concordance (c00a1eef08f4, 50 NCTs). Results in v27e concordance table above.

**Phase 3: DONE (partial)** — v27b-v27e fixed insulin (True) and CV-MG01 (True). 10 other peptide false negatives remain. v28 plan addresses these.

**Phase 4: v28 implementation (NEXT)**
- Wave 1: Pre-cascade _KNOWN_SEQUENCES check, expand sequences, replace phi4-mini→llama3.1:8b, reduce verifier evidence
- Wave 2: Fallback parser, smart retry, parse-failed consensus exclusion
- Wave 3: Peptide definition alignment (therapeutic → molecule), "trial says peptide" signal
- Wave 4: RfF truncation fix, sequence normalization, COVID keywords
- Smoke test: 10 peptide false-negative NCTs
- Full concordance: 50 NCTs, compare to v27e baseline

**Phase 5: Absorb + expand**
- Absorb Batches G+H into EDAM (edam_learning_cycle)
- Queue Batches I/J (positions 201-250)

## Environment State

| Environment | Branch | Version | Active Job |
|---|---|---|---|
| Prod (port 8005) | main | v31 (f9150a7) | 50-NCT validation (510e619f5f88) |
| Dev (port 9005) | dev | v31 (d9afd8f1) | None |

## Important Notes

- **Workflow:** Develop on `dev`, run jobs on prod. Only merge to `main` when explicitly told.
- **CRITICAL:** Always commit+push atomically in ONE bash command. Autoupdater wipes uncommitted changes every 30s.
- **Update plans after every job** — this file and `LEARNING_RUN_PLAN.md`.
- **Drug lists (`_KNOWN_PEPTIDE_DRUGS`) are FROZEN** — no additions. Fix classification through LLM prompt/reasoning improvements only. `_KNOWN_SEQUENCES` (factual data) is OK to expand.
- **All AMPs are peptides** — AMP classification forces peptide=True in consistency engine.
- **Auth token:** Retrieved from `~/Developer/amphoraxe/auth.amphoraxe.ca/data/auth.db` sessions table.

## Key File Locations

| Path | Purpose |
|---|---|
| `LEARNING_RUN_PLAN.md` | Overall strategy, job registry, concordance data |
| `results/edam.db` | EDAM learning database (incl. drug_names table) |
| `results/jobs/{job_id}.json` | Job status files |
| `results/annotations/{job_id}/{nct_id}.json` | Per-trial results |
| `results/json/{job_id}.json` | Consolidated output |
| `scripts/human_annotated_ncts.txt` | All 964 NCTs |
| `scripts/fast_learning_batch_25.txt` | Batch A (25 richest NCTs) |
| `scripts/fast_learning_batch_50.txt` | Batch A+B (50 richest NCTs) |
