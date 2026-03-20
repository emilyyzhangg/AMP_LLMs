# Agent Annotate — Continuation Plan

**Last updated:** 2026-03-20 ~11:30
**Current state:** Job #5 (`92fb568c1b96`) running on prod — 200 NCTs with v10 agents. Both dev and main have v10 code.

## Session Log (2026-03-20)

### What happened (chronological)

1. **Concordance analysis** — computed full results across jobs #1-4 (79 unique NCTs)
2. **Identified EDAM bootstrap was NOT learning** — batch A vs re-run differences are LLM noise, 0 corrections in DB
3. **Root-caused self-audit 0 corrections** — citation snippets miss route keywords
4. **Root-caused delivery_mode 45-50%** — 8B model, limited keyword search, missing citations
5. **Pushed v10 to dev** (commit 143758ef) — delivery_mode, classification, clinical_protocol fixes
6. **Pushed self-audit fix to dev** (commit f041f84d) — searches agent reasoning for contradictions
7. **Cancelled job #4** (`49ac8fdd9e90`) on prod — 36/200 saved
8. **Merged v10 + self-audit to main** (commit 272503c) — copied files from dev repo
9. **Submitted job #5** (`92fb568c1b96`) — same 200 NCTs, v10 agents, fresh research

### Code changes in v10

| File | Change | Branch |
|---|---|---|
| `agents/annotation/delivery_mode.py` | 31 keywords, all-source search, 14B model | dev + main |
| `agents/research/clinical_protocol.py` | detailedDescription + armGroups citations | dev + main |
| `agents/annotation/classification.py` | _parse_value AMP separator fix | dev + main |
| `app/services/memory/self_audit.py` | Searches agent reasoning for contradictions | dev + main |

## What to do next

### When job #5 completes (~24 hours)

**1. Update this plan** — record completion time, trial count, EDAM corrections

**2. Check EDAM corrections:**
```bash
PROD="/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/amp_llm_v3/standalone modules/agent_annotate/results"
sqlite3 "$PROD/edam.db" "SELECT source, COUNT(*) FROM corrections GROUP BY source;"
sqlite3 "$PROD/edam.db" "SELECT nct_id, field_name, original_value, corrected_value FROM corrections LIMIT 20;"
```

If corrections > 0 → self-audit fix is working. Record count in job registry.
If corrections = 0 → investigate logs: `grep "self-audit" logs/agent_annotate.log | tail -30`

**3. Run concordance on job #5:**
Compare 200 NCTs (v10) against human annotations. Compare delivery_mode vs job #4's 36 overlapping trials.

**4. Submit job #6** — next 200 NCTs from the remaining 714:
```bash
cd "/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/amp_llm_v3/standalone modules/agent_annotate"
python3 -c "
import json
# All 964 human-annotated
with open('scripts/human_annotated_ncts.txt') as f:
    all_ncts = [l.strip() for l in f if l.strip()]
# Already done (batches A+B + C)
with open('scripts/fast_learning_batch_50.txt') as f:
    done_ab = set(l.strip() for l in f if l.strip())
with open('results/jobs/92fb568c1b96.json') as f:
    done_c = set(json.load(f)['nct_ids'])
done = done_ab | done_c
remaining = [n for n in all_ncts if n not in done]
print(f'Remaining: {len(remaining)}')
batch = remaining[:200]
print(json.dumps(batch))
" > /tmp/batch_d.json
# Submit
curl -X POST http://localhost:8005/api/jobs -H "Content-Type: application/json" -d "{\"nct_ids\": $(cat /tmp/batch_d.json)}"
```

**5. Update LEARNING_RUN_PLAN.md job registry** with job #6 details.

### After all 964 complete (jobs #5-8, ~4 days)

1. Full concordance across all jobs
2. Decision: re-annotate or proceed to 884 unannotated NCTs
3. See LEARNING_RUN_PLAN.md Phases 2-4

## Environment State

| Environment | Branch | Agent Version | Active Job |
|---|---|---|---|
| Prod (port 8005) | main | v10 (272503c) | Job #5: 92fb568c1b96 (200 NCTs) |
| Dev (port 9005) | dev | v10 (f041f84d) | None |

## EDAM Database State

| Table | Count | Notes |
|---|---|---|
| experiences | 375 | Jobs #1-3 only. Job #4 cancelled pre-hook. Job #5 will add ~1000. |
| corrections | **0** | v9 self-audit was broken. v10 fix deployed — expect >0 from job #5. |
| stability_index | 125 | 25 NCTs × 5 fields with 2 runs each |
| embeddings | 250 | |
| prompt_variants | 0 | |
| config_epochs | 1 → 2 | v10 creates new epoch |

## Important Notes

- **Workflow:** Develop on `dev`, run jobs on prod. Only merge to `main` when explicitly told.
- **Update plans after every job** — this file and `LEARNING_RUN_PLAN.md` job registry.
- Prod autoupdater pulls from `main` every 30s. Do NOT push to main while a job is running unless necessary.
- Dev autoupdater pulls from `dev` every 30s.
- EDAM is non-fatal: if it errors, the pipeline still runs.
- `nomic-embed-text` must be in Ollama for EDAM embeddings.
- Human annotations: `dev-llm.amphoraxe.ca/docs/clinical_trials-with-sequences.xlsx`
- Research is cached per `(job_id, nct_id)` — new job_id = fresh research.

## Key File Locations

| Path | Purpose |
|---|---|
| `LEARNING_RUN_PLAN.md` | Overall strategy, job registry, concordance data |
| `results/edam.db` | EDAM learning database |
| `results/jobs/{job_id}.json` | Job status files |
| `results/annotations/{job_id}/{nct_id}.json` | Per-trial results |
| `results/research/{job_id}/{nct_id}.json` | Cached research per job |
| `results/json/{job_id}.json` | Consolidated output (completed jobs only) |
| `scripts/human_annotated_ncts.txt` | All 964 NCTs |
| `scripts/fast_learning_batch_50.txt` | Batches A+B (50 NCTs) |
