#!/usr/bin/env python3
"""
Stability Test: Run the same NCTs N times and compare results.

Submits multiple identical annotation jobs via the agent_annotate API,
waits for each to complete, then compares field-by-field to measure
reproducibility across runs.

Usage:
    python scripts/stability_test.py [--runs 3] [--wait-for JOB_ID]

Options:
    --runs N           Number of identical runs (default: 3)
    --wait-for JOB_ID  Wait for this job to complete before starting
    --port PORT        Agent annotate API port (default: 9005)
"""

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import httpx

BASE_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = BASE_DIR / "results"

# The 10 NCTs from job d2761eeb8102
STABILITY_NCTS = [
    "NCT00004984",
    "NCT00001827",
    "NCT00002428",
    "NCT01718834",
    "NCT00000798",
    "NCT00000886",
    "NCT00004358",
    "NCT01652573",
    "NCT00000391",
    "NCT00000435",
]

FIELDS = ["peptide", "classification", "delivery_mode", "outcome", "reason_for_failure"]


def wait_for_job(base_url: str, job_id: str, poll_interval: int = 30) -> dict:
    """Poll job status until completed or failed."""
    print(f"Waiting for job {job_id} to complete...")
    while True:
        try:
            resp = httpx.get(f"{base_url}/api/jobs/{job_id}", timeout=10)
            if resp.status_code != 200:
                print(f"  Warning: status {resp.status_code} checking job {job_id}")
                time.sleep(poll_interval)
                continue
            data = resp.json()
            status = data.get("status", "unknown")
            progress = data.get("progress", {})
            completed = progress.get("completed_trials", 0)
            total = progress.get("total_trials", 0)
            stage = progress.get("current_stage", "")
            print(
                f"  [{datetime.now().strftime('%H:%M:%S')}] "
                f"{job_id}: {status} ({completed}/{total}, stage={stage})"
            )
            if status == "completed":
                return data
            if status in ("failed", "cancelled"):
                print(f"  Job {job_id} ended with status: {status}")
                return data
        except Exception as e:
            print(f"  Error polling job {job_id}: {e}")
        time.sleep(poll_interval)


def submit_job(base_url: str, nct_ids: list[str]) -> str:
    """Submit a new annotation job and return the job ID."""
    resp = httpx.post(
        f"{base_url}/api/jobs",
        json={"nct_ids": nct_ids},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    job_id = data.get("job_id", "")
    print(f"Submitted job: {job_id}")
    return job_id


def load_job_results(job_id: str) -> dict:
    """Load results from the JSON output file."""
    json_path = RESULTS_DIR / "json" / f"{job_id}.json"
    if not json_path.exists():
        print(f"  Warning: results file not found: {json_path}")
        return {}
    with open(json_path) as f:
        return json.load(f)


def extract_final_values(results: dict) -> dict[str, dict[str, str]]:
    """Extract final field values per NCT from job results.
    Returns: {nct_id: {field_name: final_value}}
    """
    values = {}
    for trial in results.get("trials", []):
        nct_id = trial.get("nct_id", "")
        verification = trial.get("verification", {})
        fields = verification.get("fields", [])

        trial_values = {}
        for field_obj in fields:
            fname = field_obj.get("field_name", "")
            fval = field_obj.get("final_value", "")
            if fname in FIELDS:
                trial_values[fname] = fval

        # Fallback to annotation values for fields not in verification
        for ann in trial.get("annotations", []):
            fname = ann.get("field_name", "")
            if fname in FIELDS and fname not in trial_values:
                trial_values[fname] = ann.get("value", "")

        values[nct_id] = trial_values
    return values


def compare_runs(all_run_values: list[dict[str, dict[str, str]]]) -> dict:
    """Compare field values across all runs.

    Returns a report dict with per-field and per-NCT stability metrics.
    """
    n_runs = len(all_run_values)
    report = {
        "n_runs": n_runs,
        "n_ncts": len(STABILITY_NCTS),
        "fields": {},
        "per_nct": {},
        "overall_stability": 0.0,
    }

    total_comparisons = 0
    total_stable = 0

    for field in FIELDS:
        field_stable = 0
        field_total = 0
        field_details = {}

        for nct in STABILITY_NCTS:
            values_across_runs = []
            for run_vals in all_run_values:
                nct_vals = run_vals.get(nct, {})
                values_across_runs.append(nct_vals.get(field, "<missing>"))

            # Check if all runs agree
            unique_values = set(values_across_runs)
            is_stable = len(unique_values) == 1
            if is_stable:
                field_stable += 1
                total_stable += 1
            field_total += 1
            total_comparisons += 1

            field_details[nct] = {
                "values": values_across_runs,
                "stable": is_stable,
                "unique_count": len(unique_values),
                "majority": Counter(values_across_runs).most_common(1)[0][0],
            }

        report["fields"][field] = {
            "stable_count": field_stable,
            "total_count": field_total,
            "stability_pct": round(field_stable / field_total * 100, 1) if field_total > 0 else 0,
            "details": field_details,
        }

    # Per-NCT aggregation
    for nct in STABILITY_NCTS:
        nct_stable = sum(
            1 for field in FIELDS
            if report["fields"][field]["details"][nct]["stable"]
        )
        report["per_nct"][nct] = {
            "stable_fields": nct_stable,
            "total_fields": len(FIELDS),
            "fully_stable": nct_stable == len(FIELDS),
        }

    report["overall_stability"] = round(
        total_stable / total_comparisons * 100, 1
    ) if total_comparisons > 0 else 0

    return report


def print_report(report: dict, job_ids: list[str]):
    """Print a formatted stability report."""
    print("\n" + "=" * 100)
    print("STABILITY TEST REPORT")
    print(f"Runs: {report['n_runs']} | NCTs: {report['n_ncts']} | "
          f"Overall Stability: {report['overall_stability']}%")
    print(f"Job IDs: {', '.join(job_ids)}")
    print("=" * 100)

    # Per-field summary
    print(f"\n{'Field':<25} {'Stable':>8} {'Total':>8} {'Stability%':>12}")
    print("-" * 55)
    for field in FIELDS:
        fd = report["fields"][field]
        print(f"{field:<25} {fd['stable_count']:>8} {fd['total_count']:>8} "
              f"{fd['stability_pct']:>11.1f}%")

    # Per-NCT summary
    print(f"\n{'NCT ID':<18} {'Stable Fields':>14} {'Fully Stable':>13}")
    print("-" * 47)
    for nct in STABILITY_NCTS:
        nd = report["per_nct"][nct]
        marker = "YES" if nd["fully_stable"] else "NO"
        print(f"{nct:<18} {nd['stable_fields']}/{nd['total_fields']:>12} {marker:>13}")

    # Unstable fields detail
    unstable = []
    for field in FIELDS:
        for nct, detail in report["fields"][field]["details"].items():
            if not detail["stable"]:
                unstable.append((nct, field, detail["values"], detail["majority"]))

    if unstable:
        print(f"\n{'='*100}")
        print(f"UNSTABLE FIELDS ({len(unstable)} total)")
        print(f"{'='*100}")
        for nct, field, values, majority in unstable:
            run_str = " | ".join(f"R{i+1}={v}" for i, v in enumerate(values))
            print(f"  {nct}/{field}: {run_str}  (majority={majority})")
    else:
        print("\nAll fields are perfectly stable across all runs.")


def main():
    parser = argparse.ArgumentParser(description="Stability test for agent_annotate")
    parser.add_argument("--runs", type=int, default=3, help="Number of identical runs")
    parser.add_argument("--wait-for", type=str, default=None,
                        help="Wait for this job to complete before starting")
    parser.add_argument("--port", type=int, default=9005, help="Agent annotate API port")
    args = parser.parse_args()

    base_url = f"http://localhost:{args.port}"

    # Verify API is running
    try:
        resp = httpx.get(f"{base_url}/api/health", timeout=5)
        if resp.status_code != 200:
            print(f"Error: API not healthy (status {resp.status_code})")
            sys.exit(1)
    except Exception as e:
        print(f"Error: Cannot reach API at {base_url}: {e}")
        sys.exit(1)

    print(f"Stability Test: {args.runs} runs of {len(STABILITY_NCTS)} NCTs")
    print(f"API: {base_url}")

    # Wait for prerequisite job if specified
    if args.wait_for:
        result = wait_for_job(base_url, args.wait_for)
        if result.get("status") != "completed":
            print(f"Prerequisite job {args.wait_for} did not complete successfully.")
            sys.exit(1)
        print(f"Prerequisite job {args.wait_for} completed. Starting stability test.\n")

    # Submit and run N jobs sequentially
    job_ids = []
    all_run_values = []

    for run_num in range(1, args.runs + 1):
        print(f"\n--- Run {run_num}/{args.runs} ---")
        job_id = submit_job(base_url, STABILITY_NCTS)
        job_ids.append(job_id)

        # Wait for this job to complete before starting the next
        result = wait_for_job(base_url, job_id)
        if result.get("status") != "completed":
            print(f"Run {run_num} (job {job_id}) failed. Aborting stability test.")
            sys.exit(1)

        # Load and extract results
        results = load_job_results(job_id)
        if not results:
            print(f"Could not load results for job {job_id}")
            sys.exit(1)

        values = extract_final_values(results)
        all_run_values.append(values)
        print(f"Run {run_num} complete: {len(values)} trials extracted")

    # Compare all runs
    report = compare_runs(all_run_values)
    print_report(report, job_ids)

    # Save report
    output_dir = RESULTS_DIR / "stability"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = output_dir / f"stability_{timestamp}.json"
    report["job_ids"] = job_ids
    report["timestamp"] = datetime.now().isoformat()
    report["nct_ids"] = STABILITY_NCTS
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved to: {report_path}")


if __name__ == "__main__":
    main()
