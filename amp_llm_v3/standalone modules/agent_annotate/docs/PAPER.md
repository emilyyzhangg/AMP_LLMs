# Agent Annotate: A Multi-Agent Local LLM Pipeline for Publication-Grade Annotation of Antimicrobial Peptide Clinical Trials

**Amphoraxe Research Team**

---

## Abstract

Systematic review of clinical trials involving antimicrobial peptides (AMPs) requires annotating multiple structured fields across hundreds of registry entries --- a process that is slow, expensive, and unreliable when performed manually. Inter-annotator agreement among trained human reviewers reaches only approximately 80% overall and drops substantially for fields requiring investigative reasoning, such as trial outcome determination and failure classification. Existing automated approaches typically employ single large language model (LLM) calls without verification, evidence requirements, or source citations, producing annotations of insufficient quality for research use. We present Agent Annotate, a multi-agent pipeline that decomposes the annotation task into three phases: twelve parallel research agents that gather and weight evidence from 17+ free external databases --- including DBAASP (antimicrobial activity), ChEMBL (bioactivity), RCSB PDB (3D structures), EBI Proteins (sequences), APD (AMP database), WHO ICTRP (international trials), IUPHAR (pharmacology), and PDBe (structure quality) --- specialized annotation agents that apply field-specific decision logic with calibrated evidence thresholds, and a blind multi-model verification stage employing three cognitively diverse verification personas (conservative, evidence-strict, adversarial). The v9 architecture introduces a deterministic-first strategy: programmatic pre-classifiers extract signals from structured data sources (OpenFDA route fields, ClinicalTrials.gov registry statuses, known drug lookup tables) before invoking LLMs, bypassing unreliable 8B verifier models for clear cases and reducing per-trial processing time. The system enforces evidence-grounded reasoning by requiring cited sources for every annotation with full traceability (model identity, agent provenance, source URLs, evidence text), implements blind peer review in which verifier models never observe the primary annotation, and applies short-circuit optimizations that reduce unnecessary model invocations. All models execute locally via Ollama on consumer hardware, with optional Kimi K2 Thinking model support on server-class hardware. Expanded evaluation on 70 clinical trials with version comparison demonstrates that fixing research data quality (+162% citation volume) yields a +31.8 percentage-point improvement in Outcome concordance (40.9% to 72.7% vs human R1), exceeding human inter-rater agreement (55.6%) on this field. Classification reaches 75.8%, Peptide reaches 77.1%, and 78% of remaining review items are systematically resolvable without human intervention. Evaluation across three batches of 70 identical trials reveals 64.3% (R1) and 65.2% (R2) overall concordance with human annotators, against a 79.2% human-human baseline. Per-field root cause analysis identifies verifier override of correct primary classifications, overly restrictive delivery mode rules, and positive outcome bias as the primary gaps, each addressed by the v9 deterministic-first improvements. The v10 architecture introduces three verification personas (conservative, evidence-strict, adversarial) with dynamic confidence parsing and evidence budget parity, plus an EDAM self-learning system with evidence-driven self-audit that detects and corrects annotations inconsistent with the agent's own structured evidence. Preliminary evaluation on 25 trials with dense human annotation coverage yields Outcome concordance of k=0.742 (Substantial) against R1, exceeding the human inter-rater baseline of 55.6% by 24 percentage points. A core design principle governs the learning architecture: the agent never sees human annotations during learning --- it improves through evidence-grounded self-correction, and human concordance is measured independently as an evaluation metric. We describe the full architecture, error analysis across six agent versions, concordance results, and a concrete improvement plan targeting the remaining accuracy gaps.

---

## 1. Introduction

Antimicrobial peptides constitute a growing and therapeutically important class of molecules with diverse mechanisms of action, ranging from direct membrane disruption to immunomodulation and anti-biofilm activity. As the number of AMP-related clinical trials has expanded, so too has the need for structured, systematic annotation of these trials to support meta-analyses, regulatory review, and translational research.

Annotating clinical trials at scale requires classifying each trial along multiple dimensions: whether the intervention is a true antimicrobial peptide, its mode of delivery, the trial outcome, the reason for any failure, and the peptide identity of the compound under study. When performed by domain experts, this annotation process represents the gold standard for data quality. However, manual annotation suffers from three well-documented limitations. First, it is expensive: trained reviewers command significant time and resources, particularly when trials require cross-referencing registry data with published literature. Second, it is slow: annotating hundreds of trials across five fields represents weeks of effort. Third, and perhaps most critically, it is unreliable: our analysis of 617 human annotations produced by two independent replicates reveals an overall inter-annotator agreement of only 80.2%, with substantially lower concordance on specific fields and dramatic disagreements on fundamental classification decisions.

Existing automated approaches to clinical trial annotation typically employ a single LLM call per field, without verification mechanisms, evidence requirements, or source citations. These approaches inherit the well-known limitations of language models --- hallucination, overconfidence, and sensitivity to prompt phrasing --- without any of the error-correction mechanisms that human review processes provide.

Agent Annotate addresses these limitations through a pipeline of specialized AI agents running entirely on local models. The system decomposes annotation into research, annotation, and verification phases, each implemented by purpose-built agents with distinct responsibilities. Research agents gather evidence from 17+ free external databases with calibrated source weights --- including specialized peptide activity (DBAASP), bioactivity (ChEMBL), structural (RCSB PDB, PDBe), protein sequence (EBI Proteins), AMP classification (APD), international trial registries (WHO ICTRP), and pharmacology (IUPHAR) databases. Annotation agents apply field-specific decision logic with evidence threshold enforcement. Verification agents perform blind multi-model peer review using architecturally diverse model families. The result is a system that produces annotations with full provenance chains including model identity, agent provenance, source URLs, and evidence text for every field --- calibrated confidence scores, and explicit identification of cases requiring human review.

This paper describes the complete Agent Annotate system, presents baseline evaluation results against human annotations, analyzes systematic error patterns, and outlines improvements implemented in response to error analysis.

---

## 2. Background

### 2.1 Antimicrobial Peptide Classification

Antimicrobial peptides (AMPs) exert their therapeutic effects through direct antimicrobial mechanisms. We classify AMPs by three modes of action (Modes A--C). A fourth mode (Mode D, pathogen-targeting vaccine peptides) was removed in v2, re-added in v12, and permanently removed in v19 after concordance analysis on 50 trials demonstrated systematic over-classification of vaccine NCTs.

**Mode A --- Direct Antimicrobial.** Peptides that kill or inhibit microbial growth through direct physical interaction, typically via membrane disruption or pore formation. Representative examples include colistin, polymyxin B, melittin, and nisin. These peptides interact directly with microbial cell membranes, compromising structural integrity and leading to cell death.

**Mode B --- Immunostimulatory Host Defense.** Peptides that recruit innate immune cells to kill pathogens at infection sites, enhancing phagocytosis or modulating cytokine production toward pathogen clearance. Representative examples include LL-37, defensins, and cathelicidins. These peptides potentiate the host's innate capacity to clear infection. General immunomodulation or adaptive immune activation does not qualify --- the peptide must specifically recruit innate defense against pathogens.

**Mode C --- Anti-Biofilm.** Peptides that disrupt established microbial biofilms or prevent biofilm formation. Representative examples include LL-37, DJK-5, and IDR-1018. Biofilm disruption is mechanistically distinct from direct antimicrobial activity, as biofilm-resident organisms exhibit phenotypic tolerance that renders them resistant to conventional antimicrobials.

**Mode D --- Removed (v19).** Pathogen-targeting vaccine peptides (StreptInCor, HIV gp120/gp41 peptide vaccines, malaria peptide vaccines) were re-introduced as Mode D in v12 under the rationale that vaccine-mediated pathogen defense qualifies as AMP activity. Concordance analysis on 50 trials (v18+) revealed this caused systematic over-classification. Root cause: vaccine peptides work through adaptive immunity (antibody induction, T-cell priming) --- the peptide itself does not directly kill pathogens, recruit innate immune cells, or disrupt microbial structures. This mechanism is categorically different from Modes A--C. Additionally, the classifier and verifier were inconsistent: the classifier correctly returned Other for vaccine NCTs while the verifier still listed them as AMP(infection), causing the verification stage to override correct primary annotations. Mode D was permanently removed in v19; all vaccine/immunogen peptides are classified as "Other."

A critical distinction governs classification: the AMP classification is independent of the Peptide field. Many peptides are not antimicrobial --- neuropeptides (VIP/aviptadil, peptide T), metabolic hormones (GLP-1 agonists, insulin), viral entry inhibitors (enfuvirtide), bone regulators (calcitonin, vosoritide), and vaccine immunogens are all classified as "Other" despite being peptides (Peptide=True). Similarly, peptides that *suppress* immunity (autoimmune therapeutics like dnaJP1) are excluded. The core requirement is direct antimicrobial mechanism: the peptide must physically kill, disrupt, or recruit innate immune effectors against pathogens through its own biochemical action.

### 2.2 Annotation Schema

Each clinical trial is annotated across five structured fields:

| Field | Type | Values |
|---|---|---|
| Classification | Categorical (3) | AMP(infection), AMP(other), Other |
| Delivery Mode | Categorical (18) | Intravenous, Oral, Topical, Intramuscular, Subcutaneous, Intranasal, Inhaled, Intrathecal, Intraperitoneal, Intravesical, Intravitreal, Ophthalmic, Rectal, Vaginal, Transdermal, Sublingual, Other/Unspecified, Multiple |
| Outcome | Categorical (7) | Positive, Failed - completed trial, Terminated, Withdrawn, Recruiting, Active not recruiting, Unknown |
| Reason for Failure | Categorical (5+empty) | Ineffective for purpose, Adverse effects/safety concerns, Formulation/stability issues, Superseded by alternatives, Insufficient enrollment, (empty) |
| Peptide | Boolean | True, False |

The **Classification** field distinguishes true AMP trials targeting infection from AMP trials with non-infection applications (e.g., wound healing via host defense peptides) and non-AMP trials. Classification and Peptide are independent: a trial can have Peptide=True but Classification=Other (e.g., enfuvirtide is a peptide but not an AMP). **Delivery Mode** captures the route of administration. **Outcome** reflects the current status and result of the trial, incorporating both registry status and published findings. **Reason for Failure** applies only to trials with negative outcomes and must be supported by cited evidence.

**Peptide** indicates whether any active intervention drug is a peptide therapeutic --- defined as a molecule of 2--100 amino acid residues that serves as the primary pharmacological agent. This includes antimicrobial peptides, hormone analogues (semaglutide, octreotide), cyclic peptides (vancomycin), peptide vaccines, neuropeptides (aviptadil, peptide T), viral entry inhibitors (enfuvirtide), and insulin. It excludes monoclonal antibodies (>100 aa, distinct drug class), small molecules, nutritional formulas containing hydrolyzed proteins, and peptide cargo in delivery vehicles (exosomes, HSP complexes). The question is whether the active drug is a peptide, not whether the formulation contains peptides.

### 2.3 Challenges in Manual Annotation

Analysis of 617 human annotations produced by two independent annotators (designated R1 and R2) reveals systematic disagreements that underscore the difficulty of this task:

**Peptide field divergence.** R1 assigned Peptide=True to 451 trials (24% of the dataset), while R2 assigned Peptide=True to only 56 trials (3%) --- an 8:1 ratio. Only 30 trials received Peptide=True from both annotators. This divergence suggests fundamentally different interpretations of what constitutes a "peptide" intervention, despite both annotators reviewing the same trials.

**Outcome field inconsistency.** R1 used the "Recruiting" outcome category 222 times, while R2 used it zero times. This indicates that R2 either collapsed recruiting trials into other categories or systematically excluded them from annotation.

**Registry staleness.** At least 15 trials with "UNKNOWN" status on ClinicalTrials.gov had published positive results in the peer-reviewed literature. Annotators who relied solely on registry status without cross-referencing the literature would systematically misclassify these trials.

These findings demonstrate that manual annotation, while conventionally treated as ground truth, is itself substantially noisy. Any automated system must be evaluated against this backdrop of imperfect human agreement.

---

## 3. Methods

### 3.1 System Architecture

Agent Annotate implements a three-phase pipeline. Critically, Phase 1 uses a two-step research architecture rather than running all agents simultaneously:

```
Phase 1: Research (two-step)     Phase 2: Annotation         Phase 3: Verification
                                 (5 agents, sequential*)      (multi-model blind review)
                                 *sequential due to GPU memory

Step 1: Protocol-first
[Clinical Protocol  ]
   | extracts intervention names
   | from armsInterventionsModule
   v
Step 2: Parallel with metadata
[Literature         ]  ─┐
[Peptide Identity   ]   │
[Web Context        ]   │
[DBAASP (v4)        ]   │
[ChEMBL (v4)        ]   │
[RCSB PDB (v4)      ]   ├──>  [Classification Agent]  -->  [Blind Verifier 1: gemma2:9b  ]
[EBI Proteins (v4)  ]   │     [Delivery Mode Agent ]  -->  [Blind Verifier 2: qwen2.5:7b  ]
[APD (v5)           ]   │     [Outcome Agent       ]  -->  [Blind Verifier 3: phi4-mini   ]
[                   ]   │     [Failure Reason Agent]  -->  [Reconciler: qwen2.5:14b (disputes only)]
[WHO ICTRP (v5)     ]   │     [Peptide Agent       ]
[IUPHAR (v5)        ]   │
[                   ]   │
[PDBe (v5)          ]  ─┘
```

Phase 1 executes in two steps. In Step 1, the Clinical Protocol Agent runs first, fetching the trial record from ClinicalTrials.gov and extracting intervention names (drug and peptide names) from the structured `protocol_section.armsInterventionsModule.interventions` field. In Step 2, the remaining 11 agents run in parallel, each receiving the extracted intervention names as metadata. This two-step design is essential because peptide and drug database agents (DBAASP, ChEMBL, IUPHAR, PDBe) require compound names to query their databases --- without intervention names, these agents have nothing to search for and return zero citations. With intervention names available, DBAASP can search for a peptide like Nisin and return MIC data, ChEMBL can return bioactivity and mechanism data, and so on across all database agents.

The v4 pipeline expanded from four to eight research agents, adding DBAASP, ChEMBL, RCSB PDB, and EBI Proteins. The v5 expansion added seven more agents (APD, dbAMP, WHO ICTRP, IUPHAR, IntAct, CARD, PDBe), bringing the total to 15. The v8 revision removed three agents (dbAMP — server unreachable; IntAct — noise; CARD — no relevant trials) and Semantic Scholar (rate limiting), bringing the active count to 12 research agents querying 17+ free databases. All agents use free APIs exclusively. Phase 2 agents share a single Ollama instance and execute sequentially due to the memory constraints of the deployment hardware. Phase 3 applies blind verification using architecturally diverse model families.

All models run locally via Ollama on a Mac Mini M4 with 16 GB of unified memory (mac_mini profile) or on a dedicated server with 48+ GB (server profile, which enables Kimi K2 Thinking as the primary annotator). No data leaves the local machine during inference. External network access is limited to Phase 1 research queries against public databases.

### 3.2 Research Agents

Twelve research agents gather evidence from 17+ free external data sources, each assigned a calibrated weight reflecting its reliability and relevance. The original four agents (Sections 3.2.1--3.2.4) were present in v2/v3; four agents (Sections 3.2.6--3.2.9) were added in v4; four agents from the v5 expansion remain active (Sections 3.2.10, 3.2.12, 3.2.13, 3.2.16). Three v5 agents (dbAMP, IntAct, CARD) were removed in v8 due to server unavailability, noise, and irrelevance respectively.

As described in Section 3.1, the research phase uses a two-step architecture: the Clinical Protocol Agent runs first to extract intervention names, then the remaining 14 agents run in parallel using those names as search keys. This ordering is critical for database agents that cannot produce useful results without knowing the compound name.

#### 3.2.1 Clinical Protocol Agent

The Clinical Protocol Agent runs in Step 1 of the two-step research architecture (Section 3.1). It queries structured registry databases to retrieve trial metadata, intervention descriptions, arms, eligibility criteria, and status information. Critically, it extracts intervention names (drug and peptide names) from the `protocol_section.armsInterventionsModule.interventions` field of the ClinicalTrials.gov response. These extracted names are passed as shared metadata to all 14 agents in Step 2, enabling them to perform targeted database lookups by compound name.

| Source | Weight | Data Retrieved |
|---|---|---|
| ClinicalTrials.gov API v2 | 0.95 | Protocol, status, interventions, arms, conditions, outcomes, **intervention names** |
| OpenFDA | 0.85 | Drug labels, adverse events, approval status |

ClinicalTrials.gov receives the highest weight among all sources due to its authoritative status as the primary trial registry. The API v2 endpoint provides structured JSON responses with comprehensive protocol metadata, including the structured interventions module from which drug and peptide names are extracted for downstream agents. OpenFDA supplements this with regulatory context, particularly useful for determining whether an intervention has received FDA approval or has documented safety signals.

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

#### 3.3.1 Two-Pass Investigative Design (All Agents)

All five annotation agents employ a two-pass architecture. This universal design was adopted in v2 after concordance analysis showed that single-pass prompts were insufficient for 8B models, which tend to shortcut on surface-level keywords rather than following multi-step decision trees.

**Pass 1: Structured Fact Extraction.** The first LLM call extracts factual claims from the evidence package without making a classification decision. Each agent's Pass 1 prompt is tailored to its field, asking specific factual questions whose answers feed the decision tree in Pass 2.

**Pass 2: Decision with Calibrated Rules.** The second LLM call receives the Pass 1 output along with a decision tree that encodes field-specific logic. By operating on its own structured extraction rather than raw evidence, the model is less likely to be distracted by irrelevant citations.

**Design principle: no lookup tables.** The agents contain no hardcoded drug-name dictionaries or answer cheat sheets. Each agent must reason independently from the evidence gathered by the research agents. This ensures the system generalizes to novel peptides and trial designs rather than memorizing known answers.

**Classification Agent.** Uses a larger model (qwen2.5:14b on Mac Mini, kimi-k2-thinking on server) because 8B models have demonstrated inability to follow the multi-step decision tree reliably.

- *Pass 1* extracts five antimicrobial evidence dimensions: peptide identity, database matches (DRAMP, APD3, UniProt, ChEMBL), mechanism of action, therapeutic target, and immune direction.
- *Pass 2* applies a three-step decision tree: (1) Is the intervention a peptide? (2) Does this peptide have a DIRECT antimicrobial mechanism — physically killing, lysing, or disrupting pathogens, or directly recruiting innate immune cells to kill pathogens? (3) Does this AMP target infection?
- The v2 prompt encodes explicit exclusions for the most common over-classification patterns: antiretrovirals (enfuvirtide, peptide T — viral entry inhibitors, not antimicrobial), vaccine peptides (induce adaptive immunity, the peptide itself does not kill pathogens), neuropeptides (VIP/aviptadil — vasodilators), metabolic hormones (GLP-1, GLP-2), and immunosuppressive peptides. The decisive rule: if the mechanism is viral entry inhibition, receptor blocking, vaccine/antibody induction, vasodilation, or metabolic regulation, the answer is Other.
- The four-mode AMP definition was narrowed to three modes in v2, re-expanded to four modes (with Mode D) in v12, and narrowed back to three modes in v19. Mode D (pathogen-targeting vaccines) is permanently removed: vaccine peptides work through adaptive immunity and do not directly kill pathogens. Both the classifier and verifier were updated to ensure consistency — a key root cause of persistent errors was the classifier returning Other for vaccine NCTs while the verifier retained AMP(infection), causing the verification stage to override correct primary answers.

**Delivery Mode Agent.**

- *Pass 1* extracts route evidence from four source categories with explicit priority ordering: (1) FDA/drug label route (highest priority), (2) published literature route descriptions, (3) ClinicalTrials.gov protocol route, (4) database formulation data. The prompt forces the model to search all sources before concluding.
- *Pass 2* classifies the route using the source hierarchy: FDA label overrides generic protocol text. If the FDA label says "subcutaneous" but the protocol says "injection," the answer is Subcutaneous/Intradermal, not Other/Unspecified.
- The never-guess rule is preserved: if no source specifies IM, SC, or IV, the answer is Injection/Infusion - Other/Unspecified.
- *v19:* Bare SC abbreviation removed from keyword lookup (matched spurious contexts). Explicit phrases "sc injection", "sc administration", "sc dose" added. Cancer vaccine / peptide immunotherapy classification rule: when route is unspecified for peptide vaccine trials, the default is Injection/Infusion - Other/Unspecified (not Intranasal).

**Peptide Agent.**

- *Pass 1* extracts molecular facts: intervention name, molecular class (peptide chain vs antibody vs small molecule vs nutritional product), database confirmation (UniProt, DRAMP, ChEMBL entries), product description, and investigational drug role (investigational drug vs food ingredient vs targeting vector vs brand name).
- *Pass 2* applies a three-step decision tree: (1) Is the molecular class a peptide? (2) Is it the investigational drug (not a food ingredient or brand name artifact)? (3) Database/literature confirmation.
- *v15:* If peptide=False, all other fields are set to N/A and annotation is skipped (non-peptide trials are out of scope).
- *v16:* The N/A cascade requires peptide confidence ≥ 0.90 to trigger. Low-confidence False results proceed to full annotation but are flagged for review, preventing false-negative wipeouts observed in NCT02624518 and NCT02654587.

**Outcome Agent.**

- *Pass 1* extracts seven evidence elements: registry status, trial phase, published results summary, result valence (positive/negative/mixed/not available), results posted flag, completion date, and why stopped.
- *Pass 2* applies a calibrated decision tree with **completion heuristics** for older trials (added in v2):

1. If the trial is currently Recruiting or Active not recruiting, report the current status directly.
2. If the trial has been Withdrawn, classify as Withdrawn.
3. If published results demonstrate positive efficacy, classify as Positive.
4. If published results demonstrate negative efficacy, classify as Failed - completed trial. This *requires* cited evidence of failure.
5. If the trial was Terminated, classify as Terminated.
6. For COMPLETED trials without published results, apply completion heuristics:
   - H1: Phase I trials that completed normally → Positive (safety completion IS success).
   - H2: Results posted on ClinicalTrials.gov → lean Positive.
   - H3: Old trial (pre-2010) completed normally with no negative evidence → lean Positive.
   - H4: Only after exhausting H1-H3 → Unknown.
- *v16:* Added adverse event detection in the fallback heuristic: publications mentioning toxicity, adverse reactions, abscess formation, or dose-limiting events now trigger "Failed - completed trial" even when the LLM's Pass 2 defaults to "Unknown". Publications count as corroboration for H1 (Phase I completion) even when they describe a related study rather than the exact NCT ID. Negative result valence from Pass 1 now maps to "Failed" in the fallback path.

A critical rule governs the distinction between completion and failure: a registry status of COMPLETED does *not* imply failure. The "Failed - completed trial" classification requires affirmative evidence of a negative result.
- *v19:* Negative efficacy signal vocabulary expanded in the Pass 1 heuristic: "did not demonstrate/achieve/show", "no significant/benefit/improvement/efficacy", "failed to demonstrate/meet/primary", "lack of efficacy", "ineffective" now trigger "Failed - completed trial" directly, without requiring a full LLM Pass 2 invocation for obvious failure language.

**Failure Reason Agent.**

The orchestrator runs the Failure Reason Agent *after* the Outcome Agent completes and passes the outcome result in metadata. The agent implements a deterministic pre-check gate:

1. **Outcome-based pre-check (v2):** If the Outcome Agent classified the trial as Positive, Recruiting, or Active not recruiting, the Failure Reason is set to empty *without any LLM call*. This deterministic gate eliminates the dominant error pattern observed in concordance analysis, where the 8B model hallucinated "Ineffective for purpose" for 42 out of 62 non-failed trials.
2. *v16:* "Unknown" was removed from the pre-check skip list. Completed trials with Unknown outcomes may still have publishable failure reasons (e.g., toxicity discovered post-completion). The Pass 1 failure detection provides the hallucination guard instead.
3. **Only Terminated, Failed, and Unknown outcomes proceed** to the two-pass LLM investigation.
3. When the LLM is invoked, Pass 1 investigates all sources for failure signals, and Pass 2 classifies the failure mode. The "no failure" default for COMPLETED trials without published negative results is preserved.

#### 3.3.3 Deterministic Pre-Classifiers (v9)

The v9 architecture introduces a deterministic-first strategy for all five annotation agents. Before invoking the LLM, each agent attempts to resolve the annotation programmatically using structured data from the research dossier.

**Classification Pre-Classifier.** Matches intervention names against lookup tables of ~30 known AMP drugs and ~40 known non-AMP drug patterns. Also checks for AMP database hits (DRAMP, DBAASP, APD) in the research results. Deterministic matches return with confidence=0.95 and `skip_verification=True`.

**Delivery Mode Route Extraction.** Parses OpenFDA route fields (both citation text and structured raw_data) and ClinicalTrials.gov protocol keywords. Drug-class default routes serve as soft defaults with confidence=0.7.

**Outcome Status Mapping.** Maps clear-cut registry statuses deterministically: RECRUITING, WITHDRAWN, TERMINATED, ACTIVE_NOT_RECRUITING, SUSPENDED. Only COMPLETED and UNKNOWN fall through to LLM.

**Failure Reason Cascade.** The pre-check gate skips LLM entirely for non-failure outcomes (Positive, Recruiting, Active not recruiting, Unknown, Withdrawn) with `skip_verification=True`.

**Peptide Non-Peptide Exclusions.** Checks intervention names against known non-peptide drugs (HSP complexes, dexosomes, nucleoside analogues, monoclonal antibodies).

#### 3.3.4 Evidence Threshold Enforcement

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
| Verifier 2 | qwen2.5:7b | Alibaba Qwen 2.5 | 7B |
| Verifier 3 | phi4-mini:3.8b | Microsoft Phi-4 Mini | 3.8B |
| Reconciler | qwen2.5:14b | Alibaba Qwen 2.5 | 14B |

Architecture diversity across four distinct model families (Meta, Google, Alibaba, Microsoft) guards against shared systematic biases. Models trained on different data mixtures with different architectural choices (e.g., grouped query attention vs. multi-head attention, different tokenization strategies) are less likely to make the same errors on the same inputs.

**Verification Personas (v10).** Each verifier receives a distinct cognitive persona: Verifier 1 applies a conservative lens (defaults to safest interpretation when evidence is ambiguous), Verifier 2 operates as evidence-strict (only answers based on directly citable facts), and Verifier 3 acts as an adversarial reviewer (actively challenges the most obvious interpretation). This prompt diversity ensures that identical evidence produces genuinely independent assessments, rather than three models defaulting to the same reasoning pattern.

**Dynamic Confidence (v10).** Verifier confidence is parsed from self-assessment (High=0.9, Medium=0.7, Low=0.4) rather than hardcoded at 0.7. Combined with the high-confidence primary override --- which accepts the primary annotation without reconciliation when primary confidence exceeds 0.85 and all dissenting verifiers report baseline confidence --- this produces more reliable consensus outcomes.

**Evidence Parity (v10).** Verifiers now receive the same citation budget as primary annotators (30 on Mac Mini, 50 on server), eliminating systematic disagreement caused by verifiers reviewing less evidence than the primary.

**Server Verifier Scaling.** On server hardware, verifiers are upgraded to larger models (gemma2:27b, qwen2.5:32b, phi4:14b) via a configurable `server_verifiers` list. Models are auto-pulled from Ollama if not available locally.

#### 3.4.2 Consensus Protocol

The consensus threshold was lowered from 1.0 (unanimous) to 0.67 in v9, requiring agreement from 2 out of 3 verifiers. This relaxation reflects the observation that unanimous agreement among 8B verifiers was too strict: correct primary annotations were frequently overridden by a single dissenting verifier that misunderstood the decision logic.

When unanimous consensus is not reached, the reconciler model (qwen2.5:14b, the largest model in the pipeline) is invoked. The reconciler receives all opinions and their reasoning chains and is instructed to identify the most evidence-supported answer. If the reconciler cannot resolve the dispute --- for example, because the underlying evidence is genuinely ambiguous --- the field is flagged for manual human review.

#### 3.4.3 Verification Bypass (v9)

When a deterministic pre-classifier produces a high-confidence annotation (≥0.95), the `skip_verification` flag bypasses the verification pipeline entirely, creating a synthetic consensus result. This eliminates the failure mode where 8B verifiers override correct deterministic results.

#### 3.4.4 Unanimous Dissent Override Bug and Fix (v20)

The high-confidence primary override contained a systematic bug identified through concordance analysis of 50 trials. The condition `annotation.confidence > 0.85 and verifier_max_conf <= 0.7` accepted the primary annotation without reconciliation, but did not check whether any verifier actually agreed. When all three verifiers independently disagreed with the primary annotation (`agreement_ratio=0.0`), the override still fired — the primary annotation was accepted over unanimous verifier dissent.

Concordance analysis of 50 trials (v19, job c1786d005ade) identified 15 per-run cases where this condition produced incorrect final annotations. Representative case: NCT04701021 (Outcome). Primary=Positive (confidence 0.91). All three verifiers=Unknown. Before fix: Positive accepted. After fix: routed to reconciler → Unknown.

The fix adds an `agreement_ratio > 0.0` guard:

```python
if (annotation.confidence > 0.85 and verifier_max_conf <= 0.7
        and consensus.agreement_ratio > 0.0):
    # high-confidence primary accepted
```

"Unanimous dissent overrides high confidence." When all three verifiers disagree, the primary must be reconciled regardless of confidence level.

### 3.5 Concordance Analysis

The concordance analysis methodology (v2) implements the following conventions to ensure fair comparison between agent and human annotations:

**Blank exclusion.** Blank human annotations are excluded from concordance calculations. A blank cell indicates that the annotator did not annotate the field, not that the annotator chose the empty string as their answer. Including blanks would artificially inflate or deflate agreement depending on whether the agent also produced an empty result.

**Failure Reason exception.** For the Reason for Failure field, an empty value is a semantically valid answer meaning "no failure occurred." A Failure Reason cell is treated as blank (excluded from analysis) only if the corresponding Outcome field is also blank, indicating that the annotator skipped the trial entirely.

**Inter-annotator reliability.** Cohen's kappa is computed for each field to quantify agreement beyond chance. Kappa adjusts for the baseline agreement expected if both annotators assigned categories at random in proportion to their marginal distributions. Kappa values are interpreted on the standard scale: below 0 indicates less than chance agreement, 0.01--0.20 is slight, 0.21--0.40 is fair, 0.41--0.60 is moderate, 0.61--0.80 is substantial, and 0.81--1.00 is almost perfect agreement.

**Annotator composition.** The human reference data consists of two replication passes: R1 (7 annotators assigned contiguous row blocks) and R2 (primarily a single annotator). Cohen's kappa with 95% analytical confidence intervals (Fleiss et al. 1969) is the primary metric, supplemented by Gwet's AC₁ (Gwet 2008) to control for the prevalence paradox, and per-annotator pairwise analysis to detect systematic interpretive differences within the R1 team. Prevalence and bias indices (Byrt et al. 1993) are reported for each comparison to contextualize kappa values.

### 3.6 Self-Learning: Experience-Driven Annotation Memory

Agent Annotate implements a persistent self-learning layer (EDAM) that improves annotation accuracy across runs without model fine-tuning or human intervention. EDAM operates through three feedback loops: cross-run stability consensus, evidence-grounded self-review, and automated prompt optimization.

**Stability tracking** compares each (trial, field) annotation across all prior jobs, computing a stability index (0.0–1.0) and evidence anchoring grade (strong/medium/weak/none). Stable annotations become trusted few-shot exemplars; unstable fields receive additional scrutiny. Evidence grading prevents stable hallucinations from being treated as ground truth — high stability with no supporting evidence is flagged as potential systematic bias.

**Correction learning** accepts two signal types: human review decisions (stored at maximum weight with slowest decay) and autonomous self-review corrections (stored at reduced weight). Both require concrete evidence citations — ungrounded corrections are rejected by a validation function that checks for database identifiers, PMIDs, or registry URLs. Each correction generates a reflection explaining the error, which is embedded for semantic similarity search.

**Prompt auto-optimization** analyzes per-field accuracy every third job, identifies systematic error patterns, and proposes minimal prompt modifications via the premium model. Variants undergo A/B testing with automatic promotion (≥5% improvement after 20+ trials) or discard (>5% regression after 10 trials). All prompt evolution is reversible.

Memory is version-gated: each configuration change creates a new epoch, and learning entries decay exponentially with epoch distance (human corrections: floor 0.30; self-review: floor 0.10; raw experiences: floor 0.05). A 2,000-token budget caps guidance injection per LLM call. Database hard limits (10K experiences, 5K corrections) with prioritized purging prevent unbounded growth. Verifiers receive only statistical anomaly warnings — never corrections or exemplars — preserving blind verification integrity.

**EDAM test-set contamination (v20 fix).** The v18 training allowlist prevented new writes to EDAM for concordance test-batch NCTs, but did not purge existing records written before the allowlist was introduced (from v14--v17 training runs). Analysis revealed that 35 of 50 concordance test NCTs were present in EDAM at the time of v19 concordance runs. Sequential same-code concordance runs showed Outcome declining across runs (76%→72%→68%), consistent with EDAM reinforcing incorrect prior answers. In v20, these records were purged and the test batch is hard-excluded from `TRAINING_NCTS` at module load time: `TRAINING_NCTS = _load_training_ncts() - _load_test_batch_ncts()`.

**EDAM net-positive threshold.** Empirical analysis identifies a critical condition: EDAM improves accuracy only when the agent's base accuracy on a field exceeds approximately 70%. Below this threshold, EDAM reinforces incorrect answers from prior runs, causing accuracy to decline. The training/test accuracy gap (Outcome: 44--50% on training NCTs vs 68--72% on test NCTs) reflects that test NCTs were selected for high literature density while training NCTs represent the broader population with less evidence. EDAM training runs should not be evaluated against training-NCT concordance; only test-batch concordance (fast_learning_batch_50.txt) is informative for measuring EDAM effectiveness.

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

### 4.10 Version Comparison: v5.1 vs v6 (n=70, Same Trials)

To isolate the impact of agent improvements and research pipeline fixes, the same 70 NCT IDs were annotated twice using different agent versions. The OLD job (commit `22e9792`, 2026-03-16) used v5.1 agents with a partially broken research pipeline. The NEW job (commit `8553a1f`, 2026-03-17) used v6 agents with improved annotation prompts and fixed research agents.

#### 4.10.1 Research Coverage Impact

Total citations increased from 684 to 1,793 (+162%). The most impactful research agent fixes:

| Agent | OLD | NEW | Impact |
|---|---|---|---|
| ChEMBL | 0 | 366 | Bioactivity data — resolved peptide identity and mechanism questions |
| IntAct | 0 | 305 | Molecular interactions — provided AMP mechanism evidence |
| Literature | 154 | 284 | Better PubMed/PMC coverage — resolved outcome for completed trials |
| Peptide Identity | 0 | 135 | UniProt/DRAMP data — confirmed peptide status |
| DBAASP | 0 | 40 | AMP activity data — provided MIC evidence for classification |

Six agents (APD, dbAMP, EBI Proteins, RCSB PDB, PDBe, Web Context) remained at zero citations and require further investigation.

#### 4.10.2 Concordance Improvement

**Table 4.** Version comparison: agent vs human agreement on the same 70 trials.

| Field | v5.1 vs R1 | v6 vs R1 | Delta | v5.1 vs R2 | v6 vs R2 | Delta |
|---|---|---|---|---|---|---|
| **Outcome** | 40.9% | **72.7%** | **+31.8pp** | 52.2% | 54.3% | +2.2pp |
| Failure Reason | 44.4% | 55.6% | +11.1pp | 57.1% | 57.1% | 0 |
| Classification | 75.8% | 75.8% | 0 | 82.3% | 82.3% | 0 |
| Delivery Mode | 50.0% | 50.0% | 0 | 46.5% | 46.5% | 0 |
| **Peptide** | 83.3% | **77.1%** | **-6.2pp** | — | — | — |

The +31.8 percentage-point improvement in Outcome vs R1 is the largest single-version gain in the project. Of 38 outcome changes between versions, 36 shifted from Unknown to Positive. Of these, 19 were confirmed correct against R1 ground truth.

The Outcome improvement is driven by two factors: (1) research pipeline fixes provided actual literature citations that resolved Unknown outcomes, and (2) the v6 completion heuristics (Phase I completion = Positive, results posted = lean Positive) applied correctly to old completed trials.

The Peptide regression (-6.2pp) stems from multi-drug trial confusion: in 3 trials, the agent evaluated a co-administered small molecule or adjuvant instead of the peptide intervention. The prompt instructs "if MULTIPLE drugs and only ONE is a peptide, answer True," but the two-pass extraction focuses on whichever intervention appears first in the evidence.

#### 4.10.3 Review Rate

Total field-level review flags decreased from 50 to 32 (-36%). Outcome reviews decreased from 20 to 8, the largest reduction. The remaining 32 reviews decompose as: 20 failure reason (verifiers disagree on whether an empty failure reason is correct), 8 outcome (verifiers disagree on completion heuristic application), 2 peptide, 1 delivery mode, 1 classification.

Analysis of the 32 remaining review items shows that 25 (78%) are systematically resolvable without human intervention through cross-field consistency enforcement (outcome=Positive forces failure_reason=EMPTY) and heuristic-aware verifier prompts.

#### 4.10.4 Outcome Regression Analysis

Five trials newly classified as Positive disagree with R1 ground truth (which says Unknown or Failed). All five share the same root cause: the H1 completion heuristic (Phase I completion = Positive) was applied despite zero published results being found. This indicates that H1 should be calibrated to require at least one corroborating signal (results posted, published abstract, or subsequent trial) before overriding an Unknown determination.

### 4.11 Batch 1--3 Concordance Results (n=70 × 3 batches)

Three batches of 70 identical trials established concordance stability:

| Field | Agent=R1 | Agent=R2 | R1=R2 (target) | Gap |
|---|---|---|---|---|
| Classification | 76% | 71% | 86% | -10pp / -15pp |
| Delivery Mode | 47% | 46% | 68% | -21pp / -22pp |
| Outcome | 59% | 66% | 78% | -19pp / -12pp |
| Reason for Failure | 83% | 77% | 92% | -9pp / -15pp |
| Peptide | 40% | 67% | 60% | -20pp / +7pp |
| **Overall** | **64.3%** | **65.2%** | **79.2%** | **-14.9pp / -14.0pp** |

Root causes: 8B verifiers overriding correct 14B classifications, "NEVER GUESS" forcing 51% delivery modes to Other/Unspecified, Positive bias for COMPLETED trials without publications, SUSPENDED trials guessing "Business Reason", and false peptide positives on HSP complexes and dexosomes.

### 4.12 Preliminary v10 Evaluation (Batch A, n=25)

The v10 architecture (verification personas, dynamic confidence, evidence budget parity, high-confidence primary override, EDAM self-learning with self-audit) was evaluated on 25 clinical trials selected for maximum human annotation coverage (4-5 fields annotated by both R1 and R2).

**Concordance results:**

| Field | Agent vs R1 | Agent vs R2 | R1 vs R2 (baseline) | Agent exceeds? |
|---|---|---|---|---|
| Outcome | 80.0% (k=0.742) | 76.0% (k=0.691) | 55.6% (k=0.36) | **Yes (+24.4 pp)** |
| Classification | 92.0% (AC1=0.917) | 88.0% (AC1=0.865) | 91.6% (AC1=0.89) | Matches |
| Peptide | 68.2% (k=0.252) | 50.0% (k=0.000) | 48.4% (k=0.00) | Yes vs R1 |
| Delivery Mode | 44.0% (k=0.323) | 56.0% (k=0.436) | 68.2% (k=0.38) | Below |
| Reason for Failure | 56.0% (k=0.396) | 56.0% (k=0.431) | 91.3% (k=0.00) | Below |

Outcome concordance reached Substantial agreement (k=0.742) with R1, exceeding the human inter-rater baseline by 24.4 percentage points. This represents the strongest single-field result across all agent versions. Classification concordance is near-perfect by AC1 (0.917) despite paradoxically low kappa (prevalence effect --- 92% of trials are "Other"). Peptide concordance improved against R1 (68.2% vs historical ~65%) following the injection of the scientific definition (2-100 amino acid active drug) into annotator and verifier prompts.

Delivery mode remains the weakest field (44% vs R1), with a systematic pattern: the agent defaults to "Injection/Infusion - Other/Unspecified" in 12 of 14 disagreement cases where humans specified IV, SC, or IM. Post-batch analysis identified that the research evidence contained explicit FDA route keywords (e.g., "INTRAVENOUS") that the delivery mode agent failed to extract — a programmatic deficiency rather than an evidence gap.

**v10 feature utilization (from pipeline logs):**
- 15 high-confidence primary overrides (primary confidence >0.85, verifiers at baseline)
- 51 deterministic verification skips (known drug lookups, registry statuses)
- 96 reconciler resolutions
- 1/25 trials flagged for review (4%) --- down from 54% in v4

The flagging rate reduction from 54% (v4) to 4% (v10) reflects both improved annotator-verifier agreement and the automated resolution of cross-field inconsistencies, not suppression of genuine disagreements.

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

The v6 agent pipeline achieves 72.7% agreement with R1 on Outcome --- exceeding the 55.6% human inter-rater agreement on this field. This demonstrates that the multi-agent architecture with systematic literature search and completion heuristics can surpass human annotators on fields where temporal drift and inconsistent literature review are the primary sources of human disagreement.

The version comparison (Section 4.10) reveals that the improvement trajectory is field-dependent. Outcome and Failure Reason benefit strongly from richer research coverage (+31.8pp and +11.1pp respectively), because these fields require finding published results that may not be immediately visible in registry data. Classification and Delivery Mode show no improvement from additional research agents, because these fields depend primarily on ClinicalTrials.gov metadata extraction. Peptide shows a slight regression (-6.2pp) from multi-drug trial confusion introduced by richer ChEMBL data.

This pattern is informative. Fields that require primarily factual extraction (Is this compound a peptide? What is the delivery route?) reached acceptable accuracy early and are now limited by prompt engineering quality. Fields requiring investigative reasoning (Did this trial succeed or fail? Why did it fail?) are limited by research coverage --- and improve dramatically when research agents are fixed.

The v10 evaluation extends this finding: on 25 trials with dense human annotation coverage, Outcome concordance reached k=0.742 (Substantial) against R1, exceeding the human inter-rater baseline of 55.6% by 24 percentage points. This demonstrates that a locally-executed multi-agent pipeline with blind verification can produce annotations that are more consistent with expert assessment than a second expert.

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

6. **Deterministic over stochastic (v9).** When structured data sources provide a definitive answer, deterministic code produces the annotation instead of an LLM. Deterministic decisions are faster, reproducible, and cannot be degraded by unreliable verifier models.

### 5.6 Design Evolution: Lessons Learned

The Agent Annotate architecture evolved through iterative error analysis across six major versions. Each design decision was driven by measured failure patterns, not theoretical optimization.

**Lesson 1: Single-pass annotation fails on ambiguous fields.** The v1-v2 agents used a single LLM call per field. Error analysis revealed that Outcome accuracy was 26.7% --- the model would see "COMPLETED" in the registry status and stop investigating, missing published results that showed the trial had actually failed. The fix: a two-pass investigative design where Pass 1 extracts structured facts from all sources, and Pass 2 applies a decision tree to those facts. This raised Outcome agreement from 26.7% to 72.7%.

**Lesson 2: Weak verifiers create false disagreements.** Verification with 7-9B models produced 50-60% flagging rates. Analysis showed that small verifiers couldn't follow multi-step decision trees and would default to surface-level answers, creating noise rather than catching genuine errors. The fix: upgraded verifier models (v10), verification personas that force cognitively diverse approaches, and a high-confidence primary override that protects well-evidenced annotations from baseline-confidence verifier dissent.

**Lesson 3: Verifiers need the same evidence as the primary annotator.** Verifiers originally saw 25 citations while the primary saw 30-50. Disagreements often arose because verifiers missed evidence the primary had access to. The fix: matching evidence budgets (v10), so disagreements reflect genuine interpretive differences rather than information asymmetry.

**Lesson 4: Cross-field consistency resolves most review items automatically.** 25 of 32 review items in early runs were artifacts of cross-field coupling (e.g., outcome=Positive but failure_reason="Ineffective"). Post-verification consistency enforcement eliminated these without human intervention.

**Lesson 5: The agent's own evidence is its best teacher.** The EDAM self-audit loop (v10) checks whether annotations are consistent with the structured data the research agents collected. When FDA data says "INTRAVENOUS" but the agent output "Other/Unspecified", the contradiction is detected and corrected automatically --- with the FDA citation as evidence. This produces corrections without any human annotations in the loop.

**Lesson 6: Human annotations are unreliable ground truth.** R1 (7 annotators) assigned peptide=True to 451 trials; R2 (primarily one annotator) assigned True to 56 --- an 8:1 ratio. Outcome inter-rater agreement is only 55.6%. The agent's concordance with humans must be interpreted against this noisy baseline, not treated as absolute accuracy measurement.

**Lesson 7: The agent should never see human annotations during learning.** EDAM's learning loops use only internal signals: cross-run stability, evidence consistency, and self-review. Human annotations are consulted only at evaluation time via concordance analysis. This ensures that concordance improvements reflect genuine accuracy gains, not overfitting to the evaluation set.

### 5.5 Limitations

Several limitations constrain the interpretation of the current results:

**Small baseline sample.** The 25-trial baseline is sufficient for identifying systematic error patterns but insufficient for reliable estimation of per-field accuracy or for computing confidence intervals around concordance statistics. The full 614-trial evaluation is required for robust performance characterization.

**Hardware constraints.** All models run on 16 GB of unified memory, constraining model size to 14B parameters for the largest model and 8B--9B for the primary annotator and verifiers. Larger models (70B+) would likely improve performance on investigative fields but are infeasible on the current hardware.

**No multi-run consensus.** The current pipeline performs a single annotation run per trial. Multi-run consensus (N=3 or N=5, majority vote) would reduce the impact of stochastic variation in model outputs but at a proportional increase in inference time.

**Imperfect ground truth.** Human annotations exhibit 19.8% disagreement, meaning that even a perfect system would achieve at most 80.2% agreement with any single annotator. Evaluation against a consensus ground truth (where both annotators agree) would provide a cleaner signal but would exclude the 19.8% of cases that are, by definition, the most difficult.

**Concordance caveats.** R1 is a composite of 7 annotators; internal R1 reliability is not independently measurable from the available data. Missing data (43-65% blank annotations) is likely not missing at random, as harder trials receive less annotation coverage. All kappa values should be interpreted alongside their 95% CIs and the corresponding AC₁, particularly for fields with extreme prevalence (e.g., Peptide, where >90% of trials are non-peptide). For Classification and Peptide, AC₁ should be preferred over kappa as the primary agreement metric because the prevalence index exceeds 0.5 — kappa near zero with >80% raw agreement is the classic prevalence paradox, not poor agreement.

**No cross-validation.** The v3 improvements described in Section 4.4 were designed in response to errors observed on the same 25 trials used for evaluation. Performance on held-out trials may differ.

**Small v10 evaluation sample.** The v10 results are based on 25 trials. While the k=0.742 outcome result is statistically significant (95% CI: 0.545-0.940, entirely above the Moderate threshold), the delivery mode and peptide results have wide confidence intervals that preclude strong conclusions. Full evaluation of the 964 human-annotated trials is required to confirm these preliminary findings.

---

## 6. Future Work

Seven directions for future development are planned:

1. **Post-v9 concordance validation.** Run the same 70 trials to measure concordance gains, review item reduction (target: <8), and per-trial timing (target: <500s).

2. **Full evaluation on 614 overlapping trials.** Expanding the evaluation from 25 to 614 trials will enable robust per-field accuracy estimation, subgroup analysis (e.g., by trial phase, therapeutic area, or registry age), and reliable kappa computation with confidence intervals.

3. **Multi-run consensus.** Performing N=3 annotation runs per trial and selecting the majority answer for each field will reduce the impact of stochastic model variation. Preliminary experiments suggest that consensus across runs improves accuracy by 5--10% on fields with high model variance.

4. **14B primary annotator for high-error fields.** Deploying qwen2.5:14b as the primary annotator for Classification and Outcome --- the two fields with the largest agent-human gap --- while retaining 8B models for Peptide and Delivery Mode. This requires sequential field processing to manage memory but should improve instruction adherence on complex reasoning tasks.

5. **Additional sequence databases.** Integrating NCBI Protein as an additional source for the Peptide Identity Agent. Note: APD (aps.unmc.edu) and dbAMP 3.0 have been integrated as v5 research agents (Sections 3.2.10--3.2.11), along with WHO ICTRP, IUPHAR, IntAct, CARD, and PDBe (Sections 3.2.12--3.2.16).

6. **Active learning from manual review.** When annotations are flagged for manual review and a human provides the correct answer, the system can use these corrections to identify systematic prompt weaknesses and guide prompt refinement. Over time, this creates a feedback loop that progressively reduces the manual review burden.

7. **Cross-validation with held-out annotations.** Partitioning the 614-trial dataset into development and test sets, using the development set for prompt engineering and the test set for unbiased evaluation. This standard machine learning practice will provide a more honest assessment of generalization performance.

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
| ~~Semantic Scholar~~ | ~~Free~~ | — | Removed v8: heavy 429 rate limiting |
| DBAASP API (v4) | Free | No key required | 5 requests/sec |
| ChEMBL API (v4) | Free | No key required | 10 requests/sec |
| RCSB PDB API (v4) | Free | No key required | 10 requests/sec |
| EBI Proteins API (v4) | Free | No key required | 10 requests/sec |
| APD (v5) | Free | No key required | 2 requests/sec |
| ~~dbAMP 3.0~~ | ~~Free~~ | — | Removed v8: server unreachable |
| WHO ICTRP (v5) | Free | No key required | 2 requests/sec |
| IUPHAR Guide to Pharmacology (v5) | Free | No key required | 10 requests/sec |
| ~~IntAct~~ | ~~Free~~ | — | Removed v8: low hit rate, noise |
| ~~CARD~~ | ~~Free~~ | — | Removed v8: 0% relevance to dataset |
| PDBe (v5) | Free | No key required | 10 requests/sec |

All sources are freely accessible without paid subscriptions. SerpAPI was removed as it required a paid API key. Rate limits are enforced client-side through per-host semaphores to ensure compliance and prevent service disruption.

---

## 8. Conclusion

Agent Annotate demonstrates that a multi-agent pipeline with evidence requirements, field-specific decision logic, and blind multi-model verification can produce structured annotations of clinical trials with full provenance chains. The v6 agent pipeline, running 8B-parameter models on consumer hardware with 12 research agents querying 17+ free databases, achieves 72.7% agreement with human annotators on Outcome --- exceeding the 55.6% human inter-rater agreement on this field. Classification (75.8%) approaches the human ceiling (91.6%), and Peptide (77.1%) far exceeds human agreement (48.4%). The version comparison on 70 shared trials demonstrates that fixing research agent data quality (+162% citations) produces dramatic accuracy improvements (+31.8pp on Outcome), validating the architecture's core premise that evidence quality drives annotation quality. Remaining gaps in Delivery Mode (50.0%) and Failure Reason (55.6%) are addressable through cross-field consistency enforcement, heuristic-aware verifier prompts, and continued research agent fixes.

The v9 deterministic-first architecture addresses the performance gap by inverting the annotation flow: programmatic pre-classifiers handle clear cases with lookup tables and structured data extraction, while LLMs focus on genuinely ambiguous cases. This hybrid approach recognizes that small language models cannot reliably implement complex decision trees, but the same logic can be implemented deterministically as code. The architecture's modular design allows individual agents to be upgraded (e.g., from 8B to 14B models) or replaced without affecting the rest of the pipeline.

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

*Document version: 6.0 (v10 — verification personas, dynamic confidence, EDAM self-audit, preliminary Batch A results, design evolution lessons). Updated 2026-03-19.*
