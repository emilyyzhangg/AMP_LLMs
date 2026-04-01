# Agent Annotate — Continuation Plan

**Last updated:** 2026-04-01
**Current state:** v24 merged to main (9db9e33). Frontend renamed to Agreement. 5 jobs reviewed.

## v24 Changes

- **Classification:** Binary AMP/Other (was AMP(infection)/AMP(other)/Other)
- **Delivery mode:** 4 categories — Injection/Infusion, Oral, Topical, Other (was 18 granular sub-categories)
- **Peptide cascade:** ALL False cascades N/A (was deterministic-only)
- **Data source:** CSV `human_ground_truth_train_df.csv` (was Excel)
- **Agreement:** Order-agnostic sequence comparison, RfF blank+failure=Unknown, N/A treated as blank
- **API:** `/api/agreement/` (was `/api/concordance/`)

### v22-era Job Performance (old code, mapped to v24 categories)

All jobs ran on v22 code (old categories). Results mapped through v24 aliases for comparison against training CSV.

**Human baseline (R1 vs R2, training CSV, 682 NCTs):**
| Field | n | Agreement | AC₁ |
|---|---|---|---|
| Classification | 454 | 93.2% | 0.919 |
| Delivery Mode | 488 | 88.3% | 0.864 |
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

### Updated Testing Plan

**Phase 1: Fix critical bugs before v24 baseline run**
1. **[P0] Delivery mode dedup bug**: In `_parse_value()`, after mapping multi-route comma-separated values to 4 categories, deduplicate. "injection/infusion, injection/infusion" → "injection/infusion". This is 7/27 (26%) of delivery disagreements and is a pure code bug.
2. **[P0] DRVYIHP over-matching**: Tighten `_KNOWN_SEQUENCES` matching in sequence.py. Currently matches if drug name substring appears anywhere in intervention name. Change to require the intervention IS the drug (e.g., "Angiotensin II" matches, but "Angiotensin-Converting Enzyme Inhibitor" does not).

**Phase 2: Run v24 baseline concordance (after P0 fixes)**
3. Submit the concordance v22 NCTs (50 NCTs) on dev (port 9005) with v24+fixes code
4. Compare results against human R1 using the training CSV
5. Expected improvements: classification ≥94% (was 94.3%), delivery ≥85% (was 88.6% minus dedup bugs), sequence metrics now use order-agnostic comparison

**Phase 3: Address peptide under-calling (high priority)**
6. Review the 17 FALSE→TRUE NCTs from the disagreement list
7. Add consistently misclassified drugs to `_KNOWN_PEPTIDE_DRUGS`
8. Consider: should the cascade require confidence > 0.8? Or is the full cascade correct and we just need better peptide accuracy?

**Phase 4: Sequence coverage expansion**
9. Review the 27 agent-empty sequence cases — which drugs are they?
10. Add verified sequences to `_KNOWN_SEQUENCES` for high-frequency misses
11. Improve LLM fallback prompts for literature-based sequence extraction

**Phase 5: Absorb + expand**
12. Absorb Batches G+H into EDAM (edam_learning_cycle)
13. Queue Batches I/J (positions 201-250)

## Environment State

| Environment | Branch | Version | Active Job |
|---|---|---|---|
| Prod (port 8005) | main | v17 (66907432) | None (4b062214adf0 complete) |
| Dev (port 9005) | dev | v18 (fc6fddac) | None |

## Important Notes

- **Workflow:** Develop on `dev`, run jobs on prod. Only merge to `main` when explicitly told.
- **CRITICAL:** Always commit+push atomically in ONE bash command. Autoupdater wipes uncommitted changes every 30s.
- **Update plans after every job** — this file and `LEARNING_RUN_PLAN.md`.
- **Drug lists are FROZEN** — no more additions. Improvements through reasoning (Layers 1-3) only.
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
