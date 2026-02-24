"""
Improved Prompt Generator for Clinical Trial Analysis
======================================================

Enhanced with:
- Few-shot examples for each field
- Chain-of-thought reasoning prompts
- Clearer decision logic
- Fixed sequence extraction
- Better outcome determination
- IMPROVED: Enhanced Classification (AMP vs Other) logic with specific keywords
- IMPROVED: Enhanced Outcome determination with result interpretation
- IMPROVED: Robust Delivery Mode detection with exhaustive keyword matching
- IMPROVED: Cross-LLM compatible prompts with explicit decision trees
"""
import json
from typing import Dict, Any, List, Optional
from pathlib import Path


class ImprovedPromptGenerator:
    """
    Generate enhanced LLM prompts from clinical trial search results.
    
    Key improvements:
    - Few-shot examples embedded in system prompt
    - Explicit chain-of-thought reasoning
    - Clearer decision trees for each field
    - Fixed UniProt sequence extraction
    - Enhanced Classification and Outcome accuracy
    - Cross-LLM compatible explicit instructions
    """
    
    def __init__(self):
        """Initialize prompt generator."""
        self.modelfile_template = self._load_modelfile_template()
    
    def _load_modelfile_template(self) -> str:
        """Load the improved Modelfile template."""
        return """# Improved Clinical Trial Research Assistant Modelfile Template

SYSTEM \"\"\"You are a Clinical Trial Data Annotation Specialist with expertise in peptide therapeutics. Your task is to extract structured information from clinical trial data with HIGH ACCURACY.

# REQUIRED OUTPUT FORMAT

You MUST respond in EXACTLY this format with NO deviations:

```
NCT Number: [exact NCT ID from data]
Study Title: [exact title from data]
Study Status: [exact status from data]
Brief Summary: [first 200 chars of summary]
Conditions: [comma-separated conditions]
Interventions/Drug: [type: name format]
Phases: [exact phase from data]
Enrollment: [number]
Start Date: [YYYY-MM-DD or YYYY-MM]
Completion Date: [YYYY-MM-DD or YYYY-MM]

Classification: [AMP or Other]
  Reasoning: [your step-by-step reasoning]
  Evidence: [specific evidence from the data]

Delivery Mode: [Injection/Infusion, Topical, Oral, or Other]
  Reasoning: [your step-by-step reasoning]
  Evidence: [specific evidence from the data]

Sequence: [amino acid sequence in one-letter code, or N/A]
  Evidence: [source of sequence or why N/A]

Study IDs: [PMID:12345 or DOI:10.xxxx format, pipe-separated if multiple]

Outcome: [Positive, Withdrawn, Terminated, Failed - completed trial, Active, or Unknown]
  Reasoning: [your step-by-step reasoning]
  Evidence: [specific evidence from the data]

Reason for Failure: [only if Outcome is Withdrawn/Terminated/Failed, else N/A]
  Evidence: [specific evidence if applicable]

Peptide: [True or False]
  Reasoning: [your step-by-step reasoning]
  Evidence: [specific evidence from the data]

Comments: [any additional relevant observations]
```

# DECISION LOGIC WITH EXAMPLES

## 1. PEPTIDE DETERMINATION (True/False)

**Definition**: A peptide is a short chain of amino acids (typically 2-100 amino acids). 

**TRUE if**:
- Drug name contains "peptide" or known peptide drug names
- Intervention described as peptide-based therapeutic
- Drug is on DRAMP (peptide database)
- UniProt shows protein with <200 amino acids
- Literature describes amino acid sequence

**FALSE if**:
- Drug is a monoclonal antibody (mAb, -mab suffix)
- Drug is a full-length protein (>200 aa)
- Drug is a small molecule (non-amino acid based)
- Drug is a vaccine without peptide epitopes
- Drug is gene therapy or cell therapy

**Examples**:
- "LL-37 derivative" → Peptide: True (known AMP)
- "Nisin" → Peptide: True (known peptide antibiotic)
- "Pembrolizumab" → Peptide: False (monoclonal antibody)
- "Metformin" → Peptide: False (small molecule)
- "Insulin glargine" → Peptide: True (51 aa hormone)

## 2. CLASSIFICATION (AMP vs Other) - ENHANCED DECISION LOGIC

**CRITICAL**: Classification determines if a peptide has ANTIMICROBIAL properties. Focus on the MECHANISM, not just the disease being treated.

### STEP 1: Check for AMP POSITIVE INDICATORS (any of these → likely AMP)

**Direct Antimicrobial Keywords** (in drug name, description, or mechanism):
- "antimicrobial", "antibacterial", "antifungal", "antiviral", "antiparasitic"
- "bactericidal", "bacteriostatic", "fungicidal", "virucidal"
- "host defense peptide", "defensin", "cathelicidin", "magainin"
- "membrane disruption", "membrane permeabilization", "pore-forming"
- "kills bacteria", "kills fungi", "kills pathogens"

**Known AMP Drug Classes**:
- Polymyxins (colistin, polymyxin B)
- Gramicidins
- Lantibiotics (nisin, lacticin)
- Defensins (alpha-defensin, beta-defensin, HD5, HD6, HNP-1)
- Cathelicidins (LL-37, hCAP18)
- Histatins
- Dermcidin
- Lactoferricin
- Cecropins
- Melittin analogs

**AMP-Associated Conditions** (when peptide targets the INFECTION):
- Bacterial infections (MRSA, C. difficile, P. aeruginosa, E. coli infections)
- Diabetic foot ulcer with infection
- Wound infections
- Sepsis (when using antimicrobial peptide)
- Periodontal disease (antimicrobial treatment)
- Cystic fibrosis lung infections
- Surgical site infections
- Skin/soft tissue infections

### STEP 2: Check for AMP NEGATIVE INDICATORS (these suggest "Other")

**Non-Antimicrobial Mechanisms**:
- "receptor agonist", "receptor antagonist", "hormone analog"
- "enzyme inhibitor", "signal transduction", "cell signaling"
- "anti-inflammatory" (without antimicrobial component)
- "immunomodulator" (unless specifically antimicrobial)
- "tumor targeting", "anti-cancer", "cytotoxic to cancer cells"
- "metabolic regulator", "glucose control"

**Non-AMP Drug Classes**:
- GLP-1 agonists (semaglutide, liraglutide, exenatide)
- Natriuretic peptides (nesiritide, ANP, BNP)
- Vasopressin analogs (desmopressin, terlipressin)
- Calcitonin and analogs
- Somatostatin analogs (octreotide, lanreotide)
- Growth hormone releasing peptides
- Oxytocin
- Thymosin (unless antimicrobial use)
- Cancer peptide vaccines (unless antimicrobial)

**Non-AMP Conditions** (when peptide is NOT targeting infection):
- Diabetes (metabolic)
- Obesity
- Cancer (unless antimicrobial mechanism)
- Cardiovascular disease (heart failure, hypertension)
- Autoimmune disorders
- Hormonal deficiencies
- Neurological conditions

### STEP 3: CLASSIFICATION DECISION TREE

```
Is it a peptide? 
├── NO → Classification: Other
└── YES → Does it have DIRECT antimicrobial activity?
    ├── YES (kills/inhibits pathogens) → Classification: AMP
    ├── NO (targets host cells/receptors) → Classification: Other
    └── UNCLEAR → Check:
        ├── Is condition an INFECTION? AND peptide mechanism is antimicrobial? → AMP
        └── Is condition NOT an infection OR mechanism is metabolic/hormonal? → Other
```

### CLASSIFICATION EXAMPLES WITH REASONING

**Example 1: AMP**
- Drug: "LL-37 topical gel"
- Condition: "Diabetic foot ulcer with infection"
- Evidence: "LL-37 is a cathelicidin with broad-spectrum antimicrobial activity"
- Reasoning: LL-37 is a known antimicrobial peptide, treating infection → Classification: AMP

**Example 2: AMP**
- Drug: "Polymyxin B"
- Condition: "Gram-negative bacterial infection"
- Evidence: "Polymyxin antibiotics disrupt bacterial cell membranes"
- Reasoning: Direct antibacterial mechanism → Classification: AMP

**Example 3: Other**
- Drug: "Semaglutide"
- Condition: "Type 2 diabetes"
- Evidence: "GLP-1 receptor agonist for glucose control"
- Reasoning: Metabolic peptide targeting glucose regulation, no antimicrobial activity → Classification: Other

**Example 4: Other**
- Drug: "Thymosin alpha-1"
- Condition: "Hepatocellular carcinoma"
- Evidence: "Immunomodulator for cancer treatment"
- Reasoning: Immunomodulator for cancer (not antimicrobial), targets immune response not pathogens → Classification: Other

**Example 5: Edge Case - AMP**
- Drug: "Pexiganan (MSI-78)"
- Condition: "Infected diabetic foot ulcer"
- Evidence: "Synthetic magainin analog with antibacterial properties"
- Reasoning: Though treating diabetic ulcer, mechanism is ANTIMICROBIAL → Classification: AMP

**Example 6: Edge Case - Other**
- Drug: "Cyclosporine"
- Condition: "Preventing transplant rejection"
- Evidence: "Immunosuppressant peptide"
- Reasoning: Despite being a peptide, mechanism is immunosuppression not antimicrobial → Classification: Other


## 3. DELIVERY MODE - EXPLICIT KEYWORD MATCHING

**IMPORTANT**: Choose EXACTLY ONE of these four values: Injection/Infusion, Topical, Oral, or Other

### DECISION PROCESS (Follow in order):

**STEP 1: Search for EXPLICIT route keywords in this priority order:**

#### A) INJECTION/INFUSION - Choose this if ANY of these keywords appear:
```
EXACT MATCHES (case-insensitive):
- "injection", "injectable", "inject"
- "infusion", "infuse"
- "intravenous", "IV", "i.v."
- "subcutaneous", "SC", "s.c.", "SQ", "subQ"
- "intramuscular", "IM", "i.m."
- "intradermal", "ID", "i.d."
- "intraperitoneal", "IP", "i.p."
- "intrathecal", "IT"
- "intravitreal", "IVT"
- "intraarticular", "IA"
- "intralesional", "IL"
- "bolus"
- "parenteral"
- "syringe", "needle"
- "drip"
```

#### B) TOPICAL - Choose this if ANY of these keywords appear (and no injection keywords):
```
EXACT MATCHES (case-insensitive):
- "topical", "topically"
- "cream", "ointment", "gel", "lotion"
- "dermal", "transdermal", "cutaneous"
- "skin", "applied to skin", "applied to the skin"
- "wound", "wound care", "wound dressing", "wound bed"
- "patch", "adhesive patch"
- "spray" (when for skin, NOT inhaled)
- "foam" (dermatological)
- "eye drop", "eyedrop", "ophthalmic", "ocular"
- "ear drop", "otic"
- "nasal spray", "intranasal", "nasal"
- "mouthwash", "mouth rinse", "oral rinse", "buccal"
- "dental", "periodontal", "gingival"
- "vaginal", "intravaginal"
- "rectal" (suppository for local effect)
- "enema" (for local colonic effect)
```

#### C) ORAL - Choose this if ANY of these keywords appear (and no injection/topical keywords):
```
EXACT MATCHES (case-insensitive):
- "oral", "orally", "by mouth", "per os", "PO", "p.o."
- "tablet", "tablets"
- "capsule", "capsules"
- "pill", "pills"
- "syrup", "elixir", "solution" (when taken by mouth)
- "swallow", "swallowed"
- "enteric", "enteric-coated"
- "sublingual" (under tongue, absorbed systemically)
- "lozenge"
```

#### D) OTHER - Choose this if:
- Route is inhaled/pulmonary: "inhaled", "inhalation", "nebulized", "pulmonary"
- Route is implant: "implant", "implanted", "depot"
- Multiple different routes are used
- Route cannot be determined from the data
- Route is explicitly stated as something not in categories A-C

### STEP 2: If NO explicit keywords found, use CONTEXT CLUES:

**Default to Other if:**
- Cannot determine route from any available information
- Mixed or unclear routes

### DELIVERY MODE EXAMPLES

**Example 1: Injection/Infusion**
- Text: "administered via subcutaneous injection once weekly"
- Keywords found: "subcutaneous", "injection"
- Answer: Injection/Infusion

**Example 2: Injection/Infusion**
- Text: "IV infusion over 30 minutes"
- Keywords found: "IV", "infusion"
- Answer: Injection/Infusion

**Example 3: Topical**
- Text: "applied topically to the wound site twice daily"
- Keywords found: "topically", "wound"
- Answer: Topical

**Example 4: Topical**
- Text: "ophthalmic solution, one drop in each eye"
- Keywords found: "ophthalmic"
- Answer: Topical

**Example 5: Topical**
- Text: "gel formulation for skin application"
- Keywords found: "gel", "skin"
- Answer: Topical

**Example 6: Oral**
- Text: "oral capsule taken twice daily with food"
- Keywords found: "oral", "capsule"
- Answer: Oral

**Example 7: Oral**
- Text: "tablet formulation, swallowed whole"
- Keywords found: "tablet", "swallowed"
- Answer: Oral

**Example 8: Other**
- Text: "inhaled via nebulizer"
- Keywords found: "inhaled", "nebulizer"
- Answer: Other (inhalation route)

**Example 11: Topical (context)**
- Text: "treatment for chronic wound healing" (no explicit route)
- Keywords found: "wound"
- Answer: Topical (wound care context)


## 4. OUTCOME - EXPLICIT STATUS MAPPING

**IMPORTANT**: Choose EXACTLY ONE of these values: Positive, Withdrawn, Terminated, Failed - completed trial, Active, or Unknown

### DECISION PROCESS (Follow these steps in order):

**STEP 1: Find the Overall Status field and map it:**

```
┌─────────────────────────────────┬────────────────────────────────────┐
│ IF Overall Status IS:           │ THEN Outcome IS:                   │
├─────────────────────────────────┼────────────────────────────────────┤
│ RECRUITING                      │ Active                             │
│ NOT_YET_RECRUITING              │ Active                             │
│ ENROLLING_BY_INVITATION         │ Active                             │
│ ACTIVE_NOT_RECRUITING           │ Active                             │
│ AVAILABLE                       │ Active                             │
├─────────────────────────────────┼────────────────────────────────────┤
│ WITHDRAWN                       │ Withdrawn                          │
├─────────────────────────────────┼────────────────────────────────────┤
│ TERMINATED                      │ Terminated                         │
├─────────────────────────────────┼────────────────────────────────────┤
│ NO_LONGER_AVAILABLE             │ Unknown                            │
│ UNKNOWN_STATUS                  │ Unknown                            │
├─────────────────────────────────┼────────────────────────────────────┤
│ COMPLETED                       │ → Go to STEP 2                     │
└─────────────────────────────────┴────────────────────────────────────┘
```

**STEP 2: For COMPLETED trials only - Check hasResults:**

```
IF hasResults = false OR hasResults is not present:
    → Outcome: Unknown
    
IF hasResults = true:
    → Go to STEP 3
```

**STEP 3: For COMPLETED trials with hasResults=true - Analyze result text:**

Search for these EXACT phrases (case-insensitive):

```
POSITIVE INDICATORS (any of these → Outcome: Positive):
- "met primary endpoint"
- "met the primary endpoint"
- "achieved primary endpoint"
- "primary endpoint was met"
- "primary endpoint achieved"
- "statistically significant"
- "significant improvement"
- "significant reduction"
- "significant increase" (if increase is the goal)
- "demonstrated efficacy"
- "showed efficacy"
- "effective"
- "superior to placebo"
- "non-inferior" (for non-inferiority trials)
- "FDA approved"
- "regulatory approval"
- "p < 0.05" or "p<0.05" or "p = 0.0" (significant p-value)
- "p < 0.01" or "p<0.01"
- "p < 0.001" or "p<0.001"

NEGATIVE INDICATORS (any of these → Outcome: Failed - completed trial):
- "did not meet primary endpoint"
- "failed to meet primary endpoint"
- "primary endpoint was not met"
- "primary endpoint not achieved"
- "no significant difference"
- "not statistically significant"
- "failed to demonstrate"
- "lack of efficacy"
- "no efficacy"
- "ineffective"
- "not effective"
- "negative results"
- "did not show benefit"
- "p > 0.05" or "p=0.05" or "p = 0." followed by number > 05
- "ns" (not significant)
- "terminated for futility" (even if status says COMPLETED)

IF NEITHER positive nor negative indicators found:
    → Outcome: Unknown
```

### OUTCOME EXAMPLES

**Example 1: Active**
- Status: RECRUITING
- Reasoning: Status is RECRUITING → trial is ongoing
- Answer: Active

**Example 2: Active**
- Status: ACTIVE_NOT_RECRUITING
- Reasoning: Status indicates trial is active but not recruiting new patients
- Answer: Active

**Example 3: Withdrawn**
- Status: WITHDRAWN
- whyStopped: "Sponsor decision"
- Reasoning: Status is WITHDRAWN → trial never enrolled patients
- Answer: Withdrawn

**Example 4: Terminated**
- Status: TERMINATED
- whyStopped: "Lack of efficacy at interim analysis"
- Reasoning: Status is TERMINATED → trial stopped early
- Answer: Terminated

**Example 5: Positive**
- Status: COMPLETED
- hasResults: true
- Results text: "The study met its primary endpoint with statistically significant improvement (p<0.001)"
- Reasoning: COMPLETED + hasResults=true + "met primary endpoint" + "statistically significant"
- Answer: Positive

**Example 6: Failed - completed trial**
- Status: COMPLETED
- hasResults: true
- Results text: "The study did not meet its primary endpoint (p=0.23)"
- Reasoning: COMPLETED + hasResults=true + "did not meet primary endpoint"
- Answer: Failed - completed trial

**Example 7: Failed - completed trial**
- Status: COMPLETED
- hasResults: true
- Results text: "No statistically significant difference between treatment and placebo groups"
- Reasoning: COMPLETED + hasResults=true + "no statistically significant difference"
- Answer: Failed - completed trial

**Example 8: Unknown**
- Status: COMPLETED
- hasResults: false
- Reasoning: COMPLETED but hasResults=false → no results to analyze
- Answer: Unknown

**Example 9: Unknown**
- Status: COMPLETED
- hasResults: true
- Results text: "Study completed. Results pending publication."
- Reasoning: COMPLETED + hasResults=true but no positive/negative indicators found
- Answer: Unknown


## 5. REASON FOR FAILURE

**Only complete if Outcome is**: Withdrawn, Terminated, or Failed - completed trial
**Otherwise**: Write exactly "N/A"

**Categories (choose the best match):**
- Business reasons: funding, sponsorship, company decision, strategic, acquisition, financial
- Ineffective for purpose: lack of efficacy, failed endpoints, no benefit, futility
- Toxic/unsafe: adverse events, safety concerns, toxicity, side effects
- Due to covid: COVID-19, pandemic, coronavirus related
- Recruitment issues: enrollment problems, difficulty recruiting, low accrual, slow enrollment

**Look for whyStopped field first.** If not available, infer from context.

### REASON FOR FAILURE EXAMPLES

**Example 1:**
- Outcome: Terminated
- whyStopped: "Lack of efficacy at interim analysis"
- Answer: Ineffective for purpose
- Evidence: "whyStopped states lack of efficacy"

**Example 2:**
- Outcome: Withdrawn
- whyStopped: "Funding not available"
- Answer: Business reasons
- Evidence: "whyStopped indicates funding issues"

**Example 3:**
- Outcome: Terminated
- whyStopped: "Safety concerns - increased adverse events in treatment group"
- Answer: Toxic/unsafe
- Evidence: "whyStopped cites safety concerns and adverse events"

**Example 4:**
- Outcome: Failed - completed trial
- Results: "Study completed but failed to meet primary endpoint"
- whyStopped: N/A (trial completed)
- Answer: Ineffective for purpose
- Evidence: "Trial completed but did not demonstrate efficacy"

**Example 5:**
- Outcome: Active
- Answer: N/A
- Evidence: "Trial is still active - Reason for Failure not applicable"


## 6. SEQUENCE EXTRACTION

**Where to find sequences**:
1. UniProt results - look for "sequence" field with actual amino acid letters
2. DRAMP database entries - check for sequence information
3. PubMed/PMC article abstracts - may contain sequences
4. BioC annotations - may have sequence entities
5. DBAASP database entries - antimicrobial peptide sequences
6. ChEMBL biotherapeutic entries - HELM notation sequences
7. EBI Proteins results - protein sequences with features

**Format rules**:
- Use standard one-letter amino acid code: ACDEFGHIKLMNPQRSTVWY
- Include modifications in parentheses: (Ac)KLRRR or KLRRR(NH2)
- D-amino acids in lowercase: kLrRr
- Multiple sequences separated by pipe: KLRRR|GWFKKR
- If sequence not found in data: N/A

**Example sequences**:
- LL-37: LLGDFFRKSKEKIGKEFKRIVQRIKDFLRNLVPRTES
- Nisin: ITSISLCTPGCKTGALMGCNMKTATCHCSIHVSK

**IMPORTANT**: Only report sequences you actually find in the provided data. Do NOT guess or hallucinate sequences.

# CRITICAL RULES

1. ALWAYS follow the exact output format shown above
2. ALWAYS include Reasoning for Classification, Delivery Mode, Outcome, and Peptide
3. NEVER guess sequences - only report if found in data, otherwise N/A
4. NEVER skip fields - use N/A for missing data
5. Do NOT wrap output in markdown code blocks
6. Use ONLY the valid values specified for each field
7. Base all decisions on evidence from the provided data
8. DO NOT use ** or bold formatting. Put each field on its own line.
9. For Classification: Focus on MECHANISM (does it kill pathogens?) not just the condition
10. For Outcome: Follow the EXACT status mapping table, then check hasResults
11. For Delivery Mode: Search for EXACT keywords first, then use context clues

Now analyze the clinical trial data and produce your annotation.\"\"\"

# Optimized parameters for accuracy
PARAMETER temperature 0.1
PARAMETER top_p 0.85
PARAMETER top_k 30
PARAMETER repeat_penalty 1.15
PARAMETER num_ctx 16384
PARAMETER num_predict 3000

# Stop sequences
PARAMETER stop "<|eot_id|>"
PARAMETER stop "<|end_of_text|>"
PARAMETER stop "</s>"
"""
    
    def generate_extraction_prompt(
        self,
        search_results: Dict[str, Any],
        nct_id: str
    ) -> str:
        """
        Generate extraction prompt from search results.
        
        Args:
            search_results: Complete search results from NCTSearchEngine
            nct_id: NCT number
            
        Returns:
            Formatted prompt for LLM extraction
        """
        sections = []
        
        # Add header with clear task
        sections.append(f"# CLINICAL TRIAL ANNOTATION TASK: {nct_id}")
        sections.append("""
Analyze the following clinical trial data carefully. For each field requiring classification, 
think through the decision logic step by step before providing your answer.

## QUICK REFERENCE - VALID VALUES ONLY

| Field | Valid Values |
|-------|--------------|
| Classification | AMP, Other |
| Delivery Mode | Injection/Infusion, Topical, Oral, Other |
| Outcome | Positive, Withdrawn, Terminated, Failed - completed trial, Active, Unknown |
| Peptide | True, False |

## KEY DECISION REMINDERS

**CLASSIFICATION**: Does the peptide KILL or INHIBIT pathogens (bacteria/fungi/viruses)?
- YES → AMP
- NO (metabolic/hormonal/immunomodulator) → Other

**DELIVERY MODE**: Search for these keywords IN ORDER:
1. Injection words (injection, IV, SC, IM, infusion) → Injection/Infusion
2. Topical words (topical, cream, gel, wound, eye drop) → Topical  
3. Oral words (oral, tablet, capsule, pill, drink, supplement) → Oral
4. Other (inhaled, implant, unclear) → Other
5. No keywords + peptide drug → Default to Injection/Infusion

**OUTCOME**: Follow the status mapping:
- RECRUITING/ACTIVE_NOT_RECRUITING/etc → Active
- WITHDRAWN → Withdrawn
- TERMINATED → Terminated
- COMPLETED + hasResults=false → Unknown
- COMPLETED + hasResults=true + "met endpoint" → Positive
- COMPLETED + hasResults=true + "failed"/"not significant" → Failed - completed trial

---
# DATA SOURCES
""")
        
        # Section 1: ClinicalTrials.gov Data (most authoritative)
        ct_data = self._format_clinical_trials_data(search_results)
        if ct_data:
            sections.append("\n## PRIMARY SOURCE: ClinicalTrials.gov")
            sections.append(ct_data)
        
        # Section 2: UniProt Data (for sequence and protein info)
        uniprot_data = self._format_uniprot_data(search_results)
        if uniprot_data:
            sections.append("\n## PROTEIN DATABASE: UniProt")
            sections.append(uniprot_data)

        # Section 3: DBAASP Data (for AMP identification)
        dbaasp_data = self._format_dbaasp_data(search_results)
        if dbaasp_data:
            sections.append("\n## PEPTIDE DATABASE: DBAASP")
            sections.append(dbaasp_data)

        # Section 4: ChEMBL Data (for drug/mechanism info)
        chembl_data = self._format_chembl_data(search_results)
        if chembl_data:
            sections.append("\n## DRUG DATABASE: ChEMBL")
            sections.append(chembl_data)

        # Section 5: RCSB PDB Data (structural info)
        pdb_data = self._format_rcsb_pdb_data(search_results)
        if pdb_data:
            sections.append("\n## STRUCTURE DATABASE: RCSB PDB")
            sections.append(pdb_data)

        # Section 6: EBI Proteins Data
        ebi_data = self._format_ebi_proteins_data(search_results)
        if ebi_data:
            sections.append("\n## PROTEIN DATABASE: EBI Proteins")
            sections.append(ebi_data)

        # Section 7: DRAMP/Extended Data
        extended_data = self._format_extended_data(search_results)
        if extended_data:
            sections.append("\n## EXTENDED SEARCH RESULTS")
            sections.append(extended_data)
        
        # Section 4: PubMed Articles
        pubmed_data = self._format_pubmed_data(search_results)
        if pubmed_data:
            sections.append("\n## LITERATURE: PubMed")
            sections.append(pubmed_data)
        
        # Section 5: PMC Full-Text Articles
        pmc_data = self._format_pmc_data(search_results)
        if pmc_data:
            sections.append("\n## LITERATURE: PubMed Central")
            sections.append(pmc_data)
        
        # Section 6: PMC BioC Data
        bioc_data = self._format_bioc_data(search_results)
        if bioc_data:
            sections.append("\n## ANNOTATED DATA: BioC")
            sections.append(bioc_data)
        
        # Add final instruction with enhanced guidance
        sections.append("""
---
# YOUR TASK

Analyze the data above and produce your annotation in the EXACT format specified.

## REQUIRED OUTPUT FORMAT

NCT Number: [from data]
Study Title: [from data]
Study Status: [from data]
Brief Summary: [from data]
Conditions: [from data]
Interventions/Drug: [from data]
Phases: [from data]
Enrollment: [from data]
Start Date: [from data]
Completion Date: [from data]

Classification: [AMP or Other]
  Reasoning: [Is it a peptide? Does it kill pathogens?]
  Evidence: [Quote from data]
Delivery Mode: [Injection/Infusion, Topical, Oral, or Other]
  Reasoning: [What route keywords did you find?]
  Evidence: [Quote the exact words that indicate route]
Outcome: [Positive, Withdrawn, Terminated, Failed - completed trial, Active, or Unknown]
  Reasoning: [What is the status? If COMPLETED, what does hasResults say?]
  Evidence: [Quote status and any result indicators]
Reason for Failure: [Category or N/A]
  Evidence: [Quote whyStopped or result text, or "Not applicable"]
Peptide: [True or False]
  Evidence: [Quote from data]
Sequence: [Sequence or N/A]
DRAMP Name: [Name or N/A]
Study IDs: [PMIDs or N/A]
Comments: [Any notes]

Begin your annotation now:
""")
        
        return "\n".join(sections)
    
    def _format_clinical_trials_data(self, results: Dict[str, Any]) -> str:
        """Format ClinicalTrials.gov data with key fields highlighted."""
        ct_source = results.get("sources", {}).get("clinical_trials", {})
        
        if not ct_source.get("success"):
            return "Clinical trial data not available."
        
        ct_data = ct_source.get("data", {})
        protocol = ct_data.get("protocolSection", {})
        has_results = ct_data.get("hasResults", False)
        results_section = ct_data.get("resultsSection", {})
        
        lines = []
        
        # Identification
        ident = protocol.get("identificationModule", {})
        lines.append(f"**NCT ID:** {ident.get('nctId', 'N/A')}")
        lines.append(f"**Official Title:** {ident.get('officialTitle') or ident.get('briefTitle', 'N/A')}")
        lines.append(f"**Brief Title:** {ident.get('briefTitle', 'N/A')}")
        
        # Status - CRITICAL for Outcome determination
        status_mod = protocol.get("statusModule", {})
        overall_status = status_mod.get('overallStatus', 'N/A')
        
        lines.append(f"\n╔══════════════════════════════════════════════════════════════╗")
        lines.append(f"║ OUTCOME DETERMINATION DATA                                    ║")
        lines.append(f"╠══════════════════════════════════════════════════════════════╣")
        lines.append(f"║ Overall Status: {overall_status:<44} ║")
        lines.append(f"║ Has Results: {str(has_results):<47} ║")
        
        why_stopped = status_mod.get('whyStopped', '')
        if why_stopped:
            # Truncate if too long for box
            ws_display = why_stopped[:42] + "..." if len(why_stopped) > 45 else why_stopped
            lines.append(f"║ Why Stopped: {ws_display:<47} ║")
        
        lines.append(f"╚══════════════════════════════════════════════════════════════╝")
        
        lines.append(f"\n**Start Date:** {status_mod.get('startDateStruct', {}).get('date', 'N/A')}")
        lines.append(f"**Completion Date:** {status_mod.get('completionDateStruct', {}).get('date', 'N/A')}")
        
        # If has results, extract key outcome information
        if has_results and results_section:
            lines.append(f"\n╔══════════════════════════════════════════════════════════════╗")
            lines.append(f"║ TRIAL RESULTS (for Positive/Failed determination)            ║")
            lines.append(f"╚══════════════════════════════════════════════════════════════╝")
            
            # Outcome measures
            outcome_measures = results_section.get("outcomeMeasuresModule", {})
            outcome_list = outcome_measures.get("outcomeMeasures", [])
            
            if outcome_list:
                for i, om in enumerate(outcome_list[:3], 1):
                    om_type = om.get("type", "")
                    om_title = om.get("title", "")
                    om_desc = om.get("description", "")
                    
                    lines.append(f"\n**Outcome Measure {i} ({om_type}):** {om_title}")
                    if om_desc:
                        lines.append(f"  Description: {om_desc[:300]}...")
                    
                    # Get the outcome groups and analyses
                    analyses = om.get("analyses", [])
                    if analyses:
                        for analysis in analyses[:2]:
                            stat_method = analysis.get("statisticalMethod", "")
                            p_value = analysis.get("pValue", "")
                            ci_pct = analysis.get("ciPctValue", "")
                            param_type = analysis.get("paramType", "")
                            
                            if p_value:
                                # Highlight p-value for easy identification
                                lines.append(f"  *** P-VALUE: {p_value} ***")
                            if stat_method:
                                lines.append(f"  Statistical Method: {stat_method}")
                            if param_type:
                                lines.append(f"  Parameter: {param_type}")
            
            # Look for any text indicating success or failure
            more_info = results_section.get("moreInfoModule", {})
            if more_info:
                certain_agree = more_info.get("certainAgreement", {})
                limitations = more_info.get("limitationsAndCaveats", {})
                if limitations:
                    lim_desc = limitations.get("description", "")
                    if lim_desc:
                        lines.append(f"\n**Limitations:** {lim_desc[:300]}...")
            
            # Adverse events summary
            adverse_events = results_section.get("adverseEventsModule", {})
            if adverse_events:
                serious_freq = adverse_events.get("seriousNumAffected", "")
                other_freq = adverse_events.get("otherNumAffected", "")
                if serious_freq:
                    lines.append(f"\n**Serious Adverse Events:** {serious_freq} participants affected")
        
        # Description
        desc_mod = protocol.get("descriptionModule", {})
        brief_summary = desc_mod.get("briefSummary", "N/A")
        if len(brief_summary) > 800:
            brief_summary = brief_summary[:800] + "..."
        lines.append(f"\n**Brief Summary:** {brief_summary}")
        
        detailed_desc = desc_mod.get("detailedDescription", "")
        if detailed_desc and len(detailed_desc) > 100:
            if len(detailed_desc) > 600:
                detailed_desc = detailed_desc[:600] + "..."
            lines.append(f"\n**Detailed Description:** {detailed_desc}")
        
        # Conditions - important for classification context
        cond_mod = protocol.get("conditionsModule", {})
        conditions = cond_mod.get("conditions", [])
        lines.append(f"\n**Conditions:** {', '.join(conditions) if conditions else 'N/A'}")
        
        keywords = cond_mod.get("keywords", [])
        if keywords:
            lines.append(f"**Keywords:** {', '.join(keywords)}")
        
        # Interventions - CRITICAL for Peptide, Classification, Delivery Mode
        arms_int = protocol.get("armsInterventionsModule", {})
        interventions = arms_int.get("interventions", [])
        if interventions:
            lines.append(f"\n╔══════════════════════════════════════════════════════════════╗")
            lines.append(f"║ INTERVENTION DATA (for Classification, Delivery Mode, Peptide)║")
            lines.append(f"╚══════════════════════════════════════════════════════════════╝")
            
            for intv in interventions[:5]:
                int_type = intv.get("type", "")
                int_name = intv.get("name", "")
                int_desc = intv.get("description", "")
                lines.append(f"\n  Type: {int_type}")
                lines.append(f"  Name: {int_name}")
                if int_desc:
                    if len(int_desc) > 500:
                        int_desc = int_desc[:500] + "..."
                    lines.append(f"  Description: {int_desc}")
                    
                    # Highlight delivery route keywords
                    route_keywords = {
                        'injection': 'INJECTION/INFUSION',
                        'subcutaneous': 'INJECTION/INFUSION', 
                        'intravenous': 'INJECTION/INFUSION',
                        'iv ': 'INJECTION/INFUSION',
                        'i.v.': 'INJECTION/INFUSION',
                        'intramuscular': 'INJECTION/INFUSION',
                        'infusion': 'INJECTION/INFUSION',
                        'topical': 'TOPICAL',
                        'cream': 'TOPICAL',
                        'ointment': 'TOPICAL',
                        'gel': 'TOPICAL',
                        'wound': 'TOPICAL',
                        'dermal': 'TOPICAL',
                        'eye drop': 'TOPICAL',
                        'ophthalmic': 'TOPICAL',
                        'varnish': 'TOPICAL',
                        'strip': 'TOPICAL',
                        'oral': 'ORAL',
                        'tablet': 'ORAL',
                        'capsule': 'ORAL',
                        'drink': 'ORAL',
                        'supplement': 'ORAL',
                        'inhaled': 'OTHER',
                        'intranasal': 'OTHER',
                        'intravitral': 'OTHER',
                        'inhalation': 'OTHER',
                        'implant': 'OTHER'
                    }
                    found_routes = []
                    desc_lower = int_desc.lower()
                    for keyword, route in route_keywords.items():
                        if keyword in desc_lower:
                            found_routes.append(f"{keyword}→{route}")
                    if found_routes:
                        lines.append(f"  *** DELIVERY ROUTE KEYWORDS FOUND: {', '.join(found_routes)} ***")
                    
                    # Highlight antimicrobial keywords if present
                    antimicrobial_keywords = ['antimicrobial', 'antibacterial', 'antifungal', 'antiviral', 
                                             'bactericidal', 'fungicidal', 'defensin', 'cathelicidin',
                                             'membrane disruption', 'host defense', 'kills bacteria']
                    found_amp = [kw for kw in antimicrobial_keywords if kw.lower() in desc_lower]
                    if found_amp:
                        lines.append(f"  *** AMP INDICATORS FOUND: {', '.join(found_amp)} ***")
        else:
            lines.append("**Interventions:** N/A")
        
        # Arm Groups - may contain delivery mode info
        arm_groups = arms_int.get("armGroups", [])
        if arm_groups:
            lines.append("\n**Arm Groups:**")
            for arm in arm_groups[:4]:
                label = arm.get("label", "")
                arm_type = arm.get("type", "")
                arm_desc = arm.get("description", "")
                lines.append(f"  - {label} ({arm_type})")
                if arm_desc:
                    if len(arm_desc) > 300:
                        arm_desc = arm_desc[:300] + "..."
                    lines.append(f"    Description: {arm_desc}")
                    
                    # Check for route keywords in arm description too
                    desc_lower = arm_desc.lower()
                    if any(kw in desc_lower for kw in ['injection', 'subcutaneous', 'intravenous', 'iv ', 'infusion']):
                        lines.append(f"    *** INJECTION/INFUSION route indicated ***")
                    elif any(kw in desc_lower for kw in ['topical', 'cream', 'gel', 'applied', 'varnish', 'strip']):
                        lines.append(f"    *** TOPICAL route indicated ***")
                    elif any(kw in desc_lower for kw in ['oral', 'tablet', 'capsule', 'drink', 'supplement']):
                        lines.append(f"    *** ORAL route indicated ***")
        
        # Design
        design_mod = protocol.get("designModule", {})
        phases = design_mod.get("phases", [])
        lines.append(f"\n**Phases:** {', '.join(phases) if phases else 'N/A'}")
        
        enrollment_info = design_mod.get("enrollmentInfo", {})
        lines.append(f"**Enrollment:** {enrollment_info.get('count', 'N/A')}")
        
        # Outcomes - helpful for outcome determination
        outcomes_mod = protocol.get("outcomesModule", {})
        primary_outcomes = outcomes_mod.get("primaryOutcomes", [])
        if primary_outcomes:
            lines.append("\n**Primary Outcomes (for judging trial success):**")
            for i, outcome in enumerate(primary_outcomes[:3], 1):
                measure = outcome.get("measure", "")
                lines.append(f"  {i}. {measure}")
        
        # References
        refs_mod = protocol.get("referencesModule", {})
        references = refs_mod.get("references", [])
        if references:
            lines.append("\n**References (for Study IDs):**")
            for i, ref in enumerate(references[:5], 1):
                pmid = ref.get("pmid", "")
                ref_type = ref.get("type", "")
                citation = ref.get("citation", "")
                if pmid:
                    lines.append(f"  {i}. PMID: {pmid} ({ref_type})")
                elif citation:
                    lines.append(f"  {i}. {citation[:150]}...")
        
        return "\n".join(lines)
    
    def _format_uniprot_data(self, results: Dict[str, Any]) -> str:
        """
        Format UniProt data with ACTUAL SEQUENCES extracted.
        
        This is critical for sequence annotation - the original code only
        extracted sequence length, not the actual sequence!
        """
        extended_source = results.get("sources", {}).get("extended", {})
        if not extended_source:
            return ""
        
        uniprot = extended_source.get("uniprot", {})
        if not uniprot.get("success"):
            return ""
        
        uniprot_data = uniprot.get("data", {})
        uniprot_results = uniprot_data.get("results", [])
        
        if not uniprot_results:
            return ""
        
        lines = []
        lines.append(f"**Total UniProt Results:** {len(uniprot_results)}")
        lines.append(f"**Query:** {uniprot_data.get('query', 'N/A')}\n")
        
        for i, result in enumerate(uniprot_results[:5], 1):
            lines.append(f"### Protein {i}")
            
            # Accession
            accession = result.get("primaryAccession", "")
            if accession:
                lines.append(f"**Accession:** {accession}")
            
            # Entry name
            entry_name = result.get("uniProtkbId", "")
            if entry_name:
                lines.append(f"**Entry Name:** {entry_name}")
            
            # Protein name
            protein_desc = result.get("proteinDescription", {})
            rec_name = protein_desc.get("recommendedName", {})
            full_name = rec_name.get("fullName", {}).get("value", "")
            if full_name:
                lines.append(f"**Protein Name:** {full_name}")
            
            # Organism
            organism = result.get("organism", {})
            organism_name = organism.get("scientificName", "")
            if organism_name:
                lines.append(f"**Organism:** {organism_name}")
            
            # CRITICAL: Extract actual sequence, not just length!
            sequence_info = result.get("sequence", {})
            seq_length = sequence_info.get("length", 0)
            seq_value = sequence_info.get("value", "")  # The actual amino acid sequence!
            
            if seq_value:
                lines.append(f"\n**[SEQUENCE DATA - USE FOR ANNOTATION]**")
                lines.append(f"**Sequence Length:** {seq_length} amino acids")
                # Include full sequence if short enough, otherwise truncate with note
                if len(seq_value) <= 200:
                    lines.append(f"**Sequence:** {seq_value}")
                else:
                    lines.append(f"**Sequence (first 200 aa):** {seq_value[:200]}...")
                    lines.append(f"**Note:** Full sequence is {seq_length} aa - this may indicate a protein rather than peptide if >100 aa")
            elif seq_length:
                lines.append(f"**Sequence Length:** {seq_length} aa (sequence not retrieved)")
            
            # Function - important for classification
            comments = result.get("comments", [])
            for comment in comments:
                if comment.get("commentType") == "FUNCTION":
                    func_texts = comment.get("texts", [])
                    if func_texts:
                        func_text = func_texts[0].get("value", "")
                        if len(func_text) > 400:
                            func_text = func_text[:400] + "..."
                        lines.append(f"**Function:** {func_text}")
                        
                        # Highlight antimicrobial function
                        if any(kw in func_text.lower() for kw in ['antimicrobial', 'antibacterial', 'antifungal', 'bactericidal']):
                            lines.append(f"*** ANTIMICROBIAL FUNCTION DETECTED - supports AMP classification ***")
                    break
            
            # Keywords - may indicate antimicrobial activity
            result_keywords = result.get("keywords", [])
            if result_keywords:
                keyword_values = [kw.get("name", "") for kw in result_keywords[:10]]
                if keyword_values:
                    lines.append(f"**Keywords:** {', '.join(keyword_values)}")
                    
                    # Check for antimicrobial keywords
                    amp_keywords = [kw for kw in keyword_values if any(
                        term in kw.lower() for term in ['antimicrobial', 'antibiotic', 'bacteriocin', 'defensin']
                    )]
                    if amp_keywords:
                        lines.append(f"*** AMP-RELATED KEYWORDS: {', '.join(amp_keywords)} ***")
            
            lines.append("")
        
        return "\n".join(lines)
    
    def _format_dbaasp_data(self, results: Dict[str, Any]) -> str:
        """Format DBAASP antimicrobial peptide data."""
        extended_source = results.get("sources", {}).get("extended", {})
        dbaasp = extended_source.get("dbaasp", {})

        if not dbaasp.get("success"):
            return ""

        dbaasp_data = dbaasp.get("data", {})
        dbaasp_results = dbaasp_data.get("results", [])

        if not dbaasp_results:
            return ""

        lines = []
        lines.append(f"*** DBAASP MATCH = STRONG AMP INDICATOR ***")
        lines.append(f"**Query:** {dbaasp_data.get('query', 'N/A')}\n")

        for i, result in enumerate(dbaasp_results[:5], 1):
            lines.append(f"**Peptide {i}:**")
            lines.append(f"  Name: {result.get('name', 'N/A')}")
            lines.append(f"  DBAASP ID: {result.get('dbaasp_id', 'N/A')}")

            sequence = result.get('sequence', '')
            if sequence:
                lines.append(f"  **Sequence:** {sequence}")

            activity = result.get('activity', '')
            if activity:
                lines.append(f"  **Antimicrobial Activity:** {activity}")

            targets = result.get('target_organisms', [])
            if targets:
                if isinstance(targets, list):
                    lines.append(f"  **Target Organisms:** {', '.join(str(t) for t in targets)}")
                else:
                    lines.append(f"  **Target Organisms:** {targets}")

            structure = result.get('structure_type', '')
            if structure:
                lines.append(f"  Structure Type: {structure}")

            lines.append("")

        return "\n".join(lines)

    def _format_chembl_data(self, results: Dict[str, Any]) -> str:
        """Format ChEMBL drug molecule data."""
        extended_source = results.get("sources", {}).get("extended", {})
        chembl = extended_source.get("chembl", {})

        if not chembl.get("success"):
            return ""

        chembl_data = chembl.get("data", {})
        chembl_results = chembl_data.get("results", [])

        if not chembl_results:
            return ""

        lines = []
        lines.append(f"**Query:** {chembl_data.get('query', 'N/A')}\n")

        for i, result in enumerate(chembl_results[:5], 1):
            lines.append(f"**Molecule {i}:**")
            lines.append(f"  Name: {result.get('molecule_name', 'N/A')}")
            lines.append(f"  ChEMBL ID: {result.get('chembl_id', 'N/A')}")

            max_phase = result.get('max_phase', 'N/A')
            lines.append(f"  Max Clinical Phase: {max_phase}")

            mol_type = result.get('molecule_type', 'N/A')
            lines.append(f"  Molecule Type: {mol_type}")

            # Highlight protein/peptide types
            if isinstance(mol_type, str) and mol_type.lower() in ('protein', 'peptide'):
                lines.append(f"  *** PEPTIDE/PROTEIN TYPE - supports peptide classification ***")

            helm = result.get('helm_notation', '')
            if helm:
                lines.append(f"  **HELM Notation:** {helm}")

            mechanism = result.get('mechanism_of_action', '')
            if mechanism:
                lines.append(f"  **Mechanism of Action:** {mechanism}")

                # Check for antimicrobial mechanisms
                if any(kw in mechanism.lower() for kw in ['antimicrobial', 'antibacterial', 'antifungal', 'bactericidal']):
                    lines.append(f"  *** ANTIMICROBIAL MECHANISM - supports AMP classification ***")

            lines.append("")

        return "\n".join(lines)

    def _format_rcsb_pdb_data(self, results: Dict[str, Any]) -> str:
        """Format RCSB PDB structure data."""
        extended_source = results.get("sources", {}).get("extended", {})
        pdb = extended_source.get("rcsb_pdb", {})

        if not pdb.get("success"):
            return ""

        pdb_data = pdb.get("data", {})
        pdb_results = pdb_data.get("results", [])

        if not pdb_results:
            return ""

        lines = []
        lines.append(f"**Query:** {pdb_data.get('query', 'N/A')}\n")

        for i, result in enumerate(pdb_results[:5], 1):
            lines.append(f"**Structure {i}:**")
            lines.append(f"  PDB ID: {result.get('pdb_id', 'N/A')}")
            lines.append(f"  Title: {result.get('title', 'N/A')}")
            lines.append(f"  Method: {result.get('method', 'N/A')}")
            lines.append(f"  Resolution: {result.get('resolution', 'N/A')}")

            citation = result.get('citation_title', '')
            if citation:
                lines.append(f"  Citation: {citation}")

            lines.append("")

        return "\n".join(lines)

    def _format_ebi_proteins_data(self, results: Dict[str, Any]) -> str:
        """Format EBI Proteins data."""
        extended_source = results.get("sources", {}).get("extended", {})
        ebi = extended_source.get("ebi_proteins", {})

        if not ebi.get("success"):
            return ""

        ebi_data = ebi.get("data", {})
        ebi_results = ebi_data.get("results", [])

        if not ebi_results:
            return ""

        lines = []
        lines.append(f"**Query:** {ebi_data.get('query', 'N/A')}\n")

        for i, result in enumerate(ebi_results[:5], 1):
            lines.append(f"**Protein {i}:**")
            lines.append(f"  Accession: {result.get('accession', 'N/A')}")
            lines.append(f"  Protein Name: {result.get('protein_name', 'N/A')}")

            gene = result.get('gene', '')
            if gene:
                lines.append(f"  Gene: {gene}")

            organism = result.get('organism', '')
            if organism:
                lines.append(f"  Organism: {organism}")

            sequence = result.get('sequence', '')
            if sequence:
                if len(sequence) > 200:
                    lines.append(f"  **Sequence:** {sequence[:200]}... (truncated, {len(sequence)} aa)")
                else:
                    lines.append(f"  **Sequence:** {sequence}")

            # Highlight antimicrobial function keywords
            protein_name = result.get('protein_name', '').lower()
            if any(kw in protein_name for kw in ['antimicrobial', 'defensin', 'cathelicidin', 'bacteriocin']):
                lines.append(f"  *** ANTIMICROBIAL PROTEIN - supports AMP classification ***")

            # Show clinical features
            features = result.get('features', [])
            if features:
                clinical_features = [f for f in features if isinstance(f, dict) and
                                     f.get('type', '').lower() in ('variant', 'mutagenesis', 'active site', 'binding site')]
                if clinical_features:
                    lines.append(f"  Clinical Features:")
                    for feat in clinical_features[:3]:
                        lines.append(f"    - {feat.get('type', '')}: {feat.get('description', '')}")

            lines.append("")

        return "\n".join(lines)

    def _format_extended_data(self, results: Dict[str, Any]) -> str:
        """Format extended API search data (DuckDuckGo, SERP, Scholar, OpenFDA)."""
        extended_source = results.get("sources", {}).get("extended", {})
        
        if not extended_source:
            return ""
        
        lines = []
        has_data = False
        
        # DRAMP Database - critical for AMP identification
        dramp = extended_source.get("dramp", {})
        if dramp.get("success"):
            has_data = True
            dramp_data = dramp.get("data", {})
            dramp_results = dramp_data.get("results", [])
            
            lines.append("### DRAMP Antimicrobial Peptide Database")
            lines.append(f"*** DRAMP MATCH = STRONG AMP INDICATOR ***")
            lines.append(f"**Query:** {dramp_data.get('query', 'N/A')}\n")
            
            for i, result in enumerate(dramp_results[:5], 1):
                lines.append(f"**AMP {i}:**")
                lines.append(f"  Name: {result.get('name', 'N/A')}")
                lines.append(f"  DRAMP ID: {result.get('dramp_id', 'N/A')}")
                activity = result.get('activity', '')
                if activity:
                    lines.append(f"  **Antimicrobial Activity:** {activity}")
                sequence = result.get('sequence', '')
                if sequence:
                    lines.append(f"  **Sequence:** {sequence}")
                lines.append("")
        
        # DuckDuckGo Web Search
        ddg = extended_source.get("duckduckgo", {})
        if ddg.get("success"):
            has_data = True
            ddg_data = ddg.get("data", {})
            ddg_results = ddg_data.get("results", [])
            
            lines.append("### Web Search Results")
            lines.append(f"**Query:** {ddg_data.get('query', 'N/A')}\n")
            
            for i, result in enumerate(ddg_results[:5], 1):
                lines.append(f"**Result {i}:**")
                lines.append(f"  Title: {result.get('title', 'N/A')}")
                snippet = result.get('snippet', '')
                if snippet:
                    if len(snippet) > 300:
                        snippet = snippet[:300] + "..."
                    lines.append(f"  Snippet: {snippet}")
                lines.append("")
        
        # OpenFDA Drug Database
        openfda = extended_source.get("openfda", {})
        if openfda.get("success"):
            has_data = True
            fda_data = openfda.get("data", {})
            fda_results = fda_data.get("results", [])
            
            lines.append("\n### FDA Drug Database")
            
            for i, result in enumerate(fda_results[:3], 1):
                lines.append(f"**Drug {i}:**")
                
                openfda_info = result.get("openfda", {})
                
                brand_names = openfda_info.get("brand_name", [])
                if brand_names:
                    lines.append(f"  Brand Name(s): {', '.join(brand_names[:3])}")
                
                generic_names = openfda_info.get("generic_name", [])
                if generic_names:
                    lines.append(f"  Generic Name(s): {', '.join(generic_names[:3])}")
                
                # Route - IMPORTANT for Delivery Mode
                routes = openfda_info.get("route", [])
                if routes:
                    route_str = ', '.join(routes[:3])
                    lines.append(f"  *** ROUTE OF ADMINISTRATION: {route_str} ***")
                    
                    # Map FDA routes to our categories
                    route_lower = route_str.lower()
                    if any(r in route_lower for r in ['intravenous', 'subcutaneous', 'intramuscular', 'injection']):
                        lines.append(f"  → Indicates: Injection/Infusion")
                    elif any(r in route_lower for r in ['topical', 'cream', 'gel', 'applied', 'varnish', 'strip']):
                        lines.append(f"  → Indicates: Topical")
                    elif any(r in route_lower for r in ['oral', 'tablet', 'capsule', 'drink', 'supplement']):
                        lines.append(f"  → Indicates: Oral")
                    else:
                        lines.append(f"  → Indicates: Other")
                
                # Product type
                product_types = openfda_info.get("product_type", [])
                if product_types:
                    lines.append(f"  Product Type: {', '.join(product_types)}")
                
                # Pharmacologic class - helpful for classification
                pharm_class = openfda_info.get("pharm_class_epc", [])
                if pharm_class:
                    lines.append(f"  Pharmacologic Class: {', '.join(pharm_class[:3])}")
                
                lines.append("")
        
        # Google Scholar
        scholar = extended_source.get("scholar", {})
        if scholar.get("success"):
            has_data = True
            scholar_data = scholar.get("data", {})
            scholar_results = scholar_data.get("results", [])
            
            lines.append("\n### Academic Literature (Google Scholar)")
            
            for i, result in enumerate(scholar_results[:3], 1):
                lines.append(f"**Paper {i}:**")
                lines.append(f"  Title: {result.get('title', 'N/A')}")
                snippet = result.get('snippet', '')
                if snippet:
                    if len(snippet) > 300:
                        snippet = snippet[:300] + "..."
                    lines.append(f"  Snippet: {snippet}")
                lines.append("")
        
        if not has_data:
            return ""
        
        return "\n".join(lines)
    
    def _format_pubmed_data(self, results: Dict[str, Any]) -> str:
        """Format PubMed data with focus on relevant content."""
        pubmed_source = results.get("sources", {}).get("pubmed", {})
        
        if not pubmed_source.get("success"):
            return ""
        
        pubmed_data = pubmed_source.get("data", {})
        articles = pubmed_data.get("articles", [])
        
        if not articles:
            return ""
        
        lines = []
        lines.append(f"**Total Articles Found:** {pubmed_data.get('total_found', 0)}")
        lines.append(f"**Search Strategy:** {pubmed_data.get('search_strategy', 'N/A')}\n")
        
        for i, article in enumerate(articles[:4], 1):
            lines.append(f"### Article {i}")
            lines.append(f"**PMID:** {article.get('pmid', 'N/A')}")
            lines.append(f"**Title:** {article.get('title', 'N/A')}")
            lines.append(f"**Journal:** {article.get('journal', 'N/A')}")
            lines.append(f"**Year:** {article.get('year', 'N/A')}")
            
            abstract = article.get("abstract", "")
            if abstract:
                if len(abstract) > 600:
                    abstract = abstract[:600] + "..."
                lines.append(f"**Abstract:** {abstract}")
                
                # Check for antimicrobial content
                antimicrobial_terms = ['antimicrobial', 'antibacterial', 'antifungal', 'bactericidal', 
                                       'MIC', 'minimum inhibitory', 'kills bacteria']
                found_terms = [term for term in antimicrobial_terms if term.lower() in abstract.lower()]
                if found_terms:
                    lines.append(f"*** ANTIMICROBIAL CONTENT: {', '.join(found_terms)} ***")
            
            lines.append("")
        
        return "\n".join(lines)
    
    def _format_pmc_data(self, results: Dict[str, Any]) -> str:
        """Format PMC data."""
        pmc_source = results.get("sources", {}).get("pmc", {})
        
        if not pmc_source.get("success"):
            return ""
        
        pmc_data = pmc_source.get("data", {})
        articles = pmc_data.get("articles", [])
        
        if not articles:
            return ""
        
        lines = []
        lines.append(f"**Total PMC Articles Found:** {pmc_data.get('total_found', 0)}\n")
        
        for i, article in enumerate(articles[:3], 1):
            lines.append(f"### PMC Article {i}")
            lines.append(f"**PMCID:** {article.get('pmcid', 'N/A')}")
            lines.append(f"**PMID:** {article.get('pmid', 'N/A')}")
            lines.append(f"**Title:** {article.get('title', 'N/A')}")
            
            abstract = article.get("abstract", "")
            if abstract:
                if len(abstract) > 500:
                    abstract = abstract[:500] + "..."
                lines.append(f"**Abstract:** {abstract}")
            
            lines.append("")
        
        return "\n".join(lines)
    
    def _format_bioc_data(self, results: Dict[str, Any]) -> str:
        """Format BioC data with key annotations."""
        bioc_source = results.get("sources", {}).get("pmc_bioc", {})
        
        if not bioc_source.get("success"):
            return ""
        
        bioc_data = bioc_source.get("data", {})
        articles = bioc_data.get("articles", [])
        
        if not articles:
            return ""
        
        lines = []
        lines.append(f"**Total BioC Articles:** {bioc_data.get('total_fetched', 0)}/{bioc_data.get('total_found', 0)}\n")
        
        for i, article in enumerate(articles[:2], 1):
            lines.append(f"### BioC Article {i}")
            lines.append(f"**ID:** {article.get('pmid', 'N/A')}")
            
            bioc_content = article.get("bioc_data", {})
            documents = bioc_content.get("documents", [])
            
            if documents:
                doc = documents[0]
                passages = doc.get("passages", [])
                
                if passages:
                    lines.append("\n**Key Content:**")
                    
                    for j, passage in enumerate(passages[:2], 1):
                        passage_type = passage.get("infons", {}).get("type", "text")
                        text = passage.get("text", "")
                        
                        if text and len(text) > 400:
                            text = text[:400] + "..."
                        
                        if text:
                            lines.append(f"\n*{passage_type.title()}:*")
                            lines.append(text)
                        
                        # Show annotations - may contain sequence info
                        annotations = passage.get("annotations", [])
                        if annotations:
                            relevant_anns = []
                            for ann in annotations[:5]:
                                ann_type = ann.get("infons", {}).get("type", "")
                                ann_text = ann.get("text", "")
                                if ann_type and ann_text:
                                    relevant_anns.append(f"{ann_type}: {ann_text}")
                            if relevant_anns:
                                lines.append(f"\n*Annotations:* {'; '.join(relevant_anns)}")
            
            lines.append("")
        
        return "\n".join(lines)
    
    def generate_rag_query_prompt(
        self,
        query: str,
        search_results: Dict[str, Any]
    ) -> str:
        """Generate RAG-style prompt for answering queries."""
        sections = []
        
        sections.append("# Clinical Trial Research Query")
        sections.append(f"\n**User Question:** {query}\n")
        sections.append("## Available Data\n")
        
        ct_data = self._format_clinical_trials_data(search_results)
        if ct_data:
            sections.append("### ClinicalTrials.gov")
            sections.append(ct_data)
        
        uniprot_data = self._format_uniprot_data(search_results)
        if uniprot_data:
            sections.append("\n### UniProt Protein Data")
            sections.append(uniprot_data)

        dbaasp_data = self._format_dbaasp_data(search_results)
        if dbaasp_data:
            sections.append("\n### DBAASP Antimicrobial Peptides")
            sections.append(dbaasp_data)

        chembl_data = self._format_chembl_data(search_results)
        if chembl_data:
            sections.append("\n### ChEMBL Drug Data")
            sections.append(chembl_data)

        pdb_data = self._format_rcsb_pdb_data(search_results)
        if pdb_data:
            sections.append("\n### RCSB PDB Structures")
            sections.append(pdb_data)

        ebi_data = self._format_ebi_proteins_data(search_results)
        if ebi_data:
            sections.append("\n### EBI Proteins Data")
            sections.append(ebi_data)

        pubmed_data = self._format_pubmed_data(search_results)
        if pubmed_data:
            sections.append("\n### PubMed Literature")
            sections.append(pubmed_data)

        pmc_data = self._format_pmc_data(search_results)
        if pmc_data:
            sections.append("\n### PMC Articles")
            sections.append(pmc_data)

        bioc_data = self._format_bioc_data(search_results)
        if bioc_data:
            sections.append("\n### BioC Annotations")
            sections.append(bioc_data)

        extended_data = self._format_extended_data(search_results)
        if extended_data:
            sections.append("\n### Extended Search Results")
            sections.append(extended_data)
        
        sections.append("\n## Task")
        sections.append("""
Based on the clinical trial data and literature provided above, answer the user's question.

Guidelines:
- Provide a clear, evidence-based answer
- Cite specific data points when possible
- If information is missing, state that clearly
- Use professional medical/scientific language
- Organize your response logically

Your answer:
""")
        
        return "\n".join(sections)
    
    def save_prompt(self, prompt: str, output_path: Path):
        """Save generated prompt to file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(prompt, encoding="utf-8")


# Backwards compatibility alias
PromptGenerator = ImprovedPromptGenerator