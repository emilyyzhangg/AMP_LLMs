# Agent Annotate — Continuation Plan

**Last updated:** 2026-04-02
**Current state:** v27 on dev (pending push). v26 on prod (e04e458). Job 86fdce46b3c5 completed (50 NCTs). v26 concordance via API: classification 94.3%, delivery 97.1%, outcome 80.0%, peptide 92.3% (n=39, grouped categories).

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
- **UniProt snippet fix (data pipeline)**: peptide_identity.py and ebi_proteins_client.py now report mature chain lengths from CHAIN/PEPTIDE features instead of just precursor length. For insulin, snippet now says "Precursor length: 110 aa. Mature form: Insulin B chain 30 aa, Insulin A chain 21 aa (51 aa total)" instead of just "Length: 110 aa". This is the actual root cause — verifiers and reconciler were reasoning correctly from wrong data.

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

**Phase 2b: Run concordance on v26 job 86fdce46b3c5 (NEXT)**
- v26 has TERMINATED outcome override + RfF empty default fixes
- Same 50 NCTs — direct comparison to v25 concordance
- Expected: outcome improvement (TERMINATED trials no longer stuck on Unknown), RfF cascade improvement

**Phase 3: Address peptide under-calling (v27 prompt fix applied)**
- 3 FALSE→TRUE disagreements in v26: NCT00004984 (insulin), NCT02660736 (albiglutide), NCT03165435 (CV-MG01)
- v27: Updated LLM prompts to accept multi-chain peptide hormones (insulin). No drug list additions.
- Albiglutide: LLM says TRUE but verifiers flip — monitor after v27 prompt changes
- CV-MG01: peptide-conjugate, may still be FALSE via LLM — monitor

**Phase 4: Sequence coverage expansion (highest impact)**
- Review the 12-16 agent-empty sequence cases — which drugs are they?
- Add verified sequences to `_KNOWN_SEQUENCES` for high-frequency misses
- Improve LLM fallback prompts for literature-based sequence extraction
- Insulin decision: multi-chain proteins keep their sequence

**Phase 5: Absorb + expand**
- Absorb Batches G+H into EDAM (edam_learning_cycle)
- Queue Batches I/J (positions 201-250)

## Environment State

| Environment | Branch | Version | Active Job |
|---|---|---|---|
| Prod (port 8005) | main | v26 (e04e458) | None (86fdce46b3c5 complete) |
| Dev (port 9005) | dev | — | None |

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
