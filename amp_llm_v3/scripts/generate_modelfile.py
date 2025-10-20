# scripts/generate_modelfile.py
"""
Dynamic Modelfile Generator
Generates Modelfile from validation_config.py to ensure single source of truth.

Usage:
    python scripts/generate_modelfile.py [--base llama3.2] [--output Modelfile]
"""
import argparse
from pathlib import Path


def generate_modelfile(base_model: str = "llama3.2") -> str:
    """
    Generate Modelfile content.
    
    Args:
        base_model: Base model to use (default: llama3.2)
        
    Returns:
        Complete Modelfile content as string
    """
    
    # Try to import validation config
    try:
        from amp_llm.config.validation import get_validation_config
        config = get_validation_config()
        has_validation = True
    except ImportError:
        has_validation = False
    
    # Build validation rules section
    if has_validation:
        validation_rules = []
        
        # Study Status
        statuses = config.get_valid_values('study_status')
        validation_rules.append("**Study Status values:**")
        validation_rules.extend([f"- {s}" for s in statuses])
        
        # Phases
        phases = config.get_valid_values('phase')
        validation_rules.append("\n**Phase values:**")
        validation_rules.extend([f"- {p}" for p in phases])
        
        # Classification
        classifications = config.get_valid_values('classification')
        validation_rules.append("\n**Classification values:**")
        validation_rules.extend([f"- {c}" for c in classifications])
        
        # Delivery Mode
        delivery_modes = config.get_valid_values('delivery_mode')
        validation_rules.append("\n**Delivery Mode values:**")
        validation_rules.extend([f"- {d}" for d in delivery_modes])
        
        # Outcome
        outcomes = config.get_valid_values('outcome')
        validation_rules.append("\n**Outcome values:**")
        validation_rules.extend([f"- {o}" for o in outcomes])
        
        # Failure Reason
        failure_reasons = config.get_valid_values('failure_reason')
        validation_rules.append("\n**Reason for Failure values:**")
        validation_rules.extend([f"- {r}" for r in failure_reasons])
        
        validation_section = "\n".join(validation_rules)
    else:
        validation_section = "<!-- Validation config not available -->"
    
    # Build outcome mapping section
    outcome_mapping = """- COMPLETED/FINISHED → Positive
- RECRUITING/ENROLLING → Recruiting  
- ACTIVE_NOT_RECRUITING/ONGOING → Active, not recruiting
- TERMINATED/STOPPED → Terminated
- WITHDRAWN/CANCELLED → Withdrawn
- UNKNOWN/UNAVAILABLE → Unknown"""
    
    # Build peptide keywords section
    peptide_keywords = "amp, antimicrobial peptide, dramp"
    
    # Generate complete Modelfile
    modelfile = f'''# Clinical Trial Research Assistant Modelfile
# Generated from validation_config.py
FROM {base_model}

SYSTEM """You are a Clinical Trial Data Extraction Specialist. Extract structured information from clinical trial JSON data.

## OUTPUT FORMAT

Format your response EXACTLY like this (use actual data, NOT placeholders):

NCT Number: NCT07013110
Study Title: An Artificial Intelligence-powered Approach to Precision Immunotherapy
Study Status: RECRUITING
Brief Summary: This clinical study is a multi-center, randomized study...
Conditions: Rheumatoid Arthritis, Rheumatology
Interventions/Drug: Biological: dnaJP1, Other: Hydroxychloroquine, Placebo
Phases: PHASE2
Enrollment: 124
Start Date: 2025-06-18
Completion Date: 2028-11
Classification: AMP
  Evidence: Study involves antimicrobial peptide for non-infection purposes
Delivery Mode: Oral - Tablet
Sequence: N/A
DRAMP Name: dnaJP1
  Evidence: DRAMP database entry for dnaJP1
Study IDs: PMC:11855921
Outcome: Recruiting
Reason for Failure: N/A
Subsequent Trial IDs: N/A
  Evidence: N/A
Peptide: True
Comments: Early-phase trial investigating immunotherapy effects

## CRITICAL RULES

1. Use ACTUAL data from the trial, NOT placeholder text like [title here] or [PHASE#]
2. Do NOT wrap response in markdown code blocks (no ```)
3. Write values directly without brackets [ ]
4. For missing data, write exactly: N/A
5. Use EXACT values from validation lists below

## VALID VALUES

{validation_section}

## EXTRACTION GUIDELINES

**Status to Outcome mapping:**
{outcome_mapping}

**Peptide detection:**
Look for: {peptide_keywords}

**Classification logic:**
- If a peptide and antimicrobial via direct killing or immunomodulation → AMP
- If a peptide and not antimicrovial → Other

**Outcome logic**
- if a trial is RECRUITING, ENROLLING, ACTIVE, NOT RECRUITING → Active
- if a trial has completed and a peer reviewed publication, company newsletter, or biotech news article indicates safety and efficicacy -> Positive
- if a trial has completed and a peer reviewed publication, company newsletter, or biotech news article indicates toxicity or lack of efficacy -> Failed - completed trial
- if a trial is terminated or withdrawn → Terminated or Withdrawn
- if a trial has compelted with no relevant publications or news articles → Unknown

**Failure reason logic**
- Only provide a reason if the outcome is Terminated, Withdrawn or Failed - completed trial
- If a trial has failed due to financial reasons, issues with the company, or strategic pivots → Business Reason
- If a trial has failed due to lack of efficacy or not meeting endpoints → Ineffective for purpose
- If a trial has failed due to safety concerns, adverse events, or toxicity → Toxic/Unsafe
- If a trial struggled to recruit participants due to general recruitment issues → Recruitment issues
- If you are unsure → Unknown
- If the outcome is not Terminated, Withdrawn or Failed - completed trial → N/A

**DO NOT:**
- Use placeholder text like [title here], [PHASE#], [condition1, condition2]
- Wrap output in code blocks
- Include brackets in actual data
- Leave fields blank (use N/A instead)

**DO:**
- Extract actual values from the JSON
- Write values directly without formatting
- Use exact validation list values
- Provide clear evidence for classifications

Now extract the clinical trial data following this exact format with actual data."""

# Optimized parameters
PARAMETER temperature 0.15
PARAMETER top_p 0.9
PARAMETER top_k 40
PARAMETER repeat_penalty 1.2
PARAMETER num_ctx 8192
PARAMETER num_predict 2048

# Stop sequences
PARAMETER stop "<|eot_id|>"
PARAMETER stop "<|end_of_text|>"
PARAMETER stop "</s>"
'''
    
    return modelfile


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate Modelfile for Clinical Trial Research Assistant"
    )
    parser.add_argument(
        "--base",
        default="llama3.2",
        help="Base model to use (default: llama3.2)"
    )
    parser.add_argument(
        "--output",
        default="Modelfile",
        help="Output file path (default: Modelfile)"
    )
    
    args = parser.parse_args()
    
    # Generate Modelfile
    print(f"Generating Modelfile with base model: {args.base}")
    content = generate_modelfile(base_model=args.base)
    
    # Write to file
    output_path = Path(args.output)
    output_path.write_text(content, encoding='utf-8')
    
    print(f"✅ Modelfile generated successfully: {output_path}")
    print(f"   Base model: {args.base}")
    print(f"   Size: {len(content)} characters")


if __name__ == "__main__":
    main()