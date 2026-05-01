# Agent Annotate — Improvement Strategy

Strategy to surpass human annotation accuracy by fixing agent errors, exploiting the agent's structural advantages, and addressing the gaps revealed by a quality audit of both agent output and human annotations.

> **Last updated:** 2026-05-01 — v42.7.23 shipped + Job #101 production gate in flight. Canonical sources for v26+ are LEARNING_RUN_PLAN, CONTINUATION_PLAN, AGENT_STRATEGY_ROADMAP (see §17 below)

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
| NCT03998592 | Classification | AMP | AMP (both) | S. pyogenes vaccine = infection target |
| NCT03989817 | Classification | AMP | Other (both) | VIP is NOT an AMP |
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

Note: Seven more agents were added in v5 (see Section 7.5). Three were later removed in v8 (dbAMP — server unreachable; IntAct — noise; CARD — irrelevant). Semantic Scholar was also removed from the literature agent (rate limiting). Active total: 12 agents querying 17+ free databases.

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

Expanded the research pipeline from 8 to 15 parallel agents. Three were subsequently removed in v8 (see Section 7.8). Seven agents added in v5:

- **APD Agent** (aps.unmc.edu): AMP database, HTML scraping, best-effort (server requires JS). Provides independent AMP classification source.
- **dbAMP Agent** (yylab.jnu.edu.cn/dbAMP): 33K+ AMPs, HTML scraping, intermittent availability. Broad AMP reference complementing APD and DRAMP.
- **WHO ICTRP Agent** (trialsearch.who.int): International trial registry, HTML parsing. Extends ClinicalTrials.gov coverage to 17+ national/regional registries.
- **IUPHAR Guide to Pharmacology Agent** (guidetopharmacology.org): REST API, mechanism of action, drug targets, ligand classification. Authoritative pharmacological context for classification decisions.
- **IntAct Agent** (ebi.ac.uk/intact): REST API, molecular interactions, UniProt cross-references. Reveals AMP mechanisms through interaction partner analysis.
- **CARD Agent** (card.mcmaster.ca): AJAX endpoints, antibiotic resistance mechanisms, ARO terms. Provides resistance context for AMP clinical trials.
- **PDBe Agent** (ebi.ac.uk/pdbe): Solr search + REST API, structure quality metrics (resolution, R-factor). Complements RCSB PDB with quality assessment data.

SerpAPI was removed (paid service). All agents use free APIs exclusively.

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

### 9.6 Fix Broken Research Agents (DONE — v7/v8)

| Agent | v7 Status | v8 Status | Action Taken |
|---|---|---|---|
| APD | 0/10 | **10/10** | SSL verify disabled (cert chain broken) |
| Web Context | 0/10 | **10/10** | Switched from DuckDuckGo Instant Answer to HTML lite search |
| EBI Proteins | 0/10 | **3/10** | Intervention name extraction fixed. Intermittent 500s from ebi.ac.uk |
| PDBe | 0/10 | **4/10** | Intervention name extraction fixed |
| RCSB PDB | 0/10 | **Working** | v2 API format fixed ("paginate" not "pager") |
| dbAMP | 0/10 | **REMOVED** | Server permanently unreachable |
| IntAct | 1/10 | **REMOVED** | Low hit rate, generic protein noise |
| CARD | 0/10 | **REMOVED** | 0% relevance to dataset |
| Semantic Scholar | Rate limited | **REMOVED** | 429 on every batch from literature agent |

### 9.7 Structured Evidence Presentation (DONE — v8)

All annotation agents and blind verifiers now receive evidence organized into labeled sections rather than a flat weight-sorted dump:

**Sections:** TRIAL METADATA → PUBLISHED RESULTS → DRUG/PEPTIDE DATA → ANTIMICROBIAL DATA → STRUCTURAL DATA → WEB SOURCES

**Filters applied before evidence reaches LLM:**
1. Noise filter: negative search results, empty snippets (<15 chars), JSON artifacts
2. Relevance filter: database results must mention at least one actual trial intervention name
3. Deduplication: identical first 60 chars of snippet skipped
4. Snippet capping: 250 chars (mac_mini) or 500 chars (server)
5. Source-level filters: ChEMBL and IUPHAR name-match prevents fuzzy search false positives

**Impact:** NCT01697527 (92 raw citations) → 20 used on mac_mini (78% noise removal, ~873 tokens) vs 30 on server (~1500 tokens).

### 9.8 Remaining Issues (Priority: LOW)

- **APD negative confirmations**: APD returns "no exact match" for most searches — a negative result that wastes a citation slot. Consider filtering at source.
- **DuckDuckGo 202 responses**: Rate limiting causes 0 citations on some trials. Add a 1-second inter-trial delay for the web_context agent.
- **Literature 0 results for old trials**: NCT00000391, NCT00598312 return 0 PubMed/PMC results despite being completed trials. May need broader search terms (intervention name + condition) in addition to NCT ID.
- **ChEMBL wasted API calls**: Fuzzy text search returns irrelevant molecules that get filtered downstream. Moving the name-match filter before the API call would save HTTP requests.

---

## 10. Next Steps

1. **Re-run the same 70 trials with v8 agents** to validate structured evidence + agent cleanup impact on concordance.
2. **Run Kimi K2 concordance** on the same 70 trials using the server profile.
3. **Expand to full 614-trial evaluation** once v8 concordance is validated.
4. **Implement automated multi-run consensus** (Section 13) as a built-in feature.

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
   - "AMP" alone → valid (binary classification: AMP or Other)

### Phase B: Few-Shot Prompt Engineering

**Priority: CRITICAL — addresses the core accuracy problem**

1. **Peptide agent**: Add 8 worked examples with expected answers. Small models follow examples far better than rules.

2. **Classification agent**: Rewrite as two-step decision tree:
   - Step 1: Is intervention a peptide? No → "Other"
   - Step 2: Is it an ANTIMICROBIAL peptide? Yes → "AMP", No → "Other" (VIP, GLP-1, somatostatin = Not AMPs)

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

### 14.8 v9.1 Optimization Pass

Additional optimizations identified during architecture review:

1. **Failure reason skip_verification** — Pre-check gate returns now set `skip_verification=True`, saving 3 verifier calls (~45s) per non-failure trial. Combined with deterministic outcome, this cascades: deterministic outcome "Recruiting" → failure_reason pre-check skip → both fields skip verification entirely.

2. **Withdrawn skip** — Added to failure_reason pre-check. Saves 2 LLM passes + 3 verifier calls for withdrawn trials.

3. **Reconciler normalization** — Prevents reconciler from producing non-canonical values (e.g., "Intravenous" instead of "IV") that bypass consensus normalization.

4. **Server profile parity** — All 5 annotation agents now use 14B on server profile. Previously 3 agents used 8B regardless of hardware.

5. **Cascade shortcut** — Deterministic classifications skip the peptide cascade entirely, saving a classification re-run + 3 verifier calls when peptide gets flipped.

6. **Dead code cleanup** — Removed ~80 lines of unused Semantic Scholar code from literature agent.

### 14.9 Concordance v3 Methodology Fix

Architecture review identified that the concordance methodology was producing misleading baselines:

| Issue | Impact | Fix |
|---|---|---|
| Only both-filled trials counted | 50-65% of data invisible | Three-tier reporting |
| Peptide R1=R2 based on 193/1843 trials | 10% sample, selection bias | Coverage-adjusted tier |
| Failure reason 91.3% from blank-blank | Only 46 real comparisons | Outcome-aware blank handling |
| One-sided blanks invisible | 473 R1-only peptide annotations ignored | Tier 2 counts as disagreement |
| Agent evaluated on biased subset | Easier trials over-represented | Coverage reporting added |

### 15.4 Concordance Statistical Upgrades

Added to address publication-readiness gaps identified in methodology review:

1. **95% confidence intervals** on all Cohen's kappa values (Fleiss et al. 1969 analytical formula)
2. **Gwet's AC₁** alongside kappa (Gwet 2008) — robust to prevalence paradox
3. **Prevalence and bias indices** (Byrt et al. 1993) — quantify marginal skew and systematic rater disagreement
4. **Per-annotator pairwise analysis** — agent vs each individual R1/R2 annotator using workload row assignments
5. **Delivery mode normalization** — added SC, IM, subcutaneous, intramuscular, intradermal aliases
6. **Service v3 fix** — one-sided blank outcome+reason no longer skips the trial entirely; treats blank side as "" and includes for comparison
7. **R1/R2 composition documented** — R1 is a 7-annotator composite, R2 is primarily a single annotator, with workload row assignments for disaggregation

---

## 15. v10: Verification Architecture Overhaul

### 15.1 Problem

Analysis of job d2761eeb8102 (10 trials) and comparison across 6 prior jobs revealed systematic verification weaknesses:

1. **Verifiers weaker than primary annotator.** Classification uses qwen2.5:14b because 8B models can't follow the decision tree, but verification used gemma2:9b, qwen2:latest (~7B), and mistral:latest (~7B). Weak verifiers produce low-quality disagreements.
2. **Identical prompts.** All 3 verifiers saw the same prompt — zero cognitive diversity. If the prompt biases toward one answer, all three are biased identically.
3. **Evidence starvation.** Verifiers had a hardcoded 25-citation cap while primary annotators got 30-50. False disagreements from missing evidence.
4. **Hardcoded 0.7 confidence.** No signal about actual verifier certainty. The high-confidence primary override compared real primary confidence against an arbitrary constant.
5. **Outcome instability.** NCT00004984 outcome flip-flopped across 6 jobs because low-confidence verifiers overrode high-confidence primaries.

### 15.2 Fixes Implemented

**A. Mac Mini verifier upgrades:**
- gemma2:9b (kept), qwen2:latest → qwen2.5:7b, mistral:latest → phi4-mini:3.8b

**B. Server verifier config:**
- Configurable `server_verifiers` list: gemma2:27b, qwen2.5:32b, phi4:14b

**C. Verification personas (3 cognitive lenses):**
- Verifier 1 (Conservative): defaults to safest answer when evidence is ambiguous
- Verifier 2 (Evidence-strict): only answers based on directly citable facts
- Verifier 3 (Adversarial): challenges the most obvious interpretation

**D. Evidence budget parity:**
- Verifier citation cap raised from 25 to match primary (30 Mac Mini, 50 server)

**E. Dynamic verifier confidence:**
- Self-assessed High/Medium/Low → 0.9/0.7/0.4 (replaces hardcoded 0.7)

**F. High-confidence primary override:**
- Primary confidence > 0.85 AND all dissenting verifiers at baseline (≤ 0.7) → accept primary without reconciliation

**G. Server premium model toggle:**
- `server_premium_model` config: kimi-k2-thinking (default) or minimax-m2.7
- Used for classification, outcome, and reconciliation on server hardware

**H. Auto-pull missing models:**
- `ensure_model()` checks Ollama model list and pulls from registry on first use

**I. SerpAPI fully removed:**
- Removed SERPAPI_KEY from config, rate limits from http_utils. Agent Annotate uses zero paid APIs.

**J. Research coverage enhanced:**
- Per-agent coverage now includes error status and source_names list

**K. Deterministic confidence preserved:**
- Evidence threshold check no longer caps confidence on deterministic results (skip_verification=True)

### 15.3 EDAM Self-Learning System

The v10 changes are complemented by EDAM (Experience-Driven Annotation Memory), a persistent self-learning layer that automatically improves accuracy across runs.

**Learning signals used:**
- Cross-run stability (consensus across independent runs = autonomous ground truth)
- Human review decisions (highest weight, slowest decay)
- Self-review corrections (premium model re-evaluates flagged items with evidence requirement)
- Prompt optimization (A/B tested modifications targeting measured error patterns)

**Key design decisions:**
- Corrections require cited evidence — prevents ungrounded self-reinforcement
- Version-gated decay — config changes don't destroy old knowledge, just demote it
- Verifiers never see corrections — preserving blind verification integrity
- Hard database limits with prioritized purging — prevents unbounded memory growth
- All failures are non-fatal — EDAM never blocks the annotation pipeline

See METHODOLOGY.md Section 16 for full technical details.

---

## 16. v25 Fixes (2026-04-01)

Issues from concordance analysis (CONTINUATION_PLAN.md) resolved in v25:

| Issue | Status | Fix |
|---|---|---|
| Delivery mode duplicate output ("Injection/Infusion, Injection/Infusion") | **Fixed in v25** | `_parse_value()` now deduplicates after mapping multi-route values to 4 categories. Was 26% of delivery mode disagreements. |
| Sequence DRVYIHP over-matching (angiotensin matching ACE inhibitor trials) | **Fixed in v25** | Short drug names (<=4 chars) require exact match in `_KNOWN_SEQUENCES`; longer names use word-boundary regex. |
| Outcome Unknown defaults for trials with published results | **Addressed in v25** | Post-LLM `_publication_priority_override()` checks for published results when LLM returns Unknown/Active/Terminated. Evidence priority ladder: publications > CT.gov results > status > phase. |
| Peptide false negatives (agent=False, human=True) | **Partially addressed in v25** | 15 new peptide drugs added to `_KNOWN_PEPTIDE_DRUGS` (peptide vaccines, novel therapeutics from error analysis). 9 new verified sequences added to `_KNOWN_SEQUENCES`. Remaining false negatives require LLM reasoning improvements. |

---

## 17. v25 → v42.7.23 (2026-04-01 → 2026-05-01) — Atomic Era + v42.7 Cycle + Production Gate

After v25, the project went through a substantial overhaul. This file is no longer the canonical source for v26+ work — see:
- `LEARNING_RUN_PLAN.md` — full job registry through Job #99
- `CONTINUATION_PLAN.md` — current state + production goals + held-out evaluation policy
- `docs/AGENT_STRATEGY_ROADMAP.md` — design rules + decision log + future targets
- `docs/ATOMIC_EVIDENCE_DECOMPOSITION.md` — v42 atomic-decomposition design

### Headlines from the v42.7 cycle (≈2 weeks of work, 22 sub-versions)

**Research pipeline expansion:** 3 new free agents (SEC EDGAR sponsor disclosures, openFDA Drugs@FDA approvals, NIH RePORTER federal grants). 19 research agents total. v42.7.10 fixed a CRITICAL silent regression where the orchestrator was dropping the intervention `type` field, causing all 3 new agents to receive empty interventions for 2 days post-deployment.

**Outcome agent overrides (over-call control):** v42.7.7 vaccine-immunogenicity Positive override; v42.7.8 wired FDA-approved drug + SEC EDGAR signals into the dossier; v42.7.12 added FDA label indications + CT.gov registered-pubs gate to prevent off-label over-calls; v42.7.14 status-gated Failed override; v42.7.15 tightened _NEGATIVE_KW.

**Outcome agent overrides (under-call recovery):** v42.7.13 fixed an LLM hallucination by surfacing "Registered Trial Publications: 0" explicitly. v42.7.17 fixed v42.7.13's over-correction by allowing pub-title-pattern as alternative trial-specificity (drug name + phase descriptor in title; field reviews still excluded).

**Scoring/normalization:** v42.7.16 made the sequence canonicalizer strip terminal -OH / -NH2 chemistry suffixes (a scoring-side fix; agent output unchanged). compare_jobs / commit_accuracy_report use sequences_match for set-containment.

**Diagnostics:** v42.7.5 captures BOOT_COMMIT_FULL at module load + new `/api/diagnostics/code_sync` endpoint, closing the memory-vs-disk smoke-pitfall that bit us 3 times in v42.6/v42.7. v42.7.1 introduced a 5-tier `evidence_grade` (db_confirmed > deterministic > pub_trial_specific > llm > inconclusive); v42.7.2's `commit_accuracy_report.py` reports coverage × commit_accuracy stratified by grade.

**Discipline established:** per-cycle held-out separation. Held-out-A (30 NCTs, seed 4242) used as Jobs #92+#95 then retired. Held-out-B (25 NCTs, seed 5252) used as Job #96 (which surfaced v42.7.13's over-correction) then retired. Held-out-C (25 NCTs, seed 6262) used as Job #97 then retired. Held-out-D (20 NCTs, seed 7373) is now active for Job #98.

**v42.7.18 (sequence-dict expansion):** 5 entries to `_KNOWN_SEQUENCES` (solnatide/ap301/tip-peptide; io103; apraglutide backbone). Sourced from Job #97's 8/10 sequence-N/A misses on peptide=True trials.

**v42.7.19 (delivery_mode ambiguous-keyword relevance gate):** Cross-job analysis (Jobs #92/#95/#96/#97) surfaced 6 distinct NCTs where ambiguous keywords (tablet/capsule) matched on FDA Drugs / OpenAlex / placebo-comparator citations not describing the experimental arm — added `citation_mentions_experimental` flag.

**v42.7.20 (`_classify_publication` default → `general`):** Cross-job analysis showed `positive → unknown` was the dominant outcome miss class (9-12 misses per slice). Empirical: re-classifying Job #98 pubs under the new rule shows trial_specific count drops 6-48 → 0-5 per trial. Over-tagging was systematically confusing the LLM. v42.7.20 requires an explicit trial signal for `trial_specific` tagging.

**v42.7.21 (sequences: CBX129801 + SARTATE):** From Job #98 misses. CBX129801 = Long-Acting C-Peptide → 31aa proinsulin C-peptide; SARTATE = octreotate analog → fCYwKTCT (D-Phe1, D-Trp4 lowercase preserved).

**v42.7.22 (CGRP / calcitonin disambiguation):** NCT03481400 emitted wrong sequence (32aa calcitonin instead of 37aa alpha-CGRP) because the longer "calcitonin gene-related peptide" key was missing. Same v42.6.18 root cause (longest-first iteration was already in place; missing key).

**v42.7.23 (radiotracer rule split by isotope class):** v31's `_RADIOTRACER_PATTERNS` rule emitted "Other" for all radiotracers as a diagnostic-not-therapeutic distinction, but the 147-NCT milestone surfaced 5 NCTs (NCT03069989, NCT03164486, NCT05940298, NCT05968846, NCT06443762) where humans annotated injected radiotracers as Injection/Infusion. v42.7.23 splits patterns into PET (positron-emitting), SPECT (gamma-emitting), and Therapeutic (90Y, 177Lu, 131I, 225Ac, 211At). PET/SPECT → always Injection/Infusion (no oral PET tracer exists by physics). Therapeutic → defer to explicit injection signal in name/desc, fall back to v31 'Other' (preserves [131I] oral capsule case). First v42.7.23.a attempt (OpenFDA multi-formulation gate) was rejected after 0/5 smoke targeted wrong code path; redesign passed prod smoke 5/5.

**Production gate (Job #101, in flight):** 239-NCT FINAL accuracy certification on v42.7.23 main commit `2172018e`. Slice from training_csv − test_batch with full GT category coverage (positive 120 / unknown 77 / terminated 30 / failed 13 / withdrawn 10). 95% CI half-width ±6.3pp at p=0.5. ETA ~24h remaining as of 2026-05-01. Decision rule: ship if all fields meet target; accept-with-CI-bound if outcome 55-65% (GT-quality ceiling per cross-job analysis); investigate if surprise regression.

**Tooling:** `scripts/cross_job_miss_patterns.py` (per-job pattern tally + cross-job NCT recurrence); `scripts/evidence_grade_miss_analysis.py` (group misses by evidence_grade + show LLM reasoning); `scripts/pick_milestone_validation_100.py` + `scripts/milestone_validation_v42_7_22.json` (147-NCT validation tier with ±8pp CI half-width); held-out-E + held-out-F preemptively built.

### Validation summary (47-NCT clean slice)

| Job | Code | outcome | classification | sequence | Notes |
|---|---|---|---|---|---|
| #83 | v42.6.15 | 61.7% | 90.7% | 35.3% | Baseline |
| #88 | v42.7.3 | 59.6% | 90.7% | — | RfF +7.6pp; outcome -2.1pp (within noise) |
| #89 | v42.7.4 | 61.7% | 90.7% | — | Recovered |
| #90 | v42.7.4 stability | 61.7% | 90.7% | — | Same code; 4 outcome flips → 8.5% noise floor |

### Validation summary (held-out slices)

| Job | Slice | Code | outcome | Notes |
|---|---|---|---|---|
| #92 | A (30) | v42.7.11 | 60.0% | 4 over-call class |
| #95 | A (30) | v42.7.13 | 60.0% | Over-calls fixed; noise re-distributed |
| #96 | B (25) | v42.7.16 | 36.0% | Revealed v42.7.13 over-correction |
| #97 | C (25) | v42.7.17 | 68.0% | First post-fix measurement; v42.7 outcome cycle design-complete |
| #98 | D (20) | v42.7.18 | 35.0% | Slice-specific positive recall variance vs #97; peptide 94.4% / classification 100% — no regressions |
| #99 | E (20) | v42.7.22 | 55.0% | PASS — outcome ≥55% threshold met; v42.7.20 enabled 2 unknown→positive flips on clean pub evidence |
| #100 | milestone (147) | v42.7.22 | 57.8% | DECISION: continue iteration (gray zone) — peptide 89.0% / classification 97.1% production-ready, delivery 84.9% (-6.7pp regression), RfF 54.5% (small-N variance), sequence 39.0% |
| #101 | production-gate (239) | v42.7.23 | running | FINAL accuracy certification with full GT category coverage; cron `cb95c3f1` filling `docs/PRODUCTION_GATE_REPORT_TEMPLATE.md` on completion |

### What's next (post-Job #101)

**Production goals defined in CONTINUATION_PLAN:** beat human inter-rater agreement by ≥5pp on each field, validated on a 100+ NCT slice with 95% CI half-width <10pp. Per-field targets calibrated to inter-rater data: outcome ≥65% (vs 55.6%), peptide ≥85% (vs 48.4%), delivery ≥80% (vs 68.2%), classification ≥95% (vs 91.6%), RfF ≥95% (vs 91.3%), sequence ≥50%.

**Validation tiers (empirical):**
- 20-25 NCT iteration cycles (regression detection, ±22pp CI), ~3-4h
- 147-NCT milestone validation (accuracy certification, ±8pp CI), ~24h overnight
- 239-NCT production gate (final certification, ±6.3pp CI), ~42h overnight (Job #101)
- 630-NCT full-corpus annotation (publication output, no validation), ~52-70h per batch × 2 batches = 4-7 days total

**Path to "annotate everything":**
1. Job #101 production gate signs off (current step, ETA tomorrow)
2. Submit `--full-corpus-1` and `--full-corpus-2` (2 batches × 315 NCTs)
3. Merge with `scripts/merge_full_corpus_results.py JOB_1 JOB_2` → canonical JSON+CSV
4. Publish per-field accuracy + per-NCT annotations using methodology in `docs/PRODUCTION_GATE_REPORT_TEMPLATE.md` §6

**v42.8 architectural candidates (post-shipping, not blocking):**
- Drug-code → biological-name resolver (RxNorm / DrugBank API) addresses both outcome's GT-quality ceiling and sequence's drug-code under-extraction
- Sponsor press-release / conference abstract search agent — captures positive-result reporting outside peer-reviewed literature

**Path to production**: 1) outcome stabilization (current bottleneck — Job #99 = first signal post-v42.7.20); 2) sequence under-extraction (continue dict expansion + research-side widening — see v42.8 candidate #6); 3) delivery + RfF certification on milestone slice; 4) 250-NCT production gate.

**v42.7.23 candidate backlog** (in CONTINUATION_PLAN):
1. Outcome positive recall — DEFER, Rule 7 area is over-correction risk
2. Delivery_mode multi-route over-collection — SHIPPED as v42.7.19
3. Further sequence dict expansion — pending Job #99 misses
4. Vaccine-without-explicit-route default — defer, cross-slice confirmation
5. Topical-detection under-call — defer, narrow class
6. Drug-code → UniProt resolution gap (v42.8 architectural) — defer

**Data discipline**: only NCTs from the 680-NCT training CSV (`docs/human_ground_truth_train_df.csv`) for any cycle. Pool budget: ~290 GT-scoreable for outcome, 287 used so far, 58 residual.
