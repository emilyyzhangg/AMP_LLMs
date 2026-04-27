#!/bin/bash
# Full regression suite for the agent-annotate package.
#
# Runs in three tiers:
#   1. SOURCE-LEVEL TESTS — all scripts/test_v42_*.py (millisec, no network)
#   2. TRIP-WIRES — scripts/test_v42_trip_wires.py (millisec, no network)
#   3. LIVE INTEGRATION — scripts/test_*_live.py (real public APIs, ~30s each)
#
# Use before any merge to main, or as a sanity check after refactors.
# Exits 0 only if every test in tiers 1+2 passes; tier 3 failures are
# warned-but-not-fatal (third-party APIs flap occasionally).

set -uo pipefail

PY=/Users/amphoraxe/Developer/amphoraxe/dev-llm.amphoraxe.ca/amp_llm_v3/llm_env/bin/python
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

print_section() {
    printf '\n========================================\n%s\n========================================\n' "$1"
}

source_failures=0
total_files=0
total_tests=0
passed_tests=0

print_section "Tier 1 — Source-level v42 tests"
for f in scripts/test_v42_*.py; do
    total_files=$((total_files + 1))
    last=$($PY "$f" 2>&1 | tail -1)
    case "$last" in
        OK:*)
            count=$(echo "$last" | sed -nE 's/.*OK: ([0-9]+)\/([0-9]+).*/\1 \2/p')
            read -r p t <<<"$count"
            passed_tests=$((passed_tests + p))
            total_tests=$((total_tests + t))
            printf '  %s :: %s\n' "$last" "$(basename "$f")"
            ;;
        *)
            source_failures=$((source_failures + 1))
            printf '  %s :: %s  ← FAILED\n' "$last" "$(basename "$f")"
            ;;
    esac
done

print_section "Tier 2 — Trip-wire regression"
last=$($PY scripts/test_v42_trip_wires.py 2>&1 | tail -1)
case "$last" in
    OK:*) printf '  %s :: trip-wires\n' "$last" ;;
    *) source_failures=$((source_failures + 1))
       printf '  %s :: trip-wires  ← FAILED\n' "$last" ;;
esac

print_section "Tier 3 — Live integration (third-party APIs)"
live_warnings=0
for f in scripts/test_sec_edgar_live.py scripts/test_fda_drugs_live.py scripts/test_nih_reporter_live.py; do
    [ -f "$f" ] || continue
    last=$($PY "$f" 2>&1 | tail -1)
    case "$last" in
        OK:*) printf '  %s :: %s\n' "$last" "$(basename "$f")" ;;
        *) live_warnings=$((live_warnings + 1))
           printf '  %s :: %s  ← live API issue (non-fatal)\n' "$last" "$(basename "$f")" ;;
    esac
done

print_section "Summary"
printf '  Source files: %d (%d tests passed)\n' "$total_files" "$passed_tests"
printf '  Source failures: %d  (must be 0 to merge)\n' "$source_failures"
printf '  Live API warnings: %d  (non-fatal, retry if it persists)\n' "$live_warnings"

if [ "$source_failures" -eq 0 ]; then
    echo
    echo "✓ Regression PASS — safe to merge."
    exit 0
else
    echo
    echo "✗ Regression FAIL — fix source failures before merging."
    exit 1
fi
