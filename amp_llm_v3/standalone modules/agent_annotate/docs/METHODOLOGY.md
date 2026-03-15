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
15. [Persistence, Resumability, and HTTP Resilience](#15-persistence-resumability-and-http-resilience)
16. [Multi-Run Consensus Strategy](#16-multi-run-consensus-strategy)
17. [Changelog](#17-changelog)

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

The pipeline uses a two-phase architecture with intermediate persistence:

```
Phase 1 (Research):  ALL trials researched fully in parallel → each persisted to disk
Phase 2 (Annotate):  Each trial annotated + verified sequentially → each persisted to disk
```

Phase 1 research is fully parallelized across trials (bounded by a concurrency semaphore of 20) because research agents make only external HTTP calls with no Ollama dependency. Phase 2 processes trials one at a time because the system operates on a 16 GB Apple M4 Mac Mini with a single Ollama instance that can load only one model at a time. All intermediate results are persisted per-trial to disk, enabling crash resilience and job resumability (see Section 15).

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

**Sources queried (4, all in parallel):**
- **PubMed** (via NCBI eUtils API): `esearch.fcgi` to find articles (retmax=100), `efetch.fcgi` to retrieve full records with abstracts as XML. Searches by NCT ID. If efetch fails, falls back to `esummary.fcgi` for metadata.
- **PubMed Central (PMC)**: Same eUtils `esearch` endpoint with `db=pmc` (retmax=50), then `esummary` for proper titles and metadata.
- **Europe PMC** (free, no API key): `europepmc.org/webservices/rest/search` with `resultType=core` (pageSize=50). Returns abstracts directly in JSON — the best single source for abstract text without XML parsing.
- **Semantic Scholar** (free, 100 req/5min): `api.semanticscholar.org/graph/v1/paper/search` (limit=20). Returns structured paper data including abstracts, citation counts, and cross-referenced PMIDs/DOIs.

**Search strategy:** All four sources are queried in parallel within the agent using `asyncio.gather`. Each source searches by NCT ID. Results are deduplicated by PMID across all sources, keeping the citation with the longest snippet (typically the one with a full abstract).

**Abstract fetching:** PubMed results include actual abstracts fetched via `efetch` XML parsing (`rettype=abstract&retmode=xml`). The XML parser extracts structured abstracts with labeled sections (BACKGROUND, METHODS, RESULTS, CONCLUSIONS) where available. Europe PMC and Semantic Scholar return abstracts directly in JSON.

**Snippet format:** All citations use a structured, labeled format for LLM clarity:
```
Title: Effect of peptide X on wound healing
Authors: Smith J, Jones K, Lee M et al.
Journal: J Clinical Investigation (2023)
Abstract: We conducted a phase 2 randomized controlled trial...
```

**Quality scores assigned:**
- PubMed: 0.90 (peer-reviewed), 0.45 without abstract
- PMC: 0.85 (full-text access)
- Europe PMC: 0.90 (peer-reviewed with abstracts), 0.45 without abstract
- Semantic Scholar: 0.80 (structured data), 0.40 without abstract

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

**Question answered:** If the intervention is a peptide, is it an antimicrobial peptide (AMP) / host defense peptide, and if so, does it target infection?

**Prompt design:** The system prompt implements a three-step decision tree with 12 worked examples. AMP stands for Antimicrobial Peptide — not all peptides are AMPs.

**Three-step decision tree:**
1. Is the intervention a peptide? (Check the peptide determination passed via metadata.) If Peptide = False → "Other". Stop.
2. Is the peptide an antimicrobial peptide (AMP)? AMPs, also known as host defense peptides (HDPs), are peptides that participate in defense against pathogens through ANY of the following modes of action:
   - **Mode A — Direct antimicrobial:** Peptides that directly kill or inhibit bacteria, viruses, fungi, or parasites via membrane disruption, pore formation, or intracellular targeting (colistin, polymyxin B, daptomycin, nisin, melittin, magainin, cecropin, defensins, gramicidin, bacitracin, vancomycin, tyrothricin).
   - **Mode B — Immunostimulatory / host defense:** Peptides that PROMOTE immune defense against pathogens by recruiting neutrophils/macrophages, enhancing phagocytosis, activating dendritic cells, bridging innate and adaptive immunity, or stimulating protective cytokine production (LL-37/cathelicidin, defensins, thymosin alpha-1 when boosting immune defense, lactoferricin).
   - **Mode C — Anti-biofilm:** Peptides that disrupt or prevent microbial biofilm formation (LL-37, DJK-5, IDR-1018).
   - **Mode D — Pathogen-targeting vaccines/immunogens:** Peptide-based vaccines that induce immune responses against specific pathogens (StreptInCor, peptide-based HIV/malaria vaccines).

   The key criterion is that the peptide must have a known or plausible role in DEFENSE AGAINST PATHOGENS. Peptides that suppress immune responses (for autoimmunity), have purely metabolic/hormonal functions (GLP-1/GLP-2, GnRH, somatostatin analogues), or work via non-biological mechanisms (self-assembling peptides for mineralization) are NOT AMPs.
3. Does the AMP target infection? If the therapeutic use targets infection, pathogens, antimicrobial resistance, or infectious disease → "AMP(infection)". If the AMP is used for non-infection purposes such as wound healing, cancer immunotherapy, or biofilm disruption → "AMP(other)".

**Two-pass design rationale:** Single-pass classification with 8B models produced 25% concordance with human annotations because the model ignored the decision tree and pattern-matched surface features. The two-pass design forces structured fact extraction before classification, and uses a larger model (14B on Mac Mini, 72B on server) for both passes.

**Pass 1 — Evidence Extraction:** The LLM extracts 5 factual fields from the evidence:
1. Peptide Identity (molecular class, amino acid length)
2. Database Matches (DRAMP, APD3, UniProt antimicrobial annotations — highlighted at the top of the evidence)
3. Mechanism of Action (direct antimicrobial, immunostimulatory, anti-biofilm, or non-antimicrobial)
4. Therapeutic Target (infection vs cancer vs autoimmune vs metabolic vs structural)
5. Immune Direction (PROMOTE defense, SUPPRESS immunity, or immune-neutral)

**Pass 2 — Decision Tree Application:** The extracted facts from Pass 1 are passed to a second prompt that applies the three-step decision tree. Pass 2 explicitly checks the database matches and immune direction fields to prevent misclassification.

**Fallback:** If Pass 2 fails, a deterministic keyword-based fallback scans Pass 1 output for antimicrobial signals (DRAMP matches, "kills bacteria", etc.) and non-AMP signals ("metabolic hormone", "self-assembling", etc.).

**DRAMP cross-check:** The evidence text highlights DRAMP (antimicrobial peptide database) matches and UniProt annotations at the top, before other evidence. A DRAMP hit is strong evidence for AMP classification; absence of any database match combined with no antimicrobial mechanism evidence strongly favors "Other".

**Peptide cascade re-verification:** If the verification phase flips the peptide value (e.g., True → False), the classification is automatically re-run with the corrected peptide value, re-verified, and the consistency rules re-applied. This prevents stale classification values from persisting after a peptide correction.

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
| `orchestrator.hardware_profile` | "mac_mini" | Hardware profile: "mac_mini" or "server" (see below) |
| `ollama.temperature` | 0.10 | LLM temperature (low for deterministic output) |
| `ollama.timeout` | 600 | Seconds before LLM call times out |

### Hardware Profiles

The system supports two hardware profiles that control model selection for high-accuracy fields (classification, peptide) and concurrency settings:

**Mac Mini M4 (16 GB) — `hardware_profile: "mac_mini"`**
- One Ollama model at a time (asyncio.Lock)
- Sequential model switching during verification
- Classification uses qwen2.5:14b (upgraded from 8B — see rationale below)
- All other fields use llama3.1:8b
- Maximum batch size: 500 trials

**Server (unlimited VRAM) — `hardware_profile: "server"`**
- Multiple Ollama models can load simultaneously
- Classification uses qwen2.5:72b for maximum accuracy
- Verifiers can run in parallel (no sequential model switching needed)
- No practical batch size limit

**Why classification uses a larger model:** Testing on 8 trials showed that llama3.1:8b ignores explicit worked examples in the classification prompt. It pattern-matches surface features ("peptide" + "immune" → AMP) rather than following the multi-step decision tree. This produced 25% concordance with human annotations on classification. The 14B model (Mac Mini) and 72B model (server) follow the decision tree reliably.

### Default Model Assignments (Mac Mini)

| Role | Model | Size | Architecture |
|------|-------|------|-------------|
| Primary Annotator | llama3.1:8b | 4.9 GB | Meta LLaMA 3.1 |
| Classification Annotator | qwen2.5:14b | 9.0 GB | Alibaba Qwen 2.5 (overrides primary for this field) |
| Verifier 1 | gemma2:9b | 5.4 GB | Google Gemma 2 |
| Verifier 2 | qwen2:latest | 4.4 GB | Alibaba Qwen 2 |
| Verifier 3 | mistral:latest | 4.4 GB | Mistral AI |
| Reconciler | qwen2.5:14b | 9.0 GB | Alibaba Qwen 2.5 |

### Default Model Assignments (Server)

| Role | Model | Size | Architecture |
|------|-------|------|-------------|
| Primary Annotator | llama3.1:8b | 4.9 GB | Meta LLaMA 3.1 |
| Classification Annotator | qwen2.5:72b | 47 GB | Alibaba Qwen 2.5 (maximum accuracy) |
| Verifier 1 | gemma2:9b | 5.4 GB | Google Gemma 2 |
| Verifier 2 | qwen2:latest | 4.4 GB | Alibaba Qwen 2 |
| Verifier 3 | mistral:latest | 4.4 GB | Mistral AI |
| Reconciler | qwen2.5:72b | 47 GB | Alibaba Qwen 2.5 |

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

The system was developed and evaluated against human annotations from two independent replicates (~1,847 trials each, 4 annotators: Mercan, Maya, Anat, Ali). Human annotations are used exclusively for development-time evaluation and prompt refinement — they are never used at runtime.

### Human Inter-Rater Agreement

| Field | R1 Filled | R2 Filled | Overlap | Agreement Rate | Notes |
|-------|-----------|-----------|---------|----------------|-------|
| Classification | 798 (43%) | 693 (37%) | 620 | 91.6% | Most disagreements: Other vs AMP(infection) |
| Delivery Mode | 806 (43%) | 628 (33%) | 579 | 71.2% | Injection subtype confusion, casing, missing categories |
| Outcome | 617 (33%) | 472 (25%) | 372 | 55.6% | R1 used "Recruiting" 222x; R2 used it 0x (used "Active" instead) |
| Reason for Failure | 99 (5%) | 82 (4%) | 46 | 91.3% | Small overlap; most trials have no failure reason |
| Peptide | 668 (36%) | 244 (13%) | 30 | 100% | Very small overlap; R1 marked 451 True vs R2's 56 |

### Systematic Human Annotation Issues

**Definition divergence:** R1 annotated 451 trials as Peptide=True (24% of all trials) while R2 annotated only 56 (3%). This 8:1 ratio indicates a fundamentally different interpretation of "peptide" between the annotator groups. R1 appears to have used a broader definition that included peptide-related compounds, radiolabeled peptides, and peptide formulations, while R2 restricted to therapeutic peptide drugs.

**Missing categories:** R2 never used "Recruiting" as an outcome (0 instances vs R1's 222). R2 annotators mapped recruiting trials to "Active" (30x, an invalid value), "Positive", or "Unknown". R2 also omitted "Oral - Capsule" entirely (0 vs R1's 17).

**Invalid values:** R2 used "Active" (30x) which is not a valid outcome value. R2 used lowercase variants "Oral - unspecified" and "Topical - unspecified". R1 used multi-value delivery modes with comma-separated values in 24 rows (e.g., "SC, IV, Oral").

**Outcome disagreement patterns (165 disagreements):**
- R1=Recruiting vs R2=Unknown: 27 cases — temporal: trial status changed between annotation sessions
- R1=Recruiting vs R2=Positive: 26 cases — R2 checked published literature, R1 relied on registry
- R1=Unknown vs R2=Positive: 19 cases — same temporal issue
- R1=Failed vs R2=Positive: 12 cases — conflicting interpretation of published results

### Prior Concordance Results

Before the multi-agent pipeline, a Claude-based annotation system was evaluated at 852 trials:

| Field | Claude (self-research) vs Human | Notes |
|-------|-------------------------------|-------|
| Classification | 91.1% | Matches human inter-rater reliability |
| Delivery Mode | 100.0% | Exceeds human 71.2% agreement |
| Outcome | 57.0% | Comparable to human 55.6% — both struggle with temporal drift |
| Peptide | 79.3% | Between R1 (liberal) and R2 (strict) definitions |
| Reason for Failure | 76.8% | Below human 91.3% on small overlap set |

### Agent Structural Advantages

1. **100% coverage:** The agent annotates every submitted trial. Humans left 57-87% of rows blank (worst: Reason for Failure at 95-96% blank).
2. **Recency:** The agent queries live APIs at annotation time and uses the most current data available. Human annotations reflect a fixed point in time — the dominant source of outcome disagreements.
3. **Consistency:** The agent applies identical decision rules to every trial. Human annotators had systematically different definitions (451 vs 56 peptide=True).
4. **Full evidence trail:** Every annotation includes specific source identifiers (PMIDs, URLs, database accessions). Human annotators' evidence link columns were largely blank.
5. **Systematic literature investigation:** The two-pass outcome and failure reason agents actively search published literature rather than relying on registry status alone.
6. **Multi-source verification:** Agent cross-checks 6+ databases per trial (ClinicalTrials.gov, PubMed, PMC, Europe PMC, Semantic Scholar, UniProt, OpenFDA, DRAMP, web sources). Most human annotators checked 1-2 sources.

---

## 15. Persistence, Resumability, and HTTP Resilience

### Two-Phase Persistence

The pipeline persists intermediate results to disk after each trial, enabling crash resilience and job resumability.

**Storage layout:**
```
results/
├── json/{job_id}.json              # Final output (unchanged)
├── csv/{job_id}_*.csv              # CSV exports (unchanged)
├── research/{job_id}/              # Persisted research per trial
│   ├── _meta.json                  # {job_id, git_commit, config_hash, nct_ids}
│   └── NCT00000001.json           # ResearchResult[] for this trial
└── annotations/{job_id}/           # Persisted annotation results per trial
    └── NCT00000001.json           # Full trial output dict
```

**Atomic writes:** All persistence writes go to `.tmp` first, then `os.rename()` to the final filename. This prevents corrupt partial files on crash. On resume, orphaned `.tmp` files are cleaned up and the corresponding trial is re-processed.

**Resume endpoint:** `POST /api/jobs/{job_id}/resume` validates that the research on disk was produced by the same git commit and config hash. If the commit has changed, a `force=true` flag is required to override. Only failed or cancelled jobs can be resumed. The resume skips trials already persisted and re-processes the rest.

### HTTP Resilience

All research agents use a shared `resilient_get()` function (`agents/research/http_utils.py`) that provides:

**Per-host rate limiting:** Shared `asyncio.Semaphore` instances prevent hammering individual APIs when many trials are researched in parallel:

| Host | Concurrent Limit | Rationale |
|------|-----------------|-----------|
| eutils.ncbi.nlm.nih.gov | 3 (no key) / 8 (with key) | NCBI E-utilities rate limit |
| api.semanticscholar.org | 3 | 100 req/5min free tier |
| www.ebi.ac.uk | 10 | Europe PMC, generous |
| clinicaltrials.gov | 8 | CT.gov v2, generous |
| api.fda.gov | 4 | OpenFDA, 240/min |
| rest.uniprot.org | 5 | UniProt, moderate |

**Retry with exponential backoff:** On 429 (rate limited) or 5xx (server error), requests are retried up to 3 times with exponential backoff (1s, 2s, 4s). The `Retry-After` header is respected when present. Connection timeouts and read errors are also retried. The semaphore is released between retries so other requests to the same host can proceed.

---

## 16. Multi-Run Consensus Strategy

### Rationale

Running the same trial through the pipeline multiple times and taking majority vote reduces noise from LLM stochasticity. This is analogous to using multiple human replicates — the same principle that motivated the two-replicate design of the human annotation study.

Analysis of human annotation data reveals that fields where humans disagreed most (Outcome 55.6%, Peptide with R1/R2 definition divergence) are precisely the fields most sensitive to stochastic variation. Multi-run consensus addresses this systematically.

### Design

For each batch of trials:
1. Run the full pipeline N times (recommended: N=3 for throughput, N=5 for maximum accuracy).
2. Each run produces independent research (Phase 1) and independent annotation/verification (Phase 2) with the same configuration but different LLM sampling.
3. For each field on each trial, take the **majority vote** across all N runs.
4. Fields where all N runs disagree (no majority) are flagged as low-confidence and queued for manual review.
5. The **stability score** (fraction of runs that agree with the majority) is recorded per field. Fields with stability < 1.0 indicate prompt or evidence weaknesses.

### What This Reveals

- **Stable fields** (all N runs agree): The pipeline is confident and prompt engineering is adequate.
- **Unstable fields** (N runs split): The evidence is ambiguous or the prompt allows multiple valid interpretations. These are candidates for prompt tuning, additional few-shot examples, or model upgrade.
- **Comparison with human replicates:** If the agent's multi-run stability exceeds human inter-rater agreement, the agent is producing more consistent annotations than humans for that field.

### Calibration Data

High-confidence human annotations (where R1 and R2 agree) serve as ground truth for evaluation:
- Classification: 568 agreed pairs
- Delivery Mode: 412 agreed pairs
- Outcome: 207 agreed pairs
- Reason for Failure: 42 agreed pairs

For disagreements between agent and human ground truth, the agent's cited sources are independently verified to determine whether the agent found newer/better evidence (a "recency win") or made an error.

---

## 17. Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2026-03-15 | 0.3.0 | Classification agent redesigned as two-pass investigative agent (Pass 1: extract antimicrobial evidence, Pass 2: apply decision tree). Classification uses larger model (14B Mac Mini, 72B server) — 8B models ignore the multi-step decision tree. Hardware profiles added ("mac_mini" vs "server") for model selection. DRAMP database matches highlighted in classification evidence. Peptide cascade re-verification: if verification flips peptide value, classification is automatically re-run and re-verified. Deterministic fallback for classification Pass 2 failure. |
| 2026-03-15 | 0.2.0 | Two-phase pipeline (parallel research, sequential annotation). Persistence and resumability with atomic writes. Literature agent expanded to 4 sources (PubMed with abstract fetching, PMC with summaries, Europe PMC, Semantic Scholar). Structured snippets for LLM clarity. PMID deduplication. Resilient HTTP with per-host rate limiting and retry. Resume endpoint. Multi-run consensus strategy documented. Human annotation review with updated inter-rater statistics. |
| 2026-03-15 | 0.1.0 | Initial methodology document. Describes all agents, verification pipeline, cross-field consistency, evidence thresholds, quality scores, output formats, and hardware constraints. |
