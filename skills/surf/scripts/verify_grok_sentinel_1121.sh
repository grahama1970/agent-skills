#!/usr/bin/env bash
# Live verifier for agent-skills#1121: the webgrok lane must emit a
# GROK_DONE sentinel and never the WebGPT wrapper/sentinel. Exit 0 iff the
# wrapper-injection defect is gone — independent of grok provider auth
# (a logged-out tab yields a typed grok_auth_required, which is correct
# fail-closed, not the mislabeled missing_sentinel the bug produced).
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TAB_ID="${1:-}"
[ -z "$TAB_ID" ] && { echo "usage: $0 <grok-tab-id>" >&2; exit 2; }

tmp="$(mktemp -d)"
printf 'Reply in one short sentence: what is 2+2?\n' > "$tmp/in.md"
timeout 300 "$SKILL_DIR/run.sh" grok.submit \
  --input "$tmp/in.md" --output "$tmp/out.md" \
  --raw-output "$tmp/raw.md" --meta-output "$tmp/meta.json" \
  --tab-id "$TAB_ID" --no-activate >/dev/null 2>&1 || true

python3 - "$tmp/meta.json" <<'PY'
import json, sys
meta = json.load(open(sys.argv[1]))
sentinel = str(meta.get("sentinel") or "")
failure = str(meta.get("failure") or "")
ok = True
if "GROK_DONE" not in sentinel:
    print(f"FAIL: sentinel is not GROK_DONE: {sentinel!r}"); ok = False
if "WEBGPT" in sentinel.upper():
    print(f"FAIL: WebGPT wrapper sentinel leaked into grok lane: {sentinel!r}"); ok = False
if failure == "missing_sentinel":
    print("FAIL: mislabeled missing_sentinel (the #1121 defect)"); ok = False
if ok:
    print(f"PASS: grok lane emits {sentinel}; failure={failure or 'none'} (typed, not wrapper-induced)")
sys.exit(0 if ok else 1)
PY
