# Agent Annotate -- Technical Methodology

## 1. System Overview

Agent Annotate is a three-phase pipeline for annotating clinical trials involving antimicrobial peptides (AMPs) with publication-grade accuracy. All inference runs locally via Ollama-hosted language models. The pipeline processes trial records from ClinicalTrials.gov and produces structured annotations across five fields.

The three phases execute sequentially per trial:

1. **Phase 1 -- Research.** Fifteen parallel agents gather evidence from 20+ free external databases (registries, literature, protein databases, peptide activity databases, structure databases, pharmacology databases, interaction databases, resistance databases, international trial registries).
2. **Phase 2 -- Annotation.** Five agents each annotate one field, consuming the research dossier from Phase 1.
3. **Phase 3 -- Verification.** Three blind verifiers independently review each annotation, followed by consensus checking and reconciliation for disputes.

### 1.1 Output Traceability

Every annotation in the output includes full citation traceability:

- **Model identity**: Which LLM produced each annotation and each verification opinion.
- **Agent provenance**: Which research agent contributed evidence for each field.
- **Source URLs**: Direct links to the external data sources consulted (ClinicalTrials.gov, PubMed, UniProt, DBAASP, ChEMBL, RCSB PDB, EBI Proteins, APD, dbAMP, WHO ICTRP, IUPHAR, IntAct, CARD, PDBe, etc.).
- **Evidence text**: The extracted evidence passages that informed the annotation decision.
- **Verifier summary**: Each verifier's independent opinion and reasoning chain.

### 1.2 Operational Metadata

Each annotation job records:

- **Timestamps**: `started_at` and `finished_at` in Pacific time (America/Los_Angeles) throughout the system.
- **Elapsed time**: Total wall-clock time for the job and average time per trial.
- **Commit hash**: The exact git commit of the codebase used for the run, embedded in job metadata for reproducibility.

### 1.3 Disk-Persisted Review Queue

The review queue (trials flagged for manual review) is persisted to disk and survives service restarts. Previously, queued review items were lost on restart; the v4 implementation writes the queue to a JSON file that is reloaded on startup.


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

Fifteen research agents run in parallel, each querying different external sources. Every source carries a fixed quality weight reflecting its reliability for AMP clinical trial annotation. The v4 pipeline added four specialized agents (Sections 4.5--4.8) for peptide activity, bioactivity, structural, and protein sequence data. The v5 expansion added seven more agents (Sections 4.9--4.15) covering additional peptide databases, international trial registries, pharmacology, molecular interactions, antibiotic resistance, and structure quality. SerpAPI was removed (paid service); all 15 agents now use free APIs exclusively.

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
| Google Scholar | 0.70 |

Note: SerpAPI was removed from this agent as it requires a paid subscription. All research agents now use free APIs exclusively.

### 4.5 DBAASP Agent (v4)

Queries the Database of Antimicrobial Activity and Structure of Peptides (DBAASP) for peptide activity data. This agent provides direct evidence of antimicrobial activity, which is critical for the classification decision.

| Source | Weight |
|---|---|
| DBAASP API | 0.85 |

**Data provided**: Minimum inhibitory concentration (MIC) values against specific organisms, hemolytic activity, antimicrobial spectrum, peptide structure-activity relationships. DBAASP is the most comprehensive public database of experimentally validated AMP activity data.

**Role in pipeline**: Provides ground-truth antimicrobial activity data that directly informs the Classification Agent. A peptide with documented MIC values in DBAASP is strong evidence for AMP classification; absence from DBAASP does not rule out AMP status but lowers confidence.

### 4.6 ChEMBL Agent (v4)

Queries the ChEMBL database (EMBL-EBI) for bioactivity and clinical phase data on the trial intervention.

| Source | Weight |
|---|---|
| ChEMBL API | 0.85 |

**Data provided**: Bioactivity assay results, clinical development phase, mechanism of action, target information, compound properties. ChEMBL aggregates pharmacological data from medicinal chemistry literature.

**Role in pipeline**: Provides clinical development context (which phase the compound has reached across all trials, not just the one being annotated) and mechanism-of-action data that helps distinguish true antimicrobial mechanisms from other peptide therapeutics. Also useful for the Outcome Agent, as ChEMBL captures development status across multiple trials of the same compound.

### 4.7 RCSB PDB Agent (v4)

Queries the RCSB Protein Data Bank for 3D structural metadata of the intervention compound.

| Source | Weight |
|---|---|
| RCSB PDB API | 0.80 |

**Data provided**: Structural classification, molecular weight, chain length, experimental method (X-ray, NMR, cryo-EM), organism source, ligand/binding information.

**Role in pipeline**: Provides structural confirmation that a compound is a peptide (chain length, amino acid composition) and can reveal mechanism-of-action clues through binding site analysis. Particularly useful for the Peptide Agent and for resolving ambiguous cases where the compound name does not clearly indicate peptide identity.

### 4.8 EBI Proteins Agent (v4)

Queries the EBI Proteins API (UniProt programmatic access via EMBL-EBI) for protein/peptide sequence data and functional annotations.

| Source | Weight |
|---|---|
| EBI Proteins API | 0.85 |

**Data provided**: Amino acid sequences, post-translational modifications, variant information, functional annotations, subcellular localization, gene ontology terms.

**Role in pipeline**: Complements UniProt (Section 4.3) with additional sequence and variant data accessible through the EBI programmatic interface. Provides sequence-level confirmation of peptide identity and functional annotations that help distinguish antimicrobial function from other peptide activities.

### 4.9 APD Agent (v5)

Queries the Antimicrobial Peptide Database (APD) at aps.unmc.edu for curated AMP records.

| Source | Weight |
|---|---|
| APD (HTML scraping) | 0.80 |

**Data provided**: AMP classifications, activity annotations, peptide sequences, source organism data. APD is one of the earliest and most widely cited AMP databases, with curated records for natural and synthetic antimicrobial peptides.

**Role in pipeline**: Provides an independent AMP classification source that complements DRAMP (Section 4.3) and DBAASP (Section 4.5). A peptide present in APD is strong evidence for AMP status. Note: the APD server requires JavaScript rendering for some pages, so data retrieval is best-effort via HTML scraping.

### 4.10 dbAMP Agent (v5)

Queries the dbAMP 3.0 database at yylab.jnu.edu.cn/dbAMP for comprehensive AMP annotations.

| Source | Weight |
|---|---|
| dbAMP 3.0 (HTML scraping) | 0.80 |

**Data provided**: AMP sequences, functional annotations, antimicrobial activity data, target organism information. dbAMP 3.0 contains over 33,000 AMP entries with experimentally validated annotations.

**Role in pipeline**: Provides a large-scale AMP reference complementing APD and DRAMP. The database's breadth (33K+ entries) increases the likelihood of finding annotation data for less-studied peptides. Note: dbAMP availability is intermittent; the agent handles connection failures gracefully.

### 4.11 WHO ICTRP Agent (v5)

Queries the WHO International Clinical Trials Registry Platform (ICTRP) at trialsearch.who.int for international trial registry data.

| Source | Weight |
|---|---|
| WHO ICTRP (HTML parsing) | 0.85 |

**Data provided**: Trial registration data from international registries (EU Clinical Trials Register, ISRCTN, ANZCTR, ChiCTR, CTRI, etc.), trial status, intervention descriptions, conditions, sponsor information.

**Role in pipeline**: Extends the Clinical Protocol Agent's ClinicalTrials.gov coverage to international registries. Many AMP trials are conducted outside the US and may only be registered in non-US registries. ICTRP aggregates data from 17+ national and regional registries, providing global trial coverage that ClinicalTrials.gov alone cannot offer.

### 4.12 IUPHAR Guide to Pharmacology Agent (v5)

Queries the IUPHAR/BPS Guide to Pharmacology at guidetopharmacology.org via its REST API for pharmacological data.

| Source | Weight |
|---|---|
| IUPHAR Guide to Pharmacology (REST API) | 0.85 |

**Data provided**: Mechanism of action, drug targets, ligand classification, receptor-ligand interactions, approved drug status, clinical indication data.

**Role in pipeline**: Provides authoritative pharmacological context for AMP classification decisions. IUPHAR's curated mechanism-of-action data helps the Classification Agent distinguish direct antimicrobial mechanisms (Mode A) from immunomodulatory (Mode B) and other peptide therapeutic activities. The ligand classification data also informs the Peptide Agent by confirming whether an intervention is classified as a peptide ligand.

### 4.13 IntAct Agent (v5)

Queries the IntAct molecular interaction database at ebi.ac.uk/intact via its REST API for protein-protein and peptide-target interaction data.

| Source | Weight |
|---|---|
| IntAct (REST API) | 0.75 |

**Data provided**: Molecular interactions, interaction types, detection methods, UniProt cross-references, interaction partners, confidence scores.

**Role in pipeline**: Provides molecular interaction data that can reveal an AMP's mechanism of action. Interactions with membrane proteins or microbial targets support direct antimicrobial classification, while interactions with immune receptors support immunomodulatory classification. UniProt cross-references enable linking interaction data back to the Peptide Identity Agent's findings.

### 4.14 CARD Agent (v5)

Queries the Comprehensive Antibiotic Resistance Database (CARD) at card.mcmaster.ca via AJAX endpoints for antibiotic resistance data.

| Source | Weight |
|---|---|
| CARD (AJAX endpoints) | 0.80 |

**Data provided**: Resistance mechanisms, Antibiotic Resistance Ontology (ARO) terms, resistance gene annotations, drug class classifications, resistance determinant data.

**Role in pipeline**: Provides antibiotic resistance context relevant to AMP clinical trials. If a trial's target pathogen has documented resistance mechanisms in CARD, this informs the Classification Agent's assessment of the AMP's clinical relevance. CARD's ARO terms also help classify the mechanism of action for peptide antibiotics, distinguishing membrane-targeting AMPs from those with intracellular targets.

### 4.15 PDBe Agent (v5)

Queries the European Protein Data Bank (PDBe) at ebi.ac.uk/pdbe via Solr search and REST APIs for structure quality metrics.

| Source | Weight |
|---|---|
| PDBe (Solr search + REST API) | 0.80 |

**Data provided**: Structure quality metrics (resolution, R-factor, Ramachandran analysis), experimental method details, deposition metadata, cross-references to UniProt and other databases.

**Role in pipeline**: Complements the RCSB PDB Agent (Section 4.7) with European PDB data and structure quality metrics. While RCSB PDB provides structural classification and molecular weight, PDBe adds resolution and R-factor data that indicate the reliability of structural information. Higher-quality structures provide more trustworthy evidence for peptide identity and mechanism-of-action analysis.


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

### 5.3 Classification Agent (v4)

Determines whether the trial involves an AMP and, if so, whether the context is infection-related.

The v3 prompt includes explicit negative examples to reduce over-classification:

- **Peptide T** -- a neuropeptide, not an AMP
- **dnaJP1** -- an immunosuppressant peptide, not an AMP
- **GLP-1 analogues** (e.g., semaglutide) -- metabolic peptides, not AMPs
- **GnRH analogues** -- endocrine peptides, not AMPs
- **Radiolabeled peptides** -- diagnostic agents, not AMPs
- **Structural peptides** -- collagen fragments, etc., not AMPs

The governing rule: "Being a peptide does NOT make something an AMP. MOST peptide therapeutics are NOT AMPs." When in doubt, the agent classifies as "Other."

**v4 improvement -- direct antimicrobial mechanism requirement**: The v4 prompt adds a stricter classification gate. To receive an AMP classification, the intervention must have a *direct* antimicrobial mechanism fitting one of the four modes (Section 2.2). Indirect relationships to infection (e.g., a peptide used in a wound context where infection is secondary) no longer automatically qualify as AMP(infection). The agent must identify which specific mode of action applies and cite evidence for it.

### 5.4 Delivery Mode Agent (v4)

Extracts the route of administration from trial data. Uses a priority-ordered extraction strategy:

1. Arms/Interventions section of the registry record (highest priority)
2. Detailed Description field
3. Published literature methods sections
4. Drug label information
5. Intervention name keywords (lowest priority)

Includes a keyword mapping layer that normalizes abbreviations to canonical values (SC, IM, IV, PO, etc.).

**v4 improvement -- never-guess reinforcement**: The v4 prompt adds explicit reinforcement that the agent must never guess a delivery mode. If the route of administration cannot be determined from the available evidence, the agent must return empty rather than inferring from the compound type or therapeutic context. This addresses cases where the v3 agent guessed "IM" for vaccines or "Oral" for peptides without cited evidence.

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

### 5.6 Failure Reason Agent (v4)

**Pass 1:** Investigates all available evidence for failure signals -- adverse event reports, efficacy data, sponsor announcements, regulatory actions, COVID-related disruptions, enrollment data.

**Pass 2:** Classifies the reason for failure, but only if Pass 1 identified actual failure signals.

The agent includes an enhanced short-circuit mechanism for non-failures. Before classifying a failure reason, the agent checks for:
- Positive outcome signals (published positive results, successful Phase I completion)
- Active or recruiting status
- Any indication the trial is ongoing or successful

The short-circuit is not a simple string match for "No" -- it evaluates the full evidence context for positive signals. If positive signals are found, the agent returns an empty value (no failure reason).

**v4 improvement -- default no-failure for completed trials**: The v4 prompt changes the default behavior for trials that completed without explicit failure evidence. Previously, the agent would sometimes assign "Ineffective for purpose" to completed trials lacking published results. The v4 prompt instructs the agent that a completed trial with no published negative results should default to an empty failure reason (no failure), not "Ineffective for purpose." Failure reason requires affirmative evidence of failure, mirroring the Outcome Agent's rule that completion does not imply failure.

### 5.7 Peptide Agent (v4)

Determines whether the trial intervention is a peptide (True/False). Consults the Peptide Identity research dossier (UniProt, DRAMP) as primary evidence, supplemented by RCSB PDB and EBI Proteins data from the new v4 research agents.

**v4 improvement -- brand name rules**: The v4 prompt adds explicit handling for brand-name interventions. When the trial intervention is a brand name (e.g., "Solostar," "Ozempic"), the agent must resolve the brand name to its generic compound and determine peptide status based on the generic identity, not the brand name alone. The prompt includes examples of brand names that resolve to non-peptide compounds.


## 6. Phase 3 -- Verification Pipeline

### 6.1 Blind Peer Review

Three verifier models independently review each annotation. The verifiers never see the primary annotation -- they receive only the research dossier and the annotation field definition, then produce their own annotation.

| Verifier | Model |
|---|---|
| Verifier 1 | gemma2:9b |
| Verifier 2 | qwen2:latest |
| Verifier 3 | mistral:latest |

**v4 verifier prompt improvements**: The v4 verifier prompts now receive the same level of field-specific detail as the primary annotation agents, including negative examples, decision trees, and extraction hierarchies. In v3, verifiers received condensed instructions, creating an asymmetry where verifiers lacked the context to make accurate independent judgments. The v4 parity ensures that verifier disagreements reflect genuine evidence ambiguity rather than instruction gaps.

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

### 6.5 Value Normalization in Verification

#### 6.5.1 Problem

Verifier models (8B--9B parameters) frequently output trial status keywords or free-text explanations instead of valid field values. For the `reason_for_failure` field, verifiers would return values such as "COMPLETED", "Unknown", "N/A", "ACTIVE_NOT_RECRUITING", or verbose explanations like "The trial was completed successfully so there is no failure reason" instead of the expected empty string. These invalid values caused false disagreements during consensus checking, inflating the number of trials flagged for manual review and reconciliation.

#### 6.5.2 Parsing Rules

Value normalization applies two parsing strategies in order:

1. **Prefix matching for verbose explanations.** If the verifier output starts with a valid value (e.g., "Ineffective for purpose because the trial did not meet its primary endpoint"), the valid prefix is extracted. This catches cases where verifiers append explanations to their answers.

2. **Exact match for status keywords.** If the output exactly matches a known status keyword or status-like value, it is mapped to the canonical field value. For `reason_for_failure`, all status-like values map to empty string (no failure reason).

#### 6.5.3 Canonical Mapping for reason_for_failure

The following values are normalized to empty string (meaning "no failure reason"):

| Input Value | Rationale |
|---|---|
| COMPLETED | Trial status, not a failure reason |
| Unknown | Ambiguous status, not a valid failure reason value |
| N/A | Verifier shorthand for "not applicable" |
| None | Verifier shorthand for "no failure" |
| ACTIVE_NOT_RECRUITING | Trial status, not a failure reason |
| RECRUITING | Trial status, not a failure reason |
| WITHDRAWN | Trial status (handled by outcome field) |
| TERMINATED | Trial status (handled by outcome field) |

#### 6.5.4 Field-Aware Consensus Normalization

Normalization rules differ by field because valid values and common verifier errors differ:

- **reason_for_failure**: Status keywords and "N/A"/"None"/"Unknown" all normalize to empty string. This is the field most affected by verifier parsing failures.
- **outcome**: Status keywords normalize to their canonical outcome values (e.g., "COMPLETED" is not a valid outcome value and is flagged).
- **classification**: "AMP" alone is flagged as ambiguous (must specify infection or other).
- **delivery_mode**: Route abbreviations normalize to canonical values (e.g., "Intravenous" to "IV").
- **peptide**: Boolean normalization ("true"/"yes" to "True", "false"/"no" to "False").

#### 6.5.5 Retroactive Fix Capability

The normalization logic can be applied retroactively to completed jobs via `retroactive_fix.py`. This script re-reads the stored verifier opinions for each trial, applies the expanded normalization rules, recalculates consensus, and updates the job results. Trials that were previously flagged for review due to false disagreements are unflagged when normalization restores consensus. See the User Guide for usage details.


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

### 8.4 Impact of Value Normalization on Concordance

Verifier value normalization (Section 6.5) directly affects concordance calculations because it changes which trials achieve consensus and which are flagged for review. Retroactive application of the expanded normalization rules to 11 completed jobs produced the following impact:

- **74 individual field values corrected** across all affected jobs (verifier opinions remapped from status keywords to valid values).
- **12 consensus results restored** (fields that previously showed disagreement now achieve unanimous verifier agreement after normalization).
- **12 trials unflagged** from manual review queues (trials that were flagged solely due to false disagreements caused by verifier parsing failures).

This means concordance numbers calculated before the normalization fix understate actual pipeline accuracy. Any concordance analysis should be recalculated after retroactive fixes are applied to ensure reported agreement rates reflect genuine disagreements rather than parsing artifacts.


## 9. Baseline Results

### 9.1 v2 Baseline (n=25)

These results are from the 25-trial concordance analysis using v2 agents (before the v3 improvements described in Sections 5.3--5.6). All percentages are with blank annotations excluded per the v2 protocol.

#### 9.1.1 Agreement Rates (v2, n=25)

| Field | Agent vs R1 | Agent vs R2 | R1 vs R2 |
|---|---|---|---|
| Classification | 48.0% | 40.0% | 76.0% |
| Delivery Mode | 37.5% | 41.7% | 73.9% |
| Outcome | 29.2% | 21.1% | 78.9% |
| Failure Reason | 33.3% | 31.6% | 94.7% |
| Peptide | -- | 88.0% | -- |

Peptide only has Agent vs R2 because R1 had no peptide annotations in the concordance set.

#### 9.1.2 Interpretation (v2)

Agent-human agreement is consistently lower than human-human agreement. However, the human-human agreement rates themselves reveal substantial disagreement (73--79% for most fields), indicating that "ground truth" is not straightforward even for trained annotators.

### 9.2 v3 Concordance Results (n=62)

An expanded concordance analysis was run overnight using v3 agents on 62 trials. These results establish the pre-v4 baseline on a larger, more representative sample.

#### 9.2.1 Agreement Rates (v3, n=62)

| Field | Agent vs R1 | Agent vs R2 | Notes |
|---|---|---|---|
| Classification | 29.4% | 13.0% | Agent over-classifies as AMP; many non-AMP peptides receive AMP labels |
| Delivery Mode | 47.6% | 54.1% | Best-performing field; extraction logic works well for clear cases |
| Outcome | 37.1% | 60.5% | Agent defaults to Unknown too frequently; misses published positive results |
| Failure Reason | 41.9% | 43.5% | Agent over-assigns "Ineffective for purpose" to trials without failure evidence |
| Peptide | 66.7% | 60.0% | Regression from v2 on this larger sample; brand name resolution issues |

#### 9.2.2 Interpretation (v3, n=62)

The n=62 results reveal several systematic problems that the v4 agent improvements (Sections 5.3--5.7) target directly:

1. **Classification over-classification (29.4% / 13.0%)**: The agent assigns AMP classifications too aggressively. The v4 fix (Section 5.3) requires a direct antimicrobial mechanism and strengthens the default-to-Other behavior.

2. **Delivery Mode is the strongest field (47.6% / 54.1%)**: The extraction hierarchy and keyword mapping work well. The v4 never-guess reinforcement (Section 5.4) should prevent the remaining errors where the agent guesses routes without evidence.

3. **Outcome defaults to Unknown too much (37.1% / 60.5%)**: The asymmetry between R1 and R2 agreement reflects the Recruiting/Unknown divergence between human annotators. The agent agrees more with R2 (who checked literature) than R1 (who recorded registry status). The v4 improvements should help the agent find published results more reliably with the additional research agents.

4. **Failure Reason over-assigns Ineffective (41.9% / 43.5%)**: The v4 default-no-failure fix (Section 5.6) directly addresses this by requiring affirmative failure evidence before assigning any failure reason.

5. **Peptide brand name issues (66.7% / 60.0%)**: The v4 brand name rules (Section 5.7) address cases where the agent failed to resolve brand names to their generic compounds.


## 10. Hardware Profiles and Model Configuration

### 10.1 Hardware Profiles

The pipeline supports two hardware profiles that configure model selection and Ollama behavior:

| Profile | Hardware | Primary Annotator | Ollama keep_alive |
|---|---|---|---|
| `mac_mini` | Mac Mini M4, 16 GB | llama3.1:8b | 5 minutes |
| `server` | Dedicated server, 48+ GB | Kimi K2 Thinking (via OpenRouter or local) | 60 minutes |

The `mac_mini` profile uses shorter `keep_alive` (5 minutes) to free GPU memory sooner on constrained hardware. The `server` profile uses a longer `keep_alive` (60 minutes) to avoid repeated model loading on hardware with sufficient memory.

### 10.2 Kimi K2 Thinking

The `server` profile offers Kimi K2 Thinking as the primary annotation model. Kimi K2 is a reasoning-focused model that produces chain-of-thought traces before its final answer, making it better suited for investigative fields (Outcome, Failure Reason) where multi-step reasoning is required. Initial testing suggests improved instruction adherence compared to 8B models on classification and outcome tasks.

### 10.3 Ollama keep_alive Optimization

The `keep_alive` parameter controls how long Ollama retains a model in GPU memory after the last request. The v4 pipeline sets this per-profile:

- **mac_mini (5m)**: Unloads models aggressively to prevent memory pressure on 16 GB unified memory, especially when multiple annotation and verification models must be loaded sequentially.
- **server (60m)**: Keeps models loaded across the full annotation pipeline for a batch, avoiding the overhead of repeated model loading (which can take 10-30 seconds per load on larger models).


## 11. Known Issues and v3/v4 Fixes

### 11.1 Outcome Bias (v2)

**Problem:** The v2 outcome agent labeled approximately 80% of trials as "Failed - completed trial," including trials that were still recruiting, had positive results, or had simply completed without published data.

**Fix (v3):** Replaced the single-prompt approach with the calibrated two-pass decision tree described in Section 5.5. The decision tree enforces ordering (check recruiting/active first, check for positive results before considering failure) and requires cited evidence for a "Failed" label.

### 11.2 Over-Classification as AMP (v2)

**Problem:** The v2 classification agent over-classified peptide therapeutics as AMPs. Any peptide in a clinical trial tended to receive an AMP classification.

**Fix (v3):** Added explicit negative examples and the governing rule that most peptide therapeutics are not AMPs (Section 5.3). Added a default-to-Other heuristic for ambiguous cases.

### 11.3 Empty Delivery Modes (v2)

**Problem:** The v2 delivery mode agent returned empty or overly generic values for many trials where the route was determinable from the registry data.

**Fix (v3):** Implemented priority-ordered extraction with keyword mapping (Section 5.4). The agent now systematically searches multiple sections of the trial record before returning empty.

### 11.4 Failure Reasons for Non-Failed Trials (v2)

**Problem:** The v2 failure reason agent sometimes assigned failure reasons to trials that had not actually failed (e.g., recruiting trials, trials with positive results).

**Fix (v3):** Enhanced the short-circuit mechanism to check for positive signals before attempting failure classification (Section 5.6). The short-circuit now evaluates full evidence context rather than matching a single keyword.

### 11.5 8B Model Limitations

**Problem:** 8B-parameter models (the size used for most annotation and verification agents) tend to ignore worked examples provided in prompts. Even when the prompt includes detailed examples showing correct annotation behavior, the models frequently deviate from the demonstrated patterns.

**Implication:** This is the strongest argument for using the 14B-parameter reconciler (qwen2.5:14b) as the primary annotator rather than the 8B models. The 14B model shows better instruction-following and example adherence. This tradeoff is under evaluation.


## 12. Human Annotation Reliability

### 12.1 Annotator Divergence

The two independent human annotators (R1 = Emily, R2 = Anat) showed substantial disagreement on several fields, demonstrating that human annotations are not infallible ground truth.

Key divergences observed:

- **Peptide field:** R1 annotated Peptide=True for 451 trials (24% of the dataset). R2 annotated Peptide=True for 56 trials (3%). This indicates fundamentally different working definitions of "peptide."
- **Outcome field:** R1 used "Recruiting" 222 times. R2 used "Recruiting" 0 times. This suggests different interpretations of whether to record current registry status or inferred clinical outcome.
- **Peptide coverage:** Only 30 trials in the full dataset had the Peptide field filled in by both annotators, severely limiting concordance analysis for that field.

### 12.2 Practical Implication

Human annotations serve as development-time benchmarks for calibrating and improving the pipeline. They are not treated as infallible ground truth. Where human annotators disagree, the agent's annotation is evaluated against both independently, and neither human annotator is presumed correct by default.


## 13. Multi-Run Consensus

### 13.1 Approach

LLM outputs are nondeterministic. Running the same batch of trials through the pipeline multiple times (recommended N=3) and taking a majority vote per field reduces the impact of stochastic variation on any single annotation.

### 13.2 Implementation Status

Multi-run consensus is planned but not yet implemented as an automated feature. It can currently be approximated by running the pipeline multiple times and comparing outputs manually.

### 13.3 Expected Benefit

Fields where the pipeline is uncertain (low evidence quality, borderline classification) are most likely to vary across runs. Majority vote surfaces these cases: a field that receives different annotations across three runs is a natural candidate for manual review, while a field that is unanimous across runs has higher confidence.


## 14. Source Weight Rationale

Source weights reflect two factors: data reliability and relevance to clinical trial annotation.

- **ClinicalTrials.gov (0.95)** and **UniProt (0.95)** are authoritative primary sources with structured, curated data.
- **PubMed (0.90)** and **PMC (0.85)** contain peer-reviewed literature but require interpretation (the model must extract relevant information from unstructured text).
- **DBAASP (0.85)**, **ChEMBL (0.85)**, and **EBI Proteins (0.85)** are curated specialized databases providing peptide activity, bioactivity, and protein sequence data respectively.
- **WHO ICTRP (0.85)** and **IUPHAR Guide to Pharmacology (0.85)** are authoritative international sources for trial registry data and pharmacological annotations respectively.
- **OpenFDA (0.85)** and **DRAMP (0.80)** are curated databases but with narrower coverage or less frequent updates.
- **APD (0.80)**, **dbAMP 3.0 (0.80)**, **CARD (0.80)**, and **PDBe (0.80)** are specialized curated databases providing AMP classifications, antimicrobial peptide annotations, antibiotic resistance data, and structure quality metrics respectively.
- **RCSB PDB (0.80)** provides experimentally determined structural data with high reliability but coverage limited to compounds with solved structures.
- **PMC BioC (0.80)** is structured full-text but with potential parsing artifacts.
- **IntAct (0.75)** provides molecular interaction data with lower weight reflecting the indirect nature of interaction evidence for AMP classification.
- **Google Scholar (0.70)** captures preprints and non-indexed publications but with lower curation.
- **DuckDuckGo (0.40)** is general web search -- useful for press releases and regulatory decisions, but noisy and unverified.

Note: SerpAPI (previously 0.50) was removed as it requires a paid subscription. All 15 research agents now use free APIs exclusively.
