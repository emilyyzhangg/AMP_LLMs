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
- NEW: Verification prompts for two-stage annotation pipeline
"""
import logging
import re
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

# Truncation limits for different content types
class TruncationLimits:
    """Centralized truncation limits for consistent text handling."""
    BRIEF_SUMMARY = 800
    DETAILED_DESCRIPTION = 600
    ABSTRACT = 600
    PMC_ABSTRACT = 500
    INTERVENTION_DESCRIPTION = 500
    ARM_DESCRIPTION = 300
    SNIPPET = 300
    FUNCTION_TEXT = 400
    BIOC_PASSAGE = 400
    CITATION = 150


# Shared route keyword mappings for delivery mode detection
ROUTE_KEYWORDS = {
    # Injection/Infusion indicators
    'injection': 'Injection/Infusion',
    'injectable': 'Injection/Infusion',
    'inject': 'Injection/Infusion',
    'infusion': 'Injection/Infusion',
    'infuse': 'Injection/Infusion',
    'intravenous': 'Injection/Infusion',
    'iv ': 'Injection/Infusion',
    'i.v.': 'Injection/Infusion',
    'subcutaneous': 'Injection/Infusion',
    'sc ': 'Injection/Infusion',
    's.c.': 'Injection/Infusion',
    'sq ': 'Injection/Infusion',
    'subq': 'Injection/Infusion',
    'intramuscular': 'Injection/Infusion',
    'im ': 'Injection/Infusion',
    'i.m.': 'Injection/Infusion',
    'intradermal': 'Injection/Infusion',
    'intraperitoneal': 'Injection/Infusion',
    'intrathecal': 'Injection/Infusion',
    'intravitreal': 'Injection/Infusion',
    'intraarticular': 'Injection/Infusion',
    'intralesional': 'Injection/Infusion',
    'bolus': 'Injection/Infusion',
    'parenteral': 'Injection/Infusion',
    'syringe': 'Injection/Infusion',
    'needle': 'Injection/Infusion',
    'drip': 'Injection/Infusion',
    # Topical indicators
    'topical': 'Topical',
    'topically': 'Topical',
    'cream': 'Topical',
    'ointment': 'Topical',
    'gel': 'Topical',
    'lotion': 'Topical',
    'dermal': 'Topical',
    'transdermal': 'Topical',
    'cutaneous': 'Topical',
    'wound': 'Topical',
    'wound care': 'Topical',
    'wound dressing': 'Topical',
    'patch': 'Topical',
    'eye drop': 'Topical',
    'eyedrop': 'Topical',
    'ophthalmic': 'Topical',
    'ocular': 'Topical',
    'ear drop': 'Topical',
    'otic': 'Topical',
    'nasal spray': 'Topical',
    'intranasal': 'Topical',
    'nasal': 'Topical',
    'mouthwash': 'Topical',
    'mouth rinse': 'Topical',
    'oral rinse': 'Topical',
    'buccal': 'Topical',
    'dental': 'Topical',
    'periodontal': 'Topical',
    'gingival': 'Topical',
    'vaginal': 'Topical',
    'intravaginal': 'Topical',
    'rectal': 'Topical',
    'enema': 'Topical',
    # Oral indicators
    'oral': 'Oral',
    'orally': 'Oral',
    'by mouth': 'Oral',
    'per os': 'Oral',
    'po ': 'Oral',
    'p.o.': 'Oral',
    'tablet': 'Oral',
    'tablets': 'Oral',
    'capsule': 'Oral',
    'capsules': 'Oral',
    'pill': 'Oral',
    'pills': 'Oral',
    'syrup': 'Oral',
    'elixir': 'Oral',
    'swallow': 'Oral',
    'swallowed': 'Oral',
    'enteric': 'Oral',
    'enteric-coated': 'Oral',
    'sublingual': 'Oral',
    'lozenge': 'Oral',
    # Other indicators
    'inhaled': 'Other',
    'inhalation': 'Other',
    'nebulized': 'Other',
    'pulmonary': 'Other',
    'implant': 'Other',
    'implanted': 'Other',
    'depot': 'Other',
    # Additional injection-related terms often found in clinical trials
    'administered intravenously': 'Injection/Infusion',
    'administered subcutaneously': 'Injection/Infusion',
    'administered intramuscularly': 'Injection/Infusion',
    'given intravenously': 'Injection/Infusion',
    'given subcutaneously': 'Injection/Infusion',
    'given intramuscularly': 'Injection/Infusion',
    'intravenously administered': 'Injection/Infusion',
    'subcutaneously administered': 'Injection/Infusion',
    'intramuscularly administered': 'Injection/Infusion',
    'via injection': 'Injection/Infusion',
    'via infusion': 'Injection/Infusion',
    'injected': 'Injection/Infusion',
    'infused': 'Injection/Infusion',
    # Additional topical terms
    'applied topically': 'Topical',
    'topical application': 'Topical',
    'skin application': 'Topical',
    'applied to the skin': 'Topical',
    'applied to skin': 'Topical',
    'wound application': 'Topical',
    'wound healing': 'Topical',
    'dressing': 'Topical',
    'spray': 'Topical',  # Usually topical unless "inhaled spray"
    'foam': 'Topical',
    'solution for skin': 'Topical',
    # Additional oral terms
    'taken orally': 'Oral',
    'oral administration': 'Oral',
    'oral dosing': 'Oral',
    'oral dose': 'Oral',
    'taken by mouth': 'Oral',
    'orally administered': 'Oral',
    'oral solution': 'Oral',
    'oral suspension': 'Oral',
    'chewable': 'Oral',
    'granules': 'Oral',
    'powder for oral': 'Oral',
}

# Outcome status mapping - maps ClinicalTrials.gov status to our outcome categories
OUTCOME_STATUS_MAPPING = {
    # Active statuses
    'RECRUITING': 'Active',
    'NOT_YET_RECRUITING': 'Active',
    'ENROLLING_BY_INVITATION': 'Active',
    'ACTIVE_NOT_RECRUITING': 'Active',
    'AVAILABLE': 'Active',
    'TEMPORARILY_NOT_AVAILABLE': 'Active',
    # Withdrawn
    'WITHDRAWN': 'Withdrawn',
    # Terminated
    'TERMINATED': 'Terminated',
    # Unknown/Suspended
    'SUSPENDED': 'Unknown',
    'WITHHELD': 'Unknown',
    'NO_LONGER_AVAILABLE': 'Unknown',
    'UNKNOWN_STATUS': 'Unknown',
    'UNKNOWN': 'Unknown',
    # Completed requires further analysis
    'COMPLETED': 'NEEDS_RESULTS_ANALYSIS',
}

# Keywords indicating positive trial outcome
POSITIVE_OUTCOME_KEYWORDS = [
    'met primary endpoint',
    'met the primary endpoint',
    'achieved primary endpoint',
    'primary endpoint was met',
    'primary endpoint achieved',
    'statistically significant',
    'significant improvement',
    'significant reduction',
    'significant increase',
    'significant difference',
    'demonstrated efficacy',
    'showed efficacy',
    'proven effective',
    'effective treatment',
    'superior to placebo',
    'superior to control',
    'non-inferior',
    'noninferiority met',
    'non-inferiority met',
    'fda approved',
    'regulatory approval',
    'marketing authorization',
    'positive results',
    'favorable results',
    'met its endpoint',
    'endpoints were met',
    'primary outcome achieved',
]

# Keywords indicating negative/failed trial outcome
NEGATIVE_OUTCOME_KEYWORDS = [
    'did not meet primary endpoint',
    'failed to meet primary endpoint',
    'primary endpoint was not met',
    'primary endpoint not achieved',
    'did not meet the primary endpoint',
    'failed to meet the primary endpoint',
    'no significant difference',
    'not statistically significant',
    'failed to demonstrate',
    'lack of efficacy',
    'no efficacy',
    'ineffective',
    'not effective',
    'negative results',
    'did not show benefit',
    'no benefit',
    'failed to show',
    'terminated for futility',
    'futility',
    'did not achieve',
    'unsuccessful',
    'not superior',
    'inferior to',
    'no improvement',
]

# Antimicrobial keywords for AMP classification
ANTIMICROBIAL_KEYWORDS = [
    'antimicrobial', 'antibacterial', 'antifungal', 'antiviral',
    'bactericidal', 'fungicidal', 'defensin', 'cathelicidin',
    'membrane disruption', 'host defense', 'kills bacteria',
    'bacteriostatic', 'virucidal', 'antiparasitic'
]


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
    - NEW: Verification prompts for two-stage annotation
    - NEW: Robust error handling for missing/empty data
    - NEW: Configurable quality score weights
    """

    # Critical data sources for each annotation field
    REQUIRED_SOURCES = {
        'classification': ['clinical_trials', 'pubmed'],
        'delivery_mode': ['clinical_trials'],
        'outcome': ['clinical_trials'],
        'failure_reason': ['clinical_trials'],
        'peptide': ['clinical_trials', 'uniprot'],
        'sequence': ['clinical_trials', 'uniprot', 'extended']
    }

    # Default source weights for quality scoring
    # See QUALITY_SCORES.md for detailed reasoning behind these values
    DEFAULT_SOURCE_WEIGHTS = {
        # Core sources - these provide the primary trial data
        'clinical_trials': 0.40,  # Primary source: trial status, interventions, outcomes
        'pubmed': 0.15,           # Published literature context and validation
        'pmc': 0.10,              # Full-text articles for deeper context
        'pmc_bioc': 0.05,         # Annotated data extraction (supplementary)

        # Extended sources - provide additional context
        'uniprot': 0.15,          # Critical for sequence and peptide determination
        'openfda': 0.05,          # FDA drug info, delivery routes
        'duckduckgo': 0.05,       # Web context (lower reliability)
        'dramp': 0.05,            # AMP database (highly specific when available)

        # Paid sources (may not always be available)
        'serpapi': 0.00,          # Disabled by default (paid)
        'scholar': 0.00,          # Disabled by default (paid)
    }

    def __init__(
        self,
        model_name: str = "llama3.2",
        source_weights: Optional[Dict[str, float]] = None
    ):
        """
        Initialize prompt generator with optional custom quality weights.

        Args:
            model_name: The model to use in the Modelfile template (default: llama3.2)
            source_weights: Optional custom weights for source-level quality scoring.
                           Keys are source names, values are weights (should sum to ~1.0).
                           If None, uses DEFAULT_SOURCE_WEIGHTS.
        """
        self.model_name = model_name
        self.source_weights = source_weights or self.DEFAULT_SOURCE_WEIGHTS.copy()

    @classmethod
    def get_default_weights(cls) -> Dict[str, float]:
        """
        Get the default source weights for quality scoring.

        Returns:
            Dictionary of default weights that can be modified and passed back.
        """
        return cls.DEFAULT_SOURCE_WEIGHTS.copy()

    def set_source_weights(self, source_weights: Dict[str, float]) -> None:
        """
        Update the source weights used for quality scoring.

        Args:
            source_weights: New weights to use. Keys are source names, values are weights.
        """
        self.source_weights = source_weights

    def reset_weights_to_default(self) -> None:
        """Reset source weights to the default values."""
        self.source_weights = self.DEFAULT_SOURCE_WEIGHTS.copy()

    def get_current_weights(self) -> Dict[str, float]:
        """
        Get the current source weights being used.

        Returns:
            Dictionary of current weights.
        """
        return self.source_weights.copy()

    def _check_data_availability(self, search_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check which data sources are available and assess overall data quality.

        Args:
            search_results: Complete search results from NCTSearchEngine

        Returns:
            Dictionary with availability info:
            - available_sources: list of sources with data
            - missing_sources: list of sources without data
            - quality_score: 0-1 score indicating weighted data completeness
            - unweighted_score: simple ratio of available/checked sources
            - warnings: list of warning messages
            - field_recommendations: per-field recommendations for handling missing data
            - weights_used: the weights applied for scoring
        """
        # Try both possible paths for sources
        sources = search_results.get("sources", {})
        if not sources:
            sources = search_results.get("results", {}).get("sources", {})

        available = []
        missing = []
        warnings = []

        # Check core sources
        source_checks = {
            'clinical_trials': sources.get("clinical_trials", {}).get("success", False),
            'pubmed': sources.get("pubmed", {}).get("success", False),
            'pmc': sources.get("pmc", {}).get("success", False),
            'pmc_bioc': sources.get("pmc_bioc", {}).get("success", False),
        }

        # Check extended sources - try both paths
        extended = sources.get("extended", {})
        if not extended:
            extended = search_results.get("results", {}).get("sources", {}).get("extended", {})
        if extended:
            source_checks['uniprot'] = extended.get("uniprot", {}).get("success", False)
            source_checks['openfda'] = extended.get("openfda", {}).get("success", False)
            source_checks['duckduckgo'] = extended.get("duckduckgo", {}).get("success", False)
            source_checks['dramp'] = extended.get("dramp", {}).get("success", False)
            source_checks['serpapi'] = extended.get("serpapi", {}).get("success", False)
            source_checks['scholar'] = extended.get("scholar", {}).get("success", False)

        for source, is_available in source_checks.items():
            if is_available:
                available.append(source)
            else:
                missing.append(source)

        # Calculate weighted quality score using configurable weights
        quality_score = sum(self.source_weights.get(s, 0) for s in available)

        # Calculate unweighted score for comparison
        unweighted_score = len(available) / len(source_checks) if source_checks else 0

        # Generate warnings
        if 'clinical_trials' not in available:
            warnings.append("CRITICAL: No ClinicalTrials.gov data - all annotations may be unreliable")
        if 'uniprot' not in available and 'dramp' not in available:
            warnings.append("No protein database data - Sequence will be N/A, Peptide determination limited")

        # Field-specific recommendations
        field_recs = {}
        for field, required in self.REQUIRED_SOURCES.items():
            missing_required = [r for r in required if r not in available]
            if missing_required:
                if field == 'classification':
                    field_recs[field] = "Limited data - default to 'Other' unless clear AMP indicators"
                elif field == 'delivery_mode':
                    field_recs[field] = "No intervention data - default to 'Other'"
                elif field == 'outcome':
                    field_recs[field] = "No status data - use 'Unknown'"
                elif field == 'failure_reason':
                    field_recs[field] = "No status data - use 'N/A'"
                elif field == 'peptide':
                    field_recs[field] = "Limited evidence - default to 'False' unless drug name indicates peptide"
                elif field == 'sequence':
                    field_recs[field] = "No sequence database data - use 'N/A'"

        return {
            'available_sources': available,
            'missing_sources': missing,
            'quality_score': quality_score,
            'unweighted_score': unweighted_score,
            'warnings': warnings,
            'field_recommendations': field_recs,
            'weights_used': self.source_weights.copy()
        }

    def get_modelfile_template(self, model_name: Optional[str] = None) -> str:
        """
        Get the Modelfile template with the specified model.

        Args:
            model_name: Override the default model name if provided

        Returns:
            The complete Modelfile template string
        """
        return self._load_modelfile_template(model_name or self.model_name)
    
    def _load_modelfile_template(self, model_name: str = "llama3.2") -> str:
        """
        Load the improved Modelfile template.

        Args:
            model_name: The model to use (e.g., llama3.2, mistral, etc.)

        Returns:
            The complete Modelfile template string
        """
        return f"""# Improved Clinical Trial Research Assistant Modelfile Template

FROM {model_name}

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
  Reasoning: [your step-by-step reasoning]
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

**Default to Injection/Infusion if:**
- Drug is a peptide or biological (peptides usually cannot be given orally)
- Drug is an antibody or protein therapeutic
- No route information is provided AND drug is a peptide

**Default to Topical if:**
- Condition is a skin disease (dermatitis, psoriasis, wound, ulcer)
- Condition is eye disease (conjunctivitis, glaucoma)
- Condition is dental/oral cavity disease

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

**Example 9: Other**
- Text: "subcutaneous implant releasing drug over 3 months"
- Keywords found: "implant" (takes precedence)
- Answer: Other (implant)

**Example 10: Injection/Infusion (default)**
- Text: "peptide therapeutic for diabetes" (no route specified)
- Keywords found: none, but drug is a peptide
- Answer: Injection/Infusion (default for peptides)

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
│ SUSPENDED                       │ Unknown                            │
│ WITHHELD                        │ Unknown                            │
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

**Example 10: Unknown**
- Status: SUSPENDED
- Reasoning: SUSPENDED status → cannot determine outcome
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

    # ========================================================================
    # VERIFICATION PROMPT GENERATION (NEW)
    # ========================================================================
    
    def generate_verification_prompt(
        self,
        nct_id: str,
        original_annotation: str,
        parsed_data: Dict[str, str],
        trial_data: Dict[str, Any],
        primary_model: str
    ) -> str:
        """
        Generate a verification prompt for the second-stage LLM.
        
        This prompt asks the verification LLM to:
        1. Review the original annotation and reasoning
        2. Cross-check against the trial data
        3. Identify any errors or inconsistencies
        4. Provide corrections where needed
        
        Args:
            nct_id: NCT identifier
            original_annotation: The full annotation text from the primary LLM
            parsed_data: Structured data extracted from the annotation
            trial_data: The original trial data used for annotation
            primary_model: Name of the model that made the original annotation
            
        Returns:
            Formatted verification prompt
        """
        sections = []
        
        # Header
        sections.append(f"# ANNOTATION VERIFICATION TASK: {nct_id}")
        sections.append(f"""
You are a Clinical Trial Annotation Reviewer. Your task is to VERIFY and CORRECT
the annotation produced by {primary_model} for this clinical trial.

## YOUR ROLE

1. Review the original annotation and its reasoning
2. Cross-check each field against the provided trial data
3. Identify any errors, inconsistencies, or misinterpretations
4. Provide CORRECTIONS where the original annotation is wrong
5. CONFIRM fields that are correctly annotated

## VALID VALUES (for reference)

| Field | Valid Values |
|-------|--------------|
| Classification | AMP, Other |
| Delivery Mode | Injection/Infusion, Topical, Oral, Other |
| Outcome | Positive, Withdrawn, Terminated, Failed - completed trial, Active, Unknown |
| Reason for Failure | Business reasons, Ineffective for purpose, Toxic/unsafe, Due to covid, Recruitment issues, N/A |
| Peptide | True, False |

---
""")
        
        # Section 1: Original Annotation to Review
        sections.append("## ORIGINAL ANNOTATION (to verify)")
        sections.append("```")
        # Sanitize annotation to prevent prompt injection
        sanitized_annotation = self._sanitize_annotation(original_annotation) if original_annotation else "[No annotation provided]"
        sections.append(sanitized_annotation)
        sections.append("```")
        sections.append("")
        
        # Section 2: Parsed Data Summary
        sections.append("## PARSED ANNOTATION VALUES")
        if parsed_data:
            for key, value in parsed_data.items():
                if value:  # Only show non-empty values
                    sections.append(f"- **{key}**: {value}")
        else:
            sections.append("*No parsed data available*")
        sections.append("")
        
        # Section 3: Key Trial Data for Verification
        sections.append("## KEY TRIAL DATA (for cross-checking)")
        trial_summary = self._extract_verification_data(trial_data, nct_id)
        sections.append(trial_summary)
        sections.append("")
        
        # Section 4: Verification Instructions
        # Using f-string to avoid .format() issues with braces in the template
        verification_instructions = f"""---
## YOUR TASK

Review the annotation above and produce a VERIFICATION REPORT in this EXACT format:

```
VERIFICATION REPORT FOR {nct_id}
================================

## FIELD-BY-FIELD REVIEW

Classification: [CORRECT / INCORRECT]
  Original: [value from annotation]
  Verified: [your verified value - same if correct, corrected if wrong]
  Reasoning: [why you agree or disagree with the original]

Delivery Mode: [CORRECT / INCORRECT]
  Original: [value from annotation]
  Verified: [your verified value]
  Reasoning: [why you agree or disagree]

Outcome: [CORRECT / INCORRECT]
  Original: [value from annotation]
  Verified: [your verified value]
  Reasoning: [why you agree or disagree]

Reason for Failure: [CORRECT / INCORRECT / N/A]
  Original: [value from annotation]
  Verified: [your verified value]
  Reasoning: [why you agree or disagree]

Peptide: [CORRECT / INCORRECT]
  Original: [value from annotation]
  Verified: [your verified value]
  Reasoning: [why you agree or disagree]

Sequence: [CORRECT / INCORRECT / N/A]
  Original: [value from annotation]
  Verified: [your verified value]
  Reasoning: [explanation]

## SUMMARY

Total Fields Reviewed: [number]
Correct: [number]
Corrections Made: [number]

## FINAL VERIFIED ANNOTATION

[Provide the complete corrected annotation in the standard format,
incorporating all your corrections. If no corrections needed,
reproduce the original annotation.]

Classification: [verified value]
  Evidence: [evidence]
Delivery Mode: [verified value]
  Evidence: [evidence]
Outcome: [verified value]
  Evidence: [evidence]
Reason for Failure: [verified value or N/A]
  Evidence: [evidence if applicable]
Peptide: [verified value]
  Evidence: [evidence]
Sequence: [verified value or N/A]
  Evidence: [evidence]
Study IDs: [verified value or N/A]
Comments: [any additional notes about verification]
```

Begin your verification:
"""
        sections.append(verification_instructions)
        
        return "\n".join(sections)
    
    def _extract_verification_data(self, trial_data: Dict[str, Any], nct_id: str) -> str:
        """
        Extract key data points from trial data for verification purposes.
        More concise than the full extraction prompt.
        """
        lines = []
        
        # Try to get protocol section from various paths
        protocol = self._get_protocol_section(trial_data)
        
        if not protocol:
            lines.append(f"*Trial data structure not recognized for {nct_id}*")
            lines.append(f"Raw data keys: {list(trial_data.keys())[:10]}")
            return "\n".join(lines)
        
        # Identification
        ident = protocol.get("identificationModule", {})
        lines.append(f"**NCT ID:** {ident.get('nctId', nct_id)}")
        lines.append(f"**Title:** {ident.get('briefTitle', 'N/A')}")
        
        # Status (critical for Outcome)
        status_mod = protocol.get("statusModule", {})
        lines.append(f"\n**Overall Status:** {status_mod.get('overallStatus', 'N/A')}")
        why_stopped = status_mod.get('whyStopped', '')
        if why_stopped:
            lines.append(f"**Why Stopped:** {why_stopped}")
        
        # Check hasResults
        has_results = self._safe_get(trial_data, 'results', 'sources', 'clinical_trials', 'data', 'hasResults', default=False)
        if not has_results:
            has_results = self._safe_get(trial_data, 'sources', 'clinical_trials', 'data', 'hasResults', default=False)
        lines.append(f"**Has Results:** {has_results}")
        
        # Conditions
        cond_mod = protocol.get("conditionsModule", {})
        conditions = cond_mod.get("conditions", [])
        if conditions:
            lines.append(f"\n**Conditions:** {', '.join(conditions[:5])}")
        
        # Interventions (critical for Classification, Peptide, Delivery Mode)
        arms_int = protocol.get("armsInterventionsModule", {})
        interventions = arms_int.get("interventions", [])
        if interventions:
            lines.append(f"\n**Interventions:**")
            for intv in interventions[:3]:
                int_type = intv.get("type", "")
                int_name = intv.get("name", "")
                int_desc = intv.get("description", "")[:200] if intv.get("description") else ""
                lines.append(f"  - {int_type}: {int_name}")
                if int_desc:
                    lines.append(f"    Description: {int_desc}...")
        
        # Description
        desc_mod = protocol.get("descriptionModule", {})
        brief_summary = desc_mod.get("briefSummary", "")
        if brief_summary:
            lines.append(f"\n**Brief Summary:** {brief_summary[:300]}...")
        
        return "\n".join(lines)
    
    def _get_protocol_section(self, trial_data: Dict[str, Any]) -> Dict:
        """Get protocol section from trial data, handling different structures."""
        paths = [
            ('results', 'sources', 'clinical_trials', 'data', 'protocolSection'),
            ('sources', 'clinical_trials', 'data', 'protocolSection'),
            ('results', 'sources', 'clinicaltrials', 'data', 'protocolSection'),
            ('sources', 'clinicaltrials', 'data', 'protocolSection'),
            ('protocolSection',),
        ]
        
        for path in paths:
            protocol = self._safe_get(trial_data, *path, default={})
            if protocol:
                return protocol
        
        return {}
    
    def _safe_get(self, dictionary: Dict, *keys, default=None):
        """Safely navigate nested dictionary keys."""
        current = dictionary
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current if current is not None else default

    def _compute_delivery_mode_suggestion(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Pre-compute delivery mode suggestion based on all available data sources.

        Analyzes:
        1. ClinicalTrials.gov intervention descriptions and arm descriptions
        2. OpenFDA route data (if available)
        3. Drug class and formulation information

        Returns:
            Dictionary with:
            - suggested_mode: The suggested delivery mode
            - confidence: 'high', 'medium', or 'low'
            - evidence: List of evidence supporting the suggestion
            - all_keywords_found: All route keywords found in the data
        """
        evidence = []
        all_keywords_found = []
        route_votes = {'Injection/Infusion': 0, 'Topical': 0, 'Oral': 0, 'Other': 0}

        # Get sources - try both possible paths
        sources = results.get("sources", {})
        if not sources:
            sources = results.get("results", {}).get("sources", {})

        # 1. Check OpenFDA data first (most reliable for approved drugs)
        extended_source = sources.get("extended", {})
        if not extended_source:
            extended_source = results.get("results", {}).get("sources", {}).get("extended", {})

        openfda = extended_source.get("openfda", {})
        if openfda.get("success"):
            fda_data = openfda.get("data", {})
            fda_results = fda_data.get("results", [])
            for result in fda_results[:3]:
                openfda_info = result.get("openfda", {})
                routes = openfda_info.get("route", [])
                for route in routes:
                    route_lower = route.lower()
                    evidence.append(f"OpenFDA route: {route}")
                    if any(kw in route_lower for kw in ['injection', 'intravenous', 'subcutaneous', 'intramuscular', 'parenteral']):
                        route_votes['Injection/Infusion'] += 3  # High weight for FDA data
                        all_keywords_found.append(f"FDA:{route}→Injection/Infusion")
                    elif any(kw in route_lower for kw in ['topical', 'cutaneous', 'dermal', 'ophthalmic', 'nasal']):
                        route_votes['Topical'] += 3
                        all_keywords_found.append(f"FDA:{route}→Topical")
                    elif any(kw in route_lower for kw in ['oral', 'sublingual']):
                        route_votes['Oral'] += 3
                        all_keywords_found.append(f"FDA:{route}→Oral")
                    else:
                        route_votes['Other'] += 1
                        all_keywords_found.append(f"FDA:{route}→Other")

        # 2. Check ClinicalTrials.gov intervention data
        ct_source = sources.get("clinical_trials", {})
        if ct_source.get("success"):
            ct_data = ct_source.get("data", {})
            protocol = ct_data.get("protocolSection", {})

            # Check intervention descriptions
            arms_int = protocol.get("armsInterventionsModule", {})
            interventions = arms_int.get("interventions", [])

            all_text_to_search = []
            for intv in interventions:
                int_name = intv.get("name", "")
                int_desc = intv.get("description", "")
                all_text_to_search.append(int_name)
                all_text_to_search.append(int_desc)

            # Check arm group descriptions
            arm_groups = arms_int.get("armGroups", [])
            for arm in arm_groups:
                arm_desc = arm.get("description", "")
                all_text_to_search.append(arm_desc)

            # Check brief summary and detailed description
            desc_mod = protocol.get("descriptionModule", {})
            all_text_to_search.append(desc_mod.get("briefSummary", ""))
            all_text_to_search.append(desc_mod.get("detailedDescription", ""))

            combined_text = " ".join(all_text_to_search).lower()

            # Search for route keywords
            for keyword, route in ROUTE_KEYWORDS.items():
                # Use word boundary matching for short keywords
                if len(keyword) <= 3:
                    # For short keywords like 'iv', 'sc', 'im', check for word boundaries
                    if re.search(r'\b' + re.escape(keyword) + r'\b', combined_text):
                        route_votes[route] += 2
                        all_keywords_found.append(f"CT:{keyword}→{route}")
                        evidence.append(f"Found '{keyword}' in trial data")
                else:
                    if keyword in combined_text:
                        route_votes[route] += 2
                        all_keywords_found.append(f"CT:{keyword}→{route}")
                        evidence.append(f"Found '{keyword}' in trial data")

        # 3. Determine suggestion based on votes
        max_votes = max(route_votes.values())
        if max_votes == 0:
            # No keywords found - check if it's a peptide/biological (default to injection)
            suggested_mode = "Other"
            confidence = "low"
            evidence.append("No delivery route keywords found in any data source")
        else:
            # Find the route(s) with max votes
            top_routes = [route for route, votes in route_votes.items() if votes == max_votes]

            if len(top_routes) == 1:
                suggested_mode = top_routes[0]
                if max_votes >= 3:
                    confidence = "high"
                elif max_votes >= 2:
                    confidence = "medium"
                else:
                    confidence = "low"
            else:
                # Tie - use priority order: Injection/Infusion > Topical > Oral > Other
                priority_order = ['Injection/Infusion', 'Topical', 'Oral', 'Other']
                for route in priority_order:
                    if route in top_routes:
                        suggested_mode = route
                        break
                confidence = "low"
                evidence.append(f"Multiple routes detected with equal evidence: {', '.join(top_routes)}")

        return {
            'suggested_mode': suggested_mode,
            'confidence': confidence,
            'evidence': evidence[:5],  # Limit evidence to 5 items
            'all_keywords_found': all_keywords_found,
            'vote_breakdown': route_votes
        }

    def _compute_outcome_suggestion(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Pre-compute outcome suggestion based on trial status and results.

        Analyzes:
        1. Overall status field (primary determinant)
        2. hasResults flag
        3. Results section for positive/negative indicators
        4. P-values in outcome analyses

        Returns:
            Dictionary with:
            - suggested_outcome: The suggested outcome
            - confidence: 'high', 'medium', or 'low'
            - evidence: List of evidence supporting the suggestion
            - status_info: Raw status information
        """
        evidence = []

        # Get sources - try both possible paths
        sources = results.get("sources", {})
        if not sources:
            sources = results.get("results", {}).get("sources", {})

        ct_source = sources.get("clinical_trials", {})
        if not ct_source.get("success"):
            return {
                'suggested_outcome': 'Unknown',
                'confidence': 'low',
                'evidence': ['No ClinicalTrials.gov data available'],
                'status_info': {}
            }

        ct_data = ct_source.get("data", {})
        protocol = ct_data.get("protocolSection", {})
        status_mod = protocol.get("statusModule", {})

        overall_status = status_mod.get('overallStatus', 'UNKNOWN').upper()
        has_results = ct_data.get("hasResults", False)
        why_stopped = status_mod.get('whyStopped', '')

        status_info = {
            'overall_status': overall_status,
            'has_results': has_results,
            'why_stopped': why_stopped
        }

        evidence.append(f"Overall Status: {overall_status}")
        evidence.append(f"Has Results: {has_results}")
        if why_stopped:
            evidence.append(f"Why Stopped: {why_stopped[:100]}")

        # Step 1: Map status to outcome using the mapping
        mapped_outcome = OUTCOME_STATUS_MAPPING.get(overall_status, 'Unknown')

        if mapped_outcome != 'NEEDS_RESULTS_ANALYSIS':
            # Direct mapping from status
            return {
                'suggested_outcome': mapped_outcome,
                'confidence': 'high',
                'evidence': evidence,
                'status_info': status_info
            }

        # Step 2: For COMPLETED trials, analyze results
        if not has_results:
            evidence.append("Trial COMPLETED but no results posted - cannot determine success/failure")
            return {
                'suggested_outcome': 'Unknown',
                'confidence': 'medium',
                'evidence': evidence,
                'status_info': status_info
            }

        # Step 3: Analyze results section for positive/negative indicators
        results_section = ct_data.get("resultsSection", {})

        # Collect all text from results for keyword analysis
        results_text_parts = []

        # Check outcome measures
        outcome_measures = results_section.get("outcomeMeasuresModule", {})
        outcome_list = outcome_measures.get("outcomeMeasures", [])

        positive_indicators = []
        negative_indicators = []
        p_values = []

        for om in outcome_list:
            om_title = om.get("title", "")
            om_desc = om.get("description", "")
            results_text_parts.extend([om_title, om_desc])

            # Check analyses for p-values
            analyses = om.get("analyses", [])
            for analysis in analyses:
                p_value_str = analysis.get("pValue", "")
                if p_value_str:
                    p_values.append(p_value_str)
                    # Try to parse p-value
                    try:
                        # Handle various p-value formats
                        p_clean = p_value_str.lower().replace('<', '').replace('>', '').replace('=', '').strip()
                        if p_clean and p_clean[0].isdigit():
                            p_val = float(p_clean.split()[0])
                            if p_val < 0.05:
                                positive_indicators.append(f"Significant p-value: {p_value_str}")
                            else:
                                negative_indicators.append(f"Non-significant p-value: {p_value_str}")
                    except (ValueError, IndexError):
                        pass

        # Check more info module
        more_info = results_section.get("moreInfoModule", {})
        limitations = more_info.get("limitationsAndCaveats", {})
        if limitations:
            lim_desc = limitations.get("description", "")
            results_text_parts.append(lim_desc)

        # Combine all results text and search for keywords
        combined_results_text = " ".join(results_text_parts).lower()

        for keyword in POSITIVE_OUTCOME_KEYWORDS:
            if keyword in combined_results_text:
                positive_indicators.append(f"Found: '{keyword}'")

        for keyword in NEGATIVE_OUTCOME_KEYWORDS:
            if keyword in combined_results_text:
                negative_indicators.append(f"Found: '{keyword}'")

        # Determine outcome based on indicators
        if positive_indicators and not negative_indicators:
            suggested_outcome = 'Positive'
            confidence = 'high' if len(positive_indicators) >= 2 else 'medium'
            evidence.extend(positive_indicators[:3])
        elif negative_indicators and not positive_indicators:
            suggested_outcome = 'Failed - completed trial'
            confidence = 'high' if len(negative_indicators) >= 2 else 'medium'
            evidence.extend(negative_indicators[:3])
        elif positive_indicators and negative_indicators:
            # Mixed signals - need manual review
            suggested_outcome = 'Unknown'
            confidence = 'low'
            evidence.append(f"Mixed signals: {len(positive_indicators)} positive, {len(negative_indicators)} negative indicators")
            evidence.extend(positive_indicators[:2])
            evidence.extend(negative_indicators[:2])
        else:
            # No clear indicators found
            suggested_outcome = 'Unknown'
            confidence = 'low'
            evidence.append("No clear success/failure indicators found in results")

        if p_values:
            evidence.append(f"P-values found: {', '.join(p_values[:3])}")

        return {
            'suggested_outcome': suggested_outcome,
            'confidence': confidence,
            'evidence': evidence[:7],
            'status_info': status_info
        }

    def _sanitize_annotation(self, annotation: str) -> str:
        """
        Sanitize annotation text to prevent prompt injection.

        Removes or escapes patterns that could break the prompt structure
        or inject unintended instructions.

        Args:
            annotation: The raw annotation text

        Returns:
            Sanitized annotation text
        """
        if not annotation:
            return ""

        sanitized = annotation

        # Remove triple backticks that could break code block formatting
        sanitized = sanitized.replace("```", "'''")

        # Remove patterns that look like instruction injection
        injection_patterns = [
            r'(?i)ignore\s+(previous|above|all)\s+instructions?',
            r'(?i)disregard\s+(previous|above|all)',
            r'(?i)new\s+instructions?:',
            r'(?i)system\s*:',
            r'(?i)assistant\s*:',
            r'(?i)human\s*:',
        ]

        for pattern in injection_patterns:
            sanitized = re.sub(pattern, '[REMOVED]', sanitized)

        return sanitized

    def _truncate_text(self, text: str, max_length: int, suffix: str = "...") -> str:
        """
        Truncate text to a maximum length with a suffix.

        Args:
            text: The text to truncate
            max_length: Maximum allowed length
            suffix: Suffix to add when truncating (default: "...")

        Returns:
            Truncated text with suffix if needed
        """
        if not text or len(text) <= max_length:
            return text
        return text[:max_length] + suffix
    
    def get_verification_system_prompt(self) -> str:
        """
        Get the system prompt for the verification LLM.
        """
        return """You are a Clinical Trial Annotation Reviewer with expertise in peptide therapeutics and clinical trial analysis.

Your role is to VERIFY annotations made by another AI model. You must:

1. CRITICALLY EVALUATE each annotation field against the provided trial data
2. IDENTIFY errors in reasoning or classification
3. CORRECT any mistakes you find
4. CONFIRM correct annotations with brief justification

## KEY VERIFICATION RULES

### Classification (AMP vs Other)
- AMP = peptide that DIRECTLY KILLS pathogens (bacteria, fungi, viruses)
- Other = metabolic peptides, hormones, immunomodulators, cancer drugs
- Common error: Classifying immunomodulators or wound-healing peptides as AMP when they don't have direct antimicrobial activity

### Delivery Mode
- Check for explicit route keywords in intervention descriptions
- Injection/Infusion: injection, IV, SC, IM, infusion
- Topical: topical, cream, gel, wound application, eye drops
- Oral: oral, tablet, capsule
- Common error: Defaulting to wrong route when keywords are present

### Outcome
- MUST match the Overall Status exactly for non-COMPLETED trials
- RECRUITING/ACTIVE_NOT_RECRUITING → Active
- WITHDRAWN → Withdrawn
- TERMINATED → Terminated
- COMPLETED requires checking hasResults and result indicators
- Common error: Guessing outcome without checking status field

### Peptide
- True = short amino acid chain (<200 aa)
- False = antibody (-mab), full protein, small molecule
- Common error: Confusing antibodies with peptides

### Sequence
- formatted in standard amino acid code with modifications
- Only report if found in data, otherwise N/A

## OUTPUT FORMAT

Always provide:
1. Field-by-field review with CORRECT/INCORRECT status
2. Clear reasoning for each verification
3. Final verified annotation with all corrections applied

Be thorough but concise. Focus on accuracy."""

    # ========================================================================
    # ORIGINAL METHODS (preserved from original file)
    # ========================================================================
    
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

        # Check data availability first
        data_check = self._check_data_availability(search_results)

        # Add header with clear task
        sections.append(f"# CLINICAL TRIAL ANNOTATION TASK: {nct_id}")

        # Add data quality assessment if there are issues
        if data_check['warnings'] or data_check['quality_score'] < 0.5:
            sections.append("""
## ⚠️ DATA QUALITY ASSESSMENT
""")
            sections.append(f"**Data Completeness:** {data_check['quality_score']:.0%}")
            sections.append(f"**Available Sources:** {', '.join(data_check['available_sources']) or 'None'}")
            sections.append(f"**Missing Sources:** {', '.join(data_check['missing_sources']) or 'None'}")

            if data_check['warnings']:
                sections.append("\n**WARNINGS:**")
                for warning in data_check['warnings']:
                    sections.append(f"  ! {warning}")

            if data_check['field_recommendations']:
                sections.append("\n**FIELD-SPECIFIC GUIDANCE FOR LIMITED DATA:**")
                for field, rec in data_check['field_recommendations'].items():
                    sections.append(f"  - {field}: {rec}")

            sections.append("")

        # Pre-compute delivery mode and outcome suggestions
        delivery_suggestion = self._compute_delivery_mode_suggestion(search_results)
        outcome_suggestion = self._compute_outcome_suggestion(search_results)

        sections.append("""
Analyze the following clinical trial data carefully. For each field requiring classification,
think through the decision logic step by step before providing your answer.

**IMPORTANT:** If data is missing or insufficient for a field, explicitly state this and use
the default/fallback values as specified below.

## QUICK REFERENCE - VALID VALUES ONLY

| Field | Valid Values | Default if Insufficient Data |
|-------|--------------|------------------------------|
| Classification | AMP, Other | Other |
| Delivery Mode | Injection/Infusion, Topical, Oral, Other | Other |
| Outcome | Positive, Withdrawn, Terminated, Failed - completed trial, Active, Unknown | Unknown |
| Reason for Failure | Business reasons, Ineffective for purpose, Toxic/unsafe, Due to covid, Recruitment issues, N/A | N/A |
| Peptide | True, False | False |
| Sequence | Amino acid sequence | N/A |
""")

        # Add pre-computed analysis section
        sections.append("""
## ════════════════════════════════════════════════════════════════════════
## PRE-COMPUTED ANALYSIS (System Suggestions - Use as Strong Hints)
## ════════════════════════════════════════════════════════════════════════
""")

        # Delivery Mode suggestion
        dm_conf_symbol = "★★★" if delivery_suggestion['confidence'] == 'high' else ("★★" if delivery_suggestion['confidence'] == 'medium' else "★")
        sections.append(f"""
### DELIVERY MODE ANALYSIS
**Suggested Value:** {delivery_suggestion['suggested_mode']}
**Confidence:** {delivery_suggestion['confidence'].upper()} {dm_conf_symbol}
**Evidence:**""")
        for ev in delivery_suggestion['evidence']:
            sections.append(f"  - {ev}")
        if delivery_suggestion['all_keywords_found']:
            sections.append(f"**Keywords Found:** {', '.join(delivery_suggestion['all_keywords_found'][:8])}")
        sections.append(f"""
**Vote Breakdown:** Injection/Infusion={delivery_suggestion['vote_breakdown']['Injection/Infusion']}, Topical={delivery_suggestion['vote_breakdown']['Topical']}, Oral={delivery_suggestion['vote_breakdown']['Oral']}, Other={delivery_suggestion['vote_breakdown']['Other']}

⚠️ USE THIS SUGGESTION unless you find clear contradicting evidence in the data below.
""")

        # Outcome suggestion
        oc_conf_symbol = "★★★" if outcome_suggestion['confidence'] == 'high' else ("★★" if outcome_suggestion['confidence'] == 'medium' else "★")
        sections.append(f"""
### OUTCOME ANALYSIS
**Suggested Value:** {outcome_suggestion['suggested_outcome']}
**Confidence:** {outcome_suggestion['confidence'].upper()} {oc_conf_symbol}
**Status Info:**
  - Overall Status: {outcome_suggestion['status_info'].get('overall_status', 'N/A')}
  - Has Results: {outcome_suggestion['status_info'].get('has_results', 'N/A')}""")
        if outcome_suggestion['status_info'].get('why_stopped'):
            sections.append(f"  - Why Stopped: {outcome_suggestion['status_info']['why_stopped'][:100]}")
        sections.append("**Evidence:**")
        for ev in outcome_suggestion['evidence']:
            sections.append(f"  - {ev}")
        sections.append(f"""
⚠️ USE THIS SUGGESTION unless you find clear contradicting evidence in the data below.
""")

        sections.append("""
## ════════════════════════════════════════════════════════════════════════

## KEY DECISION REMINDERS

**CLASSIFICATION**: Does the peptide KILL or INHIBIT pathogens (bacteria/fungi/viruses)?
- YES → AMP
- NO (metabolic/hormonal/immunomodulator) → Other
- INSUFFICIENT DATA → Other (with explanation)

**DELIVERY MODE**: Use the PRE-COMPUTED SUGGESTION above unless contradicting evidence found.
If you disagree with the suggestion, explain why in your reasoning.

**OUTCOME**: Use the PRE-COMPUTED SUGGESTION above unless contradicting evidence found.
If you disagree with the suggestion, explain why in your reasoning.

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
            # Check if this is actual protein data or just a fallback message
            if "NOT AVAILABLE" in uniprot_data:
                logger.warning("🧬 UniProt data NOT AVAILABLE (fallback message in prompt)")
            else:
                logger.info(f"🧬 UniProt data included in prompt ({len(uniprot_data)} chars)")
        else:
            logger.warning("🧬 NO UniProt data available for prompt")

        # Extract all sequences from sources for prominent injection near output instructions
        extracted_sequences = self._extract_sequences_from_sources(search_results)
        if extracted_sequences:
            logger.info(f"🧬 Extracted {len(extracted_sequences)} sequence(s) for direct injection")
        else:
            logger.warning("🧬 No sequences could be extracted from any source")
        
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
        # Build the sequence reminder section with ALL available sequences
        sequence_reminder = ""
        if extracted_sequences:
            seq_lines = []
            seq_lines.append("## SEQUENCE DATA AVAILABLE - DO NOT OUTPUT N/A")
            seq_lines.append("")
            seq_lines.append(f"The following {len(extracted_sequences)} amino acid sequence(s) were found in protein databases.")
            seq_lines.append("**Review all sequences below and select the one that best matches the trial's drug/intervention.**")
            seq_lines.append("**Copy the chosen sequence exactly into the Sequence field, and cite its source in Evidence.**")
            seq_lines.append("")
            for i, seq_entry in enumerate(extracted_sequences, 1):
                label = f"{seq_entry['source']} {seq_entry['accession']}" if seq_entry['accession'] else seq_entry['source']
                seq_lines.append(f"**Candidate {i}: {label}**")
                if seq_entry['name']:
                    seq_lines.append(f"  Protein: {seq_entry['name']}")
                if seq_entry['organism']:
                    seq_lines.append(f"  Organism: {seq_entry['organism']}")
                seq_lines.append(f"  Length: {seq_entry['length']} aa")
                seq_lines.append(f"  Sequence: {seq_entry['sequence']}")
                seq_lines.append("")
            sequence_reminder = "\n".join(seq_lines)
        else:
            sequence_reminder = """## SEQUENCE DATA

No amino acid sequence was found in the protein databases for this trial. Use N/A for the Sequence field.
"""

        sections.append(f"""
---
# YOUR TASK

Analyze the data above and produce your annotation in the EXACT format specified.
{sequence_reminder}
## HANDLING MISSING DATA

When data is unavailable or insufficient for a field:
1. **State the limitation explicitly** in your Reasoning
2. **Use the appropriate fallback value** as specified in the table above
3. **Explain your logic** for choosing the fallback

Example for missing Outcome data:
```
Outcome: Unknown
  Reasoning: Overall status field is not available in the data. Unable to determine trial outcome.
  Evidence: No status data found in any source.
```

## REQUIRED OUTPUT FORMAT

NCT Number: [from data, or "Not found" if missing]
Study Title: [from data, or "Not found" if missing]
Study Status: [from data, or "Not available" if missing]
Brief Summary: [from data, or "Not available" if missing]
Conditions: [from data, or "Not available" if missing]
Interventions/Drug: [from data, or "Not available" if missing]
Phases: [from data, or "Not available" if missing]
Enrollment: [from data, or "Not available" if missing]
Start Date: [from data, or "Not available" if missing]
Completion Date: [from data, or "Not available" if missing]

Classification: [AMP or Other]
  Reasoning: [Is it a peptide? Does it kill pathogens? OR: Why data is insufficient]
  Evidence: [Quote from data, OR: "Insufficient data - see reasoning"]
Delivery Mode: [Injection/Infusion, Topical, Oral, or Other]
  Reasoning: [What route keywords did you find? OR: Why data is insufficient]
  Evidence: [Quote the exact words, OR: "No route information found"]
Outcome: [Positive, Withdrawn, Terminated, Failed - completed trial, Active, or Unknown]
  Reasoning: [What is the status? OR: Why data is insufficient for determination]
  Evidence: [Quote status, OR: "Status field not available"]
Reason for Failure: [Category or N/A]
  Evidence: [Quote whyStopped, OR: "Not applicable" / "No failure reason data"]
Peptide: [True or False]
  Reasoning: [Evidence for peptide determination]
  Evidence: [Quote from data, OR: "Insufficient data - defaulting to False"]
Sequence: [amino acid sequence from UniProt/DRAMP data above, or N/A if not available]
  Evidence: [Source of sequence (e.g., "UniProt accession P12345") or "No sequence data found"]
DRAMP Name: [Name or N/A]
Study IDs: [PMIDs or N/A]
Comments: [Any notes, including data quality observations]

Begin your annotation now:
""")
        
        return "\n".join(sections)
    
    def _format_clinical_trials_data(self, results: Dict[str, Any]) -> str:
        """
        Format ClinicalTrials.gov data with key fields highlighted.

        Returns:
            Formatted clinical trials data string
        """
        # Get sources - try both possible paths
        sources = results.get("sources", {})
        if not sources:
            sources = results.get("results", {}).get("sources", {})

        ct_source = sources.get("clinical_trials", {})

        if not ct_source.get("success"):
            logger.debug("Clinical trials source not available or unsuccessful")
            return """**ClinicalTrials.gov Data: NOT AVAILABLE**

⚠️ CRITICAL: Primary data source is missing. This significantly impacts annotation reliability.

**FALLBACK GUIDANCE:**
- Classification: Use 'Other' unless other sources strongly indicate AMP
- Delivery Mode: Use 'Other' - no intervention data available
- Outcome: Use 'Unknown' - no status data available
- Reason for Failure: Use 'N/A'
- Peptide: Use 'False' unless drug name in other sources indicates peptide
- Sequence: Use 'N/A' - no sequence data available

Please proceed with other available data sources, but note reduced confidence.
"""
        
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
                            param_type = analysis.get("paramType", "")
                            ci_pct = analysis.get("ciPctValue", "")

                            if p_value:
                                # Highlight p-value for easy identification
                                lines.append(f"  *** P-VALUE: {p_value} ***")
                            if stat_method:
                                lines.append(f"  Statistical Method: {stat_method}")
                            if param_type:
                                lines.append(f"  Parameter: {param_type}")
                            if ci_pct:
                                lines.append(f"  Confidence Interval: {ci_pct}%")
            
            # Look for any text indicating success or failure
            more_info = results_section.get("moreInfoModule", {})
            if more_info:
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
                if serious_freq or other_freq:
                    ae_parts = []
                    if serious_freq:
                        ae_parts.append(f"serious: {serious_freq}")
                    if other_freq:
                        ae_parts.append(f"other: {other_freq}")
                    lines.append(f"\n**Adverse Events:** {', '.join(ae_parts)} participants affected")
        
        # Description
        desc_mod = protocol.get("descriptionModule", {})
        brief_summary = desc_mod.get("briefSummary", "N/A")
        brief_summary = self._truncate_text(brief_summary, TruncationLimits.BRIEF_SUMMARY)
        lines.append(f"\n**Brief Summary:** {brief_summary}")

        detailed_desc = desc_mod.get("detailedDescription", "")
        if detailed_desc and len(detailed_desc) > 100:
            detailed_desc = self._truncate_text(detailed_desc, TruncationLimits.DETAILED_DESCRIPTION)
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
                    int_desc = self._truncate_text(int_desc, TruncationLimits.INTERVENTION_DESCRIPTION)
                    lines.append(f"  Description: {int_desc}")

                    # Highlight delivery route keywords using shared constant
                    found_routes = []
                    desc_lower = int_desc.lower()
                    for keyword, route in ROUTE_KEYWORDS.items():
                        if keyword in desc_lower:
                            found_routes.append(f"{keyword}→{route.upper()}")
                    if found_routes:
                        # Deduplicate routes while preserving order
                        seen = set()
                        unique_routes = []
                        for r in found_routes:
                            if r not in seen:
                                seen.add(r)
                                unique_routes.append(r)
                        lines.append(f"  *** DELIVERY ROUTE KEYWORDS FOUND: {', '.join(unique_routes[:5])} ***")

                    # Highlight antimicrobial keywords using shared constant
                    found_amp = [kw for kw in ANTIMICROBIAL_KEYWORDS if kw.lower() in desc_lower]
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
                    arm_desc = self._truncate_text(arm_desc, TruncationLimits.ARM_DESCRIPTION)
                    lines.append(f"    Description: {arm_desc}")

                    # Check for route keywords in arm description using shared constant
                    desc_lower = arm_desc.lower()
                    detected_route = None
                    for keyword, route in ROUTE_KEYWORDS.items():
                        if keyword in desc_lower:
                            detected_route = route
                            break  # Use first match (priority order in dict)
                    if detected_route:
                        lines.append(f"    *** {detected_route.upper()} route indicated ***")
        
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
                    citation = self._truncate_text(citation, TruncationLimits.CITATION)
                    lines.append(f"  {i}. {citation}")
        
        return "\n".join(lines)
    
    def _format_uniprot_data(self, results: Dict[str, Any]) -> str:
        """
        Format UniProt data with ACTUAL SEQUENCES extracted.

        Returns:
            Formatted UniProt data string, or guidance message if unavailable
        """
        try:
            # Get sources - try both possible paths
            sources = results.get("sources", {})
            if not sources:
                sources = results.get("results", {}).get("sources", {})

            extended_source = sources.get("extended", {})
            if not extended_source:
                logger.debug("No extended source data available for UniProt")
                return self._get_uniprot_fallback_message("No extended search data")

            uniprot = extended_source.get("uniprot", {})
            if not isinstance(uniprot, dict):
                logger.warning(f"Unexpected uniprot data type: {type(uniprot)}")
                return self._get_uniprot_fallback_message("Invalid data format")

            if not uniprot.get("success"):
                logger.debug("UniProt query was not successful")
                return self._get_uniprot_fallback_message("Query unsuccessful")

            uniprot_data = uniprot.get("data", {})
            if not isinstance(uniprot_data, dict):
                logger.warning(f"Unexpected uniprot_data type: {type(uniprot_data)}")
                return self._get_uniprot_fallback_message("Invalid data format")

            uniprot_results = uniprot_data.get("results", [])
        except Exception as e:
            logger.error(f"Error extracting UniProt data: {e}")
            return self._get_uniprot_fallback_message(f"Error: {e}")

        if not uniprot_results:
            return self._get_uniprot_fallback_message("No matching proteins found")

        # If we have results, format them
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
            seq_value = sequence_info.get("value", "")
            
            if seq_value:
                lines.append(f"\n**[SEQUENCE DATA - USE FOR ANNOTATION]**")
                lines.append(f"**Sequence Length:** {seq_length} amino acids")
                lines.append(f"**Sequence:** {seq_value}")
            elif seq_length:
                lines.append(f"**Sequence Length:** {seq_length} aa (sequence not retrieved)")
            
            # Function - important for classification
            comments = result.get("comments", [])
            for comment in comments:
                if comment.get("commentType") == "FUNCTION":
                    func_texts = comment.get("texts", [])
                    if func_texts:
                        func_text = func_texts[0].get("value", "")
                        func_text = self._truncate_text(func_text, TruncationLimits.FUNCTION_TEXT)
                        lines.append(f"**Function:** {func_text}")

                        # Check for antimicrobial indicators using shared constant
                        if any(kw in func_text.lower() for kw in ANTIMICROBIAL_KEYWORDS):
                            lines.append("*** ANTIMICROBIAL FUNCTION DETECTED - supports AMP classification ***")
                    break
            
            # Keywords
            result_keywords = result.get("keywords", [])
            if result_keywords:
                keyword_values = [kw.get("name", "") for kw in result_keywords[:10]]
                if keyword_values:
                    lines.append(f"**Keywords:** {', '.join(keyword_values)}")
                    
                    amp_keywords = [kw for kw in keyword_values if any(
                        term in kw.lower() for term in ['antimicrobial', 'antibiotic', 'bacteriocin', 'defensin']
                    )]
                    if amp_keywords:
                        lines.append(f"*** AMP-RELATED KEYWORDS: {', '.join(amp_keywords)} ***")
            
            lines.append("")
        
        return "\n".join(lines)

    def _extract_sequences_from_sources(self, results: Dict[str, Any]) -> list:
        """
        Extract ALL available amino acid sequences from sources with protein context.

        Checks UniProt and DRAMP data. Returns a list of dicts with keys:
          - source: "UniProt" or "DRAMP"
          - accession: protein accession/ID
          - name: protein name
          - organism: organism name
          - sequence: amino acid sequence string
          - length: sequence length

        This is used to inject sequences prominently near the output instructions,
        ensuring the LLM sees them even if the full UniProt section is truncated.
        """
        sequences = []
        try:
            sources = results.get("sources", {})
            if not sources:
                sources = results.get("results", {}).get("sources", {})

            extended = sources.get("extended", {})
            if not extended:
                logger.debug("_extract_sequences: No extended sources found")
                return []

            # Collect from UniProt
            uniprot = extended.get("uniprot", {})
            if uniprot.get("success"):
                uniprot_data = uniprot.get("data", {})
                for protein in uniprot_data.get("results", []):
                    seq_info = protein.get("sequence", {})
                    seq_value = seq_info.get("value", "") if isinstance(seq_info, dict) else ""
                    if seq_value:
                        # Extract protein name from nested structure
                        protein_name = protein.get("protein_name", "")
                        if not protein_name:
                            desc = protein.get("proteinDescription", {})
                            rec = desc.get("recommendedName", {})
                            protein_name = rec.get("fullName", {}).get("value", "") if isinstance(rec.get("fullName"), dict) else ""
                        organism = protein.get("organism", {})
                        org_name = organism.get("scientificName", "") if isinstance(organism, dict) else ""
                        sequences.append({
                            "source": "UniProt",
                            "accession": protein.get("primaryAccession", protein.get("accession", "")),
                            "name": protein_name,
                            "organism": org_name,
                            "sequence": seq_value,
                            "length": seq_info.get("length", len(seq_value)),
                        })

            # Collect from DRAMP
            dramp = extended.get("dramp", {})
            if dramp.get("success"):
                dramp_data = dramp.get("data", {})
                for entry in dramp_data.get("results", []):
                    seq_value = entry.get("sequence", "")
                    if seq_value:
                        sequences.append({
                            "source": "DRAMP",
                            "accession": entry.get("dramp_id", ""),
                            "name": entry.get("name", ""),
                            "organism": "",
                            "sequence": seq_value,
                            "length": len(seq_value),
                        })

        except Exception as e:
            logger.error(f"_extract_sequences: Error extracting sequences: {e}")

        logger.debug(f"_extract_sequences: Found {len(sequences)} sequences total")
        return sequences

    def _get_uniprot_fallback_message(self, reason: str) -> str:
        """Return fallback guidance when UniProt data is unavailable."""
        return f"""**UniProt Data: NOT AVAILABLE** ({reason})

**IMPACT ON ANNOTATION:**
- Sequence: Use 'N/A' - no protein sequence data available
- Peptide: Determine from intervention name/description in clinical trials data
  - Look for peptide indicators: "-tide" suffix, known peptide names, "peptide" in description
  - Default to 'False' if unclear

**GUIDANCE:**
- Check DRAMP or other extended sources if available
- Review intervention descriptions for peptide-related terminology
"""

    def _format_extended_data(self, results: Dict[str, Any]) -> str:
        """
        Format extended API search data (DRAMP, DuckDuckGo, OpenFDA, Scholar).

        Returns:
            Formatted extended data string, or guidance if unavailable
        """
        # Get sources - try both possible paths
        sources = results.get("sources", {})
        if not sources:
            sources = results.get("results", {}).get("sources", {})

        extended_source = sources.get("extended", {})

        if not extended_source:
            logger.debug("No extended source data available")
            return """**Extended Search Data: NOT AVAILABLE**

Extended databases (DRAMP, OpenFDA, web search, Google Scholar) were not queried or returned no data.

**IMPACT:**
- Sequence: May not have DRAMP peptide database matches
- Classification: No additional antimicrobial peptide database confirmation
- Delivery Mode: No FDA drug route information

**GUIDANCE:** Proceed with ClinicalTrials.gov and literature data.
"""

        lines = []
        has_data = False
        
        # DRAMP Database
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
                    snippet = self._truncate_text(snippet, TruncationLimits.SNIPPET)
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
                
                routes = openfda_info.get("route", [])
                if routes:
                    route_str = ', '.join(routes[:3])
                    lines.append(f"  *** ROUTE OF ADMINISTRATION: {route_str} ***")
                    
                    route_lower = route_str.lower()
                    if any(r in route_lower for r in ['intravenous', 'subcutaneous', 'intramuscular', 'injection']):
                        lines.append(f"  → Indicates: Injection/Infusion")
                    elif any(r in route_lower for r in ['topical', 'ophthalmic', 'nasal', 'dermal']):
                        lines.append(f"  → Indicates: Topical")
                    elif 'oral' in route_lower:
                        lines.append(f"  → Indicates: Oral")
                
                product_types = openfda_info.get("product_type", [])
                if product_types:
                    lines.append(f"  Product Type: {', '.join(product_types)}")
                
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
                    snippet = self._truncate_text(snippet, TruncationLimits.SNIPPET)
                    lines.append(f"  Snippet: {snippet}")
                lines.append("")
        
        if not has_data:
            return ""
        
        return "\n".join(lines)
    
    def _format_pubmed_data(self, results: Dict[str, Any]) -> str:
        """
        Format PubMed data.

        Returns:
            Formatted PubMed data string, or guidance if unavailable
        """
        # Get sources - try both possible paths
        sources = results.get("sources", {})
        if not sources:
            sources = results.get("results", {}).get("sources", {})

        pubmed_source = sources.get("pubmed", {})

        if not pubmed_source.get("success"):
            logger.debug("PubMed source not available or unsuccessful")
            return """**PubMed Literature: NOT AVAILABLE**

**IMPACT:** No published literature context for this trial.
**GUIDANCE:** Rely on ClinicalTrials.gov descriptions for classification evidence.
"""

        pubmed_data = pubmed_source.get("data", {})
        articles = pubmed_data.get("articles", [])

        if not articles:
            logger.debug("No PubMed articles found")
            return """**PubMed Literature: No articles found**

**NOTE:** No published literature directly linked to this trial.
This is common for newer or smaller trials. Proceed with other data sources.
"""

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
                abstract = self._truncate_text(abstract, TruncationLimits.ABSTRACT)
                lines.append(f"**Abstract:** {abstract}")

                # Check for antimicrobial content using shared constant
                found_terms = [term for term in ANTIMICROBIAL_KEYWORDS if term.lower() in abstract.lower()]
                # Also check for MIC which is specific to literature
                if 'mic' in abstract.lower() or 'minimum inhibitory' in abstract.lower():
                    found_terms.append('MIC/minimum inhibitory')
                if found_terms:
                    lines.append(f"*** ANTIMICROBIAL CONTENT: {', '.join(found_terms)} ***")

            lines.append("")

        return "\n".join(lines)
    
    def _format_pmc_data(self, results: Dict[str, Any]) -> str:
        """
        Format PMC data.

        Returns:
            Formatted PMC data string, or empty string if unavailable
        """
        # Get sources - try both possible paths
        sources = results.get("sources", {})
        if not sources:
            sources = results.get("results", {}).get("sources", {})

        pmc_source = sources.get("pmc", {})

        if not pmc_source.get("success"):
            logger.debug("PMC source not available or unsuccessful")
            return ""

        pmc_data = pmc_source.get("data", {})
        articles = pmc_data.get("articles", [])

        if not articles:
            logger.debug("No PMC articles found")
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
                abstract = self._truncate_text(abstract, TruncationLimits.PMC_ABSTRACT)
                lines.append(f"**Abstract:** {abstract}")

            lines.append("")

        return "\n".join(lines)
    
    def _format_bioc_data(self, results: Dict[str, Any]) -> str:
        """
        Format BioC data.

        Returns:
            Formatted BioC data string, or empty string if unavailable
        """
        # Get sources - try both possible paths
        sources = results.get("sources", {})
        if not sources:
            sources = results.get("results", {}).get("sources", {})

        bioc_source = sources.get("pmc_bioc", {})

        if not bioc_source.get("success"):
            logger.debug("BioC source not available or unsuccessful")
            return ""

        bioc_data = bioc_source.get("data", {})
        articles = bioc_data.get("articles", [])

        if not articles:
            logger.debug("No BioC articles found")
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

                    for passage in passages[:2]:
                        passage_type = passage.get("infons", {}).get("type", "text")
                        text = passage.get("text", "")

                        if text:
                            text = self._truncate_text(text, TruncationLimits.BIOC_PASSAGE)
                            lines.append(f"\n*{passage_type.title()}:*")
                            lines.append(text)

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