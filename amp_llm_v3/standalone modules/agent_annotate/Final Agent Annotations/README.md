# Final Agent Annotations — v42.11 Production-Ready Dataset

**Pipeline:** Agent Annotate v42.11 (Ollama-served local LLMs on a Mac Mini, 16 GB unified memory)
**Generated:** 2026-06-10
**Status:** Production-ready (sealed test cohort PASSES against human inter-annotator agreement)

This folder holds the final, human-legible-named CSVs covering every clinical trial the agent has annotated. All files share the same standard column schema (NCT ID + 5 study-metadata columns + 6 annotation fields, each with value / evidence / sources / evidence text — 30 columns total). Consolidated files prefix each row with two extra columns (`Cohort`, `Source Job ID`).

## What's here

### Per-cohort files (one CSV per cohort)

| File | Cohort | NCTs | Job ID | Wall time |
|---|---|---|---|---|
| `train_629_NCTs.csv` | train | 629 | `5c8d0aa0431a` | ~63 h |
| `validation_86_NCTs.csv` | validation | 86 | `8d9398b0af66` | 8h40m |
| `test_85_NCTs.csv` | test (sealed single-shot) | 85 | `b9301e02fef5` | 8h54m |
| `legacy_test_batch_50_NCTs.csv` | legacy test batch | 50 | `036fc5dea889` | 4h38m |
| `master_extension_994_NCTs_no_human_GT.csv` | master extension (no human GT) | 994 | `c74ce600868d` | 2h41m |

### Consolidated files (one CSV across multiple cohorts, with leading `Cohort` + `Source Job ID` columns)

| File | NCTs | Use when… |
|---|---|---|
| `ALL_consolidated__train_val_test__800_NCTs.csv` | 800 | …you want the formal 3-cohort cross-validation only |
| `ALL_consolidated__with_legacy_test_batch__850_NCTs.csv` | 850 | …you also want the 50-NCT legacy held-out cohort (still has human GT for scoring) |
| `ALL_consolidated__full_universe__1844_NCTs.csv` | 1844 | …you want every trial the agent annotated, including 994 with no human counterpart |

## Cohort definitions

- **train (629)** — development cohort. `TRAINING_NCTS` = original 680-NCT training CSV minus 50 legacy test_batch. EDAM (the self-learning layer) reads/writes here only.
- **validation (86)** — sealed cohort outside the original training universe. EDAM never fires. Used to confirm no overfitting before the single-shot test fire.
- **test (85)** — canonical held-out test cohort. Fires exactly **once** per architectural cycle. The 2026-06-02 fire is the v42.11 cycle's unbiased canonical reading.
- **legacy test batch (50)** — held out before the formal train/val/test split was established (2026-05-11). Subset of the original 680-NCT training CSV; v42.11 re-scored it on 2026-06-03.
- **master extension (994)** — trials from the annotator-master xlsx that have no human annotation (or partial annotation outside the formal cohorts). Pure agent output — cannot be scored against human IRA.

## Sealed scoring vs human inter-annotator agreement (IRA)

| Field | train | val | test | legacy_test_batch | Human IRA |
|---|---|---|---|---|---|
| classification | 96.4% | 97.1% | 97.1% | 88.6% | 92.4% |
| peptide | 89.4% | 97.5% | 97.4% | 97.9% | 86.0% |
| delivery_mode | 87.5% | 95.7% | 88.2% | 95.0% | 88.8% |
| outcome | 58.9% | 56.1% | 60.5% | 88.4% | 61.3% |
| sequence | 26.2% | 38.3% | 17.4% | 38.5% | 43.6% |
| reason_for_failure (score-blind) | 84.8% | 50% (n=2) | 100% | 80.0% | 92.3% |
| reason_for_failure (true recall) | 45.9% | 12.5% | 42.9% | 66.7% | n/a |

The master_extension cohort is not scored — no human GT exists for those 994 trials.

## LLM stack (all five jobs used identical configuration)

| Role | Ollama model | Architecture family | Parameters |
|---|---|---|---|
| Primary annotator (all 6 fields) | `qwen3:14b` | Alibaba Qwen 3 | 14.8 B |
| Verifier 1 (conservative) | `gemma3:12b` | Google Gemma 3 | 12.2 B |
| Verifier 2 (evidence-strict) | `qwen3:8b` | Alibaba Qwen 3 | 8.2 B |
| Verifier 3 (adversarial) | `llama3.1:8b` | Meta LLaMA 3.1 | 8.0 B |
| Reconciler (disputes only) | `qwen3:14b` | Alibaba Qwen 3 | 14.8 B |

All quantized at Q4_K_M. Embedding model `nomic-embed-text:latest` (274 MB) is used by EDAM for semantic similarity search over corrections and research evidence.

## Column schema

Every row carries:

- **Study metadata (6 columns):** `NCT ID`, `Study Title`, `Study Status`, `Phase`, `Conditions`, `Interventions`
- **Per-field (6 fields × 4 columns each = 24 columns):**
  - `<Field>` — the value (e.g., AMP / Other for Classification)
  - `<Field> Evidence` — deduplicated source identifiers (PMIDs, URLs, etc.)
  - `<Field> Sources` — `database:identifier` pairs
  - `<Field> Evidence Text` — extracted excerpts that informed the decision (truncated to 200 chars)

The six fields are: `Classification`, `Delivery Mode`, `Outcome`, `Reason for Failure`, `Peptide`, `Sequence`.

Consolidated files prepend `Cohort` and `Source Job ID` to that schema (32 columns total).

The leading `#` lines in every CSV record the version stamp, agent commit, and export timestamp. They are valid CSV comments — `pd.read_csv(..., comment='#')` skips them automatically.

## Reproducing

The per-cohort source job JSONs live under `results/json/<job_id>.json`. To regenerate any CSV:

```bash
python3 scripts/export_single_job_csv.py <job_id> --label <name>
```

This writes both the 16-column standard CSV (the format above) and a 61-column full audit CSV with per-field confidence, verifier opinions, reasoning chains, consensus status, reconciler usage, and manual-review flags. The full audit isn't committed here to keep the repo small.

The companion technical-form copies (under `scripts/dataset_v42_11/`) have been removed in favour of this folder.
