#!/usr/bin/env python3
"""
Standalone CLI Two-Step Annotation Tool
========================================

Performs clinical trial annotation locally using ollama models, with an optional
verification step by a second model (e.g., nemotron).

No web services required - fetches trial data directly from ClinicalTrials.gov
and other APIs, calls ollama directly for LLM inference.

Usage:
    python cli_annotate.py \
        --input /path/to/nct_ids.csv \
        --output /path/to/results.csv \
        --model llama3:latest \
        --verification-model nemotron:latest

    # Skip verification step:
    python cli_annotate.py \
        --input nct_ids.csv --output results.csv \
        --model llama3:latest --no-verify

    # Include extended data sources (UniProt, PubMed, etc.):
    python cli_annotate.py \
        --input nct_ids.csv --output results.csv \
        --model llama3:latest --verification-model nemotron:latest \
        --extended-sources
"""

import sys
import os
import re
import csv
import io
import json
import time
import asyncio
import argparse
import logging
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Setup sys.path so we can import sibling standalone modules
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent.resolve()
STANDALONE_DIR = SCRIPT_DIR.parent  # "standalone modules"
NCT_LOOKUP_DIR = STANDALONE_DIR / "nct_lookup"
LLM_ASSISTANT_DIR = STANDALONE_DIR / "llm_assistant"

# Add module directories to sys.path
for module_dir in [NCT_LOOKUP_DIR, LLM_ASSISTANT_DIR]:
    dir_str = str(module_dir)
    if dir_str not in sys.path:
        sys.path.insert(0, dir_str)

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Suppress noisy loggers from imported modules
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# Lazy imports from sibling modules (done after sys.path setup)
# ---------------------------------------------------------------------------
try:
    from nct_core import NCTSearchEngine
    from nct_models import SearchConfig
    HAS_NCT_ENGINE = True
except ImportError as e:
    logger.warning(f"Could not import NCT search engine: {e}")
    HAS_NCT_ENGINE = False

try:
    from json_parser import ClinicalTrialAnnotationParser
    HAS_JSON_PARSER = True
except ImportError as e:
    logger.warning(f"Could not import JSON parser: {e}")
    HAS_JSON_PARSER = False

try:
    from prompt_generator import PromptGenerator
    HAS_PROMPT_GEN = True
except ImportError as e:
    logger.warning(f"Could not import PromptGenerator: {e}")
    HAS_PROMPT_GEN = False

# We import specific classes from llm_assistant carefully to avoid
# triggering the FastAPI app initialization
try:
    from llm_assistant import (
        TrialAnnotator,
        AnnotationResponseParser,
        AssistantConfig,
        config as llm_config,
    )
    HAS_LLM_ASSISTANT = True
except ImportError as e:
    logger.warning(f"Could not import LLM assistant: {e}")
    HAS_LLM_ASSISTANT = False


# ============================================================================
# CLI Argument Parsing
# ============================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Standalone CLI for two-step clinical trial annotation with LLM verification.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic annotation + verification:
  python cli_annotate.py -i trials.csv -o results.csv -m llama3:latest -v nemotron:latest

  # Annotation only (no verification):
  python cli_annotate.py -i trials.csv -o results.csv -m llama3:latest --no-verify

  # With extended sources (PubMed, UniProt, etc.):
  python cli_annotate.py -i trials.csv -o results.csv -m llama3:latest -v nemotron:latest --extended-sources
        """
    )

    parser.add_argument(
        "-i", "--input",
        required=True,
        help="Path to input CSV file containing NCT IDs"
    )
    parser.add_argument(
        "-o", "--output",
        required=True,
        help="Path for the output CSV file"
    )
    parser.add_argument(
        "-m", "--model",
        default="llama3:latest",
        help="Primary annotation model (default: llama3:latest)"
    )
    parser.add_argument(
        "-v", "--verification-model",
        default="nemotron:latest",
        help="Verification model (default: nemotron:latest)"
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip the verification step"
    )
    parser.add_argument(
        "--ollama-host",
        default=os.getenv("OLLAMA_HOST", "localhost"),
        help="Ollama server host (default: localhost)"
    )
    parser.add_argument(
        "--ollama-port",
        type=int,
        default=int(os.getenv("OLLAMA_PORT", "11434")),
        help="Ollama server port (default: 11434)"
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.15,
        help="Temperature for primary annotation (default: 0.15)"
    )
    parser.add_argument(
        "--verification-temperature",
        type=float,
        default=0.1,
        help="Temperature for verification (default: 0.1)"
    )
    parser.add_argument(
        "--extended-sources",
        action="store_true",
        help="Include extended data sources (UniProt, Semantic Scholar, OpenFDA, etc.)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="LLM request timeout in seconds (default: 300)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )

    return parser.parse_args()


# ============================================================================
# CSV Reading
# ============================================================================

def read_nct_ids_from_csv(csv_path: str) -> List[str]:
    """
    Extract NCT IDs from a CSV file.
    Scans all columns for NCT ID patterns (NCT followed by 8 digits).
    """
    nct_pattern = re.compile(r'NCT\d{8}', re.IGNORECASE)
    nct_ids = []
    seen = set()

    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Input CSV not found: {csv_path}")

    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            for cell in row:
                matches = nct_pattern.findall(str(cell))
                for match in matches:
                    nct_id = match.upper()
                    if nct_id not in seen:
                        seen.add(nct_id)
                        nct_ids.append(nct_id)

    return nct_ids


# ============================================================================
# Trial Data Fetching
# ============================================================================

async def fetch_trial_data(
    nct_id: str,
    search_engine: "NCTSearchEngine",
    use_extended: bool = False
) -> Dict[str, Any]:
    """
    Fetch trial data from ClinicalTrials.gov and optionally extended sources.
    Uses the NCTSearchEngine directly (no microservices needed).
    """
    config = SearchConfig(
        use_extended_apis=use_extended,
        max_results_per_db=10,
        timeout=60
    )

    logger.info(f"  Fetching data for {nct_id}...")
    trial_data = await search_engine.search(nct_id, config)

    # Check for errors
    if trial_data.get("error"):
        logger.error(f"  Failed to fetch {nct_id}: {trial_data['error']}")
        return trial_data

    # Log what sources we got
    sources = trial_data.get("sources", {})
    successful_sources = [
        name for name, data in sources.items()
        if isinstance(data, dict) and data.get("success")
    ]
    logger.info(f"  Fetched from: {', '.join(successful_sources)}")

    return trial_data


# ============================================================================
# Annotation Pipeline
# ============================================================================

async def annotate_single_trial(
    nct_id: str,
    trial_data: Dict[str, Any],
    model: str,
    annotator: "TrialAnnotator",
    temperature: float
) -> Tuple[str, Dict[str, str]]:
    """
    Run the primary annotation on a single trial.

    Returns:
        (raw_annotation_text, parsed_data_dict)
    """
    # Generate the annotation prompt
    prompt = annotator.generate_prompt(trial_data, nct_id)

    # Call the LLM
    logger.info(f"  Annotating with {model}...")
    annotation_text = await annotator.call_llm(
        model=model,
        prompt=prompt,
        temperature=temperature,
        use_runtime_params=False
    )

    # Parse the response into structured fields
    parsed_data = AnnotationResponseParser.parse_response(
        annotation_text, nct_id, trial_data
    )

    # Validate
    is_valid = AnnotationResponseParser.validate_response(parsed_data)
    if not is_valid:
        logger.warning(f"  Annotation for {nct_id} may be incomplete (missing fields)")

    return annotation_text, parsed_data


async def verify_single_trial(
    nct_id: str,
    original_annotation: str,
    parsed_data: Dict[str, str],
    trial_data: Dict[str, Any],
    primary_model: str,
    verification_model: str,
    annotator: "TrialAnnotator",
    temperature: float
) -> Dict[str, Any]:
    """
    Run verification on a single trial's annotation.

    Returns:
        Dictionary with verification results including reasoning per field.
    """
    logger.info(f"  Verifying with {verification_model}...")

    verification_result = await annotator.verify_annotation(
        nct_id=nct_id,
        original_annotation=original_annotation,
        parsed_data=parsed_data,
        trial_data=trial_data,
        primary_model=primary_model,
        verification_model=verification_model,
        temperature=temperature
    )

    # Extract per-field reasoning from the verification report
    reasoning = extract_field_reasoning(verification_result.verification_report)

    return {
        "verification_model": verification_result.verification_model,
        "verified_parsed_data": verification_result.verified_parsed_data,
        "corrections_made": verification_result.corrections_made,
        "fields_reviewed": verification_result.fields_reviewed,
        "fields_correct": verification_result.fields_correct,
        "verification_report": verification_result.verification_report,
        "processing_time": verification_result.processing_time_seconds,
        "status": verification_result.status,
        "error": verification_result.error,
        "reasoning": reasoning,
    }


def extract_field_reasoning(verification_report: str) -> Dict[str, str]:
    """
    Extract per-field reasoning from the verification report text.
    Looks for patterns like:
        Classification: CORRECT/INCORRECT
          ...
          Reasoning: <text>
    """
    reasoning = {}
    if not verification_report:
        return reasoning

    fields = [
        "Classification", "Delivery Mode", "Outcome",
        "Reason for Failure", "Peptide", "Sequence"
    ]

    for field in fields:
        # Look for the field section and extract Reasoning line
        pattern = rf'{re.escape(field)}:\s*(?:CORRECT|INCORRECT|N/A).*?Reasoning:\s*(.+?)(?:\n\n|\n[A-Z]|\Z)'
        match = re.search(pattern, verification_report, re.IGNORECASE | re.DOTALL)
        if match:
            text = match.group(1).strip()
            # Clean up multi-line reasoning
            text = re.sub(r'\s+', ' ', text)
            reasoning[field] = text

    return reasoning


# ============================================================================
# CSV Output
# ============================================================================

def get_git_commit_id() -> str:
    """Get the current git commit ID."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            capture_output=True, text=True, timeout=5,
            cwd=str(SCRIPT_DIR)
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return 'unknown'


def write_output_csv(
    output_path: str,
    results: List[Dict[str, Any]],
    primary_model: str,
    verification_model: Optional[str],
    verify_enabled: bool,
    temperature: float,
    total_time: float,
    use_extended: bool
):
    """Write the final annotated CSV with metadata header."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Define columns
    base_columns = [
        "NCT ID", "Study Title", "Study Status", "Brief Summary", "Conditions",
        "Drug", "Phase", "Enrollment", "Start Date", "Completion Date",
        "Classification", "Classification Evidence",
        "Delivery Mode", "Delivery Mode Evidence",
        "Outcome", "Outcome Evidence",
        "Reason for Failure", "Reason for Failure Evidence",
        "Peptide", "Peptide Evidence",
        "Sequence", "Sequence Evidence",
        "Study IDs", "Comments",
    ]

    verification_columns = []
    if verify_enabled:
        verification_columns = [
            "Verification Model", "Corrections Made",
            "Classification Reasoning", "Delivery Mode Reasoning",
            "Outcome Reasoning", "Reason for Failure Reasoning",
            "Peptide Reasoning", "Sequence Reasoning",
        ]

    status_columns = ["Status", "Annotation Processing Time", "Verification Processing Time", "Error"]
    columns = base_columns + verification_columns + status_columns

    successful = sum(1 for r in results if r.get("status") == "success")
    failed = sum(1 for r in results if r.get("status") != "success")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    git_commit = get_git_commit_id()

    with open(path, 'w', newline='', encoding='utf-8') as f:
        # Metadata header
        f.write("# ===================================================================\n")
        f.write("# AMP LLM ANNOTATION RESULTS (CLI Two-Step Pipeline)\n")
        f.write("# ===================================================================\n")
        f.write("#\n")
        f.write("# GENERATION INFO\n")
        f.write(f"# Timestamp: {timestamp}\n")
        f.write(f"# Git Commit: {git_commit}\n")
        f.write(f"# Tool: cli_annotate.py (standalone)\n")
        f.write("#\n")
        f.write("# MODEL CONFIGURATION\n")
        f.write(f"# Primary Model: {primary_model}\n")
        f.write(f"# Temperature: {temperature}\n")
        if verify_enabled:
            f.write(f"# Verification Model: {verification_model}\n")
            f.write(f"# Verification: Enabled\n")
        else:
            f.write(f"# Verification: Disabled\n")
        f.write("#\n")
        f.write("# DATA SOURCES\n")
        f.write(f"# ClinicalTrials.gov: Yes\n")
        f.write(f"# Extended Sources (PubMed, UniProt, etc.): {'Yes' if use_extended else 'No'}\n")
        f.write("#\n")
        f.write("# PROCESSING STATISTICS\n")
        f.write(f"# Total Trials: {len(results)}\n")
        f.write(f"# Successful: {successful}\n")
        f.write(f"# Failed: {failed}\n")
        f.write(f"# Total Processing Time: {total_time:.1f}s\n")
        if len(results) > 0:
            f.write(f"# Avg Time Per Trial: {total_time / len(results):.1f}s\n")
        f.write("#\n")
        f.write("# ===================================================================\n")
        f.write("#\n")

        writer = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()

        for result in results:
            row = {}

            if result.get("status") == "success":
                # Use verified data if available, otherwise original
                if result.get("verified_parsed_data"):
                    parsed = result["verified_parsed_data"]
                else:
                    parsed = result.get("parsed_data", {})

                # Map parsed data to columns
                for key, value in parsed.items():
                    if key in columns:
                        row[key] = _clean_csv_value(value)
                    elif key == "Drug" or key == "Interventions/Drug":
                        row["Drug"] = _clean_csv_value(value)
                    elif key == "Phase" or key == "Phases":
                        row["Phase"] = _clean_csv_value(value)
                    elif key == "Study ID" or key == "Study IDs":
                        row["Study IDs"] = _clean_csv_value(value)

                # Always use the real NCT ID
                row["NCT ID"] = result["nct_id"]

                # Verification columns
                if verify_enabled and result.get("verification"):
                    verif = result["verification"]
                    row["Verification Model"] = verif.get("verification_model", "")
                    row["Corrections Made"] = str(verif.get("corrections_made", 0))

                    reasoning = verif.get("reasoning", {})
                    for field in ["Classification", "Delivery Mode", "Outcome",
                                  "Reason for Failure", "Peptide", "Sequence"]:
                        col_name = f"{field} Reasoning"
                        if col_name in columns:
                            row[col_name] = _clean_csv_value(reasoning.get(field, ""))

                    row["Verification Processing Time"] = f"{verif.get('processing_time', 0):.1f}s"

                row["Status"] = "success"
                row["Annotation Processing Time"] = f"{result.get('annotation_time', 0):.1f}s"

            else:
                # Error row
                row["NCT ID"] = result.get("nct_id", "")
                row["Status"] = "error"
                row["Error"] = result.get("error", "Unknown error")

            writer.writerow(row)

    logger.info(f"Output saved to: {path}")
    logger.info(f"  {successful} successful, {failed} failed")


def _clean_csv_value(value: str) -> str:
    """Clean a value for CSV output."""
    if not value:
        return ""
    value = str(value).strip()
    # Remove excessive whitespace
    value = re.sub(r'\s+', ' ', value)
    # Truncate very long values
    if len(value) > 2000:
        value = value[:1997] + "..."
    return value


# ============================================================================
# Ollama Connection Check
# ============================================================================

async def check_ollama_connection(host: str, port: int) -> bool:
    """Check if ollama is reachable and list available models."""
    import httpx
    url = f"http://{host}:{port}/api/tags"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                models = response.json().get("models", [])
                model_names = [m.get("name", "?") for m in models]
                logger.info(f"Ollama connected at {host}:{port}")
                logger.info(f"  Available models: {', '.join(model_names)}")
                return True
            else:
                logger.error(f"Ollama returned HTTP {response.status_code}")
                return False
    except Exception as e:
        logger.error(f"Cannot connect to ollama at {host}:{port}: {e}")
        return False


# ============================================================================
# Main Pipeline
# ============================================================================

async def run_pipeline(args: argparse.Namespace):
    """Main annotation pipeline."""

    # ---- Validate prerequisites ----
    if not HAS_NCT_ENGINE:
        print("ERROR: Could not import NCT search engine.")
        print(f"  Ensure nct_core.py exists at: {NCT_LOOKUP_DIR}")
        sys.exit(1)

    if not HAS_LLM_ASSISTANT:
        print("ERROR: Could not import LLM assistant modules.")
        print(f"  Ensure llm_assistant.py exists at: {LLM_ASSISTANT_DIR}")
        sys.exit(1)

    # ---- Configure ollama connection ----
    llm_config.OLLAMA_HOST = args.ollama_host
    llm_config.OLLAMA_PORT = args.ollama_port
    llm_config.LLM_TIMEOUT = args.timeout
    llm_config.VERIFICATION_TIMEOUT = args.timeout

    # Check ollama connectivity
    if not await check_ollama_connection(args.ollama_host, args.ollama_port):
        print(f"\nERROR: Cannot connect to ollama at {args.ollama_host}:{args.ollama_port}")
        print("  Make sure ollama is running: ollama serve")
        sys.exit(1)

    # ---- Read input CSV ----
    print(f"\nReading NCT IDs from: {args.input}")
    nct_ids = read_nct_ids_from_csv(args.input)
    if not nct_ids:
        print("ERROR: No NCT IDs found in input CSV.")
        print("  Expected format: CSV with NCT IDs like NCT12345678 in any column.")
        sys.exit(1)
    print(f"  Found {len(nct_ids)} NCT IDs: {', '.join(nct_ids[:5])}{'...' if len(nct_ids) > 5 else ''}")

    # ---- Print configuration ----
    verify_enabled = not args.no_verify
    print(f"\nConfiguration:")
    print(f"  Primary model:      {args.model}")
    if verify_enabled:
        print(f"  Verification model: {args.verification_model}")
    else:
        print(f"  Verification:       Disabled")
    print(f"  Ollama:             {args.ollama_host}:{args.ollama_port}")
    print(f"  Temperature:        {args.temperature}")
    print(f"  Extended sources:   {'Yes' if args.extended_sources else 'No'}")
    print(f"  Output:             {args.output}")
    print()

    # ---- Initialize search engine ----
    search_engine = NCTSearchEngine()
    await search_engine.initialize()

    # ---- Initialize annotator ----
    annotator = TrialAnnotator()

    # ---- Process each trial ----
    results = []
    total_start = time.time()

    for i, nct_id in enumerate(nct_ids):
        print(f"[{i+1}/{len(nct_ids)}] Processing {nct_id}")
        trial_start = time.time()
        result = {"nct_id": nct_id}

        try:
            # Step 1: Fetch trial data
            trial_data = await fetch_trial_data(
                nct_id, search_engine, use_extended=args.extended_sources
            )

            if trial_data.get("error"):
                result["status"] = "error"
                result["error"] = f"Data fetch failed: {trial_data['error']}"
                results.append(result)
                print(f"  ERROR: {result['error']}")
                continue

            # Step 2: Primary annotation
            annotation_text, parsed_data = await annotate_single_trial(
                nct_id=nct_id,
                trial_data=trial_data,
                model=args.model,
                annotator=annotator,
                temperature=args.temperature
            )

            annotation_time = time.time() - trial_start
            result["annotation_time"] = annotation_time
            result["parsed_data"] = parsed_data
            result["annotation_text"] = annotation_text

            # Log key fields
            classification = parsed_data.get("Classification", "?")
            outcome = parsed_data.get("Outcome", "?")
            peptide = parsed_data.get("Peptide", "?")
            print(f"  Annotation: Classification={classification}, Outcome={outcome}, Peptide={peptide} ({annotation_time:.1f}s)")

            # Step 3: Verification (if enabled)
            if verify_enabled:
                verif_start = time.time()
                verification = await verify_single_trial(
                    nct_id=nct_id,
                    original_annotation=annotation_text,
                    parsed_data=parsed_data,
                    trial_data=trial_data,
                    primary_model=args.model,
                    verification_model=args.verification_model,
                    annotator=annotator,
                    temperature=args.verification_temperature
                )

                result["verification"] = verification

                if verification["status"] == "success":
                    result["verified_parsed_data"] = verification["verified_parsed_data"]
                    corrections = verification["corrections_made"]
                    verif_time = time.time() - verif_start
                    print(f"  Verification: {corrections} correction(s) ({verif_time:.1f}s)")
                else:
                    print(f"  Verification failed: {verification.get('error', 'unknown')}")

            result["status"] = "success"

        except Exception as e:
            logger.error(f"  Error processing {nct_id}: {e}", exc_info=args.debug)
            result["status"] = "error"
            result["error"] = str(e)
            print(f"  ERROR: {e}")

        results.append(result)

    total_time = time.time() - total_start

    # ---- Close search engine ----
    await search_engine.close()

    # ---- Write output CSV ----
    print(f"\nWriting output CSV...")
    write_output_csv(
        output_path=args.output,
        results=results,
        primary_model=args.model,
        verification_model=args.verification_model if verify_enabled else None,
        verify_enabled=verify_enabled,
        temperature=args.temperature,
        total_time=total_time,
        use_extended=args.extended_sources
    )

    # ---- Print summary ----
    successful = sum(1 for r in results if r.get("status") == "success")
    failed = len(results) - successful
    total_corrections = sum(
        r.get("verification", {}).get("corrections_made", 0)
        for r in results if r.get("status") == "success"
    )

    print(f"\n{'='*60}")
    print(f"ANNOTATION COMPLETE")
    print(f"{'='*60}")
    print(f"  Total trials:    {len(results)}")
    print(f"  Successful:      {successful}")
    print(f"  Failed:          {failed}")
    if verify_enabled:
        print(f"  Corrections:     {total_corrections}")
    print(f"  Total time:      {total_time:.1f}s")
    if len(results) > 0:
        print(f"  Avg per trial:   {total_time / len(results):.1f}s")
    print(f"  Output file:     {args.output}")
    print(f"{'='*60}")


# ============================================================================
# Entry Point
# ============================================================================

def main():
    args = parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    asyncio.run(run_pipeline(args))


if __name__ == "__main__":
    main()
