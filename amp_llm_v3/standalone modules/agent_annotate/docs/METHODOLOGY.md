# Agent Annotate -- Technical Methodology

## 1. System Overview

Agent Annotate is a three-phase pipeline for annotating clinical trials involving antimicrobial peptides (AMPs) with publication-grade accuracy. All inference runs locally via Ollama-hosted language models. The pipeline processes trial records from ClinicalTrials.gov and produces structured annotations across five fields.

The three phases execute sequentially per trial:

1. **Phase 1 -- Research.** Four parallel agents gather evidence from external data sources (registries, literature, protein databases, web search).
2. **Phase 2 -- Annotation.** Five agents each annotate one field, consuming the research dossier from Phase 1.
3. **Phase 3 -- Verification.** Three blind verifiers independently review each annotation, followed by consensus checking and reconciliation for disputes.


## 2. AMP Classification Framework

### 2.1 Definition

Antimicrobial peptides (AMPs), also called host defense peptides, are short peptides that contribute to pathogen defense. The pipeline classifies AMPs by four modes of action. A peptide therapeutic must fit at least one of these modes to be considered an AMP.

### 2.2 Four Modes of Action

**Mode A -- Direct Antimicrobial**
Peptides that directly kill or inhibit pathogens through membrane disruption, pore formation, or intracellular targeting. Examples: colistin, polymyxin B, melittin.

**Mode B -- Immunostimulatory / Host Defense**
Peptides that promote immune defense against pathogens (not suppress it). Examples: LL-37, defensins, thymosin alpha-1.

**Mode C -- Anti-Biofilm**
Peptides that disrupt or prevent microbial biofilm formation. Examples: LL-37, DJK-5, IDR-1018.

**Mode D -- Pathogen-Targeting Vaccines / Immunogens**
Peptide-based vaccines designed to elicit immune responses against specific pathogens. Examples: StreptInCor, peptide HIV vaccines.

### 2.3 Key Distinction

Promoting defense against pathogens qualifies as AMP activity. Suppressing immunity does not. This distinction is critical for borderline cases -- an immunosuppressive peptide is classified as "Other" regardless of its peptide nature.


## 3. Annotation Fields

Each trial receives annotations for five fields. The allowed values for each field are fixed.

### 3.1 Classification

Categorizes the trial's relationship to AMPs.

| Value | Meaning |
|---|---|
| AMP(infection) | Trial involves an AMP used in an infection context |
| AMP(other) | Trial involves an AMP in a non-infection context (e.g., wound healing, anti-biofilm without active infection) |
| Other | Trial does not involve an AMP |

### 3.2 Delivery Mode

The route of administration. 18 valid values:

IV, IM, SC, Intranasal, Oral (swallowed), Oral (topical/rinse), Oral (lozenge/troche), Oral (sublingual), Topical (skin), Topical (wound), Topical (eye/ophthalmic), Topical (ear/otic), Topical (nasal), Topical (vaginal), Topical (rectal), Inhalation, Other, empty (when not determinable).

### 3.3 Outcome

The current status or result of the trial.

| Value | Meaning |
|---|---|
| Positive | Trial completed with positive or acceptable results |
| Withdrawn | Trial withdrawn before enrollment or dosing |
| Terminated | Trial terminated early (without positive published results) |
| Failed - completed trial | Trial completed but with cited evidence of failure |
| Recruiting | Trial is actively recruiting participants |
| Active not recruiting | Trial is ongoing but no longer recruiting |
| Unknown | Insufficient evidence to determine outcome |

### 3.4 Reason for Failure

Applies only when a trial has failed or terminated. Otherwise left empty.

| Value | Meaning |
|---|---|
| Business Reason | Sponsor decision, funding, strategic pivot |
| Ineffective for purpose | Did not meet primary efficacy endpoints |
| Toxic/Unsafe | Safety signals, adverse events |
| Due to covid | COVID-19 disrupted trial conduct |
| Recruitment issues | Insufficient enrollment |
| *(empty)* | Trial did not fail, or no failure reason determinable |

### 3.5 Peptide

Boolean field (True/False) indicating whether the intervention is a peptide.


## 4. Phase 1 -- Research Agents

Four research agents run in parallel, each querying different external sources. Every source carries a fixed quality weight reflecting its reliability for AMP clinical trial annotation.

### 4.1 Clinical Protocol Agent

Queries trial registries and drug databases for protocol-level data (design, arms, interventions, status).

| Source | Weight |
|---|---|
| ClinicalTrials.gov | 0.95 |
| OpenFDA | 0.85 |

### 4.2 Literature Agent

Queries biomedical literature for published results, methods, and outcome data.

| Source | Weight |
|---|---|
| PubMed | 0.90 |
| PMC | 0.85 |
| PMC BioC | 0.80 |

### 4.3 Peptide Identity Agent

Queries protein and peptide databases to determine the molecular identity and AMP classification of the intervention.

| Source | Weight |
|---|---|
| UniProt | 0.95 |
| DRAMP | 0.80 |

### 4.4 Web Context Agent

Queries general web search for supplementary context (press releases, conference reports, regulatory decisions).

| Source | Weight |
|---|---|
| DuckDuckGo | 0.40 |
| SerpAPI | 0.50 |
| Google Scholar | 0.70 |


## 5. Phase 2 -- Annotation Agents

Five annotation agents each handle one field. They consume the combined research dossier from Phase 1. Agents fall into two categories by design.

### 5.1 Single-Pass Agents

These agents make one LLM call to produce their annotation.

- **Classification Agent**
- **Delivery Mode Agent**
- **Peptide Agent**

### 5.2 Two-Pass Investigative Agents

These agents make two sequential LLM calls: an investigative pass that extracts and organizes evidence, followed by a decision pass that uses the extracted evidence to produce the annotation.

- **Outcome Agent**
- **Failure Reason Agent**

### 5.3 Classification Agent (v3)

Determines whether the trial involves an AMP and, if so, whether the context is infection-related.

The v3 prompt includes explicit negative examples to reduce over-classification:

- **Peptide T** -- a neuropeptide, not an AMP
- **dnaJP1** -- an immunosuppressant peptide, not an AMP
- **GLP-1 analogues** (e.g., semaglutide) -- metabolic peptides, not AMPs
- **GnRH analogues** -- endocrine peptides, not AMPs
- **Radiolabeled peptides** -- diagnostic agents, not AMPs
- **Structural peptides** -- collagen fragments, etc., not AMPs

The governing rule: "Being a peptide does NOT make something an AMP. MOST peptide therapeutics are NOT AMPs." When in doubt, the agent classifies as "Other."

### 5.4 Delivery Mode Agent (v3)

Extracts the route of administration from trial data. Uses a priority-ordered extraction strategy:

1. Arms/Interventions section of the registry record (highest priority)
2. Detailed Description field
3. Published literature methods sections
4. Drug label information
5. Intervention name keywords (lowest priority)

Includes a keyword mapping layer that normalizes abbreviations to canonical values (SC, IM, IV, PO, etc.).

### 5.5 Outcome Agent (v3)

**Pass 1:** Extracts four evidence elements from the research dossier:
- Registry status (e.g., Completed, Terminated, Recruiting)
- Trial phase
- Published results (if any)
- Result valence (positive, negative, mixed, absent)

**Pass 2:** Applies a calibrated decision tree to the extracted evidence, evaluated in strict order:

1. Registry status is Recruiting or Active not recruiting --> annotate as Recruiting or Active not recruiting.
2. Registry status is Withdrawn --> annotate as Withdrawn.
3. Published positive results exist --> annotate as Positive. Phase I trials that complete with acceptable safety data are considered positive.
4. Published negative results exist --> annotate as Failed - completed trial. This requires cited evidence of failure -- a paper, a press release, or a regulatory decision.
5. Registry status is Terminated with no positive published results --> annotate as Terminated.
6. No published results, ambiguous status --> annotate as Unknown.

Critical rule: A "Completed" registry status alone does NOT indicate failure. "Failed - completed trial" requires cited evidence that the trial failed to meet its endpoints or was otherwise unsuccessful.

### 5.6 Failure Reason Agent (v3)

**Pass 1:** Investigates all available evidence for failure signals -- adverse event reports, efficacy data, sponsor announcements, regulatory actions, COVID-related disruptions, enrollment data.

**Pass 2:** Classifies the reason for failure, but only if Pass 1 identified actual failure signals.

The agent includes an enhanced short-circuit mechanism for non-failures. Before classifying a failure reason, the agent checks for:
- Positive outcome signals (published positive results, successful Phase I completion)
- Active or recruiting status
- Any indication the trial is ongoing or successful

The short-circuit is not a simple string match for "No" -- it evaluates the full evidence context for positive signals. If positive signals are found, the agent returns an empty value (no failure reason).

### 5.7 Peptide Agent

Determines whether the trial intervention is a peptide (True/False). Consults the Peptide Identity research dossier (UniProt, DRAMP) as primary evidence.


## 6. Phase 3 -- Verification Pipeline

### 6.1 Blind Peer Review

Three verifier models independently review each annotation. The verifiers never see the primary annotation -- they receive only the research dossier and the annotation field definition, then produce their own annotation.

| Verifier | Model |
|---|---|
| Verifier 1 | gemma2:9b |
| Verifier 2 | qwen2:latest |
| Verifier 3 | mistral:latest |

### 6.2 Consensus

The consensus threshold is 1.0 (unanimous agreement required). If all three verifiers agree with each other, that value is accepted. If any verifier disagrees, the annotation is escalated to reconciliation.

### 6.3 Reconciliation

Disputed annotations are sent to a reconciler model (qwen2.5:14b) that receives:
- The primary annotation
- All three verifier annotations
- The full research dossier

The reconciler produces a final annotation with justification.

### 6.4 Manual Review Escalation

Cases that the reconciler cannot resolve (e.g., contradictory evidence, ambiguous trial designs) are flagged for manual human review.


## 7. Evidence Thresholds

Each annotation field has a minimum evidence requirement. An annotation is only produced when the research dossier meets or exceeds both the minimum source count and the minimum quality score.

| Field | Min Sources | Min Quality |
|---|---|---|
| Classification | 2 | 0.50 |
| Delivery Mode | 2 | 0.50 |
| Outcome | 2 | 0.50 |
| Reason for Failure | 1 | 0.30 |
| Peptide | 2 | 0.50 |

Reason for failure has a lower threshold because it depends on the outcome determination -- when a trial has not failed, there is no failure reason to support with evidence.


## 8. Concordance Analysis Methodology

### 8.1 Purpose

Concordance analysis compares agent annotations against human annotations to evaluate system accuracy. Two independent human annotators (R1 and R2) annotated the same trial set.

### 8.2 Blank Handling (v2 Protocol)

The v2 concordance protocol excludes blank or empty human annotations from concordance calculations. The rationale: a blank annotation means the annotator did not annotate the field, not that the annotator chose an empty value.

One exception: for the reason_for_failure field, empty IS a valid annotation (meaning "no failure"). A reason_for_failure value is only treated as blank (excluded) when the corresponding outcome field was also blank -- indicating the annotator skipped both fields.

### 8.3 Inter-Annotator Reliability

Cohen's kappa is computed for each field to measure inter-annotator agreement beyond chance. This applies to both agent-vs-human and human-vs-human comparisons.


## 9. Baseline Results

These results are from the 25-trial concordance analysis using v2 agents (before the v3 improvements described in Sections 5.3--5.6). All percentages are with blank annotations excluded per the v2 protocol.

### 9.1 Agreement Rates

| Field | Agent vs R1 | Agent vs R2 | R1 vs R2 |
|---|---|---|---|
| Classification | 48.0% | 40.0% | 76.0% |
| Delivery Mode | 37.5% | 41.7% | 73.9% |
| Outcome | 29.2% | 21.1% | 78.9% |
| Failure Reason | 33.3% | 31.6% | 94.7% |
| Peptide | -- | 88.0% | -- |

Peptide only has Agent vs R2 because R1 had no peptide annotations in the concordance set.

### 9.2 Interpretation

Agent-human agreement is consistently lower than human-human agreement. However, the human-human agreement rates themselves reveal substantial disagreement (73--79% for most fields), indicating that "ground truth" is not straightforward even for trained annotators.


## 10. Known Issues and v3 Fixes

### 10.1 Outcome Bias (v2)

**Problem:** The v2 outcome agent labeled approximately 80% of trials as "Failed - completed trial," including trials that were still recruiting, had positive results, or had simply completed without published data.

**Fix (v3):** Replaced the single-prompt approach with the calibrated two-pass decision tree described in Section 5.5. The decision tree enforces ordering (check recruiting/active first, check for positive results before considering failure) and requires cited evidence for a "Failed" label.

### 10.2 Over-Classification as AMP (v2)

**Problem:** The v2 classification agent over-classified peptide therapeutics as AMPs. Any peptide in a clinical trial tended to receive an AMP classification.

**Fix (v3):** Added explicit negative examples and the governing rule that most peptide therapeutics are not AMPs (Section 5.3). Added a default-to-Other heuristic for ambiguous cases.

### 10.3 Empty Delivery Modes (v2)

**Problem:** The v2 delivery mode agent returned empty or overly generic values for many trials where the route was determinable from the registry data.

**Fix (v3):** Implemented priority-ordered extraction with keyword mapping (Section 5.4). The agent now systematically searches multiple sections of the trial record before returning empty.

### 10.4 Failure Reasons for Non-Failed Trials (v2)

**Problem:** The v2 failure reason agent sometimes assigned failure reasons to trials that had not actually failed (e.g., recruiting trials, trials with positive results).

**Fix (v3):** Enhanced the short-circuit mechanism to check for positive signals before attempting failure classification (Section 5.6). The short-circuit now evaluates full evidence context rather than matching a single keyword.

### 10.5 8B Model Limitations

**Problem:** 8B-parameter models (the size used for most annotation and verification agents) tend to ignore worked examples provided in prompts. Even when the prompt includes detailed examples showing correct annotation behavior, the models frequently deviate from the demonstrated patterns.

**Implication:** This is the strongest argument for using the 14B-parameter reconciler (qwen2.5:14b) as the primary annotator rather than the 8B models. The 14B model shows better instruction-following and example adherence. This tradeoff is under evaluation.


## 11. Human Annotation Reliability

### 11.1 Annotator Divergence

The two independent human annotators (R1 = Emily, R2 = Anat) showed substantial disagreement on several fields, demonstrating that human annotations are not infallible ground truth.

Key divergences observed:

- **Peptide field:** R1 annotated Peptide=True for 451 trials (24% of the dataset). R2 annotated Peptide=True for 56 trials (3%). This indicates fundamentally different working definitions of "peptide."
- **Outcome field:** R1 used "Recruiting" 222 times. R2 used "Recruiting" 0 times. This suggests different interpretations of whether to record current registry status or inferred clinical outcome.
- **Peptide coverage:** Only 30 trials in the full dataset had the Peptide field filled in by both annotators, severely limiting concordance analysis for that field.

### 11.2 Practical Implication

Human annotations serve as development-time benchmarks for calibrating and improving the pipeline. They are not treated as infallible ground truth. Where human annotators disagree, the agent's annotation is evaluated against both independently, and neither human annotator is presumed correct by default.


## 12. Multi-Run Consensus

### 12.1 Approach

LLM outputs are nondeterministic. Running the same batch of trials through the pipeline multiple times (recommended N=3) and taking a majority vote per field reduces the impact of stochastic variation on any single annotation.

### 12.2 Implementation Status

Multi-run consensus is planned but not yet implemented as an automated feature. It can currently be approximated by running the pipeline multiple times and comparing outputs manually.

### 12.3 Expected Benefit

Fields where the pipeline is uncertain (low evidence quality, borderline classification) are most likely to vary across runs. Majority vote surfaces these cases: a field that receives different annotations across three runs is a natural candidate for manual review, while a field that is unanimous across runs has higher confidence.


## 13. Source Weight Rationale

Source weights reflect two factors: data reliability and relevance to clinical trial annotation.

- **ClinicalTrials.gov (0.95)** and **UniProt (0.95)** are authoritative primary sources with structured, curated data.
- **PubMed (0.90)** and **PMC (0.85)** contain peer-reviewed literature but require interpretation (the model must extract relevant information from unstructured text).
- **OpenFDA (0.85)** and **DRAMP (0.80)** are curated databases but with narrower coverage or less frequent updates.
- **PMC BioC (0.80)** is structured full-text but with potential parsing artifacts.
- **Google Scholar (0.70)** captures preprints and non-indexed publications but with lower curation.
- **SerpAPI (0.50)** and **DuckDuckGo (0.40)** are general web search -- useful for press releases and regulatory decisions, but noisy and unverified.
