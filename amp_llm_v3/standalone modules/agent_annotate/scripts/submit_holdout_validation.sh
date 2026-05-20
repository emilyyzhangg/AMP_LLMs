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
ALLOW_TEST_BATCH=0
for arg in "$@"; do
    case "$arg" in
        --dev) PORT=9005; HOST="dev" ;;
        --check-sync) CHECK_SYNC=1 ;;
        --test-batch) ALLOW_TEST_BATCH=1 ;;
        --slice-a|--slice-b|--slice-c|--slice-d|--slice-e|--slice-f|--slice-g|--slice-h|--slice-i|--slice-j|--slice-k|--slice-m|--milestone|--production-gate|--smoke-v23|--full-corpus-1|--full-corpus-2|--test-batch-50) ;;  # handled below
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
        --slice-f) SLICE="$THIS_DIR/holdout_outcome_slice_f_v42_7_23.json" ;;
        # slice-G: v42.8.1+v42.8.2 validation. 20 NCTs all with failure-class
        # outcome (8 failed-completed + 8 terminated + 4 withdrawn) and
        # GT RfF consensus, picked to exercise both the RfF emission gate
        # (lever 1) and the strong-failure publication override (lever 2).
        # Controlled re-use of full-corpus NCTs — they have been measured
        # but never used in iteration prompts or EDAM corrections.
        --slice-g) SLICE="$THIS_DIR/holdout_outcome_slice_g_v42_8_validation.json" ;;
        # slice-H: v42.8.3 (Lever 3 pub-to-trial matcher) validation. 20 NCTs:
        # 4 slice-G failed-completed Unknown misses (direct test of whether
        # the matcher surfaces pubs the existing pipeline missed),
        # 12 positive→unknown full-corpus misses (dominant outcome miss
        # class that v42.8.3 + widened trial_evidence_count gates aim to
        # close), 2 known-good positives (regression check), 2 terminated
        # (stability check). Controlled re-use of full-corpus NCTs —
        # measured but never used in iteration prompts or EDAM.
        --slice-h) SLICE="$THIS_DIR/holdout_outcome_slice_h_v42_8_3.json" ;;
        # slice-I: v42.8.4 (Lever 4 drug-code resolver) validation. 20 NCTs:
        # 12 sequence-miss NCTs with pharma-code interventions (GSK3008348,
        # ABY-029, GT-001, AMG 334, TRV027, TH1902, DSP-7888, PGV-001,
        # CNP-104, XW003, ATX-101, GLSI-100) — direct Lever 4 test;
        # 4 sequence-miss NCTs with non-code interventions (control); 4
        # sequence-hit NCTs (regression check). Controlled re-use of
        # full-corpus NCTs.
        --slice-i) SLICE="$THIS_DIR/holdout_outcome_slice_i_v42_8_4.json" ;;
        # slice-J: v42.8.5 (Lever 5 press-release agent) validation. 20 NCTs:
        # 14 NCT05+ pos→unk full-corpus misses (Lever 5 target = recency-
        # driven outcome miss class where literature is sparse but
        # sponsor press releases exist) + 4 older pos→unk + 2 known-good
        # positives (regression check). Controlled re-use of full-corpus
        # NCTs.
        --slice-j) SLICE="$THIS_DIR/holdout_outcome_slice_j_v42_8_5.json" ;;
        # slice-K: v42.8.5a (Lever 5 override tightening) validation. 20 NCTs:
        # 15 unknown-GT false flips from full-corpus #105+#106 (Lever 5 fired
        # but GT=Unknown — cross-trial-name confusion class) + 5 slice-J
        # confirmed wins (regression check that high-confidence flips
        # still fire). Decision rule: false flips → Unknown ≥10/15
        # AND regression check ≥3/5 stay Positive.
        --slice-k) SLICE="$THIS_DIR/holdout_outcome_slice_k_v42_8_5a.json" ;;
        # slice-M: v42.8.5b pre-Job-#104 decision-rule verification. 58 NCTs
        # (~12h on prod). Direct measurement of: (a) Lever 5 conversion on
        # pos→unk class (30 NCTs, 20 NCT05+ + 10 older); (b) false-flip
        # blocking on unknown-GT+PR (8 NCTs, residual after slice-K exclusion);
        # (c) Lever 1 RfF default-mapping on terminated/withdrawn (10 NCTs);
        # (d) regression check on known-good positives + failed-completed
        # (10 NCTs). Smarter than re-running 630 NCTs when we know
        # classification/peptide/delivery are stable.
        --slice-m) SLICE="$THIS_DIR/holdout_outcome_slice_m_v42_8_5b.json" ;;
        # Milestone validation: 147-NCT combined slice (Job #83 baseline +
        # held-out A/B/C/D). Used to certify accuracy with ±8pp CI
        # half-width, ~24h overnight run. Triggered when iteration cycles
        # show outcome+sequence stable across 2+ slices. See
        # CONTINUATION_PLAN's "Production Goals" section.
        --milestone) SLICE="$THIS_DIR/milestone_validation_v42_7_22.json" ;;
        # Production gate: 250-NCT FINAL accuracy certification.
        # Combines milestone (147) + slice-E (20) + slice-F (20) + 63
        # additional GT-scoreable NCTs from the residual + test-batch
        # reservation. Triggered ONLY when 147-NCT milestone confirms
        # outcome ≥65% AND no field regresses below per-field target.
        # 95% CI half-width ±6.2pp at p=0.5, ±5.7pp at p=0.7. Cost: ~41h.
        --production-gate) SLICE="$THIS_DIR/production_gate_v42_7_22.json" ;;
        # v42.7.23 targeted smoke: 5 NCTs from Job #100 milestone where
        # the v31 radiotracer rule emitted Other but GT says Injection
        # (NCT03069989, NCT03164486, NCT05940298, NCT05968846, NCT06443762).
        # Validates the radiotracer-with-explicit-injection override.
        # Cost: ~50 min on dev. Success = all 5 emit Injection/Infusion.
        --smoke-v23) SLICE="$THIS_DIR/smoke_v42_7_23_radiotracer.json" ;;
        # Full-corpus annotation (post-production-gate). 315 NCTs each;
        # the full 630-NCT training_csv-minus-test_batch universe split
        # to fit under the API's 500-NCT MAX_BATCH_SIZE limit. Cost
        # estimate per batch: ~50-80 hours on prod (~10-16 min/trial).
        # Submit batch 1, wait for completion, then submit batch 2.
        --full-corpus-1) SLICE="$THIS_DIR/full_corpus_batch_1.json" ;;
        --full-corpus-2) SLICE="$THIS_DIR/full_corpus_batch_2.json" ;;
        # Held-out test-set certification (Job #104, post full-corpus). 50
        # NCTs reserved by API contract for unbiased final measurement —
        # never seen by training/iteration/gate/full-corpus. Requires
        # --test-batch flag to bypass the router's training-CSV gate.
        # Cost: ~8h on prod. Compare per-field accuracy to Job #101 gate
        # — if within ±6.3pp CI, the gate's claim certifies on truly
        # unseen data.
        --test-batch-50) SLICE="$THIS_DIR/test_batch_50.json"; ALLOW_TEST_BATCH=1 ;;
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
if [ "$ALLOW_TEST_BATCH" = "1" ]; then
    BODY="{\"nct_ids\": $NCT_LIST, \"allow_test_batch\": true}"
else
    BODY="{\"nct_ids\": $NCT_LIST}"
fi
RESP=$(curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d "$BODY" "http://localhost:${PORT}/api/jobs")
JOB_ID=$(echo "$RESP" | $PY -c "import sys,json; print(json.load(sys.stdin).get('job_id',''))" 2>/dev/null)

if [ -z "$JOB_ID" ]; then
    echo "submit failed; raw response:" >&2
    echo "$RESP" >&2
    exit 1
fi

echo "Submitted held-out 30-NCT validation on $HOST: job_id=$JOB_ID"
echo "Track:    curl -s -H 'Authorization: Bearer \$TOKEN' http://localhost:${PORT}/api/jobs/${JOB_ID}"
echo "Compare:  python3 scripts/compare_jobs.py 51a6c2a308f8 ${JOB_ID}     # vs Job #83 baseline"
