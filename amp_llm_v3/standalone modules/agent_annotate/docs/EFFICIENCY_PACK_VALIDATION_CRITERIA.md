# v42.6 Efficiency Pack — Validation Criteria

Written 2026-04-21 before Jobs #72/#73/#74 complete. Specifies the six signals to measure when analyzing the 3×100-NCT output batch, along with baselines from Job #71 (the Phase 6 cut-over run with efficiency flags OFF), success thresholds, and what each signal means if it misses.

**Purpose.** The efficiency pack ships six flags (five code, one doc). Jobs 72–74 are the first runs where all three accuracy-affecting flags are on simultaneously (`skip_legacy_when_atomic`, `deterministic_peptide_pregate`, `skip_amp_research_for_non_peptides`) plus the bioRxiv metadata fix. This document defines what has to be true of the output for the efficiency pack to be declared working.

## 1. Peptide pre-gate hit rate (Eff #2)

**Measure.** Count trials in jobs 72/73/74 whose `peptide` annotation has `model_name == "deterministic-pregate"` and `value == "False"`. Divide by total trials across the 300.

**Baseline (Job #71, all flags off).** 25/94 = 27% peptide=False trials, all via the legacy 2-pass LLM + 3 verifiers.

**Target.** 30–40% of trials gated by the deterministic pre-gate (value=False, model_name=`deterministic-pregate`). Remaining peptide=False trials would have gone through the LLM anyway because their `clinical_protocol` intervention type was ambiguous (Biological, or Drug with database hit).

**What a miss means.**
- **<20% gated** → pre-gate too restrictive. Inspect which intervention types / database hits are blocking gating. Most likely: a non-peptide database agent is producing false-positive hits, tripping the "no peptide DB hit" requirement.
- **>50% gated** → pre-gate too permissive. Risk: some peptide trials slip into the `False` cascade, losing all downstream annotation. Spot-check by comparing gated-trials' R1 peptide column to `False`.

**Analysis query.**
```python
gated = sum(
  1 for ann in all_annotations
  if ann["field_name"] == "peptide"
  and ann.get("model_name") == "deterministic-pregate"
  and ann.get("value") == "False"
)
```

## 2. `classification_legacy` absent from output (Eff #1)

**Measure.** Count trials in jobs 72/73/74 whose annotation JSON has a `classification_legacy` key. Compare to total peptide=True trials (the only trials where classification runs at all).

**Baseline (Job #71).** `classification_legacy` present on all 69 peptide=True trials (Phase 6 swap preserved legacy as shadow).

**Target.** **Zero** `classification_legacy` keys across all 300 trials. Same for `reason_for_failure_legacy`. If present, `skip_legacy_when_atomic` flag isn't being read or the orchestrator code path didn't take effect.

**What a miss means.**
- **Legacy field still present on some trials** → the efficiency flag flip didn't propagate. Either (a) service wasn't restarted after config flip, (b) the `step2_fields` filter in orchestrator.py:1487–1488 is broken, or (c) the prefer_atomic flag is off (check config_hash in health endpoint).
- **Primary classification now contains legacy reasoning** (`[Pass 1 extraction]` instead of `[ATOMIC-CLS`) → worse. Would mean the atomic agent didn't run and legacy filled the primary slot — swap logic inverted.

**Analysis query.**
```python
legacy_present = sum(
  1 for d in annotation_jsons
  if any(a["field_name"] == "classification_legacy" for a in d["annotations"])
)
```

## 3. AMP-specific research skipped on non-peptide trials (Eff #3)

**Measure.** For each trial, count how many of these research agents produced results: `dbaasp`, `apd`, `rcsb_pdb`, `pdbe`, `ebi_proteins`. Group by whether intervention is clearly non-peptide.

**Baseline (Job #71).** All 5 AMP-specific agents ran on all 94 trials regardless of intervention type (~20s wall time contribution per non-peptide trial).

**Target.** On trials where `_intervention_is_clearly_non_peptide()` returns True (Device, Procedure, Behavioral, Radiation, Dietary Supplement, Genetic, Other types), **zero** of the 5 AMP-specific agents should have entries in `research_results`. On Drug/Biological/mixed trials, they run normally.

**What a miss means.**
- **AMP agents ran on clearly non-peptide trials** → intervention-type classifier failed or flag not read. Safe failure (extra research is harmless, just slow).
- **AMP agents skipped on real peptide trials** → bug in `_intervention_is_clearly_non_peptide`. Dangerous: loses AMP classification signal. Cross-check AMP recall (#6 below) — if it drops, this is the cause.

**Analysis query.**
```python
amp_agents = {"dbaasp", "apd", "rcsb_pdb", "pdbe", "ebi_proteins"}
for d in annotation_jsons:
  int_types = collect_intervention_types(d)
  clearly_non_peptide = all(t in NON_PEPTIDE_TYPES for t in int_types)
  amp_ran = {r["agent_name"] for r in d["research_results"]} & amp_agents
  # Expect amp_ran == set() when clearly_non_peptide; expect amp_ran == amp_agents otherwise
```

## 4. bioRxiv hit rate jump (metadata fix)

**Measure.** Count trials whose `research_results` contains a `biorxiv` entry with at least one citation. Divide by total trials.

**Baseline.**
- Job #71 (broken metadata): 3/94 = 3%
- Direct probe on 29 Cat 1 NCTs with proper metadata: 12/29 = 41%

**Target.** **≥20%** of trials return at least one bioRxiv citation (lower than the 41% probe because probe was on known-rich NCTs). Drug-name-relevant hit rate should be **≥15%**.

**What a miss means.**
- **<10% hit rate** → metadata fix didn't reach the orchestrator's bioRxiv dispatch. Check that `_run_research` passes `metadata={"interventions": [...], "title": ...}` correctly (line ~1078). Also check the prefilter (Eff #5) isn't over-dropping.
- **0% hit rate** → bioRxiv agent isn't being called at all. Verify registration in `RESEARCH_AGENTS` + config `research_agents.biorxiv` entry.

**Analysis query.**
```python
bio_any = sum(
  1 for d in annotation_jsons
  for r in d["research_results"]
  if r["agent_name"] == "biorxiv" and len(r.get("citations") or []) > 0
)
bio_drug_relevant = sum(...)  # see Job #71 analysis script
```

## 5. outcome_atomic R8 floor (Cat 1 gap closure)

**Measure.** Among trials where `outcome_atomic.rule == "R8"` (fall-through to Unknown), count how many have `R1` ground truth of `positive` — these are the Cat 1 evidence-gap cases.

**Baseline (Job #71).** 46 trials fell to R8, 32 of those had R1=positive (~70% of R8 firings were Cat 1 gaps). Overall R8 agreement: 30%.

**Target.** If bioRxiv starts surfacing trial-specific preprints, some Cat 1 gaps should close — these trials would instead fire R1 (POSITIVE pub verdict). **Aspiration:** R8 fires on <40% of trials (vs Job #71's 46/94 = 49%). Realistic: small single-digit improvement given 300 NCTs and ~20% bioRxiv hit rate.

**What a miss means.**
- **No R8 reduction** → bioRxiv citations aren't reaching Tier 1b assessment. Likely: prefilter dropping too many, or `classify_pub_specificity` routing preprints to `general` (the atomic classifier's review-marker list may flag preprint language).
- **R8 reduction without accuracy gain** → R1/R2 fired on newly-surfaced preprints but their verdicts disagree with R1 ground truth. Means the preprints aren't the same ones R1 relied on. Not actionable — needs manual triage.

**Analysis query.**
```python
r8_cat1 = sum(
  1 for d in annotation_jsons
  if outcome_rule(d) == "R8" and r1_ground_truth(d) == "positive"
)
```

## 6. Classification / AMP recall hold

**Measure.** For the 300-NCT set, score `classification` (primary, atomic after cut-over) against R1 `Classification_ann1`. Compute overall accuracy and AMP recall (AMP true-positives / R1 AMP count).

**Baseline (Job #71).**
- classification overall: 93.3% (56/60 scoreable)
- AMP recall: 86% (6/7)

**Target.** Accuracy should **hold or improve** on the 3×100 set despite efficiency flags:
- classification overall ≥ 90%
- AMP recall ≥ 80% (sample will have more AMPs; recall should stay strong)

**What a miss means.**
- **AMP recall drops** → Eff #3 (AMP research skip) misclassified a peptide trial as non-peptide, losing DBAASP/APD hits that Tier 0 needed. Cross-check: the dropped AMPs should all have `deterministic-pregate` peptide=False. Fixable by adjusting `_intervention_is_clearly_non_peptide` (Drug type without database hit should stay AMBIGUOUS, not clearly non-peptide).
- **Overall accuracy drops** → any of the three efficiency flags regressed. Triage by turning flags off one at a time in a re-run.

**Analysis query.** Same `atomic_vs_r1.py` pattern used on Job #71.

## Reference: Wall-clock target

Job #71: 94 NCTs in 8h 27min → **324s/trial avg**.

Jobs 72/73/74 projection with efficiency pack: **~160–180s/trial avg** (40–50% reduction).

Total expected wall time for 3×100 = 300 trials: **~13.5–15 hours**. If actual is >20 hours, something is taking wrong path. If <10 hours, suspiciously fast — verify NCT counts and field counts match expectations.

## Failure rollback plan

If jobs 72–74 show any of these:
- **AMP recall drops >10pts**
- **Any efficiency flag mis-fires (signals #2 or #3 failed)**
- **Classification accuracy drops >5pts**

Then flip the offending flag back to false in `default_config.yaml` on dev, merge to main, service will pick up on next job. Record the regression in `LEARNING_RUN_PLAN.md` + `CONTINUATION_PLAN.md`.

## Report format (for when all 3 complete)

Auto-produced report should include:
- Headline: pass/fail on each of the 6 signals
- Per-signal measured vs target
- Aggregate accuracy table (all 6 fields vs R1, same shape as Job #71 analysis)
- Per-batch timing and peptide=False rate
- Notable atomic vs legacy disagreements (sampled)
- Any retries/errors

Saved under `results/annotations/<job_id>/` for each job and `results/analysis/v42_6_validation_YYYY_MM_DD.md` for the consolidated report.
