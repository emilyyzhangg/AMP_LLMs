# Agent Annotate — Methodology

A complete description of the multi-agent annotation pipeline used for publication-grade clinical trial classification. This document describes every component, decision rule, and quality assurance mechanism in sufficient detail for inclusion as a methods section or supplementary material in a scientific publication.

> **Last updated:** 2026-03-15
> **Version:** 0.1.0
> **This document must be updated whenever the annotation agents, verification pipeline, or output format change.**

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Phase 1: Research — Automated Evidence Gathering](#2-phase-1-research--automated-evidence-gathering)
3. [Phase 2: Annotation — Field-Specific LLM Agents](#3-phase-2-annotation--field-specific-llm-agents)
4. [Phase 3: Cross-Field Consistency Enforcement](#4-phase-3-cross-field-consistency-enforcement)
5. [Phase 4: Blind Multi-Model Verification](#5-phase-4-blind-multi-model-verification)
6. [Phase 5: Consensus Determination and Reconciliation](#6-phase-5-consensus-determination-and-reconciliation)
7. [Phase 6: Manual Review Queue](#7-phase-6-manual-review-queue)
8. [Evidence Threshold System](#8-evidence-threshold-system)
9. [Quality Score Calculation](#9-quality-score-calculation)
10. [Output and Provenance](#10-output-and-provenance)
11. [Configuration and Reproducibility](#11-configuration-and-reproducibility)
12. [Error Handling and Failure Modes](#12-error-handling-and-failure-modes)
13. [Hardware Constraints and Sequencing](#13-hardware-constraints-and-sequencing)
14. [Comparison with Human Annotation](#14-comparison-with-human-annotation)
15. [Changelog](#15-changelog)

---

## 1. System Overview

Agent Annotate is an autonomous clinical trial annotation system that classifies peptide-based clinical trials across five fields: peptide identification, antimicrobial peptide classification, delivery mode, trial outcome, and reason for failure. It replaces single-prompt monolithic annotation with a network of specialized agents operating in a three-phase pipeline: research, annotation, and verification.

The system operates without any human annotations at runtime. All decisions are derived from live queries to external biomedical databases and APIs at the time of annotation, ensuring that the most current data is always used.

### Pipeline Architecture

For each clinical trial (identified by NCT ID), the system executes the following phases sequentially:

```
Phase 1: RESEARCH (parallel)
  Four research agents query external databases simultaneously.
  Output: structured evidence with source citations.

Phase 2: ANNOTATION (peptide first, then parallel)
  Five annotation agents each handle one field using LLM inference.
  Output: per-field annotation with value, confidence, reasoning, and evidence chain.

Phase 3: CONSISTENCY ENFORCEMENT (deterministic)
  Cross-field logic rules correct contradictions between independently produced annotations.

Phase 4: VERIFICATION (sequential per field)
  Three independent LLM verifiers blindly re-annotate each field.
  Output: per-field model opinions.

Phase 5: CONSENSUS AND RECONCILIATION
  Agreement is checked across all models. Disagreements trigger reconciliation by a larger model.
  Output: final verified annotation with consensus status.

Phase 6: MANUAL REVIEW QUEUE (if needed)
  Fields that cannot be resolved are flagged for human review.
```

Trials are processed one at a time within a job. Within each trial, research agents run in parallel (Phase 1), but all LLM inference calls (Phases 2, 4, 5) run sequentially because the system operates on a 16 GB Apple M4 Mac Mini with a single Ollama instance that can load only one model at a time.

### Cross-Branch Job Gatekeeper

Only one annotation job may run at a time across all deployed instances (production and development). When a new job is submitted, the service checks both its own queue and the other branch's agent-annotate service via `GET /api/jobs/active`. If any job is active on either branch, the submission is rejected with an HTTP 429 response. This constraint exists because both branches share the same Ollama instance and GPU resources.

---

## 2. Phase 1: Research — Automated Evidence Gathering

Four specialized research agents gather evidence from external sources. All agents run concurrently (via `asyncio.gather`) and make direct HTTP requests to public APIs. The system has zero runtime dependencies on any other internal microservice.

### 2.1 Clinical Protocol Agent

**Sources queried:**
- ClinicalTrials.gov API v2: `GET /api/v2/studies/{NCT_ID}` — retrieves the complete trial protocol including title, brief summary, overall status, why stopped, conditions, interventions (type, name, description, arm group labels), phase, enrollment, eligibility, and study design.
- OpenFDA Drug Label API: `GET /drug/label.json` — retrieves FDA-approved drug labels for interventions, which include route of administration, adverse events, and drug class information.

**Evidence extracted (as structured citations):**
- Trial title (from `protocolSection.identificationModule.briefTitle`)
- Brief summary (from `protocolSection.descriptionModule.briefSummary`)
- Overall status and why stopped (from `protocolSection.statusModule`)
- Conditions and keywords (from `protocolSection.conditionsModule`)
- Intervention details: type, name, description, other names (from `protocolSection.armsInterventionsModule`)
- Phase information
- FDA drug label route of administration

Each citation is stored as a `SourceCitation` object with the fields: `source_name`, `source_url`, `identifier`, `title`, `snippet`, `quality_score`, and `retrieved_at`.

**Quality scores assigned:**
- ClinicalTrials.gov data: 0.95 (primary authoritative source)
- OpenFDA data: 0.85

### 2.2 Literature Agent

**Sources queried:**
- PubMed (via NCBI eUtils API): `esearch.fcgi` to find articles, `esummary.fcgi` to retrieve metadata. Searches by NCT ID, trial title, conditions, and intervention names.
- PubMed Central (PMC): Same eUtils endpoint with `db=pmc` for full-text articles.
- PMC BioC: Structured entity extraction from full-text articles when available.

**Search strategy:** The agent constructs multiple search queries combining the NCT ID, intervention names, and condition terms. It retrieves up to 5 PubMed articles and 3 PMC articles, prioritizing those with the NCT ID in their text.

**Quality scores assigned:**
- PubMed: 0.90 (peer-reviewed)
- PMC: 0.85 (full-text access)
- PMC BioC: 0.80 (structured extraction, reduced quality due to parsing variability)

### 2.3 Peptide Identity Agent

**Sources queried:**
- UniProt REST API: `https://rest.uniprot.org/uniprotkb/search` — searches by intervention drug names to find matching protein/peptide entries. Returns accession numbers, protein names, organism information, keywords, and family classification.
- DRAMP Antimicrobial Peptide Database: `http://dramp.cpu-bioinfor.org/browse/search.php` — searches for known antimicrobial peptides matching the intervention names.

**Quality scores assigned:**
- UniProt: 0.95 (authoritative protein database)
- DRAMP: 0.80 (specialized AMP database)

### 2.4 Web Context Agent

**Sources queried:**
- DuckDuckGo Instant Answer API: `https://api.duckduckgo.com/` — retrieves related topics and quick answers.
- SerpAPI (Google Search): `https://serpapi.com/search` — retrieves web search results and Google Scholar results for the trial title combined with condition and intervention terms.

This agent captures supplementary information not available in formal databases: press releases about trial discontinuation, company announcements about funding decisions, regulatory agency opinions, and COVID-19 disruption reports.

**Quality scores assigned:**
- DuckDuckGo: 0.40 (variable reliability)
- SerpAPI: 0.50 (web sources)
- Google Scholar via SerpAPI: 0.70 (academic but unstructured)

### 2.5 Research Data Structure

Each research agent returns a `ResearchResult` containing:
- `agent_name`: identifies which agent produced the data (e.g., "clinical_protocol")
- `citations`: a list of `SourceCitation` objects, each with `source_name`, `source_url`, `identifier` (NCT ID, PMID, UniProt accession, URL), `title`, `snippet` (up to 500 characters of relevant text), `quality_score` (0.0-1.0), and `retrieved_at` (ISO timestamp)
- `raw_data`: the complete API response for audit purposes
- `error`: populated if the agent encountered a failure (the pipeline continues with other agents)

---

## 3. Phase 2: Annotation — Field-Specific LLM Agents

Five annotation agents each handle one field. Each agent receives the compiled research data, constructs a prompt with the evidence, calls the primary annotator LLM via Ollama, parses the structured response, and returns a `FieldAnnotation` with the value, confidence score, reasoning, cited evidence, and model name.

### 3.1 Evidence Selection

Before calling the LLM, each agent sorts all available citations by a field-specific relevance weight. This weight is the product of the source reliability weight and the field relevance weight. Each field has a relevance matrix defining how important each research agent's data is to that specific field:

| Research Agent | Peptide | Classification | Delivery Mode | Outcome | Failure Reason |
|---------------|---------|----------------|---------------|---------|----------------|
| clinical_protocol | 0.50 | 0.95 | 0.90 | 0.90 | 0.60 |
| literature | 0.75 | 0.80 | 0.85 | 0.75 | 0.70 |
| peptide_identity | 0.95 | 0.80 | 0.40 | 0.20 | 0.15 |
| web_context | 0.40 | 0.50 | 0.45 | 0.60 | 0.80 |

The top 20 citations (or 30 for the investigative agents) are included in the LLM prompt, formatted as `[source_name] identifier: snippet`.

### 3.2 Primary Annotator Model

The primary annotator is llama3.1:8b by default (configurable). All LLM calls use a temperature of 0.10 for near-deterministic output. The Ollama timeout is 600 seconds.

### 3.3 Field: Peptide (True / False)

**Agent:** `PeptideAgent` (single-pass)

**Question answered:** Is the primary intervention in this trial a peptide therapeutic?

**Prompt design:** The system prompt contains 10 worked examples demonstrating the expected input-output behavior for common edge cases. The few-shot examples were selected to address observed failure modes in which small language models ignored written instructions. Specifically:
- Aviptadil (VIP analogue, 28 amino acids) → True
- Kate Farm Peptide 1.5 (nutritional formula) → False
- Semaglutide (GLP-1 analogue, 31 amino acids) → True
- Pembrolizumab (monoclonal antibody) → False
- StreptInCor (synthetic peptide vaccine) → True
- Colistin (cyclic lipopeptide) → True
- Amoxicillin (small molecule) → False
- Apraglutide (GLP-2 analogue) → True
- GSK3732394 (multi-subunit engineered protein) → False
- Hydrolyzed whey protein formula (nutritional product) → False

**Decision criterion:** The active drug must be a peptide chain (typically 2-100 amino acid residues). The critical distinction is between the active drug being a peptide versus the formulation merely containing peptides as food ingredients. Nutritional formulas with hydrolyzed peptides are classified as False because the peptides serve a nutritional function, not a therapeutic one.

**Response parsing:** A regex extracts the `Peptide: [True|False]` line from the LLM output. If no match is found, fallback heuristics check for "peptide: true" or "is a peptide" in the text. If neither is found, the default is False.

**Confidence score:** Calculated as the average `quality_score` across the top 10 cited sources.

**Execution order:** The peptide agent runs first because its result is a dependency for the classification agent.

### 3.4 Field: Classification (AMP(infection) / AMP(other) / Other)

**Agent:** `ClassificationAgent` (single-pass, receives peptide result)

**Question answered:** If the intervention is a peptide, is it an antimicrobial peptide (AMP), and if so, does it target infection?

**Prompt design:** The system prompt implements a three-step decision tree with 9 worked examples. AMP stands for Antimicrobial Peptide — not all peptides are AMPs.

**Three-step decision tree:**
1. Is the intervention a peptide? (Check the peptide determination passed via metadata.) If Peptide = False → "Other". Stop.
2. Is the peptide an antimicrobial peptide? AMPs are defined as peptides that kill or inhibit microorganisms, or peptide-based therapeutics designed to target pathogens. Known AMPs include colistin, polymyxin B, daptomycin, nisin, defensins, LL-37, gramicidin, bacitracin, melittin, magainin, cecropin, and vancomycin. Peptide vaccines targeting pathogens (e.g., StreptInCor) also qualify. Critically, peptide hormone analogues (GLP-1/GLP-2, VIP, GnRH, somatostatin) are NOT AMPs — they are peptides used for metabolic, vascular, or hormonal purposes. If not an AMP → "Other". Stop.
3. Does the AMP target infection? If the therapeutic use targets infection, pathogens, antimicrobial resistance, or infectious disease → "AMP(infection)". If the AMP is used for non-infection purposes such as wound healing, cancer immunotherapy, or biofilm disruption → "AMP(other)".

**Response parsing:** A regex extracts the `Classification:` line. Exact matching is attempted first against the three valid values. If the model outputs bare "AMP" without a subtype, the system defaults to "Other" rather than guessing a subtype.

**Dependency:** Receives the peptide result from the orchestrator via a `metadata` dictionary containing `{"peptide_result": "True"}` or `{"peptide_result": "False"}`.

### 3.5 Field: Delivery Mode (18 valid values)

**Agent:** `DeliveryModeAgent` (single-pass)

**Question answered:** What is the specific route of administration for the primary intervention?

**Valid values (18):**
- Injection/Infusion - Intramuscular
- Injection/Infusion - Subcutaneous/Intradermal
- Injection/Infusion - Other/Unspecified
- IV
- Intranasal
- Oral - Tablet
- Oral - Capsule
- Oral - Food
- Oral - Drink
- Oral - Unspecified
- Topical - Cream/Gel
- Topical - Powder
- Topical - Spray
- Topical - Strip/Covering
- Topical - Wash
- Topical - Unspecified
- Other/Unspecified
- Inhalation

**Prompt design:** The system prompt lists all 18 values with definitions, followed by 11 guidance rules and 6 worked examples. Three critical rules are designed to prevent a common error pattern:
1. NEVER guess the injection subtype. If the protocol says "injection" without specifying intramuscular, subcutaneous, or intravenous, the correct answer is "Injection/Infusion - Other/Unspecified".
2. If an FDA drug label specifies a route (e.g., "SUBCUTANEOUS"), that overrides a generic "injection" in the trial protocol.
3. Explicit terms must be present: "intramuscular" or "IM" for Intramuscular; "subcutaneous", "SC", "sub-Q", or "intradermal" for Subcutaneous/Intradermal. The model must not infer injection subtype from drug class or "likely" administration route.

Additional rules address oral subtypes (nutritional formula = Oral - Drink, not Oral - Food) and nasal sprays (Intranasal, not Topical - Spray).

**Response parsing:** A regex extracts the `Delivery Mode:` line. Exact case-insensitive matching is attempted against all 18 values. If no exact match, fuzzy matching proceeds through category-specific keyword detection: IV/intravenous, intramuscular, subcutaneous, injection/infusion (→ Other/Unspecified), intranasal, inhalation, oral subtypes, and topical subtypes.

### 3.6 Field: Outcome (7 valid values) — Two-Pass Investigative Agent

**Agent:** `OutcomeAgent` (two-pass)

**Question answered:** What is the clinical outcome of this trial?

**Valid values:** Positive, Withdrawn, Terminated, Failed - completed trial, Recruiting, Unknown, Active not recruiting

**Design rationale:** ClinicalTrials.gov registry status is often stale or incomplete. A single-pass approach that reads the registry status and returns it directly produces systematically incorrect results. Analysis of prior annotation efforts revealed that 15 or more UNKNOWN-status trials had positive results documented in published literature, and 61 COMPLETED trials had no published results (correctly requiring an "Unknown" annotation rather than "Positive"). The two-pass design forces the model to investigate the literature before deciding.

**Pass 1 — Fact Extraction:** The LLM is given all available evidence (up to 30 citations, more than other agents) and instructed to extract five factual fields:
1. Registry Status (the overallStatus from ClinicalTrials.gov)
2. Published Results (summary of findings from PubMed, PMC, and web evidence)
3. Results Posted (whether ClinicalTrials.gov indicates results were posted)
4. Completion Date
5. Why Stopped (if terminated or withdrawn)

**Pass 2 — Determination:** The extracted facts from Pass 1 are inserted into a second prompt that applies explicit decision rules:
- Registry says TERMINATED → outcome is "Terminated", regardless of interim results.
- Registry says WITHDRAWN → outcome is "Withdrawn".
- Registry says COMPLETED → use published literature to distinguish: "Positive" (efficacy demonstrated), "Failed - completed trial" (negative results), or "Unknown" (no publications found).
- Active statuses map directly: RECRUITING → "Recruiting", ACTIVE_NOT_RECRUITING → "Active, not recruiting".
- UNKNOWN/SUSPENDED → check literature: positive findings → "Positive", negative → "Failed - completed trial", no results → "Unknown".

**Recency rule:** If multiple publications exist with conflicting conclusions, the most recent publication takes priority. This ensures that newly available data supersedes older reports.

**Fallback:** If Pass 2 fails (LLM error), a deterministic fallback function parses Pass 1 output using keyword matching on published results and registry status fields.

**Audit trail:** Both Pass 1 extraction and Pass 2 reasoning are preserved in the `reasoning` field of the annotation output.

### 3.7 Field: Reason for Failure (5 valid values or empty) — Two-Pass Investigative Agent

**Agent:** `FailureReasonAgent` (two-pass with short-circuit)

**Question answered:** If this trial failed, was terminated, or was withdrawn, why?

**Valid values:** Business Reason, Ineffective for purpose, Toxic/Unsafe, Due to covid, Recruitment issues, or empty string (if the trial did not fail)

**Design rationale:** Failure reasons are frequently hidden in literature rather than recorded in registry fields. Analysis showed that 49 out of 99 failure reasons came from COMPLETED, UNKNOWN, or ACTIVE trials where the ClinicalTrials.gov `whyStopped` field was blank. The reasons were documented only in published papers, press releases, or regulatory filings.

**Pass 1 — Investigation:** The LLM examines all evidence (up to 30 citations) and extracts:
1. Trial Status
2. Why Stopped (from ClinicalTrials.gov, or "Not provided" if blank)
3. Published Findings (quoted excerpts from papers discussing results, adverse events, or discontinuation reasons)
4. Outcome Signals (keyword-based signals: "met primary endpoint" = success, "did not meet" = failure, "adverse events" = safety, etc.)
5. Is This A Failure (Yes/No/Unclear)

**Short-circuit:** If Pass 1 determines the trial did not fail (answer starts with "No"), the agent returns an empty string immediately without invoking Pass 2. This optimization avoids an unnecessary LLM call for approximately 80% of trials.

**Pass 2 — Classification:** If failure was detected, the extracted facts are passed to a second prompt with explicit classification rules:
1. Published literature is more reliable than the `whyStopped` field. A trial with `whyStopped="Sponsor decision"` may actually have failed due to toxicity if papers report adverse events.
2. COMPLETED trials can have failure reasons if published results show the trial did not meet its primary endpoints ("Ineffective for purpose").
3. If the trial did not fail, the answer must be EMPTY.
4. Surface labels like "sponsor decision" often mask the real reason — the model must look at the evidence.
5. If multiple publications exist with conflicting findings, the most recent publication takes priority.

**Fallback:** If Pass 2 fails, a deterministic fallback function scans Pass 1 output for keywords (toxicity → Toxic/Unsafe, did not meet → Ineffective, COVID → Due to covid, recruitment → Recruitment issues, sponsor → Business Reason).

---

## 4. Phase 3: Cross-Field Consistency Enforcement

After all five fields are annotated but before verification begins, the orchestrator runs a deterministic consistency check (`_enforce_consistency`) to correct contradictions that arise from fields being annotated independently.

### Rule 1: Peptide = False implies Classification = "Other"

If the peptide agent determined that the intervention is not a peptide, then the classification cannot be AMP(infection) or AMP(other). The consistency checker forces the classification to "Other" and prepends an explanation to the reasoning field: `[Consistency override: peptide=False → Other]`.

### Rule 2: Non-failure outcomes clear the failure reason

If the outcome is one of {Positive, Recruiting, Active not recruiting, Unknown}, then no failure reason should be present. The consistency checker clears any populated failure reason to an empty string and logs the override: `[Consistency override: outcome='Positive' → no failure reason]`.

These rules are applied deterministically — they do not involve LLM inference. Both overrides are logged for the audit trail.

---

## 5. Phase 4: Blind Multi-Model Verification

Each annotated field undergoes blind verification by three independent LLM models. The verifiers never see the primary annotator's answer or reasoning — they receive only the raw research evidence and field-specific instructions.

### 5.1 Verifier Models

The default configuration uses three verifier models from different model families to maximize diversity:
- Verifier 1: gemma2:9b (Google)
- Verifier 2: qwen2:latest (Alibaba)
- Verifier 3: mistral:latest (Mistral AI)

The use of models from different training corpora and architectures ensures that systematic biases in one model family are unlikely to be shared across all verifiers.

### 5.2 Verifier Prompts

Each verifier receives a field-specific prompt with the same level of detail as the primary annotator's prompt, including worked examples and critical rules. The verifier prompts were designed to achieve prompt parity with the primary annotator — the only difference is that verifiers do not see the primary's answer.

The evidence text is constructed from the raw research citations (up to 10 per research agent), formatted as `[source_name] identifier: snippet`.

### 5.3 Verifier Output Parsing

The verifier's response is parsed to extract its suggested value. A hardened parsing function:
1. Extracts the field value using a field-specific regex pattern.
2. Normalizes common aliases: "Intravenous" → "IV", "Active" → "Active, not recruiting".
3. Matches against the list of valid values (exact match first, then substring containment).
4. Returns `None` for any unrecognizable value rather than passing through raw text. This prevents invalid values from entering the consensus check.

### 5.4 Sequential Execution

Verifiers run sequentially (one at a time) because Ollama can only load one model into GPU memory at a time on 16 GB hardware. Each verifier requires loading a different model, generating the response, then unloading before the next verifier can run.

---

## 6. Phase 5: Consensus Determination and Reconciliation

### 6.1 Value Normalization

Before comparing values, the consensus checker normalizes all values through an alias map to prevent false disagreements caused by formatting differences:

| Raw Value | Normalized To |
|-----------|--------------|
| "Intravenous" | "iv" |
| "Injection/Infusion - Intravenous" | "iv" |
| "Active" | "active, not recruiting" |
| "Active not recruiting" | "active, not recruiting" |
| "AMP" (bare, no subtype) | "other" |

### 6.2 Consensus Check

The consensus checker compares the primary annotator's answer against all verifier opinions using normalized, case-insensitive string comparison. The agreement ratio is calculated as: `agreements / total_verifiers`.

The default consensus threshold is 1.0 (unanimous agreement required). If all verifiers agree with the primary annotator, consensus is reached and the primary value becomes the final value.

### 6.3 Reconciliation

If consensus is not reached and a reconciler model is configured, a larger model (default: qwen2.5:14b, 9 GB) examines all opinions together with the evidence and makes a final determination.

The reconciler receives:
- The field name and all valid values
- The primary annotator's answer
- Each verifier's answer and reasoning (with AGREES/DISAGREES labels)
- Up to 8 citations per research agent from the raw evidence

The reconciler's system prompt instructs it to:
1. Base its decision only on evidence, not on model authority
2. Choose the most conservative/supported answer when evidence supports multiple interpretations
3. Respond with "MANUAL_REVIEW" if the evidence is genuinely insufficient

If the reconciler provides a specific answer, that becomes the final value and `consensus_reached` is set to True. If the reconciler responds with "MANUAL_REVIEW" or fails, the field is flagged for human review.

### 6.4 Skip Conditions

Fields with very low confidence (below 0.2) that were already flagged as below the evidence threshold in Phase 2 skip the verification pipeline entirely and are immediately flagged as "insufficient_evidence" requiring manual review.

---

## 7. Phase 6: Manual Review Queue

Fields that could not be resolved through verification and reconciliation are placed in a manual review queue. Each review item records:
- The job ID and NCT ID
- The field name
- The primary annotator's value
- All suggested values (from the primary and each verifier)
- All model opinions with reasoning
- The reason for flagging (model disagreement or insufficient evidence)

A human reviewer can approve the primary value, select an alternative value from the suggestions, or provide a new value with notes. All decisions are recorded in the audit trail.

---

## 8. Evidence Threshold System

Each annotation field has a minimum evidence requirement that must be met before the system will produce a high-confidence answer. If the threshold is not met, the annotation's confidence is capped at 0.3 and the reasoning is prefixed with the shortfall details.

| Field | Minimum Sources | Minimum Quality Score | Rationale |
|-------|----------------|----------------------|-----------|
| Classification | 2 | 0.50 | Core claim requiring multiple corroborating sources |
| Delivery Mode | 2 | 0.50 | Usually well-documented in protocols |
| Outcome | 2 | 0.50 | Registry status plus at least one corroborating source |
| Reason for Failure | 1 | 0.30 | Often available from a single literature source; uses two-pass investigation |
| Peptide | 2 | 0.50 | Critical for AMP research; requires protein database confirmation |

"Minimum Sources" counts the number of distinct data source names (e.g., clinicaltrials_gov, pubmed, uniprot) present in the annotation's evidence. "Minimum Quality Score" is the average quality score across all cited evidence.

---

## 9. Quality Score Calculation

Quality scores use a two-layer weighting system.

**Layer 1 — Source Reliability Weight:** Each data source is assigned a fixed reliability weight reflecting the authoritativeness and consistency of its data:

| Source | Weight |
|--------|--------|
| ClinicalTrials.gov | 0.95 |
| UniProt | 0.95 |
| PubMed | 0.90 |
| PMC | 0.85 |
| OpenFDA | 0.85 |
| PMC BioC | 0.80 |
| DRAMP | 0.80 |
| Google Scholar (SerpAPI) | 0.70 |
| SerpAPI (web) | 0.50 |
| DuckDuckGo | 0.40 |

**Layer 2 — Field Relevance Weight:** Not all sources are equally relevant to every field. The field relevance matrix (Section 3.1) adjusts which citations are prioritized for each agent.

**Per-annotation confidence:** For each field annotation, the confidence score is the average `quality_score` across the top 10 cited evidence items. This represents the overall strength of the evidence backing the annotation.

---

## 10. Output and Provenance

### 10.1 JSON Output

The primary output is a JSON file (`results/json/{job_id}.json`) containing the complete audit trail:
- System version and git commit hash
- Frozen copy of the configuration used for this job
- For each trial: metadata (title, status, phase, conditions, interventions), all annotations with full evidence chains and reasoning, all verification opinions with model names and reasoning, reconciliation details, and manual review flags.

### 10.2 Standard CSV (16 columns)

Designed for direct comparison with human annotation data:

| Column | Description |
|--------|-------------|
| NCT ID | ClinicalTrials.gov identifier |
| Study Title | Brief title |
| Study Status | Registry status |
| Phase | Trial phase |
| Conditions | Comma-separated conditions |
| Interventions | Comma-separated interventions |
| Classification | Final annotated value |
| Classification Evidence | Deduplicated source identifiers (PMIDs, URLs) |
| Delivery Mode | Final annotated value |
| Delivery Mode Evidence | Deduplicated source identifiers |
| Outcome | Final annotated value |
| Outcome Evidence | Deduplicated source identifiers |
| Reason for Failure | Final annotated value (empty if not applicable) |
| Reason for Failure Evidence | Deduplicated source identifiers |
| Peptide | Final annotated value |
| Peptide Evidence | Deduplicated source identifiers |

Evidence columns contain deduplicated identifiers in the format: `PMID:36191080; https://clinicaltrials.gov/study/NCT06729606; uniprot:P01282`.

### 10.3 Full CSV (61 columns)

Extends the standard CSV with per-field metadata:
- `{field}_confidence` — average quality score of evidence (0.0-1.0)
- `{field}_evidence_sources` — database:identifier pairs (e.g., `clinicaltrials_gov:NCT06729606; pubmed:PMID:36191080`)
- `{field}_evidence_urls` — deduplicated source URLs
- `{field}_reasoning` — the model's chain-of-thought reasoning (up to 1000 characters)
- `{field}_consensus` — whether unanimous consensus was reached (True/False)
- `{field}_final_value` — the post-verification final value
- `{field}_verifier_opinions` — each verifier's answer (format: `verifier_1: value; verifier_2: value; verifier_3: value`)
- `{field}_reconciler_used` — whether the reconciler was invoked (True/False)
- `{field}_manual_review` — whether the field was flagged for manual review (True/False)

Global columns: `flagged_for_review`, `flag_reason`, `version`, `git_commit`, `config_hash`, `annotated_at`.

---

## 11. Configuration and Reproducibility

All configuration is stored in `config/default_config.yaml` and is frozen at job creation time. The frozen configuration snapshot is stored in both the JSON output and the database, ensuring that every result can be traced back to the exact settings used to produce it.

### Configurable Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `verification.num_verifiers` | 3 | Number of blind verifiers |
| `verification.consensus_threshold` | 1.0 | Fraction of verifiers that must agree (1.0 = unanimous) |
| `verification.models` | (see below) | Model assignments for annotator, verifiers, reconciler |
| `evidence_thresholds.{field}.min_sources` | 1-2 | Minimum independent sources per field |
| `evidence_thresholds.{field}.min_quality` | 0.3-0.5 | Minimum average quality score per field |
| `orchestrator.parallel_research` | true | Whether research agents run concurrently |
| `orchestrator.parallel_annotation` | true | Whether annotation agents run concurrently (except peptide) |
| `ollama.temperature` | 0.10 | LLM temperature (low for deterministic output) |
| `ollama.timeout` | 600 | Seconds before LLM call times out |

### Default Model Assignments

| Role | Model | Size | Architecture |
|------|-------|------|-------------|
| Primary Annotator | llama3.1:8b | 4.9 GB | Meta LLaMA 3.1 |
| Verifier 1 | gemma2:9b | 5.4 GB | Google Gemma 2 |
| Verifier 2 | qwen2:latest | 4.4 GB | Alibaba Qwen 2 |
| Verifier 3 | mistral:latest | 4.4 GB | Mistral AI |
| Reconciler | qwen2.5:14b | 9.0 GB | Alibaba Qwen 2.5 |

---

## 12. Error Handling and Failure Modes

| Scenario | Handling |
|----------|----------|
| Research agent API unreachable | Agent returns a `ResearchResult` with an `error` field. Other agents continue. Downstream annotation agents receive reduced evidence. |
| LLM call fails during annotation | Agent returns a default value ("False" for peptide, "Unknown" for classification, "Other/Unspecified" for delivery mode, "Unknown" for outcome, "" for failure reason) with confidence 0.0 and an error message in reasoning. |
| LLM call fails during verification | Verifier returns a `ModelOpinion` with `suggested_value=None` and `agrees=False`. Consensus check treats this as a non-agreement. |
| Reconciler fails | `ConsensusResult` is set with `flag_reason="reconciler_error"` and the field is flagged for manual review. |
| Pass 2 fails in two-pass agents | A deterministic keyword-based fallback function parses Pass 1 output to produce a best-effort answer with reduced confidence (0.3). |
| Evidence below threshold | Confidence is capped at 0.3 and reasoning is prefixed with the shortfall details. The field skips verification and is flagged directly. |
| Entire trial processing fails | Error is captured, the trial is marked with an error in the output, and the job continues to the next trial. |
| Invalid LLM output (unrecognizable value) | Annotation agents and verifiers return `None` or a safe default. Verifiers' `None` values count as non-agreement in the consensus check. |

---

## 13. Hardware Constraints and Sequencing

The system operates on a Mac Mini with an Apple M4 chip and 16 GB of unified memory. Ollama loads one model at a time into memory. This imposes the following constraints:

- **One Ollama model at a time:** An `asyncio.Lock()` ensures that only one LLM generation call runs at any time, preventing out-of-memory errors.
- **Sequential model switching:** During verification, each verifier requires loading a different model (e.g., switching from gemma2:9b to qwen2:latest), which takes several seconds.
- **One trial at a time:** Trials within a batch are processed sequentially.
- **One job at a time across branches:** The cross-branch gatekeeper prevents concurrent jobs on production and development instances.
- **Maximum batch size:** 500 trials per job.
- **Memory management:** Research data per trial (~1-5 MB) is discarded after annotation is complete.

---

## 14. Comparison with Human Annotation

The system was developed and evaluated against human annotations from two independent replicates (~1,847 trials each, 4 annotators). Human annotations are used exclusively for development-time evaluation and prompt refinement — they are never used at runtime.

### Human Inter-Rater Agreement

| Field | Human Agreement Rate | Notes |
|-------|---------------------|-------|
| Classification | 91.6% | Moderate reliability |
| Delivery Mode | 68.2% | Low reliability; casing inconsistencies, missing categories |
| Outcome | 55.6% | Very low reliability; annotators disagreed on Positive vs Unknown vs Recruiting |
| Reason for Failure | 91.3% | Moderate reliability; small sample (46 both-filled rows) |
| Peptide | 48.4% | Very low reliability; one annotator had a much broader definition |

### Agent Structural Advantages

1. **100% coverage:** The agent annotates every submitted trial. Humans left 50-65% of rows blank.
2. **Recency:** The agent queries live APIs at annotation time and uses the most current data available. Human annotations reflect a fixed point in time.
3. **Consistency:** The agent applies identical decision rules to every trial. Human annotators varied in their interpretation of categories.
4. **Full evidence trail:** Every annotation includes specific source identifiers (PMIDs, URLs, database accessions). Human annotators' evidence link columns were largely blank.
5. **Systematic literature investigation:** The two-pass outcome and failure reason agents actively search published literature rather than relying on registry status alone.

---

## 15. Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2026-03-15 | 0.1.0 | Initial methodology document. Describes all agents, verification pipeline, cross-field consistency, evidence thresholds, quality scores, output formats, and hardware constraints. |
