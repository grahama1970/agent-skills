#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_SH="${SURF_RUN_SH:-${SKILL_DIR}/run.sh}"

# shellcheck source=lib/webgpt_resolve.sh
source "${SCRIPT_DIR}/lib/webgpt_resolve.sh"
# shellcheck source=lib/browser_oracle_resolve.sh
source "${SCRIPT_DIR}/lib/browser_oracle_resolve.sh"

usage() {
  cat <<'EOF'
Usage:
  surf webgpt.submit --input REQUEST.md --output RESPONSE.md [options]

Options:
  --input PATH              Prompt file to submit. Required.
  --output PATH             Clean response path. Required.
  --raw-output PATH         Raw response path. Default: <output>.raw.md
  --meta-output PATH        Proof metadata JSON. Default: <output>.meta.json
  --receipt-output PATH     Submit receipt JSON. Default: <output>.receipt.json
  --submitted-output PATH   Submitted prompt with sentinel injection.
  --sentinel auto|MARKER    Completion marker. Default: auto.
  --stable-polls N          Unchanged polls after sentinel before returning. Default: 3.
  --timeout SECONDS         Browser wait timeout. Default: 2400 (40 minutes).
  --advisory-after SECONDS  Soft wait before returning same-tab available text
                            without a sentinel. Default:
                            SURF_WEBGPT_ADVISORY_AFTER_SECONDS or 600.
                            Set 0 to disable.
  --roundtrip-preflight     Before submitting the main prompt, send a tiny
                            sentinel ping through the same controlled tab.
  --roundtrip-timeout SECONDS
                            Timeout for --roundtrip-preflight. Default:
                            SURF_WEBGPT_ROUNDTRIP_PREFLIGHT_TIMEOUT or 60.
  --roundtrip-output-dir DIR
                            Artifact directory for the round-trip preflight.
  --notification-assisted-wait
                            Experimental advisory mode: allow ChatGPT/browser
                            response notifications to wake human attention, but
                            never treat notifications as completion proof.
                            Completion still requires controlled-tab sentinel
                            or image-artifact proof.
  --model MODEL             Optional ChatGPT model selector label.
  --reasoning LABEL         ChatGPT reasoning dropdown label. Default:
                            SURF_WEBGPT_REASONING or "Pro".
  --project NAME            browser-oracle project binding (~/.pi/webgpt-projects/<name>.json).
  --browser-oracle-from PATH  Walk-up directory for .ask/browser-oracles.yaml (default: cwd).
  --tab-id ID               Use this exact Chrome tab as the controlled WebGPT tab.
  --url URL                 Resolve an already-open ChatGPT tab by exact URL.
  --expect-url URL          When using --tab-id, require that tab to match this
                            ChatGPT URL/conversation before submitting.
  --expect-title TEXT       When using --tab-id, require the current tab title
                            to contain this text before submitting.
  --allow-unverified-tab-id Allow a bare --tab-id even when multiple ChatGPT
                            tabs are open. Use only for privileged/manual
                            recovery where URL/title identity is unavailable.
  --create-tab              Open a fresh ChatGPT tab (inactive) and control that tab.
                            Skips persisted controlled-tab state file lookup.
  --no-remember             Do not read or write the global controlled-tab state file.
  --no-activate             Background controlled-tab mode. Do not foreground
                            the tab or its window. Requires --tab-id, --url, or
                            --create-tab so an authenticated ChatGPT tab exists.
  --allow-foreground-controlled
                            With --no-activate, allow the controlled tab to be
                            the foreground active tab (not recommended).
  --attach-file PATH        Attach a file to the ChatGPT message (uses CDP
                            DOM.setFileInputFiles via the surf chatgpt --file
                            flag). The prompt body is sent normally; ChatGPT
                            reads the attached file alongside it. Use this
                            instead of inlining large bundles in the prompt
                            to stay under the OS argv limit.
  --warn-only               Downgrade preflight path warnings from block to warn.
  --require-attachment PATTERN
                            After response, verify a downloadable file button
                            matching PATTERN exists in the DOM. Fail if missing.
  --auto-download PATTERN   After response, automatically download files whose
                            button text matches PATTERN. Uses webgpt.download
                            internally. Can be specified multiple times.
  --verify-cmd CMD          After download, extract zip and run this verify
                            command (e.g. "npm run typecheck"). If CMD is
                            "auto" or omitted, auto-detect from repo.
  --repo PATH               Repository root for --verify. Default: current dir.
EOF
}

input=""
output=""
raw_output=""
meta_output=""
receipt_output=""
submitted_output=""
sentinel="auto"
stable_polls=3
timeout_s="${SURF_WEBGPT_TIMEOUT:-2400}"
advisory_after_s="${SURF_WEBGPT_ADVISORY_AFTER_SECONDS:-0}"
model=""
reasoning="${SURF_WEBGPT_REASONING:-Pro}"
tab_id=""
project=""
browser_oracle_from=""
target_url=""
expect_url=""
expect_title=""
allow_unverified_tab_id=0
no_activate=0
create_tab=0
no_remember=0
allow_foreground_controlled=0
attach_file=""
roundtrip_preflight=0
roundtrip_timeout_s="${SURF_WEBGPT_ROUNDTRIP_PREFLIGHT_TIMEOUT:-60}"
roundtrip_output_dir=""
notification_assisted_wait="${SURF_WEBGPT_NOTIFICATION_ASSISTED_WAIT:-0}"
tab_state_file="${SURF_WEBGPT_TAB_STATE:-/tmp/surf-webgpt-controlled-tab-id}"
host_log_file="${SURF_WEBGPT_HOST_LOG:-/tmp/surf-host.log}"
warn_only=1
require_attachment=""
auto_download_patterns=()
verify_cmd=""
repo_root=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --input) input="${2:-}"; shift 2 ;;
    --output) output="${2:-}"; shift 2 ;;
    --raw-output) raw_output="${2:-}"; shift 2 ;;
    --meta-output) meta_output="${2:-}"; shift 2 ;;
    --receipt-output) receipt_output="${2:-}"; shift 2 ;;
    --submitted-output) submitted_output="${2:-}"; shift 2 ;;
    --sentinel) sentinel="${2:-}"; shift 2 ;;
    --stable-polls) stable_polls="${2:-}"; shift 2 ;;
    --timeout) timeout_s="${2:-}"; shift 2 ;;
    --advisory-after) advisory_after_s="${2:-}"; shift 2 ;;
    --roundtrip-preflight) roundtrip_preflight=1; shift ;;
    --roundtrip-timeout) roundtrip_timeout_s="${2:-}"; shift 2 ;;
    --roundtrip-output-dir) roundtrip_output_dir="${2:-}"; shift 2 ;;
    --notification-assisted-wait) notification_assisted_wait=1; shift ;;
    --model) model="${2:-}"; shift 2 ;;
    --reasoning) reasoning="${2:-}"; shift 2 ;;
    --project) project="${2:-}"; shift 2 ;;
    --browser-oracle-from) browser_oracle_from="${2:-}"; shift 2 ;;
    --tab-id) tab_id="${2:-}"; shift 2 ;;
    --url) target_url="${2:-}"; shift 2 ;;
    --expect-url) expect_url="${2:-}"; shift 2 ;;
    --expect-title) expect_title="${2:-}"; shift 2 ;;
    --allow-unverified-tab-id) allow_unverified_tab_id=1; shift ;;
    --no-activate) no_activate=1; shift ;;
    --create-tab) create_tab=1; shift ;;
    --no-remember) no_remember=1; shift ;;
    --allow-foreground-controlled) allow_foreground_controlled=1; no_activate=1; shift ;;
    --attach-file) attach_file="${2:-}"; shift 2 ;;
    --warn-only) warn_only=1; shift ;;
    --require-attachment) require_attachment="${2:-}"; shift 2 ;;
    --auto-download) auto_download_patterns+=("${2:-}"); shift 2 ;;
    --verify-cmd) verify_cmd="${2:-}"; shift 2 ;;
    --repo) repo_root="${2:-}"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

# Explicit targets must not read/write global controlled-tab state.
if [[ -n "$tab_id" || -n "$target_url" ]]; then
  no_remember=1
fi

if [[ -z "$input" || -z "$output" ]]; then
  usage >&2
  exit 2
fi
if ! [[ "$roundtrip_timeout_s" =~ ^[0-9]+$ ]] || [[ "$roundtrip_timeout_s" -lt 5 ]]; then
  echo "--roundtrip-timeout must be an integer >= 5" >&2
  exit 2
fi
if [[ ! -f "$input" ]]; then
  echo "Input file not found: $input" >&2
  exit 2
fi
if [[ -z "${SURF_RUN_SH:-}" && ! -S /tmp/surf.sock ]]; then
  echo "surf webgpt.submit requires the surf browser extension socket at /tmp/surf.sock." >&2
  echo "Run: surf setup" >&2
  exit 3
fi

# browser-oracle walk-up when no explicit tab/url/create-tab target.
if [[ -z "$tab_id" && -z "$target_url" && "$create_tab" -eq 0 ]]; then
  bo_from="$(cd "${browser_oracle_from:-.}" 2>/dev/null && pwd || pwd)"
  bo_payload="$(browser_oracle_resolve_json "$bo_from" webgpt "$project" "" 2>/dev/null || true)"
  if [[ -n "$bo_payload" ]]; then
    bo_resolved_project="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("project") or "")' <<<"$bo_payload")"
    bo_resolved_tab="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("tab_id") or "")' <<<"$bo_payload")"
    bo_resolved_url="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("conversation_url") or "")' <<<"$bo_payload")"
    bo_reconcile_status=""
    bo_reconcile_payload=""
    if [[ -n "$bo_resolved_project" ]]; then
      # A resolved project binding is authoritative. Never fall through to the
      # process-global remembered tab when its binding cannot be validated.
      no_remember=1
    fi
    if [[ -n "$bo_resolved_project" && -n "$bo_resolved_tab" ]]; then
      if ! bo_reconcile_payload="$(browser_oracle_reconcile_json webgpt "$bo_resolved_project" "${SURF_BROWSER_ORACLE_PRUNE_MISSING:-0}")"; then
        echo "webgpt.submit blocked: browser-oracle reconciliation failed for project ${bo_resolved_project}." >&2
        [[ -n "$bo_reconcile_payload" ]] && echo "$bo_reconcile_payload" >&2
        exit 3
      fi
      bo_reconcile_status="$(python3 -c 'import json,sys; d=json.load(sys.stdin); rows=d.get("rows") or []; print((rows[0].get("status") if rows else ""))' <<<"$bo_reconcile_payload" 2>/dev/null || true)"
      if [[ "$bo_reconcile_status" == "missing_live_tab" && -n "$bo_resolved_url" && ( "${SURF_BROWSER_ORACLE_CREATE_MISSING:-0}" == "1" || "${SURF_BROWSER_ORACLE_CREATE_MISSING:-0}" == "true" ) ]]; then
        bo_open_payload="$(browser_oracle_open_bind_json "$bo_resolved_project" webgpt "$bo_resolved_url" 2>/dev/null || true)"
        bo_new_tab="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("tab_id") or "")' <<<"$bo_open_payload" 2>/dev/null || true)"
        if [[ -n "$bo_new_tab" ]]; then
          bo_payload="$bo_open_payload"
          bo_resolved_tab="$bo_new_tab"
          bo_reconcile_status="ready"
        fi
      fi
      if [[ "$bo_reconcile_status" != "ready" ]]; then
        echo "webgpt.submit blocked: browser-oracle binding for project ${bo_resolved_project} is ${bo_reconcile_status:-invalid}." >&2
        [[ -n "$bo_reconcile_payload" ]] && echo "$bo_reconcile_payload" >&2
        exit 3
      fi
    elif [[ -n "$bo_resolved_project" ]]; then
      echo "webgpt.submit blocked: browser-oracle binding for project ${bo_resolved_project} has no tab id." >&2
      exit 3
    fi
    if [[ -z "$project" ]]; then
      project="$bo_resolved_project"
    fi
    if [[ -z "$tab_id" && ( -z "$bo_resolved_tab" || "$bo_reconcile_status" == "ready" ) ]]; then
      tab_id="$bo_resolved_tab"
    fi
    if [[ -z "$target_url" && ( -z "$bo_resolved_tab" || "$bo_reconcile_status" == "ready" ) ]]; then
      bo_url="$bo_resolved_url"
      if [[ -n "$bo_url" ]]; then
        target_url="$bo_url"
      fi
    fi
    if [[ -z "$expect_url" && -n "$target_url" ]]; then
      expect_url="$target_url"
    fi
  fi
fi

# Close duplicate tabs with the same conversation URL.
# The tab-id is canonical; other tabs sharing the same URL are stale duplicates
# that cause identity preflight failures.
if [[ -n "${requested_tab_id:-}" && -n "${target_url:-}" ]]; then
  tab_list_json="$("$RUN_SH" tab.list --json 2>/dev/null || true)"
  if [[ -n "$tab_list_json" ]]; then
    echo "$tab_list_json" | python3 -c "
import json, sys
tabs = json.load(sys.stdin)
target = '${target_url}'
keep = '${requested_tab_id}'
for t in tabs:
    tid = str(t.get('id',''))
    if tid != keep and t.get('url','') == target:
        print(tid)
" 2>/dev/null | while read dup_id; do
      [[ -n "$dup_id" ]] && "$RUN_SH" tab.close "$dup_id" >/dev/null 2>&1 || true
    done
  fi
fi

if [[ "$sentinel" == "auto" || -z "$sentinel" ]]; then
  rand="$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')"
  sentinel="<<<WEBGPT_DONE:$(date -u +%Y%m%dT%H%M%SZ):${rand}>>>"
fi

raw_output="${raw_output:-${output}.raw.md}"
meta_output="${meta_output:-${output}.meta.json}"
receipt_output="${receipt_output:-${output}.receipt.json}"
submitted_output="${submitted_output:-${output}.submitted.md}"
mkdir -p "$(dirname "$output")" "$(dirname "$raw_output")" "$(dirname "$meta_output")" "$(dirname "$receipt_output")" "$(dirname "$submitted_output")"



write_transport_summary() {
  [[ -f "$meta_output" ]] || return 0
  python3 "${SCRIPT_DIR}/lib/webgpt_transport.py" write-summary     --artifact-dir "$(dirname "$meta_output")"     --meta "$meta_output"     --receipt "$receipt_output"     --raw "$raw_output"     --submitted "$submitted_output"     >/dev/null 2>&1 || true
}

enrich_agent_diagnosis() {
  [[ -f "$meta_output" ]] || return 0
  python3 - "$meta_output" "$receipt_output" <<'PY'
import json
import pathlib
import sys

meta_path = pathlib.Path(sys.argv[1])
receipt_path = pathlib.Path(sys.argv[2])
try:
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)

receipt = {}
if receipt_path.exists():
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except Exception:
        receipt = {}

status = meta.get("status")
failure = meta.get("failure")
raw_has = bool(meta.get("raw_contains_sentinel"))
clean_has = bool(meta.get("clean_contains_sentinel"))
submitted = bool(receipt.get("submitted_to_chatgpt"))
conversation_url = str(meta.get("conversation_url") or "")
requested_url = str(meta.get("requested_url") or "")
identity = meta.get("tab_identity_preflight") if isinstance(meta.get("tab_identity_preflight"), dict) else {}
expected_url = str(identity.get("expected_url") or "")
identity_tab = identity.get("tab") if isinstance(identity.get("tab"), dict) else {}
identity_tab_url = str(identity_tab.get("url") or "")
target_identity_url = requested_url or expected_url or identity_tab_url
project_shell_target = "/project" in target_identity_url and "chatgpt.com/" in target_identity_url
conversation_url_proven = "chatgpt.com/" in conversation_url and "/c/" in conversation_url

if status in {"completed", "recovered_focus_changed"} and project_shell_target and not conversation_url_proven:
    status = "failed"
    failure = "project_conversation_url_unproven"
    meta["status"] = status
    meta["failure"] = failure

if failure in {"focus_stolen_mid_submit", "focus_stolen_despite_no_activate"}:
    proof_status = "degraded_focus"
    diagnosis = "The controlled tab returned sentinel output, but browser focus changed during no-activate mode."
    action = "Preserve as degraded transport evidence only; rerun in a dedicated reviewer window for clean background proof."
elif status in {"completed", "recovered_focus_changed"} and raw_has and not clean_has:
    proof_status = "response_proven"
    diagnosis = "ChatGPT returned the current sentinel-bearing assistant response from the controlled tab."
    action = "Use raw_output, output, and meta_output as Surf transport evidence; reconcile reviewer content against deterministic local proof."
elif failure == "project_conversation_url_unproven":
    proof_status = "project_session_unproven"
    diagnosis = "Surf saw sentinel output, but the target was a ChatGPT project shell and no distinct conversation URL was proven."
    action = "Do not treat this as an independent project chat. Create or bind a real project conversation URL containing /c/<id>, then rerun with --url or --expect-url for that conversation."
elif failure == "attach_file_preflight_failed":
    proof_status = "not_submitted"
    diagnosis = "Attachment preflight failed before Surf submitted anything to ChatGPT."
    action = "Fix the attachment bundle size, file count, or path, then rerun webgpt.submit."
elif failure == "create_tab_navigation_failed":
    proof_status = "not_submitted"
    diagnosis = "Surf created or selected a tab but could not navigate it to ChatGPT before submission."
    action = "Inspect stderr_log and tab state, then create or bind a known-good ChatGPT reviewer tab."
elif failure == "tab_identity_preflight_failed":
    proof_status = "not_submitted"
    diagnosis = "The requested tab did not match the required ChatGPT identity before submission."
    action = "Run tab.list and webgpt.preflight with --url, --expect-url, or --expect-title; do not submit until the target tab identity matches."
elif failure == "roundtrip_preflight_failed":
    proof_status = "not_submitted"
    diagnosis = "The small sentinel roundtrip failed, so Surf blocked the main prompt before submission."
    action = "Inspect roundtrip_preflight_output_dir, repair tab visibility/state, or use a foreground/fresh reviewer tab before retrying."
elif failure == "stale_cdp_on_explicit_tab":
    proof_status = "not_submitted"
    diagnosis = "Surf could not attach CDP to the explicitly requested tab in no-activate mode."
    action = "Release the existing debugger attachment or reload Surf, then retry the same explicit tab."
elif failure == "concurrent_submit_same_tab":
    proof_status = "not_submitted"
    diagnosis = "Another Surf WebGPT submit is already controlling the requested tab."
    action = "Wait for the active run to finish or use a separate explicitly verified tab."
elif failure == "submit_failed":
    ready_error = str(meta.get("chatgpt_ready_error") or "")
    if ready_error:
        proof_status = "not_submitted"
        diagnosis = f"ChatGPT rejected pre-submit readiness: {ready_error}"
        action = "Clear the ChatGPT composer/stopped generation state, or use a fresh foreground reviewer/project conversation tab before retrying."
    else:
        proof_status = "submitted_no_response_proof" if submitted else "delivery_not_proven"
        diagnosis = "Surf invoked ChatGPT but did not produce a current sentinel-bearing assistant response."
        action = "Check stderr_log, receipt, and raw_output. If receipt.status is prepared_prompt, treat as not delivered; if submitted_to_chatgpt, recover with webgpt.extract using this sentinel or rerun deliberately."
elif failure == "missing_sentinel" or status == "missing_sentinel":
    proof_status = "submitted_no_response_proof" if submitted else "delivery_not_proven"
    diagnosis = "Surf captured response text, but it did not contain the current completion sentinel in assistant output."
    action = "Do not use output as proof. If ChatGPT visibly completed, run webgpt.extract with the exact sentinel; otherwise resubmit to a clean verified tab."
elif failure == "response_clean_failed":
    proof_status = "submitted_no_response_proof" if submitted else "delivery_not_proven"
    diagnosis = "Surf captured a sentinel-bearing response, but terminal-sentinel validation rejected trailing assistant text."
    action = "Do not use the clean output; inspect raw_output and recover the exact response deliberately."
elif failure == "controlled_tab_id_mismatch":
    proof_status = "wrong_tab"
    diagnosis = "The response came from a different tab than the requested controlled tab."
    action = "Discard this result, rerun preflight with --url or --expect-url, and submit only after the controlled tab id matches."
else:
    proof_status = "unknown_failure" if status not in {"completed", "recovered_focus_changed"} else "response_unproven"
    diagnosis = "Surf did not map this result to a known agent-facing diagnosis."
    action = "Inspect status, failure, stderr_log, receipt_output, raw_output, and meta_output before retrying."

meta["proof_status"] = proof_status
meta["agent_diagnosis"] = diagnosis
meta["agent_action"] = action
meta["submitted_to_chatgpt"] = submitted
meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
PY
  python3 "${SCRIPT_DIR}/emit_surf_doctor_incident.py" \
    --meta "$meta_output" \
    --receipt "$receipt_output" \
    --submitted "$submitted_output" \
    --raw "$raw_output" \
    --clean "$output" \
    --heartbeat "${heartbeat_output:-${meta_output%.json}.heartbeat.json}" \
    >/dev/null 2>&1 || true
  write_transport_summary
}

attach_file_abs=""
if [[ -n "$attach_file" ]]; then
  if [[ ! -f "$attach_file" ]]; then
    echo "--attach-file: file not found: $attach_file" >&2
    exit 2
  fi
  attach_file_abs="$(readlink -f "$attach_file")"
  attach_ext="${attach_file_abs##*.}"
  attach_ext="${attach_ext,,}"
  if [[ "$attach_ext" == "zip" ]]; then
    max_zip_files="${SURF_WEBGPT_MAX_ZIP_FILES:-5}"
    set +e
    zip_preflight_json="$(python3 - "$attach_file_abs" "$max_zip_files" <<'PY'
import json
import pathlib
import sys
import zipfile

path = pathlib.Path(sys.argv[1])
max_files = int(sys.argv[2])
try:
    with zipfile.ZipFile(path) as zf:
        files = [info.filename for info in zf.infolist() if not info.is_dir()]
except Exception as exc:
    print(json.dumps({"ok": False, "file_count": 0, "max_files": max_files, "error": f"could not read zip archive: {exc}"}))
    raise SystemExit(1)
if not files:
    print(json.dumps({"ok": False, "file_count": 0, "max_files": max_files, "error": "zip archive is empty"}))
    raise SystemExit(1)
if len(files) > max_files:
    print(json.dumps({
        "ok": False,
        "file_count": len(files),
        "max_files": max_files,
        "error": f"zip contains {len(files)} files; maximum is {max_files}",
        "files": files,
    }))
    raise SystemExit(1)
print(json.dumps({"ok": True, "file_count": len(files), "max_files": max_files, "files": files}))
PY
)"
    zip_preflight_status=$?
    set -e
    if [[ "$zip_preflight_status" -ne 0 ]]; then
      failed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
      python3 - "$meta_output" "$input" "$submitted_output" "$output" "$raw_output" "$sentinel" "$attach_file_abs" "$zip_preflight_json" "$failed_at" <<'PY'
import json
import pathlib
import sys

meta, inp, submitted, out, raw, sentinel, attach_file, zip_s, failed_at = sys.argv[1:]
try:
    zip_info = json.loads(zip_s) if zip_s else {"ok": False, "error": "zip preflight did not return JSON"}
except Exception:
    zip_info = {"ok": False, "error": "zip preflight JSON parse failed"}
pathlib.Path(meta).write_text(json.dumps({
    "status": "failed",
    "failure": "attach_file_preflight_failed",
    "input": inp,
    "submitted_output": submitted,
    "output": out,
    "raw_output": raw,
    "sentinel": sentinel,
    "attach_file": attach_file,
    "attach_file_preflight": zip_info,
    "started_at": failed_at,
    "finished_at": failed_at,
}, indent=2) + "\n")
PY
      enrich_agent_diagnosis
      python3 -c 'import json,sys; print(json.loads(sys.argv[1]).get("error") or "zip attachment preflight failed")' "$zip_preflight_json" >&2
      exit 2
    fi
  fi
fi

prompt="$(cat "$input")"
_pf_args="--input "$input" --json"
if [[ "$warn_only" -eq 1 ]]; then
  _pf_args="--input "$input" --json --warn-only"
fi
prompt_path_preflight_json="$(python3 "${SCRIPT_DIR}/lib/webgpt_prompt_preflight.py" $_pf_args 2>&1)" || true
_pf_status="$(printf '%s' "$prompt_path_preflight_json" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("status","fail"))' 2>/dev/null || echo "fail")"
if [[ "$_pf_status" == "fail" ]]; then
  failed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  python3 - "$meta_output" "$input" "$submitted_output" "$output" "$raw_output" "/dev/null" "$sentinel" "$prompt_path_preflight_json" "$failed_at" <<'PY'
import json, pathlib, sys
meta, inp, submitted, out, raw, err, sentinel, preflight_s, failed_at = sys.argv[1:]
try:
    preflight = json.loads(preflight_s)
except Exception:
    preflight = {"status": "fail", "reason": "prompt_path_preflight_failed", "detail": preflight_s[-500:]}
pathlib.Path(meta).write_text(json.dumps({
    "status": "failed",
    "failure": "prompt_path_preflight_failed",
    "input": inp,
    "submitted_output": submitted,
    "output": out,
    "raw_output": raw,
    "stderr_log": err,
    "sentinel": sentinel,
    "prompt_path_preflight": preflight,
    "started_at": failed_at,
    "finished_at": failed_at,
    "agent_diagnosis": "Prompt references local filesystem paths the browser tab cannot read.",
    "agent_action": preflight.get("agent_action") or "Provide concatenated text or a small zip bundle.",
}, indent=2) + "\n")
PY
  enrich_agent_diagnosis
  write_transport_summary
  echo "webgpt.submit blocked: prompt references unreadable local filesystem paths." >&2
  printf '%s\n' "$prompt_path_preflight_json" >&2
  exit 7
elif [[ "$_pf_status" == "warn" ]]; then
  echo "webgpt.submit warning: prompt contains local filesystem path references." >&2
  printf '%s\n' "$prompt_path_preflight_json" >&2
  echo "  (Proceeding because --warn-only was set)" >&2
fi

write_webgpt_heartbeat() {
  local phase="$1"
  local page_state="$2"
  local last_artifact="${3:-}"
  local next_expected="${4:-}"
  local timeout_remaining="${5:--1}"
  python3 "${SCRIPT_DIR}/lib/webgpt_heartbeat.py" write \
    --artifact-dir "$(dirname "$meta_output")" \
    --phase "$phase" \
    --page-state "$page_state" \
    --submitted-at "${started_at:-}" \
    --last-artifact "$last_artifact" \
    --next-expected-artifact "$next_expected" \
    --timeout-remaining "$timeout_remaining" \
    --sentinel "$sentinel" >/dev/null 2>&1 || true
}

submitted_prompt="${prompt}

---

Completion contract for browser automation:

At the very end of your final answer, print exactly:

${sentinel}

Do not print anything after that marker."

printf '%s\n' "$submitted_prompt" > "$submitted_output"

write_submit_receipt() {
  local status="$1"
  local receipt_at="$2"
  local accepted="${3:-false}"
  python3 - "$receipt_output" "$status" "$receipt_at" "$accepted" "$input" "$submitted_output" "$output" "$raw_output" "$meta_output" "$sentinel" "${requested_tab_id:-}" "$target_url" "$model" "$reasoning" <<'PY'
import json
import pathlib
import sys

(
    receipt, status, receipt_at, accepted_s, inp, submitted, out, raw, meta,
    sentinel, requested_tab_id, target_url, model, reasoning,
) = sys.argv[1:]
pathlib.Path(receipt).write_text(json.dumps({
    "schema": "surf.webgpt_submit_receipt.v1",
    "status": status,
    "submitted_to_chatgpt": accepted_s == "true",
    "prepared_prompt_is_transport_proof": False,
    "input": inp,
    "submitted_output": submitted,
    "output": out,
    "raw_output": raw,
    "meta_output": meta,
    "sentinel": sentinel,
    "requested_tab_id": requested_tab_id or None,
    "requested_url": target_url or None,
    "requested_model": model or None,
    "requested_reasoning": reasoning or None,
    "receipt_at": receipt_at,
}, indent=2) + "\n", encoding="utf-8")
PY
}

write_submit_receipt "prepared_prompt" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "false"
write_webgpt_heartbeat "prompt_prepared" "waiting" "$submitted_output" "$raw_output" "$timeout_s"

stderr_log="$(mktemp /tmp/surf-webgpt-submit-stderr.XXXXXX.log)"
raw_tmp="$(mktemp /tmp/surf-webgpt-submit-raw.XXXXXX.md)"

attempt_extract_fallback() {
  local reason="${1:-unknown}"
  if [[ -z "${requested_tab_id:-}" ]]; then
    return 1
  fi
  if [[ -s "$raw_output" ]] && grep -Fq "$sentinel" "$raw_output"; then
    return 1
  fi
  if [[ "$no_activate" -eq 1 && "$reason" == "missing_sentinel" ]]; then
    "$RUN_SH" tab.activate "$requested_tab_id" >/dev/null 2>&1 || true
    sleep 2
    echo "ExtractActivateForRecovery: true" >> "$stderr_log"
  fi
  local extract_clean extract_raw extract_meta extract_err
  extract_clean="$(mktemp /tmp/surf-webgpt-submit-extract-clean.XXXXXX.md)"
  extract_raw="$(mktemp /tmp/surf-webgpt-submit-extract-raw.XXXXXX.md)"
  extract_meta="$(mktemp /tmp/surf-webgpt-submit-extract-meta.XXXXXX.json)"
  extract_err="$(mktemp /tmp/surf-webgpt-submit-extract-stderr.XXXXXX.log)"
  local per_attempt_timeout="${SURF_WEBGPT_EXTRACT_FALLBACK_TIMEOUT:-30}"
  local retry_interval="${SURF_WEBGPT_EXTRACT_FALLBACK_INTERVAL:-15}"
  local retry_budget="${SURF_WEBGPT_EXTRACT_FALLBACK_BUDGET:-180}"
  local started_at="$SECONDS"
  local attempt=0
  while (( SECONDS - started_at < retry_budget )); do
    attempt=$((attempt + 1))
    local extract_args=(--tab-id "$requested_tab_id" --output "$extract_clean" --raw-output "$extract_raw" --meta-output "$extract_meta" --timeout "$per_attempt_timeout")
    if [[ -n "$sentinel" ]]; then
      extract_args+=(--sentinel "$sentinel")
    fi
    if "${SCRIPT_DIR}/webgpt-extract.sh" "${extract_args[@]}" > /dev/null 2>"$extract_err"; then
      if [[ -s "$extract_raw" ]] && grep -Fq "$sentinel" "$extract_raw"; then
        cp "$extract_raw" "$raw_output"
        cp "$extract_clean" "$output"
        {
          echo "ExtractFallback: true"
          echo "ExtractFallbackReason: $reason"
          echo "ExtractFallbackAttempts: $attempt"
          echo "ExtractFallbackRaw: $extract_raw"
          echo "ExtractFallbackMeta: $extract_meta"
          echo "Tab ID: $requested_tab_id"
          echo "ResponseSource: webgpt-extract-fallback"
        } >> "$stderr_log"
        return 0
      fi
    fi
    sleep "$retry_interval"
  done
  {
    echo "ExtractFallback: false"
    echo "ExtractFallbackReason: $reason"
    echo "ExtractFallbackAttempts: $attempt"
    echo "ExtractFallbackErrorLog: $extract_err"
  } >> "$stderr_log"
  return 1
}
# Dedicated reviewer tab (inactive). Avoids reusing global state or auto-picking
# the newest chatgpt.com tab (often the user's foreground conversation).
if [[ "$create_tab" -eq 1 ]]; then
  no_remember=1
  # Chrome may foreground a newly created tab even when the caller requested a
  # no-activate WebGPT round. The created tab is still identity-safe because it
  # is the tab this command just opened and verified; do not block solely on
  # the foreground guard for this acquisition path.
  allow_foreground_controlled=1
  created_tab_verified=0
  if [[ -n "$project" ]]; then
    bo_open_payload="$(browser_oracle_open_bind_json "$project" webgpt "https://chatgpt.com/" 2>/dev/null || true)"
    requested_tab_id="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("tab_id") or "")' <<<"$bo_open_payload" 2>/dev/null || true)"
    if [[ -n "$requested_tab_id" ]]; then
      tab_id="$requested_tab_id"
      create_tab=0
      created_tab_verified=1
    else
      echo "webgpt.submit --create-tab failed: could not provision reviewer window for project ${project}" >&2
      [[ -n "$bo_open_payload" ]] && echo "$bo_open_payload" >&2
      exit 2
    fi
  fi
  if [[ "$create_tab" -eq 1 ]]; then
  create_out="$("$RUN_SH" tab.new "https://chatgpt.com/" 2>&1)" || {
    echo "webgpt.submit --create-tab failed: could not open ChatGPT tab" >&2
    echo "$create_out" >&2
    exit 2
  }
  requested_tab_id="$(printf '%s' "$create_out" | sed -n 's/^Created tab \([0-9][0-9]*\):.*/\1/p' | head -n 1)"
  if [[ -z "$requested_tab_id" ]]; then
    echo "webgpt.submit --create-tab failed: could not parse tab id from:" >&2
    echo "$create_out" >&2
    exit 2
  fi
  tab_id="$requested_tab_id"
  # The extension can return the created tab id before tab.list reflects the
  # new ChatGPT tab. Wait briefly so the fail-closed identity gate checks the
  # current browser state instead of a stale snapshot.
  created_tab_verified=0
  fi
  if [[ "$created_tab_verified" -ne 1 ]]; then
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    tab_list_text="$("$RUN_SH" tab.list 2>/dev/null || true)"
    if printf '%s\n' "$tab_list_text" | awk -F '\t' -v tid="$requested_tab_id" '$1 == tid && $3 ~ /chatgpt[.]com/ { found = 1 } END { exit found ? 0 : 1 }'; then
      created_tab_verified=1
      break
    fi
    sleep 0.5
  done
  fi
  if [[ "$created_tab_verified" -ne 1 ]]; then
    failed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    "$RUN_SH" tab.close "$requested_tab_id" >/dev/null 2>&1 || true
    python3 - "$meta_output" "$input" "$submitted_output" "$output" "$raw_output" "$stderr_log" "$sentinel" "$requested_tab_id" "$failed_at" <<'PY'
import json, pathlib, sys
meta, inp, submitted, out, raw, err, sentinel, requested_tab_id, failed_at = sys.argv[1:]
pathlib.Path(meta).write_text(json.dumps({
    "status": "failed",
    "failure": "create_tab_navigation_failed",
    "input": inp,
    "submitted_output": submitted,
    "output": out,
    "raw_output": raw,
    "stderr_log": err,
    "sentinel": sentinel,
    "requested_tab_id": requested_tab_id,
    "requested_tab_source": "create-tab",
    "started_at": failed_at,
    "finished_at": failed_at,
}, indent=2) + "\n")
PY
    enrich_agent_diagnosis
    echo "webgpt.submit --create-tab failed: created tab $requested_tab_id did not navigate to chatgpt.com; closed it." >&2
    exit 2
  fi
fi

effective_timeout_s="$timeout_s"
if [[ "$advisory_after_s" =~ ^[0-9]+$ && "$advisory_after_s" -gt 0 && "$advisory_after_s" -lt "$timeout_s" ]]; then
  effective_timeout_s="$advisory_after_s"
fi

heartbeat_output="$(dirname "$meta_output")/webgpt_heartbeat.json"
args=(chatgpt --query-file "$submitted_output" --sentinel "$sentinel" --stable-polls "$stable_polls" --timeout "$effective_timeout_s" --keep-tab --heartbeat-file "$heartbeat_output")
if [[ -n "$model" ]]; then
  args+=(--model "$model")
fi
if [[ -n "$reasoning" ]]; then
  args+=(--reasoning "$reasoning")
fi
if [[ -n "$tab_id" ]]; then
  requested_tab_id="$(printf '%s' "$tab_id" | tr -cd '0-9' | head -c 20 || true)"
  if [[ -z "$requested_tab_id" ]]; then
    echo "Invalid --tab-id: $tab_id" >&2
    exit 2
  fi
  args+=(--tab-id "$requested_tab_id" --target-tab-id "$requested_tab_id")
  if [[ "$create_tab" -eq 1 ]]; then
    requested_tab_source="create-tab"
  else
    requested_tab_source="tab-id"
  fi
elif [[ -n "$target_url" ]]; then
  tab_list_text="$("$RUN_SH" tab.list 2>/dev/null || true)"
  if ! webgpt_resolve_url_from_list "$target_url" "$tab_list_text"; then
    if [[ "${resolve_error:-}" == "ambiguous_url" ]]; then
      echo "Multiple open Chrome tabs match --url: $target_url" >&2
      python3 -c "import json,sys; print(json.dumps(json.loads(sys.argv[1]).get('candidates', []), indent=2))" "$resolve_json" >&2
    else
      echo "No open Chrome tab matched --url: $target_url" >&2
      echo "Use --tab-id for the exact tab or open the URL before retrying." >&2
    fi
    exit 2
  fi
  requested_tab_id="$resolved_tab_id"
  args+=(--tab-id "$requested_tab_id" --target-tab-id "$requested_tab_id")
  requested_tab_source="url"
elif [[ "$no_remember" -eq 0 && "$create_tab" -eq 0 && -f "$tab_state_file" ]]; then
  remembered_tab_id="$(tr -cd '0-9' < "$tab_state_file" | head -c 20 || true)"
  if [[ -n "$remembered_tab_id" ]]; then
    args+=(--tab-id "$remembered_tab_id")
    requested_tab_id="$remembered_tab_id"
    requested_tab_source="remembered"
  fi
fi

# Refresh the prepared receipt after target resolution. The first receipt is
# written before tab/url discovery so callers can see prompt preparation early;
# this second write records the actual intended controlled tab when available.
write_submit_receipt "prepared_prompt" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "false"

if [[ -n "${requested_tab_id:-}" ]]; then
  surf_tab_lock_path="/tmp/surf-webgpt-tab-${requested_tab_id}.lock"
  exec {surf_tab_lock_fd}>"$surf_tab_lock_path"
  if ! flock -n "$surf_tab_lock_fd"; then
    failed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    python3 - "$meta_output" "$input" "$submitted_output" "$output" "$raw_output" "$stderr_log" "$sentinel" "$requested_tab_id" "$target_url" "$model" "$reasoning" "$failed_at" "$surf_tab_lock_path" <<'PY'
import json, pathlib, sys
(
    meta, inp, submitted, out, raw, err, sentinel, requested_tab_id,
    target_url, model, reasoning, failed_at, lock_path,
) = sys.argv[1:]
pathlib.Path(meta).write_text(json.dumps({
    "status": "failed",
    "failure": "concurrent_submit_same_tab",
    "input": inp,
    "submitted_output": submitted,
    "output": out,
    "raw_output": raw,
    "stderr_log": err,
    "sentinel": sentinel,
    "requested_tab_id": requested_tab_id,
    "requested_url": target_url or None,
    "requested_model": model or None,
    "requested_reasoning": reasoning or None,
    "lock_path": lock_path,
    "submitted_to_chatgpt": False,
    "started_at": failed_at,
    "finished_at": failed_at,
}, indent=2) + "\n", encoding="utf-8")
PY
    enrich_agent_diagnosis
    echo "webgpt.submit blocked: another Surf submit is already controlling tab $requested_tab_id; no prompt submitted." >&2
    exit 9
  fi
  cleanup_surf_tab_lock() {
    rm -f -- "$surf_tab_lock_path"
  }
  trap cleanup_surf_tab_lock EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
fi

if [[ -n "${requested_tab_id:-}" ]]; then
  tab_list_text="${tab_list_text:-$("$RUN_SH" tab.list 2>/dev/null || true)}"
  identity_args=(check --tab-id "$requested_tab_id" --source "${requested_tab_source:-tab-id}")
  if [[ -n "$target_url" && "${requested_tab_source:-}" == "url" ]]; then
    identity_args+=(--expect-url "$target_url")
  elif [[ -n "$expect_url" ]]; then
    identity_args+=(--expect-url "$expect_url")
  fi
  if [[ -n "$expect_title" ]]; then
    identity_args+=(--expect-title "$expect_title")
  fi
  if [[ "$allow_unverified_tab_id" -eq 1 ]]; then
    identity_args+=(--allow-unverified-tab-id)
  fi
  set +e
  identity_preflight_json="$(
    printf '%s\n' "$tab_list_text" \
      | python3 "${SCRIPT_DIR}/lib/webgpt_tab_identity.py" "${identity_args[@]}"
  )"
  identity_status=$?
  set -e
  if [[ "$identity_status" -ne 0 ]]; then
    failed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    python3 - "$meta_output" "$input" "$submitted_output" "$output" "$raw_output" "$stderr_log" "$sentinel" "${requested_tab_id:-}" "$target_url" "$model" "$reasoning" "$identity_preflight_json" "$failed_at" <<'PY'
import json, pathlib, sys
meta, inp, submitted, out, raw, err, sentinel, requested_tab_id, target_url, model, reasoning, identity_s, failed_at = sys.argv[1:]
try:
    identity = json.loads(identity_s) if identity_s else None
except Exception:
    identity = {"ok": False, "error": "identity_meta_parse_failed"}
pathlib.Path(meta).write_text(json.dumps({
    "status": "failed",
    "failure": "tab_identity_preflight_failed",
    "input": inp,
    "submitted_output": submitted,
    "output": out,
    "raw_output": raw,
    "stderr_log": err,
    "sentinel": sentinel,
    "requested_tab_id": requested_tab_id or None,
    "requested_url": target_url or None,
    "requested_model": model or None,
    "requested_reasoning": reasoning or None,
    "tab_identity_preflight": identity,
    "started_at": failed_at,
    "finished_at": failed_at,
}, indent=2) + "\n")
PY
    enrich_agent_diagnosis
    echo "webgpt.submit tab identity preflight failed for tab $requested_tab_id." >&2
    python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('error') or 'tab_identity_failed')" "$identity_preflight_json" >&2
    echo "Use --url <conversation-url>, --expect-url, --expect-title, --create-tab, or --allow-unverified-tab-id." >&2
    exit 2
  fi
else
  identity_preflight_json=""
fi

roundtrip_preflight_json=""
roundtrip_preflight_status=0
roundtrip_preflight_dir=""
if [[ "$roundtrip_preflight" -eq 1 ]]; then
  roundtrip_preflight_dir="${roundtrip_output_dir:-$(dirname "$meta_output")/roundtrip-preflight}"
  roundtrip_args=(--timeout "$roundtrip_timeout_s" --output-dir "$roundtrip_preflight_dir")
  if [[ -n "${requested_tab_id:-}" ]]; then
    roundtrip_args+=(--tab-id "$requested_tab_id")
  fi
  if [[ -n "$target_url" ]]; then
    roundtrip_args+=(--url "$target_url")
  fi
  if [[ -n "$expect_url" ]]; then
    roundtrip_args+=(--expect-url "$expect_url")
  elif [[ -n "$target_url" && "${requested_tab_source:-}" == "url" ]]; then
    roundtrip_args+=(--expect-url "$target_url")
  fi
  if [[ -n "$expect_title" ]]; then
    roundtrip_args+=(--expect-title "$expect_title")
  fi
  if [[ -n "$project" ]]; then
    roundtrip_args+=(--project "$project")
  fi
  if [[ -n "$browser_oracle_from" ]]; then
    roundtrip_args+=(--browser-oracle-from "$browser_oracle_from")
  fi
  if [[ "$create_tab" -eq 1 && -z "${requested_tab_id:-}" ]]; then
    roundtrip_args+=(--create-tab)
  fi
  if [[ "$no_activate" -eq 1 ]]; then
    roundtrip_args+=(--no-activate)
  fi
  set +e
  roundtrip_preflight_json="$("${SCRIPT_DIR}/webgpt-roundtrip-preflight.sh" "${roundtrip_args[@]}" --json 2>"$roundtrip_preflight_dir.stderr.log")"
  roundtrip_preflight_status=$?
  set -e
  if [[ "$roundtrip_preflight_status" -ne 0 ]]; then
    failed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    python3 - "$meta_output" "$input" "$submitted_output" "$output" "$raw_output" "$stderr_log" "$sentinel" "${requested_tab_id:-}" "$target_url" "$model" "$reasoning" "${identity_preflight_json:-}" "$roundtrip_preflight_json" "$roundtrip_preflight_status" "$roundtrip_preflight_dir" "$failed_at" <<'PY'
import json, pathlib, sys
(
    meta, inp, submitted, out, raw, err, sentinel, requested_tab_id, target_url,
    model, reasoning, identity_s, roundtrip_s, roundtrip_status,
    roundtrip_dir, failed_at
) = sys.argv[1:]
try:
    identity = json.loads(identity_s) if identity_s else None
except Exception:
    identity = {"ok": False, "error": "identity_meta_parse_failed"}
try:
    roundtrip = json.loads(roundtrip_s) if roundtrip_s else {"status": "missing", "failures": ["no_roundtrip_json"]}
except Exception:
    roundtrip = {
        "status": "invalid_json",
        "failures": ["roundtrip_json_parse_failed"],
        "stdout_tail": (roundtrip_s or "")[-2000:],
    }
pathlib.Path(meta).write_text(json.dumps({
    "status": "failed",
    "failure": "roundtrip_preflight_failed",
    "input": inp,
    "submitted_output": submitted,
    "output": out,
    "raw_output": raw,
    "stderr_log": err,
    "sentinel": sentinel,
    "requested_tab_id": requested_tab_id or None,
    "requested_url": target_url or None,
    "requested_model": model or None,
    "requested_reasoning": reasoning or None,
    "tab_identity_preflight": identity,
    "roundtrip_preflight_required": True,
    "roundtrip_preflight_exit_code": int(roundtrip_status),
    "roundtrip_preflight_output_dir": roundtrip_dir,
    "roundtrip_preflight": roundtrip,
    "started_at": failed_at,
    "finished_at": failed_at,
}, indent=2) + "\n")
PY
    enrich_agent_diagnosis
    echo "webgpt.submit roundtrip preflight failed before main prompt." >&2
    python3 -c 'import json,sys; d=json.loads(sys.argv[1]); print(json.dumps({"status": d.get("status"), "failures": d.get("failures"), "diagnosis": d.get("diagnosis"), "output_dir": d.get("output_dir")}, indent=2))' "$roundtrip_preflight_json" >&2 || true
    exit 6
  fi
fi

# Pre-run focus snapshot (also used for --no-activate foreground guard).
focus_before_json="$("$RUN_SH" focus.state --json 2>/dev/null || true)"

# CDP stale connection recovery. Explicit tab identity is immutable: reload
# Surf once and retry the same tab, then fail closed before submission.
if [[ -n "${requested_tab_id:-}" ]]; then
  no_activate=1
  cdp_probe_err="$(mktemp /tmp/surf-webgpt-cdp-probe.XXXXXX.log)"
  cdp_ok="$("$RUN_SH" js "return 'cdp-ok'" --no-activate --tab-id "$requested_tab_id" 2>"$cdp_probe_err" || true)"
  if [[ "$cdp_ok" != "cdp-ok" && "$cdp_ok" != '"cdp-ok"' ]]; then
    cdp_retry_err="$(mktemp /tmp/surf-webgpt-cdp-retry.XXXXXX.log)"
    "$RUN_SH" extension.reload >/dev/null 2>"$cdp_retry_err" || true
    for _surf_ping_attempt in $(seq 1 30); do
      if "$RUN_SH" extension.ping >/dev/null 2>>"$cdp_retry_err"; then
        break
      fi
      sleep 0.5
    done
    cdp_ok="$("$RUN_SH" js "return 'cdp-ok'" --no-activate --tab-id "$requested_tab_id" 2>>"$cdp_retry_err" || true)"
  fi
  if [[ "$cdp_ok" != "cdp-ok" && "$cdp_ok" != '"cdp-ok"' ]]; then
    failed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    python3 - "$meta_output" "$input" "$submitted_output" "$output" "$raw_output" "$stderr_log" "$sentinel" "$requested_tab_id" "$target_url" "$model" "$reasoning" "${identity_preflight_json:-}" "$cdp_probe_err" "${cdp_retry_err:-}" "$failed_at" <<'PY'
import json, pathlib, sys
(
    meta, inp, submitted, out, raw, err, sentinel, requested_tab_id,
    target_url, model, reasoning, identity_s, probe_path_s, retry_path_s,
    failed_at,
) = sys.argv[1:]
try:
    identity = json.loads(identity_s) if identity_s else None
except Exception:
    identity = {"ok": False, "error": "identity_meta_parse_failed"}
def read(path_s):
    path = pathlib.Path(path_s) if path_s else None
    return path.read_text(encoding="utf-8", errors="replace") if path and path.exists() else ""
pathlib.Path(meta).write_text(json.dumps({
    "status": "failed",
    "failure": "stale_cdp_on_explicit_tab",
    "input": inp,
    "submitted_output": submitted,
    "output": out,
    "raw_output": raw,
    "stderr_log": err,
    "sentinel": sentinel,
    "requested_tab_id": requested_tab_id,
    "requested_url": target_url or None,
    "requested_model": model or None,
    "requested_reasoning": reasoning or None,
    "tab_identity_preflight": identity,
    "cdp_probe_stderr": read(probe_path_s),
    "cdp_retry_attempted": True,
    "cdp_retry_stderr": read(retry_path_s),
    "submitted_to_chatgpt": False,
    "started_at": failed_at,
    "finished_at": failed_at,
}, indent=2) + "\n", encoding="utf-8")
PY
    enrich_agent_diagnosis
    echo "webgpt.submit blocked: stale CDP on explicit tab $requested_tab_id after same-tab extension reload retry; no prompt submitted and no fallback tab created." >&2
    exit 6
  fi
fi

if [[ "$no_activate" -eq 1 ]]; then
  if [[ -z "${requested_tab_id:-}" && "$create_tab" -eq 0 ]]; then
    # No tab-id and no create-tab flag — auto-enable --create-tab for background mode
    create_tab=1
    echo "webgpt.submit: enabling --create-tab for background mode (no valid tab-id)" >&2
  fi
  if [[ -n "${requested_tab_id:-}" ]]; then
    args+=(--no-activate)
  fi
fi

if [[ -n "$attach_file_abs" ]]; then
  args+=(--file "$attach_file_abs")
fi

started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
started_epoch="$(date -u +%s)"
focus_mid_log="$(mktemp /tmp/surf-webgpt-focus-mid.XXXXXX.log)"
focus_stolen_mid=0
set +e
run_submit() {
  if command -v timeout >/dev/null 2>&1; then
    hard_timeout_s=$((timeout_s + 60))
    timeout --kill-after=10s "${hard_timeout_s}s" "$RUN_SH" "${args[@]}"
  else
    "$RUN_SH" "${args[@]}"
  fi
}
run_submit > "$raw_tmp" 2> "$stderr_log" &
submit_pid=$!
receipt_marker="$(mktemp /tmp/surf-webgpt-submit-receipt.XXXXXX.mark)"
(
  while kill -0 "$submit_pid" 2>/dev/null; do
    if [[ -f "$host_log_file" ]] && grep -F "Prompt accepted: sentinel=$sentinel" "$host_log_file" >/dev/null 2>&1; then
      write_submit_receipt "submitted_to_chatgpt" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "true"
      write_webgpt_heartbeat "submitted" "generating" "$receipt_output" "$raw_output" "$timeout_s"
      printf 'submitted_to_chatgpt\n' > "$receipt_marker"
      exit 0
    fi
    now_epoch="$(date -u +%s)"
    elapsed_s=$((now_epoch - started_epoch))
    remaining_s=$((timeout_s - elapsed_s))
    if [[ "$remaining_s" -lt 0 ]]; then
      remaining_s=0
    fi
    write_webgpt_heartbeat "delivery_pending" "waiting_for_acceptance" "$receipt_output" "$raw_output" "$remaining_s"
    sleep 0.2
  done
  if [[ -f "$host_log_file" ]] && grep -F "Prompt accepted: sentinel=$sentinel" "$host_log_file" >/dev/null 2>&1; then
    write_submit_receipt "submitted_to_chatgpt" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "true"
    printf 'submitted_to_chatgpt\n' > "$receipt_marker"
  fi
) &
receipt_pid=$!
poll_interval="${SURF_WEBGPT_FOCUS_POLL_INTERVAL:-15}"
(
  while kill -0 "$submit_pid" 2>/dev/null; do
    sleep "$poll_interval"
    now_epoch="$(date -u +%s)"
    elapsed_s=$((now_epoch - started_epoch))
    remaining_s=$((timeout_s - elapsed_s))
    if [[ "$remaining_s" -lt 0 ]]; then
      remaining_s=0
    fi
    if [[ -s "$receipt_marker" ]]; then
      write_webgpt_heartbeat "generating" "waiting_for_sentinel" "$receipt_output" "$raw_output" "$remaining_s"
    else
      write_webgpt_heartbeat "delivery_pending" "waiting_for_acceptance" "$receipt_output" "$raw_output" "$remaining_s"
    fi
    focus_now="$("$RUN_SH" focus.state --json 2>/dev/null || echo '{}')"
    if python3 "${SCRIPT_DIR}/lib/focus_changed.py" "$focus_before_json" "$focus_now"; then
      focus_stolen_mid=1
      date -u +"%Y-%m-%dT%H:%M:%SZ focus_stolen_mid_submit" >>"$focus_mid_log"
      if [[ -n "${SURF_WEBGPT_ABORT_ON_FOCUS_STEAL:-}" ]]; then
        kill "$submit_pid" 2>/dev/null || true
        break
      fi
    fi
  done
) &
poll_pid=$!
wait "$submit_pid"
status=$?
stop_background_watcher() {
  local pid="${1:-}"
  if [[ -z "$pid" ]]; then
    return 0
  fi
  pkill -TERM -P "$pid" 2>/dev/null || true
  kill "$pid" 2>/dev/null || true
}
stop_background_watcher "$poll_pid"
stop_background_watcher "$receipt_pid"
wait "$poll_pid" 2>/dev/null || true
wait "$receipt_pid" 2>/dev/null || true
set -e
finished_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
if [[ $status -eq 0 ]]; then
  write_webgpt_heartbeat "completed" "response_detected" "$raw_output" "$meta_output" 0
else
  write_webgpt_heartbeat "failed" "stalled" "$stderr_log" "$meta_output" 0
fi

# Post-run focus snapshot for proof.
focus_after_json="$("$RUN_SH" focus.state --json 2>/dev/null || true)"

if [[ "$notification_assisted_wait" == "1" || "$notification_assisted_wait" == "true" ]]; then
  {
    echo "NotificationAssistedWaitRequested: true"
    echo "NotificationAssistedWaitCompletionProof: false"
    echo "NotificationAssistedWaitReason: advisory_wake_only_sentinel_required"
  } >> "$stderr_log"
else
  {
    echo "NotificationAssistedWaitRequested: false"
    echo "NotificationAssistedWaitCompletionProof: false"
    echo "NotificationAssistedWaitReason: disabled"
  } >> "$stderr_log"
fi

cp "$raw_tmp" "$raw_output"

if [[ $status -ne 0 ]]; then
  attempt_extract_fallback "submit_failed" || true
  if grep -Fq "$sentinel" "$raw_output"; then
    {
      echo "TransportDegraded: true"
      echo "OriginalSubmitExitCode: $status"
      echo "RecoveryTransition: response_proven_after_submit_failure"
    } >> "$stderr_log"
    status=0
  else
  python3 - "$meta_output" "$input" "$submitted_output" "$output" "$raw_output" "$stderr_log" "$sentinel" "$started_at" "$finished_at" "$status" "${requested_tab_id:-}" "$target_url" "$model" "$reasoning" "${identity_preflight_json:-}" "$roundtrip_preflight" "$roundtrip_preflight_status" "$roundtrip_preflight_dir" "$roundtrip_preflight_json" <<'PY'
import json, pathlib, sys
meta, inp, submitted, out, raw, err, sentinel, started, finished, status, requested_tab_id, target_url, model, reasoning, identity_s, roundtrip_required_s, roundtrip_status_s, roundtrip_dir, roundtrip_s = sys.argv[1:]
try:
    identity = json.loads(identity_s) if identity_s else None
except Exception:
    identity = {"ok": False, "error": "identity_meta_parse_failed"}
try:
    roundtrip = json.loads(roundtrip_s) if roundtrip_s else None
except Exception:
    roundtrip = {"status": "invalid_json", "stdout_tail": (roundtrip_s or "")[-2000:]}
raw_path = pathlib.Path(raw)
out_path = pathlib.Path(out)
err_path = pathlib.Path(err)
raw_text = raw_path.read_text() if raw_path.exists() else ""
stderr_text = err_path.read_text() if err_path.exists() else ""
if raw_text:
    idx = raw_text.rfind(sentinel)
    if idx >= 0:
        out_path.write_text(raw_text[:idx].rstrip() + "\n")
    else:
        out_path.write_text(raw_text)
out_text = out_path.read_text() if out_path.exists() else ""
response_timed_out = None
timeout_error = None
response_source = None
conversation_url = None
extract_fallback_used = False
extract_fallback_reason = None
extract_fallback_raw = None
extract_fallback_meta = None
tab_id = None
chatgpt_ready_error = None
if "ChatGPT prompt composer is not empty before submit" in stderr_text:
    chatgpt_ready_error = "composer_not_empty"
elif "ChatGPT page is in a stopped-generation state before submit" in stderr_text:
    chatgpt_ready_error = "stopped_generation_state"
elif "ChatGPT page is busy before submit" in stderr_text:
    chatgpt_ready_error = "busy_stop_button_visible"
elif "ChatGPT prompt composer not present before submit" in stderr_text:
    chatgpt_ready_error = "composer_not_present"
for line in reversed(stderr_text.splitlines()):
    if line.startswith("ResponseTimedOut:") and response_timed_out is None:
        response_timed_out = line.split(":", 1)[1].strip() == "true"
    elif line.startswith("TimeoutError:") and timeout_error is None:
        timeout_error = line.split(":", 1)[1].strip()
    elif line.startswith("ResponseSource:") and response_source is None:
        response_source = line.split(":", 1)[1].strip()
    elif line.startswith("ConversationUrl:") and conversation_url is None:
        conversation_url = line.split(":", 1)[1].strip()
    elif line.startswith("Tab ID:") and tab_id is None:
        tab_id = line.split(":", 1)[1].strip()
    elif line.startswith("ExtractFallback:") and not extract_fallback_used:
        extract_fallback_used = line.split(":", 1)[1].strip() == "true"
    elif line.startswith("ExtractFallbackReason:") and extract_fallback_reason is None:
        extract_fallback_reason = line.split(":", 1)[1].strip()
    elif line.startswith("ExtractFallbackRaw:") and extract_fallback_raw is None:
        extract_fallback_raw = line.split(":", 1)[1].strip()
    elif line.startswith("ExtractFallbackMeta:") and extract_fallback_meta is None:
        extract_fallback_meta = line.split(":", 1)[1].strip()
pathlib.Path(meta).write_text(json.dumps({
    "status": "failed",
    "failure": "submit_failed",
    "chatgpt_ready_error": chatgpt_ready_error,
    "exit_code": int(status),
    "input": inp,
    "submitted_output": submitted,
    "output": out,
    "raw_output": raw,
    "stderr_log": err,
    "sentinel": sentinel,
    "requested_tab_id": requested_tab_id or None,
    "requested_url": target_url or None,
    "requested_model": model or None,
    "requested_reasoning": reasoning or None,
    "tab_identity_preflight": identity,
    "roundtrip_preflight_required": roundtrip_required_s == "1",
    "roundtrip_preflight_exit_code": int(roundtrip_status_s or 0),
    "roundtrip_preflight_output_dir": roundtrip_dir or None,
    "roundtrip_preflight": roundtrip,
    "controlled_tab_id": tab_id,
    "conversation_url": conversation_url,
    "response_source": response_source,
    "response_timed_out": response_timed_out,
    "timeout_error": timeout_error,
    "raw_contains_sentinel": sentinel in raw_text,
    "clean_contains_sentinel": sentinel in out_text,
    "raw_chars": len(raw_text),
    "clean_chars": len(out_text),
    "raw_response_advisory": bool(raw_text),
    "extract_fallback_used": extract_fallback_used,
    "extract_fallback_reason": extract_fallback_reason,
    "extract_fallback_raw": extract_fallback_raw,
    "extract_fallback_meta": extract_fallback_meta,
    "started_at": started,
    "finished_at": finished,
}, indent=2) + "\n")
PY
  enrich_agent_diagnosis
  cat "$stderr_log" >&2
  exit "$status"
  fi
fi

if ! grep -Fq "$sentinel" "$raw_output"; then
  attempt_extract_fallback "missing_sentinel" || true
  if ! grep -Fq "$sentinel" "$raw_output"; then
    cp "$raw_output" "$output"
  python3 - "$meta_output" "$input" "$submitted_output" "$output" "$raw_output" "$stderr_log" "$sentinel" "$started_at" "$finished_at" "${requested_tab_id:-}" "$target_url" "$model" "$reasoning" "${identity_preflight_json:-}" "$roundtrip_preflight" "$roundtrip_preflight_status" "$roundtrip_preflight_dir" "$roundtrip_preflight_json" <<'PY'
import json, pathlib, sys
meta, inp, submitted, out, raw, err, sentinel, started, finished, requested_tab_id, target_url, model, reasoning, identity_s, roundtrip_required_s, roundtrip_status_s, roundtrip_dir, roundtrip_s = sys.argv[1:]
try:
    identity = json.loads(identity_s) if identity_s else None
except Exception:
    identity = {"ok": False, "error": "identity_meta_parse_failed"}
try:
    roundtrip = json.loads(roundtrip_s) if roundtrip_s else None
except Exception:
    roundtrip = {"status": "invalid_json", "stdout_tail": (roundtrip_s or "")[-2000:]}
raw_text = pathlib.Path(raw).read_text() if pathlib.Path(raw).exists() else ""
out_text = pathlib.Path(out).read_text() if pathlib.Path(out).exists() else ""
stderr_text = pathlib.Path(err).read_text() if pathlib.Path(err).exists() else ""
response_timed_out = None
timeout_error = None
response_source = None
conversation_url = None
extract_fallback_used = False
extract_fallback_reason = None
extract_fallback_raw = None
extract_fallback_meta = None
tab_id = None
for line in reversed(stderr_text.splitlines()):
    if line.startswith("ResponseTimedOut:") and response_timed_out is None:
        response_timed_out = line.split(":", 1)[1].strip() == "true"
    elif line.startswith("TimeoutError:") and timeout_error is None:
        timeout_error = line.split(":", 1)[1].strip()
    elif line.startswith("ResponseSource:") and response_source is None:
        response_source = line.split(":", 1)[1].strip()
    elif line.startswith("ConversationUrl:") and conversation_url is None:
        conversation_url = line.split(":", 1)[1].strip()
    elif line.startswith("Tab ID:") and tab_id is None:
        tab_id = line.split(":", 1)[1].strip()
    elif line.startswith("ExtractFallback:") and not extract_fallback_used:
        extract_fallback_used = line.split(":", 1)[1].strip() == "true"
    elif line.startswith("ExtractFallbackReason:") and extract_fallback_reason is None:
        extract_fallback_reason = line.split(":", 1)[1].strip()
    elif line.startswith("ExtractFallbackRaw:") and extract_fallback_raw is None:
        extract_fallback_raw = line.split(":", 1)[1].strip()
    elif line.startswith("ExtractFallbackMeta:") and extract_fallback_meta is None:
        extract_fallback_meta = line.split(":", 1)[1].strip()
pathlib.Path(meta).write_text(json.dumps({
    "status": "missing_sentinel",
    "failure": "missing_sentinel",
    "input": inp,
    "submitted_output": submitted,
    "output": out,
    "raw_output": raw,
    "stderr_log": err,
    "sentinel": sentinel,
    "requested_tab_id": requested_tab_id or None,
    "requested_url": target_url or None,
    "requested_model": model or None,
    "requested_reasoning": reasoning or None,
    "tab_identity_preflight": identity,
    "roundtrip_preflight_required": roundtrip_required_s == "1",
    "roundtrip_preflight_exit_code": int(roundtrip_status_s or 0),
    "roundtrip_preflight_output_dir": roundtrip_dir or None,
    "roundtrip_preflight": roundtrip,
    "controlled_tab_id": tab_id,
    "conversation_url": conversation_url,
    "response_source": response_source,
    "response_timed_out": response_timed_out,
    "timeout_error": timeout_error,
    "raw_contains_sentinel": sentinel in raw_text,
    "clean_contains_sentinel": sentinel in out_text,
    "raw_chars": len(raw_text),
    "clean_chars": len(out_text),
    "raw_response_advisory": bool(raw_text),
    "extract_fallback_used": extract_fallback_used,
    "extract_fallback_reason": extract_fallback_reason,
    "extract_fallback_raw": extract_fallback_raw,
    "extract_fallback_meta": extract_fallback_meta,
    "started_at": started,
    "finished_at": finished,
}, indent=2) + "\n")
PY
  enrich_agent_diagnosis
  echo "ChatGPT response did not contain sentinel: $sentinel" >&2
  exit 4
  fi
fi

if ! clean_error="$(python3 - "$raw_output" "$output" "$sentinel" 2>&1 <<'PY'
import pathlib, re, sys
raw_path, out_path, sentinel = sys.argv[1:]
text = pathlib.Path(raw_path).read_text()
idx = text.rfind(sentinel)
if idx == -1:
    raise SystemExit("sentinel missing from assistant response")
after = text[idx + len(sentinel):].strip()
if after and not re.fullmatch(r"[>_▌▋▊█|\s]*", after):
    raise SystemExit("assistant response contains text after terminal sentinel")
clean = text[:idx].rstrip() + "\n"
pathlib.Path(out_path).write_text(clean)
PY
)"; then
  python3 - "$meta_output" "$input" "$submitted_output" "$output" "$raw_output" "$stderr_log" "$sentinel" "$started_at" "$finished_at" "${requested_tab_id:-}" "$target_url" "$model" "$reasoning" "${identity_preflight_json:-}" "$clean_error" <<'PY'
import json, pathlib, sys
(
    meta, inp, submitted, out, raw, err, sentinel, started, finished,
    requested_tab_id, target_url, model, reasoning, identity_s, clean_error,
) = sys.argv[1:]
try:
    identity = json.loads(identity_s) if identity_s else None
except Exception:
    identity = {"ok": False, "error": "identity_meta_parse_failed"}
raw_text = pathlib.Path(raw).read_text() if pathlib.Path(raw).exists() else ""
stderr_text = pathlib.Path(err).read_text() if pathlib.Path(err).exists() else ""
tab_id = None
response_source = None
for line in reversed(stderr_text.splitlines()):
    if line.startswith("Tab ID:") and tab_id is None:
        tab_id = line.split(":", 1)[1].strip()
    elif line.startswith("ResponseSource:") and response_source is None:
        response_source = line.split(":", 1)[1].strip()
pathlib.Path(meta).write_text(json.dumps({
    "status": "failed",
    "failure": "response_clean_failed",
    "clean_error": clean_error,
    "input": inp,
    "submitted_output": submitted,
    "output": out,
    "raw_output": raw,
    "stderr_log": err,
    "sentinel": sentinel,
    "requested_tab_id": requested_tab_id or None,
    "requested_url": target_url or None,
    "requested_model": model or None,
    "requested_reasoning": reasoning or None,
    "tab_identity_preflight": identity,
    "controlled_tab_id": tab_id,
    "response_source": response_source,
    "raw_contains_sentinel": sentinel in raw_text,
    "clean_contains_sentinel": False,
    "raw_chars": len(raw_text),
    "clean_chars": 0,
    "submitted_to_chatgpt": False,
    "started_at": started,
    "finished_at": finished,
}, indent=2) + "\n", encoding="utf-8")
PY
  enrich_agent_diagnosis
  echo "$clean_error" >&2
  exit 5
fi

# ── --require-attachment check ──────────────────────────────
if [[ -n "$require_attachment" && -n "${requested_tab_id:-}" ]]; then
  echo "Checking for required attachment matching: $require_attachment" >&2
  _attach_js="return JSON.stringify(Array.from(document.querySelectorAll('a,button,[role=button]')).filter(e => { const t = (e.textContent || e.getAttribute('aria-label') || '').toLowerCase(); return t.includes('${require_attachment,,}'); }).length, null, 2)"
  _attach_count="$("$RUN_SH" js "$_attach_js" --tab-id "$requested_tab_id" 2>/dev/null || echo 0)"
  _attach_count="$(printf '%s' "$_attach_count" | tr -cd '0-9' | head -c 5 || echo 0)"
  if [[ "${_attach_count:-0}" -eq 0 ]]; then
    echo "ERROR: --require-attachment '$require_attachment' not found in response DOM." >&2
    echo "  ChatGPT did not attach a downloadable file matching this pattern." >&2
    exit 8
  fi
  echo "Attachment verified: found ${_attach_count} matching button(s)." >&2
fi

# ── --auto-download ──────────────────────────────────────────
_downloaded_zips=()
if [[ ${#auto_download_patterns[@]} -gt 0 && -n "${requested_tab_id:-}" ]]; then
  _dl_output_dir="$(dirname "$output")"
  for _dl_pattern in "${auto_download_patterns[@]}"; do
    echo "Auto-downloading attachment matching: $_dl_pattern" >&2
    if _dl_out="$("$RUN_SH" webgpt.download --match "$_dl_pattern" --tab-id "$requested_tab_id" --output-dir "$_dl_output_dir" --timeout 120 2>&1)"; then
      echo "Downloaded: $_dl_out" >&2
      _downloaded_zips+=("$(echo "$_dl_out" | tail -1)")
    else
      echo "No downloadable file found for '$_dl_pattern' — ChatGPT likely returned text without a real file attachment." >&2
      echo "No follow-up was submitted; caller action is required." >&2
    fi
  done
fi

# ── --verify-cmd ────────────────────────────────────────────
if [[ -n "$verify_cmd" && ${#_downloaded_zips[@]} -gt 0 ]]; then
  _repo="${repo_root:-$(pwd)}"
  for _zip_path in "${_downloaded_zips[@]}"; do
    _zip_name="$(basename "$_zip_path" .zip)"
    _extract_dir="$(mktemp -d /tmp/surf-verify-XXXXXX)"
    echo "Verifying $_zip_name against $_repo..." >&2
    unzip -q "$_zip_path" -d "$_extract_dir" 2>/dev/null || {
      echo "  Failed to extract zip." >&2
      rm -rf "$_extract_dir"
      continue
    }
    # Auto-detect verify command if not provided or set to "auto"
    _detected_cmd=""
    if [[ -z "$verify_cmd" || "$verify_cmd" == "auto" ]]; then
      if [[ -f "$_repo/package.json" ]]; then
        if grep -q '"typecheck"' "$_repo/package.json" 2>/dev/null; then
          _detected_cmd="npm run typecheck"
        elif grep -q '"tsc"' "$_repo/package.json" 2>/dev/null; then
          _detected_cmd="npx tsc --noEmit"
        elif grep -q '"lint"' "$_repo/package.json" 2>/dev/null; then
          _detected_cmd="npm run lint"
        fi
      elif [[ -f "$_repo/pyproject.toml" ]]; then
        _detected_cmd="python -m pytest"
      fi
    fi
    _cmd="${verify_cmd:-$_detected_cmd}"
    if [[ -z "$_cmd" ]]; then
      echo "  No verify command specified and could not auto-detect. Skipping verify." >&2
      rm -rf "$_extract_dir"
      continue
    fi
    echo "  Verify command: $_cmd" >&2
    echo "  Applying files from zip..." >&2
    # Copy src/ from extracted zip over repo's src/
    if [[ -d "$_extract_dir/src" ]]; then
      cp -r "$_extract_dir/src/"* "$_repo/src/" 2>/dev/null || true
    fi
    # Run verify
    set +e
    _verify_out="$(cd "$_repo" && $_cmd 2>&1)"
    _verify_exit=$?
    set -e
    if [[ $_verify_exit -eq 0 ]]; then
      echo "  VERIFY PASS (exit=$_verify_exit)" >&2
    else
      echo "  VERIFY FAIL (exit=$_verify_exit)" >&2
      echo "  Errors:" >&2
      printf '%s\n' "$_verify_out" | head -20 | sed 's/^/    /' >&2
    fi
    rm -rf "$_extract_dir"
  done
fi

python3 - "$meta_output" "$input" "$submitted_output" "$output" "$raw_output" "$stderr_log" "$sentinel" "$stable_polls" "$timeout_s" "$started_at" "$finished_at" "${requested_tab_id:-}" "$target_url" "$no_activate" "$focus_before_json" "$focus_after_json" "$focus_stolen_mid" "$focus_mid_log" "$model" "$reasoning" "${identity_preflight_json:-}" "$roundtrip_preflight" "$roundtrip_preflight_status" "$roundtrip_preflight_dir" "$roundtrip_preflight_json" <<'PY'
import json, pathlib, sys
meta, inp, submitted, out, raw, err, sentinel, stable, timeout_s, started, finished, requested_tab_id, target_url, no_activate_s, focus_before_s, focus_after_s, focus_stolen_mid_s, focus_mid_log, model, reasoning, identity_s, roundtrip_required_s, roundtrip_status_s, roundtrip_dir, roundtrip_s = sys.argv[1:]
try:
    identity = json.loads(identity_s) if identity_s else None
except Exception:
    identity = {"ok": False, "error": "identity_meta_parse_failed"}
try:
    roundtrip = json.loads(roundtrip_s) if roundtrip_s else None
except Exception:
    roundtrip = {"status": "invalid_json", "stdout_tail": (roundtrip_s or "")[-2000:]}
raw_text = pathlib.Path(raw).read_text()
out_text = pathlib.Path(out).read_text()
stderr_text = pathlib.Path(err).read_text() if pathlib.Path(err).exists() else ""
tab_id = None
activated = None
tab_was_created = None
response_source = None
conversation_url = None
page_text_contains_sentinel = None
document_hidden_at_completion = None
visibility_state_at_completion = None
background_hidden_polls = None
hidden_recovery_used = None
background_poll_count = None
notification_assisted_wait_requested = False
notification_assisted_wait_completion_proof = False
notification_assisted_wait_reason = None
requested_reasoning_observed = None
selected_reasoning = None
reasoning_selection_status = None
reasoning_selection_error = None
extract_fallback_used = False
extract_fallback_reason = None
extract_fallback_raw = None
extract_fallback_meta = None
for line in reversed(stderr_text.splitlines()):
    if line.startswith("Tab ID:") and tab_id is None:
        tab_id = line.split(":", 1)[1].strip()
    elif line.startswith("Activated:") and activated is None:
        activated = line.split(":", 1)[1].strip() == "true"
    elif line.startswith("TabWasCreated:") and tab_was_created is None:
        tab_was_created = line.split(":", 1)[1].strip() == "true"
    elif line.startswith("ResponseSource:") and response_source is None:
        response_source = line.split(":", 1)[1].strip()
    elif line.startswith("ConversationUrl:") and conversation_url is None:
        conversation_url = line.split(":", 1)[1].strip()
    elif line.startswith("PageTextContainsSentinel:") and page_text_contains_sentinel is None:
        page_text_contains_sentinel = line.split(":", 1)[1].strip() == "true"
    elif line.startswith("DocumentHiddenAtCompletion:") and document_hidden_at_completion is None:
        document_hidden_at_completion = line.split(":", 1)[1].strip() == "true"
    elif line.startswith("VisibilityStateAtCompletion:") and visibility_state_at_completion is None:
        visibility_state_at_completion = line.split(":", 1)[1].strip()
    elif line.startswith("HiddenRecoveryUsed:") and hidden_recovery_used is None:
        hidden_recovery_used = line.split(":", 1)[1].strip().lower() == "true"
    elif line.startswith("BackgroundHiddenPolls:") and background_hidden_polls is None:
        try:
            background_hidden_polls = int(line.split(":", 1)[1].strip())
        except Exception:
            background_hidden_polls = None
    elif line.startswith("BackgroundPollCount:") and background_poll_count is None:
        try:
            background_poll_count = int(line.split(":", 1)[1].strip())
        except Exception:
            background_poll_count = None
    elif line.startswith("NotificationAssistedWaitRequested:"):
        notification_assisted_wait_requested = line.split(":", 1)[1].strip() == "true"
    elif line.startswith("NotificationAssistedWaitCompletionProof:"):
        notification_assisted_wait_completion_proof = line.split(":", 1)[1].strip() == "true"
    elif line.startswith("NotificationAssistedWaitReason:") and notification_assisted_wait_reason is None:
        notification_assisted_wait_reason = line.split(":", 1)[1].strip()
    elif line.startswith("RequestedReasoning:") and requested_reasoning_observed is None:
        requested_reasoning_observed = line.split(":", 1)[1].strip()
    elif line.startswith("SelectedReasoning:") and selected_reasoning is None:
        selected_reasoning = line.split(":", 1)[1].strip()
    elif line.startswith("ReasoningSelectionStatus:") and reasoning_selection_status is None:
        reasoning_selection_status = line.split(":", 1)[1].strip()
    elif line.startswith("ReasoningSelectionError:") and reasoning_selection_error is None:
        reasoning_selection_error = line.split(":", 1)[1].strip()
    elif line.startswith("ExtractFallback:") and not extract_fallback_used:
        extract_fallback_used = line.split(":", 1)[1].strip() == "true"
    elif line.startswith("ExtractFallbackReason:") and extract_fallback_reason is None:
        extract_fallback_reason = line.split(":", 1)[1].strip()
    elif line.startswith("ExtractFallbackRaw:") and extract_fallback_raw is None:
        extract_fallback_raw = line.split(":", 1)[1].strip()
    elif line.startswith("ExtractFallbackMeta:") and extract_fallback_meta is None:
        extract_fallback_meta = line.split(":", 1)[1].strip()
    if (
        tab_id is not None
        and activated is not None
        and tab_was_created is not None
        and response_source is not None
        and document_hidden_at_completion is not None
        and visibility_state_at_completion is not None
        and background_hidden_polls is not None
        and background_poll_count is not None
        and hidden_recovery_used is not None
    ):
        break
contamination = []
for needle in [
    "Skip to content",
    "Chat history",
    "You said:",
    "At the very end of your final answer, print exactly:",
    "Completion contract for browser automation:",
    "Tab ID:",
    "Activated:",
    "TabWasCreated:",
    "NoActivate:",
]:
    if needle in out_text:
        contamination.append(needle)

def _parse_focus(s):
    if not s:
        return {"focusedWindowId": None, "activeTabId": None, "activeTabUrl": None}
    try:
        d = json.loads(s)
    except Exception:
        return {"focusedWindowId": None, "activeTabId": None, "activeTabUrl": None}
    return {
        "focusedWindowId": d.get("focusedWindowId"),
        "activeTabId": d.get("activeTabId"),
        "activeTabUrl": d.get("activeTabUrl"),
    }

focus_before = _parse_focus(focus_before_s)
focus_after = _parse_focus(focus_after_s)
focus_changed = (
    focus_before["focusedWindowId"] != focus_after["focusedWindowId"]
    or focus_before["activeTabId"] != focus_after["activeTabId"]
)
no_activate = no_activate_s == "1"

tab_mismatch = bool(requested_tab_id and tab_id and requested_tab_id != tab_id)
focus_stolen_mid = focus_stolen_mid_s == "1"
focus_violation = no_activate and (focus_changed or focus_stolen_mid)
response_integrity_ok = (
    tab_id
    and not tab_mismatch
    and not contamination
    and sentinel in raw_text
    and sentinel not in out_text
)
if response_integrity_ok and not focus_violation:
    status = "completed"
elif response_integrity_ok and focus_violation:
    status = "recovered_focus_changed"
else:
    status = "failed"
if status == "completed":
    failure = None
elif focus_violation and focus_stolen_mid:
    failure = "focus_stolen_mid_submit"
elif focus_violation:
    failure = "focus_stolen_despite_no_activate"
elif tab_mismatch:
    failure = "controlled_tab_id_mismatch"
else:
    failure = "missing_controlled_tab_id_or_contaminated_clean_output"
pathlib.Path(meta).write_text(json.dumps({
    "status": status,
    "failure": failure,
    "input": inp,
    "submitted_output": submitted,
    "output": out,
    "raw_output": raw,
    "stderr_log": err,
    "sentinel": sentinel,
    "requested_tab_id": requested_tab_id or None,
    "requested_url": target_url or None,
    "requested_model": model or None,
    "requested_reasoning": reasoning or None,
    "observed_requested_reasoning": requested_reasoning_observed,
    "selected_reasoning": selected_reasoning,
    "reasoning_selection_status": reasoning_selection_status,
    "reasoning_selection_error": reasoning_selection_error,
    "tab_identity_preflight": identity,
    "roundtrip_preflight_required": roundtrip_required_s == "1",
    "roundtrip_preflight_exit_code": int(roundtrip_status_s or 0),
    "roundtrip_preflight_output_dir": roundtrip_dir or None,
    "roundtrip_preflight": roundtrip,
    "stable_polls": int(stable),
    "timeout_s": int(timeout_s),
    "raw_contains_sentinel": sentinel in raw_text,
    "clean_contains_sentinel": sentinel in out_text,
    "clean_contamination_markers": contamination,
    "raw_chars": len(raw_text),
    "clean_chars": len(out_text),
    "controlled_tab_id": tab_id,
    "controlled_tab_id_mismatch": tab_mismatch,
    "no_activate": no_activate,
    "tab_was_created": tab_was_created,
    "activated": activated,
    "focused_window_before": focus_before["focusedWindowId"],
    "focused_window_after": focus_after["focusedWindowId"],
    "active_tab_before": focus_before["activeTabId"],
    "active_tab_after": focus_after["activeTabId"],
    "focus_changed": focus_changed,
    "focus_stolen_mid_submit": focus_stolen_mid,
    "focus_invariant_ok": not focus_violation,
    "transport_degraded": bool(status == "recovered_focus_changed"),
    "recovered_output": bool(status == "recovered_focus_changed"),
    "focus_mid_log": focus_mid_log,
    "response_source": response_source,
    "response_proof_status": "response_proven" if response_integrity_ok else "response_unproven",
    "extract_fallback_used": extract_fallback_used,
    "extract_fallback_reason": extract_fallback_reason,
    "extract_fallback_raw": extract_fallback_raw,
    "extract_fallback_meta": extract_fallback_meta,
    "conversation_url": conversation_url,
    "page_text_contains_sentinel": page_text_contains_sentinel,
    "document_hidden_at_completion": document_hidden_at_completion,
    "visibility_state_at_completion": visibility_state_at_completion,
    "background_hidden_polls": background_hidden_polls,
    "hidden_recovery_used": hidden_recovery_used,
    "background_poll_count": background_poll_count,
    "notification_assisted_wait_requested": notification_assisted_wait_requested,
    "notification_assisted_wait_completion_proof": notification_assisted_wait_completion_proof,
    "notification_assisted_wait_reason": notification_assisted_wait_reason,
    "started_at": started,
    "finished_at": finished,
}, indent=2) + "\n")
PY

enrich_agent_diagnosis

if [[ "$no_remember" -eq 0 ]]; then
  python3 - "$meta_output" "$tab_state_file" <<'PY'
import json, pathlib, sys
meta_path, state_path = map(pathlib.Path, sys.argv[1:])
meta = json.loads(meta_path.read_text())
tab_id = meta.get("controlled_tab_id")
if meta.get("status") == "completed" and tab_id:
    state_path.write_text(str(tab_id).strip() + "\n")
PY
fi

cat "$meta_output"
python3 - "$meta_output" <<'PY'
import json, pathlib, sys
meta = json.loads(pathlib.Path(sys.argv[1]).read_text())
if meta.get("status") not in {"completed", "recovered_focus_changed"}:
    raise SystemExit(5)
PY
