# EDAM Learning Run Plan

## Dataset

| Set | NCTs | Description |
|---|---|---|
| Human-annotated (at least 1 field filled) | **964** | Concordance target — agent must annotate to measure accuracy |
| Both R1 and R2 annotated | 849 | Strongest concordance (both replicates available) |
| Assigned but never annotated | 884 | Have metadata but zero annotation fields filled — agent-only |
| Agent already annotated (pre-v10) | 114 | From prior runs, 104 overlap with human set |
| **Remaining for Phase 1** | **~860** | 964 minus ~104 already done |

The Excel has 1,848 NCT rows total, but only **964 have any actual annotation**. The other 884 have metadata (title, status, conditions) but all 5 annotation fields are blank — the human reviewers were assigned these trials but never completed them.

## Goal

1. **Phase 1**: Agent annotates all 964 human-annotated NCTs → full concordance measurement
2. **Phase 2**: Measure concordance, identify gaps, EDAM learns from corrections
3. **Phase 3**: Re-annotate with EDAM guidance → measured improvement
4. **Phase 4**: Annotate the 884 unreviewed NCTs — agent-only, no human counterpart
5. **Target**: Agent accuracy exceeds human inter-rater reliability (R1 vs R2 baseline)

## Human Inter-Rater Baseline (the bar to beat)

| Field | R1 vs R2 Agreement | Both-filled N | Notes |
|---|---|---|---|
| Classification | 91.6% | 620 | High agreement but kappa ≈ 0 (prevalence paradox) |
| Delivery mode | 68.2% | 579 | Route specificity disagreements |
| **Outcome** | **55.6%** | **372** | **Weakest field — agent can exceed this** |
| Reason for failure | 91.3% | 46 | Small N, mostly blank-blank agreement |
| **Peptide** | **48.4%** | **62** | **8:1 ratio (R1=451 True, R2=56 True) — definitional disagreement** |

## Runtime Estimates

| Hardware | Per trial | 964 trials | 5 batches × ~200 |
|---|---|---|---|
| Mac Mini | ~450s | ~120 hours (5.0 days) | ~24h per batch |
| Server | ~350s | ~94 hours (3.9 days) | ~19h per batch |

## Phase 1: Full Human-Set Annotation (964 NCTs)

```bash
cd "standalone modules/agent_annotate"

# All 964 NCTs are in scripts/human_annotated_ncts.txt
# Submit in 5 batches of ~200:
.venv/bin/python -c "
import httpx
ncts = open('scripts/human_annotated_ncts.txt').read().strip().split('\n')
batch_size = 200
for i in range(0, len(ncts), batch_size):
    batch = ncts[i:i+batch_size]
    resp = httpx.post('http://localhost:9005/api/jobs',
        json={'nct_ids': batch}, timeout=30)
    print(f'Batch {i//batch_size + 1}: {resp.json().get(\"job_id\", \"error\")} ({len(batch)} NCTs)')
"
```

**EDAM accumulates learning across batches:**
- Batch 1: cold start, ~1,000 experiences stored, self-review on flagged items
- Batch 2: EDAM guidance from batch 1 corrections, ~2,000 total experiences
- Batch 3: prompt optimization fires (every 3rd job), first variant proposals
- Batch 4-5: full EDAM guidance with corrections, exemplars, evolved prompts

## Phase 2: Concordance Measurement

```bash
.venv/bin/python scripts/concordance_jobs.py
```

Produces: Agent vs R1, Agent vs R2, R1 vs R2, per-annotator breakdown (kappa + CI + AC₁).

**Decision point:** If agent concordance exceeds R1 vs R2 on outcome and peptide (the weakest human fields), proceed to Phase 3. If not, analyze error patterns and adjust.

## Phase 3: Re-Annotate with Full EDAM Learning

Re-run all 964 NCTs. EDAM guidance from Phase 1 (corrections, exemplars, evolved prompts) now informs every annotation. Compare Phase 3 concordance vs Phase 1 — this is the paper's improvement metric.

## Phase 4: Annotate Beyond the Human Set (884 NCTs)

The 884 NCTs that humans never annotated. The agent annotates these with EDAM guidance from 964 human-validated trials. No concordance measurement possible — these annotations stand on the agent's learned accuracy, with full citation traceability and confidence scores.

## Monitoring

```bash
# EDAM stats
sqlite3 results/edam.db "SELECT COUNT(*) as experiences FROM experiences;"
sqlite3 results/edam.db "SELECT source, COUNT(*) FROM corrections GROUP BY source;"
sqlite3 results/edam.db "SELECT field_name, ROUND(AVG(stability_score),2), COUNT(*) FROM stability_index GROUP BY field_name;"

# Review flagged trials in real-time during running jobs
# Pipeline view → click "Review" on flagged NCTs
```

## Files

- `scripts/human_annotated_ncts.txt` — 964 NCTs with actual human annotations
- `scripts/concordance_jobs.py` — Full concordance with per-annotator breakdown
- `scripts/edam_learning_cycle.py` — Automated calibration cycle (for 10-NCT testing)
- `scripts/stability_test.py` — 3x stability test
- `results/edam.db` — Learning database (persists across all runs)
