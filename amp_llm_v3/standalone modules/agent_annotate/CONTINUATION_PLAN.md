# Agent Annotate — Continuation Plan

**Last updated:** 2026-03-23 ~17:30
**Current state:** v11 merged to main. 3 jobs submitted (514 NCTs). Job #10 running.

## Session Log (2026-03-23)

### What happened (chronological)

1. **Job #5 completed** (`92fb568c1b96`) — 200 NCTs, v10, finished 2026-03-21 19:18
2. **Job #6 completed** (`829124f16fd5`) — 200 NCTs, v10, finished 2026-03-22 23:59
3. **Ran concordance on 400 v10 NCTs** — outcome regressed to 47%, peptide under-calling at 65%
4. **Identified 3 critical issues** — outcome regression, peptide under-calling, AMP subtype blindness
5. **Created v11 fix plan** — deterministic rules, confidence fix, self-audit expansion, EDAM purge
6. **Cancelled jobs #7-9** on prod for v11 upgrade
7. **Purged 128 bad peptide True→False EDAM corrections** from prod edam.db
8. **Implemented v11** on dev (commit `efa9baef`), merged to main (commit `2a1ebba`)
9. **Analyzed v10 re-annotation impact** — 107/400 outcome, 13/400 peptide would change
10. **Submitted 3 v11 jobs** — 514 remaining NCTs in 3 batches

### v11 Jobs Submitted

| Job | ID | NCTs | Status | Notes |
|-----|-----|------|--------|-------|
| #10 | `60aa4a590462` | 200 | Running/Queued | Batch E — first v11 job |
| #11 | `26baede0fdec` | 200 | Queued | Batch F |
| #12 | `b4536fa3e108` | 114 | Queued | Batch G — final batch |

Estimated completion: ~31 hours from submission (~2026-03-25 00:30)

## What to do next

### When jobs #10-12 complete (~31 hours)

**1. Update this plan and LEARNING_RUN_PLAN.md** — record completion time, trial count, EDAM corrections

**2. Check EDAM corrections:**
```bash
PROD="/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/amp_llm_v3/standalone modules/agent_annotate/results"
sqlite3 "$PROD/edam.db" "SELECT source, field_name, original_value, corrected_value, COUNT(*) FROM corrections WHERE epoch=3 GROUP BY source, field_name, original_value, corrected_value ORDER BY COUNT(*) DESC;"
```

Expect corrections for outcome, classification, and peptide (v11 self-audit now covers all 4 fields).

**3. Run concordance on v11 jobs:**
Compare 514 v11 NCTs against human annotations. Compare v11 concordance vs v10 (400 NCTs) to measure improvement.

**4. Selective v10 re-annotation (if v11 concordance confirms improvement):**
Submit Job #13: ~120 NCTs from v10 batches that would change with v11 deterministic rules:
- 107 COMPLETED Phase I trials (outcome: Positive→Unknown)
- 13 known-peptide false negatives (peptide: False→True)

```bash
# Generate re-annotation list (run after concordance confirms improvement)
cd "/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/amp_llm_v3/standalone modules/agent_annotate"
python3 scripts/generate_v10_reannotation_list.py  # TODO: create this script
```

### After all 964 complete

1. Full concordance across all jobs (v9 batch A+B, v10 C+D, v11 E+F+G, selective re-annotations)
2. Decision: re-annotate remaining v10 trials or proceed to 884 unannotated NCTs
3. See LEARNING_RUN_PLAN.md Phases 4-5

## Environment State

| Environment | Branch | Agent Version | Active Job |
|---|---|---|---|
| Prod (port 8005) | main | v11 (2a1ebba) | Job #10: 60aa4a590462 (200 NCTs) |
| Dev (port 9005) | dev | v11 (efa9baef) | None |

## EDAM Database State (post-purge, pre-v11 jobs)

| Table | Count | Notes |
|---|---|---|
| experiences | 2,715 | Jobs #1-7 (v9 epoch 1, v10 epoch 2) |
| corrections | 42 | Post-purge. 20 pep T→F, 5 pep F→T, 7 dm, 4 outcome, etc. |
| stability_index | 2,590 | |
| embeddings | 3,065 | |
| prompt_variants | 0 | Will fire after job #12 (every 3rd job) |
| config_epochs | 2 → 3 | v11 creates epoch 3 |

### Epoch decay on v11 start

| Data | Epoch Distance | Weight | Floor |
|------|---------------|--------|-------|
| v10 experiences | 1 | 75% | 5% |
| v10 corrections | 1 | 80% | 10% |
| v9 experiences | 2 | 56% | 5% |

## Important Notes

- **Workflow:** Develop on `dev`, run jobs on prod. Only merge to `main` when explicitly told.
- **Update plans after every job** — this file and `LEARNING_RUN_PLAN.md` job registry.
- Prod autoupdater pulls from `main` every 30s. Do NOT push to main while a job is running.
- Dev autoupdater pulls from `dev` every 30s.
- **CRITICAL:** Always commit+push atomically in ONE bash command. Autoupdater wipes uncommitted changes every 30s.
- EDAM is non-fatal: if it errors, the pipeline still runs.
- Human annotations: `dev-llm.amphoraxe.ca/docs/clinical_trials-with-sequences.xlsx`

## Key File Locations

| Path | Purpose |
|---|---|
| `LEARNING_RUN_PLAN.md` | Overall strategy, job registry, concordance data |
| `results/edam.db` | EDAM learning database |
| `results/jobs/{job_id}.json` | Job status files |
| `results/annotations/{job_id}/{nct_id}.json` | Per-trial annotation results |
| `results/research/{job_id}/{nct_id}.json` | Cached research per job |
| `results/json/{job_id}.json` | Consolidated output (completed jobs only) |
| `scripts/human_annotated_ncts.txt` | All 964 NCTs |
| `scripts/fast_learning_batch_50.txt` | Batches A+B (50 NCTs) |
