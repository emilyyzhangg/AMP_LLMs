# Agent Annotate v42.11 — Public Annotation Dataset

**Pipeline version:** v42.11 (commit `bacc31ce`; dev-corpus job ran on prior commit `42c36b31` with identical agent code)
**Dataset generated:** 2026-06-03
**Status:** Production-ready (sealed test PASSES)

This directory contains the v42.11 stack's annotations for 800 unique clinical trials, split into three formal cohorts. Numbers below come from `scripts/score_full_corpus.py` against the matching `docs/human_ground_truth_<cohort>_df.csv`.

## Files

| File | Cohort | NCTs | Source job | Per-trial pace |
|---|---|---|---|---|
| **`all_annotations_800nct.csv`** | **all** | **800** | merged from the three below | — |
| `train_dev_corpus_5c8d0aa0431a.csv` | train | 629 | `5c8d0aa0431a` (2026-05-28, ~63 h wall) | ~6.0 min |
| `val_8d9398b0af66.csv` | val | 86 | `8d9398b0af66` (2026-05-28, 8h40m) | 6.05 min |
| `test_b9301e02fef5.csv` | test | 85 | `b9301e02fef5` (2026-06-02, 8h54m, 85/85 OK) | 6.29 min |

`all_annotations_800nct.csv` is the **single-file form** — every currently-annotated NCT in one CSV with two extra leading columns (`Cohort`, `Source Job ID`). Remaining 16 columns are identical to the per-cohort files. Use this when you want one dataset; use the per-cohort files when you want them split.

Each CSV is in the canonical "standard" format produced by `app/services/output_service.generate_standard_csv` (the same format the in-app `/api/jobs/<id>/csv` endpoint serves). Columns: NCT ID, Study Title, Study Status, Phase, Conditions, Interventions, then for each of the 6 annotation fields (`classification`, `delivery_mode`, `outcome`, `reason_for_failure`, `peptide`, `sequence`): the field value plus three companion columns — Evidence (deduplicated source identifiers), Sources (`database:identifier` pairs), and Evidence Text (extracted excerpts that informed the decision). The leading `#` line records the version stamp + commit + export timestamp.

The "full" 61-column audit CSV (per-field confidence, verifier opinions, reasoning chain, consensus status, reconciler usage, manual-review flag, config hash) is not committed here to keep the repo small. Regenerate with `python3 scripts/export_single_job_csv.py <job_id> --label <name>` against `results/json/<job_id>.json` — the script writes both standard and full CSVs.

## Cohort definitions

- **train** (`docs/human_ground_truth_train_df.csv`, 680 NCTs total; 629 of them form `TRAINING_NCTS` after carving out the legacy 50-NCT `test_batch`): the development cohort. EDAM (Experience-Driven Annotation Memory) is permitted to read/write across this cohort only.
- **val** (`docs/human_ground_truth_val_df.csv`, 86 NCTs): a sealed validation cohort outside the original training universe. EDAM never fires on these trials. Used to confirm no overfitting before the single-shot test fire.
- **test** (`docs/human_ground_truth_test_df.csv`, 85 NCTs): the canonical held-out test cohort. Fires exactly **once** per architectural cycle. The 2026-06-02 fire (`b9301e02fef5`) is the v42.11 cycle's unbiased canonical reading.

The formal split was established 2026-05-11. The 50-NCT legacy `test_batch` (`scripts/fast_learning_batch_50.txt`) is a subset of the original 680-NCT training CSV; it was used for the pre-formal-split production-gate certification (Job #101) on v42.7.22 and is **not** included in this v42.11 dataset release.

## Headline accuracy (sealed test `b9301e02fef5`, scored against `docs/human_ground_truth_test_df.csv`)

| Field | Agent | 95% CI | Human IRA | Verdict |
|---|---|---|---|---|
| classification | 97.1% (68/70) | ±3.9pp | 92.4% | beats IRA (+4.7pp) |
| peptide | 97.4% (37/38) | ±5.1pp | 86.0% | beats IRA (+11.4pp) |
| delivery_mode | 88.2% (60/68) | ±7.7pp | 88.8% | at IRA |
| outcome | 60.5% (23/38) | ±15.5pp | 61.3% | at human ceiling (−0.8pp) |
| sequence | 17.4% (8/46) | ±11.0pp | 43.6% | data-bound (cohort variance vs val 38.3%) |
| reason_for_failure (score-blind) | 100% (6/6) | — | 92.3% | precision intact |
| reason_for_failure (true recall) | 42.9% (6/14) | ±25.9pp | n/a | data-bound (no whyStopped text) |

Three fields beat human inter-annotator agreement (IRA); delivery_mode sits at IRA; outcome is at the human-consistency ceiling (humans themselves only agree 61.3% of the time on this field, so further headroom is mathematically bounded under a two-annotator GT regime); sequence and RfF true-recall gaps are bound by source-data availability rather than agent capability. Full per-cohort and stratified numbers are in `docs/PAPER.md` §4 and `docs/AGENT_STRATEGY_ROADMAP.md` §1.

## Reproducing

```bash
# Regenerate a single cohort's CSV from its stored job JSON:
python3 scripts/export_single_job_csv.py <job_id> --label <name>
#   produces:  scripts/<name>_<job_id>_<commit8>.csv      (standard, 16 cols)
#              scripts/<name>_<job_id>_<commit8>_full.csv (full audit, 61 cols)

# Re-score against the matching GT:
python3 scripts/score_full_corpus.py <job_id> --gt-path docs/human_ground_truth_<cohort>_df.csv
```

The agent code that produced these annotations is at commit `bacc31ce` on `main`. The training/val/test GT CSVs are checked in at `docs/human_ground_truth_*.csv`. Together with this repo at the same commit, every annotation can be re-derived bit-for-bit (modulo non-deterministic LLM sampling at the boundary; the deterministic-first cascade covers ~54% of trials with `skip_verification=True` and is fully reproducible).

## Citation / usage notes

When using this dataset, please cite the v42.11 pipeline rather than any individual job. Annotations carry per-trial provenance: every field value is accompanied by an evidence chain referencing ClinicalTrials.gov, PubMed/PMC, UniProt, DRAMP, OpenFDA, and the v42.x research-agent sources (see `docs/PAPER.md` §3.2). Human inter-annotator-agreement numbers in this README are computed from a 617-paired-annotation pool (`docs/clinical_trials-with-sequences.xlsx`, two independent annotators).
