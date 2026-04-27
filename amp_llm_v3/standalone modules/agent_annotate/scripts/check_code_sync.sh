#!/bin/bash
# check_code_sync.sh — assert the running annotate service is on the
# same commit as the on-disk HEAD before declaring a smoke pass.
#
# Background: the autoupdater LaunchDaemon (`com.amplm.autoupdate.dev`
# / `com.amplm.autoupdate`) pulls every 30s but skips the annotate
# restart while jobs are active. Three times in v42.6/v42.7 we shipped
# code, watched a smoke pass, and only later realized the smoke had
# silently run on the previous commit. This helper closes that gap.
#
# Usage:
#   scripts/check_code_sync.sh                  # dev (port 9005)
#   scripts/check_code_sync.sh --prod           # prod (port 8005)
#
# Exit:
#   0 — boot_commit_full == disk_commit_full (safe to trust smoke output)
#   1 — drift detected (force restart, then re-run smoke)
#   2 — endpoint unreachable / parse error

set -euo pipefail

PORT=9005
if [ "${1:-}" = "--prod" ]; then
    PORT=8005
fi

URL="http://localhost:${PORT}/api/diagnostics/code_sync"

# Pull a session token the same way Claude's other helpers do.
TOKEN=$(sqlite3 "/Users/amphoraxe/Developer/amphoraxe/auth.amphoraxe.ca/data/auth.db" \
    "SELECT token FROM sessions WHERE expires_at > datetime('now') ORDER BY created_at DESC LIMIT 1;")
PY=/Users/amphoraxe/Developer/amphoraxe/dev-llm.amphoraxe.ca/amp_llm_v3/llm_env/bin/python

response=$(curl -s -m 10 -H "Authorization: Bearer $TOKEN" "$URL")
if [ -z "$response" ]; then
    echo "ERROR: empty response from $URL"
    exit 2
fi

read -r in_sync boot disk active <<<"$(echo "$response" | $PY -c '
import sys, json
d = json.load(sys.stdin)
print(d.get("code_in_sync"), d.get("boot_commit_short", "?"),
      d.get("disk_commit_short", "?"), d.get("active_jobs", "?"))
' 2>/dev/null || echo "ERR ? ? ?")"

if [ "$in_sync" = "ERR" ]; then
    echo "ERROR: could not parse $URL response"
    echo "Raw: $response"
    exit 2
fi

echo "boot=$boot  disk=$disk  active_jobs=$active  code_in_sync=$in_sync"

if [ "$in_sync" = "True" ]; then
    exit 0
fi

cat <<EOF >&2

DRIFT: running process is on commit ${boot} but on-disk HEAD is ${disk}.
The autoupdater skipped restart (likely because active_jobs=${active}).
Push a no-op trigger commit, OR cancel active jobs and let autoupdater
restart, before trusting any smoke validation.
EOF
exit 1
