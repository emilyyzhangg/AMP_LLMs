#!/bin/bash
# Submit the 30-NCT held-out outcome slice for validation.
#
# Usage:
#   scripts/submit_holdout_validation.sh                  # prod (port 8005)
#   scripts/submit_holdout_validation.sh --dev            # dev (port 9005)
#   scripts/submit_holdout_validation.sh --check-sync     # assert
#       code_in_sync == true before submitting (recommended)
#
# Prints the submitted job_id on success.

set -euo pipefail

PORT=8005
HOST="prod"
CHECK_SYNC=0
for arg in "$@"; do
    case "$arg" in
        --dev) PORT=9005; HOST="dev" ;;
        --check-sync) CHECK_SYNC=1 ;;
        --slice-a|--slice-b|--slice-c|--slice-d|--slice-e) ;;  # handled below
        *) echo "unknown arg: $arg" >&2; exit 2 ;;
    esac
done

THIS_DIR="$(cd "$(dirname "$0")" && pwd)"
# Default to held-out-E (post-v42.7.18 cycle, ready for v42.7.19+ validation).
# Older slices retired:
#   A — Jobs #92 + #95 (v42.7.11 / v42.7.13)
#   B — Job #96 (revealed v42.7.13 over-correction)
#   C — Job #97 (validated v42.7.17 fix; outcome 68%)
#   D — Job #98 (v42.7.18 sequence-dict expansion)
# Per standard ML tune-set/held-out separation. --slice-a / -b / -c / -d
# force older slices (rarely needed; reproduce historical jobs only).
SLICE="$THIS_DIR/holdout_outcome_slice_e_v42_7_19.json"
for arg in "$@"; do
    case "$arg" in
        --slice-a) SLICE="$THIS_DIR/holdout_outcome_slice_v42_7_5.json" ;;
        --slice-b) SLICE="$THIS_DIR/holdout_outcome_slice_b_v42_7_14.json" ;;
        --slice-c) SLICE="$THIS_DIR/holdout_outcome_slice_c_v42_7_17.json" ;;
        --slice-d) SLICE="$THIS_DIR/holdout_outcome_slice_d_v42_7_18.json" ;;
        --slice-e) SLICE="$THIS_DIR/holdout_outcome_slice_e_v42_7_19.json" ;;
    esac
done
if [ ! -f "$SLICE" ]; then
    echo "slice file not found: $SLICE" >&2
    exit 2
fi

PY=/Users/amphoraxe/Developer/amphoraxe/dev-llm.amphoraxe.ca/amp_llm_v3/llm_env/bin/python
TOKEN=$(sqlite3 "/Users/amphoraxe/Developer/amphoraxe/auth.amphoraxe.ca/data/auth.db" \
    "SELECT token FROM sessions WHERE expires_at > datetime('now') ORDER BY created_at DESC LIMIT 1;")

if [ "$CHECK_SYNC" = "1" ]; then
    sync=$(curl -s -m 10 -H "Authorization: Bearer $TOKEN" \
        "http://localhost:${PORT}/api/diagnostics/code_sync" \
        | $PY -c "import sys,json; print(json.load(sys.stdin).get('code_in_sync'))" 2>/dev/null \
        || echo "ERROR")
    if [ "$sync" != "True" ]; then
        echo "ABORT: ${HOST} code_in_sync=${sync} — service is on stale memory." >&2
        echo "Force a restart (push a no-op commit OR ensure active_jobs=0 and wait 30s)." >&2
        exit 1
    fi
    echo "code_in_sync=True on $HOST — safe to submit"
fi

NCT_LIST=$(cat "$SLICE")
RESP=$(curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d "{\"nct_ids\": $NCT_LIST}" "http://localhost:${PORT}/api/jobs")
JOB_ID=$(echo "$RESP" | $PY -c "import sys,json; print(json.load(sys.stdin).get('job_id',''))" 2>/dev/null)

if [ -z "$JOB_ID" ]; then
    echo "submit failed; raw response:" >&2
    echo "$RESP" >&2
    exit 1
fi

echo "Submitted held-out 30-NCT validation on $HOST: job_id=$JOB_ID"
echo "Track:    curl -s -H 'Authorization: Bearer \$TOKEN' http://localhost:${PORT}/api/jobs/${JOB_ID}"
echo "Compare:  python3 scripts/compare_jobs.py 51a6c2a308f8 ${JOB_ID}     # vs Job #83 baseline"
