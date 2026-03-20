# Agent Annotate — Continuation Plan

**Last updated:** 2026-03-20
**Current state:** Batch C running on prod (49ac8fdd9e90, 200 NCTs, ~32/200 complete). v10 agent fixes pushed to dev. Self-audit generates 0 corrections (root cause identified, fix designed).

## What was done this session (2026-03-20)

### Analysis
1. **Full concordance analysis** across batches A, B, C partial, and EDAM bootstrap
2. **Identified EDAM bootstrap was NOT learning** — differences between batch A and re-run are stochastic LLM noise, not EDAM improvement (0 corrections in DB, no guidance active)
3. **Root-caused self-audit 0 corrections** — citation snippets don't contain route keywords that the LLM finds in full evidence text. Self-audit can't see what the LLM saw.
4. **Root-caused delivery_mode 45-50% concordance** — 8B model ignores Pass 1 evidence in Pass 2; deterministic path only searches clinicaltrials_gov citations; missing detailedDescription and armGroups

### Code changes (pushed to dev, commit 143758ef)
1. **delivery_mode v10** — expanded keywords (31 entries), broadened search to ALL citation sources, upgraded mac_mini model from 8B to 14B
2. **clinical_protocol v10** — extracts detailedDescription and armGroups as citations
3. **classification v10** — fixed _parse_value swallowing AMP classifications with non-standard separators

### Plans updated
- `LEARNING_RUN_PLAN.md` — corrected false assumptions about self-audit, added self-audit enhancement spec, revised phase plan
- `CONTINUATION_PLAN.md` — this file

## What to do next

### Step 1: Validate v10 on dev (while batch C runs on prod)

Test with known-failing NCTs from batch A:
```bash
# Delete cached research so clinical_protocol re-fetches with new citations
DEV_RESEARCH="/Users/amphoraxe/Developer/amphoraxe/dev-llm.amphoraxe.ca/amp_llm_v3/standalone modules/agent_annotate/results/research"
for nct in NCT02624518 NCT02646475 NCT02665377 NCT03597282 NCT03697551 NCT00000886 NCT05361733; do
    rm -f "$DEV_RESEARCH/$nct.json"
done

# Submit test job
NCTS='["NCT02624518","NCT02646475","NCT02665377","NCT03597282","NCT03697551","NCT00000886","NCT05361733"]'
curl -X POST http://localhost:9005/api/jobs -H "Content-Type: application/json" -d "{\"nct_ids\": $NCTS}"
```

Expected: delivery_mode concordance improves significantly (these 5 IV trials should now resolve via expanded keywords or 14B model).

### Step 2: Fix self-audit (CRITICAL)

**Without this fix, EDAM will never generate corrections.** See `LEARNING_RUN_PLAN.md` "Self-audit enhancement" section for the full spec.

Summary: `self_audit.py._audit_delivery_mode()` must also search the agent's own Pass 1 reasoning (stored in `annotations[].reasoning`) for route keywords. Currently it only searches citation snippets, which miss most route evidence.

Push to dev alongside the v10 validation.

### Step 3: After batch C finishes (~23 hours from 2026-03-20 10:00)

1. **Run concordance on full batch C** (200 NCTs vs human annotations)
2. **Merge dev → main** (v10 + self-audit fix)
3. **Delete cached research** for batch C's 200 NCTs:
   ```bash
   PROD_RESEARCH="/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/amp_llm_v3/standalone modules/agent_annotate/results/research"
   # Get NCT list from job file
   python3 -c "import json; d=json.load(open('results/jobs/49ac8fdd9e90.json')); [print(n) for n in d['nct_ids']]" > /tmp/batch_c_ncts.txt
   for nct in $(cat /tmp/batch_c_ncts.txt); do rm -f "$PROD_RESEARCH/$nct.json"; done
   ```
4. **Re-run batch C's 200 NCTs with v10** — this generates EDAM corrections via:
   - Stability tracker: compares v9 run vs v10 run for same NCTs
   - Self-audit (enhanced): catches Pass 1 vs Pass 2 contradictions
5. **Continue with remaining ~714 NCTs** in batches of 200

### Step 4: Continue Phase 1 (remaining 714 NCTs)

After the v10 re-run of batch C:
```
Batch D: ~200 NCTs  — first batch with real EDAM corrections from batch C comparison
Batch E: ~200 NCTs  — compounding corrections
Batch F: ~164 NCTs  — remaining NCTs
```

### Step 5: Full concordance + decision

After all 964 annotated, run `scripts/concordance_jobs.py` across all jobs.
Decision criteria in `LEARNING_RUN_PLAN.md` Phase 5.

## EDAM database state (2026-03-20)

| Table | Count | Notes |
|---|---|---|
| experiences | 375 | 25 NCTs × 5 fields × 3 jobs (A, B, A-repeat) |
| corrections | **0** | Self-audit broken — see root cause above |
| stability_index | 125 with >1 run | Only batch A NCTs (25×5), 15 unstable fields |
| embeddings | 250 | |
| prompt_variants | 0 | Optimization hasn't fired yet |
| config_epochs | 1 | Single config version so far |

## Key file locations

| Path | Purpose |
|---|---|
| `results/edam.db` | EDAM learning database |
| `results/jobs/49ac8fdd9e90.json` | Batch C job status (running) |
| `results/annotations/{job_id}/{nct_id}.json` | Per-trial annotation results |
| `results/research/{nct_id}.json` | Cached research data per trial |
| `results/review_queue.json` | Flagged items for manual review |
| `results/batch_a_analysis.md` | Batch A concordance analysis |
| `scripts/human_annotated_ncts.txt` | All 964 NCTs with human annotations |
| `scripts/fast_learning_batch_50.txt` | Batches A+B NCTs (50) |
| `LEARNING_RUN_PLAN.md` | Overall EDAM strategy and concordance data |
| `app/services/memory/self_audit.py` | Self-audit (needs enhancement) |

## Important notes

- Prod autoupdater pulls from `main` every 30s — do NOT merge dev → main while batch C is running
- Dev autoupdater pulls from `dev` every 30s
- v10 is on dev only (commit 143758ef). Prod still runs v9.
- EDAM is non-fatal: if it errors, the pipeline runs normally
- The `nomic-embed-text` model must be available in Ollama for EDAM embeddings
- Human annotation Excel: `dev-llm.amphoraxe.ca/docs/clinical_trials-with-sequences.xlsx`
- Research cache: deleting `results/research/{nct_id}.json` forces re-research on next run
