# Agent Annotate — Continuation Plan

**Last updated:** 2026-03-24
**Current state:** v12 fixes applied on dev. No active jobs. Needs commit+push to dev, then Batch A re-run.

## Session Log (2026-03-24)

### What happened (chronological)

1. **Analyzed job 1ff6092a499c** (v11+eff, 25 NCTs) — UI showed 30 trials, actually 25 unique
2. **Found dedup bug** in `orchestrator.py:899-924` — trial appended before persistence; if persistence failed, except block added duplicate. Fixed: moved append after persistence, added dedup guard in except block.
3. **Added dedup safety net** in `output_service.py` `save_json_output()`
4. **Fixed concordance/results endpoints** (`concordance.py`, `results.py`) — were reading stale `total_trials` field from JSON; now derive from actual unique NCT count
5. **Fixed existing JSON** (`1ff6092a499c.json`) — deduped 30→25 trials, updated total_trials, removed .tmp files
6. **Ran concordance on v11+eff job** — outcome regressed to 52% vs R1 (was 80% in v9)
7. **Root-caused outcome regression:**
   - 6/9 wrong Unknowns from Phase I guard (COMPLETED Phase I without hasResults → Unknown)
   - hasResults is frequently unpopulated even when publications exist
   - All 9 Unknowns wrong: humans unanimously agree (5 Failed, 4 Positive)
8. **Root-caused RFR regression:**
   - 5/14 errors cascade from wrong Unknown outcome (consistency rule blanks RFR)
   - 3/14 from Withdrawn trials getting blank RFR (humans annotated real reasons)
9. **Implemented v12 fixes:**
   - Removed Phase I guard deterministic rule (`outcome.py`)
   - Removed confidence source_sufficiency cap /2 (`outcome.py`)
   - Removed Withdrawn from failure_reason pre-check skip list (`failure_reason.py`)
   - Removed Withdrawn from consistency rules (`orchestrator.py`, both pre- and post-verification)
   - Widened self-audit evidence keywords for Positive check (`self_audit.py`)
10. **Discovered wrong batch** — job 1ff6092a499c used different NCTs than `fast_learning_batch_25.txt` (only 12/25 overlap with v9). 3-way comparison invalid.
11. **Updated LEARNING_RUN_PLAN.md** — added v12 version entry, updated job registry, concordance results, and phase plan

### Active Job

None.

## What to do next

### Step 1: Commit and push v12 to dev

```bash
cd "/Users/amphoraxe/Developer/amphoraxe/dev-llm.amphoraxe.ca"
git add -A && git commit -m "v12: fix outcome regression, dedup bug, withdrawn RFR" && git push
```

### Step 2: Re-run Batch A on CORRECT NCTs

Submit using the correct batch file (`fast_learning_batch_25.txt`):
```bash
cd "/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/amp_llm_v3/standalone modules/agent_annotate"
# Only after v12 is merged to main and prod autoupdater picks it up
NCT_IDS=$(python3 -c "
with open('scripts/fast_learning_batch_25.txt') as f:
    ncts = [l.strip() for l in f if l.strip()]
import json; print(json.dumps(ncts))
")
curl -s -X POST http://localhost:8005/api/jobs \
  -H 'Content-Type: application/json' \
  -d "{\"nct_ids\": $NCT_IDS}"
```

### Step 3: 3-way concordance (v9 vs v10 vs v12)

All on same 25 NCTs from `fast_learning_batch_25.txt`:
- v9 job #1: `c7e666682865`
- v10 repeat: `5d207b30f11c`
- v12 job: TBD

Expected: outcome should recover to 80%+ (Phase I guard was sole cause of 9/9 errors).

### Step 4: If v12 validated → submit remaining 514 NCTs

Regenerate batch files and submit 3 jobs (see LEARNING_RUN_PLAN.md Phase 2).

## Environment State

| Environment | Branch | Agent Version | Active Job |
|---|---|---|---|
| Prod (port 8005) | main | v11+eff (710912f) | None |
| Dev (port 9005) | dev | v12 (uncommitted) | None |

## EDAM Database State

| Table | Count | Notes |
|---|---|---|
| experiences | 2,715 | v9 epoch 1 (375), v10 epoch 2 (2,340) |
| corrections | 42 | Post-purge |
| stability_index | 2,590 | |
| embeddings | 3,065 | |
| prompt_variants | 0 | |
| config_epochs | 2 → 3 | v11 created epoch 3 on job 1ff6092a499c |

## Important Notes

- **Workflow:** Develop on `dev`, run jobs on prod. Only merge to `main` when explicitly told.
- **CRITICAL:** Always commit+push atomically in ONE bash command. Autoupdater wipes uncommitted changes every 30s.
- **Update plans after every job** — this file and `LEARNING_RUN_PLAN.md` job registry.
- Prod autoupdater pulls from `main` every 30s. Do NOT push to main while a job is running.
- EDAM is non-fatal: if it errors, the pipeline still runs.
- Human annotations: `dev-llm.amphoraxe.ca/docs/clinical_trials-with-sequences.xlsx`

## Key File Locations

| Path | Purpose |
|---|---|
| `LEARNING_RUN_PLAN.md` | Overall strategy, job registry, concordance data |
| `results/edam.db` | EDAM learning database |
| `results/jobs/{job_id}.json` | Job status files |
| `results/annotations/{job_id}/{nct_id}.json` | Per-trial annotation results |
| `results/json/{job_id}.json` | Consolidated output (completed jobs only) |
| `scripts/human_annotated_ncts.txt` | All 964 NCTs |
| `scripts/fast_learning_batch_25.txt` | Batches A+B original 25 (matches v9 job #1) |
