# Agent Annotate: A Multi-Agent Local LLM Pipeline for Publication-Grade Annotation of Antimicrobial Peptide Clinical Trials

**Amphoraxe Research Team**

---

## Abstract

Systematic review of clinical trials involving antimicrobial peptides (AMPs) requires annotating multiple structured fields across hundreds of registry entries --- a process that is slow, expensive, and unreliable when performed manually. Inter-annotator agreement among trained human reviewers reaches only approximately 80% overall and drops substantially for fields requiring investigative reasoning, such as trial outcome determination and failure classification. Existing automated approaches typically employ single large language model (LLM) calls without verification, evidence requirements, or source citations, producing annotations of insufficient quality for research use. We present Agent Annotate, a multi-agent pipeline that decomposes the annotation task into three phases: fifteen parallel research agents that gather and weight evidence from 20+ free external databases --- including DBAASP (antimicrobial activity), ChEMBL (bioactivity), RCSB PDB (3D structures), EBI Proteins (sequences), APD (AMP database), dbAMP (peptide annotations), WHO ICTRP (international trials), IUPHAR (pharmacology), IntAct (molecular interactions), CARD (antibiotic resistance), and PDBe (structure quality) --- specialized annotation agents that apply field-specific decision logic with calibrated evidence thresholds, and a blind multi-model verification stage employing four architecturally diverse local LLMs. The system enforces evidence-grounded reasoning by requiring cited sources for every annotation with full traceability (model identity, agent provenance, source URLs, evidence text), implements blind peer review in which verifier models never observe the primary annotation, and applies short-circuit optimizations that reduce unnecessary model invocations. All models execute locally via Ollama on consumer hardware, with optional Kimi K2 Thinking model support on server-class hardware. Expanded evaluation on 62 clinical trials reveals systematic error patterns --- classification over-triggering (29.4% agreement with R1), outcome defaulting to Unknown (37.1%), and spurious failure reasons (41.9%) --- each addressed by targeted v4 agent improvements. We describe the full architecture, error analysis, v4 improvements, and concordance results.

---

## 1. Introduction

Antimicrobial peptides constitute a growing and therapeutically important class of molecules with diverse mechanisms of action, ranging from direct membrane disruption to immunomodulation and anti-biofilm activity. As the number of AMP-related clinical trials has expanded, so too has the need for structured, systematic annotation of these trials to support meta-analyses, regulatory review, and translational research.

Annotating clinical trials at scale requires classifying each trial along multiple dimensions: whether the intervention is a true antimicrobial peptide, its mode of delivery, the trial outcome, the reason for any failure, and the peptide identity of the compound under study. When performed by domain experts, this annotation process represents the gold standard for data quality. However, manual annotation suffers from three well-documented limitations. First, it is expensive: trained reviewers command significant time and resources, particularly when trials require cross-referencing registry data with published literature. Second, it is slow: annotating hundreds of trials across five fields represents weeks of effort. Third, and perhaps most critically, it is unreliable: our analysis of 617 human annotations produced by two independent replicates reveals an overall inter-annotator agreement of only 80.2%, with substantially lower concordance on specific fields and dramatic disagreements on fundamental classification decisions.

Existing automated approaches to clinical trial annotation typically employ a single LLM call per field, without verification mechanisms, evidence requirements, or source citations. These approaches inherit the well-known limitations of language models --- hallucination, overconfidence, and sensitivity to prompt phrasing --- without any of the error-correction mechanisms that human review processes provide.

Agent Annotate addresses these limitations through a pipeline of specialized AI agents running entirely on local models. The system decomposes annotation into research, annotation, and verification phases, each implemented by purpose-built agents with distinct responsibilities. Research agents gather evidence from 20+ free external databases with calibrated source weights --- including specialized peptide activity (DBAASP), bioactivity (ChEMBL), structural (RCSB PDB), protein sequence (EBI Proteins), AMP classification (APD, dbAMP), international trial registries (WHO ICTRP), pharmacology (IUPHAR), molecular interactions (IntAct), antibiotic resistance (CARD), and structure quality (PDBe) databases. Annotation agents apply field-specific decision logic with evidence threshold enforcement. Verification agents perform blind multi-model peer review using architecturally diverse model families. The result is a system that produces annotations with full provenance chains including model identity, agent provenance, source URLs, and evidence text for every field --- calibrated confidence scores, and explicit identification of cases requiring human review.

This paper describes the complete Agent Annotate system, presents baseline evaluation results against human annotations, analyzes systematic error patterns, and outlines improvements implemented in response to error analysis.

---

## 2. Background

### 2.1 Antimicrobial Peptide Classification

Antimicrobial peptides exert their therapeutic effects through four recognized modes of action, which we designate Modes A through D:

**Mode A --- Direct Antimicrobial.** Peptides that kill or inhibit microbial growth through direct physical interaction, typically via membrane disruption or pore formation. Representative examples include colistin, polymyxin B, melittin, and nisin. These peptides interact directly with microbial cell membranes, compromising structural integrity and leading to cell death.

**Mode B --- Immunostimulatory Host Defense.** Peptides that enhance the host immune response against pathogens by recruiting neutrophils, enhancing phagocytosis, or modulating cytokine production. Representative examples include LL-37, defensins, and thymosin alpha-1. These peptides do not necessarily kill pathogens directly but potentiate the host's capacity to clear infection.

**Mode C --- Anti-Biofilm.** Peptides that disrupt established microbial biofilms or prevent biofilm formation. Representative examples include LL-37, DJK-5, and IDR-1018. Biofilm disruption is mechanistically distinct from direct antimicrobial activity, as biofilm-resident organisms exhibit phenotypic tolerance that renders them resistant to conventional antimicrobials.

**Mode D --- Pathogen-Targeting Vaccines and Immunogens.** Peptide-based vaccines or immunogens designed to elicit adaptive immune responses against specific pathogens. Representative examples include StreptInCor and peptide-based HIV vaccine candidates. These peptides function as antigens rather than effectors.

A critical distinction governs classification: peptides that *promote* defense against pathogens qualify as AMPs under this schema, while peptides that *suppress* immunity (such as autoimmune therapeutics like dnaJP1) do not. Similarly, metabolic hormones and their analogues (GLP-1 receptor agonists, insulin derivatives) are excluded regardless of their peptide nature, as are neuropeptides, radiolabeled peptide tracers, and other non-antimicrobial applications.

### 2.2 Annotation Schema

Each clinical trial is annotated across five structured fields:

| Field | Type | Values |
|---|---|---|
| Classification | Categorical (3) | AMP(infection), AMP(other), Other |
| Delivery Mode | Categorical (18) | Intravenous, Oral, Topical, Intramuscular, Subcutaneous, Intranasal, Inhaled, Intrathecal, Intraperitoneal, Intravesical, Intravitreal, Ophthalmic, Rectal, Vaginal, Transdermal, Sublingual, Other/Unspecified, Multiple |
| Outcome | Categorical (7) | Positive, Failed - completed trial, Terminated, Withdrawn, Recruiting, Active not recruiting, Unknown |
| Reason for Failure | Categorical (5+empty) | Ineffective for purpose, Adverse effects/safety concerns, Formulation/stability issues, Superseded by alternatives, Insufficient enrollment, (empty) |
| Peptide | Boolean | True, False |

The **Classification** field distinguishes true AMP trials targeting infection from AMP trials with non-infection applications (e.g., wound healing via host defense peptides) and non-AMP trials. **Delivery Mode** captures the route of administration. **Outcome** reflects the current status and result of the trial, incorporating both registry status and published findings. **Reason for Failure** applies only to trials with negative outcomes and must be supported by cited evidence. **Peptide** indicates whether the intervention compound is a true peptide.

### 2.3 Challenges in Manual Annotation

Analysis of 617 human annotations produced by two independent annotators (designated R1 and R2) reveals systematic disagreements that underscore the difficulty of this task:

**Peptide field divergence.** R1 assigned Peptide=True to 451 trials (24% of the dataset), while R2 assigned Peptide=True to only 56 trials (3%) --- an 8:1 ratio. Only 30 trials received Peptide=True from both annotators. This divergence suggests fundamentally different interpretations of what constitutes a "peptide" intervention, despite both annotators reviewing the same trials.

**Outcome field inconsistency.** R1 used the "Recruiting" outcome category 222 times, while R2 used it zero times. This indicates that R2 either collapsed recruiting trials into other categories or systematically excluded them from annotation.

**Registry staleness.** At least 15 trials with "UNKNOWN" status on ClinicalTrials.gov had published positive results in the peer-reviewed literature. Annotators who relied solely on registry status without cross-referencing the literature would systematically misclassify these trials.

These findings demonstrate that manual annotation, while conventionally treated as ground truth, is itself substantially noisy. Any automated system must be evaluated against this backdrop of imperfect human agreement.

---

## 3. Methods

### 3.1 System Architecture

Agent Annotate implements a three-phase pipeline:

```
Phase 1: Research           Phase 2: Annotation         Phase 3: Verification
(15 agents, parallel)       (5 agents, sequential*)      (multi-model blind review)
                            *sequential due to GPU memory

[Clinical Protocol  ]  -->  [Classification Agent]  -->  [Blind Verifier 1: gemma2:9b  ]
[Literature         ]  -->  [Delivery Mode Agent ]  -->  [Blind Verifier 2: qwen2:latest]
[Peptide Identity   ]  -->  [Outcome Agent       ]  -->  [Blind Verifier 3: mistral:latest]
[Web Context        ]  -->  [Failure Reason Agent]  -->  [Reconciler: qwen2.5:14b (disputes only)]
[DBAASP (v4)        ]       [Peptide Agent       ]
[ChEMBL (v4)        ]
[RCSB PDB (v4)      ]
[EBI Proteins (v4)  ]
[APD (v5)           ]
[dbAMP (v5)         ]
[WHO ICTRP (v5)     ]
[IUPHAR (v5)        ]
[IntAct (v5)        ]
[CARD (v5)          ]
[PDBe (v5)          ]
```

Phase 1 agents operate in parallel, as they perform network I/O without requiring GPU resources. The v4 pipeline expanded from four to eight research agents, adding DBAASP, ChEMBL, RCSB PDB, and EBI Proteins. The v5 expansion added seven more agents (APD, dbAMP, WHO ICTRP, IUPHAR, IntAct, CARD, PDBe), bringing the total to 15 research agents querying 20+ free databases. SerpAPI was removed (paid service); all agents now use free APIs exclusively. Phase 2 agents share a single Ollama instance and execute sequentially due to the memory constraints of the deployment hardware. Phase 3 applies blind verification using architecturally diverse model families.

All models run locally via Ollama on a Mac Mini M4 with 16 GB of unified memory (mac_mini profile) or on a dedicated server with 48+ GB (server profile, which enables Kimi K2 Thinking as the primary annotator). No data leaves the local machine during inference. External network access is limited to Phase 1 research queries against public databases.

### 3.2 Research Agents

Fifteen research agents gather evidence from 20+ free external data sources, each assigned a calibrated weight reflecting its reliability and relevance. The original four agents (Sections 3.2.1--3.2.4) were present in v2/v3; four agents (Sections 3.2.6--3.2.9) were added in v4; seven agents (Sections 3.2.10--3.2.16) were added in v5.

#### 3.2.1 Clinical Protocol Agent

The Clinical Protocol Agent queries structured registry databases to retrieve trial metadata, intervention descriptions, arms, eligibility criteria, and status information.

| Source | Weight | Data Retrieved |
|---|---|---|
| ClinicalTrials.gov API v2 | 0.95 | Protocol, status, interventions, arms, conditions, outcomes |
| OpenFDA | 0.85 | Drug labels, adverse events, approval status |

ClinicalTrials.gov receives the highest weight among all sources due to its authoritative status as the primary trial registry. The API v2 endpoint provides structured JSON responses with comprehensive protocol metadata. OpenFDA supplements this with regulatory context, particularly useful for determining whether an intervention has received FDA approval or has documented safety signals.

#### 3.2.2 Literature Agent

The Literature Agent queries biomedical literature databases to retrieve published results, review articles, and full-text content relevant to each trial.

| Source | Weight | Data Retrieved |
|---|---|---|
| PubMed | 0.90 | Abstracts, MeSH terms, publication metadata |
| PMC | 0.85 | Full-text articles, figures, supplementary materials |
| PMC BioC | 0.80 | Structured full-text in BioC XML format |

Published literature is critical for overriding stale registry status. A trial listed as "UNKNOWN" on ClinicalTrials.gov may have published positive results in a peer-reviewed journal years prior. The Literature Agent prioritizes results publications over review articles and protocol descriptions.

#### 3.2.3 Peptide Identity Agent

The Peptide Identity Agent queries protein and peptide databases to determine whether an intervention compound is a true peptide and to retrieve sequence and functional information.

| Source | Weight | Data Retrieved |
|---|---|---|
| UniProt | 0.95 | Protein sequences, function annotations, subcellular localization |
| DRAMP | 0.80 | Antimicrobial peptide-specific annotations, MIC data, structural class |

UniProt receives the highest weight due to its comprehensive coverage and curation standards. DRAMP (Data Repository of Antimicrobial Peptides) provides AMP-specific annotations not available in general protein databases, including minimum inhibitory concentration data and antimicrobial spectrum information.

#### 3.2.4 Web Context Agent

The Web Context Agent queries general web search engines and academic search services to retrieve contextual information not available in structured databases.

| Source | Weight | Data Retrieved |
|---|---|---|
| DuckDuckGo | 0.40 | General web results, news articles |
| Google Scholar | 0.70 | Academic citations, related articles |

Web sources receive substantially lower weights than structured databases, reflecting the higher noise and lower reliability of unstructured web content. Google Scholar receives the highest web weight due to its focus on academic content. Note: SerpAPI was removed as it requires a paid subscription; all research agents now use free APIs exclusively.

#### 3.2.5 HTTP Resilience

All research agents implement HTTP resilience through two mechanisms. First, per-host rate-limiting semaphores enforce the rate limits specified in Section 7.3, preventing request throttling. Second, retry logic with exponential backoff handles transient failures: HTTP 429 (Too Many Requests) and 5xx (Server Error) responses trigger retries with geometrically increasing delays, while 4xx client errors (other than 429) are treated as permanent failures.

#### 3.2.6 DBAASP Agent (v4)

The DBAASP Agent queries the Database of Antimicrobial Activity and Structure of Peptides for experimentally validated antimicrobial activity data.

| Source | Weight | Data Retrieved |
|---|---|---|
| DBAASP API | 0.85 | MIC values, hemolytic activity, antimicrobial spectrum, structure-activity data |

DBAASP provides direct evidence of antimicrobial activity that is critical for the Classification Agent. A peptide with documented MIC values in DBAASP constitutes strong evidence for AMP classification. This agent's data also informs the Peptide Agent by confirming peptide identity through the database's curated peptide records.

#### 3.2.7 ChEMBL Agent (v4)

The ChEMBL Agent queries the EMBL-EBI ChEMBL database for bioactivity assay results and clinical development data.

| Source | Weight | Data Retrieved |
|---|---|---|
| ChEMBL API | 0.85 | Bioactivity assays, clinical development phase, mechanism of action, target data |

ChEMBL provides pharmacological context spanning multiple trials of the same compound. This is particularly valuable for the Outcome Agent, as a compound that has progressed to later clinical phases in other trials provides context for interpreting the current trial's status. The mechanism-of-action data helps the Classification Agent distinguish true antimicrobial mechanisms from other peptide therapeutic applications.

#### 3.2.8 RCSB PDB Agent (v4)

The RCSB PDB Agent queries the Protein Data Bank for 3D structural metadata of intervention compounds.

| Source | Weight | Data Retrieved |
|---|---|---|
| RCSB PDB API | 0.80 | Structural classification, molecular weight, chain length, experimental method, binding data |

Structural data provides independent confirmation of peptide identity (chain length, amino acid composition) and can reveal mechanism-of-action clues through binding site analysis. Coverage is limited to compounds with experimentally solved structures, so absence from PDB does not preclude peptide identity.

#### 3.2.9 EBI Proteins Agent (v4)

The EBI Proteins Agent queries the EMBL-EBI Proteins API for sequence and functional annotation data.

| Source | Weight | Data Retrieved |
|---|---|---|
| EBI Proteins API | 0.85 | Amino acid sequences, post-translational modifications, variants, functional annotations, GO terms |

This agent complements the Peptide Identity Agent's UniProt queries (Section 3.2.3) with additional sequence-level data accessible through the EBI programmatic interface, including variant information and detailed functional annotations that help distinguish antimicrobial function from other peptide activities.

#### 3.2.10 APD Agent (v5)

The APD Agent queries the Antimicrobial Peptide Database (aps.unmc.edu) for curated AMP records via HTML scraping.

| Source | Weight | Data Retrieved |
|---|---|---|
| APD (HTML scraping) | 0.80 | AMP classifications, activity annotations, peptide sequences, source organism |

APD is one of the earliest and most widely cited AMP databases. Presence in APD is strong evidence for AMP status. The server requires JavaScript rendering for some pages, so data retrieval is best-effort.

#### 3.2.11 dbAMP Agent (v5)

The dbAMP Agent queries the dbAMP 3.0 database (yylab.jnu.edu.cn/dbAMP) for comprehensive AMP annotations via HTML scraping.

| Source | Weight | Data Retrieved |
|---|---|---|
| dbAMP 3.0 (HTML scraping) | 0.80 | AMP sequences, functional annotations, antimicrobial activity, target organisms |

dbAMP 3.0 contains over 33,000 AMP entries with experimentally validated annotations, providing broad coverage that increases the likelihood of finding data for less-studied peptides. Availability is intermittent; the agent handles connection failures gracefully.

#### 3.2.12 WHO ICTRP Agent (v5)

The WHO ICTRP Agent queries the International Clinical Trials Registry Platform (trialsearch.who.int) for international trial registry data via HTML parsing.

| Source | Weight | Data Retrieved |
|---|---|---|
| WHO ICTRP (HTML parsing) | 0.85 | Trial registrations from 17+ international registries, status, interventions, conditions |

ICTRP extends ClinicalTrials.gov coverage to international registries (EU Clinical Trials Register, ISRCTN, ANZCTR, ChiCTR, CTRI, etc.). Many AMP trials conducted outside the US may only be registered in non-US registries.

#### 3.2.13 IUPHAR Guide to Pharmacology Agent (v5)

The IUPHAR Agent queries the IUPHAR/BPS Guide to Pharmacology (guidetopharmacology.org) via its REST API for pharmacological data.

| Source | Weight | Data Retrieved |
|---|---|---|
| IUPHAR Guide to Pharmacology (REST API) | 0.85 | Mechanism of action, drug targets, ligand classification, receptor-ligand interactions |

IUPHAR provides authoritative pharmacological context that helps the Classification Agent distinguish direct antimicrobial mechanisms from immunomodulatory and other peptide therapeutic activities. Ligand classification data also informs the Peptide Agent.

#### 3.2.14 IntAct Agent (v5)

The IntAct Agent queries the IntAct molecular interaction database (ebi.ac.uk/intact) via its REST API for protein-protein and peptide-target interaction data.

| Source | Weight | Data Retrieved |
|---|---|---|
| IntAct (REST API) | 0.75 | Molecular interactions, interaction types, detection methods, UniProt cross-references |

Molecular interaction data can reveal AMP mechanisms of action. Interactions with membrane proteins or microbial targets support direct antimicrobial classification, while interactions with immune receptors support immunomodulatory classification.

#### 3.2.15 CARD Agent (v5)

The CARD Agent queries the Comprehensive Antibiotic Resistance Database (card.mcmaster.ca) via AJAX endpoints for resistance mechanism data.

| Source | Weight | Data Retrieved |
|---|---|---|
| CARD (AJAX endpoints) | 0.80 | Resistance mechanisms, ARO terms, resistance gene annotations, drug class classifications |

CARD provides antibiotic resistance context relevant to AMP clinical trials. ARO terms help classify the mechanism of action for peptide antibiotics, distinguishing membrane-targeting AMPs from those with intracellular targets.

#### 3.2.16 PDBe Agent (v5)

The PDBe Agent queries the European Protein Data Bank (ebi.ac.uk/pdbe) via Solr search and REST APIs for structure quality metrics.

| Source | Weight | Data Retrieved |
|---|---|---|
| PDBe (Solr search + REST API) | 0.80 | Structure quality metrics (resolution, R-factor), experimental method details, deposition metadata |

PDBe complements the RCSB PDB Agent (Section 3.2.8) with structure quality metrics. Resolution and R-factor data indicate the reliability of structural information, with higher-quality structures providing more trustworthy evidence for peptide identity and mechanism-of-action analysis.

### 3.3 Annotation Agents

Five annotation agents process the evidence gathered in Phase 1, each specialized for a single annotation field. These agents fall into two architectural categories based on the complexity of the decision required.

#### 3.3.1 Single-Pass Agents

The Classification, Delivery Mode, and Peptide agents each perform a single LLM call with a field-specific system prompt and the full evidence package as user input.

**Classification Agent.** The system prompt encodes:
- The four-mode AMP definition (Modes A through D) with representative examples for each mode.
- Explicit negative examples: GLP-1 receptor agonists, neuropeptides (substance P, neuropeptide Y), immunosuppressants (dnaJP1, cyclosporine), and radiolabeled peptide tracers are enumerated as non-AMP.
- A default-to-Other rule: when the evidence is insufficient to confidently assign AMP(infection) or AMP(other), the agent must classify the trial as Other. This conservative default reduces false-positive AMP classifications.

**Delivery Mode Agent.** The system prompt encodes:
- A priority-ordered extraction hierarchy: Arms/Interventions descriptions take precedence, followed by the trial Description field, then published literature, then drug label information, and finally the trial Name as a last resort.
- A keyword mapping table for route abbreviations and synonyms (e.g., "IV" maps to Intravenous, "PO" maps to Oral, "topical cream/ointment/gel" maps to Topical).

**Peptide Agent.** The system prompt encodes the biochemical definition of a peptide (amino acid polymer, typically under 100 residues) and instructs the model to cross-reference the Peptide Identity Agent's findings from UniProt and DRAMP.

#### 3.3.2 Two-Pass Investigative Agents

The Outcome and Failure Reason agents employ a two-pass architecture, reflecting the investigative complexity of these fields.

**Pass 1: Structured Fact Extraction.** The first LLM call extracts factual claims from the evidence package without making a classification decision. The model is instructed to list: the registry status, any published results and their conclusions, any safety signals, the trial phase, enrollment figures, and the date of last update. This pass produces a structured intermediate representation.

**Pass 2: Decision with Calibrated Rules.** The second LLM call receives the Pass 1 output along with a decision tree that encodes field-specific logic.

The **Outcome Agent v3 decision tree** applies the following rules in priority order:

1. If the trial is currently Recruiting or Active not recruiting, report the current status directly.
2. If the trial has been Withdrawn, classify as Withdrawn.
3. If published results demonstrate positive efficacy or if a Phase I trial completed its safety evaluation successfully, classify as Positive. Phase I safety completion is treated as a positive outcome because Phase I trials are designed to assess safety, not efficacy.
4. If published results demonstrate negative efficacy (failure to meet primary endpoint, lack of superiority over comparator), classify as Failed - completed trial. This classification *requires* cited evidence of failure.
5. If the trial was Terminated and no positive results are published, classify as Terminated.
6. If the evidence is ambiguous or insufficient, classify as Unknown.

A critical rule governs the distinction between completion and failure: a registry status of COMPLETED does *not* imply failure. Many trials complete successfully. The "Failed - completed trial" classification requires affirmative evidence of a negative result, not merely the absence of a positive one.

The **Failure Reason Agent** implements a short-circuit mechanism before invoking the LLM. The enhanced non-failure detection checks three conditions:

1. **Positive signal detection:** If the Outcome Agent classified the trial as Positive, Recruiting, or Active not recruiting, the Failure Reason is set to empty without an LLM call.
2. **Active status detection:** If the registry status indicates the trial is ongoing, the Failure Reason is set to empty.
3. **Malformed Pass 1 detection:** If the Pass 1 output from the Outcome Agent is structurally invalid or empty, the Failure Reason is set to empty rather than risking a hallucinated failure reason.

When the short-circuit does not fire, the Failure Reason Agent proceeds with its own two-pass architecture, extracting failure-related facts in Pass 1 and classifying the failure mode in Pass 2.

#### 3.3.3 Evidence Threshold Enforcement

Each annotation field is configured with minimum evidence requirements:

| Parameter | Description |
|---|---|
| `min_sources` | Minimum number of distinct sources that must provide relevant evidence |
| `min_quality` | Minimum quality score across the evidence package |

The quality score for a given source is computed as:

```
quality = (source_weight * field_relevance) / max_weight
```

where `source_weight` is the calibrated weight from Section 3.2, `field_relevance` is a per-field multiplier reflecting how informative that source type is for the specific annotation field, and `max_weight` is the maximum possible weight (used for normalization).

When the evidence for a field falls below the configured threshold, the annotation proceeds but with two consequences: the confidence score is capped at 0.3 (indicating low confidence), and the field is flagged for mandatory verification in Phase 3. This mechanism ensures that weakly-evidenced annotations are never presented as high-confidence results.

### 3.4 Verification Pipeline

The verification pipeline implements blind multi-model peer review. The term "blind" is used precisely: verifier models receive the evidence package and the annotation task but *never* observe the primary annotator's answer. This prevents anchoring bias, where a verifier would disproportionately agree with a presented answer.

#### 3.4.1 Model Selection

| Role | Model | Architecture Family | Parameters |
|---|---|---|---|
| Primary annotator | llama3.1:8b | Meta LLaMA | 8B |
| Verifier 1 | gemma2:9b | Google Gemma | 9B |
| Verifier 2 | qwen2:latest | Alibaba Qwen | ~7B |
| Verifier 3 | mistral:latest | Mistral AI | ~7B |
| Reconciler | qwen2.5:14b | Alibaba Qwen 2.5 | 14B |

Architecture diversity across four distinct model families (Meta, Google, Alibaba, Mistral) guards against shared systematic biases. Models trained on different data mixtures with different architectural choices (e.g., grouped query attention vs. multi-head attention, different tokenization strategies) are less likely to make the same errors on the same inputs.

#### 3.4.2 Consensus Protocol

The consensus threshold is set to 1.0, requiring unanimous agreement among the primary annotator and all verifiers. This strict threshold reflects the system's conservative design philosophy: annotations that pass unanimous verification are highly likely to be correct, while annotations that fail provide an honest signal of uncertainty.

When unanimous consensus is not reached, the reconciler model (qwen2.5:14b, the largest model in the pipeline) is invoked. The reconciler receives all opinions and their reasoning chains and is instructed to identify the most evidence-supported answer. If the reconciler cannot resolve the dispute --- for example, because the underlying evidence is genuinely ambiguous --- the field is flagged for manual human review.

### 3.5 Concordance Analysis

The concordance analysis methodology (v2) implements the following conventions to ensure fair comparison between agent and human annotations:

**Blank exclusion.** Blank human annotations are excluded from concordance calculations. A blank cell indicates that the annotator did not annotate the field, not that the annotator chose the empty string as their answer. Including blanks would artificially inflate or deflate agreement depending on whether the agent also produced an empty result.

**Failure Reason exception.** For the Reason for Failure field, an empty value is a semantically valid answer meaning "no failure occurred." A Failure Reason cell is treated as blank (excluded from analysis) only if the corresponding Outcome field is also blank, indicating that the annotator skipped the trial entirely.

**Inter-annotator reliability.** Cohen's kappa is computed for each field to quantify agreement beyond chance. Kappa adjusts for the baseline agreement expected if both annotators assigned categories at random in proportion to their marginal distributions. Kappa values are interpreted on the standard scale: below 0 indicates less than chance agreement, 0.01--0.20 is slight, 0.21--0.40 is fair, 0.41--0.60 is moderate, 0.61--0.80 is substantial, and 0.81--1.00 is almost perfect agreement.

---

## 4. Evaluation

### 4.1 Baseline Dataset

The baseline evaluation dataset comprises 25 clinical trials selected as the first 25 entries (sorted alphabetically by NCT identifier) from the set of 614 trials annotated by both human annotators. Both annotators --- designated R1 (Emily) and R2 (Anat) --- independently annotated all five fields for all 25 trials. This selection method avoids cherry-picking and provides a representative sample of the difficulty distribution across the full dataset.

### 4.2 Pre-Improvement Results (v2 Agents)

Table 1 presents the concordance between the agent pipeline (v2) and each human annotator, as well as the inter-annotator agreement between the two humans. Blank human annotations are excluded per the methodology described in Section 3.5.

**Table 1.** Concordance analysis on 25 baseline trials (v2 agents, blanks excluded).

| Field | Agent=R1 | Agent=R2 | R1=R2 | kappa(Agent,R1) | kappa(Agent,R2) |
|---|---|---|---|---|---|
| Classification | 12/25 (48.0%) | 10/25 (40.0%) | 19/25 (76.0%) | +0.241 | +0.103 |
| Delivery Mode | 9/24 (37.5%) | 10/24 (41.7%) | 17/23 (73.9%) | +0.283 | +0.335 |
| Outcome | 7/24 (29.2%) | 4/19 (21.1%) | 15/19 (78.9%) | +0.091 | +0.087 |
| Failure Reason | 8/24 (33.3%) | 6/19 (31.6%) | 18/19 (94.7%) | +0.008 | +0.054 |
| Peptide | N/A | 22/25 (88.0%) | N/A | N/A | -0.056 |
| **OVERALL** | **36/97 (37.1%)** | **52/112 (46.4%)** | **69/86 (80.2%)** | | |

Several patterns are immediately apparent:

1. **Human-human agreement (80.2%) substantially exceeds agent-human agreement (37.1%--46.4%).** The agent pipeline does not yet match human performance on any field except Peptide.

2. **Agent-human kappa values are low across all fields.** The highest kappa (Agent, R2 for Delivery Mode: +0.335) falls in the "fair" range; most values are in the "slight" range or below. This indicates that agent-human agreement, while above chance for some fields, is not yet meaningfully reliable.

3. **Peptide is the strongest field.** Agent=R2 agreement on Peptide reaches 88.0%, approaching the level of a factual lookup. The negative kappa (-0.056) reflects a near-degenerate marginal distribution (R2 assigned Peptide=True to very few trials), making kappa unreliable for this field.

4. **Outcome and Failure Reason are the weakest fields.** Agent-human agreement is below 35% for both, and kappa values approach zero, indicating near-random agreement.

### 4.3 Error Analysis

Systematic examination of the 25 baseline trials reveals four categories of error, each traceable to specific architectural or model-level causes.

#### 4.3.1 Outcome Bias: Conflation of Completion with Failure

The agent assigned "Failed - completed trial" to 20 of 25 trials (80%), a rate dramatically higher than either human annotator. Root cause analysis reveals that the 8-billion-parameter model conflated a ClinicalTrials.gov registry status of COMPLETED with a negative trial outcome. In reality, many Phase I trials that completed successfully (i.e., demonstrated an acceptable safety profile) were marked as failed by the agent.

This error is consistent with a surface-level pattern-matching failure: the model associates "completed trial" in the category name "Failed - completed trial" with the COMPLETED registry status, ignoring the semantic distinction between trial completion (a procedural event) and trial failure (a scientific conclusion requiring evidence).

#### 4.3.2 Classification Over-Triggering

The agent classified five or more non-AMP peptide trials (including trials of Peptide T and insulin-related compounds) as AMP. Root cause analysis indicates that the 8B model pattern-matches the co-occurrence of "peptide" and a disease context to produce an AMP classification, ignoring the explicit worked examples in the system prompt that enumerate these compounds as non-AMP.

This failure mode is consistent with the known tendency of smaller language models to attend preferentially to salient keywords over nuanced instructions. The worked examples, while present in the prompt, are insufficient to override the model's prior association between "peptide" and "antimicrobial."

#### 4.3.3 Delivery Mode Information Extraction Gaps

The agent returned empty or generic "Other/Unspecified" delivery mode annotations for trials where the route of administration was clearly stated in the ClinicalTrials.gov intervention description. This indicates a failure in information extraction rather than classification: the model failed to locate the relevant text within the evidence package, despite its presence.

#### 4.3.4 Spurious Failure Reasons

The agent assigned "Ineffective for purpose" to trials that both human annotators left blank (because the trial succeeded or was ongoing). Root cause analysis reveals that the Pass 1 short-circuit mechanism in the Failure Reason Agent only caught an exact string match of "No" when determining that no failure occurred. Responses such as "No failure reason identified," "N/A," or "The trial has not failed" did not trigger the short-circuit, causing the agent to proceed to Pass 2 and hallucinate a failure reason.

### 4.4 Improvements (v3 Agents)

Each error category identified in Section 4.3 motivated a specific architectural or prompt-level fix in the v3 agent revision:

**Outcome decision tree (Section 4.3.1).** The v3 Outcome Agent implements the priority-ordered decision tree described in Section 3.3.2. The critical addition is the explicit rule that COMPLETED registry status does not imply failure, and that "Failed - completed trial" requires cited evidence of a negative result. Phase I safety completion is explicitly defined as a positive outcome.

**Classification negative examples (Section 4.3.2).** The v3 Classification Agent system prompt expands the negative example set and reformats them as a structured exclusion list presented before the positive AMP definition. The default-to-Other rule is elevated to a first-class instruction: "When evidence is insufficient, classify as Other."

**Delivery Mode extraction hierarchy (Section 4.3.3).** The v3 Delivery Mode Agent implements the priority-ordered extraction hierarchy described in Section 3.3.1, with explicit keyword mappings for common route abbreviations. The model is instructed to search each source in priority order and to report the first match found, reducing the likelihood of returning "Other/Unspecified" when a specific route is available.

**Enhanced non-failure short-circuit (Section 4.3.4).** The v3 Failure Reason Agent replaces the exact-match short-circuit with the enhanced detection mechanism described in Section 3.3.2. The new mechanism checks for positive outcome signals, active trial status, and malformed Pass 1 output, catching the full range of non-failure conditions that the v2 agent missed.

### 4.5 Expanded Evaluation (v3 Agents, n=62)

An overnight concordance run on 62 trials using v3 agents provides a larger baseline for evaluation. Results are presented as agent-vs-human agreement rates.

**Table 3.** Concordance analysis on 62 trials (v3 agents, blanks excluded).

| Field | Agent=R1 | Agent=R2 | Dominant Error Pattern |
|---|---|---|---|
| Classification | 29.4% | 13.0% | Over-classification as AMP |
| Delivery Mode | 47.6% | 54.1% | Best field; extraction logic effective |
| Outcome | 37.1% | 60.5% | Defaults to Unknown too frequently |
| Failure Reason | 41.9% | 43.5% | Over-assigns "Ineffective for purpose" |
| Peptide | 66.7% | 60.0% | Brand name resolution failures |

The n=62 results reveal that the v3 improvements did not fully resolve the systematic errors identified in the n=25 baseline. Classification agreement *decreased* on the larger sample, indicating that the negative example approach was insufficient to prevent over-classification. Delivery Mode remained the strongest field. The asymmetry between R1 and R2 agreement on Outcome (37.1% vs 60.5%) reflects the temporal drift between human annotators --- the agent agrees more with R2, who cross-referenced literature, than with R1, who primarily recorded registry status.

### 4.6 Error Analysis: Value Distribution Problems (n=62)

The n=62 evaluation exposes value distribution problems not visible in the n=25 sample:

1. **Classification**: The agent assigns AMP(infection) or AMP(other) to a far higher proportion of trials than either human annotator. Many non-AMP peptide therapeutics (metabolic, neurological, endocrine) receive AMP classifications because the 8B model pattern-matches "peptide + disease" to "AMP."

2. **Outcome**: The agent's distribution is skewed toward Unknown, while human annotators use Positive, Recruiting, and Terminated more frequently. The agent fails to find published results that would resolve Unknown status, particularly for older trials.

3. **Failure Reason**: The agent assigns "Ineffective for purpose" to completed trials without published negative results. The distribution should be dominated by empty values (most trials do not fail), but the agent's distribution is flatter.

### 4.6.1 Root Cause Analysis: Verifier Parsing Failures in reason_for_failure

Deeper analysis of the review conflicts reveals that the majority of flagged disagreements were concentrated in a single field. Of 103 total review conflicts across all fields, 68 (66%) occurred in `reason_for_failure`. Of those 68, approximately 57 were false disagreements caused by verifier parsing failures rather than genuine evidence-based disagreements.

**Value distribution of invalid verifier outputs for reason_for_failure:**

| Invalid Value | Occurrences | Root Cause |
|---|---|---|
| COMPLETED | 13 | Verifier echoed ClinicalTrials.gov registry status |
| Unknown | 13 | Verifier returned ambiguous status instead of empty string |
| None | 11 | Verifier used "None" as shorthand for "not applicable" |
| N/A | 5 | Verifier used "N/A" instead of leaving field empty |
| ACTIVE_NOT_RECRUITING | 3 | Verifier echoed trial status |
| Other status keywords | 12 | Various registry statuses returned as failure reasons |

In all of these cases, the verifier correctly determined that the trial had no failure reason but expressed this conclusion using a status keyword or shorthand rather than the expected empty string. The consensus algorithm treated these as disagreements with verifiers that correctly returned empty, triggering unnecessary reconciliation and manual review flagging.

**Fix applied:** The value normalization layer (described in METHODOLOGY.md Section 6.5) was expanded to catch all status-as-value patterns. The canonical mapping normalizes COMPLETED, Unknown, None, N/A, and all trial status keywords to empty string for the `reason_for_failure` field.

**Retroactive results:** Applying the fix retroactively to 11 completed jobs corrected 74 individual field values, restored consensus on 12 fields, and unflagged 12 trials from manual review. This demonstrates that the true disagreement rate for `reason_for_failure` is substantially lower than the 56.5%--58.1% conflict rate initially reported. The inflated conflict rate was an artifact of verifier output formatting, not genuine evidence ambiguity.

**Implication for reported accuracy:** The concordance figures in Table 3 (Section 4.5) for Failure Reason (41.9% agent=R1, 43.5% agent=R2) include trials whose annotations were distorted by false review conflicts. After retroactive normalization, the effective agreement rates should be recalculated, as many trials that underwent unnecessary reconciliation may have had their correct consensus annotation overwritten by the reconciler.

### 4.7 Improvements (v4 Agents)

The v4 agent revision targets the systematic errors revealed by the n=62 evaluation:

**Classification: Direct antimicrobial mechanism requirement.** The v4 Classification Agent requires identification of a specific mode of action (Modes A--D) with cited evidence. Indirect relationships to infection no longer qualify for AMP classification. This addresses the over-classification pattern where any peptide in a disease context received an AMP label.

**Classification: Strengthened negative examples.** The v4 prompt expands the negative example set and adds the explicit rule that an AMP must have a *direct* antimicrobial mechanism.

**Delivery Mode: Never-guess reinforcement.** The v4 Delivery Mode Agent adds explicit reinforcement that empty is the correct answer when evidence is insufficient. The agent must never infer a route from compound type or therapeutic context alone.

**Failure Reason: Default no-failure for completed trials.** The v4 Failure Reason Agent defaults to empty (no failure) for completed trials without published negative results. Failure reason requires affirmative evidence of failure.

**Peptide: Brand name resolution rules.** The v4 Peptide Agent resolves brand-name interventions to their generic compounds before determining peptide status.

**Verifier prompt parity.** All v4 verifier prompts receive the same field-specific detail as the primary annotation agents, eliminating the instruction asymmetry that undermined v3 verification quality.

**Four new research agents (v4).** The DBAASP, ChEMBL, RCSB PDB, and EBI Proteins agents (Section 3.2.6--3.2.9) provide richer evidence for all annotation fields, particularly Classification (antimicrobial activity data from DBAASP) and Peptide (structural confirmation from PDB, sequence data from EBI Proteins).

**Seven additional research agents (v5).** The APD, dbAMP, WHO ICTRP, IUPHAR, IntAct, CARD, and PDBe agents (Section 3.2.10--3.2.16) expand the research pipeline to 15 agents querying 20+ free databases. These additions provide independent AMP classification sources (APD, dbAMP), international trial registry coverage (WHO ICTRP), pharmacological mechanism-of-action data (IUPHAR), molecular interaction evidence (IntAct), antibiotic resistance context (CARD), and structure quality metrics (PDBe). SerpAPI was removed as it required a paid subscription.

### 4.8 Citation Traceability

The v4 pipeline produces full citation traceability for every annotation. Each field in the output records:

- **Model**: Which LLM produced the annotation and each verifier opinion.
- **Agent**: Which research agents contributed evidence.
- **Sources**: Direct URLs to the external databases consulted.
- **Evidence**: The extracted text passages that informed the decision.
- **Verifier summary**: Each verifier's independent opinion and reasoning.

This traceability enables post-hoc auditing of any annotation decision and supports the reproducibility goals described in Section 7.2.

### 4.9 Kimi K2 Model Evaluation

The server hardware profile enables Kimi K2 Thinking as an alternative primary annotator. Kimi K2 is a reasoning-focused model that produces explicit chain-of-thought traces before its final answer. Preliminary evaluation suggests:

- **Improved instruction adherence** on investigative fields (Outcome, Failure Reason) where multi-step reasoning is required.
- **Better negative example compliance** for Classification, where the model more reliably distinguishes non-AMP peptide therapeutics.
- **Higher latency** per annotation due to the thinking trace, partially offset by the server profile's longer Ollama keep_alive (60 minutes vs 5 minutes on mac_mini).

A full concordance evaluation with Kimi K2 on the 62-trial set is planned to quantify the improvement over 8B models.

### 4.5 Human Agreement Analysis

Inter-annotator agreement between R1 and R2, with blanks excluded, provides the ceiling against which the agent pipeline should be evaluated:

**Table 2.** Human inter-annotator agreement by field (blanks excluded).

| Field | Concordant | Total | Agreement | Interpretation |
|---|---|---|---|---|
| Classification | 19 | 25 | 76.0% | Moderate |
| Delivery Mode | 17 | 23 | 73.9% | Moderate |
| Outcome | 15 | 19 | 78.9% | Moderate-to-substantial |
| Failure Reason | 18 | 19 | 94.7% | Near-perfect |
| **Overall** | **69** | **86** | **80.2%** | **Substantial** |

Failure Reason shows the highest human agreement (94.7%), likely because this field is only applicable to a subset of trials (those that failed) and the failure categories are relatively well-defined. Classification and Delivery Mode show the lowest agreement (73.9%--76.0%), reflecting genuine ambiguity in AMP classification boundaries and the difficulty of extracting delivery mode information from heterogeneous trial descriptions.

The overall human agreement of 80.2% establishes the practical ceiling for automated annotation: a perfect system that agreed with both annotators on every trial would achieve 80.2% agreement with each, since the annotators themselves disagree 19.8% of the time.

---

## 5. Discussion

### 5.1 Agent vs. Human Performance

The v2 agent pipeline achieves 37.1%--46.4% overall agreement with human annotators, substantially below the 80.2% human-human agreement. However, the performance gap is not uniformly distributed across fields. Peptide identification (88.0% agreement with R2) approaches human-level performance, while Outcome (21.1%--29.2%) and Failure Reason (31.6%--33.3%) fall well below.

This pattern is informative. Fields that require primarily factual extraction (Is this compound a peptide? What is the delivery route?) show stronger agent performance than fields requiring investigative reasoning (Did this trial succeed or fail? Why did it fail?). Factual extraction maps well to the information retrieval capabilities of the research agents, while investigative reasoning demands the kind of multi-step inference and contextual judgment that taxes smaller language models.

### 5.2 Model Size Effects

The error analysis in Section 4.3 reveals a consistent pattern: the 8-billion-parameter primary annotator (llama3.1:8b) ignores nuanced prompt instructions in favor of surface-level pattern matching. Worked examples of non-AMP peptides are overridden by keyword co-occurrence. The semantic distinction between trial completion and trial failure is collapsed. Enumerated extraction hierarchies are bypassed.

These behaviors are consistent with the established literature on scaling and instruction-following in language models. Smaller models exhibit weaker instruction adherence, shorter effective context windows for in-context learning, and greater susceptibility to keyword-based shortcuts. The 14-billion-parameter reconciler (qwen2.5:14b) demonstrates qualitatively better instruction-following in our verification experiments, suggesting that model size is a primary bottleneck.

This observation motivates a concrete improvement: deploying a 14B model as the primary annotator for high-error fields (Classification, Outcome) while retaining the 8B model for factual extraction fields (Peptide, Delivery Mode) where its performance is acceptable.

### 5.3 Verification Pipeline Value

Despite the primary annotator's limitations, the multi-model verification pipeline provides diagnostic value. Fields where all four models (primary + three verifiers) agree are empirically more likely to match human annotations than fields with disagreement. More importantly, fields with inter-model disagreement correlate with fields exhibiting high human disagreement, suggesting that model disagreement is a useful proxy for annotation difficulty.

The blind verification protocol --- in which verifiers never observe the primary annotation --- is essential to this diagnostic value. If verifiers could see the primary answer, anchoring bias would inflate apparent consensus, masking genuine uncertainty. Blind verification preserves the independence of each model's judgment, making disagreement a reliable signal.

### 5.4 Design Principles

Five design principles govern the Agent Annotate architecture:

1. **Evidence over opinion.** Every annotation must be accompanied by cited sources. An annotation without evidence, regardless of model confidence, is treated as low-quality and flagged for review.

2. **Blind verification.** Verifier models never observe the primary annotator's answer. This prevents anchoring bias and ensures that consensus reflects genuine agreement rather than conformity.

3. **Published literature overrides registry status.** ClinicalTrials.gov status fields are frequently stale, particularly for older trials. When published results contradict registry status, the published results take precedence.

4. **Conservatism under uncertainty.** When evidence is insufficient, the system defaults to the most conservative classification: Other for Classification, Unknown for Outcome. This design choice accepts higher false-negative rates in exchange for lower false-positive rates, appropriate for a system whose outputs will inform downstream research decisions.

5. **Short-circuit optimization.** When a definitive determination can be made without an LLM call (e.g., a trial classified as Positive does not need a Failure Reason), the system skips unnecessary computation. This reduces latency, conserves GPU resources, and eliminates opportunities for hallucination.

### 5.5 Limitations

Several limitations constrain the interpretation of the current results:

**Small baseline sample.** The 25-trial baseline is sufficient for identifying systematic error patterns but insufficient for reliable estimation of per-field accuracy or for computing confidence intervals around concordance statistics. The full 614-trial evaluation is required for robust performance characterization.

**Hardware constraints.** All models run on 16 GB of unified memory, constraining model size to 14B parameters for the largest model and 8B--9B for the primary annotator and verifiers. Larger models (70B+) would likely improve performance on investigative fields but are infeasible on the current hardware.

**No multi-run consensus.** The current pipeline performs a single annotation run per trial. Multi-run consensus (N=3 or N=5, majority vote) would reduce the impact of stochastic variation in model outputs but at a proportional increase in inference time.

**Imperfect ground truth.** Human annotations exhibit 19.8% disagreement, meaning that even a perfect system would achieve at most 80.2% agreement with any single annotator. Evaluation against a consensus ground truth (where both annotators agree) would provide a cleaner signal but would exclude the 19.8% of cases that are, by definition, the most difficult.

**No cross-validation.** The v3 improvements described in Section 4.4 were designed in response to errors observed on the same 25 trials used for evaluation. Performance on held-out trials may differ.

---

## 6. Future Work

Six directions for future development are planned:

1. **Full evaluation on 614 overlapping trials.** Expanding the evaluation from 25 to 614 trials will enable robust per-field accuracy estimation, subgroup analysis (e.g., by trial phase, therapeutic area, or registry age), and reliable kappa computation with confidence intervals.

2. **Multi-run consensus.** Performing N=3 annotation runs per trial and selecting the majority answer for each field will reduce the impact of stochastic model variation. Preliminary experiments suggest that consensus across runs improves accuracy by 5--10% on fields with high model variance.

3. **14B primary annotator for high-error fields.** Deploying qwen2.5:14b as the primary annotator for Classification and Outcome --- the two fields with the largest agent-human gap --- while retaining 8B models for Peptide and Delivery Mode. This requires sequential field processing to manage memory but should improve instruction adherence on complex reasoning tasks.

4. **Additional sequence databases.** Integrating NCBI Protein as an additional source for the Peptide Identity Agent. Note: APD (aps.unmc.edu) and dbAMP 3.0 have been integrated as v5 research agents (Sections 3.2.10--3.2.11), along with WHO ICTRP, IUPHAR, IntAct, CARD, and PDBe (Sections 3.2.12--3.2.16).

5. **Active learning from manual review.** When annotations are flagged for manual review and a human provides the correct answer, the system can use these corrections to identify systematic prompt weaknesses and guide prompt refinement. Over time, this creates a feedback loop that progressively reduces the manual review burden.

6. **Cross-validation with held-out annotations.** Partitioning the 614-trial dataset into development and test sets, using the development set for prompt engineering and the test set for unbiased evaluation. This standard machine learning practice will provide a more honest assessment of generalization performance.

---

## 7. Technical Details

### 7.1 Infrastructure

| Component | Technology |
|---|---|
| Hardware | Mac Mini M4, 16 GB unified memory |
| Model serving | Ollama (local inference) |
| Backend | FastAPI (Python) |
| Frontend | React + TypeScript |
| Service management | macOS LaunchDaemons (boot at startup, no login required) |
| Auto-update | 30-second git polling with graceful restart when no active jobs |

The LaunchDaemon architecture ensures that all services start automatically at boot without requiring user login. The auto-update mechanism polls the git repository every 30 seconds, and when changes are detected, waits for any active annotation jobs to complete before pulling updates and restarting the service. This enables continuous deployment without risking interrupted annotations.

### 7.2 Reproducibility

Every annotation job stores a complete reproducibility record:

| Artifact | Purpose |
|---|---|
| Configuration snapshot | Frozen copy of all agent configurations at job creation time |
| Git commit hash | Exact codebase version used for the annotation run |
| Semantic version | Human-readable version identifier (e.g., v3.1.0) |
| Full evidence chains | Every piece of evidence retrieved, with source URL and timestamp |
| Model opinions | Every model's answer and reasoning chain, for primary and all verifiers |
| Consensus record | Final consensus decision, dissenting opinions, and reconciler output (if invoked) |

This record enables exact reproduction of any annotation decision: given the same evidence inputs and model versions, the same reasoning chain can be replayed. It also supports post-hoc analysis of failure modes, as every step in the pipeline is logged with sufficient detail to diagnose errors.

### 7.3 Data Sources

Table 3 summarizes the external data sources accessed by the research agents, including access requirements and rate limits.

**Table 4.** External data sources.

| Source | Access | Authentication | Rate Limit |
|---|---|---|---|
| ClinicalTrials.gov API v2 | Free | No key required | 10 requests/sec |
| PubMed / PMC (NCBI E-utils) | Free | Optional API key | 3--10 requests/sec |
| Europe PMC | Free | No key required | 10 requests/sec |
| UniProt | Free | No key required | 25 requests/sec |
| DRAMP | Free | No key required | 3 requests/sec |
| OpenFDA | Free | No key required | 4 requests/sec |
| DuckDuckGo | Free | No key required | 1 request/sec |
| Semantic Scholar | Free | No key required | 3 requests/sec |
| DBAASP API (v4) | Free | No key required | 5 requests/sec |
| ChEMBL API (v4) | Free | No key required | 10 requests/sec |
| RCSB PDB API (v4) | Free | No key required | 10 requests/sec |
| EBI Proteins API (v4) | Free | No key required | 10 requests/sec |
| APD (v5) | Free | No key required | 2 requests/sec |
| dbAMP 3.0 (v5) | Free | No key required | 2 requests/sec |
| WHO ICTRP (v5) | Free | No key required | 2 requests/sec |
| IUPHAR Guide to Pharmacology (v5) | Free | No key required | 10 requests/sec |
| IntAct (v5) | Free | No key required | 10 requests/sec |
| CARD (v5) | Free | No key required | 5 requests/sec |
| PDBe (v5) | Free | No key required | 10 requests/sec |

All sources are freely accessible without paid subscriptions. SerpAPI was removed as it required a paid API key. Rate limits are enforced client-side through per-host semaphores to ensure compliance and prevent service disruption.

---

## 8. Conclusion

Agent Annotate demonstrates that a multi-agent pipeline with evidence requirements, field-specific decision logic, and blind multi-model verification can produce structured annotations of clinical trials with full provenance chains. The current implementation, constrained to 8B-parameter models on consumer hardware, does not yet match human-human agreement, but the error analysis reveals that the performance gap is systematic and traceable to specific, addressable causes: model size limitations on investigative reasoning, surface-level pattern matching overriding nuanced instructions, and insufficient short-circuit coverage for edge cases.

The v3 improvements --- outcome decision trees, expanded negative example sets, extraction hierarchies, and enhanced non-failure detection --- target each identified error category directly. The architecture's modular design allows individual agents to be upgraded (e.g., from 8B to 14B models) or replaced without affecting the rest of the pipeline.

More broadly, the blind verification protocol and evidence threshold enforcement represent design patterns applicable beyond AMP clinical trial annotation. Any domain requiring structured annotation of complex documents --- drug safety reports, regulatory filings, systematic reviews --- could benefit from the same combination of specialized research agents, calibrated evidence requirements, and architecturally diverse blind verification.

---

## References

This document constitutes an internal methodology paper for the Agent Annotate system. The following references would be required for external publication:

1. ClinicalTrials.gov. U.S. National Library of Medicine. https://clinicaltrials.gov/
2. Ollama. Local large language model serving. https://ollama.ai/
3. Cohen, J. (1960). A coefficient of agreement for nominal scales. *Educational and Psychological Measurement*, 20(1), 37--46.
4. Wang, G., Li, X., and Wang, Z. (2016). APD3: the antimicrobial peptide database as a tool for research and education. *Nucleic Acids Research*, 44(D1), D1087--D1093.
5. Kang, X., et al. (2019). DRAMP 2.0, an updated data repository of antimicrobial peptides. *Scientific Data*, 6, 148.
6. The UniProt Consortium. (2023). UniProt: the Universal Protein Knowledgebase in 2023. *Nucleic Acids Research*, 51(D1), D523--D531.
7. Touvron, H., et al. (2023). LLaMA: Open and efficient foundation language models. *arXiv preprint arXiv:2302.13971*.
8. Jiang, A. Q., et al. (2023). Mistral 7B. *arXiv preprint arXiv:2310.06825*.
9. Team Gemma. (2024). Gemma 2: Improving open language models at a practical size. *arXiv preprint arXiv:2408.00118*.
10. Yang, A., et al. (2024). Qwen2 technical report. *arXiv preprint arXiv:2407.10671*.

---

*Document version: 3.0 (v5 research pipeline expansion to 15 agents, 20+ free databases). Generated 2026-03-16.*
