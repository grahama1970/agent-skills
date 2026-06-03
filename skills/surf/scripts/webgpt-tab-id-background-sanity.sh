#!/usr/bin/env bash
# Fast real-world e2e: explicit Chrome tab id + CDP targeting while another tab stays active.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_SH="${SURF_RUN_SH:-${SKILL_DIR}/run.sh}"
# shellcheck source=lib/webgpt_resolve.sh
source "${SCRIPT_DIR}/lib/webgpt_resolve.sh"

usage() {
  cat <<'EOF'
Usage:
  surf webgpt.tab-id-background-sanity [options]

Proves surf targets a specific Chrome tab by id without foregrounding it.

Options:
  --tab-id ID
  --url URL          ChatGPT tab (Tab ID Viewer). Default: non-active chatgpt.com tab.
  --output-dir PATH    Artifacts. Default: /tmp/surf-tabid-bg-<timestamp>
  --json               Machine-readable stdout only
  -h, --help           Show help

Environment:
  SURF_WEBGPT_SANITY_TAB_ID   Default --tab-id (also used by ./sanity.sh)

Exit: 0 PASS | 2 usage | 3 SKIP | 5 FAIL
EOF
}

tab_id=""
target_url=""
output_dir=""
json_only=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tab-id) tab_id="${2:-}"; shift 2 ;;
    --url) target_url="${2:-}"; shift 2 ;;
    --output-dir) output_dir="${2:-}"; shift 2 ;;
    --json) json_only=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

tab_id="${tab_id:-${SURF_WEBGPT_SANITY_TAB_ID:-}}"

if [[ -z "$tab_id" && -n "$target_url" ]]; then
  tab_list_text="$("$RUN_SH" tab.list 2>/dev/null || true)"
  if webgpt_resolve_url_from_list "$target_url" "$tab_list_text"; then
    tab_id="$resolved_tab_id"
  else
    echo "FAIL: could not resolve --url: $target_url (${resolve_error:-})" >&2
    exit 5
  fi
fi

if [[ -z "${SURF_RUN_SH:-}" && ! -S /tmp/surf.sock ]]; then
  echo "SKIP: surf extension socket missing at /tmp/surf.sock" >&2
  exit 3
fi

if [[ -z "$output_dir" ]]; then
  output_dir="/tmp/surf-tabid-bg-$(date -u +%Y%m%dT%H%M%SZ)"
fi
mkdir -p "$output_dir"

focus_before_json="$("$RUN_SH" focus.state --json 2>/dev/null || echo '{}')"
active_before="$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('activeTabId') or '')" "$focus_before_json")"

if [[ -z "$tab_id" ]]; then
  tab_id="$(
    "$RUN_SH" tab.list 2>/dev/null \
      | awk -F '\t' -v active="$active_before" '
          $3 ~ /^https:\/\/chatgpt\.com/ && $1 != active && $1 != "" {
            print $1
            exit
          }
        '
  )"
fi

if [[ -z "$tab_id" ]]; then
  echo "SKIP: no --tab-id and no non-active chatgpt.com tab" >&2
  exit 3
fi

tab_id="$(printf '%s' "$tab_id" | tr -cd '0-9' | head -c 20)"

log="$output_dir/sanity.log"
{
  echo "controlled_tab_id=$tab_id active_before=$active_before"
  echo "focus_before=$focus_before_json"
} >"$log"

if [[ "$tab_id" == "$active_before" ]]; then
  echo "WARN: controlled tab is already active; switch tabs for stronger proof" >>"$log"
fi

set +e
js_out="$("$RUN_SH" js --tab-id "$tab_id" 'return { title: document.title, url: location.href, host: location.hostname }' 2>>"$log")"
js_status=$?
click_out="$("$RUN_SH" click --selector body --tab-id "$tab_id" --no-screenshot 2>>"$log")"
click_status=$?
set -e

focus_after_json="$("$RUN_SH" focus.state --json 2>/dev/null || echo '{}')"

result_json="$output_dir/tab-id-background-sanity.json"
python3 - "$result_json" "$tab_id" "$active_before" "$js_status" "$click_status" "$js_out" "$click_out" "$focus_before_json" "$focus_after_json" "$log" <<'PY'
import json, pathlib, sys
out_path, tab_id, active_before, js_status, click_status, js_out, click_out, fb, fa, log_path = sys.argv[1:]

def pf(s):
    try:
        return json.loads(s)
    except Exception:
        return {}

before, after = pf(fb), pf(fa)
focus_changed = (
    before.get("focusedWindowId") != after.get("focusedWindowId")
    or before.get("activeTabId") != after.get("activeTabId")
)
js_ok = int(js_status) == 0 and "chatgpt.com" in js_out
click_ok = int(click_status) == 0 and click_out.strip() == "OK"
focus_ok = not focus_changed
status = "pass" if js_ok and click_ok and focus_ok else "fail"
failure = None
if not js_ok:
    failure = "cdp_js_failed_or_wrong_host"
elif not click_ok:
    failure = "cdp_click_failed"
elif not focus_ok:
    failure = "focus_stolen_during_probe"

result = {
    "status": status,
    "failure": failure,
    "controlled_tab_id": tab_id,
    "active_tab_before": before.get("activeTabId"),
    "active_tab_after": after.get("activeTabId"),
    "focus_changed": focus_changed,
    "js_ok": js_ok,
    "click_ok": click_ok,
    "js_sample": js_out[:500],
    "log_path": log_path,
    "notes": [
        "CDP js+click on --tab-id while activeTabId unchanged.",
        "Full sentinel: surf webgpt.no-activate-sanity --tab-id ID",
    ],
}
pathlib.Path(out_path).write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
raise SystemExit(0 if status == "pass" else 5)
PY

if [[ "$json_only" -eq 0 ]]; then
  echo "Artifacts: $output_dir"
fi
