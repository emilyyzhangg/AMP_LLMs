# EDAM Learning Run Plan

## Prerequisites
- Job `a7cd7d71813b` (100-trial batch) was at 59/100 when service stopped
- It can be resumed after v10 code deploys: `POST /api/jobs/a7cd7d71813b/resume?force=true`
- Or start fresh — the research cache (Phase 1) is preserved on disk

## Option A: Resume the 100-trial job first, then run EDAM
```bash
# 1. Service restarts automatically via autoupdater (pulls from main)
# 2. Resume the interrupted job
curl -X POST http://localhost:9005/api/jobs/a7cd7d71813b/resume?force=true

# 3. Once complete, run the full EDAM learning cycle
cd "standalone modules/agent_annotate"
.venv/bin/python scripts/edam_learning_cycle.py --wait-for a7cd7d71813b
```

## Option B: Skip the old job, start fresh with EDAM
```bash
cd "standalone modules/agent_annotate"
.venv/bin/python scripts/edam_learning_cycle.py
```

## What the learning cycle does

### Phase 1: Calibration (3 runs × 10 NCTs = ~2.5 hours)
- Same 10 NCTs run 3 times independently
- EDAM stores all experiences, computes first stability index
- Self-review corrects flagged items after each run
- **Result:** Baseline stability data for 50 (NCT, field) pairs

### Phase 2: Compounding (3 runs × 10 NCTs = ~2.5 hours)
- Same 10 NCTs again, but now with EDAM guidance active
- Corrections from Phase 1 appear in annotation prompts
- Stability exemplars used as few-shot examples
- First prompt optimization pass fires after run 6
- **Result:** Measurable improvement in flagging rate and stability

### Phase 3: Transfer (1 run × 10 NCTs = ~1.2 hours)
- Default: same calibration set (provide --full-batch-file for 100+ NCTs)
- Learning from Phases 1-2 transfers via EDAM guidance
- **Result:** Tests whether learning generalizes

### Phase 4: Convergence (1 run × 10 NCTs = ~1.2 hours)
- Re-run calibration set to measure improvement vs Phase 1
- Compare stability scores, flagging rates, correction counts
- **Result:** The paper's primary improvement metric

## Total estimated time: ~7.5 hours (Mac Mini, sequential)

## Calibration NCT set (10 trials)
```
NCT00004984    NCT00001827    NCT00002428    NCT01718834    NCT00000798
NCT00000886    NCT00004358    NCT01652573    NCT00000391    NCT00000435
```

## Monitoring during runs
```bash
# Check EDAM memory growth
sqlite3 results/edam.db "SELECT * FROM config_epochs;"
sqlite3 results/edam.db "SELECT field_name, COUNT(*), ROUND(AVG(stability_score),2) FROM stability_index GROUP BY field_name;"
sqlite3 results/edam.db "SELECT source, COUNT(*) FROM corrections GROUP BY source;"

# Check job progress
curl -s http://localhost:9005/api/jobs | python3 -m json.tool
```

## After the cycle completes
1. Compare Phase 1 vs Phase 4 stability scores
2. Check EDAM database stats: `sqlite3 results/edam.db "SELECT * FROM prompt_variants;"`
3. Run concordance against human annotations (if available)
4. Consider running a larger batch (100+ NCTs) with `--full-batch-file`

## Expanding to larger batches
```bash
# Create a file with 100 NCT IDs
# Then run:
.venv/bin/python scripts/edam_learning_cycle.py \
    --calibration-runs 5 \
    --full-batch-file path/to/ncts_100.txt \
    --phases 1,2,3,4
```
