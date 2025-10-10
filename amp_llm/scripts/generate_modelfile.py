"""
Dynamic Modelfile Generator
Generates Modelfile from validation_config.py to ensure single source of truth.

Usage:
    python generate_modelfile.py [--base llama3.2] [--output Modelfile]
"""
import argparse
from pathlib import Path
from validation_config import get_validation_config


MODELFILE_TEMPLATE = """# Clinical Trial Research Assistant Modelfile
# AUTO-GENERATED from validation_config.py
# DO NOT EDIT MANUALLY - Run generate_modelfile.py to regenerate
# validation_config_hash: {config_hash}

FROM {base_model}

SYSTEM \"\"\"You are a Clinical Trial Data Extraction Specialist. Extract structured information from clinical trial JSON data.

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
Classification: AMP(other)
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

{validation_rules}

## EXTRACTION GUIDELINES

**Status to Outcome mapping:**
{outcome_mapping}

**Peptide detection:**
Look for: {peptide_keywords}

**Classification logic:**
- If peptide AND treats infection → AMP(infection)
- If peptide BUT other purpose → AMP(other)
- If not peptide → Other

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

Now extract the clinical trial data following this exact format with actual data.\"\"\"

# Optimized parameters
PARAMETER temperature {temperature}
PARAMETER top_p {top_p}
PARAMETER top_k {top_k}
PARAMETER repeat_penalty {repeat_penalty}
PARAMETER num_ctx {num_ctx}
PARAMETER num_predict {num_predict}

# Stop sequences
PARAMETER stop "<|eot_id|>"
PARAMETER stop "<|end_of_text|>"
PARAMETER stop "</s>"
"""


def format_validation_rules(config) -> str:
    """Format validation rules for Modelfile."""
    lines = []
    
    all_values = config.get_all_valid_values()
    
    for field_name, values in all_values.items():
        lines.append(f"**{field_name}** (choose ONE):")
        for value in values:
            lines.append(f"{value} | ", end="")
        # Remove last separator and add newline
        lines[-1] = lines[-1].rstrip(" | ")
        lines.append("")
    
    return "\n".join(lines)


def format_outcome_mapping(config) -> str:
    """Format outcome mapping for Modelfile."""
    lines = []
    
    for status, outcome in config.status_to_outcome.items():
        lines.append(f"- {status.upper()} → {outcome}")
    
    return "\n".join(lines)


def format_peptide_keywords(config) -> str:
    """Format peptide keywords for Modelfile."""
    return ", ".join(config.peptide_keywords)


def generate_modelfile(
    base_model: str = "llama3.2",
    output_path: Path = Path("Modelfile"),
    temperature: float = 0.15,
    top_p: float = 0.9,
    top_k: int = 40,
    repeat_penalty: float = 1.2,
    num_ctx: int = 8192,
    num_predict: int = 2048
) -> str:
    """
    Generate Modelfile from validation config.
    
    Args:
        base_model: Base model name
        output_path: Where to save Modelfile
        temperature: Model temperature
        top_p: Top-p sampling
        top_k: Top-k sampling
        repeat_penalty: Repetition penalty
        num_ctx: Context window size
        num_predict: Max tokens to generate
        
    Returns:
        Generated Modelfile content
    """
    config = get_validation_config()
    
    # Get current hash before generation
    import hashlib
    config_path = Path("validation_config.py")
    if config_path.exists():
        config_hash = hashlib.md5(config_path.read_text(encoding='utf-8').encode()).hexdigest()
    else:
        config_hash = "unknown"
    
    # Format validation rules
    validation_rules = format_validation_rules(config)
    outcome_mapping = format_outcome_mapping(config)
    peptide_keywords = format_peptide_keywords(config)
    
    # Generate Modelfile
    modelfile_content = MODELFILE_TEMPLATE.format(
        config_hash=config_hash,
        base_model=base_model,
        validation_rules=validation_rules,
        outcome_mapping=outcome_mapping,
        peptide_keywords=peptide_keywords,
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
        repeat_penalty=repeat_penalty,
        num_ctx=num_ctx,
        num_predict=num_predict
    )
    
    return modelfile_content


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate Modelfile from validation_config.py"
    )
    parser.add_argument(
        "--base",
        default="llama3.2",
        help="Base model name (default: llama3.2)"
    )
    parser.add_argument(
        "--output",
        default="Modelfile",
        help="Output file path (default: Modelfile)"
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.15,
        help="Model temperature (default: 0.15)"
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Preview without saving"
    )
    
    args = parser.parse_args()
    
    print("🔧 Generating Modelfile from validation_config.py...")
    print(f"   Base model: {args.base}")
    print(f"   Temperature: {args.temperature}")
    
    # Generate
    modelfile_content = generate_modelfile(
        base_model=args.base,
        output_path=Path(args.output),
        temperature=args.temperature
    )
    
    if args.preview:
        print("\n" + "="*60)
        print("PREVIEW:")
        print("="*60)
        print(modelfile_content)
        print("="*60)
        print("\nTo save, run without --preview")
    else:
        # Save
        output_path = Path(args.output)
        
        # Backup existing if present
        if output_path.exists():
            backup_path = output_path.with_suffix('.modelfile.backup')
            print(f"📦 Backing up existing Modelfile to {backup_path}")
            output_path.rename(backup_path)
        
        output_path.write_text(modelfile_content, encoding='utf-8')
        
        print(f"✅ Generated {output_path}")
        print(f"   Size: {len(modelfile_content)} bytes")
        print(f"\n💡 Next steps:")
        print(f"   1. Review the file: cat {output_path}")
        print(f"   2. Build model: python main.py (select Research Assistant)")
        print(f"   3. Or manually: ollama create ct-research-assistant -f {output_path}")


if __name__ == "__main__":
    main()