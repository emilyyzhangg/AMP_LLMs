# Agent Annotate — Continuation Plan

**Last updated:** 2026-03-27
**Current state:** v19 (61781e32) on dev. v18+hotfixes (776aeea) on main. Batch A+B (50 NCTs) complete (job 76392846aee8). v19 ready to merge and run.

## Current Concordance (v18+hotfixes, 50 NCTs)

| Field | v18+ vs R1 | v18+ AC₁ | v17 best (25) | Target | Met? |
|---|---|---|---|---|---|
| Classification | 87.8% | 0.870 | 88.0% | AC₁≥0.82 | YES |
| Delivery Mode | 67.3% | 0.654 | 68.0% | ≥73% | NO |
| Outcome | 70.0% | 0.657 | 76.0% | ≥80% | NO (regressed) |
| Reason for Failure | 72.0% | 0.671 | 68.0% | ≥84% | NO (improved) |
| Peptide | 88.9% | 0.865 | 90.9% | ≥86% | YES |
| Sequence | 59.1%* | 0.574 | 32% (empty) | ≥30% exact | YES (breakthrough) |

*Sequence: 13/22 = exact matches. Real sequences now extracted correctly.

**2/6 targets met.** Big wins: sequence breakthrough, RfF improvement. Main blocker: outcome Failed under-calling.

## Next Step: Merge v19 to main and run Batch A+B

### v19 changes (all on dev, commit 61781e32)

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
| Prod (port 8005) | main | v18+hotfixes (776aeea) | None (76392846aee8 complete) |
| Dev (port 9005) | dev | v19 (d777be62) | None |

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
