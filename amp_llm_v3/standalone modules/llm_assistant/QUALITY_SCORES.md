# Quality Score System Documentation

## Overview

The quality score system measures data completeness for clinical trial annotation. It helps the LLM understand when data is insufficient and guides fallback behavior.

There are **two types of quality scores**:

1. **Source-Level Quality Score** (in `prompt_generator.py`)
   - Measures which data sources successfully returned data
   - Used to assess overall data availability before annotation

2. **Field-Level Quality Score** (in `json_parser.py`)
   - Measures data completeness for each annotation field
   - Used to warn when specific fields may have unreliable annotations

---

## Source-Level Weights

These weights determine how much each data source contributes to the overall quality score.

### Default Weights and Reasoning

| Source | Default Weight | Reasoning |
|--------|----------------|-----------|
| `clinical_trials` | **0.40** | Primary authoritative source. Contains trial status, interventions, outcomes, conditions, and all core metadata. Most critical for accurate annotation. |
| `pubmed` | **0.15** | Published literature provides scientific context and validation. Important for classification decisions and understanding drug mechanisms. |
| `uniprot` | **0.15** | Critical for protein/peptide identification and sequence data. Required for the Sequence field and strongly influences Peptide determination. |
| `pmc` | **0.10** | Full-text articles from PubMed Central provide deeper context than abstracts alone. Moderately important for evidence extraction. |
| `openfda` | **0.05** | FDA drug database provides official drug information including approved routes of administration. Helpful for Delivery Mode but supplementary. |
| `duckduckgo` | **0.05** | Web search provides supplementary context from various sources. Lower weight due to variable reliability and potential for irrelevant results. |
| `dramp` | **0.05** | DRAMP antimicrobial peptide database. Highly specific - if a drug appears in DRAMP, it's almost certainly an antimicrobial peptide (strong AMP indicator). |
| `pmc_bioc` | **0.05** | BioC-annotated data provides structured entity extraction from PMC articles. Supplementary to raw PMC text. |
| `serpapi` | **0.00** | Paid API (Google Search). Disabled by default. Set >0 if you have an API key configured. |
| `scholar` | **0.00** | Paid API (Google Scholar). Disabled by default. Set >0 if you have an API key configured. |

### Why These Weights?

1. **ClinicalTrials.gov (40%)** is weighted highest because:
   - It's the authoritative source for trial status (determines Outcome)
   - Contains intervention details (determines Delivery Mode, Peptide)
   - Has official conditions and keywords (influences Classification)
   - Without it, most annotations become unreliable

2. **PubMed + UniProt (15% each)** are the next tier because:
   - PubMed validates clinical findings with published research
   - UniProt is essential for protein/peptide identification
   - Together they provide scientific validation

3. **Extended sources (5% each)** are supplementary:
   - Provide additional context but aren't authoritative
   - DRAMP is highly specific when available
   - Web/FDA data fills gaps but has lower reliability

---

## Field-Level Weights

These weights determine importance of individual data fields for each annotation task.

### Classification Weights

Used to determine AMP vs Other:

| Field | Default Weight | Reasoning |
|-------|----------------|-----------|
| `brief_summary` | **0.25** | Often contains mechanism description (e.g., "antimicrobial", "kills bacteria") |
| `brief_title` | **0.15** | Drug name and indication in title help classification |
| `conditions` | **0.15** | Target conditions (infections vs metabolic disease) indicate AMP likelihood |
| `keywords` | **0.10** | May contain "antimicrobial", "peptide" keywords |
| `detailed_description` | **0.10** | Additional mechanism details |
| `interventions` | **0.05** | Drug type (DRUG vs BIOLOGICAL) provides hints |
| Others | **0.05** each | Supporting context |

### Delivery Mode Weights

Used to determine Injection/Infusion, Topical, Oral, or Other:

| Field | Default Weight | Reasoning |
|-------|----------------|-----------|
| `interventions` | **0.35** | Intervention descriptions often contain route keywords |
| `arm_groups` | **0.25** | Arm descriptions may specify administration method |
| `brief_summary` | **0.15** | Sometimes mentions "administered topically" etc. |
| Others | **0.05-0.10** | Supporting context |

### Outcome Weights

Used to determine trial result status:

| Field | Default Weight | Reasoning |
|-------|----------------|-----------|
| `overall_status` | **0.35** | Primary determinant - directly maps to Outcome |
| `why_stopped` | **0.15** | Critical for Withdrawn/Terminated trials |
| `has_results` | **0.10** | Determines if we can assess Positive vs Failed |
| `completion_date` | **0.10** | Helps validate status |
| Others | **0.05** each | Supporting context |

### Failure Reason Weights

Used only when Outcome is Withdrawn/Terminated/Failed:

| Field | Default Weight | Reasoning |
|-------|----------------|-----------|
| `why_stopped` | **0.45** | Primary/only source for failure reason |
| `overall_status` | **0.25** | Validates that trial actually failed |
| Others | **0.05** each | Supporting context |

### Peptide Weights

Used to determine True/False for peptide status:

| Field | Default Weight | Reasoning |
|-------|----------------|-----------|
| `interventions` | **0.25** | Drug name is key indicator ("-tide" suffix, known peptides) |
| `brief_summary` | **0.20** | May describe drug as "peptide therapeutic" |
| `brief_title` | **0.15** | Drug name in title |
| `keywords` | **0.15** | May contain "peptide" keyword |
| Others | **0.05-0.10** | Supporting context |

---

## API Usage

### Get Current Weights
```bash
GET /quality-weights
```

### Get Default Weights
```bash
GET /quality-weights/defaults
```

### Update Weights
```bash
POST /quality-weights
Content-Type: application/json

{
    "source_weights": {
        "clinical_trials": 0.5,
        "pubmed": 0.2
    }
}
```

### Reset to Defaults
```bash
POST /quality-weights/reset
```

### View Documentation
```bash
GET /quality-weights/docs
```

---

## When to Adjust Weights

### Increase a Source Weight When:
- The source is highly reliable for your use case
- The source provides unique information not available elsewhere
- You have high-quality data consistently from this source

### Decrease a Source Weight When:
- The source is unreliable or returns inconsistent data
- The source data is often incomplete or irrelevant
- The source is less important for your annotation focus

### Example Scenarios

**Scenario 1: Focus on peptide therapeutics**
```json
{
    "source_weights": {
        "uniprot": 0.25,
        "dramp": 0.15,
        "openfda": 0.02
    }
}
```

**Scenario 2: Only using ClinicalTrials.gov**
```json
{
    "source_weights": {
        "clinical_trials": 1.0,
        "pubmed": 0.0,
        "uniprot": 0.0,
        "pmc": 0.0
    }
}
```

**Scenario 3: Literature-heavy analysis**
```json
{
    "source_weights": {
        "pubmed": 0.25,
        "pmc": 0.20,
        "clinical_trials": 0.30
    }
}
```

---

## Quality Score Interpretation

| Score Range | Interpretation |
|-------------|----------------|
| 0.7 - 1.0 | **Excellent** - All or most critical sources available |
| 0.5 - 0.7 | **Good** - Core sources available, some gaps |
| 0.3 - 0.5 | **Fair** - Missing important sources, annotations may be less reliable |
| 0.0 - 0.3 | **Poor** - Critical data missing, high risk of incorrect annotations |

When quality score is low, the system:
1. Adds warnings to the prompt
2. Instructs the LLM to use fallback values
3. Includes explicit guidance for each field

---

## Implementation Details

### Source Weights Location
- File: `prompt_generator.py`
- Class: `ImprovedPromptGenerator`
- Attribute: `DEFAULT_SOURCE_WEIGHTS`
- Runtime: `self.source_weights`

### Field Weights Location
- File: `json_parser.py`
- Class: `ClinicalTrialAnnotationParser`
- Attribute: `DEFAULT_FIELD_WEIGHTS`
- Runtime: `self.field_weights`

### Calculation Methods
- Source score: `sum(weight for source in available_sources)`
- Field score: `sum(weight for field if field has data) / sum(all weights)`
