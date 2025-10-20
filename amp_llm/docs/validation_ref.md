# Clinical Trial Data Validation Reference

## Overview

All extracted clinical trial data is validated against strict controlled vocabularies to ensure consistency and data quality. This document lists all valid values for each validated field.

## Validated Fields

### 1. Study Status

**Field**: `study_status`  
**Type**: Single value (choose ONE)  
**Description**: Current status of the clinical trial

| Valid Value | Description |
|-------------|-------------|
| `NOT_YET_RECRUITING` | Trial approved but not yet recruiting participants |
| `RECRUITING` | Currently recruiting participants |
| `ENROLLING_BY_INVITATION` | Only enrolling invited/pre-selected participants |
| `ACTIVE_NOT_RECRUITING` | Trial ongoing but no longer recruiting |
| `COMPLETED` | Trial has completed |
| `SUSPENDED` | Trial temporarily paused |
| `TERMINATED` | Trial stopped early |
| `WITHDRAWN` | Trial withdrawn before enrollment |
| `UNKNOWN` | Status cannot be determined |

**Example**: `Study Status: COMPLETED`

---

### 2. Phases

**Field**: `phases`  
**Type**: List (can have multiple values)  
**Description**: Clinical trial phase(s)

| Valid Value | Description |
|-------------|-------------|
| `EARLY_PHASE1` | Early Phase 1 (formerly Phase 0) |
| `PHASE1` | Phase 1 - Safety/dosage |
| `PHASE1\|PHASE2` | Combined Phase 1/2 |
| `PHASE2` | Phase 2 - Efficacy and side effects |
| `PHASE2\|PHASE3` | Combined Phase 2/3 |
| `PHASE3` | Phase 3 - Efficacy vs standard treatment |
| `PHASE4` | Phase 4 - Post-marketing surveillance |

**Example**: `Phases: PHASE1, PHASE2`  
**Example**: `Phases: PHASE2|PHASE3`

---

### 3. Classification

**Field**: `classification`  
**Type**: Single value (choose ONE)  
**Description**: Type of intervention being studied

| Valid Value | When to Use |
|-------------|-------------|
| `AMP` | Antimicrobial peptide study treating infections, sepsis, bacterial/fungal diseases |
| `AMP` | Antimicrobial peptide study for non-infection purposes (metabolism, cancer, wound healing, etc.) |
| `Other` | Not an antimicrobial peptide study (traditional drugs, biologics, devices, etc.) |

**Decision Tree**:
```
Is study about peptides/AMPs?
├─ YES: Does it treat infections?
│   ├─ YES → AMP(infection)
│   └─ NO → AMP(other)
└─ NO → Other
```

**Examples**:
- AMP for sepsis → `AMP`
- AMP for diabetes → `AMP`
- Non-antimicrobial peptide drug for diabetes → `Other`
- LEAP-2 for glucose regulation → `AMP`

---

### 4. Delivery Mode

**Field**: `delivery_mode`  
**Type**: Single value (choose ONE)  
**Description**: How the intervention is administered

#### Injection/Infusion

| Valid Value | When to Use |
|-------------|-------------|
| `Injection/Infusion - Intramuscular` | IM injection |
| `Injection/Infusion - Subcutaneous/Intradermal` | SubQ or intradermal injection |
| `Injection/Infusion - Other/Unspecified` | Injection but route not specified |
| `IV` | Intravenous infusion |

#### Oral

| Valid Value | When to Use |
|-------------|-------------|
| `Oral - Tablet` | Tablet form |
| `Oral - Capsule` | Capsule form |
| `Oral - Food` | Mixed in food |
| `Oral - Drink` | Liquid/beverage form |
| `Oral - Unspecified` | Oral but form not specified |

#### Topical

| Valid Value | When to Use |
|-------------|-------------|
| `Topical - Cream/Gel` | Cream or gel application |
| `Topical - Powder` | Powder form |
| `Topical - Spray` | Spray application |
| `Topical - Strip/Covering` | Adhesive strips, patches, bandages |
| `Topical - Wash` | Wash or rinse |
| `Topical - Unspecified` | Topical but type not specified |

#### Other

| Valid Value | When to Use |
|-------------|-------------|
| `Intranasal` | Nasal spray or drops |
| `Inhalation` | Inhaled via nebulizer or inhaler |
| `Other/Unspecified` | Route not listed above or unclear |

**Examples**:
- Peptide infused over 180 minutes → `IV`
- Antibiotic pill → `Oral - Tablet`
- Wound gel with AMP → `Topical - Cream/Gel`
- Nasal AMP spray → `Intranasal`

---

### 5. Outcome

**Field**: `outcome`  
**Type**: Single value (choose ONE)  
**Description**: Result or current state of the trial

| Valid Value | When to Use |
|-------------|-------------|
| `Positive` | Trial completed successfully with positive results |
| `Failed - completed trial` | Trial completed but did not meet primary endpoints |
| `Terminated` | Trial ended early (before completion) |
| `Withdrawn` | Trial withdrawn before enrollment |
| `Recruiting` | Currently recruiting participants |
| `Active, not recruiting` | Trial ongoing but closed to enrollment |
| `Unknown` | Outcome not yet known or unclear |

**Mapping from Status**:
- `COMPLETED` → Usually `Positive` (check results)
- `TERMINATED` → `Terminated`
- `WITHDRAWN` → `Withdrawn`
- `RECRUITING` → `Recruiting`
- `ACTIVE_NOT_RECRUITING` → `Active, not recruiting`

**Examples**:
- Trial finished, met endpoints → `Positive`
- Trial finished, failed to meet endpoints → `Failed - completed trial`
- Trial stopped early for safety → `Terminated`
- Trial stopped before starting → `Withdrawn`

---

### 6. Reason for Failure/Withdrawal

**Field**: `failure_reason`  
**Type**: Single value (choose ONE)  
**Description**: Why trial failed, terminated, or was withdrawn

| Valid Value | When to Use |
|-------------|-------------|
| `Business Reason` | Sponsor decision, funding issues, strategic reasons |
| `Ineffective for purpose` | Intervention not showing efficacy |
| `Toxic/Unsafe` | Safety concerns, adverse events |
| `Due to covid` | COVID-19 pandemic impact |
| `Recruitment issues` | Unable to enroll sufficient participants |
| `N/A` | Trial not failed/terminated/withdrawn |

**Usage**:
- Only applicable when Outcome is: `Terminated`, `Withdrawn`, or `Failed - completed trial`
- For successful/ongoing trials, use: `N/A`

**Examples**:
- Trial stopped for adverse events → `Toxic/Unsafe`
- Couldn't find enough patients → `Recruitment issues`
- Pandemic disruption → `Due to covid`
- Company shut down program → `Business Reason`
- No efficacy signal in interim analysis → `Ineffective for purpose`

---

### 7. Peptide

**Field**: `is_peptide`  
**Type**: Boolean (True or False only)  
**Description**: Whether the study involves peptides or AMPs

| Valid Value | When to Use |
|-------------|-------------|
| `True` | Study involves peptides, AMPs, protein fragments |
| `False` | Study does NOT involve peptides |

**Detection Keywords**:
- Peptide, polypeptide
- AMP, antimicrobial peptide
- DRAMP database reference
- Sequence data (amino acid sequences)
- Protein fragment

**Examples**:
- LEAP-2 study → `True`
- LL-37 study → `True`
- Traditional antibiotic (azithromycin) → `False`
- Monoclonal antibody → `False` (full antibody, not peptide)

---

## Validation in Practice

### Command Line

```bash
Research >>> validate

📋 Valid Values for All Fields:

Study Status (choose ONE):
  • NOT_YET_RECRUITING
  • RECRUITING
  ...

[Shows all valid values]
```

### Automated Validation

The system automatically:
1. **Validates on extraction**: Checks values when creating `ClinicalTrialExtraction`
2. **Fuzzy matching**: Attempts to match similar values (e.g., "Phase 1" → "PHASE1")
3. **Warnings**: Shows validation warnings if values don't match
4. **Logging**: Logs validation issues for review

### Validation Errors

If extraction has invalid values:

```
⚠️  Validation warnings:
  • Invalid study_status: 'active' (must be one of: NOT_YET_RECRUITING, RECRUITING, ...)
  • Invalid delivery_mode: 'oral' (must be one of: Oral - Tablet, Oral - Capsule, ...)
```

---

## Examples by Trial Type

### Example 1: Completed AMP Infection Trial

```
NCT Number: NCT12345678
Study Status: COMPLETED
Phases: PHASE2
Classification: AMP(infection)
Delivery Mode: IV
Outcome: Positive
Reason for Failure: N/A
Peptide: True
```

### Example 2: Terminated AMP Metabolic Trial

```
NCT Number: NCT87654321
Study Status: TERMINATED
Phases: EARLY_PHASE1
Classification: AMP(other)
Delivery Mode: Injection/Infusion - Subcutaneous/Intradermal
Outcome: Terminated
Reason for Failure: Recruitment issues
Peptide: True
```

### Example 3: Recruiting Non-Peptide Trial

```
NCT Number: NCT11223344
Study Status: RECRUITING
Phases: PHASE3
Classification: Other
Delivery Mode: Oral - Tablet
Outcome: Recruiting
Reason for Failure: N/A
Peptide: False
```

---

## Best Practices

### For Manual Entry

1. **Copy exact values** from this document
2. **Match capitalization** exactly (e.g., `PHASE1` not `Phase1`)
3. **Use pipe character** for combined phases (e.g., `PHASE1|PHASE2`)
4. **Include parentheses** in classification (e.g., `AMP(infection)`)
5. **Boolean values** must be `True` or `False` (not `Yes`/`No`)

### For AI Extraction

The Modelfile includes these validation rules, so the AI should:
1. Use exact values from validation lists
2. Choose most specific delivery mode available
3. Classify AMPs correctly based on purpose
4. Map status to appropriate outcome
5. Provide failure reason only when applicable

### For Database Import

When importing external data:
```python
from data.clinical_trial_rag import validate_enum_value, StudyStatus

# Validate before creating extraction
status = validate_enum_value(raw_status, StudyStatus, "study_status")
```

---

## Troubleshooting

### "Invalid study_status" Error

**Problem**: Value doesn't match enum  
**Solution**: Check exact spelling and capitalization

```
❌ study_status: 'completed' 
✅ study_status: 'COMPLETED'
```

### "Invalid delivery_mode" Error

**Problem**: Value too generic  
**Solution**: Use most specific option

```
❌ delivery_mode: 'oral'
✅ delivery_mode: 'Oral - Tablet'
```

### "Invalid classification" Error

**Problem**: Missing parentheses  
**Solution**: Include exact formatting

```
❌ classification: 'AMP infection'
✅ classification: 'AMP(infection)'
```

---

## Updating Valid Values

To add new valid values:

1. Edit `data/clinical_trial_rag.py`
2. Add to appropriate Enum class:
   ```python
   class DeliveryMode(str, Enum):
       # Existing values...
       NEW_MODE = "New - Mode"
   ```
3. Update `Modelfile` validation section
4. Update this documentation
5. Rebuild custom model

---

## Reference Card

```
┌──────────────────────────────────────────┐
│ VALIDATION QUICK REFERENCE               │
├──────────────────────────────────────────┤
│ Status: COMPLETED, RECRUITING, etc.      │
│ Phases: PHASE1, PHASE2, PHASE1|PHASE2    │
│ Classification: AMP(infection),          │
│                 AMP(other), Other        │
│ Delivery: IV, Oral - Tablet, etc.        │
│ Outcome: Positive, Terminated, etc.      │
│ Failure: Toxic/Unsafe, Recruitment, N/A  │
│ Peptide: True or False                   │
└──────────────────────────────────────────┘
```

Use `validate` command in Research Assistant to see full lists anytime!
