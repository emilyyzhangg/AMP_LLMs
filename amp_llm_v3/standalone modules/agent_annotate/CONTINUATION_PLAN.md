# Agent Annotate — Continuation Plan

**Last updated:** 2026-03-23 ~18:30
**Current state:** v11+efficiency merged to main. Batch A test job running. All other jobs paused.

## Session Log (2026-03-23)

### What happened (chronological)

1. **Ran concordance on 400 v10 NCTs** — outcome regressed to 47%, peptide 65%, 0/14 AMP subtypes
2. **Created v11 fix plan** — deterministic rules, confidence fix, self-audit expansion, EDAM purge
3. **Purged 128 bad peptide True→False EDAM corrections** from prod edam.db
4. **Implemented v11** — outcome, peptide, classification, self-audit fixes
5. **Cancelled jobs #7-9** on prod for v11 upgrade
6. **Submitted 3 v11 jobs** (514 NCTs) — then paused for efficiency improvements
7. **Implemented efficiency improvements:**
   - Model-grouped verification (15→3 model switches per trial)
   - Unified annotation_model (qwen2.5:14b for all fields, 0 annotation switches)
   - Enhanced progress reporting (field/agent/model/timings in UI)
8. **Cancelled 3 v11 jobs** to test Batch A first
9. **Submitted Batch A test** (`19a39aa475a3`, 25 NCTs) — same NCTs as v9 job #1

### Active Job

| Job | ID | NCTs | Status | Notes |
|-----|-----|------|--------|-------|
| Batch A test | `19a39aa475a3` | 25 | **Running** | v11+efficiency. Same NCTs as v9 job #1. |

## What to do next

### When Batch A test completes (~1-2 hours)

**1. Run 3-way concordance: v9 vs v10 vs v11**

```bash
cd "/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/amp_llm_v3/standalone modules/agent_annotate"
# v9 job #1: c7e666682865 (Batch A, 25 NCTs)
# v10 EDAM re-run: 5d207b30f11c (Batch A repeat, 25 NCTs)
# v11 test: 19a39aa475a3 (Batch A, 25 NCTs)
# Run concordance on all 3 against human R1/R2
```

**2. Compare timing: v9/v10 vs v11+efficiency**
- v9 Batch A: 3.0h (180s/trial avg)
- v11 should be significantly faster with model-grouped verification + unified annotation model
- Check `avg_seconds_per_trial` in job status

**3. Evaluate qwen2.5:14b vs llama3.1:8b impact**
- Compare outcome concordance (was 80% in v9 batch A, 47% in v10 400 NCTs)
- Compare peptide concordance (was 78.9% in v9 batch A, 65% in v10 400 NCTs)
- If any field regressed with 14b, consider per-field annotation_model config

**4. If results are good → resume 514 NCT jobs**

Re-submit the 3 jobs (same NCT batches):
```bash
curl -s -X POST http://localhost:8005/api/jobs -H "Content-Type: application/json" -d "{\"nct_ids\": $(cat /tmp/batch_e.json)}"
curl -s -X POST http://localhost:8005/api/jobs -H "Content-Type: application/json" -d "{\"nct_ids\": $(cat /tmp/batch_f.json)}"
curl -s -X POST http://localhost:8005/api/jobs -H "Content-Type: application/json" -d "{\"nct_ids\": $(cat /tmp/batch_g.json)}"
```

Or regenerate batch files:
```bash
cd "/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/amp_llm_v3/standalone modules/agent_annotate"
python3 -c "
import json
with open('scripts/human_annotated_ncts.txt') as f:
    all_ncts = [l.strip() for l in f if l.strip()]
with open('scripts/fast_learning_batch_50.txt') as f:
    batch_ab = set(l.strip() for l in f if l.strip())
with open('results/jobs/92fb568c1b96.json') as f:
    job5 = set(json.load(f).get('nct_ids', []))
with open('results/jobs/829124f16fd5.json') as f:
    job6 = set(json.load(f).get('nct_ids', []))
done = batch_ab | job5 | job6
remaining = [n for n in all_ncts if n not in done]
print(f'Remaining: {len(remaining)}')
for i, start in enumerate(range(0, len(remaining), 200)):
    batch = remaining[start:start+200]
    with open(f'/tmp/batch_{chr(101+i)}.json', 'w') as f:
        json.dump(batch, f)
    print(f'Batch {chr(101+i)}: {len(batch)} NCTs')
"
```

### After all 964 complete

1. Full concordance across all jobs
2. Selective v10 re-annotation (Job #13, ~120 NCTs) if v11 confirmed better
3. Decision: proceed to 884 unannotated NCTs

## Environment State

| Environment | Branch | Agent Version | Active Job |
|---|---|---|---|
| Prod (port 8005) | main | v11+efficiency (710912f) | Batch A test: 19a39aa475a3 |
| Dev (port 9005) | dev | v11+efficiency (710912f) | None |

## EDAM Database State (post-purge, pre-v11 jobs)

| Table | Count | Notes |
|---|---|---|
| experiences | 2,715 | v9 epoch 1 (375), v10 epoch 2 (2,340) |
| corrections | 42 | Post-purge |
| stability_index | 2,590 | |
| embeddings | 3,065 | |
| prompt_variants | 0 | |
| config_epochs | 2 → 3 | v11 creates epoch 3 on Batch A test |

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
| `scripts/fast_learning_batch_50.txt` | Batches A+B (50 NCTs) |
