# Agent Annotate — Continuation Plan

**Last updated:** 2026-03-31
**Current state:** v22 (fc02b08) on main. v22 code fixes applied. 5 jobs queued and running unattended: concordance v22 (6657f8896238) + Batches G R1/R2 (55826cb5853a, 799905fee5c4) + Batches H R1/R2 (6ae5c0fb0de1, 4953bff0b240). Next action: when concordance completes, run concordance_jobs.py and check outcome ≥70%.

## Latest Concordance

### v21 (50 NCTs, job c2c43af95162) — 2026-03-31

| Field | v21 | v19 R1 | v18+ baseline | Target | Met? |
|---|---|---|---|---|---|
| Classification | **92.0% / AC₁=0.917** | 92.0% / AC₁=0.917 | 87.8% / 0.870 | Hold 92% | YES (held) |
| Delivery Mode | 63.3% / AC₁=0.609 | 65.3% / AC₁=0.632 | 67.3% / 0.654 | ≥65% | NO (-2pp regress) |
| Outcome | **68.0% / AC₁=0.633** | 72.0% / AC₁=0.680 | 70.0% / 0.657 | ≥76% | **NO (-4pp REGRESSION)** |
| Reason for Failure | 70.0% / AC₁=0.657 | 72.0% / AC₁=0.671 | 72.0% / 0.671 | ≥70% | YES (barely) |
| Peptide | 82.2% / AC₁=0.769 | 86.7% / AC₁=0.834 | 88.9% / 0.865 | ≥86% | NO (-4.5pp regress) |
| Sequence | 61.9% (21/21) / AC₁=0.603 | 65.0% / AC₁=0.634 | 59.1% / 0.574 | ≥30% | YES |

**Key findings:**
- **TERMINATED fix: net-neutral/negative.** 0 TERMINATED→Positive cases fixed (NCT00977145, NCT02654587 still wrong). 2 new overcorrection errors introduced (NCT00982696: Unknown→Failed; NCT03490942: Terminated→Failed). The evidence-based pipeline is too aggressively calling Failed for genuinely-Terminated trials when it finds any failure signal.
- **Outcome fell BELOW v18+ baseline** (68% vs 70%). v19's +2pp gain was erased. EDAM purge + rebuilt training removed signal without restoring enough.
- **16 Agent vs R1 outcome disagreements:** 5 persistent evidence gaps (NCT00002428, NCT00004984, NCT02660736, NCT02665377, NCT04672083), 2 TERMINATED-fix failures (NCT00977145, NCT02654587), 2 new overcorrections (NCT00982696, NCT03490942), 4 active-trial-status disagreements (R1/R2 themselves disagree), 1 genuine regression (NCT00972569, correctly Failed in v19, now Unknown in v21), 2 other.
- **RfF 70%: just made target** — but 3 cascade errors from outcome, multiple Business Reason vs other-category confusions.
- **Peptide regression -4.5pp:** 7 cases False→True misses. Under-calling True by end of test batch. Possibly EDAM Batches E/F training noise or cascade logic interaction.
- **Delivery mode -2pp:** Experimental-arm-only filter had zero effect. Errors are structural sub-category confusion (SC/IM/IV/Other) and missing multi-route (oral+injection combos).

**Decision: BELOW 70% threshold → examine failure cases in detail before more training.**

### v20 partial (15/50 NCTs, job e0f556c703c7) — 2026-03-30 (cancelled at 15/50)

| Field | v20 partial (15 NCTs) | v19 R1 baseline (50 NCTs) | Change |
|---|---|---|---|
| Classification | 100% | 92.0% / AC₁=0.917 | +8pp (small N) |
| Delivery Mode | 60.0% | 63.3% / 0.614 | -3pp |
| Outcome | 46.7% | 72.0% / 0.680 | **-25pp regression** |
| Reason for Failure | 66.7% | 68.0% / 0.625 | -1pp |
| Peptide | 100% | 80.0% / 0.734 | +20pp |

Key finding: Outcome regression confirmed at 15/50 NCTs. Root cause identified as `[Deterministic v11]` mapping `TERMINATED → "Terminated"` in `outcome.py`, bypassing LLM entirely. Fixed in v21 — but fix was not sufficient (see v21 results above).

### v19 (50 NCTs, 2 runs: c1786d005ade / ac6af4e49fe2) — 2026-03-27

| Field | v19 R1 | v19 R2 | v18+ baseline | Target | Met? |
|---|---|---|---|---|---|
| Classification | **92.0% / AC₁=0.917** | **92.0% / AC₁=0.917** | 87.8% / 0.870 | AC₁≥0.82 | YES (+4.2%) |
| Delivery Mode | 65.3% / 0.632 | 63.3% / 0.614 | 67.3% / 0.654 | ≥73% | NO (slight regress) |
| Outcome | 72.0% / 0.680 | 68.0% / 0.634 | 70.0% / 0.657 | ≥80% | NO (slight improve) |
| Reason for Failure | 72.0% / 0.671 | 68.0% / 0.625 | 72.0% / 0.671 | ≥84% | NO (same) |
| Peptide | 86.7% / 0.834 | 80.0% / 0.734 | 88.9% / 0.865 | ≥86% | Borderline / high variance |
| Sequence | 65.0% / 0.634 | 68.4% / 0.668 | 59.1% / 0.574 | ≥30% | YES (from code only) |

## v21 Changes (merged to main, commit 69e7d14)

**1. TERMINATED overcalling fix (CRITICAL)**
- `outcome.py`: removed `"TERMINATED"` from `_DETERMINISTIC_STATUSES`. Was blindly mapping all TERMINATED trials to outcome="Terminated" with `skip_verification=True`, bypassing LLM entirely.
- Root cause of -25pp outcome regression on v20 partial concordance.
- Trials stopped early for efficacy (positive published results, drug advanced to later phases) were annotated "Terminated" instead of "Positive".
- Fix: TERMINATED now falls through to the 2-pass LLM pipeline. PASS2_PROMPT item 4 checks evidence: Positive if positive results/drug advanced, Failed if safety/futility, Terminated if business reason or no signal.
- `verifier.py`: updated TERMINATED rule from "always Terminated" to evidence-based decision tree.

**2. Phase-based completion heuristics (HIGH)**
- `outcome.py` PASS2_PROMPT H1b: Phase I completed >5yr ago + no Phase II found + no publications → "Unknown" (drug likely didn't advance, but "Failed" requires positive evidence)
- `outcome.py` PASS2_PROMPT H3b: Phase II/III completed >10yr ago + no publications + no negative evidence → lean "Positive" (common for older industry-sponsored trials that didn't publish)
- `verifier.py`: H1b and H3b added to verifier instruction.

**3. Delivery mode: EXPERIMENTAL arm only (MEDIUM)**
- `delivery_mode.py` `_deterministic_delivery_mode()`: filter `intervention_names` to arms where `armGroups[type=EXPERIMENTAL]`. Falls back to all interventions if no arm type data available (older CT.gov records).
- PASS1_SYSTEM: explicit instruction to focus on EXPERIMENTAL arm route only, ignore placebo/comparator/background arms.
- PASS2_SYSTEM Rule 6: clarified multi-route applies to experimental drugs only.

**4. EDAM surgical purge (Option C)**
- Deleted ALL outcome + delivery_mode experiences (351 each) and corrections (10 outcome, 30 delivery_mode).
- Rationale: outcome experiences contaminated by biased TERMINATED→Terminated mappings from v20 code; delivery_mode experiences contaminated by comparator arm routes + 25+ contradictory corrections.
- Retained: classification (351 exp, 18 corr), peptide (351 exp, 52 corr), reason_for_failure (351 exp, 23 corr), sequence (351 exp, 0 corr).
- EDAM post-purge: 1,404 experiences / 93 corrections / 120 unique NCTs.
- New training (Batches E/F) on v21 code will rebuild outcome + delivery_mode from scratch with correct annotations.

## v22 Code Changes (Applied 2026-03-31)

**EDAM purge:** Deleted 1 bad outcome experience (NCT03232112, "Failed - completed trial" — TERMINATED trial, wrong annotation from v21 TERMINATED→Failed bug). All other experiences retained. Post-purge: 1,775 experiences / 123 corrections.

**Fix A — outcome.py PASS2_PROMPT item 4 (CRITICAL):** Removed "Failed - completed trial" from TERMINATED branch entirely. "Failed - completed trial" is EXCLUSIVELY for COMPLETED trials with published negative results. TERMINATED trials now only resolve to "Positive" (drug advanced/positive results) or "Terminated" (everything else). Also added explicit TERMINATED RULE to CRITICAL RULES block.

**Fix B — verifier.py (CRITICAL):** Same semantic fix — removed "Safety failure, futility → Failed - completed trial" bullet from TERMINATED verifier rule. Verifier now enforces: TERMINATED → only Positive or Terminated.

**Fix C — peptide.py _KNOWN_PEPTIDE_DRUGS (MEDIUM):** Added ISA101b, ISA101, MELITAC 12.1, MELITAC to known-peptide list. These multi-epitope peptide cancer vaccines were causing False→True misses in 7 concordance NCTs.

**Fix D — peptide.py PASS2_SYSTEM (MEDIUM):** Strengthened multi-drug False guard — "False is only valid if EVERY intervention is confirmed non-peptide. If even one drug is a peptide (even a co-administered peptide vaccine alongside a mAb), the answer is True."

**Fix E — delivery_mode.py PASS1 (LOW):** Added explicit multi-drug route instruction — if EXPERIMENTAL arm has multiple drugs, report route for each drug separately; do not merge or omit routes.

**Job queue (submitted 2026-03-31, v22 commit fc02b08):**
1. Concordance v22 — 6657f8896238 — 50 test NCTs (fast_learning_batch_50.txt) — gate: outcome ≥70%
2. Batch G R1 — 55826cb5853a — positions 151-175 (25 NCTs)
3. Batch G R2 — 799905fee5c4 — positions 151-175 (25 NCTs)
4. Batch H R1 — 6ae5c0fb0de1 — positions 176-200 (25 NCTs)
5. Batch H R2 — 4953bff0b240 — positions 176-200 (25 NCTs)

**Expected impact:** TERMINATED fix recovers NCT00982696 + NCT03490942 → +2 correct outcomes = +4pp → outcome ~72%. Peptide ISA101b/MELITAC fix recovers ~5pp → peptide ~87%.

---

## Strategic Plan: Post-v21 Analysis (2026-03-31)

**v21 concordance result: outcome=68% — BELOW 70% threshold. Do not proceed to Batches G/H.**

### Root cause priorities (in order of impact)

**Priority 1: TERMINATED overcorrection (2 new errors introduced by v21 fix)**
- NCT00982696: outcome=Unknown (R1), agent=Failed. Trial has TERMINATED status with complex history — agent found some failure signal and called Failed instead of Unknown.
- NCT03490942: outcome=Terminated (R1), agent=Failed. Business-reason termination, agent incorrectly called Failed.
- **Fix needed:** The LLM is too eager to call Failed after the deterministic bypass was removed. The evidence-check pipeline needs a higher evidence bar for Failed: require explicit adverse events or efficacy failure reports, not just absence of positive results. Terminated should remain the default when evidence is ambiguous.

**Priority 2: TERMINATED→Positive still not working (0 of 2 cases fixed)**
- NCT00977145: Positive (R1), agent=Terminated. Drug advanced but no published results accessible.
- NCT02654587: Positive (R1), agent=Terminated. Same pattern.
- **Fix needed:** The H3b heuristic (Phase II/III >10yr + no pubs + no negative evidence → lean Positive) may need to be applied more aggressively for TERMINATED trials. Or add Phase heuristic specifically for TERMINATED + drug-advanced evidence.

**Priority 3: Persistent evidence-gap failures (5 cases, unchanged across all versions)**
- NCT00002428, NCT00004984, NCT02660736, NCT02665377, NCT04672083: all require adverse event/efficacy publications not accessible through current sources.
- **No code fix possible.** Structural literature access gap. Accept as floor.

**Priority 4: Peptide regression (-4.5pp)**
- 7 cases of Agent=False where R1=True. Under-calling peptide.
- Investigate if EDAM Batches E/F trained on non-peptide cases that are suppressing True calls.
- Consider: peptide field EDAM contributions from training may be introducing False bias if training NCTs have more non-peptide drugs.

**Priority 5: RfF Business Reason vs other category confusion (5 cases)**
- NCT03018288, NCT03397966, NCT03490942, NCT03500484, NCT05813314: all confusion between Business Reason and other termination categories.
- R1/R2 also disagree on several — these may be at the human annotation reliability ceiling.

**Priority 6: NCT00972569 regression (correctly Failed in v19, now Unknown in v21)**
- Single case but troubling — suggests EDAM or prompt changes destabilized a previously correct answer.
- Check if EDAM experience for this NCT changed between v19 and v21.

### EDAM net-positive threshold assessment
- Outcome on test NCTs: 68% (BELOW the 70% threshold). EDAM Batches E/F did NOT help.
- The purge + rebuild strategy failed to reach baseline. Possible causes:
  1. 50 training NCTs (Batches E/F, positions 101-150) have lower literature density than test NCTs.
  2. EDAM rebuilt experiences for outcome include the TERMINATED overcorrection pattern.
  3. Training vs test gap (outcome 44-50% on training NCTs) means EDAM is learning from unreliable signal.
- **Decision: Do not run Batches G/H until outcome code is fixed.** Adding more training on broken code will make things worse.

### Next steps (code fixes before any more training)
1. **Fix TERMINATED overcorrection:** Tighten Failed evidence requirement — require explicit adverse event records or efficacy failure publications, not inference from absence of positive results.
2. **Fix TERMINATED→Positive:** Strengthen Phase heuristic for TERMINATED + Phase II/III trials where the drug appears to have advanced (infer from later trials, drug approvals, etc.).
3. **Investigate peptide regression:** Check which EDAM experiences are contributing False bias for NCT00977145, NCT03018288, NCT03165435, NCT03258008, NCT03597282 (all Agent=False, R1=True).
4. After code fixes → single re-concordance run (50 test NCTs). If outcome ≥70%: add to EDAM and proceed to Batches G/H.

**Training vs test gap:** Outcome 44-50% on training NCTs vs 68-72% on test NCTs. Test NCTs selected for literature richness. Do NOT use training-NCT concordance to evaluate model quality — always use test batch (fast_learning_batch_50.txt).

**Hardware constraint:** No parallel jobs. Mac Mini M4, 16GB. Submit jobs one at a time (API queues them).

## Current: v22 Queued (2026-03-31)

### v22 Jobs — Queued and Running
| Job | Batch | NCTs | Status |
|---|---|---|---|
| 6657f8896238 | Concordance v22 | 50 test NCTs | **Running / Queued** |
| 55826cb5853a | Batch G R1 | 25 (positions 151-175) | **Queued** |
| 799905fee5c4 | Batch G R2 | 25 (positions 151-175) | **Queued** |
| 6ae5c0fb0de1 | Batch H R1 | 25 (positions 176-200) | **Queued** |
| 4953bff0b240 | Batch H R2 | 25 (positions 176-200) | **Queued** |

### Status: All jobs queued — running unattended

### v21 Batch E/F Training — Complete (archived)
| Job | Batch | NCTs | Status |
|---|---|---|---|
| 83c6ad7fd4d7 | Batch E run 1 | 25 (positions 101-125) | **Complete** |
| 54acb4a8136d | Batch E run 2 | 25 (positions 101-125) | **Complete** |
| f78d3554f29f | Batch F run 1 | 25 (positions 126-150) | **Complete** |
| 92fce293f860 | Batch F run 2 | 25 (positions 126-150) | **Complete** |
| c2c43af95162 | Concordance v21 | 50 test NCTs | **Complete — 68% outcome (BELOW threshold)** |

### v20 Training (completed, EDAM outcome+delivery_mode purged)
| Job | Batch | NCTs | EDAM exp written | Notes |
|---|---|---|---|---|
| ba96acf75132 | Train-C run 1 | 50 | 300 | First clean training run |
| 29830f7d3785 | Train-C run 2 | 50 | 300 | |
| 798817a09db3 | Train-D run 1 | 50 | 300 | |
| 3fc6552eb54e | Train-D run 2 | 50 | 300 | |

All 1,200 outcome + delivery_mode experiences from these jobs were purged (see v21 EDAM purge above).

## Environment State

| Environment | Branch | Version | Active Job |
|---|---|---|---|
| Prod (port 8005) | main | v22 (fc02b08) | 6657f8896238 running (Concordance v22) |
| Dev (port 9005) | dev | v21 (6ce9aff) | None |

## Important Notes

- **Workflow:** Develop on `dev`, run jobs on prod. Only merge to `main` when explicitly told.
- **CRITICAL:** Always commit+push atomically in ONE bash command. Autoupdater wipes uncommitted changes every 30s. Use: `git checkout dev && git cherry-pick <hash> && git push origin dev && git checkout main` for dev changes.
- **Autoupdater behavior:** Runs every 30s, does `git checkout main` then `git reset --hard origin/main`. Never work directly on main — dev only.
- **Update plans after every job** — this file and `LEARNING_RUN_PLAN.md`.
- **Drug lists are FROZEN** — no more additions. Improvements through reasoning (Layers 1-3) only.
- **All AMPs are peptides** — AMP classification forces peptide=True in consistency engine.
- **Auth token:** Retrieved from `~/Developer/amphoraxe/auth.amphoraxe.ca/data/auth.db` sessions table.
- **EDAM allowlist:** Only 642 training CSV NCTs stored in EDAM. Test NCTs (fast_learning_batch_50.txt) hard-excluded by subtraction in edam_config.py.
- **Hardware:** No parallel jobs. Mac Mini M4, 16GB. API queues jobs automatically.
- **EDAM net-positive threshold:** Base accuracy must be ≥~70% for EDAM to help. Below threshold it reinforces wrong answers.
- **Failed jobs (cf642da98bd6, 434ad7a32ff8):** Both status=failed, 0 EDAM writes. No purge needed.
- **Training vs test gap:** Outcome 44-50% on training NCTs vs 68-72% on test NCTs. Don't evaluate EDAM effectiveness on training concordance.

## How to Run v21 Concordance (after Batch E/F complete)

```bash
TOKEN=$(sqlite3 ~/Developer/amphoraxe/auth.amphoraxe.ca/data/auth.db "SELECT token FROM sessions ORDER BY created_at DESC LIMIT 1;")
NCT_IDS=$(python3 -c "
with open('/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/amp_llm_v3/standalone modules/agent_annotate/scripts/fast_learning_batch_50.txt') as f:
    ncts = [l.strip() for l in f if l.strip()]
import json; print(json.dumps(ncts))
")
curl -s -X POST http://localhost:8005/api/jobs \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $TOKEN" \
  -d "{\"nct_ids\": $NCT_IDS}"
```

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
