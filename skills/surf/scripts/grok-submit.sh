#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_SH="${SURF_RUN_SH:-${SKILL_DIR}/run.sh}"

usage() {
  cat <<'EOF'
Usage:
  surf grok.submit --input REQUEST.md --output RESPONSE.md [options]

Options:
  --input PATH              Prompt file to submit. Required.
  --output PATH             Clean response path. Required.
  --raw-output PATH         Raw response path. Default: <output>.raw.md
  --meta-output PATH        Proof metadata JSON. Default: <output>.meta.json
  --submitted-output PATH   Submitted prompt with sentinel injection.
  --sentinel auto|MARKER    Completion marker. Default: auto.
  --timeout SECONDS         Browser wait timeout. Default: 300.
  --model MODEL             Optional Grok model: auto, fast, expert, grok-4.20-beta.
  --deep-search             Enable Grok DeepSearch.
  --with-page               Include current page context using upstream surf grok.
  --tab-id ID               Use this exact live Grok/X tab before submit.
  --url URL                 Resolve and verify an already-open Grok/X tab.
  --attach-file PATH        Attach a file before submitting when Grok exposes
                            a file input. May be repeated.
  --attach-files PATHS      Comma-separated attachment paths. Equivalent to
                            repeated --attach-file flags.
  --no-activate             Accepted for Tau/browser-handler parity. Grok uses
                            exact-tab CDP control; some Chrome/Grok states may
                            still require the tab to be visible to generate.
EOF
}

input=""
output=""
raw_output=""
meta_output=""
submitted_output=""
sentinel="auto"
timeout_s=300
model=""
deep_search=0
with_page=0
tab_id=""
target_url=""
no_activate=0
attach_files=()
tab_state_file="${SURF_GROK_TAB_STATE:-/tmp/surf-grok-controlled-tab-id}"
provider_busy_cooldown_s="${SURF_GROK_PROVIDER_BUSY_COOLDOWN_SECONDS:-120}"
provider_busy_retry_attempts="${SURF_GROK_PROVIDER_BUSY_RETRY_ATTEMPTS:-1}"

add_attach_files_arg() {
  local value="$1"
  local IFS=','
  local part
  for part in $value; do
    if [[ -n "$part" ]]; then
      attach_files+=("$part")
    fi
  done
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --input) input="${2:-}"; shift 2 ;;
    --output) output="${2:-}"; shift 2 ;;
    --raw-output) raw_output="${2:-}"; shift 2 ;;
    --meta-output) meta_output="${2:-}"; shift 2 ;;
    --submitted-output) submitted_output="${2:-}"; shift 2 ;;
    --sentinel) sentinel="${2:-}"; shift 2 ;;
    --timeout) timeout_s="${2:-}"; shift 2 ;;
    --stable-polls) shift 2 ;; # accepted for browser-handler command parity
    --model) model="${2:-}"; shift 2 ;;
    --deep-search) deep_search=1; shift ;;
    --with-page) with_page=1; shift ;;
    --tab-id) tab_id="${2:-}"; shift 2 ;;
    --url) target_url="${2:-}"; shift 2 ;;
    --no-activate) no_activate=1; shift ;;
    --attach-file) attach_files+=("${2:-}"); shift 2 ;;
    --attach-files) add_attach_files_arg "${2:-}"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$input" || -z "$output" ]]; then
  usage >&2
  exit 2
fi
if [[ ! -f "$input" ]]; then
  echo "Input file not found: $input" >&2
  exit 2
fi
if [[ -z "${SURF_RUN_SH:-}" && ! -S /tmp/surf.sock ]]; then
  echo "surf grok.submit requires the surf browser extension socket at /tmp/surf.sock." >&2
  echo "Run: surf setup" >&2
  exit 3
fi
attach_file_abs=()
for attach_file in "${attach_files[@]}"; do
  if [[ ! -f "$attach_file" ]]; then
    echo "--attach-file: file not found: $attach_file" >&2
    exit 2
  fi
  attach_file_abs+=("$(readlink -f "$attach_file")")
done

if [[ "$sentinel" == "auto" || -z "$sentinel" ]]; then
  rand="$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')"
  sentinel="<<<GROK_DONE:$(date -u +%Y%m%dT%H%M%SZ):${rand}>>>"
fi

raw_output="${raw_output:-${output}.raw.md}"
meta_output="${meta_output:-${output}.meta.json}"
submitted_output="${submitted_output:-${output}.submitted.md}"
mkdir -p "$(dirname "$output")" "$(dirname "$raw_output")" "$(dirname "$meta_output")" "$(dirname "$submitted_output")"

prompt="$(cat "$input")"
submitted_prompt="${prompt}

---

Automation-only instruction: answer the user's request normally. Do not mention,
quote, summarize, or explain this automation instruction. After your complete
answer, append a final line containing only this exact marker:

${sentinel}

Do not print anything after that marker."

printf '%s\n' "$submitted_prompt" > "$submitted_output"

requested_tab_id=""
resolved_url=""
if [[ -n "$tab_id" ]]; then
  requested_tab_id="$(printf '%s' "$tab_id" | tr -cd '0-9' | head -c 20 || true)"
  if [[ -z "$requested_tab_id" ]]; then
    echo "Invalid --tab-id: $tab_id" >&2
    exit 2
  fi
elif [[ -n "$target_url" ]]; then
  requested_tab_id="$(
    "$RUN_SH" tab.list --json 2>/dev/null \
      | python3 -c 'import json, sys
target = sys.argv[1].rstrip("/")
data = json.load(sys.stdin)
if isinstance(data, dict):
    data = data.get("tabs", [])
for tab in data:
    url = str(tab.get("url") or "").rstrip("/")
    if url == target:
        print(tab.get("id") or "")
        raise SystemExit(0)
' "$target_url"
  )"
  if [[ -z "$requested_tab_id" ]]; then
    echo "No open Chrome tab matched --url: $target_url" >&2
    echo "Use --tab-id for the exact tab or open the URL before retrying." >&2
    exit 2
  fi
elif [[ -f "$tab_state_file" ]]; then
  remembered_tab_id="$(tr -cd '0-9' < "$tab_state_file" | head -c 20 || true)"
  if [[ -n "$remembered_tab_id" ]]; then
    requested_tab_id="$remembered_tab_id"
  fi
fi

tab_preflight_json="{}"
if [[ -n "$requested_tab_id" ]]; then
  tab_preflight_json="$(
    "$RUN_SH" tab.list --json 2>/dev/null \
      | python3 -c 'import json, sys, urllib.parse
tab_id, expected_url = sys.argv[1], sys.argv[2].rstrip("/")
try:
    data = json.load(sys.stdin)
except Exception as exc:
    print(json.dumps({"ok": False, "error": "tab_list_invalid_json", "detail": str(exc)}))
    raise SystemExit(0)
if isinstance(data, dict):
    data = data.get("tabs", [])
tab = next((t for t in data if str(t.get("id") or "") == tab_id), None)
if not tab:
    print(json.dumps({"ok": False, "error": "missing_live_tab", "expected_tab_id": tab_id}))
    raise SystemExit(0)
url = str(tab.get("url") or "")
host = urllib.parse.urlparse(url).netloc.lower()
provider_ok = host in {"grok.com", "www.grok.com", "x.com", "www.x.com"}
expected = urllib.parse.urlparse(expected_url) if expected_url else None
if not expected:
    url_ok = True
elif expected.path in {"", "/"} and not expected.query and not expected.fragment:
    url_ok = host.removeprefix("www.") == expected.netloc.lower().removeprefix("www.")
else:
    url_ok = url.rstrip("/") == expected_url
print(json.dumps({
    "ok": bool(provider_ok and url_ok),
    "expected_tab_id": tab_id,
    "expected_url": expected_url or None,
    "live_url": url,
    "provider_ok": provider_ok,
    "url_ok": url_ok,
    "tab": tab,
}))
' "$requested_tab_id" "$target_url"
  )"
  if ! printf '%s' "$tab_preflight_json" | python3 -c 'import json,sys; raise SystemExit(0 if json.load(sys.stdin).get("ok") else 1)' 2>/dev/null; then
    python3 - "$meta_output" "$input" "$submitted_output" "$output" "$raw_output" "$sentinel" "$requested_tab_id" "$target_url" "$tab_preflight_json" <<'PY'
import json, pathlib, sys
meta, inp, submitted, out, raw, sentinel, tab_id, target_url, preflight = sys.argv[1:]
pathlib.Path(meta).write_text(json.dumps({
    "status": "failed",
    "failure": "browser_tab_identity_mismatch",
    "proof_status": "wrong_tab",
    "input": inp,
    "submitted_output": submitted,
    "output": out,
    "raw_output": raw,
    "sentinel": sentinel,
    "requested_tab_id": tab_id or None,
    "requested_url": target_url or None,
    "tab_identity_preflight": json.loads(preflight),
}, indent=2, sort_keys=True) + "\n")
PY
    echo "Grok tab identity preflight failed: $tab_preflight_json" >&2
    exit 4
  fi
  resolved_url="$(printf '%s' "$tab_preflight_json" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("live_url") or "")')"
fi

stderr_log="$(mktemp /tmp/surf-grok-submit-stderr.XXXXXX.log)"
raw_tmp="$(mktemp /tmp/surf-grok-submit-raw.XXXXXX.md)"
fallback_summary_json=""
provider_busy_cooldown_count=0
generic_first_attempted=0
args=(grok "$submitted_prompt" --timeout "$timeout_s")
if [[ -n "$requested_tab_id" ]]; then
  args+=(--tab-id "$requested_tab_id" --target-tab-id "$requested_tab_id")
fi
if [[ -n "$model" ]]; then
  args+=(--model "$model")
fi
if [[ "$deep_search" -eq 1 ]]; then
  args+=(--deep-search)
fi
if [[ "$with_page" -eq 1 ]]; then
  args+=(--with-page)
fi

focus_before_json="$("$RUN_SH" focus.state --json 2>/dev/null || true)"
started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
attempt=0
if [[ -n "$requested_tab_id" && "${SURF_GROK_NATIVE_EXACT_TAB_FIRST:-1}" != "1" ]]; then
  fallback_args=(
    python3 "${SCRIPT_DIR}/grok_generic_fallback.py"
    --surf-run "$RUN_SH"
    --tab-id "$requested_tab_id"
    --submitted-prompt-path "$submitted_output"
    --raw-output "$raw_tmp"
    --sentinel "$sentinel"
    --timeout "$timeout_s"
    --stable-polls 2
  )
  for attach_file in "${attach_file_abs[@]}"; do
    fallback_args+=(--attach-file "$attach_file")
  done
  set +e
  fallback_summary_json="$("${fallback_args[@]}" 2>>"$stderr_log")"
  status=$?
  set -e
  generic_first_attempted=1
else
  status=1
fi
while true; do
  if [[ "$generic_first_attempted" -eq 1 && "$status" -eq 0 ]]; then
    break
  fi
  if [[ "$generic_first_attempted" -eq 1 && "$status" -ne 0 ]]; then
    haystack="$(cat "$stderr_log" "$raw_tmp" 2>/dev/null | tr '[:upper:]' '[:lower:]' || true)"
    if [[ "$haystack" == *"system is currently busy"* || "$haystack" == *"temporarily busy"* || "$haystack" == *"high demand"* || "$haystack" == *"capacity is busy"* ]]; then
      if [[ "$attempt" -lt "$provider_busy_retry_attempts" ]]; then
        attempt=$((attempt + 1))
        provider_busy_cooldown_count=$((provider_busy_cooldown_count + 1))
        echo "Grok provider busy; cooling down ${provider_busy_cooldown_s}s before retry ${attempt}/${provider_busy_retry_attempts}." >&2
        sleep "$provider_busy_cooldown_s"
        set +e
        fallback_summary_json="$("${fallback_args[@]}" 2>>"$stderr_log")"
        status=$?
        set -e
        continue
      fi
    fi
    break
  fi
  set +e
  if command -v timeout >/dev/null 2>&1; then
    hard_timeout_s=$((timeout_s + 60))
    timeout --kill-after=10s "${hard_timeout_s}s" "$RUN_SH" "${args[@]}" > "$raw_tmp" 2> "$stderr_log"
  else
    "$RUN_SH" "${args[@]}" > "$raw_tmp" 2> "$stderr_log"
  fi
  status=$?
  set -e
  haystack="$(cat "$stderr_log" "$raw_tmp" 2>/dev/null | tr '[:upper:]' '[:lower:]' || true)"
  if [[ $status -ne 0 && -n "$requested_tab_id" && ( "$haystack" == *"unknown message type: grok_evaluate"* || "$status" -eq 124 || "$status" -eq 137 ) ]]; then
    fallback_args=(
      python3 "${SCRIPT_DIR}/grok_generic_fallback.py"
      --surf-run "$RUN_SH"
      --tab-id "$requested_tab_id"
      --submitted-prompt-path "$submitted_output"
      --raw-output "$raw_tmp"
      --sentinel "$sentinel"
      --timeout "$timeout_s"
      --stable-polls 2
    )
    for attach_file in "${attach_file_abs[@]}"; do
      fallback_args+=(--attach-file "$attach_file")
    done
    set +e
    fallback_summary_json="$("${fallback_args[@]}" 2>>"$stderr_log")"
    fallback_status=$?
    set -e
    if [[ $fallback_status -eq 0 ]]; then
      status=0
      break
    fi
  fi
  haystack="$(cat "$stderr_log" "$raw_tmp" 2>/dev/null | tr '[:upper:]' '[:lower:]' || true)"
  if [[ "$haystack" == *"system is currently busy"* || "$haystack" == *"temporarily busy"* || "$haystack" == *"high demand"* || "$haystack" == *"capacity is busy"* ]]; then
    if [[ "$attempt" -lt "$provider_busy_retry_attempts" ]]; then
      attempt=$((attempt + 1))
      provider_busy_cooldown_count=$((provider_busy_cooldown_count + 1))
      echo "Grok provider busy; cooling down ${provider_busy_cooldown_s}s before retry ${attempt}/${provider_busy_retry_attempts}." >&2
      sleep "$provider_busy_cooldown_s"
      continue
    fi
  fi
  break
done
finished_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
focus_after_json="$("$RUN_SH" focus.state --json 2>/dev/null || true)"

cp "$raw_tmp" "$raw_output"

if [[ $status -ne 0 ]]; then
  python3 - "$meta_output" "$input" "$submitted_output" "$output" "$raw_output" "$stderr_log" "$sentinel" "$started_at" "$finished_at" "$status" "$requested_tab_id" "$target_url" "$resolved_url" "$tab_preflight_json" "$focus_before_json" "$focus_after_json" "$no_activate" "$provider_busy_cooldown_s" "$provider_busy_cooldown_count" "$provider_busy_retry_attempts" "$fallback_summary_json" "$(printf '%s\n' "${attach_file_abs[@]}" | python3 -c 'import json,sys; print(json.dumps([line.strip() for line in sys.stdin if line.strip()]))')" <<'PY'
import json, pathlib, sys
meta, inp, submitted, out, raw, err, sentinel, started, finished, status, requested_tab_id, target_url, resolved_url, preflight, focus_before, focus_after, no_activate, cooldown_s, cooldown_count, retry_attempts, fallback_summary, attach_files_s = sys.argv[1:]
stderr_text = pathlib.Path(err).read_text(errors="replace") if pathlib.Path(err).exists() else ""
raw_text = pathlib.Path(raw).read_text(errors="replace") if pathlib.Path(raw).exists() else ""
fallback = json.loads(fallback_summary) if fallback_summary else None
fallback_text = json.dumps(fallback or {})
haystack = (stderr_text + "\n" + raw_text + "\n" + fallback_text).lower()
if "not authenticated" in haystack or "login required" in haystack or "log in to x.com" in haystack:
    failure = "grok_auth_required"
    blocker = "BLOCKED_GROK_AUTH_REQUIRED"
elif "unknown message type: grok_evaluate" in haystack:
    failure = "grok_tool_unsupported"
    blocker = "BLOCKED_GROK_TOOL_UNSUPPORTED"
elif "premium" in haystack or "subscribe" in haystack:
    failure = "grok_subscription_required"
    blocker = "BLOCKED_GROK_SUBSCRIPTION_REQUIRED"
elif "system is currently busy" in haystack or "temporarily busy" in haystack or "high demand" in haystack or "capacity is busy" in haystack:
    failure = "grok_provider_capacity_busy"
    blocker = "BLOCKED_GROK_PROVIDER_CAPACITY"
elif "rate limit" in haystack or "quota" in haystack or "too many" in haystack:
    failure = "grok_provider_rate_limited"
    blocker = "BLOCKED_GROK_PROVIDER_RATE_LIMIT"
elif "timed out after" in haystack and ("'js'" in haystack or " surf/run.sh" in haystack or "run.sh" in haystack):
    failure = "browser_tab_read_timeout"
    blocker = "BROWSER_TAB_READ_TIMEOUT"
else:
    failure = "grok_submit_failed"
    blocker = None
if failure == "browser_tab_read_timeout":
    proof_status = "browser_tab_read_timeout"
elif blocker:
    proof_status = "provider_blocked"
else:
    proof_status = "failed"
pathlib.Path(meta).write_text(json.dumps({
    "status": "failed",
    "exit_code": int(status),
    "failure": failure,
    "blocker": blocker,
    "proof_status": proof_status,
    "input": inp,
    "submitted_output": submitted,
    "output": out,
    "raw_output": raw,
    "stderr_log": err,
    "sentinel": sentinel,
    "requested_tab_id": requested_tab_id or None,
    "requested_url": target_url or None,
    "resolved_url": resolved_url or None,
    "tab_identity_preflight": json.loads(preflight or "{}"),
    "no_activate": no_activate == "1",
    "attach_files": json.loads(attach_files_s or "[]"),
    "provider_busy_cooldown_seconds": int(cooldown_s),
    "provider_busy_cooldown_count": int(cooldown_count),
    "provider_busy_retry_attempts": int(retry_attempts),
    "fallback_summary": fallback,
    "focus_before": json.loads(focus_before or "{}") if focus_before else None,
    "focus_after": json.loads(focus_after or "{}") if focus_after else None,
    "started_at": started,
    "finished_at": finished,
}, indent=2, sort_keys=True) + "\n")
PY
  cat "$stderr_log" >&2
  exit "$status"
fi

if ! grep -Fq "$sentinel" "$raw_output"; then
  python3 - "$meta_output" "$input" "$submitted_output" "$output" "$raw_output" "$stderr_log" "$sentinel" "$started_at" "$finished_at" "$requested_tab_id" "$target_url" "$resolved_url" "$tab_preflight_json" "$focus_before_json" "$focus_after_json" "$no_activate" "$provider_busy_cooldown_s" "$provider_busy_cooldown_count" "$provider_busy_retry_attempts" "$fallback_summary_json" "$(printf '%s\n' "${attach_file_abs[@]}" | python3 -c 'import json,sys; print(json.dumps([line.strip() for line in sys.stdin if line.strip()]))')" <<'PY'
import json, pathlib, sys
meta, inp, submitted, out, raw, err, sentinel, started, finished, requested_tab_id, target_url, resolved_url, preflight, focus_before, focus_after, no_activate, cooldown_s, cooldown_count, retry_attempts, fallback_summary, attach_files_s = sys.argv[1:]
text = pathlib.Path(raw).read_text(errors="replace") if pathlib.Path(raw).exists() else ""
busy = any(needle in text.lower() for needle in ["system is currently busy", "temporarily busy", "high demand", "capacity is busy"])
pathlib.Path(meta).write_text(json.dumps({
    "status": "missing_sentinel",
    "failure": "grok_provider_capacity_busy" if busy else "missing_sentinel",
    "blocker": "BLOCKED_GROK_PROVIDER_CAPACITY" if busy else None,
    "proof_status": "provider_capacity_limited" if busy else "submitted_no_response_proof",
    "input": inp,
    "submitted_output": submitted,
    "output": out,
    "raw_output": raw,
    "stderr_log": err,
    "sentinel": sentinel,
    "requested_tab_id": requested_tab_id or None,
    "requested_url": target_url or None,
    "resolved_url": resolved_url or None,
    "tab_identity_preflight": json.loads(preflight or "{}"),
    "no_activate": no_activate == "1",
    "attach_files": json.loads(attach_files_s or "[]"),
    "provider_busy_cooldown_seconds": int(cooldown_s),
    "provider_busy_cooldown_count": int(cooldown_count),
    "provider_busy_retry_attempts": int(retry_attempts),
    "fallback_summary": json.loads(fallback_summary) if fallback_summary else None,
    "focus_before": json.loads(focus_before or "{}") if focus_before else None,
    "focus_after": json.loads(focus_after or "{}") if focus_after else None,
    "started_at": started,
    "finished_at": finished,
}, indent=2, sort_keys=True) + "\n")
PY
  echo "Grok response did not contain sentinel: $sentinel" >&2
  exit 4
fi

python3 - "$raw_output" "$output" "$sentinel" <<'PY'
import pathlib, sys
raw_path, out_path, sentinel = sys.argv[1:]
text = pathlib.Path(raw_path).read_text()
idx = text.rfind(sentinel)
if idx == -1:
    raise SystemExit("sentinel missing from assistant response")
after = text[idx + len(sentinel):].strip()
if after:
    raise SystemExit("assistant response contains text after terminal sentinel")
clean = text[:idx].rstrip() + "\n"
pathlib.Path(out_path).write_text(clean)
PY

python3 - "$meta_output" "$input" "$submitted_output" "$output" "$raw_output" "$stderr_log" "$sentinel" "$timeout_s" "$started_at" "$finished_at" "$requested_tab_id" "$target_url" "$resolved_url" "$tab_preflight_json" "$focus_before_json" "$focus_after_json" "$no_activate" "$provider_busy_cooldown_s" "$provider_busy_cooldown_count" "$provider_busy_retry_attempts" "$fallback_summary_json" "$(printf '%s\n' "${attach_file_abs[@]}" | python3 -c 'import json,sys; print(json.dumps([line.strip() for line in sys.stdin if line.strip()]))')" <<'PY'
import json, pathlib, sys
meta, inp, submitted, out, raw, err, sentinel, timeout_s, started, finished, requested_tab_id, target_url, resolved_url, preflight, focus_before, focus_after, no_activate, cooldown_s, cooldown_count, retry_attempts, fallback_summary, attach_files_s = sys.argv[1:]
raw_text = pathlib.Path(raw).read_text()
out_text = pathlib.Path(out).read_text()
pathlib.Path(meta).write_text(json.dumps({
    "status": "completed",
    "proof_status": "response_proven",
    "input": inp,
    "submitted_output": submitted,
    "output": out,
    "raw_output": raw,
    "stderr_log": err,
    "sentinel": sentinel,
    "requested_tab_id": requested_tab_id or None,
    "requested_url": target_url or None,
    "resolved_url": resolved_url or None,
    "tab_identity_preflight": json.loads(preflight or "{}"),
    "tab_bound_control_proof": "exact_tab_prompt_verified_submit_observed" if requested_tab_id else "upstream_grok_created_tab",
    "timeout_s": int(timeout_s),
    "raw_contains_sentinel": sentinel in raw_text,
    "clean_contains_sentinel": sentinel in out_text,
    "raw_chars": len(raw_text),
    "clean_chars": len(out_text),
    "controlled_tab_id": requested_tab_id or None,
    "no_activate": no_activate == "1",
    "attach_files": json.loads(attach_files_s or "[]"),
    "provider_busy_cooldown_seconds": int(cooldown_s),
    "provider_busy_cooldown_count": int(cooldown_count),
    "provider_busy_retry_attempts": int(retry_attempts),
    "fallback_summary": json.loads(fallback_summary) if fallback_summary else None,
    "focus_before": json.loads(focus_before or "{}") if focus_before else None,
    "focus_after": json.loads(focus_after or "{}") if focus_after else None,
    "started_at": started,
    "finished_at": finished,
}, indent=2, sort_keys=True) + "\n")
PY

if [[ -n "$requested_tab_id" ]]; then
  printf '%s\n' "$requested_tab_id" > "$tab_state_file"
fi

cat "$meta_output"
