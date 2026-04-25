#!/usr/bin/env python3
"""Pick NCTs that share interventions heavily so drug_cache hit-rate is measurable."""
import csv, json, sys
from pathlib import Path
from collections import defaultdict

CSV = Path("/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/amp_llm_v3/standalone modules/agent_annotate/docs/human_ground_truth_train_df.csv")
TEST_BATCH = Path("/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/amp_llm_v3/standalone modules/agent_annotate/scripts/fast_learning_batch_50.txt")
RES = Path("/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/amp_llm_v3/standalone modules/agent_annotate/results/research")
JSON_BASE = Path("/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/amp_llm_v3/standalone modules/agent_annotate/results/json")

# Drugs known to repeat heavily; we'll pull every NCT containing any of these
TARGET_DRUGS = ["erenumab", "pembrolizumab", "nivolumab", "glucagon", "ipilimumab",
                "semaglutide", "liraglutide", "poly iclc", "poly-iclc"]

def excluded_ncts() -> set[str]:
    """For drug_cache validation we do NOT exclude prior-job NCTs — the goal
    is to measure cache hit rate on a high-repetition slice, and re-running
    NCTs that share drugs is ideal for that. Only the test-batch is excluded
    because the prod API rejects it (TRAINING_NCTS = csv - test_batch)."""
    out: set[str] = set()
    if TEST_BATCH.exists():
        out |= {l.strip().upper() for l in TEST_BATCH.open() if l.strip()}
    return out


def main() -> int:
    with CSV.open() as f:
        training = {(r['nct_id'] or '').upper().strip() for r in csv.DictReader(f) if r['nct_id']}

    excl = excluded_ncts()
    print(f"training NCTs: {len(training)}, excluded (test_batch+prior_jobs): {len(excl)}", file=sys.stderr)

    drug_to_ncts: dict[str, set[str]] = defaultdict(set)
    nct_drugs: dict[str, set[str]] = defaultdict(set)

    seen = 0
    for job_dir in RES.iterdir():
        if not job_dir.is_dir():
            continue
        for f in job_dir.iterdir():
            if not f.name.startswith('NCT'):
                continue
            nct = f.stem.upper()
            if nct not in training or nct in excl:
                continue
            try:
                d = json.load(f.open())
                for r in d.get('results', []):
                    if r.get('agent_name') != 'clinical_protocol':
                        continue
                    rd = r.get('raw_data') or {}
                    ps = rd.get('protocolSection') or rd.get('protocol_section', {})
                    for i in ps.get('armsInterventionsModule', {}).get('interventions', []):
                        name = (i.get('name', '') or '').strip().lower()
                        if not name or len(name) < 4:
                            continue
                        if i.get('type') not in ('DRUG', 'BIOLOGICAL'):
                            continue
                        for td in TARGET_DRUGS:
                            if td in name:
                                drug_to_ncts[td].add(nct)
                                nct_drugs[nct].add(td)
                seen += 1
            except Exception:
                pass

    print(f"\nNCTs with target drugs (after excluding prior jobs):", file=sys.stderr)
    for td, ncts in sorted(drug_to_ncts.items(), key=lambda x: -len(x[1])):
        print(f"  [{len(ncts):>3}] {td}", file=sys.stderr)

    # Take all NCTs that have at least one target drug
    all_ncts = sorted(nct_drugs.keys())
    print(f"\nTotal slice: {len(all_ncts)} NCTs covering {len(drug_to_ncts)} target drugs", file=sys.stderr)

    # Cap at 40 to keep wall-time reasonable
    selected = all_ncts[:40]
    print(f"Selected {len(selected)} NCTs", file=sys.stderr)

    print(json.dumps(selected))
    return 0


if __name__ == "__main__":
    sys.exit(main())
