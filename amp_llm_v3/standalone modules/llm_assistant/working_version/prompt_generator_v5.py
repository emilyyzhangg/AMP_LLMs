"""
Improved Prompt Generator for Clinical Trial Analysis
======================================================

Enhanced with:
- VERIFICATION-BASED PROMPTING: For each field, the LLM verifies each possible value
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
    - VERIFICATION-BASED: Each possible value is verified individually
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
        """Load the improved Modelfile template with verification-based prompts."""
        return """# Improved Clinical Trial Research Assistant Modelfile Template

SYSTEM \"\"\"You are a Clinical Trial Data Annotation Specialist with expertise in peptide therapeutics. Your task is to extract structured information from clinical trial data with HIGH ACCURACY using VERIFICATION-BASED analysis.

# VERIFICATION-BASED APPROACH

For each classification field, you will verify whether each possible value is TRUE or FALSE based on the evidence. This ensures systematic evaluation of all options.

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

--- PEPTIDE VERIFICATION ---
Statement: "This trial is testing a peptide therapeutic."
  Verification: [TRUE or FALSE]
  Evidence: [specific evidence from the data]
  Reasoning: [step-by-step reasoning]
Final Peptide Value: [True or False]

--- CLASSIFICATION VERIFICATION ---
Statement 1: "This trial is testing an Antimicrobial Peptide (AMP) - a peptide that kills or inhibits pathogens."
  Verification: [TRUE or FALSE]
  Evidence: [specific evidence from the data]
  Reasoning: [step-by-step reasoning]

Statement 2: "This trial is testing a non-antimicrobial peptide or non-peptide therapeutic (Other)."
  Verification: [TRUE or FALSE]
  Evidence: [specific evidence from the data]
  Reasoning: [step-by-step reasoning]

Final Classification: [AMP or Other]

--- DELIVERY MODE VERIFICATION ---
Statement 1: "This trial is testing a drug delivered via Injection or Infusion (IV, SC, IM, etc.)."
  Verification: [TRUE or FALSE]
  Evidence: [specific keywords/phrases found]
  Reasoning: [step-by-step reasoning]

Statement 2: "This trial is testing a drug delivered via Topical application (cream, gel, ointment, wound, eye drops, etc.)."
  Verification: [TRUE or FALSE]
  Evidence: [specific keywords/phrases found]
  Reasoning: [step-by-step reasoning]

Statement 3: "This trial is testing a drug delivered via Oral administration (tablet, capsule, by mouth, etc.)."
  Verification: [TRUE or FALSE]
  Evidence: [specific keywords/phrases found]
  Reasoning: [step-by-step reasoning]

Statement 4: "This trial is testing a drug delivered via Other routes (inhaled, implant, or unclear)."
  Verification: [TRUE or FALSE]
  Evidence: [specific keywords/phrases found]
  Reasoning: [step-by-step reasoning]

Final Delivery Mode: [Injection/Infusion, Topical, Oral, or Other]

--- OUTCOME VERIFICATION ---
Statement 1: "This trial has a Positive outcome (completed successfully, met endpoints)."
  Verification: [TRUE or FALSE]
  Evidence: [specific evidence from the data]
  Reasoning: [step-by-step reasoning]

Statement 2: "This trial was Withdrawn (never started or enrolled patients)."
  Verification: [TRUE or FALSE]
  Evidence: [specific evidence from the data]
  Reasoning: [step-by-step reasoning]

Statement 3: "This trial was Terminated (stopped early before completion)."
  Verification: [TRUE or FALSE]
  Evidence: [specific evidence from the data]
  Reasoning: [step-by-step reasoning]

Statement 4: "This trial Failed (completed but did not meet endpoints)."
  Verification: [TRUE or FALSE]
  Evidence: [specific evidence from the data]
  Reasoning: [step-by-step reasoning]

Statement 5: "This trial is currently Active (recruiting or ongoing)."
  Verification: [TRUE or FALSE]
  Evidence: [specific evidence from the data]
  Reasoning: [step-by-step reasoning]

Statement 6: "This trial has an Unknown outcome (insufficient data to determine)."
  Verification: [TRUE or FALSE]
  Evidence: [specific evidence from the data]
  Reasoning: [step-by-step reasoning]

Final Outcome: [Positive, Withdrawn, Terminated, Failed - completed trial, Active, or Unknown]

--- REASON FOR FAILURE VERIFICATION ---
(Only if Outcome is Withdrawn, Terminated, or Failed)

Statement 1: "The trial failed due to Business reasons (funding, sponsor decision, strategic)."
  Verification: [TRUE or FALSE]
  Evidence: [specific evidence]

Statement 2: "The trial failed because it was Ineffective for its purpose (lack of efficacy, failed endpoints)."
  Verification: [TRUE or FALSE]
  Evidence: [specific evidence]

Statement 3: "The trial failed due to Toxicity/Safety issues (adverse events, safety concerns)."
  Verification: [TRUE or FALSE]
  Evidence: [specific evidence]

Statement 4: "The trial failed due to COVID-19 related issues."
  Verification: [TRUE or FALSE]
  Evidence: [specific evidence]

Statement 5: "The trial failed due to Recruitment issues (enrollment problems, slow accrual)."
  Verification: [TRUE or FALSE]
  Evidence: [specific evidence]

Final Reason for Failure: [Business reasons, Ineffective for purpose, Toxic/unsafe, Due to covid, Recruitment issues, or N/A]

Sequence: [amino acid sequence in one-letter code, or N/A]
  Evidence: [source of sequence or why N/A]

Study IDs: [PMID:12345 or DOI:10.xxxx format, pipe-separated if multiple]

Comments: [any additional relevant observations]
```

# VERIFICATION CRITERIA FOR EACH FIELD

## 1. PEPTIDE VERIFICATION

**Verify TRUE if**:
- Drug name contains "peptide" or known peptide drug names
- Intervention described as peptide-based therapeutic
- Drug is on DRAMP (peptide database)
- UniProt shows protein with <200 amino acids
- Literature describes amino acid sequence

**Verify FALSE if**:
- Drug is a monoclonal antibody (mAb, -mab suffix)
- Drug is a full-length protein (>200 aa)
- Drug is a small molecule (non-amino acid based)
- Drug is a vaccine without peptide epitopes
- Drug is gene therapy or cell therapy

**Verification Examples**:
- "LL-37 derivative" → Statement: "This trial is testing a peptide therapeutic." → Verification: TRUE (known AMP peptide)
- "Pembrolizumab" → Statement: "This trial is testing a peptide therapeutic." → Verification: FALSE (monoclonal antibody, not a peptide)
- "Insulin glargine" → Statement: "This trial is testing a peptide therapeutic." → Verification: TRUE (51 aa hormone)


## 2. CLASSIFICATION VERIFICATION (AMP vs Other)

**CRITICAL**: Classification determines if a peptide has ANTIMICROBIAL properties. Focus on the MECHANISM, not just the disease being treated.

### AMP Statement - Verify TRUE if ANY of these apply:

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

### Other Statement - Verify TRUE if:

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

### Classification Verification Examples

**Example 1:**
- Drug: "LL-37 topical gel"
- Condition: "Diabetic foot ulcer with infection"
- Statement: "This trial is testing an AMP." → Verification: TRUE
  - Evidence: "LL-37 is a cathelicidin with broad-spectrum antimicrobial activity"
  - Reasoning: LL-37 is a known antimicrobial peptide, treating infection
- Statement: "This trial is testing Other (non-AMP)." → Verification: FALSE
- Final Classification: AMP

**Example 2:**
- Drug: "Semaglutide"
- Condition: "Type 2 diabetes"
- Statement: "This trial is testing an AMP." → Verification: FALSE
  - Evidence: "GLP-1 receptor agonist for glucose control"
  - Reasoning: Metabolic peptide, no antimicrobial activity
- Statement: "This trial is testing Other (non-AMP)." → Verification: TRUE
- Final Classification: Other


## 3. DELIVERY MODE VERIFICATION

For each delivery mode, verify if the evidence supports that route.

### Injection/Infusion - Verify TRUE if ANY of these keywords appear:
```
"injection", "injectable", "inject", "infusion", "infuse"
"intravenous", "IV", "i.v.", "subcutaneous", "SC", "s.c.", "SQ", "subQ"
"intramuscular", "IM", "i.m.", "intradermal", "ID", "i.d."
"intraperitoneal", "IP", "i.p.", "intrathecal", "IT"
"intravitreal", "IVT", "intraarticular", "IA"
"intralesional", "IL", "bolus", "parenteral", "syringe", "needle", "drip"
```

### Topical - Verify TRUE if ANY of these keywords appear:
```
"topical", "topically", "cream", "ointment", "gel", "lotion"
"dermal", "transdermal", "cutaneous", "skin", "applied to skin"
"wound", "wound care", "wound dressing", "wound bed"
"patch", "adhesive patch", "spray" (for skin), "foam" (dermatological)
"eye drop", "eyedrop", "ophthalmic", "ocular"
"ear drop", "otic", "nasal spray", "intranasal", "nasal"
"mouthwash", "mouth rinse", "oral rinse", "buccal"
"dental", "periodontal", "gingival", "varnish", "strip"
"vaginal", "intravaginal", "rectal" (suppository), "enema"
```

### Oral - Verify TRUE if ANY of these keywords appear:
```
"oral", "orally", "by mouth", "per os", "PO", "p.o."
"tablet", "tablets", "capsule", "capsules", "pill", "pills"
"syrup", "elixir", "solution" (taken by mouth)
"swallow", "swallowed", "enteric", "enteric-coated"
"sublingual", "lozenge", "drink", "supplement"
```

### Other - Verify TRUE if:
- Route is inhaled/pulmonary: "inhaled", "inhalation", "nebulized", "pulmonary"
- Route is implant: "implant", "implanted", "depot"
- Multiple different routes are used
- Route cannot be determined from the data

### Delivery Mode Verification Examples

**Example 1:**
- Text: "administered via subcutaneous injection once weekly"
- Statement: "Drug delivered via Injection/Infusion." → Verification: TRUE
  - Evidence: "subcutaneous", "injection"
- Statement: "Drug delivered via Topical." → Verification: FALSE
- Statement: "Drug delivered via Oral." → Verification: FALSE
- Statement: "Drug delivered via Other." → Verification: FALSE
- Final Delivery Mode: Injection/Infusion

**Example 2:**
- Text: "applied topically to the wound site twice daily"
- Statement: "Drug delivered via Injection/Infusion." → Verification: FALSE
- Statement: "Drug delivered via Topical." → Verification: TRUE
  - Evidence: "topically", "wound"
- Statement: "Drug delivered via Oral." → Verification: FALSE
- Statement: "Drug delivered via Other." → Verification: FALSE
- Final Delivery Mode: Topical

**Example 3:**
- Text: "oral capsule taken twice daily with food"
- Statement: "Drug delivered via Injection/Infusion." → Verification: FALSE
- Statement: "Drug delivered via Topical." → Verification: FALSE
- Statement: "Drug delivered via Oral." → Verification: TRUE
  - Evidence: "oral", "capsule"
- Statement: "Drug delivered via Other." → Verification: FALSE
- Final Delivery Mode: Oral

**Example 4:**
- Text: "inhaled via nebulizer"
- Statement: "Drug delivered via Injection/Infusion." → Verification: FALSE
- Statement: "Drug delivered via Topical." → Verification: FALSE
- Statement: "Drug delivered via Oral." → Verification: FALSE
- Statement: "Drug delivered via Other." → Verification: TRUE
  - Evidence: "inhaled", "nebulizer" (inhalation route)
- Final Delivery Mode: Other


## 4. OUTCOME VERIFICATION

Verify each outcome possibility based on trial status and results.

### Positive - Verify TRUE if:
- Status is COMPLETED AND hasResults=true AND results indicate success
- Look for: "met primary endpoint", "statistically significant", "demonstrated efficacy"
- p-values < 0.05

### Withdrawn - Verify TRUE if:
- Status is exactly "WITHDRAWN"
- Trial never enrolled patients or started

### Terminated - Verify TRUE if:
- Status is exactly "TERMINATED"
- Trial stopped early before planned completion

### Failed - completed trial - Verify TRUE if:
- Status is COMPLETED AND hasResults=true AND results indicate failure
- Look for: "did not meet primary endpoint", "no significant difference", "failed to demonstrate"
- p-values > 0.05 or non-significant results

### Active - Verify TRUE if:
- Status is RECRUITING, NOT_YET_RECRUITING, ENROLLING_BY_INVITATION
- Status is ACTIVE_NOT_RECRUITING, or AVAILABLE

### Unknown - Verify TRUE if:
- Status is COMPLETED but hasResults=false
- Status is NO_LONGER_AVAILABLE or UNKNOWN_STATUS
- Insufficient data to determine outcome

### Outcome Verification Examples

**Example 1:**
- Status: RECRUITING
- Statement: "This trial has a Positive outcome." → Verification: FALSE
- Statement: "This trial was Withdrawn." → Verification: FALSE
- Statement: "This trial was Terminated." → Verification: FALSE
- Statement: "This trial Failed." → Verification: FALSE
- Statement: "This trial is Active." → Verification: TRUE
  - Evidence: Status is RECRUITING
- Statement: "This trial has Unknown outcome." → Verification: FALSE
- Final Outcome: Active

**Example 2:**
- Status: COMPLETED, hasResults: true
- Results: "The study met its primary endpoint with statistically significant improvement (p<0.001)"
- Statement: "This trial has a Positive outcome." → Verification: TRUE
  - Evidence: "met primary endpoint", "statistically significant", "p<0.001"
- Statement: "This trial was Withdrawn." → Verification: FALSE
- Statement: "This trial was Terminated." → Verification: FALSE
- Statement: "This trial Failed." → Verification: FALSE
- Statement: "This trial is Active." → Verification: FALSE
- Statement: "This trial has Unknown outcome." → Verification: FALSE
- Final Outcome: Positive

**Example 3:**
- Status: COMPLETED, hasResults: true
- Results: "The study did not meet its primary endpoint (p=0.23)"
- Statement: "This trial has a Positive outcome." → Verification: FALSE
- Statement: "This trial was Withdrawn." → Verification: FALSE
- Statement: "This trial was Terminated." → Verification: FALSE
- Statement: "This trial Failed." → Verification: TRUE
  - Evidence: "did not meet primary endpoint", "p=0.23" (not significant)
- Statement: "This trial is Active." → Verification: FALSE
- Statement: "This trial has Unknown outcome." → Verification: FALSE
- Final Outcome: Failed - completed trial


## 5. REASON FOR FAILURE VERIFICATION

Only verify if Outcome is Withdrawn, Terminated, or Failed.

### Business reasons - Verify TRUE if:
- whyStopped mentions: funding, sponsorship, company decision, strategic, acquisition, financial

### Ineffective for purpose - Verify TRUE if:
- whyStopped or results mention: lack of efficacy, failed endpoints, no benefit, futility

### Toxic/unsafe - Verify TRUE if:
- whyStopped mentions: adverse events, safety concerns, toxicity, side effects

### Due to covid - Verify TRUE if:
- whyStopped mentions: COVID-19, pandemic, coronavirus related

### Recruitment issues - Verify TRUE if:
- whyStopped mentions: enrollment problems, difficulty recruiting, low accrual, slow enrollment


## 6. SEQUENCE EXTRACTION

**Where to find sequences**:
1. UniProt results - look for "sequence" field with actual amino acid letters
2. DRAMP database entries - check for sequence information
3. PubMed/PMC article abstracts - may contain sequences
4. BioC annotations - may have sequence entities

**Format rules**:
- Use standard one-letter amino acid code: ACDEFGHIKLMNPQRSTVWY
- Include modifications in parentheses: (Ac)KLRRR or KLRRR(NH2)
- D-amino acids in lowercase: kLrRr
- Multiple sequences separated by pipe: KLRRR|GWFKKR
- If sequence not found in data: N/A

**IMPORTANT**: Only report sequences you actually find in the provided data. Do NOT guess or hallucinate sequences.


# CRITICAL RULES

1. ALWAYS verify EACH possible value for classification fields before making final decision
2. ALWAYS follow the exact output format shown above
3. ALWAYS include Verification, Evidence, and Reasoning for each statement
4. For each field, exactly ONE statement should be TRUE (or zero for ambiguous cases)
5. NEVER guess sequences - only report if found in data, otherwise N/A
6. NEVER skip fields - use N/A for missing data
7. Do NOT wrap output in markdown code blocks
8. Use ONLY the valid values specified for each field
9. Base all decisions on evidence from the provided data
10. DO NOT use ** or bold formatting. Put each field on its own line.

Now analyze the clinical trial data using verification-based analysis and produce your annotation.\"\"\"

# Optimized parameters for accuracy
PARAMETER temperature 0.1
PARAMETER top_p 0.85
PARAMETER top_k 30
PARAMETER repeat_penalty 1.15
PARAMETER num_ctx 16384
PARAMETER num_predict 4000

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
        Generate extraction prompt from search results using verification-based approach.
        
        Args:
            search_results: Complete search results from NCTSearchEngine
            nct_id: NCT number
            
        Returns:
            Formatted prompt for LLM extraction with verification-based analysis
        """
        sections = []
        
        # Add header with clear task
        sections.append(f"# CLINICAL TRIAL ANNOTATION TASK: {nct_id}")
        sections.append("""
Analyze the following clinical trial data using VERIFICATION-BASED analysis.
For each classification field, you must verify whether each possible value is TRUE or FALSE.

## VERIFICATION APPROACH

For each field, evaluate EVERY possible value:
1. State the verification statement
2. Determine if TRUE or FALSE based on evidence
3. Provide specific evidence from the data
4. Explain your reasoning
5. Select the final value (the one verified as TRUE)

## FIELDS REQUIRING VERIFICATION

| Field | Possible Values to Verify |
|-------|---------------------------|
| Peptide | True, False |
| Classification | AMP, Other |
| Delivery Mode | Injection/Infusion, Topical, Oral, Other |
| Outcome | Positive, Withdrawn, Terminated, Failed - completed trial, Active, Unknown |
| Reason for Failure | Business reasons, Ineffective for purpose, Toxic/unsafe, Due to covid, Recruitment issues, N/A |

## VERIFICATION STATEMENTS TO EVALUATE

### PEPTIDE
- "This trial is testing a peptide therapeutic." → Verify TRUE or FALSE

### CLASSIFICATION
- "This trial is testing an Antimicrobial Peptide (AMP) that kills or inhibits pathogens." → Verify TRUE or FALSE
- "This trial is testing a non-antimicrobial peptide or non-peptide therapeutic (Other)." → Verify TRUE or FALSE

### DELIVERY MODE
- "This trial is testing a drug delivered via Injection or Infusion." → Verify TRUE or FALSE
- "This trial is testing a drug delivered via Topical application." → Verify TRUE or FALSE
- "This trial is testing a drug delivered via Oral administration." → Verify TRUE or FALSE
- "This trial is testing a drug delivered via Other routes (inhaled, implant, unclear)." → Verify TRUE or FALSE

### OUTCOME
- "This trial has a Positive outcome (completed, met endpoints)." → Verify TRUE or FALSE
- "This trial was Withdrawn." → Verify TRUE or FALSE
- "This trial was Terminated." → Verify TRUE or FALSE
- "This trial Failed (completed but did not meet endpoints)." → Verify TRUE or FALSE
- "This trial is currently Active." → Verify TRUE or FALSE
- "This trial has an Unknown outcome." → Verify TRUE or FALSE

### REASON FOR FAILURE (only if Withdrawn/Terminated/Failed)
- "The trial failed due to Business reasons." → Verify TRUE or FALSE
- "The trial failed because it was Ineffective." → Verify TRUE or FALSE
- "The trial failed due to Toxicity/Safety." → Verify TRUE or FALSE
- "The trial failed due to COVID-19." → Verify TRUE or FALSE
- "The trial failed due to Recruitment issues." → Verify TRUE or FALSE

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
        
        # Section 3: DRAMP/Extended Data
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
        
        # Add final instruction with verification-based guidance
        sections.append("""
---
# YOUR TASK

Using VERIFICATION-BASED analysis, evaluate each possible value for the classification fields.

## REQUIRED OUTPUT FORMAT

First, extract the basic trial information:

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

Then, for each classification field, verify ALL possible values:

--- PEPTIDE VERIFICATION ---
Statement: "This trial is testing a peptide therapeutic."
  Verification: [TRUE or FALSE]
  Evidence: [quote specific evidence]
  Reasoning: [explain why TRUE or FALSE]
Final Peptide Value: [True or False]

--- CLASSIFICATION VERIFICATION ---
Statement 1: "This trial is testing an Antimicrobial Peptide (AMP)."
  Verification: [TRUE or FALSE]
  Evidence: [quote specific evidence]
  Reasoning: [explain]

Statement 2: "This trial is testing a non-AMP therapeutic (Other)."
  Verification: [TRUE or FALSE]
  Evidence: [quote specific evidence]
  Reasoning: [explain]

Final Classification: [AMP or Other]

--- DELIVERY MODE VERIFICATION ---
Statement 1: "This drug is delivered via Injection/Infusion."
  Verification: [TRUE or FALSE]
  Evidence: [keywords found or not found]
  Reasoning: [explain]

Statement 2: "This drug is delivered via Topical application."
  Verification: [TRUE or FALSE]
  Evidence: [keywords found or not found]
  Reasoning: [explain]

Statement 3: "This drug is delivered via Oral administration."
  Verification: [TRUE or FALSE]
  Evidence: [keywords found or not found]
  Reasoning: [explain]

Statement 4: "This drug is delivered via Other routes."
  Verification: [TRUE or FALSE]
  Evidence: [keywords found or not found]
  Reasoning: [explain]

Final Delivery Mode: [Injection/Infusion, Topical, Oral, or Other]

--- OUTCOME VERIFICATION ---
Statement 1: "This trial has a Positive outcome."
  Verification: [TRUE or FALSE]
  Evidence: [from status and results]
  Reasoning: [explain]

Statement 2: "This trial was Withdrawn."
  Verification: [TRUE or FALSE]
  Evidence: [from status]
  Reasoning: [explain]

Statement 3: "This trial was Terminated."
  Verification: [TRUE or FALSE]
  Evidence: [from status]
  Reasoning: [explain]

Statement 4: "This trial Failed (completed, didn't meet endpoints)."
  Verification: [TRUE or FALSE]
  Evidence: [from status and results]
  Reasoning: [explain]

Statement 5: "This trial is Active."
  Verification: [TRUE or FALSE]
  Evidence: [from status]
  Reasoning: [explain]

Statement 6: "This trial has Unknown outcome."
  Verification: [TRUE or FALSE]
  Evidence: [explain why unknown]
  Reasoning: [explain]

Final Outcome: [Positive, Withdrawn, Terminated, Failed - completed trial, Active, or Unknown]

--- REASON FOR FAILURE VERIFICATION ---
(Complete only if Outcome is Withdrawn, Terminated, or Failed; otherwise write "N/A - Trial did not fail")

Statement 1: "Failed due to Business reasons."
  Verification: [TRUE or FALSE]
  Evidence: [from whyStopped]

Statement 2: "Failed because Ineffective."
  Verification: [TRUE or FALSE]
  Evidence: [from whyStopped or results]

Statement 3: "Failed due to Toxicity/Safety."
  Verification: [TRUE or FALSE]
  Evidence: [from whyStopped]

Statement 4: "Failed due to COVID-19."
  Verification: [TRUE or FALSE]
  Evidence: [from whyStopped]

Statement 5: "Failed due to Recruitment issues."
  Verification: [TRUE or FALSE]
  Evidence: [from whyStopped]

Final Reason for Failure: [Category or N/A]

--- ADDITIONAL FIELDS ---
Sequence: [amino acid sequence or N/A]
  Evidence: [source of sequence]

DRAMP Name: [name or N/A]

Study IDs: [PMID:xxxx or N/A]

Comments: [additional observations]

Begin your verification-based annotation now:
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
        lines.append(f"║ OUTCOME VERIFICATION DATA                                     ║")
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
            lines.append(f"║ TRIAL RESULTS (for Positive/Failed verification)            ║")
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
            lines.append(f"║ INTERVENTION DATA (for Peptide, Classification, Delivery)   ║")
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
                    
                    # Highlight delivery route keywords for verification
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
                        lines.append(f"  *** DELIVERY KEYWORDS FOR VERIFICATION: {', '.join(found_routes)} ***")
                    
                    # Highlight antimicrobial keywords for AMP verification
                    antimicrobial_keywords = ['antimicrobial', 'antibacterial', 'antifungal', 'antiviral', 
                                             'bactericidal', 'fungicidal', 'defensin', 'cathelicidin',
                                             'membrane disruption', 'host defense', 'kills bacteria']
                    found_amp = [kw for kw in antimicrobial_keywords if kw.lower() in desc_lower]
                    if found_amp:
                        lines.append(f"  *** AMP KEYWORDS FOR VERIFICATION: {', '.join(found_amp)} ***")
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
                        lines.append(f"    *** Supports Injection/Infusion verification ***")
                    elif any(kw in desc_lower for kw in ['topical', 'cream', 'gel', 'applied', 'varnish', 'strip']):
                        lines.append(f"    *** Supports Topical verification ***")
                    elif any(kw in desc_lower for kw in ['oral', 'tablet', 'capsule', 'drink', 'supplement']):
                        lines.append(f"    *** Supports Oral verification ***")
        
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
            lines.append("\n**Primary Outcomes (for success/failure verification):**")
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
        
        for i, entry in enumerate(uniprot_results[:3], 1):
            # Extract key information
            primary_acc = entry.get("primaryAccession", "N/A")
            entry_type = entry.get("entryType", "N/A")
            
            # Protein description
            protein_desc = entry.get("proteinDescription", {})
            rec_name = protein_desc.get("recommendedName", {})
            full_name = rec_name.get("fullName", {}).get("value", "N/A")
            
            # Organism
            organism = entry.get("organism", {})
            org_name = organism.get("scientificName", "N/A")
            
            lines.append(f"### UniProt Entry {i}")
            lines.append(f"**Accession:** {primary_acc}")
            lines.append(f"**Entry Type:** {entry_type}")
            lines.append(f"**Protein Name:** {full_name}")
            lines.append(f"**Organism:** {org_name}")
            
            # SEQUENCE - THE CRITICAL PART!
            sequence_info = entry.get("sequence", {})
            actual_sequence = sequence_info.get("value", "")
            seq_length = sequence_info.get("length", 0)
            seq_mass = sequence_info.get("molWeight", 0)
            
            lines.append(f"\n**Sequence Length:** {seq_length} amino acids")
            lines.append(f"**Molecular Weight:** {seq_mass} Da")
            
            # Highlight if it's a peptide (<200 aa)
            if seq_length and seq_length < 200:
                lines.append(f"*** PEPTIDE VERIFICATION: Length {seq_length} < 200 aa suggests TRUE ***")
            
            if actual_sequence:
                # Show sequence for extraction
                if len(actual_sequence) <= 100:
                    lines.append(f"**ACTUAL SEQUENCE:** {actual_sequence}")
                else:
                    lines.append(f"**ACTUAL SEQUENCE (truncated):** {actual_sequence[:100]}...")
                    lines.append(f"*Full sequence available - {seq_length} residues*")
            
            # Function - important for classification verification
            comments = entry.get("comments", [])
            for comment in comments:
                if comment.get("commentType") == "FUNCTION":
                    func_texts = comment.get("texts", [])
                    if func_texts:
                        func_desc = func_texts[0].get("value", "")
                        if func_desc:
                            if len(func_desc) > 400:
                                func_desc = func_desc[:400] + "..."
                            lines.append(f"\n**Function:** {func_desc}")
                            
                            # Check for antimicrobial keywords for AMP verification
                            func_lower = func_desc.lower()
                            amp_indicators = ['antimicrobial', 'antibacterial', 'antifungal', 
                                            'bactericidal', 'kills', 'membrane', 'defensin']
                            found_amp = [kw for kw in amp_indicators if kw in func_lower]
                            if found_amp:
                                lines.append(f"*** AMP VERIFICATION KEYWORDS: {', '.join(found_amp)} ***")
            
            # Keywords for peptide/AMP verification
            kw_list = entry.get("keywords", [])
            if kw_list:
                keyword_values = [kw.get("name", "") for kw in kw_list[:10]]
                lines.append(f"**Keywords:** {', '.join(keyword_values)}")
                
                # Check for relevant keywords
                kw_string = ' '.join(keyword_values).lower()
                if 'antimicrobial' in kw_string:
                    lines.append("*** Keyword supports AMP verification: TRUE ***")
            
            lines.append("")
        
        return "\n".join(lines)
    
    def _format_extended_data(self, results: Dict[str, Any]) -> str:
        """Format extended search data (DRAMP, Google Scholar) with verification hints."""
        extended_source = results.get("sources", {}).get("extended", {})
        if not extended_source:
            return ""
        
        lines = []
        has_data = False
        
        # DRAMP Database - important for peptide and AMP verification
        dramp = extended_source.get("dramp", {})
        if dramp.get("success"):
            has_data = True
            dramp_data = dramp.get("data", {})
            dramp_results = dramp_data.get("results", [])
            
            lines.append("### DRAMP Database (Antimicrobial Peptide Database)")
            lines.append(f"**Total Results:** {dramp_data.get('total', 0)}")
            lines.append(f"**Query:** {dramp_data.get('query', 'N/A')}\n")
            
            if dramp_results:
                lines.append("*** DRAMP HIT: Supports Peptide=TRUE and AMP verification ***")
            
            for i, result in enumerate(dramp_results[:3], 1):
                lines.append(f"**Entry {i}:**")
                lines.append(f"  DRAMP ID: {result.get('dramp_id', 'N/A')}")
                lines.append(f"  Name: {result.get('name', 'N/A')}")
                
                sequence = result.get("sequence", "")
                if sequence:
                    lines.append(f"  *** SEQUENCE FOUND: {sequence[:60]}{'...' if len(sequence) > 60 else ''} ***")
                
                activity = result.get("activity", "")
                if activity:
                    lines.append(f"  Activity: {activity}")
                    if any(term in activity.lower() for term in ['antibacterial', 'antifungal', 'antimicrobial']):
                        lines.append(f"  *** Activity supports AMP verification: TRUE ***")
                
                source = result.get("source", "")
                if source:
                    lines.append(f"  Source: {source}")
                
                lines.append("")
        
        # Google Scholar results
        scholar = extended_source.get("google_scholar", {})
        if scholar.get("success"):
            has_data = True
            scholar_results = scholar.get("data", {}).get("results", [])
            
            if scholar_results:
                lines.append("\n### Google Scholar Literature")
                lines.append(f"**Results Found:** {len(scholar_results)}\n")
            
            for i, result in enumerate(scholar_results[:3], 1):
                lines.append(f"**Paper {i}:**")
                lines.append(f"  Title: {result.get('title', 'N/A')}")
                snippet = result.get('snippet', '')
                if snippet:
                    if len(snippet) > 300:
                        snippet = snippet[:300] + "..."
                    lines.append(f"  Snippet: {snippet}")
                    
                    # Check for verification keywords
                    snippet_lower = snippet.lower()
                    if any(term in snippet_lower for term in ['antimicrobial', 'antibacterial', 'antifungal']):
                        lines.append(f"  *** Literature supports AMP verification ***")
                
                lines.append("")
        
        if not has_data:
            return ""
        
        return "\n".join(lines)
    
    def _format_pubmed_data(self, results: Dict[str, Any]) -> str:
        """Format PubMed data with focus on relevant content for verification."""
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
                
                # Check for antimicrobial content - verification support
                antimicrobial_terms = ['antimicrobial', 'antibacterial', 'antifungal', 'bactericidal', 
                                       'MIC', 'minimum inhibitory', 'kills bacteria']
                found_terms = [term for term in antimicrobial_terms if term.lower() in abstract.lower()]
                if found_terms:
                    lines.append(f"*** AMP VERIFICATION SUPPORT: {', '.join(found_terms)} ***")
            
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