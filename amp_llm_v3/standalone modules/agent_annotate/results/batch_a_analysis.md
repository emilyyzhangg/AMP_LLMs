# Batch A Analysis — Job c7e666682865

**Date:** 2026-03-19
**Commit:** 8d6f236 (v10 + EDAM)
**NCTs:** 25 (richest human-annotated — 4-5 fields filled by both R1 and R2)
**Duration:** 3.0 hours (435s/trial avg)
**Flagged:** 1/25 (4%) — NCT05361733 (peptide + delivery_mode)

## Concordance Results

| Field | vs | N | Agree% | κ | 95% CI | AC₁ | Interpretation |
|---|---|---|---|---|---|---|---|
| **Outcome** | **R1** | **25** | **80.0%** | **0.742** | **[0.545, 0.940]** | **0.770** | **Substantial** |
| **Outcome** | **R2** | **25** | **76.0%** | **0.691** | **[0.502, 0.881]** | **0.725** | **Substantial** |
| Classification | R1 | 25 | 92.0% | -0.020 | [-0.212, 0.172] | 0.917 | Prevalence paradox — AC₁ = 0.917 |
| Classification | R2 | 25 | 88.0% | -0.056 | [-0.423, 0.311] | 0.865 | Prevalence paradox — AC₁ = 0.865 |
| Delivery mode | R1 | 25 | 44.0% | 0.323 | [0.170, 0.476] | 0.388 | Fair |
| Delivery mode | R2 | 25 | 56.0% | 0.436 | [0.248, 0.625] | 0.498 | Moderate |
| Reason for failure | R1 | 25 | 56.0% | 0.396 | [0.207, 0.584] | 0.489 | Fair |
| Reason for failure | R2 | 25 | 56.0% | 0.431 | [0.261, 0.600] | 0.499 | Moderate |
| Peptide | R1 | 22 | 68.2% | 0.252 | [-0.025, 0.530] | 0.491 | Fair |
| Peptide | R2 | 12 | 50.0% | 0.000 | [0.000, 0.000] | 0.200 | Slight |

## Comparison vs Human Inter-Rater Baseline

| Field | Human R1 vs R2 | Agent vs R1 | Agent vs R2 | Agent exceeds humans? |
|---|---|---|---|---|
| **Outcome** | **55.6%** | **80.0%** | **76.0%** | **YES — by 20-24 points** |
| Classification | 91.6% | 92.0% | 88.0% | Matches (prevalence paradox) |
| Delivery mode | 68.2% | 44.0% | 56.0% | No — route specificity issue |
| Peptide | 48.4% | 68.2% | 50.0% | YES vs R1 (68.2% > 48.4%) |
| Reason for failure | 91.3% | 56.0% | 56.0% | No — but different comparison basis |

## Key Findings

### Outcome: MAJOR IMPROVEMENT
- κ = 0.742 vs R1, κ = 0.691 vs R2 — both "Substantial" agreement
- **This exceeds the human inter-rater baseline (55.6%) by 20+ percentage points**
- Previous best (v6-7): 72.7% agreement vs R1 — now 80.0%
- The two-pass design + v10 verification improvements are working

### Classification: Prevalence paradox (AC₁ tells the real story)
- Cohen's kappa is near 0 (meaningless due to 92% "Other" prevalence)
- AC₁ = 0.917 — "Almost Perfect" agreement
- 92% raw agreement — the agent and humans agree on classification

### Peptide: Improving but still has gaps
- 68.2% vs R1 (up from historical ~65-70%)
- Main pattern: agent says False, humans say True (7 cases)
- Need to investigate: are these monoclonal antibodies, nutritional formulas, or genuine peptides the agent is missing?

### Delivery mode: Persistent weakness
- Agent defaults to "Injection/Infusion - Other/Unspecified" too often
- Humans correctly specify IV, IM, SC from FDA labels and protocol text
- The agent isn't extracting specific routes from evidence — the delivery mode agent needs improvement

## EDAM Learning Status

- **125 experiences stored** (25 NCTs × 5 fields)
- **0 corrections** (no self-review corrections generated — only 1 flagged trial)
- **125 stability entries** (all score 1.0 — first run, nothing to compare against)
- **81 embeddings** generated
- **Epoch 1** established

## Next Steps (per CONTINUATION_PLAN.md)

1. Submit batch B (next 25 NCTs from fast_learning_batch_50.txt)
2. After batch B: compare concordance — EDAM guidance from batch A should show improvement
3. Investigate the 7 peptide False→True disagreements — is the definition too strict?
4. Investigate delivery mode "Other/Unspecified" pattern — agent needs to extract specific routes
