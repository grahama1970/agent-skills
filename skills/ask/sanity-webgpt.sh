#!/usr/bin/env bash
# Live e2e sanity for `$ask webgpt` (--oracle-backend webgpt).
#
# Exercises the full path:
#   /ask -> webgpt_runtime.call_webgpt -> surf webgpt.submit --no-activate
#   -> controlled ChatGPT tab -> sentinel round trip -> answer + meta.
#
# Pre-flight modes (mutually exclusive):
#   --tab-id ID        : control an existing chatgpt.com tab by id.
#   --url URL          : control an open ChatGPT conversation by exact URL.
#   --create-tab       : let surf create or pick a background ChatGPT tab
#                        (auto-mode for autonomous agent flows).
# If none are given AND auto-resolve cannot find exactly one chatgpt.com tab,
# the script prints a help message asking the user to choose.
#
# Run from the skill dir:
#   ./sanity-webgpt.sh --tab-id 837343543
#   ./sanity-webgpt.sh --create-tab
#   ./sanity-webgpt.sh --url "https://chatgpt.com/c/<convo>"
#
# Exit 0 on pass, 1 on fail. Prints a JSON summary either way.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_SH="${SCRIPT_DIR}/run.sh"
SURF_RUN="${ASK_SURF_RUN:-${SCRIPT_DIR}/../surf/run.sh}"

usage() {
  cat <<'EOF'
Usage:
  sanity-webgpt.sh [--tab-id ID | --url URL | --create-tab] [options]

Mutually-exclusive tab acquisition modes:
  --tab-id ID          Control an existing chatgpt.com tab by id.
  --url URL            Control an open ChatGPT conversation by exact URL.
  --create-tab         Let the agent create or pick a background tab via surf.

Other options:
  --output-dir DIR     Artifact directory (default: /tmp/ask-webgpt-sanity-<ts>)
  --timeout SECONDS    Round-trip timeout (default: 300)
  --help               Show this help
EOF
}

tab_id=""
target_url=""
create_tab=0
output_dir=""
timeout_s=300

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tab-id) tab_id="${2:-}"; shift 2 ;;
    --url) target_url="${2:-}"; shift 2 ;;
    --create-tab) create_tab=1; shift ;;
    --output-dir) output_dir="${2:-}"; shift 2 ;;
    --timeout) timeout_s="${2:-}"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

# Enforce mutual exclusion early.
mode_count=0
[[ -n "$tab_id" ]] && ((mode_count++)) || true
[[ -n "$target_url" ]] && ((mode_count++)) || true
[[ "$create_tab" -eq 1 ]] && ((mode_count++)) || true
if [[ $mode_count -gt 1 ]]; then
  echo "Choose at most one of: --tab-id, --url, --create-tab" >&2
  exit 2
fi

# Pre-flight: if no mode picked, try to auto-pick a single chatgpt.com tab.
# When 0 or >1 candidates exist, print a clear help block and exit 2 so the
# project agent (or human) knows exactly what to do next.
if [[ $mode_count -eq 0 ]]; then
  candidates="$("$SURF_RUN" tab.list 2>/dev/null | awk -F '\t' '$3 ~ /chatgpt\.com/ {print $0}' || true)"
  candidate_count=0
  if [[ -n "$candidates" ]]; then
    candidate_count="$(printf '%s\n' "$candidates" | wc -l | tr -d ' ')"
  fi
  if [[ "$candidate_count" == "1" ]]; then
    tab_id="$(printf '%s' "$candidates" | awk -F '\t' '{print $1}')"
    auto_resolved=1
  else
    script_path="$0"
    cat >&2 <<EOF
\$ask webgpt sanity needs a controlled ChatGPT tab. Pick one of:

  1. Open exactly one chatgpt.com tab in Chrome, then re-run with no flags.
  2. Pass --tab-id <id> (use the Tab ID Viewer Chrome extension to copy
     the id from the tab you want controlled), e.g.:
       $script_path --tab-id 837343564
  3. Pass --url <conversation-url> for a specific conversation, e.g.:
       $script_path --url "https://chatgpt.com/c/..."
  4. Pass --create-tab to let the agent create or pick a background
     chatgpt.com tab autonomously (no human-readable id needed):
       $script_path --create-tab

EOF
    if [[ "$candidate_count" -gt 1 ]]; then
      cat >&2 <<EOF
Open ChatGPT tab candidates (${candidate_count}) — pass --tab-id to choose:
$candidates

EOF
    else
      cat >&2 <<'EOF'
No chatgpt.com tabs are currently open.

EOF
    fi
    exit 2
  fi
fi

if [[ -z "$output_dir" ]]; then
  output_dir="/tmp/ask-webgpt-sanity-$(date -u +%Y%m%dT%H%M%SZ)"
fi
mkdir -p "$output_dir"

# Capture focus state BEFORE the call. The whole point of --no-activate is
# that this should be byte-identical after the call.
focus_before="$("$SURF_RUN" focus.state --json 2>/dev/null || echo '{}')"
printf '%s\n' "$focus_before" > "$output_dir/focus.before.json"

# Construct the $ask invocation. Use the `webgpt` model shorthand so the
# full alias-router path is exercised end-to-end.
ask_args=(ask "webgpt In one sentence, confirm this WebGPT sanity round trip succeeded by name (mention 'WebGPT sanity').")
ask_args+=(--ask-id "ask-webgpt-sanity-$(date -u +%Y%m%dT%H%M%SZ)")
ask_args+=(--run-output-root "$output_dir/ask-runs")
if [[ -n "$tab_id" ]]; then
  ask_args+=(--webgpt-tab-id "$tab_id")
elif [[ -n "$target_url" ]]; then
  ask_args+=(--webgpt-url "$target_url")
elif [[ "$create_tab" -eq 1 ]]; then
  ask_args+=(--webgpt-create-tab)
fi

set +e
"$RUN_SH" "${ask_args[@]}" > "$output_dir/ask.stdout.log" 2> "$output_dir/ask.stderr.log"
ask_status=$?
set -e

# Capture focus state AFTER the call.
focus_after="$("$SURF_RUN" focus.state --json 2>/dev/null || echo '{}')"
printf '%s\n' "$focus_after" > "$output_dir/focus.after.json"

# Find the run dir created by /ask.
ask_run_dir="$(/bin/ls -dt "$output_dir/ask-runs"/ask-* 2>/dev/null | head -1 || true)"
ask_status_file=""
ask_events_file=""
if [[ -n "$ask_run_dir" ]]; then
  ask_status_file="$(/bin/ls "$ask_run_dir"/*.status.json 2>/dev/null | head -1 || true)"
  ask_events_file="$(/bin/ls "$ask_run_dir"/*.events.jsonl 2>/dev/null | head -1 || true)"
fi

# Find the underlying webgpt artifact dir by reading the oracle_webgpt_call_finished
# event the runtime emits. Globbing /tmp/ask-webgpt-*/ is unreliable because the
# sanity script's own output dir matches the same prefix.
webgpt_meta=""
if [[ -n "$ask_events_file" && -f "$ask_events_file" ]]; then
  webgpt_artifact_dir="$(python3 - "$ask_events_file" <<'PY'
import json, pathlib, sys
events = pathlib.Path(sys.argv[1]).read_text().splitlines()
for line in reversed(events):
    try:
        ev = json.loads(line)
    except Exception:
        continue
    if ev.get("event") in {"oracle_webgpt_call_finished", "oracle_webgpt_call_started"}:
        artifact = ev.get("artifact_dir")
        if artifact:
            print(artifact)
            break
PY
)"
  if [[ -n "$webgpt_artifact_dir" && -f "$webgpt_artifact_dir/02_response.meta.json" ]]; then
    webgpt_meta="$webgpt_artifact_dir/02_response.meta.json"
  fi
fi

# Score the result.
python3 - "$ask_status" "$ask_status_file" "$webgpt_meta" "$output_dir/focus.before.json" "$output_dir/focus.after.json" "$tab_id" "$target_url" "$create_tab" "$output_dir" "${auto_resolved:-0}" <<'PY'
import json, pathlib, sys

ask_status = int(sys.argv[1])
ask_status_file = pathlib.Path(sys.argv[2]) if sys.argv[2] else None
webgpt_meta_path = pathlib.Path(sys.argv[3]) if sys.argv[3] else None
focus_before = json.loads(pathlib.Path(sys.argv[4]).read_text() or "{}")
focus_after = json.loads(pathlib.Path(sys.argv[5]).read_text() or "{}")
tab_id_arg = sys.argv[6]
url_arg = sys.argv[7]
create_tab = sys.argv[8] == "1"
output_dir = pathlib.Path(sys.argv[9])
auto_resolved = sys.argv[10] == "1"

def _load_json(p):
    if not p or not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}

ask_status_json = _load_json(ask_status_file)
webgpt_meta = _load_json(webgpt_meta_path)
result_summary = ask_status_json.get("result_summary", {})
oracle_alias = result_summary.get("oracle_model_alias") or {}

failures = []
if ask_status != 0:
    failures.append(f"ask_exit_code={ask_status}")
if ask_status_json.get("state") != "answered":
    failures.append(f"ask_state={ask_status_json.get('state')}")
if not result_summary.get("oracle_enabled"):
    failures.append("oracle_enabled=false")
if result_summary.get("oracle_model") != "webgpt":
    failures.append(f"oracle_model={result_summary.get('oracle_model')} (expected webgpt)")
if oracle_alias.get("oracle_backend") != "webgpt":
    failures.append(f"oracle_alias.backend={oracle_alias.get('oracle_backend')}")

served = result_summary.get("oracle_model_served") or ""
if not served.startswith("webgpt:") or len(served) <= len("webgpt:"):
    failures.append(f"oracle_model_served={served!r} (expected webgpt:<tab-id>)")
served_tab_id = served.split(":", 1)[1] if ":" in served else ""

if webgpt_meta.get("status") != "completed":
    failures.append(f"meta.status={webgpt_meta.get('status')}")
if webgpt_meta.get("failure"):
    failures.append(f"meta.failure={webgpt_meta.get('failure')}")
if webgpt_meta.get("no_activate") is not True:
    failures.append(f"meta.no_activate={webgpt_meta.get('no_activate')}")
if webgpt_meta.get("focus_changed") is True:
    failures.append("meta.focus_changed=true")
if not webgpt_meta.get("raw_contains_sentinel"):
    failures.append("meta.raw_contains_sentinel=false")
if webgpt_meta.get("clean_contains_sentinel"):
    failures.append("meta.clean_contains_sentinel=true")
contamination = webgpt_meta.get("clean_contamination_markers") or []
if contamination:
    failures.append(f"meta.clean_contamination_markers={contamination}")

controlled_tab_id = str(webgpt_meta.get("controlled_tab_id") or "").strip()
if tab_id_arg and controlled_tab_id and controlled_tab_id != tab_id_arg:
    failures.append(f"controlled_tab_id={controlled_tab_id} != requested {tab_id_arg}")
if served_tab_id and controlled_tab_id and served_tab_id != controlled_tab_id:
    failures.append(
        f"oracle_model_served tab={served_tab_id} != meta.controlled_tab_id={controlled_tab_id}"
    )

before_fw = focus_before.get("focusedWindowId")
after_fw = focus_after.get("focusedWindowId")
before_tab = focus_before.get("activeTabId")
after_tab = focus_after.get("activeTabId")
if before_fw != after_fw:
    failures.append(f"focused_window changed: {before_fw} -> {after_fw}")
if before_tab != after_tab:
    failures.append(f"active_tab changed: {before_tab} -> {after_tab}")

# Sanity on the actual answer text.
clean_chars = int(webgpt_meta.get("clean_chars") or 0)
if clean_chars < 30:
    failures.append(f"clean_chars={clean_chars} (expected >=30 — answer too short)")

result = {
    "status": "pass" if not failures else "fail",
    "failures": failures,
    "mode": (
        "tab-id" if tab_id_arg else
        "url" if url_arg else
        "create-tab" if create_tab else
        "auto-resolve" if auto_resolved else
        "unknown"
    ),
    "ask_exit_code": ask_status,
    "ask_state": ask_status_json.get("state"),
    "ask_run_dir": str(ask_status_file.parent) if ask_status_file else None,
    "webgpt_meta_path": str(webgpt_meta_path) if webgpt_meta_path else None,
    "oracle_enabled": result_summary.get("oracle_enabled"),
    "oracle_model": result_summary.get("oracle_model"),
    "oracle_backend": oracle_alias.get("oracle_backend"),
    "oracle_model_served": served,
    "served_tab_id": served_tab_id,
    "controlled_tab_id": controlled_tab_id,
    "requested_tab_id": webgpt_meta.get("requested_tab_id"),
    "no_activate": webgpt_meta.get("no_activate"),
    "focus_changed_meta": webgpt_meta.get("focus_changed"),
    "raw_contains_sentinel": webgpt_meta.get("raw_contains_sentinel"),
    "clean_contains_sentinel": webgpt_meta.get("clean_contains_sentinel"),
    "clean_chars": clean_chars,
    "focused_window_before": before_fw,
    "focused_window_after": after_fw,
    "active_tab_before": before_tab,
    "active_tab_after": after_tab,
}
(output_dir / "sanity-webgpt-result.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
if result["status"] != "pass":
    raise SystemExit(1)
PY
