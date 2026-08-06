#!/usr/bin/env bash
# Live verifier for agent-skills#1138: kimi.submit composer insertion must
# accept a plain-markdown prompt (was: "composer did not receive inserted
# text"). Exit 0 iff a submit against a valid kimi tab reaches
# proof_status=response_proven with submitted_to_kimi=true.
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TAB_ID="${1:-}"
[ -z "$TAB_ID" ] && { echo "usage: $0 <kimi-tab-id>" >&2; exit 2; }
tmp="$(mktemp -d)"
printf '# Review request\n\nReply in one short paragraph, then stop.\n' > "$tmp/in.md"
timeout 300 "$SKILL_DIR/run.sh" kimi.submit --input "$tmp/in.md" \
  --output "$tmp/out.md" --raw-output "$tmp/raw.md" \
  --meta-output "$tmp/meta.json" --tab-id "$TAB_ID" --no-activate >/dev/null 2>&1 || true
python3 - "$tmp/meta.json" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
ok = m.get("proof_status") == "response_proven" and m.get("submitted_to_kimi") is True
if ok:
    print(f"PASS: composer inserted + submitted; response_proven, {m.get('raw_chars')} chars")
else:
    print(f"FAIL: proof_status={m.get('proof_status')} submitted={m.get('submitted_to_kimi')}")
sys.exit(0 if ok else 1)
PY
