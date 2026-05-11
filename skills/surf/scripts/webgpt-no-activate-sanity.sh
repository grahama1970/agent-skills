#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_SH="${SURF_RUN_SH:-${SKILL_DIR}/run.sh}"

usage() {
  cat <<'EOF'
Usage:
  surf webgpt.no-activate-sanity --tab-id ID [options]

Runs a real ChatGPT/WebGPT sentinel round trip in background controlled-tab
mode (--no-activate) and asserts that the user's foreground tab/window did not
change AND the proof contract still holds.

Options:
  --tab-id ID          REQUIRED. Authenticated ChatGPT tab id to control.
  --output-dir PATH    Artifact directory. Default: /tmp/surf-webgpt-noact-<timestamp>
  --timeout SECONDS    Browser wait timeout. Default: 900.
  --model MODEL        Optional ChatGPT model selector label.
EOF
}

tab_id=""
output_dir=""
timeout_s=900
model=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tab-id) tab_id="${2:-}"; shift 2 ;;
    --output-dir) output_dir="${2:-}"; shift 2 ;;
    --timeout) timeout_s="${2:-}"; shift 2 ;;
    --model) model="${2:-}"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$tab_id" ]]; then
  echo "--tab-id is required for the no-activate sanity check." >&2
  usage >&2
  exit 2
fi

if [[ -z "$output_dir" ]]; then
  output_dir="/tmp/surf-webgpt-noact-$(date -u +%Y%m%dT%H%M%SZ)"
fi
mkdir -p "$output_dir"

request="$output_dir/01_request.md"
response="$output_dir/02_response.md"
meta="$output_dir/02_response.meta.json"
shot="$output_dir/no-activate-shot.png"

# Minimal but non-trivial prompt; the WebGPT proof contract still bites.
cat > "$request" <<'EOF'
Return Markdown with these exact sections, under 250 words total:

## Background-Tab Mode
## Why It Matters

Do not include code blocks. Obey the final marker instruction appended by the browser automation.
EOF

# Pre-run focus snapshot.
focus_before_json="$("$RUN_SH" focus.state --json 2>/dev/null || echo '{}')"

set +e
"$RUN_SH" webgpt.submit \
  --input "$request" \
  --output "$response" \
  --meta-output "$meta" \
  --tab-id "$tab_id" \
  --timeout "$timeout_s" \
  --stable-polls 3 \
  --no-activate \
  ${model:+--model "$model"}
submit_status=$?
set -e

# Post-run focus snapshot.
focus_after_json="$("$RUN_SH" focus.state --json 2>/dev/null || echo '{}')"

# Separately exercise the screenshot path with --no-activate to verify the CDP
# path works against a background tab and never falls back to captureVisibleTab.
set +e
"$RUN_SH" screenshot --tab-id "$tab_id" --output "$shot" --no-activate --json > "$output_dir/screenshot.json" 2> "$output_dir/screenshot.stderr.log"
screenshot_status=$?
set -e

python3 - "$meta" "$response" "$request" "$output_dir" "$shot" "$screenshot_status" "$submit_status" "$tab_id" "$focus_before_json" "$focus_after_json" "$output_dir/screenshot.json" <<'PY'
import json, pathlib, sys, re

meta_path, response_path, request_path, output_dir, shot_path = map(pathlib.Path, sys.argv[1:6])
screenshot_status = int(sys.argv[6])
submit_status = int(sys.argv[7])
requested_tab_id = sys.argv[8]
focus_before_s = sys.argv[9]
focus_after_s = sys.argv[10]
screenshot_meta_path = pathlib.Path(sys.argv[11])

def _parse(s):
    try:
        return json.loads(s)
    except Exception:
        return {}

focus_before = _parse(focus_before_s)
focus_after = _parse(focus_after_s)
screenshot_meta = _parse(screenshot_meta_path.read_text()) if screenshot_meta_path.exists() else {}

meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
text = response_path.read_text() if response_path.exists() else ""

required = ["Background-Tab Mode", "Why It Matters"]
missing = [
    item for item in required
    if not re.search(rf"(?m)^\s*#{{0,6}}\s*{re.escape(item)}\s*$", text)
]
bad_text = []
for needle in ["Skip to content", "Chat history", "You said:", "Completion contract for browser automation:"]:
    if needle in text:
        bad_text.append(needle)

# Focus-state assertions: must not change in --no-activate mode.
active_tab_before = focus_before.get("activeTabId")
active_tab_after = focus_after.get("activeTabId")
focused_window_before = focus_before.get("focusedWindowId")
focused_window_after = focus_after.get("focusedWindowId")
focus_changed = (
    active_tab_before != active_tab_after
    or focused_window_before != focused_window_after
)

# Screenshot method must be authoritative (CDP), not visible-tab fallback.
screenshot_method = screenshot_meta.get("method")
screenshot_authoritative = screenshot_meta.get("authoritative")

failures = []
if submit_status != 0:
    failures.append(f"submit_exit_code={submit_status}")
if meta.get("status") != "completed":
    failures.append(f"meta_status={meta.get('status')}")
if meta.get("failure"):
    failures.append(f"meta_failure={meta.get('failure')}")
if missing:
    failures.append(f"missing_sections={missing}")
if bad_text:
    failures.append(f"clean_response_contamination={bad_text}")
if not meta.get("raw_contains_sentinel"):
    failures.append("raw_missing_sentinel")
if meta.get("clean_contains_sentinel"):
    failures.append("clean_contains_sentinel")
if meta.get("no_activate") is not True:
    failures.append(f"meta.no_activate={meta.get('no_activate')}")
if focus_changed:
    failures.append(
        f"focus_changed: tab {active_tab_before}->{active_tab_after}, window {focused_window_before}->{focused_window_after}"
    )
if meta.get("focus_changed") is True:
    failures.append("meta.focus_changed=true (submit-side snapshot also detected drift)")
if str(meta.get("controlled_tab_id") or "") != requested_tab_id:
    failures.append(
        f"controlled_tab_id={meta.get('controlled_tab_id')} != requested {requested_tab_id}"
    )
if screenshot_status != 0:
    failures.append(f"screenshot_exit_code={screenshot_status}")
elif screenshot_method != "cdp" and screenshot_method != "cdp_fullpage":
    failures.append(f"screenshot_method={screenshot_method} (expected cdp)")
elif screenshot_authoritative is False:
    failures.append("screenshot_authoritative=false")

status = "pass" if not failures else "fail"
result = {
    "status": status,
    "failures": failures,
    "artifact_dir": str(output_dir),
    "request": str(request_path),
    "response": str(response_path),
    "meta": str(meta_path),
    "screenshot": str(shot_path) if shot_path.exists() else None,
    "screenshot_method": screenshot_method,
    "screenshot_authoritative": screenshot_authoritative,
    "submit_exit_code": submit_status,
    "meta_status": meta.get("status"),
    "meta_failure": meta.get("failure"),
    "no_activate": meta.get("no_activate"),
    "controlled_tab_id": meta.get("controlled_tab_id"),
    "requested_tab_id": requested_tab_id,
    "missing_sections": missing,
    "bad_clean_response_markers": bad_text,
    "raw_contains_sentinel": meta.get("raw_contains_sentinel"),
    "clean_contains_sentinel": meta.get("clean_contains_sentinel"),
    "active_tab_before": active_tab_before,
    "active_tab_after": active_tab_after,
    "focused_window_before": focused_window_before,
    "focused_window_after": focused_window_after,
    "focus_changed": focus_changed,
    "meta_focus_changed": meta.get("focus_changed"),
    "tab_was_created": meta.get("tab_was_created"),
    "activated": meta.get("activated"),
}
(output_dir / "no-activate-sanity-result.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
if status != "pass":
    raise SystemExit(1)
PY
