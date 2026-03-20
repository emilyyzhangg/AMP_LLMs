# EDAM Learning Run Plan (Revised)

## Why the original plan was wrong

The original plan called for running the same 25 NCTs 3-6 times to bootstrap EDAM through stability tracking. This doesn't work well because:

1. **Temperature is 0.1.** The pipeline is nearly deterministic. Re-running the same NCTs produces ~95% identical results. Stability tracking just confirms "same input → same output" — that's not learning.
2. **Self-audit is the highest-value loop.** It catches evidence contradictions (FDA says "INTRAVENOUS", agent says "Other/Unspecified") on the FIRST run. It doesn't need re-runs.
3. **Re-runs waste compute.** Each batch takes ~3 hours. Running 25 NCTs 3 times uses 9 hours that could annotate 75 new NCTs instead.

## Revised approach: forward progress with self-audit

Instead of re-running the same NCTs, move forward through all 964 in batches. Self-audit generates corrections after each batch. EDAM guidance compounds batch-over-batch.

## What's already done

| Batch | Job ID | NCTs | Status | EDAM corrections |
|---|---|---|---|---|
| A | c7e666682865 | 25 (richest) | Complete | 0 (self-audit not in this commit) |
| B | ae1ece9d4e0a | 25 (next richest) | Complete | 0 (no overlap, self-audit not active) |
| A repeat | 5d207b30f11c | same 25 as A | Running | First self-audit run — expect corrections |

## Plan going forward

### Phase 1: Complete the 964 human-annotated NCTs

After the A repeat finishes (with self-audit generating its first corrections):

```
Batch C: ~200 NCTs  (~24 hours)  — EDAM guidance from A-repeat self-audit corrections
Batch D: ~200 NCTs  (~24 hours)  — EDAM guidance from A-repeat + C corrections
Batch E: ~200 NCTs  (~24 hours)  — compounding corrections
Batch F: ~164 NCTs  (~20 hours)  — remaining NCTs, richest EDAM guidance
```

**What EDAM does each batch:**
- Self-audit scans ALL trials for evidence contradictions → corrections stored with citations
- Corrections from prior batches appear as guidance in future annotation prompts
- Prompt optimization fires after batch D (every 3rd job) — first variant proposals
- Self-review handles any flagged items

**Total: ~92 hours (3.8 days) for remaining 914 NCTs in 4-5 batches.**

### Phase 2: Measure concordance on all 964

```bash
.venv/bin/python scripts/concordance_jobs.py
```

Compare: Agent vs R1, Agent vs R2, R1 vs R2 baseline across all 964 NCTs.

### Phase 3: Re-annotate ALL 964 with full EDAM learning

After Phase 1+2, EDAM has corrections from 964 trials. Now re-run the entire set:
- Every annotation gets EDAM guidance (corrections, exemplars, evolved prompts)
- Compare Phase 3 concordance vs Phase 1 — this is the measured improvement

### Phase 4: Annotate the 884 unannotated NCTs

Agent-only, no human counterpart. Grounded by EDAM learning from 964 validated trials.

## What to do RIGHT NOW

After job `5d207b30f11c` completes:

**1. Check if self-audit generated corrections:**
```bash
PROD="/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/amp_llm_v3/standalone modules/agent_annotate/results"
sqlite3 "$PROD/edam.db" "SELECT source, COUNT(*) FROM corrections GROUP BY source;"
sqlite3 "$PROD/edam.db" "SELECT nct_id, field_name, original_value, corrected_value, reflection FROM corrections LIMIT 10;"
```

**2. If corrections exist → submit batch C (next 200 NCTs):**
```bash
cd "standalone modules/agent_annotate"
# Extract NCTs not yet annotated (exclude first 50)
comm -23 scripts/human_annotated_ncts.txt <(sort scripts/fast_learning_batch_50.txt) | head -200 > /tmp/batch_c.txt
NCTS=$(cat /tmp/batch_c.txt | python3 -c "import sys,json; print(json.dumps(sys.stdin.read().strip().split()))")
curl -X POST http://localhost:8005/api/jobs -H "Content-Type: application/json" -d "{\"nct_ids\": $NCTS}"
```

**3. If no corrections → investigate why self-audit didn't fire:**
Check the prod logs for EDAM self-audit output:
```bash
grep "self-audit" "$PROD/../logs/agent_annotate.log" | tail -20
```

## Key files
- `scripts/human_annotated_ncts.txt` — all 964 NCTs
- `scripts/fast_learning_batch_25.txt` — batch A NCTs (25)
- `scripts/fast_learning_batch_50.txt` — batch A+B NCTs (50)
- `results/edam.db` — EDAM learning database
- `CONTINUATION_PLAN.md` — step-by-step pickup instructions
