# Agent Annotate — Continuation Plan

**Last updated:** 2026-03-19 (post-batch A analysis)
**Current state:** Batch A COMPLETE. Results analyzed. Ready for batch B.

## What was done this session

### Code changes (all committed to both dev and main):
1. **v10 verification overhaul** — personas (conservative/evidence-strict/adversarial), dynamic confidence (High/Medium/Low), evidence budget parity, verifier upgrades (Mac Mini: gemma2:9b, qwen2.5:7b, phi4-mini:3.8b; Server: gemma2:27b, qwen2.5:32b, phi4:14b)
2. **Server premium model toggle** — `server_premium_model` in YAML (kimi-k2-thinking default, minimax-m2.7 option), drives classification + outcome + reconciler
3. **EDAM self-learning system** — 3 feedback loops (stability tracking, correction learning with self-review, prompt auto-optimization), SQLite + Ollama embeddings, hardware-aware profiles
4. **Peptide definition injection** — scientific definition (2-100 AA active drug) in annotator + verifier prompts
5. **Concordance statistical upgrades** — kappa CIs, Gwet's AC₁, prevalence/bias indices, per-annotator disaggregation
6. **High-confidence primary override** — primary confidence > 0.85 + verifier baseline → skip reconciler
7. **SerpAPI removed** — zero paid APIs in agent_annotate
8. **UI fixes** — cancelled job results saved, pipeline NCT status (OK/Review/Failed), resume button, real-time review during running jobs, latest-first sorting everywhere

### Batch files created:
- `scripts/fast_learning_batch_25.txt` — 25 NCTs with 4-5 fields filled by BOTH R1 and R2
- `scripts/fast_learning_batch_50.txt` — 50 richest NCTs (includes the 25 above)
- `scripts/human_annotated_ncts.txt` — all 964 NCTs with actual human annotations

## What to do next

### Batch A: COMPLETE (job c7e666682865)
- **25/25 trials completed** in 3.0 hours (435s/trial avg)
- **1/25 flagged** (4%) — NCT05361733 (peptide + delivery_mode)
- **EDAM:** 125 experiences, 81 embeddings, 0 corrections (only 1 flagged trial), epoch 1
- **Full analysis:** `results/batch_a_analysis.md`

**Key results:**
- **Outcome: κ=0.742 vs R1 (Substantial) — EXCEEDS human baseline of 55.6%**
- Classification: AC₁=0.917 (kappa paradox — 92% "Other")
- Peptide: 68.2% vs R1 — improving but agent too strict on False
- Delivery mode: 44% vs R1 — agent defaults to "Other/Unspecified" too often

### Next: Submit batch B (next 25 richest NCTs)
```bash
# The fast_learning_batch_50.txt has 50 NCTs — batch A was the first 25
# Extract NCTs 26-50:
tail -25 scripts/fast_learning_batch_50.txt > /tmp/batch_b.txt
NCTS=$(cat /tmp/batch_b.txt | python3 -c "import sys,json; print(json.dumps(sys.stdin.read().strip().split()))")
curl -X POST http://localhost:8005/api/jobs \
  -H "Content-Type: application/json" \
  -d "{\"nct_ids\": $NCTS}"
```

### After batches A+B complete (50 NCTs, ~6 hours total):

**Step 5: Measure concordance improvement**
- Compare batch A (no EDAM guidance) vs batch B (EDAM guidance from A)
- If kappa improved → proceed to larger batches
- If not → check EDAM DB for corrections, verify self-review is working

**Step 6: Submit remaining NCTs in larger batches**
```bash
# All 964 human-annotated NCTs minus the 50 already done:
comm -23 scripts/human_annotated_ncts.txt scripts/fast_learning_batch_50.txt > /tmp/remaining.txt
wc -l /tmp/remaining.txt  # Should be ~914

# Submit in batches of 200:
python3 -c "
import httpx, json
ncts = open('/tmp/remaining.txt').read().strip().split('\n')
batch_size = 200
for i in range(0, len(ncts), batch_size):
    batch = ncts[i:i+batch_size]
    # Wait for previous batch to complete before submitting next
    resp = httpx.post('http://localhost:8005/api/jobs',
        json={'nct_ids': batch}, timeout=30)
    print(f'Batch: {resp.json().get(\"job_id\", \"error\")} ({len(batch)} NCTs)')
    break  # Submit one at a time, run next after it completes
"
```

### After all 964 NCTs annotated (~5 days):

**Step 7: Full concordance analysis**
```bash
.venv/bin/python scripts/concordance_jobs.py
# Update JOB_FILES list to include all completed job JSONs
```

**Step 8: Decision — re-annotate or proceed?**
- If agent concordance exceeds R1 vs R2 on outcome (55.6%) and peptide (48.4%) → proceed to Phase 4
- If not → analyze error patterns, check EDAM corrections, potentially adjust prompts

**Step 9: Annotate the 884 never-annotated NCTs (Phase 4)**
```bash
# These NCTs have metadata but no human annotations
# Extract from Excel: rows with NCT ID but no filled annotation fields
# Agent annotates with full EDAM guidance from 964 human-validated trials
```

## Key file locations
- **Prod results:** wherever the prod service writes (check prod plist for working directory)
- **Dev results:** `standalone modules/agent_annotate/results/`
- **EDAM database:** `results/edam.db` (one per environment)
- **Batch files:** `scripts/fast_learning_batch_25.txt`, `scripts/fast_learning_batch_50.txt`, `scripts/human_annotated_ncts.txt`
- **Learning plan:** `LEARNING_RUN_PLAN.md`
- **This file:** `CONTINUATION_PLAN.md`

## Important notes for the next Claude session
- The autoupdater pulls from main every 30 seconds — all code changes must be pushed to main
- EDAM is non-fatal: if it errors, the pipeline still runs normally
- The `nomic-embed-text` model needs to be available in Ollama for EDAM embeddings (auto-pulled on first use)
- Review flagged items in real-time at `http://localhost:8005/agent-annotate/review?job_id=c7e666682865`
- The human annotation Excel is at `dev-llm.amphoraxe.ca/docs/clinical_trials-with-sequences.xlsx`
