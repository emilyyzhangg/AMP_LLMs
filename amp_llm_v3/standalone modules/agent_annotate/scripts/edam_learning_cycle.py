#!/usr/bin/env python3
"""
EDAM Learning Cycle: Automated multi-phase self-improvement pipeline.

Runs the full EDAM learning cycle without human intervention:
  Phase 1 (Calibration):  3-5x runs on a small calibration set (10 NCTs)
  Phase 2 (Compounding):  2-3x more runs on the same set (EDAM guidance active)
  Phase 3 (Transfer):     1x full batch (100+ NCTs) with accumulated learning
  Phase 4 (Convergence):  1x re-run calibration set to measure improvement

Each phase waits for the previous to complete. EDAM post-job hooks run
automatically after every job, building the learning memory.

Usage:
    # Full cycle with default calibration set (10 NCTs from d2761eeb8102)
    python scripts/edam_learning_cycle.py

    # Custom calibration runs and full batch
    python scripts/edam_learning_cycle.py --calibration-runs 5 --full-batch-file ncts_100.txt

    # Wait for a running job first
    python scripts/edam_learning_cycle.py --wait-for a7cd7d71813b

    # Only run specific phases
    python scripts/edam_learning_cycle.py --phases 1,2,3,4

Options:
    --calibration-runs N    Calibration runs per phase (default: 3 for P1, 3 for P2)
    --full-batch-file FILE  Text file with NCT IDs for Phase 3 (one per line)
    --wait-for JOB_ID       Wait for this job to complete before starting
    --port PORT             Agent annotate API port (default: 9005)
    --phases PHASES         Comma-separated phase numbers to run (default: 1,2,3,4)
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

BASE_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = BASE_DIR / "results"

# Default calibration set: the 10 NCTs from job d2761eeb8102
CALIBRATION_NCTS = [
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


def wait_for_job(base_url: str, job_id: str, poll_interval: int = 30) -> dict:
    """Poll job status until completed or failed."""
    print(f"  Waiting for job {job_id}...")
    while True:
        try:
            resp = httpx.get(f"{base_url}/api/jobs/{job_id}", timeout=10)
            if resp.status_code != 200:
                time.sleep(poll_interval)
                continue
            data = resp.json()
            status = data.get("status", "unknown")
            progress = data.get("progress", {})
            completed = progress.get("completed_trials", 0)
            total = progress.get("total_trials", 0)
            print(
                f"    [{datetime.now().strftime('%H:%M:%S')}] "
                f"{status} ({completed}/{total})"
            )
            if status == "completed":
                return data
            if status in ("failed", "cancelled"):
                print(f"    Job {job_id} ended with status: {status}")
                return data
        except Exception as e:
            print(f"    Error polling: {e}")
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
    return data.get("job_id", "")


def get_edam_stats(base_url: str) -> dict:
    """Get EDAM memory statistics."""
    try:
        resp = httpx.get(f"{base_url}/api/health", timeout=5)
        return resp.json() if resp.status_code == 200 else {}
    except Exception:
        return {}


def load_ncts_from_file(path: str) -> list[str]:
    """Load NCT IDs from a text file (one per line)."""
    ncts = []
    with open(path) as f:
        for line in f:
            nct = line.strip()
            if nct and nct.startswith("NCT"):
                ncts.append(nct)
    return ncts


def run_phase(base_url: str, phase_name: str, nct_ids: list[str],
              num_runs: int) -> list[str]:
    """Run N identical jobs sequentially, waiting for each to complete."""
    print(f"\n{'='*70}")
    print(f"  {phase_name}: {num_runs} runs × {len(nct_ids)} NCTs")
    print(f"{'='*70}")

    job_ids = []
    for run_num in range(1, num_runs + 1):
        print(f"\n  --- Run {run_num}/{num_runs} ---")
        job_id = submit_job(base_url, nct_ids)
        print(f"  Submitted: {job_id}")
        job_ids.append(job_id)

        result = wait_for_job(base_url, job_id)
        if result.get("status") != "completed":
            print(f"  Run {run_num} failed. Stopping phase.")
            break

        print(f"  Run {run_num} complete.")

    return job_ids


def print_summary(phase_results: dict):
    """Print the full learning cycle summary."""
    print(f"\n{'='*70}")
    print("  EDAM LEARNING CYCLE COMPLETE")
    print(f"{'='*70}")

    total_jobs = 0
    for phase, data in phase_results.items():
        jobs = data.get("job_ids", [])
        total_jobs += len(jobs)
        print(f"\n  {phase}: {len(jobs)} jobs")
        for jid in jobs:
            print(f"    - {jid}")

    print(f"\n  Total jobs: {total_jobs}")
    print(f"  Timestamp: {datetime.now().isoformat()}")
    print(f"\n  EDAM database: results/edam.db")
    print(f"  Review the learning with: sqlite3 results/edam.db")
    print(f"    SELECT field_name, COUNT(*), AVG(stability_score)")
    print(f"    FROM stability_index GROUP BY field_name;")


def main():
    parser = argparse.ArgumentParser(description="EDAM learning cycle")
    parser.add_argument("--calibration-runs", type=int, default=3,
                        help="Calibration runs per phase (default: 3)")
    parser.add_argument("--full-batch-file", type=str, default=None,
                        help="File with NCT IDs for Phase 3")
    parser.add_argument("--wait-for", type=str, default=None,
                        help="Wait for this job to complete first")
    parser.add_argument("--port", type=int, default=9005,
                        help="Agent annotate API port")
    parser.add_argument("--phases", type=str, default="1,2,3,4",
                        help="Comma-separated phases to run")
    args = parser.parse_args()

    base_url = f"http://localhost:{args.port}"
    phases = [int(p.strip()) for p in args.phases.split(",")]

    # Verify API is running
    try:
        resp = httpx.get(f"{base_url}/api/health", timeout=5)
        if resp.status_code != 200:
            print(f"Error: API not healthy (status {resp.status_code})")
            sys.exit(1)
    except Exception as e:
        print(f"Error: Cannot reach API at {base_url}: {e}")
        sys.exit(1)

    print(f"EDAM Learning Cycle")
    print(f"  API: {base_url}")
    print(f"  Calibration set: {len(CALIBRATION_NCTS)} NCTs")
    print(f"  Calibration runs: {args.calibration_runs} per phase")
    print(f"  Phases: {phases}")

    # Wait for prerequisite job
    if args.wait_for:
        result = wait_for_job(base_url, args.wait_for)
        if result.get("status") != "completed":
            print(f"Prerequisite job failed. Aborting.")
            sys.exit(1)
        print(f"Prerequisite job complete.\n")

    phase_results = {}

    # Phase 1: Calibration
    if 1 in phases:
        job_ids = run_phase(
            base_url, "PHASE 1: CALIBRATION",
            CALIBRATION_NCTS, args.calibration_runs,
        )
        phase_results["Phase 1 (Calibration)"] = {"job_ids": job_ids}

    # Phase 2: Compounding
    if 2 in phases:
        job_ids = run_phase(
            base_url, "PHASE 2: COMPOUNDING (EDAM active)",
            CALIBRATION_NCTS, args.calibration_runs,
        )
        phase_results["Phase 2 (Compounding)"] = {"job_ids": job_ids}

    # Phase 3: Transfer
    if 3 in phases:
        if args.full_batch_file:
            full_ncts = load_ncts_from_file(args.full_batch_file)
        else:
            # Default: use the calibration set (user can override)
            print("\n  Phase 3: No --full-batch-file specified, using calibration set.")
            print("  Tip: provide a larger NCT list for better transfer learning.")
            full_ncts = CALIBRATION_NCTS

        job_ids = run_phase(
            base_url, "PHASE 3: TRANSFER (full batch)",
            full_ncts, 1,
        )
        phase_results["Phase 3 (Transfer)"] = {"job_ids": job_ids}

    # Phase 4: Convergence check
    if 4 in phases:
        job_ids = run_phase(
            base_url, "PHASE 4: CONVERGENCE (re-calibrate)",
            CALIBRATION_NCTS, 1,
        )
        phase_results["Phase 4 (Convergence)"] = {"job_ids": job_ids}

    print_summary(phase_results)

    # Save cycle report
    output_dir = RESULTS_DIR / "edam_cycles"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = output_dir / f"cycle_{timestamp}.json"
    report = {
        "timestamp": datetime.now().isoformat(),
        "calibration_ncts": CALIBRATION_NCTS,
        "calibration_runs": args.calibration_runs,
        "phases_run": phases,
        "results": phase_results,
    }
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n  Cycle report saved to: {report_path}")


if __name__ == "__main__":
    main()
