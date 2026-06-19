#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SURF_DISPATCH_SH="${SURF_DISPATCH_SH:-${SKILL_DIR}/run.sh}"

usage() {
  cat <<'EOF'
Usage:
  surf webgpt.e2e-sanity [options]

Options:
  --tab-id ID             Also test this explicit ChatGPT tab.
  --url URL               Also test this already-open ChatGPT conversation URL.
  --expect-url URL        Identity assertion for --tab-id.
  --expect-title TEXT     Identity assertion for --tab-id.
  --no-activate           Run round trips in background mode. Default: on.
  --foreground            Disable --no-activate for diagnostic foreground runs.
  --timeout SECONDS       Per-roundtrip timeout. Default: 120.
  --output-dir DIR        Artifact directory. Default: /tmp/surf-webgpt-e2e-<utc>.
  --json                  Print JSON only.
  -h, --help

Runs a fail-closed WebGPT transport sanity matrix for brittle paths that have
burned project agents: stale native host, wrong tab, prompt not delivered,
missing sentinel, project shell without conversation URL, focus drift, and
reasoning selector drift.
EOF
}

tab_id=""
target_url=""
expect_url=""
expect_title=""
no_activate=1
timeout_s=120
output_dir=""
json_only=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tab-id) tab_id="${2:-}"; shift 2 ;;
    --url) target_url="${2:-}"; shift 2 ;;
    --expect-url) expect_url="${2:-}"; shift 2 ;;
    --expect-title) expect_title="${2:-}"; shift 2 ;;
    --no-activate) no_activate=1; shift ;;
    --foreground) no_activate=0; shift ;;
    --timeout) timeout_s="${2:-}"; shift 2 ;;
    --output-dir) output_dir="${2:-}"; shift 2 ;;
    --json) json_only=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if ! [[ "$timeout_s" =~ ^[0-9]+$ ]] || [[ "$timeout_s" -lt 10 ]]; then
  echo "--timeout must be an integer >= 10" >&2
  exit 2
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
output_dir="${output_dir:-/tmp/surf-webgpt-e2e-${timestamp}}"
mkdir -p "$output_dir"/scenarios

fresh_json="$output_dir/extension-fresh.json"
tab_list_json="$output_dir/tab-list.json"
focus_json="$output_dir/focus-state.json"
summary_json="$output_dir/e2e-sanity-result.json"

fresh_status=0
"$SURF_DISPATCH_SH" extension.fresh --json >"$fresh_json" 2>"$output_dir/extension-fresh.stderr.log" || fresh_status=$?
tab_list_status=0
"$SURF_DISPATCH_SH" tab.list --json >"$tab_list_json" 2>"$output_dir/tab-list.stderr.log" || tab_list_status=$?
focus_status=0
"$SURF_DISPATCH_SH" focus.state --json >"$focus_json" 2>"$output_dir/focus-state.stderr.log" || focus_status=$?
fresh_state="$(python3 - "$fresh_json" <<'PY'
import json, pathlib, sys
try:
    print(json.loads(pathlib.Path(sys.argv[1]).read_text()).get("status") or "")
except Exception:
    print("")
PY
)"

if [[ "$fresh_status" -ne 0 || "$fresh_state" != "fresh" || "$tab_list_status" -ne 0 || "$focus_status" -ne 0 ]]; then
  python3 - "$summary_json" "$output_dir" "$fresh_json" "$fresh_status" "$tab_list_json" "$tab_list_status" "$focus_json" "$focus_status" "$json_only" <<'PY'
import json
import pathlib
import sys

summary_path, output_dir, fresh_path, fresh_status, tab_list_path, tab_list_status, focus_path, focus_status, json_only_s = sys.argv[1:]

def read_json(path):
    p = pathlib.Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"parse_error": str(exc), "tail": p.read_text(encoding="utf-8", errors="replace")[-2000:]}

fresh = read_json(fresh_path) or {}
tabs = read_json(tab_list_path)
focus = read_json(focus_path)
checks = [
    {
        "name": "extension_native_fresh",
        "ok": int(fresh_status) == 0 and fresh.get("status") == "fresh",
        "detail": fresh.get("status") or f"exit={fresh_status}",
        "artifact": fresh_path,
        "agent_action": "Run surf extension.reload from the installed Surf checkout, then extension.ping and extension.fresh before any WebGPT submit.",
    },
    {
        "name": "tab_list_available",
        "ok": int(tab_list_status) == 0 and isinstance(tabs, list),
        "detail": f"tabs={len(tabs) if isinstance(tabs, list) else 'unavailable'}",
        "artifact": tab_list_path,
        "agent_action": "Repair Surf extension/socket before trusting tab ids.",
    },
    {
        "name": "focus_state_available",
        "ok": int(focus_status) == 0 and isinstance(focus, dict) and bool(focus.get("activeTabId")),
        "detail": f"active_tab={focus.get('activeTabId') if isinstance(focus, dict) else None}",
        "artifact": focus_path,
        "agent_action": "Do not claim no-activate/focus invariants without focus.state.",
    },
]
first_failure = next((c["name"] for c in checks if not c["ok"]), None)
result = {
    "schema": "surf.webgpt_e2e_sanity.v1",
    "status": "fail",
    "failure_code": first_failure,
    "output_dir": output_dir,
    "checks": checks,
    "scenarios": [],
    "agent_action": "Stop before submitting any WebGPT prompt. Repair the failed precondition first.",
}
pathlib.Path(summary_path).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps(result, indent=2, sort_keys=True) if json_only_s == "1" else f"webgpt.e2e-sanity: fail\noutput_dir: {output_dir}\nfailure_code: {first_failure}")
raise SystemExit(7)
PY
fi

run_roundtrip() {
  local name="$1"
  shift
  local dir="$output_dir/scenarios/$name"
  mkdir -p "$dir"
  local args=(webgpt.roundtrip-preflight --timeout "$timeout_s" --output-dir "$dir" --json)
  if [[ "$no_activate" -eq 1 ]]; then
    args+=(--no-activate)
  fi
  args+=("$@")
  local status=0
  "$SURF_DISPATCH_SH" "${args[@]}" >"$dir/roundtrip.stdout.json" 2>"$dir/roundtrip.stderr.log" || status=$?
  printf '%s\n' "$status" >"$dir/exit-code.txt"
}

run_roundtrip "fresh-create-tab" --create-tab

if [[ -n "$tab_id" || -n "$target_url" ]]; then
  target_args=()
  if [[ -n "$tab_id" ]]; then
    target_args+=(--tab-id "$tab_id")
  fi
  if [[ -n "$target_url" ]]; then
    target_args+=(--url "$target_url")
  fi
  if [[ -n "$expect_url" ]]; then
    target_args+=(--expect-url "$expect_url")
  fi
  if [[ -n "$expect_title" ]]; then
    target_args+=(--expect-title "$expect_title")
  fi
  run_roundtrip "explicit-target" "${target_args[@]}"
fi

python3 - "$summary_json" "$output_dir" "$fresh_json" "$fresh_status" "$tab_list_json" "$tab_list_status" "$focus_json" "$focus_status" "$json_only" <<'PY'
import json
import pathlib
import sys

(
    summary_path,
    output_dir,
    fresh_path,
    fresh_status,
    tab_list_path,
    tab_list_status,
    focus_path,
    focus_status,
    json_only_s,
) = sys.argv[1:]

root = pathlib.Path(output_dir)

def read_json(path):
    p = pathlib.Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"parse_error": str(exc), "tail": p.read_text(encoding="utf-8", errors="replace")[-2000:]}

def read_text(path):
    p = pathlib.Path(path)
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""

checks = []
failures = []

def add_check(name, ok, detail="", artifact=None, action=None):
    item = {
        "name": name,
        "ok": bool(ok),
        "detail": detail,
    }
    if artifact:
        item["artifact"] = artifact
    if action:
        item["agent_action"] = action
    checks.append(item)
    if not ok:
        failures.append(name)

fresh = read_json(fresh_path) or {}
add_check(
    "extension_native_fresh",
    int(fresh_status) == 0 and fresh.get("status") == "fresh",
    fresh.get("status") or f"exit={fresh_status}",
    fresh_path,
    "Run surf extension.reload, then extension.ping and extension.fresh before any WebGPT submit.",
)

tabs = read_json(tab_list_path)
add_check(
    "tab_list_available",
    int(tab_list_status) == 0 and isinstance(tabs, list),
    f"tabs={len(tabs) if isinstance(tabs, list) else 'unavailable'}",
    tab_list_path,
    "Repair Surf extension/socket before trusting tab ids.",
)

focus = read_json(focus_path)
add_check(
    "focus_state_available",
    int(focus_status) == 0 and isinstance(focus, dict) and bool(focus.get("activeTabId")),
    f"active_tab={focus.get('activeTabId') if isinstance(focus, dict) else None}",
    focus_path,
    "Do not claim no-activate/focus invariants without focus.state.",
)

scenario_results = []
for scenario_dir in sorted((root / "scenarios").glob("*")):
    stdout_json = scenario_dir / "roundtrip.stdout.json"
    stderr_log = scenario_dir / "roundtrip.stderr.log"
    exit_code_path = scenario_dir / "exit-code.txt"
    exit_code = int(read_text(exit_code_path).strip() or "999") if exit_code_path.exists() else 999
    payload = read_json(stdout_json) or {}
    if not payload and (scenario_dir / "roundtrip-preflight.json").exists():
        payload = read_json(scenario_dir / "roundtrip-preflight.json") or {}
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    diagnosis = payload.get("diagnosis") if isinstance(payload.get("diagnosis"), dict) else {}
    name = scenario_dir.name
    scenario_failures = []
    if exit_code != 0 or payload.get("status") != "pass":
        scenario_failures.append("roundtrip_failed")
    if meta.get("proof_status") != "response_proven":
        scenario_failures.append("response_not_proven")
    if meta.get("submitted_to_chatgpt") is not True:
        scenario_failures.append("not_submitted_to_chatgpt")
    if meta.get("raw_contains_sentinel") is not True:
        scenario_failures.append("missing_sentinel")
    if not meta.get("controlled_tab_id"):
        scenario_failures.append("missing_controlled_tab_id")
    if meta.get("controlled_tab_id_mismatch"):
        scenario_failures.append("controlled_tab_id_mismatch")
    if meta.get("no_activate") is True and meta.get("focus_invariant_ok") is not True:
        scenario_failures.append("focus_changed_despite_no_activate")
    conversation_url = str(meta.get("conversation_url") or "")
    requested_url = str(meta.get("requested_url") or "")
    preflight = meta.get("tab_identity_preflight") if isinstance(meta.get("tab_identity_preflight"), dict) else {}
    preflight_tab = preflight.get("tab") if isinstance(preflight.get("tab"), dict) else {}
    target_url = requested_url or str(preflight.get("expected_url") or "") or str(preflight_tab.get("url") or "")
    if "chatgpt.com/g/" in target_url and "/project" in target_url and "/c/" not in conversation_url:
        scenario_failures.append("project_session_unproven")
    if meta.get("requested_reasoning") and not (
        meta.get("selected_reasoning") or meta.get("reasoning_selection_status")
    ):
        scenario_failures.append("reasoning_status_missing")
    if meta.get("reasoning_selection_status") == "selector_unavailable":
        # This is not a transport failure, but it must be visible because Pro was not selected.
        scenario_failures.append("warning_reasoning_selector_unavailable")
    result = {
        "name": name,
        "status": "pass" if not [f for f in scenario_failures if not f.startswith("warning_")] else "fail",
        "warnings": [f for f in scenario_failures if f.startswith("warning_")],
        "failures": [f for f in scenario_failures if not f.startswith("warning_")],
        "exit_code": exit_code,
        "artifact_dir": str(scenario_dir),
        "controlled_tab_id": meta.get("controlled_tab_id"),
        "conversation_url": conversation_url or None,
        "requested_reasoning": meta.get("requested_reasoning"),
        "reasoning_selection_status": meta.get("reasoning_selection_status"),
        "roundtrip_failures": payload.get("failures"),
        "diagnosis": diagnosis,
        "stderr_tail": read_text(stderr_log)[-2000:],
    }
    scenario_results.append(result)
    add_check(
        f"scenario_{name}",
        result["status"] == "pass",
        ",".join(result["failures"] + result["warnings"]) or "pass",
        str(scenario_dir),
        "Do not submit large WebGPT work until this scenario passes without hard failures.",
    )

hard_failures = [f for f in failures if not f.startswith("warning_")]
status = "pass" if not hard_failures else "fail"
first_failure = hard_failures[0] if hard_failures else None
result = {
    "schema": "surf.webgpt_e2e_sanity.v1",
    "status": status,
    "failure_code": first_failure,
    "output_dir": output_dir,
    "checks": checks,
    "scenarios": scenario_results,
    "agent_action": (
        "Transport sanity passed for the configured scenarios; use scenario artifacts as pre-submit proof."
        if status == "pass"
        else "Stop WebGPT project-agent work. Inspect the first failed check and scenario artifact_dir before retrying."
    ),
}
pathlib.Path(summary_path).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
if json_only_s == "1":
    print(json.dumps(result, indent=2, sort_keys=True))
else:
    print(f"webgpt.e2e-sanity: {status}")
    print(f"output_dir: {output_dir}")
    if first_failure:
        print(f"failure_code: {first_failure}")
    for check in checks:
        marker = "OK" if check["ok"] else "FAIL"
        print(f"{marker}\t{check['name']}\t{check['detail']}")
raise SystemExit(0 if status == "pass" else 7)
PY
