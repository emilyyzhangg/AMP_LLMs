# EDAM Learning Run Plan

**Last updated:** 2026-03-21 ~19:00

## Job Registry

This is the canonical list of every annotation job run. Update after every job.

| # | Batch | Job ID | NCTs | Completed | Status | Agent Ver | Git Commit | EDAM Corrections | Started | Finished | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | A | c7e666682865 | 25 | 25/25 | **Complete** | v9 | 8d6f236 | 0 | 2026-03-19 12:20 | 2026-03-19 15:21 | Richest 25 NCTs (4-5 fields both R1+R2). First prod run. |
| 2 | B | ae1ece9d4e0a | 25 | 25/25 | **Complete** | v9 | 8d6f236 | 0 | 2026-03-19 ~17:00 | 2026-03-19 ~20:00 | Next richest 25. No NCT overlap with A. |
| 3 | A repeat | 5d207b30f11c | 25 | 25/25 | **Complete** | v9 | 8d6f236 | 0 | 2026-03-19 20:34 | 2026-03-19 23:31 | EDAM bootstrap — same 25 as batch A. Differences are stochastic noise only. |
| 4 | C (v9) | 49ac8fdd9e90 | 200 | 36/200 | **Cancelled** | v9 | c1d6599 | N/A | 2026-03-20 05:59 | 2026-03-20 ~11:00 | Cancelled to merge v10 agents. 36 per-trial annotations saved. No consolidated JSON. |
| 5 | C (v10) | 92fb568c1b96 | 200 | 143/200 | **Running** (resumed) | v10 | 272503c | TBD | 2026-03-20 ~11:15 | — | Same 200 NCTs as job #4. Interrupted twice by autoupdater, resumed at 143. |
| 6 | D | 7412fcad059f | 200 | 0/200 | **Queued** | v10 | 1112528 | TBD | — | — | NCT03516773–NCT04389775. First batch with EDAM corrections from job #5. |
| 7 | E | daa1db01dac0 | 200 | 0/200 | **Queued** | v10 | 1112528 | TBD | — | — | NCT04397926–NCT05293665. Compounding EDAM corrections. |
| 8 | F | 1d9944e81bda | 200 | 0/200 | **Queued** | v10 | 1112528 | TBD | — | — | NCT05301192–NCT06429566. |
| 9 | G | 076d1edc6060 | 114 | 0/114 | **Queued** | v10 | 1112528 | TBD | — | — | NCT06430671–NCT07012330. Final batch, completes all 964. |

### Agent version summary

| Version | Commit | Key changes |
|---|---|---|
| v9 | 8d6f236 | Two-pass annotation, deterministic bypass, EDAM system, verification personas |
| v10 | 272503c (main), f041f84d (dev) | delivery_mode: expanded keywords (31), all-source search, 14B model on mac_mini. clinical_protocol: detailedDescription + armGroups. classification: _parse_value fix. self_audit: searches agent reasoning for contradictions. |
| v10+queue | 1112528 (main), 84118cdc (dev) | Job queue: multiple jobs submitted and run sequentially. Cross-branch gatekeeper in worker. METHODOLOGY/PAPER: Peptide and AMP definitions expanded. |

## NCT Coverage

| Set | Count | Status |
|---|---|---|
| Human-annotated (total) | 964 | Target for Phase 1 |
| Batch A+B (richest 50) | 50 | Complete (v9), 25 have 2 runs |
| Batch C (200) | 200 | v10 running (job #5, 143/200) |
| Batches D–G (714) | 714 | Queued (jobs #6–9), auto-starts after #5 |
| Unannotated (no human ref) | 884 | Phase 6 — agent-only |

## Why EDAM self-audit generated 0 corrections (jobs #1-4)

**Root cause:** Self-audit searches citation snippet text for route keywords (e.g., "intravenous"). But the route info the LLM finds often comes from:

1. **Literature abstracts not captured in snippets** — snippets are truncated title/author/journal
2. **Arm group descriptions not extracted** — fixed in v10 clinical_protocol
3. **Detailed descriptions not extracted** — fixed in v10 clinical_protocol

**Fix applied in v10:** Self-audit now also searches the agent's own Pass 1 reasoning (stored in `annotations[].reasoning`). If Pass 1 found "intravenous" but Pass 2 said "Other/Unspecified", that's a correction.

## Why the original EDAM assumptions were wrong

1. **"Self-audit catches evidence contradictions on first run"** — FALSE. Citation snippets miss keywords.
2. **"Forward progress generates compounding corrections"** — FALSE without the self-audit fix.
3. **"Re-runs waste compute"** — PARTIALLY TRUE. Re-runs after agent improvements (v9→v10) generate corrections via stability comparison.
4. **"EDAM self-review handles flagged items"** — Only 1-3/25 trials get flagged. Most errors aren't flagged.

## Plan going forward

### Phase 1: Complete 964 human-annotated NCTs with v10

All jobs queued and running autonomously. No intervention required.

```
Job #5: 200 NCTs (RUNNING, 143/200) — ~7h remaining
Job #6: 200 NCTs (QUEUED)           — ~24h, first batch with EDAM corrections from #5
Job #7: 200 NCTs (QUEUED)           — ~24h, compounding corrections
Job #8: 200 NCTs (QUEUED)           — ~24h
Job #9: 114 NCTs (QUEUED)           — ~14h, final batch
```

**Estimated total: ~4 days from 2026-03-21 19:00 → ~2026-03-25.**

EDAM post-job hook fires between each job, storing corrections that feed into the next job's prompts. Prompt optimization fires every 3rd job (will first trigger after job #7 or #8).

After all jobs complete: update this registry, run full concordance, check EDAM corrections.

### Phase 2: Full concordance on all 964

```bash
.venv/bin/python scripts/concordance_jobs.py
```

Break down by batch to see v9 vs v10 improvement and EDAM compounding.

### Phase 3: Decision — re-annotate or proceed?

**Targets (must exceed human inter-rater baseline):**
- Outcome: human R1 vs R2 = 55.6% → agent target: >70%
- Peptide: human R1 vs R2 = 48.4% → agent target: >65%
- Classification: AC₁ > 0.85
- Delivery mode: > 60% (biggest improvement expected from v10)

If met → Phase 4. If not → analyze errors, potentially fix agents, re-run worst batches.

### Phase 4: Annotate 884 unannotated NCTs

Agent-only, no human counterpart. Full EDAM guidance from 964 validated trials.

## EDAM Database State

| Table | Count | Notes |
|---|---|---|
| experiences | 375 | Jobs #1-3 (25×5×3). Job #4 cancelled before EDAM hook. |
| corrections | **0** | Self-audit was broken in v9. Fixed in v10 — expect corrections from job #5. |
| stability_index | 125 with >1 run | Only batch A NCTs (25×5 from jobs #1 and #3). 15 unstable fields. |
| embeddings | 250 | |
| prompt_variants | 0 | Fires every 3rd job. First pass at job #6 or #7. |
| config_epochs | 1 → 2 | v10 code change will create epoch 2. |

## Concordance Summary (as of 2026-03-20, 79 unique NCTs from jobs #1-4)

### Agent vs R1 by batch

| Field | A+EDAM (MV, 25) | B (25) | C v9 partial (30) |
|---|---|---|---|
| Classification | 91.7% / AC₁ 0.91 | 92.0% / AC₁ 0.91 | 48.0% / AC₁ 0.34 |
| Peptide | 78.9% / κ 0.41 | 78.3% / κ 0.23 | 73.3% / κ 0.25 |
| Outcome | 81.8% / κ 0.76 | 60.0% / κ 0.43 | 66.7% / κ 0.33 |
| Delivery mode | 45.0% / κ 0.34 | 50.0% / κ 0.31 | 43.5% / κ 0.34 |
| Reason for failure | 60.9% / κ 0.43 | 44.0% / κ 0.26 | 93.3% / AC₁ 0.93 |

### Stability (batch A vs EDAM re-run, no EDAM guidance)

| Field | Stability |
|---|---|
| Classification | 96.0% |
| Reason for failure | 92.0% |
| Outcome | 88.0% |
| Peptide | 84.0% |
| Delivery mode | 80.0% |

## Key Files

| Path | Purpose |
|---|---|
| `CONTINUATION_PLAN.md` | Step-by-step pickup instructions for next session |
| `results/edam.db` | EDAM learning database |
| `results/jobs/{job_id}.json` | Job status files |
| `results/annotations/{job_id}/{nct_id}.json` | Per-trial annotation results |
| `results/research/{job_id}/{nct_id}.json` | Cached research per job |
| `results/json/{job_id}.json` | Consolidated output (completed jobs only) |
| `results/review_queue.json` | Flagged items for manual review |
| `results/batch_a_analysis.md` | Batch A concordance analysis |
| `scripts/human_annotated_ncts.txt` | All 964 NCTs with human annotations |
| `scripts/fast_learning_batch_50.txt` | Batches A+B NCTs (50) |
| `app/services/memory/self_audit.py` | Self-audit (v10: searches reasoning) |
| `agents/annotation/delivery_mode.py` | v10: expanded keywords, 14B, all-source |
| `agents/annotation/classification.py` | v10: _parse_value fix |
| `agents/research/clinical_protocol.py` | v10: detailedDescription + armGroups |
