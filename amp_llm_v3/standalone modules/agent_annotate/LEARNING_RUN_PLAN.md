# EDAM Learning Run Plan (Revised 2026-03-20)

## Current state

| Batch | Job ID | NCTs | Status | EDAM corrections | Agent version |
|---|---|---|---|---|---|
| A | c7e666682865 | 25 (richest) | Complete | 0 | v9 (8B delivery, no detailedDesc) |
| B | ae1ece9d4e0a | 25 (next richest) | Complete | 0 | v9 |
| A repeat | 5d207b30f11c | same 25 as A | Complete | 0 | v9 |
| C | 49ac8fdd9e90 | 200 | Running (~32/200) | N/A | v9 |

### v10 agent fix pushed to dev (2026-03-20)

Delivery mode and classification agents were updated on `dev` branch (commit 143758ef).
Prod is still on `main` running batch C with old v9 agents.

## Why EDAM self-audit generated 0 corrections

**Root cause identified:** Self-audit searches citation snippet text for route keywords (e.g., "intravenous"). But the route info the LLM finds often comes from:

1. **Literature abstracts not captured in snippets** — The literature agent stores truncated title/author/journal snippets. When the LLM reads the full evidence text during Pass 1, it finds "administered intravenously" in the abstract, but the citation snippet only has the title. Self-audit can't see what the LLM saw.

2. **Arm group descriptions not extracted** — ClinicalTrials.gov arm descriptions often contain explicit routes ("Rituximab 375mg/m2 IV") but clinical_protocol.py didn't extract them as citations until v10.

3. **Detailed descriptions not extracted** — Same issue. Fixed in v10.

**Result:** Self-audit's evidence_text is a subset of what the LLM actually processes. The keywords exist in the raw evidence but not in the structured citation snippets that self-audit can search.

**Fix required:** Self-audit needs to also search the LLM's Pass 1 output (stored in `annotations[].reasoning`) for route keywords. If Pass 1 extracted "Most Specific Route: intravenous" but Pass 2 output "Other/Unspecified", that's an auditable contradiction within the agent's own output, not just evidence vs output. See "Self-audit enhancement" below.

## Why the original EDAM assumptions were wrong

1. **"Self-audit catches evidence contradictions on first run"** — FALSE. Self-audit finds 0 corrections because citation snippets don't contain the route keywords. The contradictions exist but self-audit can't see them.

2. **"Forward progress with self-audit generates compounding corrections"** — FALSE without fixing self-audit. Batches B, C, D would all generate 0 corrections. EDAM guidance would remain empty.

3. **"Re-runs waste compute"** — PARTIALLY TRUE. Re-runs with identical code are wasteful. But re-runs AFTER agent improvements (v9 → v10) are the most valuable thing EDAM can do — they generate corrections by comparing old vs new values for the same NCT.

4. **"EDAM self-review handles flagged items"** — Self-review (Loop 2) only fires for trials flagged by verification. Batch A had 1/25 flagged, batch B had 3/25 flagged. Most of the delivery_mode errors were NOT flagged because the verifiers also don't have route keywords in their evidence.

## Revised plan

### Phase 1: Let batch C finish on prod (v9)

**ETA:** ~23 hours remaining from 2026-03-20 10:00.

Batch C is valuable despite using old agents because:
- The 4 non-delivery-mode fields (classification, peptide, outcome, reason_for_failure) are unaffected by the v10 delivery_mode changes
- The research data is cached to disk per-trial (takes ~5 min/trial to research)
- EDAM gets 200×5 = 1000 experiences for the stability tracker
- The delivery_mode values (even if ~45% wrong) become baseline for Phase 2 comparison

**Do NOT stop batch C.**

### Phase 1.5: Validate v10 on dev

While batch C runs on prod, test v10 on dev with 5-10 known-failing NCTs:

```bash
# Pick NCTs where delivery_mode was wrong in batch A
# NCT02624518, NCT02646475, NCT02665377, NCT03597282, NCT03697551 (all agent=Other/Unspec, human=IV)
# NCT00000886 (agent=Inj-Other, human=IM), NCT05361733 (agent=Inj-Other, human=Oral)
NCTS='["NCT02624518","NCT02646475","NCT02665377","NCT03597282","NCT03697551","NCT00000886","NCT05361733"]'
curl -X POST http://localhost:9005/api/jobs -H "Content-Type: application/json" -d "{\"nct_ids\": $NCTS}"
```

**Must delete dev cached research first** so clinical_protocol re-fetches with detailedDescription + armGroups:
```bash
DEV_RESEARCH="/Users/amphoraxe/Developer/amphoraxe/dev-llm.amphoraxe.ca/amp_llm_v3/standalone modules/agent_annotate/results/research"
for nct in NCT02624518 NCT02646475 NCT02665377 NCT03597282 NCT03697551 NCT00000886 NCT05361733; do
    rm -f "$DEV_RESEARCH/$nct.json"
done
```

Compare v10 results against v9 and human annotations. If delivery_mode concordance improves significantly → proceed to Phase 2.

### Phase 2: Merge v10 to main, re-run batch C's 200 NCTs

After batch C completes and v10 is validated on dev:

1. Merge dev → main (or cherry-pick the v10 commit)
2. Delete cached research for batch C's 200 NCTs (so clinical_protocol re-fetches with new citations):
   ```bash
   PROD_RESEARCH="/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/amp_llm_v3/standalone modules/agent_annotate/results/research"
   for nct in $(cat /path/to/batch_c_ncts.txt); do
       rm -f "$PROD_RESEARCH/$nct.json"
   done
   ```
3. Submit same 200 NCTs as new job on prod

**Why this generates EDAM corrections:** EDAM stability tracker compares the old run (v9) with the new run (v10) for each (NCT, field). Delivery_mode values that flip from "Other/Unspecified" to "IV" become instability flags. Self-audit (even in current form) may catch more because the new citations contain route keywords.

**Research cache note:** Only delete clinical_protocol research cache — literature, peptide_identity, etc. are unaffected by the v10 changes and don't need re-fetching. However, research is stored per-trial (all agents in one file), so the whole file must be deleted. Re-research takes ~5 min/trial but only clinical_protocol + OpenFDA do network calls; the other agents may also cache separately.

### Phase 2.5: Fix self-audit (critical for EDAM learning)

Self-audit needs to be enhanced to search **the agent's own Pass 1 output** (stored in annotation reasoning), not just citation snippets. This catches the common pattern:

> Pass 1: "Literature Route: administered intravenously (PMID:2872248)"
> Pass 2: "Delivery Mode: Injection/Infusion - Other/Unspecified"

The fix:
- In `self_audit.py._audit_delivery_mode()`, also extract and search the delivery_mode annotation's `reasoning` field
- Look for `"Most Specific Route: "` or `"Protocol Route: "` patterns from Pass 1 output
- If Pass 1 found a specific route but Pass 2 defaulted to Other/Unspecified, that's a contradiction → correction

This is the single highest-impact EDAM fix. Without it, self-audit will continue generating 0 corrections regardless of how many batches run.

### Phase 3: Continue with remaining ~714 NCTs

After Phase 2 re-run, EDAM should have:
- Stability data from 2 runs of 200 NCTs (v9 vs v10)
- Self-audit corrections (from the enhanced self-audit)
- Correction guidance injected into annotation prompts

Submit remaining NCTs in batches of 200:
```
Batch D: ~200 NCTs  (~24 hours)  — first batch with real EDAM corrections
Batch E: ~200 NCTs  (~24 hours)  — compounding corrections
Batch F: ~164 NCTs  (~20 hours)  — remaining NCTs
```

Prompt optimization fires every 3rd job. First optimization pass should be after batch D (the 6th total job).

### Phase 4: Full concordance on all 964

```bash
.venv/bin/python scripts/concordance_jobs.py
```

Compare: Agent vs R1, Agent vs R2, R1 vs R2 baseline across all 964 NCTs.
Break down by batch to see compounding EDAM improvement.

### Phase 5: Decision — re-annotate or proceed?

**If agent concordance exceeds human baselines on most fields:**
- Outcome: human R1 vs R2 = 55.6% → agent target: >70%
- Peptide: human R1 vs R2 = 48.4% → agent target: >65%
- Classification: AC₁ > 0.85
- Delivery mode: > 60% (most improved field from v10)

→ Proceed to annotate the 884 never-annotated NCTs (Phase 6)

**If not:** Analyze error patterns per field. Delivery mode may need a 3rd data source (e.g., DrugBank API for route info). Classification "Other" bias may need the deterministic known-AMP list expanded.

### Phase 6: Annotate 884 unannotated NCTs

Agent-only, no human counterpart. Full EDAM guidance from 964 validated trials.

## Self-audit enhancement (critical TODO)

**File:** `app/services/memory/self_audit.py`

Add a new check in `_audit_delivery_mode()`:

```python
def _audit_delivery_mode(self, nct_id, agent_value, evidence_lower, all_citations,
                          annotation_reasoning=""):
    """Check if evidence OR the agent's own Pass 1 output contains explicit route."""
    if agent_value not in _UNSPECIFIC_ROUTES:
        return None

    # EXISTING: Search citation snippets for route keywords
    # ... (current code) ...

    # NEW: Search the agent's own Pass 1 output for contradictions
    if annotation_reasoning:
        pass1_lower = annotation_reasoning.lower()
        # Check if Pass 1 extracted a specific route that Pass 2 ignored
        for keyword, correct_value in _ROUTE_EVIDENCE_MAP.items():
            if correct_value is None:
                continue
            if keyword in pass1_lower:
                return {
                    "field_name": "delivery_mode",
                    "original_value": agent_value,
                    "corrected_value": correct_value,
                    "reflection": (
                        f"Agent's own Pass 1 extraction found '{keyword}' "
                        f"but Pass 2 defaulted to '{agent_value}'. "
                        f"The model's extraction contradicts its own classification."
                    ),
                    "evidence_citations": [],
                }
```

Also update `audit_trial()` to pass annotation reasoning:
```python
dm_ann = ann_by_field.get("delivery_mode", {})
dm_reasoning = dm_ann.get("reasoning", "")
dm_correction = self._audit_delivery_mode(
    nct_id, final_by_field.get("delivery_mode", ""),
    evidence_lower, evidence_citations,
    annotation_reasoning=dm_reasoning,
)
```

## Key files

- `scripts/human_annotated_ncts.txt` — all 964 NCTs
- `scripts/fast_learning_batch_25.txt` — batch A NCTs (25)
- `scripts/fast_learning_batch_50.txt` — batch A+B NCTs (50)
- `results/edam.db` — EDAM learning database (375 experiences, 0 corrections, 125 stability entries)
- `CONTINUATION_PLAN.md` — step-by-step pickup instructions
- `app/services/memory/self_audit.py` — self-audit (needs enhancement, see above)
- `agents/annotation/delivery_mode.py` — v10 on dev, v9 on prod
- `agents/annotation/classification.py` — v10 _parse_value fix on dev
- `agents/research/clinical_protocol.py` — v10 detailedDescription + armGroups on dev

## Concordance summary (as of 2026-03-20, 79 unique NCTs)

### Agent vs R1 by batch

| Field | A+EDAM (MV, 25) | B (25) | C partial (30) |
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
