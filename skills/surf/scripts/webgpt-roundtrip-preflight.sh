#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_SH="${SURF_RUN_SH:-${SKILL_DIR}/run.sh}"
SURF_DISPATCH_SH="${SURF_DISPATCH_SH:-${SKILL_DIR}/run.sh}"

usage() {
  cat <<'EOF'
Usage:
  surf webgpt.roundtrip-preflight [--tab-id ID|--url URL|--create-tab] [options]

Options:
  --tab-id ID             Explicit Chrome ChatGPT tab id.
  --url URL               Resolve an already-open ChatGPT conversation URL.
  --expect-url URL        Identity assertion when --tab-id is used.
  --expect-title TEXT     Title assertion when --tab-id is used.
  --project NAME          browser-oracle project binding.
  --browser-oracle-from PATH
                           Walk-up directory for browser-oracle binding.
  --create-tab            Create a fresh inactive ChatGPT tab.
  --no-activate           Keep the controlled tab in background if possible.
  --timeout SECONDS       Round-trip timeout. Default: 60.
  --output-dir DIR        Artifact directory. Default: /tmp/surf-webgpt-roundtrip-<ts>.
  --json                  Print summary JSON only.

Runs a tiny sentinel-bearing WebGPT prompt before an expensive review bundle.
It proves the selected tab can complete the same sentinel transport path in the
requested visibility mode. It writes request, response, raw response, submitted
prompt, Surf meta, stderr, preflight JSON, focus snapshots, tab list, and a
summary JSON.
EOF
}

tab_id=""
target_url=""
expect_url=""
expect_title=""
project=""
browser_oracle_from=""
create_tab=0
no_activate=0
timeout_s=60
output_dir=""
as_json=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tab-id) tab_id="${2:-}"; shift 2 ;;
    --url) target_url="${2:-}"; shift 2 ;;
    --expect-url) expect_url="${2:-}"; shift 2 ;;
    --expect-title) expect_title="${2:-}"; shift 2 ;;
    --project) project="${2:-}"; shift 2 ;;
    --browser-oracle-from) browser_oracle_from="${2:-}"; shift 2 ;;
    --create-tab) create_tab=1; shift ;;
    --no-activate) no_activate=1; shift ;;
    --timeout) timeout_s="${2:-}"; shift 2 ;;
    --output-dir) output_dir="${2:-}"; shift 2 ;;
    --json) as_json=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if ! [[ "$timeout_s" =~ ^[0-9]+$ ]] || [[ "$timeout_s" -lt 5 ]]; then
  echo "--timeout must be an integer >= 5" >&2
  exit 2
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
rand="$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')"
output_dir="${output_dir:-/tmp/surf-webgpt-roundtrip-${timestamp}-${rand}}"
mkdir -p "$output_dir"

request="$output_dir/01_roundtrip_request.md"
response="$output_dir/02_roundtrip_response.md"
raw="$output_dir/02_roundtrip_response.raw.md"
meta="$output_dir/02_roundtrip_response.meta.json"
submitted="$output_dir/02_roundtrip_response.submitted.md"
stderr_log="$output_dir/webgpt-submit.stderr.log"
preflight_json="$output_dir/preflight.json"
focus_before="$output_dir/focus_before.json"
focus_after="$output_dir/focus_after.json"
tab_list="$output_dir/tab_list.json"
summary="$output_dir/roundtrip-preflight.json"

sentinel="<<<WEBGPT_PREFLIGHT_DONE:${timestamp}:${rand}>>>"
cat > "$request" <<EOF
Reply with exactly this line and nothing else:

pong ${sentinel}
EOF

"$SURF_DISPATCH_SH" focus.state --json > "$focus_before" 2>/dev/null || true
"$SURF_DISPATCH_SH" tab.list --json --with-kde > "$tab_list" 2>/dev/null || "$SURF_DISPATCH_SH" tab.list --json > "$tab_list" 2>/dev/null || true

preflight_cmd=("$SURF_DISPATCH_SH" webgpt.preflight --json)
if [[ -n "$tab_id" ]]; then
  preflight_cmd+=(--tab-id "$tab_id")
fi
if [[ -n "$target_url" ]]; then
  preflight_cmd+=(--url "$target_url")
fi
if [[ -n "$expect_url" ]]; then
  preflight_cmd+=(--expect-url "$expect_url")
fi
if [[ -n "$expect_title" ]]; then
  preflight_cmd+=(--expect-title "$expect_title")
fi
if [[ "$no_activate" -eq 1 ]]; then
  preflight_cmd+=(--no-activate)
fi
if [[ "$create_tab" -eq 1 ]]; then
  preflight_cmd+=(--create-tab)
fi

preflight_status=0
"${preflight_cmd[@]}" > "$preflight_json" 2> "$output_dir/preflight.stderr.log" || preflight_status=$?

submit_dispatch="$SURF_DISPATCH_SH"
if [[ -n "${SURF_RUN_SH:-}" ]]; then
  submit_dispatch="$SKILL_DIR/run.sh"
fi

submit_cmd=("$submit_dispatch" webgpt.submit
  --input "$request"
  --output "$response"
  --raw-output "$raw"
  --meta-output "$meta"
  --submitted-output "$submitted"
  --sentinel "$sentinel"
  --stable-polls 1
  --timeout "$timeout_s"
  --advisory-after "$timeout_s"
)
if [[ -n "$tab_id" ]]; then
  submit_cmd+=(--tab-id "$tab_id")
fi
if [[ -n "$target_url" ]]; then
  submit_cmd+=(--url "$target_url")
fi
if [[ -n "$expect_url" ]]; then
  submit_cmd+=(--expect-url "$expect_url")
fi
if [[ -n "$expect_title" ]]; then
  submit_cmd+=(--expect-title "$expect_title")
fi
if [[ -n "$project" ]]; then
  submit_cmd+=(--project "$project")
fi
if [[ -n "$browser_oracle_from" ]]; then
  submit_cmd+=(--browser-oracle-from "$browser_oracle_from")
fi
if [[ "$create_tab" -eq 1 ]]; then
  submit_cmd+=(--create-tab)
fi
if [[ "$no_activate" -eq 1 ]]; then
  submit_cmd+=(--no-activate)
fi

submit_status=0
submit_pid=""
submit_started_with_setsid=0
rate_limit_wait_s="${SURF_WEBGPT_ROUNDTRIP_RATE_LIMIT_WAIT_SECONDS:-${SURF_WEBGPT_RATE_LIMIT_WAIT_SECONDS:-300}}"
cleanup_submit_child() {
  if [[ -n "${submit_pid:-}" ]] && kill -0 "$submit_pid" 2>/dev/null; then
    if [[ "$submit_started_with_setsid" -eq 1 ]]; then
      kill -TERM -- "-$submit_pid" 2>/dev/null || true
      sleep 0.2
      kill -KILL -- "-$submit_pid" 2>/dev/null || true
    else
      pkill -TERM -P "$submit_pid" 2>/dev/null || true
      kill -TERM "$submit_pid" 2>/dev/null || true
      sleep 0.2
      pkill -KILL -P "$submit_pid" 2>/dev/null || true
      kill -KILL "$submit_pid" 2>/dev/null || true
    fi
  fi
}
handle_termination() {
  cleanup_submit_child
  exit 143
}
trap handle_termination TERM INT HUP
trap cleanup_submit_child EXIT
if command -v setsid >/dev/null 2>&1; then
  env \
    SURF_WEBGPT_EXTRACT_FALLBACK_BUDGET="${SURF_WEBGPT_ROUNDTRIP_EXTRACT_FALLBACK_BUDGET:-1}" \
    SURF_WEBGPT_RATE_LIMIT_WAIT_SECONDS="$rate_limit_wait_s" \
    setsid "${submit_cmd[@]}" > "$output_dir/webgpt-submit.stdout.log" 2> "$stderr_log" &
  submit_started_with_setsid=1
else
  env \
    SURF_WEBGPT_EXTRACT_FALLBACK_BUDGET="${SURF_WEBGPT_ROUNDTRIP_EXTRACT_FALLBACK_BUDGET:-1}" \
    SURF_WEBGPT_RATE_LIMIT_WAIT_SECONDS="$rate_limit_wait_s" \
    "${submit_cmd[@]}" > "$output_dir/webgpt-submit.stdout.log" 2> "$stderr_log" &
fi
submit_pid=$!
wait "$submit_pid" || submit_status=$?
submit_pid=""
trap - TERM INT HUP
trap - EXIT
"$SURF_DISPATCH_SH" focus.state --json > "$focus_after" 2>/dev/null || true

python3 "${SCRIPT_DIR}/lib/webgpt_transport.py" write-summary \
  --artifact-dir "$output_dir" \
  --meta "$meta" \
  --raw "$raw" \
  --submitted "$submitted" >/dev/null 2>&1 || true

python3 - "$summary" "$output_dir" "$sentinel" "$timeout_s" "$preflight_status" "$submit_status" "$preflight_json" "$meta" "$raw" "$response" "$stderr_log" "$focus_before" "$focus_after" "$tab_list" "$request" "$submitted" "$as_json" <<'PY'
import json
import pathlib
import sys

(
    summary_path,
    output_dir,
    sentinel,
    timeout_s,
    preflight_status,
    submit_status,
    preflight_path,
    meta_path,
    raw_path,
    response_path,
    stderr_path,
    focus_before_path,
    focus_after_path,
    tab_list_path,
    request_path,
    submitted_path,
    as_json,
) = sys.argv[1:]

def read_json(path):
    p = pathlib.Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"parse_error": str(exc), "text_tail": p.read_text(encoding="utf-8", errors="replace")[-1000:]}

def read_text(path):
    p = pathlib.Path(path)
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""

meta = read_json(meta_path) or {}
preflight = read_json(preflight_path) or {}
raw_text = read_text(raw_path)
clean_text = read_text(response_path)
stderr_text = read_text(stderr_path)
focus_before = read_json(focus_before_path)
focus_after = read_json(focus_after_path)
tab_list_text = read_text(tab_list_path)

failures = []
if int(preflight_status) != 0 or preflight.get("status") != "pass":
    failures.append("tab_identity_preflight_failed")
if int(submit_status) != 0:
    failures.append("roundtrip_submit_failed")
if meta.get("status") not in {"completed", "recovered_focus_changed"}:
    failures.append(f"meta_status_{meta.get('status') or 'missing'}")
if sentinel not in raw_text:
    failures.append("missing_sentinel")
if meta.get("controlled_tab_id_mismatch"):
    failures.append("controlled_tab_id_mismatch")

timeout_error = str(meta.get("timeout_error") or "")
hidden_stall = (
    "document_hidden=true" in timeout_error
    or meta.get("document_hidden_at_completion") is True and "missing_sentinel" in failures
    or int(meta.get("background_hidden_polls") or 0) > 0 and "missing_sentinel" in failures
)
if hidden_stall:
    failures.append("hidden_tab_stall")

warnings = []
if meta.get("no_activate") is True and meta.get("focus_invariant_ok") is not True:
    if (
        sentinel in raw_text
        and meta.get("controlled_tab_id")
        and meta.get("status") == "recovered_focus_changed"
    ):
        warnings.append("focus_drift_completed")
    else:
        failures.append("focus_changed_despite_no_activate")
if meta.get("reasoning_selection_status") == "selector_unavailable":
    warnings.append("reasoning_selector_unavailable")

if failures:
    status = "fail"
elif warnings:
    status = "degraded"
else:
    status = "pass"
payload = {
    "schema": "surf.webgpt_roundtrip_preflight.v1",
    "status": status,
    "failures": failures,
    "warnings": warnings,
    "transport_degraded": bool(warnings),
    "output_dir": output_dir,
    "sentinel": sentinel,
    "timeout_seconds": int(timeout_s),
    "preflight_exit_code": int(preflight_status),
    "submit_exit_code": int(submit_status),
    "preflight": preflight,
    "meta": meta,
    "debug": {
        "request": request_path,
        "submitted": submitted_path,
        "response": response_path,
        "raw_response": raw_path,
        "meta": meta_path,
        "stderr": stderr_path,
        "preflight": preflight_path,
        "focus_before": focus_before_path,
        "focus_after": focus_after_path,
        "tab_list": tab_list_path,
        "raw_chars": len(raw_text),
        "clean_chars": len(clean_text),
        "stderr_tail": stderr_text[-2000:],
        "tab_list_tail": tab_list_text[-4000:],
        "focus_before_payload": focus_before,
        "focus_after_payload": focus_after,
    },
    "diagnosis": {
        "hidden_tab_stall": hidden_stall,
        "document_hidden_at_completion": meta.get("document_hidden_at_completion"),
        "visibility_state_at_completion": meta.get("visibility_state_at_completion"),
        "background_hidden_polls": meta.get("background_hidden_polls"),
        "background_poll_count": meta.get("background_poll_count"),
        "raw_contains_sentinel": sentinel in raw_text,
        "clean_contains_sentinel": sentinel in clean_text,
        "focus_changed": meta.get("focus_changed"),
        "controlled_tab_id": meta.get("controlled_tab_id"),
        "requested_tab_id": meta.get("requested_tab_id"),
        "requested_url": meta.get("requested_url"),
    },
}
pathlib.Path(summary_path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps(payload, indent=2, sort_keys=True) if as_json == "1" else f"webgpt.roundtrip-preflight: {status} -> {summary_path}")
raise SystemExit(0 if status in {"pass", "degraded"} else 6)
PY
