# Agent Annotate — Continuation Plan

**Last updated:** 2026-03-24 (end of session)
**Current state:** v12+reasoning on both dev and main (bb2c6fb). Batch A running (ba1689125a8f). EDAM epoch 1 starting fresh.

## Active Job

| Job | ID | NCTs | Status | Version | Notes |
|-----|-----|------|--------|---------|-------|
| Batch A (v12+reasoning) | `ba1689125a8f` | 25 | **Running** | bb2c6fb | First run with full reasoning-first stack. ~3h. |

## What to do when job completes

### 1. Run concordance
Check the Agreement Metrics page at `llm.amphoraxe.ca/agent-annotate/concordance` — it should auto-detect the completed job. Compare against v12 baseline (job cdcfc68c191d):

| Field | v12 baseline | Expected v12+reasoning |
|---|---|---|
| Classification | 92% | Should improve (Mode D re-added, growth inhibition) |
| Outcome | 72% | Should improve (min_sources 1, better research) |
| Peptide | 73% | Should improve (Pass 1/2 check, drug name resolution, UniProt cross-validation) |
| Delivery mode | 60% | Should improve (infusion→IV, auto-injector→SC) |
| Reason for failure | 80% | Should hold or improve |
| Sequence | N/A | First run — check if any sequences extracted |

### 2. Check EDAM state
```python
import sqlite3
conn = sqlite3.connect('results/edam.db')
for t in ['experiences','corrections','drug_names','config_epochs']:
    c = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
    print(f'{t}: {c}')
```
Verify: drug_names has cached resolutions, corrections include consistency_override and reconciliation sources.

### 3. Analyze remaining disagreements
Focus on: are the remaining errors in researchable drugs (Layer 1 can help) or novel/unknown drugs (fundamental limit)?

### 4. If targets met → Phase 2 (50 NCTs)
Submit Batch A+B (`fast_learning_batch_50.txt`). If concordance holds → Phase 3 (full 964).

## Session Summary (2026-03-24)

**15 commits** covering:
- v12 bug fixes (dedup, Phase I guard, confidence cap, Withdrawn RFR)
- Sequence as 6th annotation field
- Peptide definition 2-50 AA single-chain
- AMP Mode D re-added (pathogen-targeting vaccines)
- AMP Mode A expanded (growth inhibition, bacteriostatic)
- Reasoning-first strategy (Layers 1-3: drug name resolution, structured handoff, cross-validation)
- EDAM learning improvements (consistency overrides, reconciliation, drug name caching, reasoning patterns)
- Grouped concordance toggle, Agreement Metrics (AC₁ primary)
- SerpAPI removed, evidence thresholds lowered
- Multi-drug peptide bypass fixed, AMP→peptide consistency rule

## Environment State

| Environment | Branch | Version | Active Job |
|---|---|---|---|
| Prod (port 8005) | main | v12+reasoning (bb2c6fb) | ba1689125a8f |
| Dev (port 9005) | dev | v12+reasoning (bb2c6fb) | None |

## Important Notes

- **Workflow:** Develop on `dev`, run jobs on prod. Only merge to `main` when explicitly told.
- **CRITICAL:** Always commit+push atomically in ONE bash command. Autoupdater wipes uncommitted changes every 30s.
- **Update plans after every job** — this file and `LEARNING_RUN_PLAN.md`.
- **Drug lists are FROZEN** — no more additions. Improvements through reasoning (Layers 1-3) only.
- **All AMPs are peptides** — AMP classification forces peptide=True in consistency engine.

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
