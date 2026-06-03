# Agent Annotate — User Guide

Publication-grade clinical trial annotation powered by a network of specialized AI agents with blind multi-model verification.

**Related documents:**
- `METHODOLOGY.md` — Complete technical methodology for scientific publication (every agent, check, and verification step described in full). §5.4.1 covers shadow mode.
- `IMPLEMENTATION_PLAN.md` — Development phases and roadmap
- `IMPROVEMENT_STRATEGY.md` — Accuracy improvement plan based on comparison with human annotations
- `ATOMIC_EVIDENCE_DECOMPOSITION.md` — v42 atomic architecture design (outcome, classification, failure_reason)
- `PERFORMANCE.md` — throughput tuning guide with the v42.6 efficiency flags, recommended configs for high-volume (10k–30k NCT) jobs, and infra-level parallelism recommendations
- `EFFICIENCY_PACK_VALIDATION_CRITERIA.md` — signal-by-signal success criteria for v42.6 throughput flags, with Job #71 baselines and failure rollback plan. Use when analyzing a job that has efficiency flags active.

## Shadow-mode fields (v42)

Annotation outputs may include `<field>_atomic` keys alongside the standard fields (for example, `outcome` and `outcome_atomic`). The `_atomic` values come from the v42 atomic evidence-decomposition pipeline running in parallel with the legacy agent. They are observability/A-B data — the legacy field remains authoritative for downstream consumers — until the per-field `prefer_atomic_*` config flag is flipped. See `METHODOLOGY.md §5.4.1` for the full semantics.

## v42.7 era (current, 2026-04-28)

- **19 research agents** = 15 prior + bioRxiv (v42 Phase 6) + SEC EDGAR sponsor disclosures (v42.7.0) + openFDA Drugs@FDA approvals (v42.7.0) + NIH RePORTER federal grants (v42.7.6). Each fires per-trial, contributes citations to the LLM-visible dossier, and may trigger structural overrides.
- **Outcome agent overrides:** vaccine-immunogenicity Positive override (v42.7.7) with pub-title-pattern alternative (v42.7.17); FDA-approved drug override gated on strong-efficacy keywords (v42.7.12); Failed override gated on terminal registry status (v42.7.14).
- **Publication classifier (v42.7.20):** `_classify_publication` defaults to `general` unless an explicit trial signal (NCT match, "phase X", "first-in-human", "clinical trial", "primary endpoint", "we report", etc.) is present in the title. Cleaner [TRIAL-SPECIFIC] tags so the LLM can trust them when applying Rule 7 condition (ii). Cross-job analysis showed v41b's "default to trial_specific" was systematically over-tagging field-review pubs (Job #98: typical trial saw 6-48 false trial_specific tags).
- **Delivery_mode relevance gate (v42.7.19):** ambiguous keywords (tablet/capsule) only fire on citations that mention an experimental intervention name. Addresses 6 distinct NCTs across Jobs #92/#95/#96/#97 with spurious-oral pattern from FDA Drugs / OpenAlex citations on similarly-named approved drugs.
- **Sequence dictionary expansions (v42.7.18 / .21 / .22):** `_KNOWN_SEQUENCES` extended for solnatide+aliases / io103 / apraglutide / cbx129801 / sartate / cgrp+aliases. Sequences-only — `_KNOWN_PEPTIDE_DRUGS` deliberately untouched.
- **Evidence grading:** every annotation carries an `evidence_grade` ∈ {db_confirmed, deterministic, pub_trial_specific, llm, inconclusive} (v42.7.1). Used by `scripts/commit_accuracy_report.py` for coverage × commit-accuracy stratification, and by `scripts/evidence_grade_miss_analysis.py` to surface which agent layer is failing.
- **Code-sync diagnostic:** `/api/diagnostics/code_sync` returns boot vs disk commit + active-job count (v42.7.5). `scripts/check_code_sync.sh` is the smoke-harness gate.
- **Held-out evaluation:** per-cycle held-out rotation. See `CONTINUATION_PLAN.md` for active slice + retired slices. `scripts/submit_holdout_validation.sh --check-sync` defaults to the active slice. `--milestone` flag triggers the 147-NCT validation tier (~24h, ±8pp CI half-width). Pool universe: 680 NCTs from `docs/human_ground_truth_train_df.csv` only.
- **Diagnostic tooling:** `scripts/heldout_analysis.sh` (7-section job report); `scripts/cross_job_miss_patterns.py` (cross-job pattern hunting); `scripts/evidence_grade_miss_analysis.py` (which-layer-is-failing diagnostic).

---

## Table of Contents

1. [How It Works](#1-how-it-works)
2. [Mandatory Evidence Thresholds](#2-mandatory-evidence-thresholds)
3. [Multi-Model Verification](#3-multi-model-verification)
4. [Source Citations](#4-source-citations)
5. [Configuration Reference](#5-configuration-reference)
6. [Interpreting Results](#6-interpreting-results)

---

## 1. How It Works

Agent Annotate replaces the single-prompt annotation approach with a network of specialized agents, each optimized for a specific task.

### Agent Architecture

```
                         +---------------+
                         |  Orchestrator |
                         +-------+-------+
                                 |
              +------------------+------------------+
              |                  |                   |
     +--------v--------+ +------v-------+ +---------v---------+
     | Research Agents  | |  Annotation  | |   Verification    |
     |   (parallel)     | |   Agents     | |     Agents        |
     +--------+---------+ +------+-------+ +---------+---------+
              |                  |                    |
     +----+---+--+----+   +-----+-----+       +------+------+
     |    |      |    |   | 5 field   |       | N models    |
     | CP | Lit  | PI |   | agents    |       | blind       |
     |    |      |    |   |           |       | verify      |
     +----+------+----+   +-----------+       +-------------+
      WC
```

**Phase 1 — Research** (parallel): Four specialized research agents gather data from their assigned sources:
- **Clinical Protocol Agent**: ClinicalTrials.gov + OpenFDA — trial design, interventions, status, safety
- **Literature Agent**: PubMed + PMC + PMC BioC — published findings, full-text, entity extraction
- **Peptide Identity Agent**: UniProt + DRAMP — peptide/protein identification, sequences
- **Web Context Agent**: DuckDuckGo — supplementary web context

**Phase 2 — Annotation** (parallel): Five annotation agents each handle one field:
- **Classification**: AMP or Other — identifies antimicrobial peptide trials
- **Delivery Mode**: 4 categories — Injection/Infusion, Oral, Topical, Other
- **Outcome**: Positive, Failed - completed trial, Terminated, Withdrawn, Active, Recruiting, Unknown — uses a **two-pass investigative strategy** (see below)
- **Reason for Failure**: Business Reason, Ineffective for purpose, Toxic/Unsafe, Due to covid, Recruitment issues, or empty — uses a **two-pass investigative strategy** (see below)
- **Peptide**: True or False

All values match the data validation rules in the human annotation Excel.

Each annotation agent receives only the research relevant to its field. If evidence is insufficient, it requests additional research from the orchestrator.

### Investigative Agents (Two-Pass Strategy)

The **Outcome** and **Reason for Failure** agents use a two-pass approach, designed from analysis of 617 human annotations that revealed single-pass agents frequently produce incorrect results for these fields.

**The problem:** ClinicalTrials.gov status is often stale or incomplete. A simple agent sees `overallStatus: UNKNOWN` and returns "Unknown" — but human annotators found 15+ UNKNOWN-status trials with positive results published in literature. Similarly, `whyStopped` is blank for COMPLETED trials, but humans found failure reasons in published papers for 49 out of 99 cases.

**Pass 1 — Fact Extraction:** The agent extracts structured facts from ALL evidence sources:
- Registry status and whyStopped from ClinicalTrials.gov
- Published results, adverse events, and findings from PubMed/PMC
- Signals of success, failure, toxicity, or recruitment problems
- Whether the trial appears to have failed at all

**Pass 2 — Determination:** Given all extracted facts, the agent makes its decision with explicit rules:
- Published literature **overrides** ClinicalTrials.gov status
- A trial with UNKNOWN status but positive published results → Positive (not Unknown)
- A trial with TERMINATED status but positive published results → Positive (not Terminated)
- A COMPLETED trial with no published results → Unknown (not Positive)
- A COMPLETED trial with negative results in a paper → Failed - completed trial, reason: Ineffective for purpose
- "Unknown" and empty are **last resorts**, not defaults

**Smart short-circuit:** The Reason for Failure agent skips Pass 2 entirely if Pass 1 determines the trial did not fail — saving an Ollama call for the ~80% of trials without a failure reason.

**Phase 3 — Verification** (sequential per field): Independent LLM models re-annotate each field blindly, then consensus is checked.

---

## 2. Mandatory Evidence Thresholds

Every annotation field has a minimum evidence requirement that **must** be met before the system will produce a final answer. This is the core mechanism that prevents guessing.

### How It Works

Each annotation agent evaluates its available evidence against two criteria:

| Criterion | What It Measures |
|-----------|-----------------|
| **Minimum Sources** | How many independent data sources corroborate the conclusion |
| **Minimum Quality Score** | A weighted score (0.0-1.0) reflecting the reliability and completeness of available data |

### Key Principle

**The system will NEVER guess.** If an annotation agent cannot meet its evidence thresholds after all available sources have been searched, the field is marked as **"Requires Manual Review"** with a detailed explanation of what was searched, what was found, and why it was insufficient.

### Default Thresholds

| Field | Min Sources | Min Quality Score | Rationale |
|-------|-------------|-------------------|-----------|
| Classification | 2 | 0.50 | Core claim — must have multiple corroborating sources |
| Delivery Mode | 2 | 0.50 | Usually well-documented in trial protocols |
| Outcome | 2 | 0.50 | Status + at least one corroborating source |
| Reason for Failure | 1 | 0.30 | Uses two-pass investigation; often requires published literature beyond whyStopped (49/99 human-annotated reasons came from trials where whyStopped was blank) |
| Peptide | 2 | 0.50 | Critical for AMP research — requires protein database confirmation |

### How Quality Scores Are Calculated

Quality scores use a two-layer weighting system:

**Layer 1 — Source Availability**: Each data source has a reliability weight.

| Source | Weight | Rationale |
|--------|--------|-----------|
| ClinicalTrials.gov | 0.40 | Primary authoritative source |
| PubMed | 0.15 | Peer-reviewed literature |
| UniProt | 0.15 | Authoritative protein database |
| PMC | 0.10 | Full-text access to published research |
| OpenFDA | 0.05 | Official drug safety data |
| DRAMP/DBAASP | 0.05 | Specialized AMP database |
| DuckDuckGo | 0.05 | Web context (variable reliability) |
| PMC BioC | 0.05 | Structured entity extraction |

**Layer 2 — Field Relevance**: Not all sources matter equally for every field. Field-specific weights adjust the score accordingly.

### Customizing Thresholds

Edit `config/default_config.yaml` under `evidence_thresholds`, or change via the Settings page in the UI.

---

## 3. Multi-Model Verification

Multi-model verification is a **blind peer review** built into the annotation pipeline.

### How It Works

1. The **primary annotator** (Model A) annotates a field using the full research data and produces an answer with cited evidence.
2. One or more **independent verifiers** (Models B, C, ...) receive ONLY the raw trial data — they never see Model A's answer or reasoning.
3. Each verifier independently annotates the same field.
4. A **consensus check** compares all answers:
   - **All agree** -> High-confidence result with all models' evidence chains.
   - **Disagreement** -> A **Reconciliation Agent** (larger model) examines all answers and evidence, resolves or flags for manual review.

### Configuring the Number of Verifiers

Edit `config/default_config.yaml` under `verification`, or use the Settings page:

```yaml
verification:
  num_verifiers: 3
  require_consensus: true
  consensus_threshold: 1.0  # 1.0 = unanimous

  models:
    - name: "primary"
      ollama_model: "llama3.1:8b"
      role: "annotator"
    - name: "verifier_1"
      ollama_model: "gemma3:12b"          # Conservative persona (v42 upgrade, same Gemma family)
    - name: "verifier_2"
      ollama_model: "qwen3:8b"            # Evidence-strict persona (v42 upgrade, same Qwen family)
    - name: "verifier_3"
      ollama_model: "phi4-mini:3.8b"      # Adversarial persona
    - name: "reconciliation"
      ollama_model: "qwen2.5:14b"
      role: "reconciler"
```

**To add a verifier**: Add an entry to `models` with `role: "verifier"` and update `num_verifiers`.

### Recommendations by Use Case

| Use Case | Verifiers | Consensus | Notes |
|----------|-----------|-----------|-------|
| **Journal publication** | 2-3 | Unanimous (1.0) | Maximum rigor |
| **Internal review** | 1 | Unanimous (1.0) | Good balance |
| **Exploratory screening** | 0 | N/A | Fastest, not for publication |

### Verification Personas

Each verifier applies a different cognitive approach to the same evidence:

- **Verifier 1 (Conservative):** Defaults to safest answer when evidence is ambiguous. Absence of evidence is not evidence of a result.
- **Verifier 2 (Evidence-strict):** Only answers based on directly citable facts. Acknowledges gaps explicitly.
- **Verifier 3 (Adversarial):** Actively challenges the most obvious interpretation. Looks for contradicting evidence.

### Dynamic Confidence

Verifiers self-assess their confidence as High (0.9), Medium (0.7), or Low (0.4). This feeds into the consensus system — a low-confidence verifier disagreement carries less weight than a high-confidence one.

### Server Hardware Upgrades

On server hardware (240+ GB RAM), the system automatically upgrades to stronger models:

| Role | Mac Mini | Server |
|---|---|---|
| Premium (classification, outcome, reconciler) | qwen2.5:14b | kimi-k2-thinking (configurable) |
| Verifier 1 | gemma3:12b | gemma2:27b |
| Verifier 2 | qwen3:8b | qwen2.5:32b |
| Verifier 3 | phi4-mini:3.8b | phi4:14b |

Toggle between `kimi-k2-thinking` and `minimax-m2.7` for the premium model via `server_premium_model` in the config. All models are auto-pulled from Ollama if not available locally.

---

## 4. Source Citations

Every annotation includes a complete evidence chain with traceable citations.

### Citation Format

Each annotation field in the output includes:

```
Field: [Value]
Evidence:
  - [Source Database] [Identifier]: "[Relevant excerpt]"
    Location: [Specific field/section where data was found]
Verified By:
  - [Model Name] ([Ollama Model ID]): Independently concluded [Value]
    Based on: [Source Database] [Identifier] — "[Key evidence]"
Confidence: [High/Medium/Low]
Quality Score: [0.00-1.00]
```

### What Gets Cited

| Source | Identifier Format | What Is Cited |
|--------|-------------------|---------------|
| ClinicalTrials.gov | NCT ID | Specific field paths (briefTitle, briefSummary, interventions, etc.) |
| PubMed | PMID | Title, abstract excerpts, MeSH terms |
| PMC | PMC ID | Full-text excerpts with section references |
| UniProt | Accession | Protein name, keywords, family, function |
| DBAASP/DRAMP | Entry ID | Peptide name, activity, sequence |
| OpenFDA | Application number | Drug name, route, adverse events |
| DuckDuckGo | URL | Page title, relevant excerpt |
| Google Scholar | DOI or URL | Publication title, authors, year, excerpt |

---

## 5. Configuration Reference

All configuration lives in `config/default_config.yaml` and is editable through the Settings UI.

### verification

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `num_verifiers` | int | 3 | Number of independent verification models |
| `require_consensus` | bool | true | Whether all verifiers must agree |
| `consensus_threshold` | float | 1.0 | Fraction of verifiers that must agree (0.0-1.0) |
| `models` | list | (see file) | Model definitions with name, ollama_model, and role |

### evidence_thresholds

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `[field].min_sources` | int | 1-2 | Minimum independent sources required |
| `[field].min_quality_score` | float | 0.3-0.5 | Minimum quality score (0.0-1.0) |

### orchestrator

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `max_retry_rounds` | int/null | null | Max research retry rounds (null = unlimited) |
| `parallel_research` | bool | true | Run research agents concurrently |
| `parallel_annotation` | bool | true | Run annotation agents concurrently |

### ollama

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `host` | string | localhost | Ollama server hostname |
| `port` | int | 11434 | Ollama server port |
| `timeout_seconds` | int | 600 | Request timeout |
| `temperature` | float | 0.10 | LLM temperature (lower = more deterministic) |

---

## 6. Interpreting Results

### Result Statuses

| Status | Meaning | Action Required |
|--------|---------|-----------------|
| **Verified** | All models agree, evidence thresholds met | None — ready for publication |
| **Requires Manual Review — Insufficient Evidence** | Evidence thresholds not met | Review evidence and annotate manually |
| **Requires Manual Review — Model Disagreement** | Verifiers disagreed | Review each model's reasoning |
| **Error** | Technical failure | Check logs, retry |

### Output Files

- **JSON** (primary): Complete audit trail at `results/json/{job_id}.json` — includes all research findings, annotation reasoning (with Pass 1/Pass 2 outputs for investigative agents), verification opinions, and manual review decisions
- **Standard CSV** (16 columns): NCT ID, Study Title, Study Status, Phase, Conditions, Interventions, then for each of the 5 annotation fields: the value + an evidence column with PMIDs, URLs, and database identifiers
- **Full CSV** (61 columns): Standard columns + per-field: confidence, evidence sources (database:identifier pairs), evidence URLs, reasoning chain, consensus status, final value, verifier opinions, reconciler usage, manual review flag + global: flagged_for_review, flag_reason, version, git_commit, config_hash, annotated_at

### Evidence Citations in CSV

Every annotation field includes a companion evidence column (e.g., `Classification Evidence`) containing deduplicated source identifiers:
- PubMed articles: `PMID:36191080`
- PMC full-text: `PMC:11773215`
- ClinicalTrials.gov: `https://clinicaltrials.gov/study/NCT06729606`
- UniProt entries: `uniprot:P01282`
- Web sources: full URL

The full CSV expands this with separate `{field}_evidence_sources` (database:identifier pairs) and `{field}_evidence_urls` columns, plus the model's `{field}_reasoning` chain-of-thought.

### Recency Principle

The agent queries live APIs at annotation time, so it always uses the latest available data. When multiple publications exist with conflicting conclusions, the most recent publication takes priority. This means:
- A trial that was "Recruiting" when humans annotated it may now be "Completed" with published results → the agent correctly annotates the current status
- Newer publications override older ones — if a 2024 paper found inconclusive results but a 2025 paper demonstrated efficacy, the outcome is "Positive"

### Annotation Field Values (matching human annotation Excel)

| Field | Valid Values |
|-------|-------------|
| Classification | AMP, Other |
| Delivery Mode | Injection/Infusion, Oral, Topical, Other |
| Outcome | Positive, Failed - completed trial, Terminated, Withdrawn, Active, Recruiting, Unknown |
| Reason for Failure | Business Reason, Ineffective for purpose, Toxic/Unsafe, Due to covid, Recruitment issues (empty if not applicable) |
| Peptide | TRUE, FALSE |

---

## 7. Known Limitations & Accuracy Notes

Based on comparison of agent output against human annotations (Replicates 1 & 2 in `clinical_trials-with-sequences.xlsx`):

### Classification: "AMP" Does Not Mean "Any Peptide"

AMP stands for **Antimicrobial Peptide**. The classification categories are:
- **AMP**: The intervention is an antimicrobial peptide (targets infection, wound healing, cancer, immunomodulation via antimicrobial mechanism)
- **Other**: Everything else — including peptides that are NOT antimicrobial (GLP-1 analogues, VIP, somatostatin analogues, GnRH analogues)

**Common agent error**: Classifying all peptides as AMP. VIP/Aviptadil for headaches is a peptide but NOT an AMP → should be "Other". Semaglutide for diabetes is a peptide but NOT an AMP → should be "Other". Only peptides with antimicrobial activity or that target pathogens qualify as AMP.

### Peptide: Nutritional Formulas vs Peptide Drugs

The agent sometimes misclassifies nutritional products containing hydrolyzed peptides as peptide therapeutics. The distinction:
- **True**: The active drug IS a peptide (colistin, semaglutide, VIP, StreptInCor vaccine)
- **False**: The product CONTAINS peptides as food ingredients (Kate Farm Peptide 1.5, hydrolyzed protein formulas)

Also note that large multi-subunit proteins and engineered protein scaffolds are NOT peptides, even if they contain peptide chains.

### Delivery Mode: Injection Subtype Guessing

Despite explicit instructions not to guess, the agent sometimes defaults to Intramuscular when the protocol just says "injection." If a specific subtype isn't explicitly stated in the trial protocol or FDA label, the correct answer is "Injection/Infusion - Other/Unspecified."

### Cross-Field Consistency

The agent currently annotates each field independently with no cross-validation. This can produce contradictions:
- Outcome = "Positive" with Reason for Failure = "Ineffective for purpose" (impossible)
- Peptide = "False" with Classification = "AMP" (impossible)

A post-annotation consistency check is planned (see `docs/IMPROVEMENT_STRATEGY.md`).

### Verification ≠ Correctness

All verifiers agreeing does not guarantee correctness — small models can unanimously agree on a wrong answer. The multi-model verification catches *inconsistency* across model families, not factual errors shared across all models. Always review flagged items and spot-check verified items.

### Fully Autonomous Design

Agent Annotate is designed to operate without a human counterpart. Human annotations (in `docs/clinical_trials-with-sequences.xlsx`) were used during development to evaluate accuracy and refine prompts, but they are **never used at runtime**. All agent decisions are based solely on live data from external APIs (ClinicalTrials.gov, PubMed, UniProt, FDA, web sources). This means the agent always uses the latest available data and is not constrained by the point-in-time snapshot of any human dataset.

---

## 8. Production deployment workflow (post-v42.7.23)

The validated agent on main commit `2172018e` (v42.7.23) is the production-ready stack. To go from "code ready" to "fully annotated 630-NCT publication output", run the following sequence (cost: ~5-7 days end-to-end on prod):

### 8.1 One-time: production gate certification (Job #101)
```bash
bash scripts/submit_holdout_validation.sh --production-gate --check-sync
# → submits 239-NCT slice (training_csv − test_batch), ETA ~42h
# When complete:
bash scripts/heldout_analysis.sh JOB_ID 51a6c2a308f8 | tail -100  # authoritative
python3 scripts/score_production_gate.py JOB_ID --write           # supplementary + decision template
# Decision rule:
#   outcome ≥65% AND no field regresses → SHIP
#   outcome 55-65% → ACCEPT WITH CI BOUND (GT-quality ceiling per cross-job analysis)
#   outcome <55% → INVESTIGATE before scaling up
```

### 8.1b Sealed validation + single-shot test (the canonical accuracy numbers)

The 86-NCT validation set (`scripts/validation_set_v1.json`) and 85-NCT test set (`scripts/test_set_v1.json`) are held-out cohorts outside the 629-NCT training universe. Both live in `ALL_GT_NCTS` but not `TRAINING_NCTS`, so EDAM corrections never fire on them — they stay sealed across runs. The GT CSVs (`docs/human_ground_truth_val_df.csv`, `docs/human_ground_truth_test_df.csv`) carry the **raw granular CT.gov labels** ("Recruiting", "Active, not recruiting", "Injection/Infusion - Subcutaneous/Intradermal", "IV", etc.), unlike the train GT which was pre-flattened. The scorer's `coarsen(field, value)` (added in `8d8c1f62`) handles this automatically — no preprocessing needed.

```bash
# Validation set — run after a development cycle to confirm the agent
# generalizes off-train. Iterate freely on the val number; it's allowed.
bash scripts/submit_holdout_validation.sh --validation-set --check-sync --test-batch
# Score:
python3 scripts/score_full_corpus.py <job_id> --gt-path docs/human_ground_truth_val_df.csv

# Test set — SINGLE SHOT. Fires once per architectural cycle; the result
# is the unbiased canonical accuracy number for the deployed code. The
# --test-set flag auto-sets allow_test_batch=true.
bash scripts/submit_holdout_validation.sh --test-set --check-sync
# Score:
python3 scripts/score_full_corpus.py <job_id> --gt-path docs/human_ground_truth_test_df.csv
```

ETA on prod: ~9h for either cohort. Both are submitted to the same `/api/jobs` endpoint with the same MAX_BATCH_SIZE budget as full-corpus.

**Canonical sealed-cohort numbers (v42.11, commit `bacc31ce`/`cd45dff2`):**

| Field | Val (86, `8d9398b0af66`) | Test (85, `b9301e02fef5`) | Human IRA | Verdict |
|---|---|---|---|---|
| classification | 97.1% (68/70) ±3.9pp | **97.1%** (68/70) ±3.9pp | 92.4% | ✅ identical, beats human (+4.7) |
| peptide | 97.5% (39/40) ±4.8pp | **97.4%** (37/38) ±5.1pp | 86.0% | ✅ matches val, beats human (+11.4) |
| delivery_mode | 95.7% (67/70) ±4.7pp | **88.2%** (60/68) ±7.7pp | 88.8% | ✅ at human IRA on test (CIs overlap val) |
| outcome | 56.1% (23/41) ±15.2pp | **60.5%** (23/38) ±15.5pp | 61.3% | ≈ human ceiling (test −0.8 vs IRA) |
| sequence | 38.3% (18/47) ±13.9pp | **17.4%** (8/46) ±11.0pp | 43.6% | data-bound; cohort variance |
| RfF score-blind | 50.0% (1/2, n=2 noise) | **100%** (6/6) | 92.3% | precision intact when emitted |
| RfF true recall | 12.5% (1/8) | **42.9%** (6/14) ±25.9pp | n/a | data-bound (registry stop-reason gap) |

Single-shot test PASSES → **production-ready**. No field shows overfitting to train; no field shows val→test degradation beyond cohort variance. Sequence + RfF-recall are bound by missing source data, not agent capability.

### 8.2 Full-corpus annotation (post-gate)
```bash
# PREFERRED: whole training corpus (629 unique scoreable NCTs) as ONE resumable
# job → one merged result to score directly (no merge step). ~63h on prod.
# (Requires MAX_BATCH_SIZE >= 629 in app/routers/jobs.py — currently 750.)
bash scripts/submit_holdout_validation.sh --full-corpus --check-sync

# ALTERNATIVE: two ~315-NCT halves (older flow; needs the merge step in 8.3)
bash scripts/submit_holdout_validation.sh --full-corpus-1 --check-sync
# Wait for batch 1 to complete, then:
bash scripts/submit_holdout_validation.sh --full-corpus-2 --check-sync
```

### 8.3 Export single-job CSV (preferred, post-2026-06)
```bash
# Export standard (16-col) + full (61-col) CSVs from a single completed job.
# Works for the single-job full-corpus flow AND the val/test sealed cohorts.
python3 scripts/export_single_job_csv.py <job_id> --label <name>
#   produces:  scripts/<name>_<job_id>_<commit8>.csv      (standard)
#              scripts/<name>_<job_id>_<commit8>_full.csv (full audit)
```

For the legacy two-batch flow (deprecated; use only if you split into 8.2 alternate path):
```bash
python3 scripts/merge_full_corpus_results.py JOB_ID_1 JOB_ID_2
python3 scripts/score_full_corpus.py --merged-json scripts/full_corpus_merged_<commit>.json
```

### 8.4 Publication outputs (v42.11)
The canonical publication-ready dataset lives at **`scripts/dataset_v42_11/`** with one CSV per cohort:
- `train_dev_corpus_5c8d0aa0431a.csv` — 629 NCTs (job `5c8d0aa0431a`, ~63h on prod)
- `val_8d9398b0af66.csv` — 86 NCTs (sealed validation, PASSES)
- `test_b9301e02fef5.csv` — 85 NCTs (single-shot test, PASSES → production-ready)
- `README.md` — cohort definitions, per-field headline accuracy, reproduction instructions

Each CSV is the canonical 16-col standard format (NCT ID, study metadata, then 6 annotation fields × {value, evidence, sources, evidence text}); regenerate with `scripts/export_single_job_csv.py`. The 61-col full audit (per-field confidence, verifier opinions, reasoning chain, consensus status, reconciler usage, manual-review flag, config hash) is not committed but is one command away via the same script.

Companion docs for paper Methods:
- `docs/PAPER.md` — full publication paper (v42.11 rewrite, 2026-06-03)
- `docs/AGENT_STRATEGY_ROADMAP.md` §1.3 — sealed test results in roadmap form
- `docs/PRODUCTION_GATE_REPORT.md` (historical, v42.7.22 production gate)
- `docs/PRODUCTION_GATE_REPORT_TEMPLATE.md` (methodology section template)

### 8.5 What to publish
| Claim | Source | Caveat |
|---|---|---|
| Per-field accuracy on test | `PAPER.md` §4.4 + `dataset_v42_11/README.md` | ±3.9pp to ±25.9pp CIs per field; 85-NCT sealed cohort |
| Beats human inter-rater agreement | `PAPER.md` §4.5 vs-IRA table | True for classification (+4.7pp), peptide (+11.4pp); delivery at IRA; outcome at human ceiling (−0.8pp) |
| Annotation dataset | `scripts/dataset_v42_11/*.csv` | 800 unique NCTs (629 train + 86 val + 85 test); evidence-grade column in full CSV |
| Methodology | `PAPER.md` §3 | Reproducible from main commit `bacc31ce` + `docs/human_ground_truth_*.csv` |

For downstream consumers wanting only high-confidence annotations: regenerate the full CSV and filter to `evidence_grade ∈ {db_confirmed, deterministic}` (per `app/models/annotation.py`).

---

## 9. Maintenance Scripts

### 9.0 Standalone agent evaluation (test a single agent WITHOUT a full run)

Replay one annotation agent against the **cached research** already saved from a
past job (`results/research/<job_id>/<nct>.json`) and score it against ground
truth. Skips the full pipeline, verification, and the other five fields — so you
iterate one agent in seconds-to-minutes instead of a ~7.6 min/trial full run.

```bash
# Deterministic peptide anchor only — INSTANT, no LLM. Reports anchor coverage,
# precision, and how many trials defer to the LLM.
python3 scripts/eval_peptide.py <research_job_id> [--errors]

# Any single agent (runs its real deterministic + LLM logic) on cached research.
# Cross-field deps (peptide_result/classification_result/outcome_result) are
# injected from ground truth so the agent is tested with correct upstream inputs.
python3 scripts/eval_agent.py <field> <research_job_id> [--limit N] [--errors]
#   field ∈ peptide | classification | delivery_mode | outcome |
#           reason_for_failure | sequence
```

Notes: `eval_agent.py` does NOT apply the orchestrator's post-annotation overrides
or verification, so it measures the agent's own output. It uses Ollama for fields
with an LLM step — don't run it while a production job is annotating (they contend
for the single loaded model). Use a recent 315-trial research job (e.g.
`c7ca38f92f6b`) for the fullest coverage.

### 9.0a export_single_job_csv.py

Exports a completed single-job result to standard (16-col) + full (61-col) CSVs. Use for the v42.11 single-job full-corpus flow and the val/test sealed cohorts; the legacy `merge_full_corpus_results.py` is only for the older two-batch flow. Outputs land in `scripts/` with the naming pattern `<label>_<job_id>_<commit8>{,_full}.csv`. The v42.11 publication-ready dataset at `scripts/dataset_v42_11/` was produced with this script — see that directory's `README.md` for the full provenance.

### 8.1 retroactive_fix.py

Applies expanded value normalization rules to completed annotation jobs. This script is used when normalization logic is updated (e.g., new verifier parsing patterns are discovered) and previously completed jobs need to be re-processed with the improved rules.

**What it does:**
1. Reads stored verifier opinions for each trial in the target job(s)
2. Applies the current normalization rules (field-aware: different rules per field)
3. Recalculates consensus based on normalized verifier values
4. Updates job results: corrects field values, restores consensus where possible, unflags trials from manual review when false disagreements are eliminated
5. Reports a summary of changes (fields corrected, consensus restored, trials unflagged)

**Usage:**

```bash
# Preview changes without modifying any data
python retroactive_fix.py --dry-run

# Process all completed jobs
python retroactive_fix.py

# Process a specific job by ID
python retroactive_fix.py --job <job_id>
```

**When to use:**
- After updating normalization rules in the verification pipeline
- After discovering new verifier output patterns that cause false disagreements
- To recalculate concordance numbers after normalization improvements
- As a one-time fix when deploying normalization updates to production

**Safety:** The `--dry-run` flag is recommended before any production run. It reports exactly what would change without modifying stored data.

### 8.2 concordance_test.py

Runs concordance analysis for a single job against human annotations. Calculates per-field agreement rates, Cohen's kappa, and confusion matrices. Useful for validating that a specific job's annotations align with human benchmarks.

**Usage:**

```bash
python concordance_test.py <job_id>
```

### 8.3 concordance_jobs.py

Runs concordance analysis across multiple completed jobs to compare pipeline versions or track improvement over time. Produces aggregate statistics and per-job breakdowns.

**Usage:**

```bash
# Analyze all completed jobs
python concordance_jobs.py

# Compare specific jobs
python concordance_jobs.py --jobs <job_id_1> <job_id_2>
```

## 7. Self-Learning (EDAM)

Agent Annotate includes a self-learning system called EDAM (Experience-Driven Annotation Memory) that improves accuracy across runs without human intervention.

### How It Works

After every job, EDAM:
1. **Stores experiences** — every annotation outcome is recorded with its evidence and confidence
2. **Computes stability** — compares the same trial across prior runs to identify stable vs flipping fields
3. **Self-reviews flagged items** — the premium model re-evaluates items where verifiers disagreed, generating corrections with evidence citations
4. **Optimizes prompts** — every 3rd job, analyzes error patterns and proposes prompt improvements

Before each annotation, EDAM retrieves relevant guidance:
- Past corrections for similar trials ("NCT00004984 was corrected from Positive to Failed")
- Stable exemplars as few-shot examples ("Trials like this consistently get 'Other'")
- Anomaly warnings ("85% of recent trials got the same value — check for bias")

### Running the Learning Cycle

```bash
# Full automated cycle (3x calibration + 3x compounding + 1x full batch + 1x convergence)
python scripts/edam_learning_cycle.py --wait-for RUNNING_JOB_ID

# Custom: 5 calibration runs, then a 100-NCT batch
python scripts/edam_learning_cycle.py --calibration-runs 5 --full-batch-file ncts_100.txt

# Only calibration phases
python scripts/edam_learning_cycle.py --phases 1,2
```

### Monitoring

Check EDAM status via the database:
```bash
sqlite3 results/edam.db "SELECT field_name, COUNT(*), ROUND(AVG(stability_score),2) FROM stability_index GROUP BY field_name;"
sqlite3 results/edam.db "SELECT source, COUNT(*) FROM corrections GROUP BY source;"
sqlite3 results/edam.db "SELECT field_name, variant_name, status, accuracy_score FROM prompt_variants;"
```

### Configuration

Key parameters in `app/services/memory/edam_config.py`:

| Parameter | Default | Purpose |
|---|---|---|
| `MEMORY_BUDGET_TOKENS` | 2000 | Max guidance tokens per annotation call |
| `SELF_REVIEW_ENABLED` | True | Toggle autonomous self-review |
| `SELF_REVIEW_MAX_ITEMS` | 10 | Max flagged items to self-review per job |
| `OPTIMIZATION_INTERVAL_JOBS` | 3 | Run prompt optimizer every Nth job |
| `ANOMALY_THRESHOLD` | 0.80 | Flag if >80% of trials share same value |
| `MAX_EXPERIENCES` | 10000 | Database size cap |
