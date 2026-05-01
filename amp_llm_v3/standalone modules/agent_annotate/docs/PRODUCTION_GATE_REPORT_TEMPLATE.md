# Production Gate Certification Report — Template

**Status:** AWAITING JOB #101 RESULT (production gate in flight on prod, commit `2172018e`).
**Filled-in version posted:** `docs/PRODUCTION_GATE_REPORT.md` (created when Job #101 completes).

This template defines the exact structure the cron `cb95c3f1` will fill in when Job #101 (`826f2608ddd8`) completes. Pre-structuring here makes the post-gate write-up mechanical and avoids ad-hoc reporting that varies between cycles.

---

## 1. Headline

| Item | Value |
|---|---|
| Code commit | `2172018e` (v42.7.22 + v42.7.23) |
| Slice | `production_gate_v42_7_22.json` (239 NCTs from training_csv − test_batch) |
| Wall-clock | _TBD: e.g. 47h 12m_ |
| Errors | _TBD_ |
| Warnings | _TBD_ |
| Job ID | `826f2608ddd8` |
| Date completed | _TBD_ |

## 2. Per-field accuracy (95% CI half-width via Wald approximation)

> **Source of truth:** `bash scripts/heldout_analysis.sh 826f2608ddd8 51a6c2a308f8` §1 (canonical methodology — same fuzzy matching as `compare_jobs.py`). Do NOT use the strict-lower-bound numbers from `score_production_gate.py` §2 here; that script under-counts (e.g. RfF n=1 instead of n=22 because it doesn't credit blank-vs-blank). Use `score_production_gate.py` only for §3 (per-outcome-class breakdown) and Wald CI math.

| Field | Production target | Result | 95% CI | Status |
|---|---|---|---|---|
| classification | ≥95% | _N/N = X.X%_ | ±_X.X_pp | ✅ / ⚠️ / ❌ |
| peptide | ≥85% | _N/N = X.X%_ | ±_X.X_pp | ✅ / ⚠️ / ❌ |
| delivery_mode | ≥80% | _N/N = X.X%_ | ±_X.X_pp | ✅ / ⚠️ / ❌ |
| outcome | ≥65% | _N/N = X.X%_ | ±_X.X_pp | ✅ / ⚠️ / ❌ |
| sequence | ≥50% | _N/N = X.X%_ | ±_X.X_pp | ✅ / ⚠️ / ❌ |
| reason_for_failure | ≥95% | _N/N = X.X%_ | ±_X.X_pp | ✅ / ⚠️ / ❌ |

Note: each field's denominator is the count of NCTs in the slice that had GT consensus for THAT field (different per field; classification consensus is more common than reason_for_failure consensus per IMPROVEMENT_STRATEGY §1.2).

## 3. Outcome stratified by GT class

| GT outcome | n | hits | accuracy | notes |
|---|---|---|---|---|
| positive | _≤120_ | _TBD_ | _X.X%_ | bottleneck class — pos→unk is GT-quality ceiling |
| unknown | _≤77_ | _TBD_ | _X.X%_ | should be high; conservative agent rarely over-calls |
| terminated | _≤30_ | _TBD_ | _X.X%_ | first measurement at scale (untested in iteration cycles) |
| failed - completed trial | _≤13_ | _TBD_ | _X.X%_ | first measurement at scale |
| withdrawn | _≤10_ | _TBD_ | _X.X%_ | first measurement at scale |

## 4. Comparison to human inter-rater agreement

| Field | Human IRA (per IMPROVEMENT_STRATEGY §1.2) | Agent (Job #101) | Δ |
|---|---|---|---|
| classification | 91.6% | _X.X%_ | _+/- X.Xpp_ |
| peptide | 48.4% | _X.X%_ | _+/- X.Xpp_ |
| delivery_mode | 68.2% | _X.X%_ | _+/- X.Xpp_ |
| outcome | 55.6% | _X.X%_ | _+/- X.Xpp_ |
| reason_for_failure | 91.3% | _X.X%_ | _+/- X.Xpp_ |
| sequence | n/a (no IRA) | _X.X%_ | n/a |

**Conclusion:** _agent BEATS / MATCHES / TRAILS humans on N of 5 fields with comparable IRA data._

## 5. Production decision

> Bucket based on §2's heldout_analysis numbers (canonical), NOT score_production_gate's strict-lower-bound numbers. Per CONTINUATION_PLAN's per-field targets:

- **SHIP** (recommend full-corpus annotation): _list of fields meeting target_
- **ACCEPT with CI bounds** (GT-quality ceiling): _list of fields in 55-65% gray zone_
- **INVESTIGATE** (regression or well-below target): _list of fields below 55% on outcome OR substantial regression_

**Final decision:** _SHIP / SHIP-WITH-FLAG / INVESTIGATE_

## 6. Diagnostics

### 6.1 Cross-version comparison (fields that changed since Job #83 baseline)

_Auto-generated from `bash scripts/heldout_analysis.sh 826f2608ddd8 51a6c2a308f8 | head -25`_

### 6.2 Outcome miss patterns

_Auto-generated from `scripts/cross_job_miss_patterns.py 826f2608ddd8 --field outcome | tail -25`_

### 6.3 Evidence-grade distribution

_Auto-generated from `scripts/evidence_grade_miss_analysis.py 826f2608ddd8 --field outcome | tail -50`_

## 7. Methodology disclosure

- **Data source:** `docs/human_ground_truth_train_df.csv` (680 NCTs total). Production gate slice: 239 NCTs from training_csv − test_batch. The 50-NCT `fast_learning_batch_50.txt` test_batch reservation is excluded by API contract (TRAINING_NCTS = full_csv − test_batch).
- **Code commit:** `2172018e` (v42.7.0–v42.7.23 cumulative). Public via git history.
- **Hardware:** Mac Mini M-series, Ollama-hosted qwen3:14b, 19 research agents in parallel per trial.
- **Per-trial cost:** ~10-16 min (research + annotation + verification phases).
- **GT consensus rule:** R1==R2, OR only one annotator filled in (per `consensus()` function in `scripts/cross_job_miss_patterns.py`). Trials with R1≠R2 disagreement are excluded from per-field denominators.
- **Sequence scoring:** `sequences_match` set-containment (per `app/services/concordance_service.py:299`); GT sequences canonicalized to strip terminal -OH/-NH2 chemistry suffixes (v42.7.16) before set comparison.

## 8. Next steps

- ✅ **Production gate signed off** (this report) → start full-corpus annotation (`scripts/full_corpus_batch_1.json` + `_2.json`, ~4-7 days)
- ⚠️ **Outcome with CI bound:** users of the agent's outputs should treat outcome=Positive with confidence X% (CI ±Y%), and may filter to high-confidence subsets via `evidence_grade ∈ {db_confirmed, deterministic}` for downstream use
- 🚫 **DO NOT** continue v42.7.X iteration on outcome without new evidence sources — cross-job analysis confirmed pos→unk is the GT-quality ceiling, not a fixable v42.7 bug. Future improvement requires v42.8 architectural work (RxNorm/DrugBank resolver, sponsor press-release search, etc.).
