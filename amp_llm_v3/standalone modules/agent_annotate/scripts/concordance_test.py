#!/usr/bin/env python3
"""
Concordance Test: Agent vs Human Annotators (R1 & R2)

Compares agent annotations against two independent human replicates
from the clinical trials Excel file. Calculates raw agreement and
Cohen's kappa for each annotation field, and identifies disagreements.

R1 = "Trials Replicate 1" sheet (multiple annotators: Mercan, Maya, Anat, Ali, Emre, Iris, Berke)
R2 = "Trials Replicate 2" sheet (mostly Emily, some Anat, Ali, Iris)
"""

import csv
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import openpyxl

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
EXCEL_PATH = Path(
    "/Users/amphoraxe/Developer/amphoraxe/dev-llm.amphoraxe.ca/docs/"
    "clinical_trials-with-sequences.xlsx"
)
CSV_PATH = (
    BASE_DIR
    / "results"
    / "csv"
    / "dff30bc65cea_full_20260315_143725.csv"
)
OUTPUT_DIR = BASE_DIR / "results" / "concordance"

# ---------------------------------------------------------------------------
# Field definitions
# ---------------------------------------------------------------------------
# Maps our canonical field names to:
#   - Excel column indices (0-based) for Replicate 1 & 2
#   - CSV column header name
#   - Whether blank means "not annotated" (True) or is a valid value (False)
FIELDS = {
    "classification": {
        "excel_r1_col": 10,  # K
        "excel_r2_col": 10,  # K
        "csv_col": "Classification",
        "blank_means_skip": True,
    },
    "delivery_mode": {
        "excel_r1_col": 12,  # M
        "excel_r2_col": 12,  # M
        "csv_col": "Delivery Mode",
        "blank_means_skip": True,
    },
    "outcome": {
        "excel_r1_col": 17,  # R
        "excel_r2_col": 17,  # R
        "csv_col": "Outcome",
        "blank_means_skip": True,
    },
    "reason_for_failure": {
        "excel_r1_col": 18,  # S
        "excel_r2_col": 18,  # S
        "csv_col": "Reason for Failure",
        "blank_means_skip": False,  # blank IS valid (means "no failure reason")
    },
    "peptide": {
        "excel_r1_col": 21,  # V
        "excel_r2_col": 21,  # V
        "csv_col": "Peptide",
        "blank_means_skip": True,
    },
}

# ---------------------------------------------------------------------------
# Value normalisation
# ---------------------------------------------------------------------------
DELIVERY_MODE_ALIASES = {
    "intravenous": "IV",
    "iv": "IV",
    "injection/infusion - intravenous": "IV",
    "oral - unspecified": "Oral - Unspecified",
    "oral - unspecified": "Oral - Unspecified",
    "oral - capsule": "Oral - Capsule",
    "oral - tablet": "Oral - Tablet",
    "oral - drink": "Oral - Drink",
    "oral - food": "Oral - Food",
    "injection": "Injection/Infusion - Other/Unspecified",
    "topical - unspecified": "Topical - Unspecified",
    "other/unspecified": "Other/Unspecified",
}

OUTCOME_ALIASES = {
    "active": "Active, not recruiting",
    "active, not recruiting": "Active, not recruiting",
    "active not recruiting": "Active, not recruiting",
    "recruiting": "Recruiting",
    "failed": "Failed - completed trial",
    "failed - completed trial": "Failed - completed trial",
    "positive": "Positive",
    "terminated": "Terminated",
    "withdrawn": "Withdrawn",
    "unknown": "Unknown",
}

CLASSIFICATION_ALIASES = {
    "amp(infection)": "AMP(infection)",
    "amp(other)": "AMP(other)",
    "amp (infection)": "AMP(infection)",
    "amp (other)": "AMP(other)",
    "other": "Other",
}

REASON_ALIASES = {
    "business reason": "Business Reason",
    "ineffective for purpose": "Ineffective for purpose",
    "recruitment issues": "Recruitment issues",
    "toxic/unsafe": "Toxic/Unsafe",
    "due to covid": "Due to covid",
}

PEPTIDE_ALIASES = {
    "true": "True",
    "false": "False",
    "yes": "True",
    "no": "False",
    "1": "True",
    "0": "False",
}


def normalise(value, field_name):
    """Normalise a value for comparison, returning (normalised_str, is_blank)."""
    if value is None:
        return ("", True)

    # Handle booleans (Excel stores Peptide as bool)
    if isinstance(value, bool):
        return (str(value), False)

    s = str(value).strip()
    if s == "" or s.lower() == "none":
        return ("", True)

    s_lower = s.lower()

    if field_name == "delivery_mode":
        # For multi-value delivery modes, normalise each part
        parts = [p.strip() for p in s.split(",")]
        normalised_parts = []
        for part in parts:
            part_lower = part.strip().lower()
            normalised_parts.append(
                DELIVERY_MODE_ALIASES.get(part_lower, part.strip())
            )
        # Sort to make order-independent comparison
        normalised_parts.sort()
        return (", ".join(normalised_parts), False)
    elif field_name == "outcome":
        return (OUTCOME_ALIASES.get(s_lower, s), False)
    elif field_name == "classification":
        return (CLASSIFICATION_ALIASES.get(s_lower, s), False)
    elif field_name == "reason_for_failure":
        return (REASON_ALIASES.get(s_lower, s), False)
    elif field_name == "peptide":
        return (PEPTIDE_ALIASES.get(s_lower, s), False)
    else:
        return (s, False)


# ---------------------------------------------------------------------------
# Cohen's Kappa (manual implementation)
# ---------------------------------------------------------------------------
def cohens_kappa(labels_a, labels_b):
    """
    Compute Cohen's kappa for two lists of categorical labels.
    Returns (kappa, po, pe) where po = observed agreement, pe = expected agreement.
    """
    assert len(labels_a) == len(labels_b), "Label lists must be same length"
    n = len(labels_a)
    if n == 0:
        return (float("nan"), float("nan"), float("nan"))

    # All unique labels
    all_labels = sorted(set(labels_a) | set(labels_b))

    # Count agreements
    agreements = sum(1 for a, b in zip(labels_a, labels_b) if a == b)
    po = agreements / n

    # Expected agreement by chance
    count_a = Counter(labels_a)
    count_b = Counter(labels_b)
    pe = sum((count_a[label] / n) * (count_b[label] / n) for label in all_labels)

    if pe == 1.0:
        # Perfect agreement by chance — kappa undefined, return 1 if perfect
        return (1.0 if po == 1.0 else 0.0, po, pe)

    kappa = (po - pe) / (1.0 - pe)
    return (kappa, po, pe)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_excel_annotations(path):
    """Load human annotations from both replicate sheets.
    Returns dict: { nct_id: { 'r1': {field: raw_value}, 'r2': {field: raw_value} } }
    """
    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    data = defaultdict(lambda: {"r1": {}, "r2": {}})

    for replicate, sheet_name in [
        ("r1", "Trials Replicate 1"),
        ("r2", "Trials Replicate 2"),
    ]:
        ws = wb[sheet_name]
        for row in ws.iter_rows(min_row=2, values_only=True):
            nct = row[0]
            if nct is None:
                continue
            nct = str(nct).strip()
            for field_name, field_def in FIELDS.items():
                col_idx = field_def[f"excel_{replicate}_col"]
                raw = row[col_idx] if col_idx < len(row) else None
                data[nct][replicate][field_name] = raw

    wb.close()
    return dict(data)


def load_agent_annotations(path):
    """Load agent annotations from CSV (skipping comment header).
    Returns dict: { nct_id: {field: raw_value} }
    """
    data = {}
    with open(str(path), "r") as f:
        # Skip comment line
        first_line = f.readline()
        if not first_line.startswith("#"):
            f.seek(0)  # Not a comment, rewind
        reader = csv.DictReader(f)
        for row in reader:
            nct = row["NCT ID"].strip()
            entry = {}
            for field_name, field_def in FIELDS.items():
                entry[field_name] = row[field_def["csv_col"]]
            data[nct] = entry
    return data


# ---------------------------------------------------------------------------
# Concordance computation
# ---------------------------------------------------------------------------
def compute_concordance(agent_data, human_data):
    """
    For each field, compute concordance between:
      - Agent vs R1
      - Agent vs R2
      - R1 vs R2

    Returns a dict with results per field per comparison pair.
    """
    # Identify NCT IDs present in all three sources
    agent_ncts = set(agent_data.keys())
    human_ncts = set(human_data.keys())
    common_ncts = sorted(agent_ncts & human_ncts)

    print(f"Agent NCT IDs:  {len(agent_ncts)}")
    print(f"Human NCT IDs:  {len(human_ncts)}")
    print(f"Overlapping:    {len(common_ncts)}")
    print()

    if not common_ncts:
        print("ERROR: No overlapping NCT IDs found!")
        return {}

    results = {}
    all_disagreements = []

    for field_name, field_def in FIELDS.items():
        blank_means_skip = field_def["blank_means_skip"]
        field_result = {}

        for pair_name, src_a_label, src_b_label, get_a, get_b in [
            (
                "Agent vs R1",
                "Agent",
                "R1",
                lambda nct: agent_data[nct][field_name],
                lambda nct: human_data[nct]["r1"].get(field_name),
            ),
            (
                "Agent vs R2",
                "Agent",
                "R2",
                lambda nct: agent_data[nct][field_name],
                lambda nct: human_data[nct]["r2"].get(field_name),
            ),
            (
                "R1 vs R2",
                "R1",
                "R2",
                lambda nct: human_data[nct]["r1"].get(field_name),
                lambda nct: human_data[nct]["r2"].get(field_name),
            ),
        ]:
            labels_a = []
            labels_b = []
            pair_disagreements = []
            included_ncts = []
            skipped_blank = 0

            for nct in common_ncts:
                raw_a = get_a(nct)
                raw_b = get_b(nct)

                norm_a, blank_a = normalise(raw_a, field_name)
                norm_b, blank_b = normalise(raw_b, field_name)

                # Skip logic: for fields where blank_means_skip,
                # exclude if EITHER annotator is blank
                if blank_means_skip and (blank_a or blank_b):
                    skipped_blank += 1
                    continue

                # For reason_for_failure: blank is a valid value (empty string)
                # Normalise blanks to a canonical empty representation
                if not blank_means_skip:
                    if blank_a:
                        norm_a = ""
                    if blank_b:
                        norm_b = ""

                included_ncts.append(nct)
                labels_a.append(norm_a)
                labels_b.append(norm_b)

                if norm_a != norm_b:
                    pair_disagreements.append(
                        {
                            "nct_id": nct,
                            "field": field_name,
                            "comparison": pair_name,
                            f"{src_a_label.lower()}_value": norm_a,
                            f"{src_b_label.lower()}_value": norm_b,
                            f"{src_a_label.lower()}_raw": str(raw_a),
                            f"{src_b_label.lower()}_raw": str(raw_b),
                        }
                    )

            n = len(labels_a)
            if n > 0:
                kappa, po, pe = cohens_kappa(labels_a, labels_b)
                agreements = sum(
                    1 for a, b in zip(labels_a, labels_b) if a == b
                )
            else:
                kappa, po, pe = float("nan"), float("nan"), float("nan")
                agreements = 0

            field_result[pair_name] = {
                "n": n,
                "skipped_blank": skipped_blank,
                "agreements": agreements,
                "raw_agreement_pct": round(po * 100, 1) if n > 0 else None,
                "cohens_kappa": round(kappa, 4) if n > 0 else None,
                "pe": round(pe, 4) if n > 0 else None,
                "disagreements": pair_disagreements,
            }
            all_disagreements.extend(pair_disagreements)

        results[field_name] = field_result

    return results, all_disagreements, common_ncts


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------
def kappa_interpretation(k):
    """Landis & Koch interpretation of kappa."""
    if k is None or k != k:  # NaN check
        return "N/A"
    if k < 0:
        return "Poor"
    elif k < 0.21:
        return "Slight"
    elif k < 0.41:
        return "Fair"
    elif k < 0.61:
        return "Moderate"
    elif k < 0.81:
        return "Substantial"
    else:
        return "Almost Perfect"


def print_concordance_table(results):
    """Print a formatted concordance summary table."""
    print("=" * 110)
    print(f"{'Field':<25} {'Comparison':<15} {'N':>5} {'Skip':>5} {'Agree':>6} {'Agree%':>8} {'Kappa':>8} {'Interpretation':<16}")
    print("-" * 110)

    for field_name in FIELDS:
        field_result = results.get(field_name, {})
        first = True
        for pair_name in ["Agent vs R1", "Agent vs R2", "R1 vs R2"]:
            pr = field_result.get(pair_name, {})
            n = pr.get("n", 0)
            skipped = pr.get("skipped_blank", 0)
            agreements = pr.get("agreements", 0)
            pct = pr.get("raw_agreement_pct")
            kappa = pr.get("cohens_kappa")

            pct_str = f"{pct:.1f}%" if pct is not None else "N/A"
            kappa_str = f"{kappa:.4f}" if kappa is not None else "N/A"
            interp = kappa_interpretation(kappa)

            label = field_name if first else ""
            print(
                f"{label:<25} {pair_name:<15} {n:>5} {skipped:>5} "
                f"{agreements:>6} {pct_str:>8} {kappa_str:>8} {interp:<16}"
            )
            first = False
        print("-" * 110)

    print("=" * 110)


def print_disagreements(all_disagreements):
    """Print detailed disagreement listing."""
    if not all_disagreements:
        print("\nNo disagreements found.")
        return

    print(f"\n{'='*110}")
    print(f"DETAILED DISAGREEMENTS ({len(all_disagreements)} total)")
    print(f"{'='*110}")

    # Group by field, then comparison
    by_field = defaultdict(lambda: defaultdict(list))
    for d in all_disagreements:
        by_field[d["field"]][d["comparison"]].append(d)

    for field_name in FIELDS:
        field_disags = by_field.get(field_name, {})
        if not field_disags:
            continue
        print(f"\n--- {field_name} ---")
        for pair_name in ["Agent vs R1", "Agent vs R2", "R1 vs R2"]:
            disags = field_disags.get(pair_name, [])
            if not disags:
                continue
            print(f"  [{pair_name}]")
            for d in disags:
                # Extract the two value keys dynamically
                val_keys = [k for k in d if k.endswith("_value")]
                raw_keys = [k for k in d if k.endswith("_raw")]
                vals = {k: d[k] for k in val_keys}
                raws = {k: d[k] for k in raw_keys}
                val_strs = " | ".join(
                    f"{k.replace('_value', '').upper()}={repr(v)}"
                    for k, v in sorted(vals.items())
                )
                print(f"    {d['nct_id']}: {val_strs}")


def print_per_trial_matrix(results, common_ncts, agent_data, human_data):
    """Print a per-trial concordance matrix."""
    print(f"\n{'='*110}")
    print("PER-TRIAL CONCORDANCE MATRIX")
    print(f"{'='*110}")
    print(f"{'NCT ID':<16}", end="")
    for field_name in FIELDS:
        print(f" {'AgR1':>5} {'AgR2':>5} {'R1R2':>5} |", end="")
    print()
    print(f"{'':16}", end="")
    for field_name in FIELDS:
        abbr = field_name[:12]
        width = 20
        print(f" {abbr:^{width}}|", end="")
    print()
    print("-" * (16 + len(FIELDS) * 21))

    for nct in common_ncts:
        print(f"{nct:<16}", end="")
        for field_name, field_def in FIELDS.items():
            blank_means_skip = field_def["blank_means_skip"]

            agent_raw = agent_data[nct][field_name]
            r1_raw = human_data[nct]["r1"].get(field_name)
            r2_raw = human_data[nct]["r2"].get(field_name)

            a_norm, a_blank = normalise(agent_raw, field_name)
            r1_norm, r1_blank = normalise(r1_raw, field_name)
            r2_norm, r2_blank = normalise(r2_raw, field_name)

            # For reason_for_failure, blanks are valid
            if not blank_means_skip:
                if a_blank:
                    a_norm = ""
                if r1_blank:
                    r1_norm = ""
                if r2_blank:
                    r2_norm = ""

            def match_str(v1, b1, v2, b2):
                if blank_means_skip and (b1 or b2):
                    return "  -  "
                return " YES " if v1 == v2 else " NO  "

            ag_r1 = match_str(a_norm, a_blank, r1_norm, r1_blank)
            ag_r2 = match_str(a_norm, a_blank, r2_norm, r2_blank)
            r1_r2 = match_str(r1_norm, r1_blank, r2_norm, r2_blank)
            print(f" {ag_r1} {ag_r2} {r1_r2} |", end="")
        print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 110)
    print("AGENT ANNOTATE - CONCORDANCE TEST")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Excel:     {EXCEL_PATH}")
    print(f"CSV:       {CSV_PATH}")
    print("=" * 110)
    print()

    # Verify files exist
    if not EXCEL_PATH.exists():
        print(f"ERROR: Excel file not found: {EXCEL_PATH}")
        sys.exit(1)
    if not CSV_PATH.exists():
        print(f"ERROR: CSV file not found: {CSV_PATH}")
        sys.exit(1)

    # Load data
    print("Loading human annotations from Excel...")
    human_data = load_excel_annotations(EXCEL_PATH)
    print(f"  Loaded {len(human_data)} NCT IDs from Excel")

    print("Loading agent annotations from CSV...")
    agent_data = load_agent_annotations(CSV_PATH)
    print(f"  Loaded {len(agent_data)} NCT IDs from CSV")
    print()

    # Compute concordance
    results, all_disagreements, common_ncts = compute_concordance(
        agent_data, human_data
    )

    if not results:
        sys.exit(1)

    # Print summary table
    print("\nCONCORDANCE SUMMARY")
    print_concordance_table(results)

    # Print kappa interpretation guide
    print("\nKappa Interpretation (Landis & Koch):")
    print("  < 0.00  Poor | 0.00-0.20  Slight | 0.21-0.40  Fair")
    print("  0.41-0.60  Moderate | 0.61-0.80  Substantial | 0.81-1.00  Almost Perfect")
    print()

    # Print per-trial matrix
    print_per_trial_matrix(results, common_ncts, agent_data, human_data)

    # Print disagreements
    print_disagreements(all_disagreements)

    # Print raw values for manual inspection
    print(f"\n{'='*110}")
    print("RAW VALUE COMPARISON (for manual inspection)")
    print(f"{'='*110}")
    for nct in common_ncts:
        print(f"\n{nct}:")
        for field_name in FIELDS:
            agent_raw = agent_data[nct][field_name]
            r1_raw = human_data[nct]["r1"].get(field_name)
            r2_raw = human_data[nct]["r2"].get(field_name)
            a_norm, _ = normalise(agent_raw, field_name)
            r1_norm, _ = normalise(r1_raw, field_name)
            r2_norm, _ = normalise(r2_raw, field_name)
            print(f"  {field_name}:")
            print(f"    Agent: {repr(agent_raw):>45} -> {repr(a_norm)}")
            print(f"    R1:    {repr(r1_raw):>45} -> {repr(r1_norm)}")
            print(f"    R2:    {repr(r2_raw):>45} -> {repr(r2_norm)}")

    # Save JSON results
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    json_output = {
        "timestamp": datetime.now().isoformat(),
        "excel_path": str(EXCEL_PATH),
        "csv_path": str(CSV_PATH),
        "common_ncts": common_ncts,
        "n_agent": len(agent_data),
        "n_human": len(human_data),
        "n_overlap": len(common_ncts),
        "fields": {},
        "disagreements": all_disagreements,
    }

    for field_name in FIELDS:
        field_json = {}
        for pair_name in ["Agent vs R1", "Agent vs R2", "R1 vs R2"]:
            pr = results[field_name][pair_name]
            field_json[pair_name] = {
                "n": pr["n"],
                "skipped_blank": pr["skipped_blank"],
                "agreements": pr["agreements"],
                "raw_agreement_pct": pr["raw_agreement_pct"],
                "cohens_kappa": pr["cohens_kappa"],
                "n_disagreements": len(pr["disagreements"]),
            }
        json_output["fields"][field_name] = field_json

    json_path = OUTPUT_DIR / "concordance_results.json"
    with open(json_path, "w") as f:
        json.dump(json_output, f, indent=2)
    print(f"\n\nJSON results saved to: {json_path}")


if __name__ == "__main__":
    main()
