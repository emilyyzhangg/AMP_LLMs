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
    """
    
    def __init__(self):
        """Initialize prompt generator."""
        self.modelfile_template = self._load_modelfile_template()
    
    def _load_modelfile_template(self) -> str:
        """Load the improved Modelfile template."""
        return """# Improved Clinical Trial Research Assistant Modelfile Template

FROM llama3.2

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

## 3. DELIVERY MODE

**Decision Tree**:
1. Check intervention descriptions for explicit route
2. Check arm group descriptions
3. Check trial title/summary
4. Infer from intervention type if not stated

**Injection/Infusion**:
- Keywords: IV, intravenous, SC, subcutaneous, IM, intramuscular, injection, infusion, bolus, drip
- Default for: Most biologicals, peptides without other indication

**Topical**:
- Keywords: topical, dermal, cream, ointment, gel, spray (skin), patch, varnish, rinse, mouthwash, eye drops, nasal spray, wound dressing
- Context: Skin conditions, wound care, oral/dental, ophthalmic

**Oral**:
- Keywords: oral, tablet, capsule, pill, by mouth, PO, solution (drink), syrup
- Note: Most peptides degrade orally - only choose if explicitly stated

**Other**:
- Inhalation, rectal, vaginal, implant, or unclear/multiple routes

**Examples**:
- "Subcutaneous injection once weekly" → Delivery Mode: Injection/Infusion
- "Topical gel applied to wound site" → Delivery Mode: Topical
- "Oral capsule twice daily" → Delivery Mode: Oral
- "Intravitreal injection" → Delivery Mode: Injection/Infusion
- "Inhaled formulation" → Delivery Mode: Other

## 4. OUTCOME - ENHANCED DECISION LOGIC

**CRITICAL**: Outcome determination requires careful analysis of trial status AND available results.

### STEP 1: Map Status to Initial Outcome Category

| Trial Status | Initial Outcome |
|-------------|-----------------|
| RECRUITING | Active |
| NOT_YET_RECRUITING | Active |
| ENROLLING_BY_INVITATION | Active |
| ACTIVE_NOT_RECRUITING | Active |
| AVAILABLE | Active |
| WITHDRAWN | Withdrawn |
| TERMINATED | Terminated |
| SUSPENDED | Unknown |
| WITHHELD | Unknown |
| NO_LONGER_AVAILABLE | Unknown |
| COMPLETED | → Go to Step 2 |
| UNKNOWN | Unknown |

### STEP 2: For COMPLETED Trials - Analyze Results

**If hasResults = true**, look for these indicators:

**POSITIVE Outcome Indicators** (any of these → Positive):
- "met primary endpoint", "achieved primary endpoint"
- "statistically significant improvement", "significant efficacy"
- "demonstrated superiority", "non-inferior" (for non-inferiority trials)
- "FDA approved", "regulatory approval"
- "primary objective achieved"
- p-value < 0.05 for primary endpoint with positive effect
- "effective", "efficacious" in conclusions

**FAILED Outcome Indicators** (any of these → Failed - completed trial):
- "did not meet primary endpoint", "failed to meet primary endpoint"
- "no statistically significant difference", "not significant"
- "failed to demonstrate efficacy", "lack of efficacy"
- "primary endpoint not achieved"
- p-value ≥ 0.05 for primary endpoint
- "ineffective" in conclusions
- "safety concerns led to stopping" (if completed but negative)

**If hasResults = false**:
- No results posted yet → Outcome: Unknown
- Results expected but not available → Outcome: Unknown

### STEP 3: For TERMINATED Trials - Check Reason

Look for whyStopped field:
- "lack of efficacy" → Terminated (Reason: Ineffective)
- "safety", "adverse events", "toxicity" → Terminated (Reason: Toxic/unsafe)
- "funding", "sponsor decision", "business" → Terminated (Reason: Business)
- "enrollment", "recruitment" → Terminated (Reason: Recruitment issues)
- "COVID" → Terminated (Reason: Due to covid)

### OUTCOME EXAMPLES WITH REASONING

**Example 1: Positive**
- Status: COMPLETED
- hasResults: true
- Results text: "Primary endpoint met with p<0.001, showing 45% reduction in infection rate"
- Reasoning: Completed with significant positive results → Outcome: Positive

**Example 2: Failed - completed trial**
- Status: COMPLETED
- hasResults: true
- Results text: "Study did not meet its primary endpoint (p=0.23)"
- Reasoning: Completed but failed to show efficacy → Outcome: Failed - completed trial

**Example 3: Unknown**
- Status: COMPLETED
- hasResults: false
- Results text: N/A
- Reasoning: Trial completed but no results available → Outcome: Unknown

**Example 4: Terminated**
- Status: TERMINATED
- whyStopped: "Lack of efficacy at interim analysis"
- Reasoning: Stopped early due to futility → Outcome: Terminated

**Example 5: Active**
- Status: RECRUITING
- Reasoning: Trial still enrolling → Outcome: Active

**Example 6: Withdrawn**
- Status: WITHDRAWN
- whyStopped: "Funding issues"
- Reasoning: Never started enrollment → Outcome: Withdrawn

## 5. REASON FOR FAILURE

**Only complete if Outcome is**: Withdrawn, Terminated, or Failed - completed trial
**Otherwise**: N/A

**Categories**:
- Business reasons: funding, sponsorship, company decision, strategic, acquisition
- Ineffective for purpose: lack of efficacy, failed endpoints, no benefit
- Toxic/unsafe: adverse events, safety concerns, toxicity
- Due to covid: COVID-19 related delays or issues
- Recruitment issues: enrollment problems, difficulty recruiting, low accrual

**Use whyStopped field** when available. Otherwise infer from context.

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
10. For Outcome: If COMPLETED, carefully check hasResults and result text

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

IMPORTANT REMINDERS:
- For CLASSIFICATION: Focus on whether the peptide has ANTIMICROBIAL activity (kills/inhibits pathogens)
- For OUTCOME: If status is COMPLETED, check hasResults and look for endpoint success/failure indicators

## OUTPUT FORMAT
NCT Number: [NCT ID]
Study Title: [Full title]
Study Status: [Status from ClinicalTrials.gov]
Brief Summary: [Summary text]
Conditions: [List of conditions]
Interventions/Drug: [Drug names]
Phases: [Trial phase]
Enrollment: [Number]
Start Date: [Date]
Completion Date: [Date]

Classification: [AMP or Other]
  Reasoning: [Think step-by-step: Is it a peptide? Does it have antimicrobial mechanism?]
  Evidence: [Quote specific evidence about antimicrobial activity or lack thereof]
Delivery Mode: [Injection/Infusion, Topical, Oral, or Other]
  Evidence: [Quote or reasoning]
Outcome: [Positive, Withdrawn, Terminated, Failed - completed trial, Active, or Unknown]
  Reasoning: [Check status first, then if COMPLETED check hasResults and endpoint data]
  Evidence: [Quote specific result data or status information]
Reason for Failure: [N/A or reason]
  Evidence: [Quote or reasoning]
Peptide: [True or False]
  Evidence: [Quote or reasoning]
Sequence: [Amino acid sequence or N/A]
DRAMP Name: [Name or N/A]
Study IDs: [PMIDs separated by |]
Comments: [Any additional notes]


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
        
        # Add final instruction with enhanced guidance
        sections.append("""
---
# YOUR TASK

Based on ALL the data provided above, complete the annotation following the EXACT format 
specified in your instructions. 

CLASSIFICATION CHECKLIST:
□ Is the intervention a peptide?
□ Does it have DIRECT antimicrobial activity (kills bacteria/fungi/viruses)?
□ Look for keywords: antimicrobial, antibacterial, antifungal, bactericidal, defensin, cathelicidin
□ If treating infection WITH antimicrobial mechanism → AMP
□ If metabolic/hormonal/immunomodulator without antimicrobial activity → Other

OUTCOME CHECKLIST (for COMPLETED trials):
□ Check hasResults field (true/false)
□ If hasResults=true, look for: "met primary endpoint", "significant", "efficacy demonstrated"
□ If hasResults=true but "failed to meet", "not significant", "lack of efficacy" → Failed
□ If hasResults=false → Unknown

Remember to:
1. Include step-by-step REASONING for Classification, Delivery Mode, Outcome, and Peptide
2. Only report Sequence if you find actual amino acid sequences in the data
3. Use evidence from the specific data sources when available
4. If data is missing or unclear, state N/A with brief explanation

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
        lines.append(f"\n**[CRITICAL FOR OUTCOME DETERMINATION]**")
        lines.append(f"**Overall Status:** {status_mod.get('overallStatus', 'N/A')}")
        lines.append(f"**Has Results:** {has_results}")
        why_stopped = status_mod.get('whyStopped', '')
        if why_stopped:
            lines.append(f"**Why Stopped:** {why_stopped}")
        lines.append(f"**Start Date:** {status_mod.get('startDateStruct', {}).get('date', 'N/A')}")
        lines.append(f"**Completion Date:** {status_mod.get('completionDateStruct', {}).get('date', 'N/A')}")
        
        # If has results, extract key outcome information
        if has_results and results_section:
            lines.append(f"\n**[TRIAL RESULTS - USE FOR OUTCOME DETERMINATION]**")
            
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
                            
                            if p_value:
                                lines.append(f"  **P-value:** {p_value}")
                            if stat_method:
                                lines.append(f"  Statistical Method: {stat_method}")
            
            # Adverse events summary
            adverse_events = results_section.get("adverseEventsModule", {})
            if adverse_events:
                serious_freq = adverse_events.get("seriousNumAffected", "")
                if serious_freq:
                    lines.append(f"\n**Serious Adverse Events:** {serious_freq} affected")
        
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
        lines.append(f"\n**[IMPORTANT FOR CLASSIFICATION]**")
        lines.append(f"**Conditions:** {', '.join(conditions) if conditions else 'N/A'}")
        
        keywords = cond_mod.get("keywords", [])
        if keywords:
            lines.append(f"**Keywords:** {', '.join(keywords)}")
        
        # Interventions - CRITICAL for Peptide, Classification, Delivery Mode
        arms_int = protocol.get("armsInterventionsModule", {})
        interventions = arms_int.get("interventions", [])
        if interventions:
            lines.append(f"\n**[CRITICAL FOR PEPTIDE/CLASSIFICATION/DELIVERY MODE]**")
            lines.append("**Interventions:**")
            for intv in interventions[:5]:
                int_type = intv.get("type", "")
                int_name = intv.get("name", "")
                int_desc = intv.get("description", "")
                lines.append(f"  - Type: {int_type}")
                lines.append(f"    Name: {int_name}")
                if int_desc:
                    if len(int_desc) > 400:
                        int_desc = int_desc[:400] + "..."
                    lines.append(f"    Description: {int_desc}")
                    
                    # Highlight antimicrobial keywords if present
                    antimicrobial_keywords = ['antimicrobial', 'antibacterial', 'antifungal', 'antiviral', 
                                             'bactericidal', 'fungicidal', 'defensin', 'cathelicidin',
                                             'membrane disruption', 'host defense']
                    found_keywords = [kw for kw in antimicrobial_keywords if kw.lower() in int_desc.lower()]
                    if found_keywords:
                        lines.append(f"    **[AMP INDICATORS FOUND: {', '.join(found_keywords)}]**")
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
                            lines.append(f"**[ANTIMICROBIAL FUNCTION DETECTED - supports AMP classification]**")
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
                        lines.append(f"**[AMP-RELATED KEYWORDS: {', '.join(amp_keywords)}]**")
            
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
            lines.append(f"**[DRAMP MATCH = STRONG AMP INDICATOR]**")
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
                    lines.append(f"  **Route of Administration:** {', '.join(routes[:3])}")
                
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
                    lines.append(f"**[ANTIMICROBIAL CONTENT: {', '.join(found_terms)}]**")
            
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