#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-$(pwd)}"
python3 "$ROOT/skills/personaplex/tests/test_p11_wire_chatwell_patch.py"
python3 "$ROOT/skills/personaplex/scripts/apply_p11_wire_chatwell.py" --repo-root "$ROOT"

echo "P11 ChatWell PersonaPlex wiring sanity complete"
echo "Expected exit code: 0 when ChatTab.tsx contains the known piChat.send(query, type) seam"
