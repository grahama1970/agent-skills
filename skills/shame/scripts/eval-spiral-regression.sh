#!/usr/bin/env bash
# Spiral-regression guard (incident 2026-09-08): runs the REAL stop-boundary
# checker via `run.sh preflight` against the exact candidate shapes that caused
# the rejection spiral, and asserts each is classified correctly.
#
# usage: eval-spiral-regression.sh prose-list|unbacked-verified|compliant
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

proof="$work/proof.txt"
printf 'spiral-guard-proof-token\n' > "$proof"

case "${1:?mode required}" in
    prose-list)
        # The spiral's first shape: a prose "Status Report" list, no fenced JSON.
        cat > "$work/c.md" <<EOF
Work is done.

Status Report
- Goal: something
- State: done
- Verified: some command -> some result
- Proof: $proof
EOF
        expect="missing_agent_status_json"
        ;;
    unbacked-verified)
        # The spiral's second shape: shell command/result pair vs a text proof.
        cat > "$work/c.md" <<EOF
Work is done.

\`\`\`json
{"schema": "pi.agent_status.v1", "goal": "g", "state": "done",
 "changed": ["no change: guard fixture"],
 "verified": [{"command": "git show --stat HEAD", "result": "spiral-guard-proof-token"}],
 "proof": ["$proof"]}
\`\`\`
EOF
        expect="verified_not_backed_by_proof"
        ;;
    compliant)
        # The documented exit: read-command verified backed by the proof file.
        cat > "$work/c.md" <<EOF
Work is done.

\`\`\`json
{"schema": "pi.agent_status.v1", "goal": "g", "state": "done",
 "changed": ["no change: guard fixture"],
 "verified": [{"command": "read $proof", "result": "spiral-guard-proof-token"}],
 "proof": ["$proof"]}
\`\`\`
EOF
        expect="valid_agent_status_json"
        ;;
    *) echo "unknown mode: $1" >&2; exit 2 ;;
esac

# preflight exits non-zero on reject; that is expected data here, not an error
out="$("$SKILL_DIR/run.sh" preflight "$work/c.md" || true)"
echo "$out"
python3 - "$expect" <<PY
import json, sys
out = json.loads('''$out''')
expect = sys.argv[1]
codes = out.get("reason_codes") or []
if expect == "valid_agent_status_json":
    assert out["decision"] == "pass" and expect in codes, (out["decision"], codes)
else:
    assert out["decision"] == "reject" and expect in codes, (out["decision"], codes)
print(f"SPIRAL_GUARD_OK mode-expected={expect}")
PY
