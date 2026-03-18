# Agent Annotate — Improvement Strategy

Strategy to surpass human annotation accuracy by fixing agent errors, exploiting the agent's structural advantages, and addressing the gaps revealed by a quality audit of both agent output and human annotations.

> **Last updated:** 2026-03-17

> **IMPORTANT DESIGN PRINCIPLE:** Human annotations (`docs/clinical_trials-with-sequences.xlsx`) are used **only for development-time evaluation and prompt refinement** — measuring agent accuracy, identifying error patterns, and tuning prompts. Human annotations are **never used at runtime**. The agents must produce correct annotations independently, relying solely on live data from external APIs (ClinicalTrials.gov, PubMed, UniProt, etc.). The goal is to build agents that don't need a human counterpart.

---

## 1. Human Annotation Quality Audit

Before trying to beat the humans, we need to know how reliable they are. Both replicates in `docs/clinical_trials-with-sequences.xlsx` (~1847 rows each, 4 annotators: Mercan, Maya, Anat, Ali) were audited.

### 1.1 Coverage Gaps

| Field | R1 Filled | R2 Filled | R1 Blank | R2 Blank |
|-------|-----------|-----------|----------|----------|
| Classification | 798 (43%) | 693 (37%) | 1,048 | 1,156 |
| Delivery Mode | 806 (44%) | 628 (34%) | 1,040 | 1,221 |
| Outcome | 617 (33%) | 472 (26%) | 1,229 | 1,377 |
| Reason for Failure | 99 (5%) | 82 (4%) | 1,747 | 1,767 |
| Peptide | 668 (36%) | 244 (13%) | 1,178 | 1,605 |

**~50-65% of rows are unannotated in both replicates.** The agent can annotate 100% of submitted trials.

### 1.2 Inter-Rater Agreement (where both replicates have a value)

| Field | Both Filled | Agree | Disagree | Agreement Rate |
|-------|-------------|-------|----------|----------------|
| Classification | 620 | 568 | 52 | 91.6% |
| Delivery Mode | 579 | 395 | 184 | **68.2%** |
| Outcome | 372 | 207 | 165 | **55.6%** |
| Reason for Failure | 46 | 42 | 4 | 91.3% |
| Peptide | 62 | 30 | 32 | **48.4%** |

**Outcome and Peptide are essentially unreliable** — humans can't agree with each other. This is the biggest opportunity for the agent to surpass humans.

### 1.3 Systematic Human Errors

- **R2 used invalid "Active" (30x)** instead of "Recruiting" or "Active, not recruiting"
- **R2 never used "Recruiting"** (0 instances vs R1's 222) — entire category missing from one annotator's vocabulary
- **R2 missing "Oral - Capsule"** entirely (0 vs R1's 17)
- **Casing inconsistencies**: R2 uses "Oral - unspecified" / "Topical - unspecified" (lowercase)
- **R1 Peptide? is over-broad**: 451 True vs R2's 56 True — one annotator classified far too many interventions as peptides
- **21 missing failure reasons** where Outcome = Terminated/Withdrawn/Failed
- **1 logical inconsistency**: NCT05265806 has Outcome=Recruiting + Reason=Toxic/Unsafe
- **R1 used multi-value delivery modes** (24 rows with comma-separated values like "SC, IV, Oral") — not a valid format

### 1.4 Key Disagreement Patterns

**Outcome** (165 disagreements — biggest problem):
- R1=Recruiting vs R2=Unknown: 27 cases
- R1=Recruiting vs R2=Positive: 26 cases
- R1=Unknown vs R2=Positive: 19 cases
- R1=Failed vs R2=Positive: 12 cases

These disagreements stem from annotators checking ClinicalTrials.gov at different times and with different willingness to search published literature. The agent, with its two-pass investigative strategy and systematic literature search, should resolve these definitively.

**Peptide** (32 disagreements out of 62 overlap):
- R1=True vs R2=False: 27 cases — R1 annotator has an overly broad definition of "peptide"

---

## 2. Agent Error Summary (10 agent-annotated trials)

| NCT ID | Field | Agent | Human | Root Cause |
|--------|-------|-------|-------|------------|
| NCT06729606 | Peptide | False | True | Aviptadil IS VIP (28 AA) — listed in prompt but model ignored it |
| NCT03987672 | Peptide | True | False (both) | Nutritional formula — prompt warns against this but model ignored |
| NCT03984812 | Peptide | True | False (R1) | Multi-subunit protein, antibody-like |
| NCT03998592 | Classification | AMP(other) | AMP(infection) (both) | S. pyogenes vaccine = infection target |
| NCT03989817 | Classification | AMP(other) | Other (both) | VIP is NOT an AMP |
| NCT03998592 | Delivery Mode | IM | Other/Unspecified (both) | Guessed IM — violates rules |
| NCT05415410 | Delivery Mode | Other/Unspec | SC/ID | Missed FDA label signal |
| NCT03984812 | Delivery Mode | Other/Unspec | SC/ID (both) | Missed SC from literature |
| NCT03989817 | Failure Reason | Ineffective | empty (both) | Contradicts Positive outcome |
| NCT04098562 | All fields | Invalid values | N/A | "AMP", "Topical", "Active", "N/A" |

---

## 3. Structural Advantages Over Humans

The agent has inherent advantages that, once errors are fixed, should yield higher accuracy than human annotators:

| Advantage | Impact |
|-----------|--------|
| **100% coverage** | Humans left 50-65% of rows blank. Agent annotates every submitted trial. |
| **Recency** | Agent queries live APIs at annotation time — always gets the latest publications and status updates. Humans annotated at a fixed point and never revisited. |
| **Consistency** | Agent applies the same rules every time. Humans have 48-68% agreement on peptide, delivery mode, and outcome. |
| **Evidence trail** | Agent cites every source with PMIDs, URLs, and identifiers. Humans' "evidence link(s)" columns are mostly blank. |
| **Multi-source verification** | Agent cross-checks ClinicalTrials.gov, PubMed, PMC, UniProt, DRAMP, FDA, web. Humans typically check 1-2 sources. |
| **Two-pass investigation** | Outcome and failure reason agents dig into literature instead of stopping at registry status. |

---

## 4. Recency Principle

**Latest information always wins.** If a trial was "Recruiting" when humans annotated it but has since completed with positive results, the correct annotation is "Positive" — not "Recruiting" or "Unknown."

### Implementation

The research agents already query live APIs, so recency is built in. To make it explicit:

1. **Literature agent**: When searching PubMed/PMC, sort results by publication date descending. Prioritize the most recent publication in the evidence chain. If a 2025 paper reports positive results but a 2023 paper reported inconclusive results, the 2025 paper wins.

2. **Outcome agent Pass 2 prompt**: Add explicit rule: "If multiple publications exist with conflicting conclusions, prefer the most recent publication. Newer data supersedes older data."

3. **Evidence output**: Include `retrieved_at` timestamp in the CSV evidence columns so reviewers can see how current the data is.

4. **Web context agent**: Search for press releases and regulatory decisions (FDA approvals, EMA opinions) that may post-date the published literature.

---

## 5. Citation Gap Fix (DONE)

**Problem**: The full CSV had zero citation data — all evidence (PMIDs, URLs, database identifiers) captured in JSON was dropped during CSV generation.

**Fix applied to `output_service.py`**:

**Standard CSV** now includes per-field evidence columns:
- `Classification Evidence`, `Delivery Mode Evidence`, `Outcome Evidence`, `Reason for Failure Evidence`, `Peptide Evidence`
- Format: deduplicated identifiers — `PMID:36191080; https://clinicaltrials.gov/study/NCT06729606`

**Full CSV** now includes per-field:
- `{field}_evidence_sources` — database:identifier pairs (`clinicaltrials_gov:NCT06729606; pubmed:PMID:36191080`)
- `{field}_evidence_urls` — deduplicated URLs
- `{field}_reasoning` — the model's chain-of-thought (up to 1000 chars)

---

## 6. v3 Concordance Results (n=62, Overnight Jobs)

An overnight concordance run on 62 trials using v3 agents produced the following baseline results. These inform the v4 improvement priorities.

### 6.1 Agreement Rates

| Field | Agent vs R1 | Agent vs R2 | Dominant Error |
|-------|-------------|-------------|----------------|
| Classification | 29.4% | 13.0% | Agent over-classifies as AMP |
| Delivery Mode | 47.6% | 54.1% | Best field (extraction logic works) |
| Outcome | 37.1% | 60.5% | Agent defaults to Unknown too much |
| Failure Reason | 41.9% | 43.5% | Agent over-assigns "Ineffective" |
| Peptide | 66.7% | 60.0% | Brand name resolution failures |

### 6.2 Key Findings

- **Classification is the weakest field** at 29.4% / 13.0%. The v3 negative examples were insufficient; the 8B model still pattern-matches "peptide + disease" to AMP.
- **Delivery Mode is the strongest field** at 47.6% / 54.1%. The priority-ordered extraction hierarchy works well for clear cases.
- **Outcome R1 vs R2 asymmetry** (37.1% vs 60.5%): Agent agrees more with R2 (who checked literature) than R1 (who recorded registry status). This is a feature, not a bug -- the agent's literature search aligns with the annotator who did the same.
- **Failure Reason over-assigns "Ineffective"** to completed trials without published negative results. The agent treats absence of positive results as evidence of failure.
- **Peptide regression** from 88.0% (v2, n=25) to 66.7%/60.0% (v3, n=62): The larger sample exposed brand-name resolution issues not present in the initial 25 trials.

---

## 7. v4 Improvements Implemented (DONE)

The following v4 changes have been implemented in response to the n=62 concordance results:

### 7.1 Four New Research Agents — v4 (DONE)

- **DBAASP Agent**: Queries peptide activity/MIC data. Provides direct antimicrobial activity evidence for the Classification Agent.
- **ChEMBL Agent**: Queries bioactivity and clinical phase data. Provides mechanism-of-action and cross-trial development context.
- **RCSB PDB Agent**: Queries 3D structure metadata. Provides structural confirmation of peptide identity.
- **EBI Proteins Agent**: Queries sequences, variants, functional annotations. Complements UniProt with additional sequence-level data.

Note: Seven more agents were added in v5 (see Section 7.5), bringing the total to 15 research agents querying 20+ free databases.

### 7.2 Annotation Agent Improvements (DONE)

- **Classification**: Added direct antimicrobial mechanism requirement. Must identify which mode of action (A-D) applies with cited evidence. Strengthened default-to-Other.
- **Failure Reason**: Default no-failure for completed trials without published negative results. Failure reason requires affirmative evidence.
- **Peptide**: Added brand name resolution rules. Agent must resolve brand names to generic compounds.
- **Delivery Mode**: Added never-guess reinforcement. Empty is correct when evidence is insufficient.

### 7.3 Verification/Verifier Improvements (DONE)

- **Verifier prompt parity**: All verifiers now receive the same field-specific detail (negative examples, decision trees, extraction hierarchies) as the primary annotation agents.

### 7.4 Output & Infrastructure Improvements (DONE)

- **Citation traceability**: Every field records model identity, agent provenance, source URLs, evidence text, verifier summary.
- **Disk-persisted review queue**: Review queue survives service restarts (written to JSON, reloaded on startup).
- **Pacific timestamps**: All timestamps throughout the system use America/Los_Angeles.
- **Commit hash in metadata**: Job metadata includes the exact git commit hash for reproducibility.
- **Job timing metadata**: `started_at`, `finished_at`, `elapsed`, average time per trial.
- **Kimi K2 Thinking**: Available as primary annotator on the server hardware profile.
- **Ollama keep_alive optimization**: 5 minutes on mac_mini, 60 minutes on server profile.
- **Hardware profiles**: `mac_mini` (16 GB, 8B models, 5m keep_alive) vs `server` (48+ GB, Kimi K2 option, 60m keep_alive).

---

### 7.5 v5: Research Pipeline Expansion from 8 to 15 Agents (DONE)

Expanded the research pipeline from 8 to 15 parallel agents querying 20+ free databases. Seven new agents added:

- **APD Agent** (aps.unmc.edu): AMP database, HTML scraping, best-effort (server requires JS). Provides independent AMP classification source.
- **dbAMP Agent** (yylab.jnu.edu.cn/dbAMP): 33K+ AMPs, HTML scraping, intermittent availability. Broad AMP reference complementing APD and DRAMP.
- **WHO ICTRP Agent** (trialsearch.who.int): International trial registry, HTML parsing. Extends ClinicalTrials.gov coverage to 17+ national/regional registries.
- **IUPHAR Guide to Pharmacology Agent** (guidetopharmacology.org): REST API, mechanism of action, drug targets, ligand classification. Authoritative pharmacological context for classification decisions.
- **IntAct Agent** (ebi.ac.uk/intact): REST API, molecular interactions, UniProt cross-references. Reveals AMP mechanisms through interaction partner analysis.
- **CARD Agent** (card.mcmaster.ca): AJAX endpoints, antibiotic resistance mechanisms, ARO terms. Provides resistance context for AMP clinical trials.
- **PDBe Agent** (ebi.ac.uk/pdbe): Solr search + REST API, structure quality metrics (resolution, R-factor). Complements RCSB PDB with quality assessment data.

SerpAPI was removed (paid service). All 15 agents now use free APIs exclusively.

---

## 7.6 v4.1: Verifier Value Normalization Fix (DONE)

### Problem

Post-v4 analysis revealed that 66% of all review conflicts (68 out of 103) were concentrated in the `reason_for_failure` field. Approximately 57 of those were false disagreements caused by verifier models outputting trial status keywords (COMPLETED, Unknown, N/A, None, ACTIVE_NOT_RECRUITING) instead of the expected empty string. The verifiers correctly determined that no failure reason existed but expressed this using non-canonical values, causing the consensus algorithm to treat them as disagreements.

### Fix

Expanded the value normalization layer in the verification pipeline to catch status-as-value patterns. For `reason_for_failure`, all trial status keywords and common shorthand values (N/A, None, Unknown) are normalized to empty string before consensus checking. The normalization is field-aware: different rules apply per field (e.g., delivery mode normalizes route abbreviations, peptide normalizes boolean variants).

### Impact

Retroactive application across 11 completed jobs:
- **74 individual field values corrected** (verifier opinions remapped to canonical values)
- **12 consensus results restored** (fields now achieve unanimous agreement)
- **12 trials unflagged** from manual review (false disagreements eliminated)

### Maintenance Tool: retroactive_fix.py

The `retroactive_fix.py` script applies the expanded normalization rules to completed jobs. It re-reads stored verifier opinions, normalizes values, recalculates consensus, and updates job results. Supports `--dry-run` for preview and `--job` for targeting specific jobs. See USER_GUIDE.md for full usage.

---

## 7.7 v5.1: Research Agent Bug Fixes — Intervention Name Extraction (DONE)

### Problem

Testing all 15 research agents against known peptides (Nisin, Colistin, Leuprolide) revealed that 12 of 15 agents returned 0 citations despite the peptides existing in their databases. Only clinical_protocol, literature, and WHO ICTRP produced results.

Root cause: agents serialized intervention metadata dicts as strings (`"{'name': 'Nisin'}"`) instead of extracting the name field (`"Nisin"`). Every database search was querying for a Python dict literal.

### Fixes

- **All agents**: Added `_extract_intervention_names()` helper that handles both `[{"name": "X"}]` and `["X"]` formats
- **DBAASP**: Fixed URL (`/peptides` not `/api/v2/peptides`), fixed query params (`name.value=X&name.comparator=like`)
- **CARD**: Removed 3.2MB ARO index download that frequently timed out; livesearch alone is sufficient
- **IUPHAR**: Added case-variant search (original + lowercase)
- **Literature/Semantic Scholar**: Added 1s delay to prevent 429 rate limiting

### Verification Results

| Agent | Nisin (known AMP) | Colistin (known AMP) | Leuprolide (non-AMP) |
|-------|:-:|:-:|:-:|
| DBAASP | 5 citations | 4 citations | 0 (correct) |
| CARD | 0 (correct, no resistance data) | 5 citations | 0 (correct) |
| ChEMBL | 3 citations | 3 citations | 3 citations |
| IUPHAR | 0 | 1 citation | 1 citation |
| IntAct | 1 citation | 0 | 0 |
| Peptide Identity | 2 citations | 2 citations | 2 citations |

DBAASP now provides MIC/activity data that directly proves AMP status. CARD provides resistance mechanism data for known antimicrobials. These should significantly improve classification accuracy.

---

## 8. v6 Concordance Results: Version Comparison (n=70)

Two annotation jobs were run on the **same 70 NCT IDs** using different agent versions, enabling a direct head-to-head comparison of the impact of agent improvements and research pipeline fixes.

- **OLD job (08219e16a405):** Commit `22e9792`, config hash `6230af65d248`, 2026-03-16. Research pipeline partially broken — ChEMBL, Peptide Identity, DBAASP, IntAct, IUPHAR, WHO ICTRP all returned 0 citations.
- **NEW job (34f1d3bb2cf7):** Commit `8553a1f`, config hash `879288a77361`, 2026-03-17. All annotation agents improved (commit `526f4e1`), cheat sheets removed (`ccd92fd`), noisy research agents fixed (`8553a1f`).

### 8.1 Research Coverage: +162% Total Citations

| Agent | OLD citations | NEW citations | Delta | Notes |
|---|---|---|---|---|
| ChEMBL | 0 | 366 | +366 | Was broken (dict serialization), now fixed |
| IntAct | 0 | 305 | +305 | New agent, producing rich interaction data |
| Literature | 154 | 284 | +130 | Better PubMed/PMC coverage |
| Peptide Identity | 0 | 135 | +135 | Was broken, now returns UniProt/DRAMP data |
| WHO ICTRP | 0 | 69 | +69 | New agent, international registry coverage |
| IUPHAR | 0 | 58 | +58 | New agent, pharmacology/mechanism data |
| DBAASP | 0 | 40 | +40 | Was broken (URL/params), now returns MIC data |
| CARD | 0 | 6 | +6 | New agent, resistance data for known AMPs |
| Clinical Protocol | 530 | 530 | 0 | Unchanged (already working) |
| APD, dbAMP, EBI, RCSB, PDBe, Web | 0 | 0 | 0 | **Still broken — need investigation** |
| **TOTAL** | **684** | **1,793** | **+1,109** | |

**6 agents still produce 0 citations:** APD (JS-dependent), dbAMP (intermittent availability), EBI Proteins, RCSB PDB, PDBe, Web Context (DuckDuckGo). These should be investigated and fixed.

### 8.2 Concordance vs Human Ground Truth

| Field | OLD vs R1 | NEW vs R1 | Delta | OLD vs R2 | NEW vs R2 | Delta |
|---|---|---|---|---|---|---|
| **Outcome** | 40.9% | **72.7%** | **+31.8pp** | 52.2% | 54.3% | +2.2pp |
| Reason for Failure | 44.4% | 55.6% | +11.1pp | 57.1% | 57.1% | 0 |
| Classification | 75.8% | 75.8% | 0 | 82.3% | 82.3% | 0 |
| Delivery Mode | 50.0% | 50.0% | 0 | 46.5% | 46.5% | 0 |
| **Peptide** | 83.3% | **77.1%** | **-6.2pp** | — | — | — |

**Outcome +31.8pp is the largest single-version improvement in the project.** The combination of fixed research agents (providing actual literature citations) and improved completion heuristics resolved 36 of 41 "Unknown" outcomes to "Positive". Of the 19 newly correct outcomes vs R1, most were old completed Phase I/II trials where the agent now finds published results or correctly applies completion heuristics.

**Peptide -6.2pp is a regression** caused by multi-drug trial confusion. In 3 trials (NCT01673217, NCT01687595, NCT01697527), the agent evaluated a co-administered small molecule or adjuvant instead of the peptide intervention, leading to False when the correct answer was True.

### 8.3 Review Rate Improvement

| Field | OLD reviews | NEW reviews | Delta |
|---|---|---|---|
| Outcome | 20/70 | 8/70 | -12 |
| Reason for Failure | 24/70 | 20/70 | -4 |
| Delivery Mode | 5/70 | 1/70 | -4 |
| Classification | 0/70 | 1/70 | +1 |
| Peptide | 1/70 | 2/70 | +1 |
| **Total field reviews** | **50** | **32** | **-18 (-36%)** |

### 8.4 Annotation Stability Between Versions

| Field | Agree | Changed | Stability |
|---|---|---|---|
| Classification | 67/70 | 3 | 95.7% |
| Peptide | 63/70 | 7 | 90.0% |
| Delivery Mode | 61/70 | 9 | 87.1% |
| Outcome | 32/70 | 38 | 45.7% |
| Reason for Failure | 31/70 | 39 | 44.3% |

Outcome and failure reason are highly coupled — when outcome shifts from Unknown to Positive, failure reason shifts from "Ineffective" to EMPTY. This coupling explains the coordinated instability.

### 8.5 Outcome Regression Analysis

The new agents fixed 19 outcomes vs R1 but introduced 5 regressions:

| NCT | NEW value | Human R1 | Root Cause |
|---|---|---|---|
| NCT01651715 | Positive | Failed | Phase I/II completed, no published results — H1 heuristic overrode "failed" evidence |
| NCT01654120 | Positive | Unknown | Liraglutide Phase IV — agent inferred positive from completion |
| NCT01660529 | Positive | Unknown | Early Phase I peptide vaccine — H1 heuristic applied |
| NCT01673217 | Positive | Unknown | NY-ESO-1 Phase I — H1 heuristic applied despite below-threshold evidence |
| NCT01689051 | Positive | Unknown | GLP-1 study, no published results — H1 heuristic too aggressive |

**Pattern:** All 5 regressions vs R1 are H1 heuristic over-applications (Phase I completion = Positive), applied even when:
- No publications found (NCT01689051, NCT01660529, NCT01673217)
- Evidence quality is below threshold (NCT01673217 had only 1 source when 2 were required)
- The human annotator said Unknown (meaning no result evidence was available)

Against R2, there are 12 regressions — most follow the same pattern: agent says Positive for completed trials where R2 said Unknown because no publications were found.

### 8.6 Peptide Regression Analysis

3 trials regressed from True → False:

| NCT | Intervention | Root Cause |
|---|---|---|
| NCT01673217 | NY-ESO-1 peptide vaccine + decitabine | Agent focused on decitabine (small molecule), ignored peptide vaccine |
| NCT01687595 | HerpV peptide vaccine + QS-21 adjuvant | Agent focused on QS-21 adjuvant, ignored HerpV peptides |
| NCT01697527 | TCR cells + aldesleukin (IL-2) | Agent correctly ID'd aldesleukin as protein but verifiers overrode to False |

**Pattern:** In multi-drug trials, the agent evaluates whichever intervention ChEMBL returns data for first (typically small molecules), rather than examining all interventions. The peptide prompt says "If a trial tests MULTIPLE drugs and only ONE is a peptide, answer True" but the two-pass extraction focuses on a single intervention.

### 8.7 Failure Reason Value Normalization Issues

The parser still allows non-canonical values through:
- `INEFFECTIVE_FOR_PURPOSE` (uppercase sentinel) appears 7 times in new results
- `INEFFECIVE_FOR_PURPOSE` (typo) appears 1 time
- `EMPTY` (string) vs `""` (empty string) used inconsistently

These are not genuine disagreements but formatting artifacts. The `_parse_value()` method catches most variants but the uppercase sentinel values from the pre-check skip path bypass parsing entirely.

### 8.8 Verifier Disagreement Patterns (NEW job)

| Field | Pattern | Count | Automatable? |
|---|---|---|---|
| Outcome | Positive vs Unknown | 3 | Yes — add H1-H5 heuristics to verifier prompts |
| Outcome | Positive vs Failed | 4 | Partially — need published evidence to adjudicate |
| Outcome | Positive vs Recruiting | 1 | Yes — check current registry status |
| Reason for Failure | Primary=EMPTY, verifiers=Ineffective | 12 | Yes — pass outcome to verifiers |
| Reason for Failure | Primary=EMPTY, verifiers=Toxic | 5 | Yes — pass outcome to verifiers |
| Delivery Mode | IM vs Other/Unspecified | 1 | Yes — check explicit route mentions |
| Peptide | True vs False | 2 | Partially — multi-drug disambiguation needed |

**25 of 32 review items are automatable** using cross-field consistency enforcement and heuristic-aware verifier prompts.

---

## 9. v7 Improvement Plan

Based on the v6 concordance analysis, six targeted improvements:

### 9.1 Cross-Field Consistency Enforcement (Priority: CRITICAL)

Implement `_enforce_consistency()` in the orchestrator, called AFTER verification:
- `outcome ∈ {Positive, Recruiting, Active, Unknown}` → force `reason_for_failure = ""` regardless of verifier opinions
- `peptide = False` → force `classification = "Other"`
- `outcome ∈ {Terminated, Withdrawn, Failed}` + `reason_for_failure = ""` → flag for review

This alone would resolve 12 of 20 failure reason review items.

### 9.2 Verifier Prompt Parity for Outcome Heuristics (Priority: CRITICAL)

The primary outcome agent has completion heuristics (H1-H5) that verifiers lack. Add the same heuristics to the verifier outcome prompt:
- H1: Phase I completion = Positive
- H2/H4: Results posted = lean Positive
- H3: Long-completed trials that led to later phases = Positive
- H5: Default Unknown only after exhausting H1-H4

This would resolve 3 of 8 outcome review items.

### 9.3 Outcome H1 Heuristic Calibration (Priority: HIGH)

The H1 heuristic (Phase I completion = Positive) is too aggressive. It should NOT apply when:
- Evidence quality is below threshold (fewer than `min_sources` citations)
- No publications of any kind were found for the trial
- The trial is early Phase I with no results posted

Add a confidence tier: H1 with supporting evidence → "Positive" at high confidence. H1 with zero publications → "Positive" at LOW confidence (flag for review instead of forcing Positive).

### 9.4 Multi-Intervention Peptide Evaluation (Priority: HIGH)

When a trial has multiple interventions, the peptide agent should evaluate ALL of them, not just the first one ChEMBL returns data for. Modify Pass 1 to iterate over all interventions and produce a fact extraction for each. Pass 2 then answers True if ANY intervention is a peptide.

### 9.5 Failure Reason Value Normalization (Priority: MEDIUM)

The pre-check skip path returns bare `""` but other paths return `"EMPTY"` or `"INEFFECTIVE_FOR_PURPOSE"`. Normalize all outputs through `_parse_value()` — including the pre-check skip and the `_infer_from_pass1()` fallback. Add `"INEFFECIVE_FOR_PURPOSE"` (typo) to the fuzzy matching list.

### 9.6 Fix Broken Research Agents (Priority: MEDIUM)

Six research agents produce 0 citations across all 70 trials. Investigate and fix:
- **APD**: Requires JavaScript — may need headless browser or alternative endpoint
- **dbAMP**: Intermittent availability — add retry logic and health check
- **EBI Proteins**: Likely URL/params issue similar to the DBAASP fix
- **RCSB PDB**: May need different search strategy (structure search vs text search)
- **PDBe**: Same as RCSB PDB
- **Web Context (DuckDuckGo)**: Rate limiting or API changes

---

## 10. Next Steps

1. **Implement v7 improvements** (Sections 9.1-9.5) and re-run the same 70 trials to validate.
2. **Fix broken research agents** (Section 9.6) to bring all 15 agents online.
3. **Run Kimi K2 concordance** on the same 70 trials using the server profile.
4. **Expand to full 614-trial evaluation** once v7 shows improvement on the 70-trial set.
5. **Implement automated multi-run consensus** (Section 11) as a built-in feature.

---

## 11. Improvement Plan (Original)

---

## 9. Improvement Plan (Original)

### Phase A: Output Validation & Cross-Field Consistency

**Priority: CRITICAL — prevents contradictory/invalid results immediately**

1. **Hard validation in `_parse_value()`**: If parsed value is not in VALID_VALUES, return `None` → orchestrator treats as "requires manual review". Never guess.

2. **Cross-field consistency in orchestrator** (`_check_consistency()`):
   - peptide=False → force classification to "Other"
   - outcome in {Positive, Recruiting, Active, Unknown} → force reason_for_failure to ""
   - outcome in {Terminated, Withdrawn, Failed} + reason_for_failure="" → flag for review

3. **Verifier value normalization** before consensus check:
   - "Intravenous" → "IV"
   - "Active" → "Active, not recruiting"
   - "AMP" alone → flag as ambiguous

### Phase B: Few-Shot Prompt Engineering

**Priority: CRITICAL — addresses the core accuracy problem**

1. **Peptide agent**: Add 8 worked examples with expected answers. Small models follow examples far better than rules.

2. **Classification agent**: Rewrite as three-step decision tree:
   - Step 1: Is intervention a peptide? No → "Other"
   - Step 2: Is it an ANTIMICROBIAL peptide? No → "Other" (VIP, GLP-1, somatostatin = Not AMPs)
   - Step 3: Does the AMP target infection? Yes → AMP(infection), No → AMP(other)

3. **Delivery mode agent**: Add negative examples (what NOT to do). Add positive examples where FDA label specifies route.

4. **Verifier prompt parity**: Give verifiers the SAME detailed prompts + examples as the primary annotator. Currently verifiers get condensed instructions, causing asymmetric accuracy.

### Phase C: Recency-Aware Literature Search

**Priority: HIGH — key advantage over humans**

1. Sort PubMed/PMC results by date descending in the literature agent.
2. Add recency rule to outcome/failure Pass 2 prompts: "newest publication wins."
3. Add publication year to evidence output so reviewers can see data freshness.
4. Web context agent: search for regulatory decisions and press releases.

### Phase D: Peptide Cascade Protection

**Priority: MEDIUM**

1. If peptide flips during verification, re-run classification with the corrected value.
2. Classification agent independently verifies questionable peptide results (intervention contains "nutritional", "formula", "shake").

### Phase E: Selective Model Upgrade

**Priority: LOW — requires more processing time**

Use the 14B reconciler model as primary annotator for peptide and classification (highest error rate fields). Keep 8B for delivery_mode, outcome, reason_for_failure.

---

## 12. Accuracy Targets (Updated 2026-03-17)

| Field | Human R1-R2 Agreement | v3 Agent vs R1 (n=62) | v6 Agent vs R1 (n=70) | Target |
|---|---|---|---|---|
| Classification | 91.6% | 29.4% | 75.8% | >85% |
| Delivery Mode | 68.2% | 47.6% | 50.0% | >70% |
| Outcome | 55.6% | 37.1% | **72.7%** | >75% |
| Reason for Failure | 91.3% | 41.9% | 55.6% | >70% |
| Peptide | 48.4% | 66.7% | 77.1% | >85% |

**Outcome already exceeds human inter-rater agreement** (72.7% vs 55.6%). The agent's literature search + completion heuristics resolve the temporal drift that plagued human annotations. Classification (75.8%) is approaching the R1-R2 agreement ceiling (91.6%). Peptide (77.1%) far exceeds human agreement (48.4%) and is approaching the target. Delivery mode and failure reason remain below targets and are the priority for v7 improvements.

---

## 11. Multi-Run Consensus (Agent Ensemble)

**Priority: HIGH — directly reduces annotation noise**

Running the same batch through the pipeline N times and taking majority vote per field. This is the agent equivalent of the human two-replicate design, but with N=3-5 replicates instead of 2.

### Why It Works

Human annotation review revealed that the biggest accuracy problems come from stochastic variation:
- LLM temperature (0.10) is low but not zero — different runs can produce different answers
- Borderline cases (is this peptide? is this AMP?) flip between runs
- The two-pass agents (outcome, failure reason) are especially sensitive because Pass 1 extraction varies

With N=3 runs, a field must be wrong in 2 out of 3 runs to produce an incorrect majority vote. This sharply reduces the error rate for borderline cases.

### Implementation

1. Submit the same NCT IDs as N separate jobs (or use a wrapper that runs N pipeline iterations)
2. Collect all N annotation outputs for each trial
3. For each field: majority vote across N runs → final answer
4. Record stability score: fraction of runs agreeing with majority
5. Fields with stability < 0.67 (no majority in 3 runs) → flag for manual review

### What Unstable Fields Reveal

Instability = the prompt allows the LLM to interpret the evidence differently on each run. Fixes:
- Add more few-shot examples covering the ambiguous case
- Tighten the decision criteria (e.g., stricter peptide definition)
- Upgrade to larger model for that field (14B reconciler as primary)

---

## 12. Lessons from Human Annotation Patterns

### Peptide Definition Ambiguity

R1 annotators marked 451 trials (24%) as Peptide=True. R2 annotators marked 56 (3%). This 8:1 ratio is the largest systematic divergence in the dataset. Analysis of the R1 annotations shows they included:
- Radiolabeled peptide conjugates (e.g., 177Lu-DOTATATE) — these use a peptide as a targeting vector but the therapeutic mechanism is radiation, not the peptide itself
- Peptide receptor agonists/antagonists where the "peptide" label is ambiguous
- Nutritional peptide formulas

**Agent implication:** The agent should use the strict R2-aligned definition: the active drug must be a synthetic or natural peptide chain (2-100 amino acid residues) used for its direct therapeutic effect. Radiolabeled conjugates where the peptide serves as a targeting vector should be classified based on the primary mechanism of action.

### Outcome Temporal Drift

R1 used "Recruiting" 222 times; R2 used it 0 times. The two replicates were annotated at different dates. Trials that were recruiting when R1 annotated them had changed status by the time R2 annotated. R2 annotators then checked published literature and found results, leading to "Positive" or "Unknown" instead.

**Agent implication:** The agent's live API queries already handle this. For evaluation, trials where the agent says "Positive" and humans said "Recruiting" are likely recency wins, not errors. These must be verified by checking the agent's cited publications.

### Delivery Mode Specificity

167 delivery mode disagreements on 579 overlap (29%). Common patterns:
- Capsule vs Tablet (R1 and R2 disagree on form factor)
- SC/ID vs Other/Unspecified (one annotator found the specific route, the other didn't)
- Nasal spray classified as "Intranasal" by one, "Topical - Spray" by the other

**Agent implication:** The agent should aggressively use FDA label data for route specification. If the FDA label says "SUBCUTANEOUS" and the trial protocol says only "injection", the FDA data should override. The current prompt rules already specify this, but the agent should also flag when it upgrades from "Other/Unspecified" to a specific route based on FDA evidence.

---

## 13. Measuring Improvement

Human annotations are the **development-time benchmark only**. They inform prompt tuning and error analysis but are never fed to the agents at runtime.

**Ground truth construction:**
- Classification: 568 R1=R2 agreed pairs → high-confidence ground truth
- Delivery Mode: 412 agreed pairs
- Outcome: 207 agreed pairs
- Reason for Failure: 42 agreed pairs
- Where R1 and R2 disagree, independently verify using the agent's cited sources

**Evaluation process:**
1. Run the agent on a diverse set of NCTs after each improvement phase.
2. Compare against ground truth (agreed pairs) and disputed pairs (where the agent resolves the dispute).
3. Track per-field: accuracy, stability (multi-run agreement), reconciliation rate, manual review rate.
4. For recency wins: document cases where the agent found newer publications than what humans used. These cases confirm the agent is correct, not the human benchmark.
5. Multi-run consensus: compare N-run majority vote accuracy against single-run accuracy.

**End state:** The agents operate fully autonomously — no human annotations in the loop. The human Excel is archived as a historical benchmark, not an ongoing dependency.
