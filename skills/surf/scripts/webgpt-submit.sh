#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_SH="${SURF_RUN_SH:-${SKILL_DIR}/run.sh}"

# shellcheck source=lib/webgpt_resolve.sh
source "${SCRIPT_DIR}/lib/webgpt_resolve.sh"

usage() {
  cat <<'EOF'
Usage:
  surf webgpt.submit --input REQUEST.md --output RESPONSE.md [options]

Options:
  --input PATH              Prompt file to submit. Required.
  --output PATH             Clean response path. Required.
  --raw-output PATH         Raw response path. Default: <output>.raw.md
  --meta-output PATH        Proof metadata JSON. Default: <output>.meta.json
  --submitted-output PATH   Submitted prompt with sentinel injection.
  --sentinel auto|MARKER    Completion marker. Default: auto.
  --stable-polls N          Unchanged polls after sentinel before returning. Default: 3.
  --timeout SECONDS         Browser wait timeout. Default: 900.
  --model MODEL             Optional ChatGPT model selector label.
  --reasoning LABEL         Optional ChatGPT reasoning dropdown label
                            (for example: "Pro" or "Heavy Reasoning").
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
EOF
}

input=""
output=""
raw_output=""
meta_output=""
submitted_output=""
sentinel="auto"
stable_polls=3
timeout_s=900
model=""
reasoning=""
tab_id=""
target_url=""
expect_url=""
expect_title=""
allow_unverified_tab_id=0
no_activate=0
create_tab=0
no_remember=0
allow_foreground_controlled=0
attach_file=""
tab_state_file="${SURF_WEBGPT_TAB_STATE:-/tmp/surf-webgpt-controlled-tab-id}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --input) input="${2:-}"; shift 2 ;;
    --output) output="${2:-}"; shift 2 ;;
    --raw-output) raw_output="${2:-}"; shift 2 ;;
    --meta-output) meta_output="${2:-}"; shift 2 ;;
    --submitted-output) submitted_output="${2:-}"; shift 2 ;;
    --sentinel) sentinel="${2:-}"; shift 2 ;;
    --stable-polls) stable_polls="${2:-}"; shift 2 ;;
    --timeout) timeout_s="${2:-}"; shift 2 ;;
    --model) model="${2:-}"; shift 2 ;;
    --reasoning) reasoning="${2:-}"; shift 2 ;;
    --tab-id) tab_id="${2:-}"; shift 2 ;;
    --url) target_url="${2:-}"; shift 2 ;;
    --expect-url) expect_url="${2:-}"; shift 2 ;;
    --expect-title) expect_title="${2:-}"; shift 2 ;;
    --allow-unverified-tab-id) allow_unverified_tab_id=1; shift ;;
    --no-activate) no_activate=1; shift ;;
    --create-tab) create_tab=1; shift ;;
    --no-remember) no_remember=1; shift ;;
    --allow-foreground-controlled) allow_foreground_controlled=1; shift ;;
    --attach-file) attach_file="${2:-}"; shift 2 ;;
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
if [[ ! -f "$input" ]]; then
  echo "Input file not found: $input" >&2
  exit 2
fi
if [[ -z "${SURF_RUN_SH:-}" && ! -S /tmp/surf.sock ]]; then
  echo "surf webgpt.submit requires the surf browser extension socket at /tmp/surf.sock." >&2
  echo "Run: surf setup" >&2
  exit 3
fi

if [[ "$sentinel" == "auto" || -z "$sentinel" ]]; then
  rand="$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')"
  sentinel="<<<WEBGPT_DONE:$(date -u +%Y%m%dT%H%M%SZ):${rand}>>>"
fi

raw_output="${raw_output:-${output}.raw.md}"
meta_output="${meta_output:-${output}.meta.json}"
submitted_output="${submitted_output:-${output}.submitted.md}"
mkdir -p "$(dirname "$output")" "$(dirname "$raw_output")" "$(dirname "$meta_output")" "$(dirname "$submitted_output")"

prompt="$(cat "$input")"
submitted_prompt="${prompt}

---

Completion contract for browser automation:

At the very end of your final answer, print exactly:

${sentinel}

Do not print anything after that marker."

printf '%s\n' "$submitted_prompt" > "$submitted_output"

stderr_log="$(mktemp /tmp/surf-webgpt-submit-stderr.XXXXXX.log)"
raw_tmp="$(mktemp /tmp/surf-webgpt-submit-raw.XXXXXX.md)"
# Dedicated reviewer tab (inactive). Avoids reusing global state or auto-picking
# the newest chatgpt.com tab (often the user's foreground conversation).
if [[ "$create_tab" -eq 1 ]]; then
  no_remember=1
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
fi

args=(chatgpt "$submitted_prompt" --sentinel "$sentinel" --stable-polls "$stable_polls" --timeout "$timeout_s" --keep-tab)
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
    echo "webgpt.submit tab identity preflight failed for tab $requested_tab_id." >&2
    python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('error') or 'tab_identity_failed')" "$identity_preflight_json" >&2
    echo "Use --url <conversation-url>, --expect-url, --expect-title, --create-tab, or --allow-unverified-tab-id." >&2
    exit 2
  fi
else
  identity_preflight_json=""
fi

# Pre-run focus snapshot (also used for --no-activate foreground guard).
focus_before_json="$("$RUN_SH" focus.state --json 2>/dev/null || true)"

if [[ "$no_activate" -eq 1 ]]; then
  if [[ -z "${requested_tab_id:-}" ]]; then
    echo "--no-activate requires --tab-id, --url, or --create-tab so we never foreground a tab to discover one." >&2
    exit 2
  fi
  if [[ "$allow_foreground_controlled" -eq 0 ]]; then
    active_now="$(webgpt_focus_active_tab_id "$focus_before_json")"
    if [[ -n "$active_now" && "$active_now" == "$requested_tab_id" ]]; then
      echo "Controlled tab $requested_tab_id is the foreground active tab; --no-activate will fail." >&2
      echo "Switch to another tab, pick a dedicated reviewer tab, or pass --allow-foreground-controlled." >&2
      exit 2
    fi
  fi
  args+=(--no-activate)
fi

if [[ -n "$attach_file" ]]; then
  if [[ ! -f "$attach_file" ]]; then
    echo "--attach-file: file not found: $attach_file" >&2
    exit 2
  fi
  attach_file_abs="$(readlink -f "$attach_file")"
  args+=(--file "$attach_file_abs")
fi

started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
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
poll_interval="${SURF_WEBGPT_FOCUS_POLL_INTERVAL:-15}"
(
  while kill -0 "$submit_pid" 2>/dev/null; do
    sleep "$poll_interval"
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
kill "$poll_pid" 2>/dev/null || true
wait "$poll_pid" 2>/dev/null || true
set -e
finished_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Post-run focus snapshot for proof.
focus_after_json="$("$RUN_SH" focus.state --json 2>/dev/null || true)"

cp "$raw_tmp" "$raw_output"

if [[ $status -ne 0 ]]; then
  python3 - "$meta_output" "$input" "$submitted_output" "$output" "$raw_output" "$stderr_log" "$sentinel" "$started_at" "$finished_at" "$status" "${requested_tab_id:-}" "$target_url" "$model" "$reasoning" "${identity_preflight_json:-}" <<'PY'
import json, pathlib, sys
meta, inp, submitted, out, raw, err, sentinel, started, finished, status, requested_tab_id, target_url, model, reasoning, identity_s = sys.argv[1:]
try:
    identity = json.loads(identity_s) if identity_s else None
except Exception:
    identity = {"ok": False, "error": "identity_meta_parse_failed"}
pathlib.Path(meta).write_text(json.dumps({
    "status": "failed",
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
    "started_at": started,
    "finished_at": finished,
}, indent=2) + "\n")
PY
  cat "$stderr_log" >&2
  exit "$status"
fi

if ! grep -Fq "$sentinel" "$raw_output"; then
  python3 - "$meta_output" "$input" "$submitted_output" "$output" "$raw_output" "$stderr_log" "$sentinel" "$started_at" "$finished_at" "${requested_tab_id:-}" "$target_url" "$model" "$reasoning" "${identity_preflight_json:-}" <<'PY'
import json, pathlib, sys
meta, inp, submitted, out, raw, err, sentinel, started, finished, requested_tab_id, target_url, model, reasoning, identity_s = sys.argv[1:]
try:
    identity = json.loads(identity_s) if identity_s else None
except Exception:
    identity = {"ok": False, "error": "identity_meta_parse_failed"}
pathlib.Path(meta).write_text(json.dumps({
    "status": "missing_sentinel",
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
    "started_at": started,
    "finished_at": finished,
}, indent=2) + "\n")
PY
  echo "ChatGPT response did not contain sentinel: $sentinel" >&2
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
if after and after.strip(">"):
    raise SystemExit("assistant response contains text after terminal sentinel")
clean = text[:idx].rstrip() + "\n"
pathlib.Path(out_path).write_text(clean)
PY

python3 - "$meta_output" "$input" "$submitted_output" "$output" "$raw_output" "$stderr_log" "$sentinel" "$stable_polls" "$timeout_s" "$started_at" "$finished_at" "${requested_tab_id:-}" "$target_url" "$no_activate" "$focus_before_json" "$focus_after_json" "$focus_stolen_mid" "$focus_mid_log" "$model" "$reasoning" "${identity_preflight_json:-}" <<'PY'
import json, pathlib, sys
meta, inp, submitted, out, raw, err, sentinel, stable, timeout_s, started, finished, requested_tab_id, target_url, no_activate_s, focus_before_s, focus_after_s, focus_stolen_mid_s, focus_mid_log, model, reasoning, identity_s = sys.argv[1:]
try:
    identity = json.loads(identity_s) if identity_s else None
except Exception:
    identity = {"ok": False, "error": "identity_meta_parse_failed"}
raw_text = pathlib.Path(raw).read_text()
out_text = pathlib.Path(out).read_text()
stderr_text = pathlib.Path(err).read_text() if pathlib.Path(err).exists() else ""
tab_id = None
activated = None
tab_was_created = None
for line in reversed(stderr_text.splitlines()):
    if line.startswith("Tab ID:") and tab_id is None:
        tab_id = line.split(":", 1)[1].strip()
    elif line.startswith("Activated:") and activated is None:
        activated = line.split(":", 1)[1].strip() == "true"
    elif line.startswith("TabWasCreated:") and tab_was_created is None:
        tab_was_created = line.split(":", 1)[1].strip() == "true"
    if tab_id is not None and activated is not None and tab_was_created is not None:
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
status = "completed" if (
    tab_id
    and not tab_mismatch
    and not contamination
    and sentinel in raw_text
    and sentinel not in out_text
    and not focus_violation
) else "failed"
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
    "tab_identity_preflight": identity,
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
    "focus_mid_log": focus_mid_log,
    "started_at": started,
    "finished_at": finished,
}, indent=2) + "\n")
PY

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
if meta.get("status") != "completed":
    raise SystemExit(5)
PY
