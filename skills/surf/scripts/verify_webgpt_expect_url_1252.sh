#!/usr/bin/env bash
# Live verifier for agent-skills#1252: a webgpt.submit with --tab-id and
# --expect-url must clear the identity guard even amid many ChatGPT tabs
# (was: unverified_tab_id_with_multiple_chatgpt_tabs -> submitted_to_chatgpt
# false). Exit 0 iff tab_identity_preflight.ok is true and the run reaches
# submitted_to_chatgpt=true. Requires an ask-provisioned chatgpt tab id.
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TAB="${1:-}"
[ -z "$TAB" ] && { echo "usage: $0 <chatgpt-tab-id>" >&2; exit 2; }
tmp="$(mktemp -d)"
printf 'Reply in one short sentence: what is 2+2?\n' > "$tmp/in.md"
url="$("$SKILL_DIR/run.sh" tab.list --json 2>/dev/null | python3 -c "import json,sys;
tabs=json.load(sys.stdin); tabs=tabs.get('tabs') if isinstance(tabs,dict) else tabs;
print(next((t.get('url','') for t in tabs if str(t.get('id'))=='$TAB'), 'https://chatgpt.com/'))" 2>/dev/null || echo 'https://chatgpt.com/')"
timeout 300 "$SKILL_DIR/run.sh" webgpt.submit --input "$tmp/in.md" \
  --output "$tmp/out.md" --raw-output "$tmp/raw.md" --meta-output "$tmp/meta.json" \
  --tab-id "$TAB" --expect-url "$url" --no-activate >/dev/null 2>&1 || true
python3 - "$tmp/meta.json" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
pf = (m.get("tab_identity_preflight") or {}).get("ok")
submitted = m.get("submitted_to_chatgpt")
count = (m.get("tab_identity_preflight") or {}).get("chatgpt_tabs_count")
if pf is True and submitted is True:
    print(f"PASS: preflight cleared with {count} chatgpt tabs open; submitted_to_chatgpt=true")
    sys.exit(0)
print(f"FAIL: preflight_ok={pf} submitted={submitted} failure={m.get('failure')}")
sys.exit(1)
PY
