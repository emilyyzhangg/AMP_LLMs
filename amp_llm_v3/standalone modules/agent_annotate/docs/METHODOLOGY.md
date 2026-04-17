# Agent Annotate -- Technical Methodology

## 1. System Overview

Agent Annotate is a three-phase pipeline for annotating clinical trials involving antimicrobial peptides (AMPs) with publication-grade accuracy. All inference runs locally via Ollama-hosted language models. The pipeline processes trial records from ClinicalTrials.gov and produces structured annotations across five fields.

The three phases execute sequentially per trial:

1. **Phase 1 -- Research.** Twelve parallel agents gather evidence from 17+ free external databases (registries, literature, protein databases, peptide activity databases, structure databases, pharmacology databases, international trial registries).
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

An antimicrobial peptide (AMP), also called a host defense peptide, is a single-chain peptide (2--50 amino acids) that contributes to pathogen defense through antimicrobial mechanisms --- killing, inhibiting the growth of, disrupting, or inducing immune responses against pathogens through the peptide's own biochemical action. Both bactericidal (killing) and bacteriostatic (growth inhibition) mechanisms qualify. The pipeline classifies AMPs by four modes of action. A peptide must fit at least one mode to be classified as an AMP.

**Critically, the AMP classification is independent of the Peptide field.** A trial can have Peptide=True (the drug is a peptide) but Classification=Other (the peptide is not antimicrobial). For example, enfuvirtide is a peptide (Peptide=True) but is a viral entry inhibitor, not an AMP (Classification=Other). Semaglutide is a peptide (Peptide=True) but is a metabolic hormone, not an AMP (Classification=Other).

### 2.2 Four Modes of Action (v12)

**Mode A -- Direct Antimicrobial**
Peptides that kill, inhibit the growth of, or disrupt pathogens --- includes both bactericidal and bacteriostatic mechanisms: membrane disruption, pore formation, intracellular targeting, growth inhibition, ion channel disruption. Examples: colistin, polymyxin B, melittin, daptomycin, nisin, gramicidin.

**Mode B -- Immunostimulatory / Host Defense**
Peptides that directly recruit innate immune cells to kill pathogens at infection sites. Examples: LL-37, defensins, cathelicidins. The peptide must specifically recruit innate defense against pathogens --- general immunomodulation or adaptive immune activation does not qualify.

**Mode C -- Anti-Biofilm**
Peptides that directly disrupt microbial biofilms through biochemical interaction. Examples: LL-37, DJK-5, IDR-1018.

**Mode D -- Pathogen-Targeting Immunogens (re-added v12)**
Peptide vaccines and immunogens designed to induce immune responses SPECIFICALLY against pathogens (bacteria, viruses, fungi). Examples: HIV gp120/gp41 peptide vaccines, malaria peptide vaccines, StreptInCor (streptococcal). The peptide must target a specific pathogen --- cancer neoantigen vaccines do NOT qualify (they target tumor cells, not pathogens). Mode D was removed in v2 based on 70-trial concordance but re-added in v12 because the AMP definition should encompass all mechanisms of pathogen defense, including adaptive immune induction against specific pathogens.

### 2.3 Key Distinctions

1. **Antimicrobial mechanism required.** The peptide must kill, inhibit the growth of, or disrupt pathogens through its own biochemical action --- or recruit immune cells to fight pathogens --- or target a specific pathogen as a vaccine/immunogen. Both bactericidal and bacteriostatic mechanisms qualify. General immunomodulation without pathogen specificity does not qualify.

2. **Treating infection ≠ AMP.** A peptide that treats an infectious disease through a non-antimicrobial mechanism (e.g., enfuvirtide blocks HIV viral fusion but does not kill the virus) is classified as "Other." Being tested in an infection context does not make a peptide an AMP.

3. **Promoting defense vs suppressing immunity.** An immunosuppressive peptide is "Other" regardless of its peptide nature. An immunostimulatory peptide is only an AMP if it specifically recruits innate defense against pathogens (Mode B), not if it merely promotes general immune activation.

4. **Pathogen-targeting vaccine peptides ARE AMPs (Mode D).** Peptides designed to induce immune responses against specific pathogens (HIV vaccines, malaria vaccines, etc.) are AMP. However, cancer neoantigen vaccines are NOT AMPs because they target tumor cells, not pathogens.

5. **Peptide ≠ AMP.** Many peptides are not antimicrobial: neuropeptides (VIP/aviptadil, peptide T), metabolic hormones (GLP-1 agonists, insulin), bone growth regulators (vosoritide/CNP, calcitonin), viral entry inhibitors (enfuvirtide), and radiolabeled tracers. All are classified as "Other" despite being peptides (Peptide=True).

### 2.4 Relationship Between Peptide and Classification Fields

| Peptide | Classification | Example |
|---|---|---|
| True | AMP | Colistin for MDR bacterial infection, LL-37 for diabetic wound healing |
| True | Other | Enfuvirtide (viral entry inhibitor), semaglutide (GLP-1), calcitonin (bone), peptide T (neuropeptide), HIV peptide vaccine |
| False | Other | Amoxicillin (small molecule), Peptamen (nutritional formula), pembrolizumab (antibody) |


## 3. Annotation Fields

Each trial receives annotations for five fields. The allowed values for each field are fixed.

### 3.1 Classification

Categorizes the trial's relationship to AMPs.

| Value | Meaning |
|---|---|
| AMP | Trial involves an antimicrobial peptide (any mode of action: direct antimicrobial, immunostimulatory host defense, anti-biofilm, or pathogen-targeting immunogen) |
| Other | Trial does not involve an AMP (Other = peptide but not AMP, or not a peptide) |

### 3.2 Delivery Mode

The route of administration. 4 valid values:

Injection/Infusion, Oral, Topical, Other.

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

Boolean field (True/False) indicating whether the intervention is a peptide therapeutic.

**Definition (v12):** A peptide therapeutic is a SINGLE-CHAIN molecule consisting of 2--50 amino acid residues that serves as the ACTIVE therapeutic drug in the clinical trial. The peptide must be the primary pharmacological agent --- not a carrier, adjuvant, nutritional component, or targeting vector.

**Included as peptide (True):**
- Antimicrobial peptides: colistin, daptomycin, nisin, polymyxin B, LL-37 (37 aa), defensins
- Hormone analogues: semaglutide (31 aa, GLP-1), octreotide (8 aa), leuprolide (10 aa)
- Cyclic peptides and glycopeptides: vancomycin, gramicidin, bacitracin
- Peptide vaccines where the peptide IS the active immunogen (e.g., StreptInCor, HIV gp120 peptide vaccines)
- Neuropeptides used as drugs: aviptadil (VIP, 28 aa), substance P antagonists, peptide T
- Viral entry inhibitors that are peptides: enfuvirtide (T-20, 36 amino acids)
- Bone/growth peptides: teriparatide (34 aa), calcitonin (32 aa)

**Excluded as peptide (False):**
- Proteins >50 amino acids: insulin (51 aa, also multi-chain A+B), interferons, erythropoietin, vosoritide (CNP analogue, 39 aa but check)
- Multi-chain complexes forming tertiary/quaternary structure (complex proteins, not peptides)
- Monoclonal antibodies (multi-chain, ~150 kDa): pembrolizumab, trastuzumab
- Small molecule drugs: amoxicillin, metformin, ciprofloxacin
- Nutritional formulas containing hydrolyzed proteins: "Peptide 1.5", Peptamen, Kate Farms
- Heat shock protein-peptide complexes: HSPPC-96/Oncophage (the HSP is the drug)
- Exosome/dexosome vehicles loaded with peptides (the vehicle is the drug)
- Gene therapies, cell therapies, medical devices
- Single amino acids (e.g., L-glutamine, L-arginine supplements)

**Cross-validation with Sequence field (v12):** When the Sequence agent extracts an amino acid sequence, the consistency engine cross-validates: sequence in 2--50 AA range forces peptide=True; sequence >50 AA or multi-chain forces peptide=False.

**Sequence agent DRVYIHP fix and expanded known sequences (v25):** Short drug names (<=4 characters) now require exact match in `_KNOWN_SEQUENCES`, while longer names use word-boundary regex. This prevents false positives where "angiotensin" in an intervention name (e.g., "Angiotensin-Converting Enzyme Inhibitor") would match the DRVYIHP angiotensin II sequence. The `_KNOWN_SEQUENCES` table was expanded from 12 to 21 drugs with 9 new verified sequences including gv1001 (16aa), abaloparatide (34aa), vosoritide/bmn111 (39aa), satoreotide (8aa), and others.

**Key rule:** The question is whether ANY active intervention drug is a peptide --- not whether the formulation contains peptides. Brand names containing "peptide" do NOT make the product a peptide drug.


## 4. Phase 1 -- Research Agents

Twelve research agents query different external sources. Every source carries a fixed quality weight reflecting its reliability for AMP clinical trial annotation. The v4 pipeline added four specialized agents (Sections 4.5--4.8) for peptide activity, bioactivity, structural, and protein sequence data. The v5 expansion added seven more agents (Sections 4.9--4.15) covering additional peptide databases, international trial registries, pharmacology, molecular interactions, antibiotic resistance, and structure quality. SerpAPI was removed (paid service); all 12 agents now use free APIs exclusively.

### 4.0 Two-Step Research Architecture

Phase 1 executes in two steps rather than running all 12 agents simultaneously. This two-step design is critical because peptide/drug database agents (DBAASP, ChEMBL, IUPHAR, PDBe, etc.) need to know the intervention name to query their databases. Without a name to search for, these agents return zero citations.

**Step 1 -- Protocol-first metadata extraction.** The Clinical Protocol Agent (Section 4.1) runs first. It fetches the trial record from ClinicalTrials.gov and extracts intervention names (drug and peptide names) from the structured `protocol_section.armsInterventionsModule.interventions` field. It also queries OpenFDA for supplementary drug metadata. The extracted intervention names are stored as shared metadata for use in Step 2.

**Step 2 -- Parallel database queries with intervention metadata.** The remaining 14 agents run in parallel, each receiving the intervention names extracted in Step 1. This enables database agents to perform targeted lookups: DBAASP searches by peptide name and returns MIC data (e.g., 5 hits for Nisin with minimum inhibitory concentration values), ChEMBL searches by compound name for bioactivity and clinical phase data, CARD searches by antibiotic name for resistance mechanisms (e.g., 5 hits for Colistin resistance data), IUPHAR searches by ligand name for pharmacological profiles, IntAct searches by protein name for molecular interactions, and PDBe searches by molecule name for structure quality metrics.

**Data flow:**

```
Step 1:  ClinicalTrials.gov API
              |
              v
         Extract intervention names from
         protocol_section.armsInterventionsModule.interventions
              |
              v
         Intervention metadata (e.g., "Nisin", "Colistin")
              |
Step 2:       v
         [Literature      ] [Peptide Identity] [Web Context    ]
         [DBAASP          ] [ChEMBL          ] [RCSB PDB       ]
         [EBI Proteins    ] [APD             ] [dbAMP          ]
         [WHO ICTRP       ] [IUPHAR          ] [IntAct         ]
         [CARD            ] [PDBe            ]
         (all 14 agents run in parallel with intervention names)
```

Previously, all agents ran in parallel with no shared metadata, which meant database agents had only the NCT ID and trial title to work with -- insufficient for querying peptide/drug databases that require compound names as search keys.

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

### 5.1 Two-Pass Investigative Design (All Agents)

All five annotation agents use a two-pass investigative architecture. This universal design was adopted in v2 after 70-trial concordance analysis showed that single-pass prompts were insufficient for 8B models, which shortcut on surface-level keywords rather than following multi-step decision trees.

- **Pass 1: Structured Fact Extraction** -- The first LLM call extracts factual claims from the evidence package without making a classification decision. Each agent's Pass 1 prompt is tailored to its field.
- **Pass 2: Decision with Calibrated Rules** -- The second LLM call receives the Pass 1 output along with a decision tree that encodes field-specific logic.

**Design principle**: No lookup tables or hardcoded drug dictionaries. Agents must reason independently from evidence. This ensures generalization to novel peptides and trial designs.

### 5.2 Classification Agent (v5)

Uses a larger model (qwen2.5:14b on Mac Mini, kimi-k2-thinking on server) because 8B models ignore the multi-step decision tree.

**Pass 1:** Extracts five antimicrobial evidence dimensions:
- Peptide identity and molecular class
- Database matches (DRAMP, APD3, UniProt, ChEMBL, RCSB PDB, EBI Proteins)
- Mechanism of action (direct antimicrobial vs other)
- Therapeutic target (infection vs non-infection)
- Immune direction (promote defense vs suppress vs neutral)

**Pass 2:** Applies a two-step decision tree (binary AMP/Other classification):
1. Is the intervention a peptide? If not → Other.
2. Does this peptide have a DIRECT antimicrobial mechanism — physically killing/lysing/disrupting pathogens or directly recruiting innate immune cells to kill pathogens? If yes → AMP. If not → Other.

**v5 changes (from 70-trial concordance analysis):**
- **AMP definition narrowed to three modes (v5)**: Mode D was removed. *Note: Mode D was re-added in v12 — pathogen-targeting vaccine peptides are now classified as AMP. See Section 2.2.*
- **Explicit antiretroviral exclusions**: Enfuvirtide/T-20 (viral entry inhibitor, NOT antimicrobial), Peptide T/DAPTA (CCR5 receptor blocker), HIV peptide vaccines (antibody induction). These were the dominant over-classification pattern (30 of 36 classification disagreements).
- **Mechanism-based decisive rule**: If the mechanism is viral entry inhibition, receptor blocking, vaccine/antibody induction, vasodilation, or metabolic regulation → Other, regardless of infectious disease context.
- **Default to Other**: When in doubt, false AMP classification is worse than missing a true AMP.

### 5.3 Delivery Mode Agent (v5)

**Pass 1:** Extracts route evidence from all sources with explicit priority ordering:
1. FDA/drug label route (highest priority — "for subcutaneous use")
2. Published literature route descriptions
3. ClinicalTrials.gov protocol text (intervention description, arm groups)
4. Database formulation data (ChEMBL, IUPHAR)
5. Drug formulation keywords (tablet, capsule, solution, etc.)

The prompt forces the model to search ALL sources before concluding, explicitly noting the most specific route found.

**Pass 2:** Classifies using source hierarchy — FDA label overrides generic protocol text. Routes are mapped to four simplified categories: Injection/Infusion (covers IV, IM, SC, and all other injection/infusion routes), Oral, Topical, Other.

**v5 changes**: Upgraded from single-pass to two-pass. The single-pass agent defaulted to "Other" in 52% of injection cases because it only checked protocol text. The two-pass design forces active search across FDA labels, literature, and databases before classifying.

Never-guess rule preserved: if no source specifies a route, the answer is Other.

**v25:** Fixed multi-route deduplication. When multiple intervention drugs map to the same simplified category (e.g., IV + Subcutaneous both map to "Injection/Infusion"), the result is now deduplicated to a single value. Previously, "Injection/Infusion, Injection/Infusion" appeared in output for 26% of delivery mode disagreements. After mapping to four categories, `_parse_value()` now deduplicates before joining.

### 5.4 Outcome Agent (v4)

**Pass 1:** Extracts seven evidence elements:
- Registry status (COMPLETED, TERMINATED, RECRUITING, etc.)
- Trial phase
- Published results summary (with quotes)
- Result valence (positive/negative/mixed/not available)
- Results posted flag
- Completion date
- Why stopped

**Pass 2:** Applies a calibrated decision tree with **completion heuristics** (added in v2 after concordance showed 15+ "Unknown" defaults for old completed trials that humans correctly marked "Positive"):

1. Recruiting/Active not recruiting → report current status.
2. Withdrawn → Withdrawn.
3. Published positive results → Positive. Phase I completion with acceptable safety → Positive.
4. Published negative results → Failed - completed trial. Requires cited evidence of failure.
5. Terminated → Terminated.
6. For COMPLETED trials without published results, apply completion heuristics:
   - H1: Phase I completion → Positive (safety trial completion IS success).
   - H2: Results posted on ClinicalTrials.gov → lean Positive.
   - H3: Trial completed >10 years ago, no negative evidence → lean Positive.
   - H4: Only after exhausting H1-H3 → Unknown.

Critical rule: "Completed" registry status alone does NOT indicate failure. "Failed - completed trial" requires affirmative evidence of a negative result.

**v25:** Introduces an evidence priority ladder for outcome determination: publications > CT.gov posted results > CT.gov registry status > trial phase. A post-LLM `_publication_priority_override()` function checks whether published results exist when the LLM returns Unknown, Active, or Terminated, and reclassifies accordingly. This addresses the dominant error pattern where the LLM defaults to Unknown for trials with published results it failed to incorporate.

**v42 Atomic Outcome Pipeline (shadow mode).** After v39→v41b oscillation confirmed that a single-LLM-on-full-dossier architecture cannot be stabilized by prompt tuning (each fix inverted the FP/FN error class), v42 rebuilds outcome as a four-tier atomic pipeline stored under a parallel field `outcome_atomic` during shadow-mode validation:

- **Tier 0** — deterministic pre-label (RECRUITING/WITHDRAWN/SUSPENDED, or COMPLETED+hasResults+p<0.05).
- **Tier 1a** — structural trial-specificity classifier: three Y/N questions (NCT-in-body, PMID-in-CT.gov-references, title-design+drug) with no keyword list.
- **Tier 1b** — per-publication LLM call (gemma3:12b) answering five atomic Y/N/UNCLEAR questions grounded in a single pub's text plus one forced evidence_quote.
- **Tier 2** — deterministic registry signal extractor (status, completion date, stale flag, primary-endpoint p-values, ChEMBL max_phase, CT.gov reference PMIDs).
- **Tier 3** — deterministic aggregator mapping atomic answers to a label via ordered rules R1–R8 (see `agents/annotation/outcome_aggregator.py`). No LLM makes the final outcome decision; R3 uses most-recent-pub verdict when POSITIVE and FAILED coexist.

Every verdict carries a named rule, a rule description, and the atomic inputs that fired it. Design details in `docs/ATOMIC_EVIDENCE_DECOMPOSITION.md`. Enabled via `config.orchestrator.outcome_atomic_shadow` (default OFF).

### 5.5 Failure Reason Agent (v5)

**Deterministic pre-check gate (v2):** The orchestrator runs the Failure Reason Agent AFTER the Outcome Agent and passes the outcome result in metadata. Before any LLM call, the agent checks:

- If outcome is Positive, Recruiting, Active not recruiting, or Unknown → return empty immediately. No LLM call. This deterministic gate eliminated the dominant concordance error: the 8B model hallucinated "Ineffective for purpose" for 42 out of 62 non-failed trials.

**Only Terminated and Failed outcomes proceed** to the two-pass LLM investigation:

**Pass 1:** Investigates all evidence for failure signals — adverse event reports, efficacy data, sponsor announcements, regulatory actions, COVID disruptions, enrollment data.

**Pass 2:** Classifies the failure mode, but only if Pass 1 identified actual failure signals. COMPLETED trials without published negative results default to empty (no failure).

### 5.6 Peptide Agent (v5)

**Pass 1:** Extracts molecular facts:
- Intervention name
- Molecular class (peptide chain / antibody / small molecule / nutritional product / large multi-subunit protein)
- Database confirmation (UniProt, DRAMP, DBAASP, ChEMBL entries)
- Product description (drug vs nutritional formula vs dietary supplement)
- Investigational drug role (investigational drug / food ingredient / targeting vector / brand name only)

**Pass 2:** Applies a three-step decision tree:
1. Is the molecular class a peptide? (Antibodies, small molecules, nutritional products → False)
2. Is it the investigational drug? (Food ingredients, brand name artifacts → False)
3. Database/literature confirmation (DRAMP/UniProt/ChEMBL entry → True; no hits but clearly peptide → True)

**v15:** If peptide=False, all other fields (Classification, Delivery Mode, Outcome, Reason for Failure) are set to N/A and annotation is skipped. ALL peptide=False cascades set downstream fields to N/A unconditionally --- there is no longer a distinction between deterministic and LLM-based False results for cascade purposes.

**v5 changes**: Upgraded from single-pass to two-pass. The single-pass agent over-identified peptides (Agent=True for non-peptide interventions) and under-identified (Agent=False for real peptides) because 8B models shortcut on whether "peptide" appeared in the trial text. The two-pass design forces molecular class determination before the True/False decision.

**v25:** The `_KNOWN_PEPTIDE_DRUGS` deterministic lookup table was expanded with 15 additional peptide drugs identified through error analysis of concordance jobs, including peptide vaccines (pvx-410, polypepi1018, gv1001) and novel therapeutics (satoreotide, pemziviptadil, emi-137, neobomb1). The expanded list now covers peptide vaccines and edge-case therapeutics that the LLM consistently misclassified as non-peptides.


## 6. Phase 3 -- Verification Pipeline

### 6.1 Blind Peer Review

Three verifier models independently review each annotation. The verifiers never see the primary annotation -- they receive only the research dossier and the annotation field definition, then produce their own annotation.

| Verifier | Model |
|---|---|
| Verifier 1 | gemma3:12b |
| Verifier 2 | qwen3:8b |
| Verifier 3 | phi4-mini:3.8b |

**v4 verifier prompt improvements**: The v4 verifier prompts now receive the same level of field-specific detail as the primary annotation agents, including negative examples, decision trees, and extraction hierarchies. In v3, verifiers received condensed instructions, creating an asymmetry where verifiers lacked the context to make accurate independent judgments. The v4 parity ensures that verifier disagreements reflect genuine evidence ambiguity rather than instruction gaps.

#### 6.1.1 Verification Personas (v10)

Each verifier receives a different cognitive persona prepended to its system prompt, ensuring diverse reasoning even with identical evidence:

| Verifier | Persona | Approach |
|---|---|---|
| Verifier 1 | Conservative | Defaults to safest answer when evidence is ambiguous. Absence of evidence ≠ evidence of a result. |
| Verifier 2 | Evidence-strict | Only answers based on directly citable facts. Acknowledges gaps explicitly. |
| Verifier 3 | Adversarial | Actively challenges the obvious interpretation. Looks for contradicting evidence. |

#### 6.1.2 Dynamic Verifier Confidence (v10)

Verifier confidence is now parsed from the model's self-assessment rather than hardcoded. Each verifier response includes a `Confidence: [High/Medium/Low]` field, mapped to numeric scores:

| Self-Assessment | Confidence Score |
|---|---|
| High | 0.9 |
| Medium | 0.7 |
| Low | 0.4 |

This enables the high-confidence primary override (Section 6.4) to make smarter decisions — a verifier that says "Low confidence" will not block a high-confidence primary annotation.

#### 6.1.3 Evidence Budget Parity (v10)

Verifiers now receive the same citation budget as primary annotators (30 on Mac Mini, 50 on server), up from a hardcoded cap of 25. This eliminates false disagreements caused by verifiers missing evidence the primary annotator had access to.

#### 6.1.4 Server Verifier Overrides (v10)

On server hardware (240+ GB RAM), verifiers are upgraded to stronger models:

| Slot | Mac Mini | Server |
|---|---|---|
| Verifier 1 (Conservative) | gemma3:12b | gemma2:27b |
| Verifier 2 (Evidence-strict) | qwen3:8b | qwen2.5:32b |
| Verifier 3 (Adversarial) | phi4-mini:3.8b | phi4:14b |

Server verifiers are configurable via `server_verifiers` in the YAML config and auto-pulled from Ollama if not available locally.

### 6.2 Consensus

The consensus threshold is 1.0 (unanimous agreement required). If all three verifiers agree with each other, that value is accepted. If any verifier disagrees, the annotation is escalated to reconciliation.

### 6.3 Reconciliation

Disputed annotations are sent to a reconciler model (qwen2.5:14b) that receives:
- The primary annotation
- All three verifier annotations
- The full research dossier

The reconciler produces a final annotation with justification.

### 6.4 High-Confidence Primary Override (v10)

When the primary annotator has confidence > 0.85 and all dissenting verifiers are at baseline confidence (≤ 0.7), the primary answer is accepted without reconciliation. This prevents low-confidence verifier noise from overriding a high-confidence primary annotation, reducing unnecessary reconciliation calls.

### 6.5 Manual Review Escalation

Cases that the reconciler cannot resolve (e.g., contradictory evidence, ambiguous trial designs) are flagged for manual human review.

### 6.6 Value Normalization in Verification

#### 6.6.1 Problem

Verifier models (8B--9B parameters) frequently output trial status keywords or free-text explanations instead of valid field values. For the `reason_for_failure` field, verifiers would return values such as "COMPLETED", "Unknown", "N/A", "ACTIVE_NOT_RECRUITING", or verbose explanations like "The trial was completed successfully so there is no failure reason" instead of the expected empty string. These invalid values caused false disagreements during consensus checking, inflating the number of trials flagged for manual review and reconciliation.

#### 6.6.2 Parsing Rules

Value normalization applies two parsing strategies in order:

1. **Prefix matching for verbose explanations.** If the verifier output starts with a valid value (e.g., "Ineffective for purpose because the trial did not meet its primary endpoint"), the valid prefix is extracted. This catches cases where verifiers append explanations to their answers.

2. **Exact match for status keywords.** If the output exactly matches a known status keyword or status-like value, it is mapped to the canonical field value. For `reason_for_failure`, all status-like values map to empty string (no failure reason).

#### 6.6.3 Canonical Mapping for reason_for_failure

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

#### 6.6.4 Field-Aware Consensus Normalization

Normalization rules differ by field because valid values and common verifier errors differ:

- **reason_for_failure**: Status keywords and "N/A"/"None"/"Unknown" all normalize to empty string. This is the field most affected by verifier parsing failures.
- **outcome**: Status keywords normalize to their canonical outcome values (e.g., "COMPLETED" is not a valid outcome value and is flagged).
- **classification**: "AMP" is a valid value (binary AMP/Other classification).
- **delivery_mode**: Route abbreviations normalize to the four canonical categories (e.g., "Intravenous", "IV", "IM", "SC" all normalize to "Injection/Infusion"; "Oral tablet" normalizes to "Oral"; etc.).
- **peptide**: Boolean normalization ("true"/"yes" to "True", "false"/"no" to "False").

#### 6.6.5 Retroactive Fix Capability

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

### 8.2 Human Annotator Structure

The human annotation dataset consists of two independent replication passes over the same 1,846 clinical trials:

- **R1 ("Trials Replicate 1")**: Annotated by a team of 7 annotators — Mercan (rows 1-309), Maya (310-617), Anat (617-822), Ali (823-926, 1417-1544), Emre (926-1186), Iris (1187-1417), Berke (1545-1846). Each annotator was assigned a contiguous block of trials. The R1 sheet is therefore a composite of 7 annotators with potentially different working definitions and annotation thoroughness.

- **R2 ("Trials Replicate 2")**: Annotated by multiple independent annotators including Emily (rows 1-461, 481-922, 941-1383), Anat (462-480), Ali (923-941), and Iris (1384-1405).

This structure means that R1 vs R2 concordance measures agreement between two multi-annotator composites — not between two single equivalent independent raters. The 8:1 Peptide ratio (R1=451 True vs R2=56 True) likely reflects inter-annotator variability within R1, not a single coherent disagreement between two replication passes.

Annotator row assignments are derived from the "Tentative workload" sheet in the original source Excel file (now converted to CSV format as `human_ground_truth_train_df.csv`), enabling per-annotator concordance analysis.

### 8.3 Blank Handling (v2 Protocol)

The v2 concordance protocol excludes blank or empty human annotations from concordance calculations. The rationale: a blank annotation means the annotator did not annotate the field, not that the annotator chose an empty value.

One exception: for the reason_for_failure field, empty IS a valid annotation (meaning "no failure"). A reason_for_failure value is only treated as blank (excluded) when the corresponding outcome field was also blank -- indicating the annotator skipped both fields.

**Additional concordance comparison rules:**

- **"N/A" treated as blank for skip purposes.** When a field value is "N/A" (e.g., from a peptide=False cascade), it is treated as blank/skip --- the pair is excluded from concordance, not counted as a disagreement.
- **Reason for Failure: blank reason + failure outcome = "Unknown" (not skip).** When an annotator has a failure-class outcome (Terminated, Failed) but left the reason_for_failure blank, the blank is treated as "Unknown" rather than skipped. This prevents inflating agreement by excluding cases where the annotator failed to provide a reason.
- **Peptide=False exclusion.** When either side (agent or human) has peptide=False, non-peptide fields (Classification, Delivery Mode, Outcome, Reason for Failure) are skipped in concordance. Non-peptide trials are out of scope for AMP annotation, so disagreements on downstream fields are meaningless when the trial is not a peptide.

### 8.4 Inter-Annotator Reliability

Cohen's kappa is computed for each field to measure inter-annotator agreement beyond chance. This applies to both agent-vs-human and human-vs-human comparisons.

### 8.5 Statistical Methods

**Cohen's kappa** (Cohen 1960) with 95% analytical confidence intervals (Fleiss, Cohen & Everitt 1969) is the primary agreement metric. However, kappa is known to be paradoxically low when category prevalence is extreme (the "prevalence paradox" — Feinstein & Cicchetti 1990). To address this:

**Gwet's AC₁** (Gwet 2008) is reported alongside kappa for all comparisons. AC₁ uses a different chance-agreement estimator that is robust to skewed marginal distributions, providing a more stable estimate when one category dominates (e.g., >80% of trials classified as "Other").

**Prevalence index** and **bias index** (Byrt, Bishop & Carlin 1993) are computed for each comparison to quantify the degree of marginal skew and systematic rater disagreement, respectively. When prevalence index > 0.5, Cohen's kappa is likely underestimating agreement, and AC₁ should be preferred.

**Per-annotator analysis**: Pairwise kappa between the agent and each individual human annotator (identified via the workload mapping) enables detection of annotator-specific biases. This reveals whether the agent systematically agrees more with certain annotators than others — a signal of annotator interpretation variability rather than agent error.

All confidence intervals use the large-sample normal approximation. With typical comparison sizes of n=35-62, these intervals should be interpreted with caution; bootstrap CIs may provide tighter estimates for future analyses with larger samples.

**Reporting guidance (v16):** For fields where the prevalence index exceeds 0.5 (Classification, Peptide), kappa is unreliable and AC₁ should be treated as the primary agreement metric. Kappa is retained for completeness and for fields with balanced distributions (Outcome, Delivery Mode, Reason for Failure). All concordance tables should report both kappa and AC₁ side by side. When interpreting kappa near zero with high raw agreement (>80%), the prevalence paradox is almost certainly the explanation — not poor agreement.

### 8.6 Impact of Value Normalization on Concordance

Verifier value normalization (Section 6.6) directly affects concordance calculations because it changes which trials achieve consensus and which are flagged for review. Retroactive application of the expanded normalization rules to 11 completed jobs produced the following impact:

- **74 individual field values corrected** across all affected jobs (verifier opinions remapped from status keywords to valid values).
- **12 consensus results restored** (fields that previously showed disagreement now achieve unanimous verifier agreement after normalization).
- **12 trials unflagged** from manual review queues (trials that were flagged solely due to false disagreements caused by verifier parsing failures).

This means concordance numbers calculated before the normalization fix understate actual pipeline accuracy. Any concordance analysis should be recalculated after retroactive fixes are applied to ensure reported agreement rates reflect genuine disagreements rather than parsing artifacts.

### 8.7 Concordance v3 Protocol

The v3 concordance protocol addresses three methodological issues identified in the v2 protocol:

**Issue 1: Asymmetric coverage.** Human annotators left 50-65% of fields blank. The v2 protocol only evaluated trials where both sides had a value, creating a biased sample. Fields that annotators found easy (and filled in) showed higher agreement than the true population rate.

**Issue 2: One-sided blanks.** When R1 annotated a field but R2 left it blank (or vice versa), this was invisible to concordance. For Peptide, R1 filled 473 trials that R2 left blank -- a massive asymmetry completely hidden from the v2 concordance numbers.

**Issue 3: Failure reason inflation.** The v2 protocol treated blank reason_for_failure as a valid "empty" value, causing 1709 both-blank pairs to count as agreement. The 91.3% agreement rate was dominated by blank-blank pairs, with only 46 trials where both annotators gave an actual reason.

**Three-tier reporting:**

| Tier | Denominator | Blank handling | Measures |
|---|---|---|---|
| Tier 1 (Strict) | Both sides filled | Skip if either blank | Quality of committed annotations |
| Tier 2 (Coverage) | At least one side filled | One-sided blank = disagree | Consistency of annotation effort |
| Tier 3 (Full) | All overlapping trials | Blank-blank = agree, one-sided = disagree | Overall annotation consistency |

**Failure reason special handling (v3):** Instead of treating all blank reason_for_failure values as "legitimately empty", the v3 protocol checks the corresponding outcome field:
- Both outcome and reason blank -- skip (annotator didn't engage)
- Non-failure outcome + blank reason -- legitimate empty (agreement if agent also empty)
- Failure outcome + blank reason -- missing data (treated as blank/skip)

### 8.8 Universal Blank Handling Standard

All concordance computations, annotator counts, and data displays follow one standard:

**An NCT is considered "annotated" by a human only if at least one of the five annotation fields has a non-blank value.** Rows where all five fields are blank/None are treated as unannotated — the annotator was assigned the row but did not engage with it.

This standard applies everywhere:
1. **Annotator NCT counts**: Only count rows with at least one filled field. Many annotators left large portions of their assigned rows blank (Ali 12%, Emre 7%, Berke 11% coverage in R1; Emily filled 817 of 1789 assigned rows in R2). Without this filter, counts are misleadingly inflated.
2. **Annotator-filtered concordance**: Only include annotated rows when computing per-annotator concordance.
3. **R1/R2 flat data**: The `_human_data_as_flat()` function excludes completely blank rows, so overlapping NCT counts and concordance denominators reflect actual annotations only.
4. **Per-field blank handling**: Within annotated rows, individual fields may still be blank. For `blank_means_skip=True` fields (classification, delivery_mode, outcome, peptide), the pair is skipped if either side is blank. For `reason_for_failure`, outcome-aware handling applies (blank reason + blank outcome = unannotated, blank reason + non-failure outcome = legitimate "no failure").
5. **Agent annotations**: Always have all 5 fields filled — the agent never produces blank annotations.

### 8.9 Concordance Limitations

1. **Both R1 and R2 are multi-annotator composites.** Cohen's kappa between R1 and R2 measures agreement between two teams of annotators, not between two single equivalent raters. Internal variability within each team is not captured by the current analysis and may inflate apparent R1-R2 disagreement.

2. **Missing data is not MCAR.** 43-65% of human annotations are blank across fields. Blanks are more likely for trials that are harder to annotate, introducing selection bias into the filled-only (Tier 1) concordance. The three-tier analysis (Section 8.7) partially mitigates this by reporting coverage-adjusted metrics.

3. **Sample sizes limit kappa precision.** Per-field comparisons range from n=35 to n=62, yielding 95% CI widths of ±0.10 to ±0.15 for moderate kappa values. Conclusions about "Moderate" vs "Substantial" agreement should be treated as approximate.

4. **Human baseline is a ceiling, not a floor.** The agent's concordance with R1 cannot meaningfully exceed R1's own reliability. When the agent achieves 72.7% outcome agreement with R1 vs R1-R2's 55.6%, this indicates the agent is more consistent with R1's interpretation — it does not prove the agent is more accurate than R2.


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

### 10.4 Server Configuration Options (v10)

The server hardware profile exposes additional YAML config toggles:

- **`server_premium_model`**: Selects the primary annotation model on server hardware. Options are `kimi-k2-thinking` (default) or `minimax-m2.7`.
- **`server_verifiers`**: Overrides the default Mac Mini verifier models with stronger server-grade models (see Section 6.1.4). Accepts a list of three Ollama model tags.
- **`ensure_model()`**: An auto-pull utility that checks whether each configured Ollama model is available locally before a run starts. Missing models are pulled automatically, preventing mid-run failures when switching hardware profiles or upgrading model versions.


## 11. v6 Version Comparison Results (n=70, 2026-03-17)

### 11.0.1 Summary

The same 70 trials were annotated by v5.1 agents (commit `22e9792`) and v6 agents (commit `8553a1f`). Research coverage increased +162% (684 → 1,793 total citations). Outcome concordance vs R1 improved +31.8pp (40.9% → 72.7%), exceeding human inter-rater agreement (55.6%). Review rate decreased -36% (50 → 32 field-level reviews). Peptide regressed -6.2pp due to multi-drug trial confusion.

### 11.0.2 Research Agent Status (v8, 2026-03-17)

| Agent | Status | Citations (n=10 test) | Notes |
|---|---|---|---|
| Clinical Protocol | Core | 77 (10/10) | ClinicalTrials.gov + OpenFDA |
| Literature | Core | 76 (7/10) | PubMed + PMC + Europe PMC. Semantic Scholar removed (429 rate limits) |
| Web Context | Working | 46 (10/10) | DuckDuckGo HTML lite search (fixed v7) |
| ChEMBL | Working | 42 (10/10) | Bioactivity, molecule types, mechanisms. Name-match filter added v8 |
| PDBe | Working | 18 (4/10) | Crystal structures with resolution/quality metrics |
| APD | Fixed v7 | 17 (10/10) | SSL verify disabled (cert chain broken). Returns AMP search results |
| Peptide Identity | Working | 17 (5/10) | UniProt + DRAMP |
| WHO ICTRP | Working | 10 (10/10) | International trial registry |
| EBI Proteins | Intermittent | 8 (3/10) | 500 errors from ebi.ac.uk, works when available |
| RCSB PDB | Fixed v8 | 6+ (varies) | v2 API uses "paginate" not "pager". Now returns real structures |
| DBAASP | Niche | 5 (1/10) | Only hits for actual AMPs. Correct behavior |
| IUPHAR | Working | 4 (4/10) | Pharmacology, FDA approval. Name-match filter added v8 |
| **REMOVED: dbAMP** | Dead | 0 | Server (yylab.jnu.edu.cn) permanently unreachable |
| **REMOVED: IntAct** | Noise | 0 | 1/10 hit rate, generic protein interactions (CFTR, MAPT, HTT) |
| **REMOVED: CARD** | Irrelevant | 0 | 0/10 hit rate, only for AMR-specific trials |
| **REMOVED: Semantic Scholar** | Rate limited | 0 | 429 on every batch, exhausts retries |
| dbAMP | Broken (intermittent) | 0 |
| EBI Proteins | Broken (unknown) | 0 |
| RCSB PDB | Broken (unknown) | 0 |
| PDBe | Broken (unknown) | 0 |
| Web Context | Broken (DuckDuckGo) | 0 |

### 11.0.3 Key Findings

1. **Research quality drives annotation quality.** The +162% citation increase directly caused the +31.8pp outcome improvement.
2. **Completion heuristics are effective but need calibration.** H1 (Phase I completion = Positive) over-applies when zero publications are found, causing 5 regressions vs R1.
3. **Cross-field coupling creates correlated instability.** When outcome shifts Unknown→Positive, failure reason shifts Ineffective→EMPTY, making both fields appear unstable between versions.
4. **78% of review items are automatable.** Cross-field consistency (outcome=Positive → force failure_reason=EMPTY) and heuristic-aware verifier prompts would resolve 25 of 32 reviews.

### 11.0.4 v8 Changes: Structured Evidence, Agent Cleanup, Hardware-Aware Budgets (2026-03-17)

**Agents removed (3 dead + 1 rate-limited source):**
- **dbAMP** (yylab.jnu.edu.cn): Server permanently unreachable (ConnectError on every request).
- **IntAct** (ebi.ac.uk/intact): 1/10 hit rate across test trials. Returned generic high-connectivity proteins (CFTR, MAPT, HTT) for almost every search — noise, not signal.
- **CARD** (card.mcmaster.ca): 0/10 hit rate. Only relevant for antibiotic resistance mechanism trials, which are extremely rare in the AMP clinical trial dataset.
- **Semantic Scholar**: Removed from literature agent. Heavy rate limiting (HTTP 429 on every batch, exhausting 3 retries per trial) made it unreliable. PubMed + PMC + Europe PMC provide sufficient literature coverage.

**Pipeline now:** 12 agents querying 17+ free databases (down from 15/20+).

**Structured evidence presentation (all agents + verifiers):**
- Evidence organized into labeled sections: TRIAL METADATA, PUBLISHED RESULTS, DRUG/PEPTIDE DATA, ANTIMICROBIAL DATA, STRUCTURAL DATA, WEB SOURCES.
- Noise filter strips: negative search results ("no exact match"), empty snippets (<15 chars), JSON artifacts.
- Relevance filter drops database results that don't mention actual trial interventions. Prevents fuzzy text-search false positives (e.g., searching "Peptide T" in IUPHAR no longer returns "GLP-1" or "peptide YY").
- Deduplication: citations with identical first 60 chars of snippet are skipped.
- Snippet capping per hardware profile: mac_mini 250 chars, server 500 chars.

**Hardware-profile-aware evidence budgets:**

| Profile | Models | Max Citations | Snippet Cap | Typical Token Range |
|---|---|---|---|---|
| mac_mini (16 GB) | 8B primary, 9B verifiers | 20-30 | 250 chars | 300-900 tokens |
| server (240+ GB) | 14B-70B primary, 14B verifiers | 35-50 | 500 chars | 500-1500 tokens |

Section budgets scale with max_citations so the server profile gets proportionally more literature, drug data, and structural data per trial.

**Source-level relevance filters** added to ChEMBL (name-match prevents fuzzy search returning random molecules) and IUPHAR (name-match prevents substring matches on different peptides). These complement the evidence builder's cross-cutting relevance filter.

---

## 11.1 v10 Preliminary Results (Batch A, n=25)

Twenty-five trials selected for maximum human annotation coverage (4-5 fields annotated by both R1 and R2) were annotated with the v10 architecture on 2026-03-19 (commit 8d6f236).

**Key metrics:**
- Duration: 3.0 hours (435s/trial average)
- Flagging rate: 4% (1/25 trials) — down from 54% in v4, 23% in v8
- EDAM: 125 experiences stored, 81 embeddings generated, epoch 1 established

**Concordance against human baselines:**

| Field | Agent vs R1 (κ) | Agent vs R2 (κ) | R1 vs R2 baseline (κ) | Agent exceeds? |
|---|---|---|---|---|
| Outcome | 0.742 [0.545, 0.940] | 0.691 [0.502, 0.881] | 0.36 | **Yes** |
| Classification | AC₁=0.917 | AC₁=0.865 | AC₁=0.89 | Matches |
| Peptide | 0.252 [-0.025, 0.530] | 0.000 | 0.00 | Improves vs R1 |
| Delivery Mode | 0.323 [0.170, 0.476] | 0.436 [0.248, 0.625] | 0.38 | Mixed |
| Reason for Failure | 0.396 [0.207, 0.584] | 0.431 [0.261, 0.600] | N/A | N/A |

**Outcome** is the headline result: κ=0.742 (Substantial) against R1, with the entire 95% CI above the Moderate threshold. This exceeds the human R1 vs R2 agreement of 55.6% by 24 percentage points.

**v10 verification features observed in logs:**
- 15 high-confidence primary overrides accepted primary annotation without reconciliation
- 51 deterministic verification skips (known drugs, registry statuses)
- 96 reconciler invocations resolved by the premium model
- Verification personas active (conservative, evidence-strict, adversarial assigned to verifier_1/2/3)

**Systematic patterns identified:**
- Delivery mode: agent defaults to "Other/Unspecified" in 12/14 disagreements where humans specified IV, SC, or IM
- Peptide: agent too strict on False for peptide vaccines (OSE2101, NEO-PV-01) and GLP-1 analogues (albiglutide) — definition refinement needed for borderline cases

---

## 12. Known Issues and v3/v4/v6 Fixes

### 12.1 Outcome Bias (v2)

**Problem:** The v2 outcome agent labeled approximately 80% of trials as "Failed - completed trial," including trials that were still recruiting, had positive results, or had simply completed without published data.

**Fix (v3):** Replaced the single-prompt approach with the calibrated two-pass decision tree described in Section 5.5. The decision tree enforces ordering (check recruiting/active first, check for positive results before considering failure) and requires cited evidence for a "Failed" label.

### 12.2 Over-Classification as AMP (v2)

**Problem:** The v2 classification agent over-classified peptide therapeutics as AMPs. Any peptide in a clinical trial tended to receive an AMP classification.

**Fix (v3):** Added explicit negative examples and the governing rule that most peptide therapeutics are not AMPs (Section 5.3). Added a default-to-Other heuristic for ambiguous cases.

### 12.3 Empty Delivery Modes (v2)

**Problem:** The v2 delivery mode agent returned empty or overly generic values for many trials where the route was determinable from the registry data.

**Fix (v3):** Implemented priority-ordered extraction with keyword mapping (Section 5.4). The agent now systematically searches multiple sections of the trial record before returning empty.

### 12.4 Failure Reasons for Non-Failed Trials (v2)

**Problem:** The v2 failure reason agent sometimes assigned failure reasons to trials that had not actually failed (e.g., recruiting trials, trials with positive results).

**Fix (v3):** Enhanced the short-circuit mechanism to check for positive signals before attempting failure classification (Section 5.6). The short-circuit now evaluates full evidence context rather than matching a single keyword.

### 12.5 8B Model Limitations

**Problem:** 8B-parameter models (the size used for most annotation and verification agents) tend to ignore worked examples provided in prompts. Even when the prompt includes detailed examples showing correct annotation behavior, the models frequently deviate from the demonstrated patterns.

**Implication:** This is the strongest argument for using the 14B-parameter reconciler (qwen2.5:14b) as the primary annotator rather than the 8B models. The 14B model shows better instruction-following and example adherence. This tradeoff is under evaluation.


### 12.6 Outcome Positive Bias (v6)

**Problem:** The v6 outcome agent over-applies the H1 completion heuristic (Phase I completion = Positive) even when zero publications are found. This caused 5 regressions vs R1 ground truth where the agent said "Positive" but the human said "Unknown" because no result evidence was available.

**Planned fix (v7):** Calibrate H1 to require at least one corroborating signal (results posted, published abstract, or subsequent trial) before overriding Unknown. Without corroboration, H1 should produce "Positive" at LOW confidence and flag for review rather than forcing Positive.

### 12.7 Multi-Drug Peptide Confusion (v6)

**Problem:** In multi-drug trials, the peptide agent evaluates whichever intervention ChEMBL returns data for first (typically small molecules), rather than examining all interventions. This caused 3 False→True regressions where the agent focused on a co-administered small molecule instead of the peptide vaccine.

**Planned fix (v7):** Modify Pass 1 to iterate over ALL interventions from the clinical_protocol agent and produce a fact extraction for each. Pass 2 then answers True if ANY intervention is a peptide.

### 12.8 Failure Reason Value Normalization (v6)

**Problem:** The pre-check skip path and `_infer_from_pass1()` fallback bypass `_parse_value()`, allowing non-canonical values like `INEFFECTIVE_FOR_PURPOSE` (uppercase sentinel), `INEFFECIVE_FOR_PURPOSE` (typo), and `EMPTY` (string instead of empty string) into the output.

**Planned fix (v7):** Route all output paths through `_parse_value()`. Add the typo variant to the fuzzy matching list.

## 13. Human Annotation Reliability

### 13.1 Annotator Divergence

The two independent human annotator groups (R1 and R2, each comprising multiple annotators) showed substantial disagreement on several fields, demonstrating that human annotations are not infallible ground truth.

Key divergences observed:

- **Peptide field:** R1 annotated Peptide=True for 451 trials (24% of the dataset). R2 annotated Peptide=True for 56 trials (3%). This indicates fundamentally different working definitions of "peptide."
- **Outcome field:** R1 used "Recruiting" 222 times. R2 used "Recruiting" 0 times. This suggests different interpretations of whether to record current registry status or inferred clinical outcome.
- **Peptide coverage:** Only 30 trials in the full dataset had the Peptide field filled in by both annotators, severely limiting concordance analysis for that field.

### 13.2 Practical Implication

Human annotations serve as development-time benchmarks for calibrating and improving the pipeline. They are not treated as infallible ground truth. Where human annotators disagree, the agent's annotation is evaluated against both independently, and neither human annotator is presumed correct by default.


## 14. Multi-Run Consensus

### 14.1 Approach

LLM outputs are nondeterministic. Running the same batch of trials through the pipeline multiple times (recommended N=3) and taking a majority vote per field reduces the impact of stochastic variation on any single annotation.

### 14.2 Implementation Status

Multi-run consensus is planned but not yet implemented as an automated feature. It can currently be approximated by running the pipeline multiple times and comparing outputs manually.

### 14.3 Expected Benefit

Fields where the pipeline is uncertain (low evidence quality, borderline classification) are most likely to vary across runs. Majority vote surfaces these cases: a field that receives different annotations across three runs is a natural candidate for manual review, while a field that is unanimous across runs has higher confidence.


## 15. Source Weight Rationale

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

### 15.6 v9.1 Optimization Pass

Additional optimizations applied after the initial v9 implementation:

1. **Failure reason verification skip**: The failure reason pre-check gate now sets `skip_verification=True` when returning empty for non-failure outcomes, saving 3 verifier calls per non-failure trial.

2. **Withdrawn outcome skip**: "Withdrawn" added to the failure reason pre-check skip list. Withdrawn trials (withdrawn before enrollment) don't have failure reasons.

3. **Reconciler value normalization**: The reconciler's output is now normalized through the same canonical mapping as verifier values, preventing non-canonical values from bypassing the normalization layer. Majority vote fallback also normalizes before counting.

4. **OpenFDA raw_data route extraction**: The delivery mode deterministic checker now also inspects structured OpenFDA route data from `raw_data` (the full API response), not just citation snippet text patterns.

5. **Server profile model selection**: All annotation agents (delivery_mode, peptide, failure_reason) now use qwen2.5:14b on the server hardware profile, matching classification and outcome. Previously these agents always used 8B regardless of hardware.

6. **Peptide cascade shortcut**: When classification was produced by the deterministic pre-classifier (skip_verification=True), the peptide cascade re-verification is skipped entirely. Deterministic classification is based on drug name lookup, not peptide value, so a flipped peptide cannot change the result.

7. **LLM call counter**: The Ollama client now tracks total and per-model LLM call counts, enabling measurement of the <15 calls/trial target.

8. **Semantic Scholar dead code removed**: The unused `_search_semantic_scholar()` method was removed from the literature agent (disabled since v8).

## 16. Self-Learning: Experience-Driven Annotation Memory (EDAM)

### 16.1 Overview

EDAM is a self-learning layer that improves annotation accuracy across runs without model fine-tuning. It uses three feedback loops operating on inference-time signals: cross-run stability consensus, evidence-grounded self-review, and automated prompt optimization. All learning persists to a SQLite database (`results/edam.db`) with Ollama embeddings for semantic retrieval.

EDAM is designed for autonomous operation — it requires zero human intervention to improve. Human review decisions are the highest-quality learning signal when available, but the system converges on accuracy through its own consistency analysis when humans are absent.

### 16.2 Three Feedback Loops

**Loop 1 — Stability Tracking.** After every job, EDAM compares each (NCT, field) annotation against all prior runs. Fields that produce the same value across 3+ runs are graded "stable" and their annotations become trusted exemplars. Fields that flip between values are flagged as unstable. Evidence anchoring grades each stable annotation as strong (published PMID, high confidence, consensus reached), medium (registry data, moderate confidence), weak (heuristic inference only), or none (single run, no comparison). Stable annotations at "none" evidence grade are flagged as potential systematic bias rather than trusted exemplars.

**Loop 2 — Correction Learning.** Two correction sources: (a) human review decisions (approve/override) stored with maximum weight, and (b) autonomous self-review using the premium model on flagged items. Self-review corrections require at least one concrete evidence citation (PMID, database identifier, or registry URL) — ungrounded self-corrections are rejected. Each correction generates a reflection explaining why the original annotation was wrong, which becomes retrievable guidance for future annotations via semantic embedding similarity search.

**Loop 2b — Evidence-Driven Self-Audit.** Runs on ALL trials after every job (not just flagged ones). Compares each annotation against the structured data collected by the research agents. Two audit types:

- **Delivery mode audit**: Scans evidence for explicit route keywords from FDA labels and protocol text (INTRAVENOUS, SUBCUTANEOUS, INTRAMUSCULAR, ORAL, TOPICAL, etc.). If evidence contains an explicit route but the agent output a less specific value (e.g., "Other" when FDA says "INTRAVENOUS", which should map to "Injection/Infusion"), the self-audit auto-corrects with the FDA citation as evidence. Routes are mapped to four categories: Injection/Infusion, Oral, Topical, Other.

- **Peptide audit**: Checks if research evidence (UniProt, DRAMP) contains amino acid counts in the peptide range (2-100 AA) that contradict the agent's peptide=True/False decision. A correction is only generated if no counter-evidence (monoclonal antibody, nutritional formula) is found. This catches cases where the agent has the molecular evidence but failed to apply the peptide definition correctly.

Both audit types require concrete evidence citations — no ungrounded corrections. Self-audit corrections are stored with "self_audit" source and moderate decay weight. Unlike Loop 2 self-review (which requires a flagged item and a premium model LLM call), self-audit is purely programmatic — it runs in milliseconds per trial with no LLM invocation.

**Loop 3 — Prompt Auto-Optimization.** Every 3rd job, EDAM analyzes per-field accuracy using corrections as ground truth. When a field's error rate exceeds 5%, the premium model proposes a minimal prompt modification targeting the most common error pattern. Variants are A/B tested: promoted after 20+ trials show ≥5% improvement, auto-discarded if accuracy drops by >5% after 10 trials. Prompt evolution is fully reversible.

### 16.3 Version-Gated Memory with Epoch Decay

Each configuration change (new model, new prompt, new thresholds) creates a new "epoch." Learning entries are tagged with their epoch and weighted by epoch distance from the current configuration:

| Source | Decay Rate | Floor Weight | Rationale |
|---|---|---|---|
| Human corrections | 0.85^d | 0.30 | Evidence→answer mapping is config-independent |
| Self-review corrections | 0.80^d | 0.10 | Model self-critique may have biases |
| Raw experiences | 0.75^d | 0.05 | Model behavior is config-specific |

Where d = epoch distance (current_epoch - entry_epoch). Human corrections never fully vanish because they represent ground truth about the evidence, not about model behavior.

### 16.4 Token Budget and Memory Limits

Each annotation LLM call receives a maximum of 2,000 tokens of EDAM guidance, allocated by priority:

| Category | Budget Share | Content |
|---|---|---|
| Corrections | 50% (1,000 tokens) | Past mistakes and how to avoid them |
| Stable exemplars | 25% (500 tokens) | Known-good few-shot examples |
| Prompt guidance | 15% (300 tokens) | Active variant instructions |
| Anomaly warnings | 10% (200 tokens) | Systematic bias alerts |

Database hard limits: 10,000 experiences, 5,000 corrections. Oldest low-weight entries are purged when limits are reached. Human corrections are protected from automatic purging.

### 16.5 Verifier Blindness Preservation

Verifiers receive ONLY anomaly warnings (field-wide statistical alerts), never corrections or exemplars. Injecting corrections into verifier prompts would leak the "expected" answer and defeat the purpose of blind verification. Anomaly warnings are safe because they contain no trial-specific information — only field-level statistics ("85% of recent trials classified as 'Other'").

### 16.6 Autonomous Learning Protocol

The recommended learning cycle for autonomous operation (no human intervention required):

| Phase | Runs | Dataset | Purpose |
|---|---|---|---|
| 1. Calibration | 3× | 10-NCT calibration set | Establish baseline stability |
| 2. Compounding | 3× | Same 10 NCTs | EDAM guidance active, corrections accumulate |
| 3. Transfer | 1× | Full 100+ NCT batch | Learning from calibration transfers to unseen trials |
| 4. Convergence | 1× | 10-NCT calibration set | Measure improvement vs Phase 1 baseline |

Phases 1-2 build the learning memory. Phase 3 tests generalization. Phase 4 measures the improvement delta. The cycle can be repeated indefinitely — each iteration adds more experiences, corrections, and prompt refinements.

### 16.7 Safeguards Against Runaway Learning

1. **Evidence-grounded corrections only.** Self-corrections must cite a specific source (PMID, database, registry). "I think it should be X" is never stored.
2. **Anomaly detection.** If >80% of trials receive the same value for any field across recent epochs, a warning is injected into all annotation and verification prompts.
3. **Prompt variants are reversible.** Every variant is A/B tested with measured accuracy. Regressions trigger automatic revert.
4. **Human corrections override everything.** When a human reviews an annotation, their decision is stored at maximum weight and never purged.
5. **Epoch boundaries prevent stale contamination.** Config changes demote old experiences rather than deleting them — the system re-learns under the new config with historical context.
6. **Database size caps.** Hard limits on all tables prevent unbounded growth. Purge strategy removes oldest, lowest-weight entries first.


## 17. Design Philosophy

### 17.1 Evidence-Grounded Learning Without Human Supervision

A core design principle of Agent Annotate is that the agent never sees human annotations during annotation or learning. Human annotations from the ground truth dataset (`human_ground_truth_train_df.csv`, R1 and R2) are used exclusively at evaluation time via concordance analysis. The EDAM self-learning system improves the agent through four internal signals:

1. **Cross-run stability**: consensus across independent runs as autonomous ground truth
2. **Evidence consistency**: self-audit compares annotations against the agent's own research data
3. **Self-review**: premium model re-evaluates flagged items with evidence citation requirements
4. **Prompt evolution**: accuracy metrics from self-audit corrections drive prompt modifications

This separation ensures that concordance improvements against human annotations reflect genuine accuracy gains, not overfitting to the evaluation set. The agent's accuracy is measured independently from its learning, which is essential for scientific credibility.

### 17.2 Lessons Learned From Iterative Error Analysis

The architecture evolved through six major versions, each driven by measured failure patterns:

| Version | Key Problem Identified | Fix Applied | Impact |
|---|---|---|---|
| v1-v2 | Single-pass agents stopped at registry status (26.7% outcome agreement) | Two-pass investigative design: extract facts, then apply decision tree | +46 pp outcome agreement |
| v3 | 8B models ignored worked examples in classification | Upgraded to 14B for classification, added explicit decision tree prompts | Classification accuracy stabilized |
| v4-v5 | Insufficient evidence: 4 research agents missed published results | Expanded to 15 research agents querying 20+ databases | +162% citation volume |
| v6-v7 | Cross-field inconsistencies generated false review items | Post-verification consistency enforcement | 25/32 review items auto-resolved |
| v8 | Verifiers injected spurious failure reasons (8.1% agreement) | Value normalization, failure_reason pre-check skip | +64.5 pp failure_reason agreement |
| v9 | Deterministic cases wasted LLM calls on verification | Programmatic pre-classifiers bypass verification for clear cases | 51 verification skips per 25 trials |
| v10 | Weak verifiers (7-9B) override strong primaries (14B) | Verification personas, dynamic confidence, high-confidence primary override, evidence budget parity | 54% → 4% flagging rate |

### 17.3 Hardware-Aware Design

The pipeline adapts to available hardware through a single `hardware_profile` configuration:

- **Mac Mini (16-24 GB)**: Sequential model loading, 5-minute keep-alive, 8B/9B verifiers, 14B for classification/reconciliation, 2000-token EDAM guidance budget, 10K experience database limit
- **Server (240+ GB)**: Persistent model loading, 60-minute keep-alive, 27B/32B verifiers, configurable premium model (kimi-k2-thinking or minimax-m2.7), 3500-token EDAM guidance budget, 100K experience database limit

All models are auto-pulled from Ollama on first use. No manual model management is required when switching hardware profiles.

### 17.4 Zero Paid API Dependencies

All research agents use free, publicly accessible APIs and databases. SerpAPI (previously used for web search) was removed. The NCBI API key (free registration) increases PubMed rate limits from 3/sec to 10/sec but is not required. This ensures the system can be deployed without subscription costs or API key management beyond a single free NCBI registration.
