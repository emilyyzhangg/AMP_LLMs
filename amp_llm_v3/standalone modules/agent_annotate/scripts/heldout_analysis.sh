#!/bin/bash
# Run a structured analysis of the held-out 30-NCT validation results.
#
# Usage: scripts/heldout_analysis.sh <heldout_job_id> [<baseline_job_id>]
#
# Default baseline: Job #83 (51a6c2a308f8) — v42.6.15 production baseline
# on the 47-NCT clean slice. NCT overlap with the held-out 30 is empty
# by construction; the comparison shows whether v42.7.7-11 generalizes
# to unseen trials.
#
# Outputs (all to stdout):
#   1. Whole-job per-field accuracy delta vs baseline
#   2. Per-NCT outcome breakdown (gain / loss / unchanged)
#   3. Research-agent firing counts (NIH RePORTER / FDA Drugs / SEC EDGAR
#      citations per trial — confirms v42.7.10 fix is actually working)
#   4. v42.7.7-11 path firing diagnostics
#   5. Evidence_grade distribution (calibrated-decline coverage stratification)
#   6. Outcome miss-pattern tally + delivery_mode miss-pattern tally
#      (uses cross_job_miss_patterns.py — see also that script for
#      cross-cycle pattern hunting against ≥2 historical jobs)

set -euo pipefail

HELDOUT_JOB="${1:?usage: $0 <heldout_job_id> [<baseline_job_id>]}"
BASELINE_JOB="${2:-51a6c2a308f8}"

THIS_DIR="$(cd "$(dirname "$0")" && pwd)"
PY=/Users/amphoraxe/Developer/amphoraxe/dev-llm.amphoraxe.ca/amp_llm_v3/llm_env/bin/python

echo "=========================================================="
echo "Held-out validation analysis"
echo "  Held-out job: $HELDOUT_JOB"
echo "  Baseline job: $BASELINE_JOB"
echo "=========================================================="
echo

echo "── 1. Per-field accuracy delta ─────────────────────────"
$PY "$THIS_DIR/compare_jobs.py" "$BASELINE_JOB" "$HELDOUT_JOB"
echo

echo "── 2. Outcome per-NCT breakdown ────────────────────────"
$PY "$THIS_DIR/compare_jobs.py" "$BASELINE_JOB" "$HELDOUT_JOB" --field outcome
echo

echo "── 3. Research-agent firing pattern (v42.7.10 sanity) ──"
$PY - <<EOF
import json, sys
from pathlib import Path
candidates = [
    Path("/Users/amphoraxe/Developer/amphoraxe/dev-llm.amphoraxe.ca/amp_llm_v3/standalone modules/agent_annotate/results/json/${HELDOUT_JOB}.json"),
    Path("/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/amp_llm_v3/standalone modules/agent_annotate/results/json/${HELDOUT_JOB}.json"),
]
job_path = next((p for p in candidates if p.exists()), None)
if not job_path:
    print(f"  could not find ${HELDOUT_JOB}.json in any of {candidates}")
    sys.exit(1)
job = json.load(open(job_path))
agents_of_interest = ("nih_reporter", "fda_drugs", "sec_edgar")
counts = {a: {"any_citations": 0, "approved_drugs": 0} for a in agents_of_interest}
total = 0
for t in job.get("trials", []) or job.get("results", []):
    total += 1
    for r in t.get("research_results", []) or []:
        ag = r.get("agent_name")
        if ag not in agents_of_interest:
            continue
        if r.get("citations"):
            counts[ag]["any_citations"] += 1
        rd = r.get("raw_data", {}) or {}
        if any(k.endswith("_approved") and v is True for k, v in rd.items()):
            counts[ag]["approved_drugs"] += 1
print(f"  Trials: {total}")
for ag in agents_of_interest:
    c = counts[ag]
    pct_cite = 100 * c["any_citations"] / total if total else 0
    print(f"  {ag:15s}: cited on {c['any_citations']:>2}/{total} ({pct_cite:5.1f}%)" +
          (f", FDA-approved on {c['approved_drugs']}" if ag == "fda_drugs" else ""))
EOF
echo

echo "── 4. v42.7.7-11 path firing diagnostics ───────────────"
$PY - <<EOF
import json, sys
from pathlib import Path
candidates = [
    Path("/Users/amphoraxe/Developer/amphoraxe/dev-llm.amphoraxe.ca/amp_llm_v3/standalone modules/agent_annotate/results/json/${HELDOUT_JOB}.json"),
    Path("/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/amp_llm_v3/standalone modules/agent_annotate/results/json/${HELDOUT_JOB}.json"),
]
job_path = next((p for p in candidates if p.exists()), None)
if not job_path:
    sys.exit(0)
job = json.load(open(job_path))
trials = job.get("trials", []) or job.get("results", [])
counts = {
    "vaccine_trials":               0,  # is_vaccine_trial true (v42.7.7 detector)
    "vaccine_with_immuno":          0,  # vaccine + ≥1 immunogenicity keyword (v42.7.7 override eligible)
    "fda_approved_drugs":           0,  # ≥1 fda_drugs_*_approved=True (v42.7.8 override eligible)
    "sec_edgar_disclosed":          0,  # ≥1 SEC EDGAR citation (v42.7.8 context)
    "nih_reporter_funded":          0,  # ≥1 NIH RePORTER citation (v42.7.6 context)
}
# We can't introspect the dossier directly from saved trials, but we can
# cross-reference research_results + outcome reasoning text.
for t in trials:
    rr = t.get("research_results", []) or []
    has_fda = False; has_sec = False; has_nih = False
    intervention_names = []
    intervention_types = []
    for r in rr:
        ag = r.get("agent_name")
        if ag == "fda_drugs":
            rd = r.get("raw_data", {}) or {}
            if any(k.endswith("_approved") and v is True for k, v in rd.items()):
                has_fda = True
        elif ag == "sec_edgar":
            if r.get("citations"):
                has_sec = True
        elif ag == "nih_reporter":
            if r.get("citations"):
                has_nih = True
        elif ag == "clinical_protocol":
            rd = r.get("raw_data", {}) or {}
            proto = rd.get("protocol_section") or rd.get("protocolSection") or {}
            ai = proto.get("armsInterventionsModule", {}) or {}
            for it in ai.get("interventions", []) or []:
                if isinstance(it, dict):
                    n = (it.get("name") or "").strip()
                    if n:
                        intervention_names.append(n)
                        intervention_types.append((it.get("type") or "").upper())
    # Detect vaccine via name tokens (mirrors outcome.py:_VACCINE_NAME_TOKENS)
    _VAC = ("vaccine", "vaccination", "vaccinated", "immunotherapy",
            "immunisation", "immunization", "immunogen")
    is_vaccine = any(any(tok in n.lower() for tok in _VAC) for n in intervention_names)
    if is_vaccine:
        counts["vaccine_trials"] += 1
    # Check outcome reasoning for immunogenicity language
    has_immuno = False
    for a in t.get("annotations", []) or []:
        if a.get("field_name") == "outcome":
            r = (a.get("reasoning") or "").lower()
            for kw in ("induces immune", "antibody response", "antibody titer",
                      "t cell response", "seroconversion", "immunogen"):
                if kw in r:
                    has_immuno = True
                    break
            break
    if is_vaccine and has_immuno:
        counts["vaccine_with_immuno"] += 1
    if has_fda:
        counts["fda_approved_drugs"] += 1
    if has_sec:
        counts["sec_edgar_disclosed"] += 1
    if has_nih:
        counts["nih_reporter_funded"] += 1
total = len(trials)
print(f"  Trials analyzed: {total}")
for k, v in counts.items():
    pct = 100 * v / total if total else 0
    print(f"  {k:30s}: {v:>2}/{total} ({pct:5.1f}%)")
EOF
echo

echo "── 5. Evidence_grade distribution (commit-accuracy) ────"
$PY "$THIS_DIR/commit_accuracy_report.py" "$HELDOUT_JOB" 2>&1 | head -80
echo

echo "── 6. Outcome + delivery miss-pattern tally ────────────"
$PY "$THIS_DIR/cross_job_miss_patterns.py" "$HELDOUT_JOB" --field outcome 2>&1 | tail -25
echo
$PY "$THIS_DIR/cross_job_miss_patterns.py" "$HELDOUT_JOB" --field delivery_mode 2>&1 | tail -15
