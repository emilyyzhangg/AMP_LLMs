#!/usr/bin/env python3
"""
Retroactive fix: re-evaluate consensus on existing job results.

Applies improved value normalization to verifier opinions in completed jobs,
then re-runs consensus checking. This fixes false disagreements caused by
verifiers outputting trial statuses (COMPLETED, Unknown, N/A) instead of
valid failure reason values.

Usage:
    python scripts/retroactive_fix.py                    # process all jobs
    python scripts/retroactive_fix.py --job <job_id>     # process one job
    python scripts/retroactive_fix.py --dry-run          # show changes without saving
"""

import json
import os
import sys
import argparse
import copy
from pathlib import Path
from collections import Counter

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results" / "json"

# Canonical valid values per field
VALID_VALUES = {
    "classification": ["AMP(infection)", "AMP(other)", "Other"],
    "peptide": ["True", "False"],
    "outcome": ["Positive", "Withdrawn", "Terminated", "Failed - completed trial",
                 "Recruiting", "Unknown", "Active, not recruiting"],
    "delivery_mode": [
        "Injection/Infusion - Intramuscular", "Injection/Infusion - Other/Unspecified",
        "Injection/Infusion - Subcutaneous/Intradermal", "IV", "Intranasal",
        "Oral - Tablet", "Oral - Capsule", "Oral - Food", "Oral - Drink",
        "Oral - Unspecified", "Topical - Cream/Gel", "Topical - Powder",
        "Topical - Spray", "Topical - Strip/Covering", "Topical - Wash",
        "Topical - Unspecified", "Other/Unspecified", "Inhalation",
    ],
    "reason_for_failure": ["Business Reason", "Ineffective for purpose",
                           "Toxic/Unsafe", "Due to covid", "Recruitment issues", ""],
}

# Patterns that mean "no failure" for reason_for_failure
NO_FAILURE_PREFIXES = (
    "completed", "unknown", "active", "recruiting", "not_yet", "n/a",
    "none", "empty", "not applicable",
)

NO_FAILURE_EXACT = {
    "completed", "unknown", "active_not_recruiting", "active, not recruiting",
    "recruiting", "not_yet_recruiting", "not yet recruiting", "none", "n/a",
    "not applicable", "empty", "",
}

# Outcome aliases
OUTCOME_ALIASES = {
    "active": "Active, not recruiting",
    "active not recruiting": "Active, not recruiting",
    "active_not_recruiting": "Active, not recruiting",
}


def normalize_verifier_value(field_name: str, value: str) -> str:
    """Normalize a verifier's suggested_value to a canonical form."""
    if value is None:
        return None

    stripped = value.strip().strip('"').strip("'").strip("*").strip()
    lower = stripped.lower()

    if field_name == "reason_for_failure":
        if lower in NO_FAILURE_EXACT:
            return ""
        for prefix in NO_FAILURE_PREFIXES:
            if lower.startswith(prefix):
                return ""
        # Check if it's a valid value
        for valid in VALID_VALUES["reason_for_failure"]:
            if valid.lower() == lower:
                return valid
        # Substring match
        for valid in VALID_VALUES["reason_for_failure"]:
            if valid and valid.lower() in lower:
                return valid
        return value  # Return as-is if can't normalize

    if field_name == "outcome":
        if lower in OUTCOME_ALIASES:
            return OUTCOME_ALIASES[lower]
        if lower == "completed":
            return None  # Not a valid outcome
        for valid in VALID_VALUES["outcome"]:
            if valid.lower() == lower:
                return valid

    if field_name == "delivery_mode":
        if lower == "intravenous":
            return "IV"

    return value


def recheck_consensus(field_name: str, original_value: str, opinions: list) -> dict:
    """Re-evaluate consensus with normalized verifier values."""
    if not opinions:
        return {"consensus": True, "agrees": 0, "total": 0, "changes": []}

    primary_lower = original_value.strip().lower() if original_value else ""
    # Normalize primary too
    if field_name == "reason_for_failure" and primary_lower in NO_FAILURE_EXACT:
        primary_lower = ""
    elif field_name == "reason_for_failure":
        for prefix in NO_FAILURE_PREFIXES:
            if primary_lower.startswith(prefix):
                primary_lower = ""
                break

    changes = []
    agrees = 0
    for opinion in opinions:
        old_sv = opinion.get("suggested_value", "")
        new_sv = normalize_verifier_value(field_name, old_sv)
        if new_sv is None:
            new_sv = old_sv  # Can't normalize, keep original

        new_sv_lower = new_sv.strip().lower() if new_sv else ""

        # Check agreement
        new_agrees = (new_sv_lower == primary_lower)

        if new_sv != old_sv or new_agrees != opinion.get("agrees", False):
            changes.append({
                "model": opinion.get("model_name", ""),
                "old_value": old_sv,
                "new_value": new_sv,
                "old_agrees": opinion.get("agrees", False),
                "new_agrees": new_agrees,
            })

        opinion["suggested_value"] = new_sv
        opinion["agrees"] = new_agrees
        if new_agrees:
            agrees += 1

    total = len(opinions)
    consensus = agrees == total  # unanimous

    return {
        "consensus": consensus,
        "agrees": agrees,
        "total": total,
        "changes": changes,
    }


def process_job(job_path: Path, dry_run: bool = False) -> dict:
    """Process a single job JSON file, returning stats."""
    with open(job_path) as f:
        job = json.load(f)

    job_id = job_path.stem
    trials = job.get("trials", [])
    if isinstance(trials, dict):
        trials = list(trials.values())

    stats = {
        "job_id": job_id,
        "total_trials": len(trials),
        "fields_fixed": 0,
        "consensus_flipped": 0,
        "unflagged_trials": 0,
        "details": [],
    }

    for trial in trials:
        ver = trial.get("verification")
        if not ver or not isinstance(ver, dict):
            continue

        nct = trial.get("nct_id", "")
        any_field_changed = False
        all_consensus_now = True

        for field in ver.get("fields", []):
            field_name = field.get("field_name", "")
            original_value = field.get("original_value", "")
            opinions = field.get("opinions", [])

            if not opinions:
                continue

            result = recheck_consensus(field_name, original_value, opinions)

            if result["changes"]:
                stats["fields_fixed"] += 1
                any_field_changed = True

                was_consensus = field.get("consensus_reached", False)
                now_consensus = result["consensus"]

                if not was_consensus and now_consensus:
                    stats["consensus_flipped"] += 1
                    field["consensus_reached"] = True
                    field["final_value"] = original_value
                    field["agreement_ratio"] = result["agrees"] / result["total"]

                    stats["details"].append({
                        "nct_id": nct,
                        "field": field_name,
                        "action": "CONSENSUS_RESTORED",
                        "primary": original_value,
                        "agrees": f"{result['agrees']}/{result['total']}",
                        "changes": result["changes"],
                    })

            if not field.get("consensus_reached", False):
                all_consensus_now = False

        # If all fields now have consensus, unflag the trial
        if any_field_changed and all_consensus_now and ver.get("flagged_for_review"):
            ver["flagged_for_review"] = False
            ver["overall_consensus"] = True
            ver["flag_reason"] = None
            stats["unflagged_trials"] += 1

    if not dry_run and stats["fields_fixed"] > 0:
        # Atomic write
        tmp_path = job_path.with_suffix(".json.tmp")
        with open(tmp_path, "w") as f:
            json.dump(job, f, indent=2)
        os.replace(tmp_path, job_path)

    return stats


def main():
    parser = argparse.ArgumentParser(description="Retroactive consensus fix")
    parser.add_argument("--job", help="Process a specific job ID")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without saving")
    args = parser.parse_args()

    if args.job:
        job_path = RESULTS_DIR / f"{args.job}.json"
        if not job_path.exists():
            print(f"Job {args.job} not found at {job_path}")
            sys.exit(1)
        jobs = [job_path]
    else:
        jobs = sorted(RESULTS_DIR.glob("*.json"))

    print(f"{'DRY RUN — ' if args.dry_run else ''}Processing {len(jobs)} job(s)...\n")

    total_fixed = 0
    total_flipped = 0
    total_unflagged = 0

    for job_path in jobs:
        stats = process_job(job_path, dry_run=args.dry_run)
        if stats["fields_fixed"] > 0:
            print(f"Job {stats['job_id']}: {stats['fields_fixed']} fields normalized, "
                  f"{stats['consensus_flipped']} consensus restored, "
                  f"{stats['unflagged_trials']} trials unflagged")
            for detail in stats["details"][:10]:
                print(f"  {detail['nct_id']}/{detail['field']}: {detail['action']} "
                      f"(primary='{detail['primary']}', now {detail['agrees']} agree)")
                for c in detail["changes"]:
                    print(f"    {c['model']}: '{c['old_value']}' → '{c['new_value']}' "
                          f"(agrees: {c['old_agrees']} → {c['new_agrees']})")
        else:
            print(f"Job {stats['job_id']}: no changes needed")

        total_fixed += stats["fields_fixed"]
        total_flipped += stats["consensus_flipped"]
        total_unflagged += stats["unflagged_trials"]

    print(f"\n{'DRY RUN — ' if args.dry_run else ''}TOTAL: "
          f"{total_fixed} fields normalized, "
          f"{total_flipped} consensus restored, "
          f"{total_unflagged} trials unflagged")


if __name__ == "__main__":
    main()
