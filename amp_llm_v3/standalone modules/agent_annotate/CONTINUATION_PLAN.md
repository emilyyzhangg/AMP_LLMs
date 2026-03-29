# Agent Annotate — Continuation Plan

**Last updated:** 2026-03-29
**Current state:** v20 (163eaf1) on main. Training-C run 1 running (job ba96acf75132). EDAM fully clean — all 50 test-batch NCTs purged from experiences/corrections/stability_index. Test-batch NCTs now hard-excluded from TRAINING_NCTS in code (edam_config.py).

## Latest Concordance

### v19 (50 NCTs, 2 runs: c1786d005ade / ac6af4e49fe2) — 2026-03-27

| Field | v19 R1 | v19 R2 | v18+ baseline | Target | Met? |
|---|---|---|---|---|---|
| Classification | **92.0% / AC₁=0.917** | **92.0% / AC₁=0.917** | 87.8% / 0.870 | AC₁≥0.82 | YES (+4.2%) |
| Delivery Mode | 65.3% / 0.632 | 63.3% / 0.614 | 67.3% / 0.654 | ≥73% | NO (slight regress) |
| Outcome | 72.0% / 0.680 | 68.0% / 0.634 | 70.0% / 0.657 | ≥80% | NO (slight improve) |
| Reason for Failure | 72.0% / 0.671 | 68.0% / 0.625 | 72.0% / 0.671 | ≥84% | NO (same) |
| Peptide | 86.7% / 0.834 | 80.0% / 0.734 | 88.9% / 0.865 | ≥86% | Borderline / high variance |
| Sequence | 65.0% / 0.634 | 68.4% / 0.668 | 59.1% / 0.574 | ≥30% | YES (from code only) |

Key findings:
- Classification fixed: vaccine misclassification (NCT00000886/00002428) resolved ✅
- Reconciler bug found: 15 cases where `agreement_ratio=0.0` still kept Pass1 value → fixed in v20
- High run-to-run variance on peptide (7%) due to temp=0.05 → fixed in v20 (temp=0.0)
- Sequence improvement purely from v19 code changes, not EDAM (EDAM hadn't fired)
- 35 test-batch NCTs were still in EDAM (contamination) → purged in v20

## Current: v20 Training runs (jobs ba96acf75132 + 3 queued)

### v20 changes (merged to main, commit 163eaf1)

**1. Reconciler bug fix (CRITICAL)**
- `orchestrator.py`: unanimous verifier disagreement (`agreement_ratio=0.0`) now always routes to reconciler
- Prevents high-confidence Pass1 from overriding 3/3 verifiers
- Fixes 15 known per-run cases including NCT04701021 (Outcome=Positive should be Unknown)

**2. EDAM test-set contamination resolved**
- `edam_config.py`: `TRAINING_NCTS` now permanently subtracts `fast_learning_batch_50.txt` at load
- All 50 test-batch NCTs purged from prod EDAM (1,314 experiences, 113 corrections, 175 stability entries removed)
- EDAM now: 360 experiences / 31 corrections from clean training NCTs only

**3. CT.gov results section (Layer 1)**
- `clinical_protocol.py`: extracts `hasResults` flag and `outcomeMeasuresModule` primary outcomes from already-fetched CT.gov response (no extra HTTP call)
- `hasResults: Yes/No` always emitted as citation; primary outcome data added when posted

**4. Delivery mode ambiguity bias (Layer 2)**
- `delivery_mode.py` Rule 8: explicit route keyword required; no inferring SC from drug class or IV from mg/kg
- `verifier.py`: matching instruction with examples

**5. Outcome verifier clarification (Layer 2)**
- `verifier.py`: "Failed" requires positive evidence of endpoint failure; absence of publications = Unknown

**6. AMP(other) boundary (Layer 2)**
- `classification.py`: Step 3 now states AMP(other) requires confirmed antimicrobial mechanism from Step 2

**7. Peptide deterministic temperature**
- `config_models.py`: peptide field temp `0.05 → 0.0`; eliminates 7% run-to-run variance

### v19 changes (commit ee4fdee)

**1. Classification — Mode D removed (CRITICAL fix)**
- Removed Mode D (pathogen-targeting immunogens = AMP) from both classifier and verifier
- Root cause of persistent NCT00000886/NCT00002428 misclassification: **verifier still had HIV/influenza vaccines as AMP while classifier said Other** — verifier was overriding the correct answer
- ic41, ic43 removed from _KNOWN_AMP_DRUGS
- All vaccine peptides now: Other

**2. Outcome — negative efficacy signals added (HIGH)**
- _infer_from_pass1 now catches: "did not demonstrate/achieve/show", "no significant/benefit/improvement/efficacy", "failed to demonstrate/meet/primary", "lack of efficacy", "ineffective"
- NCT04672083 (Phase 1, no pubs) → Unknown is correct; R1 wrong on that one
- Other 4 failing NCTs expected to improve with new signals

**3. Delivery mode — SC tightened + cancer vaccine fallback (MEDIUM)**
- Removed bare " sc " abbreviation from keyword table
- Added "sc injection", "sc administration", "sc dose" as explicit replacements
- Added RULE 7: peptide vaccines / cancer immunotherapy → Other/Unspecified, NOT Intranasal when route unspecified

**4. Sequence — primary interventions only + DBAASP/APD suppression (MEDIUM)**
- _extract_primary_interventions(): filter to EXPERIMENTAL arms only (not comparators/background)
- DBAASP and APD suppressed for classification=Other trials (they're AMP DBs; return false positives for cancer vaccines)
- Fixes NCT00995358: Brevinin from frog skin was returned for a cancer peptide vaccine trial

**5. Literature — old trial fallback (LOW)**
- Trials with NCT number < 100,000 (pre-2005) always run title-based fallback search
- Fixes NCT00004984 (DPT-1): NCT ID search found secondary papers only; title search finds NEJM 2002 primary paper

### How to run v19 (after merging to main)

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

### What to check after v19

1. **Outcome:** Expect ≥76% vs R1 (6+ Failed cases now correctly identified)
2. **RfF:** Expect cascade improvement — if outcome Fixed, 6 RfF empties should resolve
3. **Classification:** NCT00000886 and NCT00002428 should now be "Other"
4. **Delivery mode:** Expect minor improvement if SC evidence threshold raised
5. **Sequence + Peptide:** Should stay stable (no changes to these)

## Environment State

| Environment | Branch | Version | Active Job |
|---|---|---|---|
| Prod (port 8005) | main | v20 (163eaf1) | ba96acf75132 running (training-C ×50) |
| Dev (port 9005) | dev | v20 (c3417a5) | None |

### Training Queue (2026-03-29)
| Job | Batch | NCTs | Status |
|---|---|---|---|
| ba96acf75132 | training-C run 1 | 50 | **running** |
| 29830f7d3785 | training-C run 2 | 50 | queued |
| 798817a09db3 | training-D run 1 | 50 | queued |
| 3fc6552eb54e | training-D run 2 | 50 | queued |

100 unique training NCTs (CSV positions 1-100, excl. test batch), each run twice for EDAM stability.
After all 4 complete: run Batch A+B (50 test NCTs) on v20 to measure concordance improvement.

## Important Notes

- **Workflow:** Develop on `dev`, run jobs on prod. Only merge to `main` when explicitly told.
- **CRITICAL:** Always commit+push atomically in ONE bash command. Autoupdater wipes uncommitted changes every 30s.
- **Update plans after every job** — this file and `LEARNING_RUN_PLAN.md`.
- **Drug lists are FROZEN** — no more additions. Improvements through reasoning (Layers 1-3) only.
- **All AMPs are peptides** — AMP classification forces peptide=True in consistency engine.
- **Auth token:** Retrieved from `~/Developer/amphoraxe/auth.amphoraxe.ca/data/auth.db` sessions table.
- **EDAM allowlist:** Only 642 training CSV NCTs stored in EDAM. Test NCTs excluded.

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
