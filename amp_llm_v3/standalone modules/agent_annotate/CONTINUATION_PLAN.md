# Agent Annotate — Continuation Plan

**Last updated:** 2026-03-25
**Current state:** v16 on both dev and main (8223691). No active jobs. EDAM has 300 experiences from v14/v15 runs.

## Next Step: Run Batch A on v16

v16 has 6 substantial fixes. Need to re-run Batch A (25 NCTs) to validate improvements before moving to Phase 2.

### Submit the job
```bash
TOKEN="J6YtEd_HKw5G7aBzG86dcLyVD54itfCZqiMG2x-9xEk"
NCT_IDS=$(python3 -c "
with open('scripts/fast_learning_batch_25.txt') as f:
    ncts = [l.strip() for l in f if l.strip()]
import json; print(json.dumps(ncts))
")
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"nct_ids\": $NCT_IDS}" http://localhost:8005/api/jobs
```

### What to check after completion

1. **Run concordance** — compare v16 vs v15 (c3fa1fbba5c2):
   - Sequence: was 0/25 — expect >0 (critical fix)
   - Outcome: was 78.3% — expect ≥80% (adverse-event heuristics)
   - Peptide: was 86.4% — check that confidence gate doesn't regress
   - RfF: was 84.0% — check Unknown-gate removal helps (Toxic/Unsafe, Ineffective)
   - Delivery: was 69.6%/95.7% bucketed — check multi-route support

2. **Convergence check:** If v16 vs v15 concordance differs by <2% on all non-sequence fields → code is stable, ready for Phase 2.

3. **If sequence >50%:** Phase 1 targets met across all fields → submit Phase 2 (50 NCTs).

4. **If regressions:** Analyze per-trial disagreements, fix code, re-run.

### v16 changes being tested

| Fix | What changed | Expected impact |
|---|---|---|
| Sequence agent | metadata passed to all agents, raw_data key fallback, prefix stripping | 0%→>0% (was totally broken) |
| Outcome heuristics | Adverse-event keyword detection, publications as H1 corroboration | 78.3%→≥80% |
| Peptide cascade gate | Require conf≥0.90 for False→N/A cascade | Protect NCT02624518, NCT02654587 |
| Multi-route delivery | Comma-separated routes for combination trials | Improve strict concordance |
| RfF Unknown gate | Removed "Unknown" from skip list | Detect Toxic/Unsafe, Ineffective |
| AC1 docs | Prevalence paradox guidance in paper/methodology | No concordance impact |

## v15 Concordance Baseline (job c3fa1fbba5c2)

| Field | vs R1 | vs R2 | R1↔R2 |
|---|---|---|---|
| Classification | 83.3% (AC₁=0.82) | 87.5% | 88.0% |
| Delivery Mode | 69.6% / bucketed 95.7% | 73.9% | 76.0% |
| Outcome | 78.3% (κ=0.72) | 69.6% | 80.0% |
| Reason for Failure | 84.0% (κ=0.77) | 80.0% | 88.0% |
| Peptide | 86.4% | 75.0% | 83.3% |
| Sequence | 0.0% | 0.0% | 70.6% |

## Environment State

| Environment | Branch | Version | Active Job |
|---|---|---|---|
| Prod (port 8005) | main | v16 (8223691) | None |
| Dev (port 9005) | dev | v16 (8223691) | None |

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
