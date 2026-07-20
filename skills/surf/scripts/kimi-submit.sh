#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_SH="${SURF_RUN_SH:-${SKILL_DIR}/run.sh}"

usage() {
  cat <<'EOF'
Usage:
  surf kimi.submit --input REQUEST.md --output RESPONSE.md [options]

Options:
  --input PATH              Prompt file to submit. Required.
  --output PATH             Clean response path. Required.
  --raw-output PATH         Raw response path. Default: <output>.raw.md
  --meta-output PATH        Proof metadata JSON. Default: <output>.meta.json
  --submitted-output PATH   Submitted prompt with sentinel injection.
  --sentinel auto|MARKER    Completion marker. Default: auto.
  --stable-polls N          Unchanged polls after sentinel before returning. Default: 3.
  --timeout SECONDS         Browser wait timeout. Default: 300.
  --model MODEL             Optional Kimi model selector label.
  --tab-id ID               Use this exact Chrome tab as the controlled Kimi tab.
  --url URL                 Resolve an already-open Kimi tab by exact URL.
  --no-activate             Background controlled-tab mode. Do not foreground
                            the tab or its window. Requires --tab-id or --url
                            so an authenticated Kimi tab is already open.
  --attach-file PATH        Attach a file to the Kimi message (uses the
                            Kimi tab CDP upload path). The prompt body is sent normally; Kimi
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
timeout_s=300
model=""
tab_id=""
target_url=""
no_activate=0
attach_file=""
attach_file_abs=""
tab_state_file="${SURF_KIMI_TAB_STATE:-/tmp/surf-kimi-controlled-tab-id}"

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
    --tab-id) tab_id="${2:-}"; shift 2 ;;
    --url) target_url="${2:-}"; shift 2 ;;
    --no-activate) no_activate=1; shift ;;
    --attach-file) attach_file="${2:-}"; shift 2 ;;
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
  echo "surf kimi.submit requires the surf browser extension socket at /tmp/surf.sock." >&2
  echo "Run: surf setup" >&2
  exit 3
fi

if [[ "$sentinel" == "auto" || -z "$sentinel" ]]; then
  rand="$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')"
  sentinel="<<<KIMI_DONE:$(date -u +%Y%m%dT%H%M%SZ):${rand}>>>"
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

stderr_log="$(mktemp /tmp/surf-kimi-submit-stderr.XXXXXX.log)"
raw_tmp="$(mktemp /tmp/surf-kimi-submit-raw.XXXXXX.md)"
args=(kimi_tab "$submitted_prompt" --sentinel "$sentinel" --stable-polls "$stable_polls" --timeout "$timeout_s" --keep-tab)
if [[ -n "$model" ]]; then
  args+=(--model "$model")
fi
if [[ -n "$tab_id" ]]; then
  requested_tab_id="$(printf '%s' "$tab_id" | tr -cd '0-9' | head -c 20 || true)"
  if [[ -z "$requested_tab_id" ]]; then
    echo "Invalid --tab-id: $tab_id" >&2
    exit 2
  fi
  args+=(--tab-id "$requested_tab_id" --target-tab-id "$requested_tab_id")
elif [[ -n "$target_url" ]]; then
  requested_tab_id="$(
    "$RUN_SH" tab.list 2>/dev/null \
      | awk -F '\t' -v target="$target_url" '
          $3 == target { print $1; found=1; exit }
          target !~ /\/$/ && $3 == target "/" { print $1; found=1; exit }
          target ~ /\/$/ {
            without=target
            sub(/\/$/, "", without)
            if ($3 == without) { print $1; found=1; exit }
          }
        ' \
      | head -n 1
  )"
  if [[ -z "$requested_tab_id" ]]; then
    echo "No open Chrome tab matched --url: $target_url" >&2
    echo "Use --tab-id for the exact tab or open the URL before retrying." >&2
    exit 2
  fi
  args+=(--tab-id "$requested_tab_id" --target-tab-id "$requested_tab_id")
elif [[ -f "$tab_state_file" ]]; then
  remembered_tab_id="$(tr -cd '0-9' < "$tab_state_file" | head -c 20 || true)"
  if [[ -n "$remembered_tab_id" ]]; then
    args+=(--tab-id "$remembered_tab_id")
    requested_tab_id="$remembered_tab_id"
  fi
fi

if [[ "$no_activate" -eq 1 ]]; then
  if [[ -z "${requested_tab_id:-}" ]]; then
    echo "--no-activate requires --tab-id (or --url that resolves to an open tab) so we never have to foreground a tab to find one." >&2
    exit 2
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

# Pre-run focus snapshot for proof. Best-effort: if focus.state is missing
# from an older surf-cli, leave the fields as null.
focus_before_json="$("$RUN_SH" focus.state --json 2>/dev/null || true)"

started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
set +e
if command -v timeout >/dev/null 2>&1; then
  hard_timeout_s=$((timeout_s + 60))
  timeout --kill-after=10s "${hard_timeout_s}s" "$RUN_SH" "${args[@]}" > "$raw_tmp" 2> "$stderr_log"
else
  "$RUN_SH" "${args[@]}" > "$raw_tmp" 2> "$stderr_log"
fi
status=$?
set -e
finished_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Post-run focus snapshot for proof.
focus_after_json="$("$RUN_SH" focus.state --json 2>/dev/null || true)"

cp "$raw_tmp" "$raw_output"

if [[ $status -ne 0 ]]; then
  python3 - "$meta_output" "$input" "$submitted_output" "$output" "$raw_output" "$stderr_log" "$sentinel" "$started_at" "$finished_at" "$status" "${requested_tab_id:-}" "$target_url" <<'PY'
import json, pathlib, sys
meta, inp, submitted, out, raw, err, sentinel, started, finished, status, requested_tab_id, target_url = sys.argv[1:]
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
    "started_at": started,
    "finished_at": finished,
}, indent=2) + "\n")
PY
  cat "$stderr_log" >&2
  exit "$status"
fi

if ! grep -Fq "$sentinel" "$raw_output"; then
  python3 - "$meta_output" "$input" "$submitted_output" "$output" "$raw_output" "$stderr_log" "$sentinel" "$started_at" "$finished_at" "${requested_tab_id:-}" "$target_url" <<'PY'
import json, pathlib, sys
meta, inp, submitted, out, raw, err, sentinel, started, finished, requested_tab_id, target_url = sys.argv[1:]
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
    "started_at": started,
    "finished_at": finished,
}, indent=2) + "\n")
PY
  echo "Kimi response did not contain sentinel: $sentinel" >&2
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

python3 - "$meta_output" "$input" "$submitted_output" "$output" "$raw_output" "$stderr_log" "$sentinel" "$stable_polls" "$timeout_s" "$started_at" "$finished_at" "${requested_tab_id:-}" "$target_url" "$no_activate" "$focus_before_json" "$focus_after_json" "$attach_file_abs" <<'PY'
import json, pathlib, sys
meta, inp, submitted, out, raw, err, sentinel, stable, timeout_s, started, finished, requested_tab_id, target_url, no_activate_s, focus_before_s, focus_after_s, attach_file = sys.argv[1:]
raw_text = pathlib.Path(raw).read_text()
out_text = pathlib.Path(out).read_text()
stderr_text = pathlib.Path(err).read_text() if pathlib.Path(err).exists() else ""
tab_id = None
activated = None
tab_was_created = None
attachment = None
for line in reversed(stderr_text.splitlines()):
    if line.startswith("Tab ID:") and tab_id is None:
        tab_id = line.split(":", 1)[1].strip()
    elif line.startswith("Activated:") and activated is None:
        activated = line.split(":", 1)[1].strip() == "true"
    elif line.startswith("TabWasCreated:") and tab_was_created is None:
        tab_was_created = line.split(":", 1)[1].strip() == "true"
    elif line.startswith("Attachment:") and attachment is None:
        payload = line.split(":", 1)[1].strip()
        try:
            attachment = json.loads(payload)
        except Exception:
            attachment = {"parse_error": True, "raw": payload}
    if tab_id is not None and activated is not None and tab_was_created is not None and (not attach_file or attachment is not None):
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
activation_violation = no_activate and activated is True
attachment_missing = bool(attach_file) and not attachment
attachment_preview_missing = bool(attach_file) and bool(attachment) and attachment.get("previewVisible") is False
status = "completed" if (
    tab_id
    and not tab_mismatch
    and not contamination
    and sentinel in raw_text
    and sentinel not in out_text
    and not activation_violation
    and not attachment_missing
    and not attachment_preview_missing
) else "failed"
if status == "completed":
    failure = None
elif activation_violation:
    failure = "focus_stolen_despite_no_activate"
elif tab_mismatch:
    failure = "controlled_tab_id_mismatch"
elif attachment_missing:
    failure = "attachment_metadata_missing"
elif attachment_preview_missing:
    failure = "attachment_preview_missing"
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
    "attach_file": attach_file or None,
    "attachment": attachment,
    "attachment_missing": attachment_missing,
    "attachment_preview_missing": attachment_preview_missing,
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
    "activation_violation": activation_violation,
    "focused_window_before": focus_before["focusedWindowId"],
    "focused_window_after": focus_after["focusedWindowId"],
    "active_tab_before": focus_before["activeTabId"],
    "active_tab_after": focus_after["activeTabId"],
    "focus_changed": focus_changed,
    "started_at": started,
    "finished_at": finished,
}, indent=2) + "\n")
PY

python3 - "$meta_output" "$tab_state_file" <<'PY'
import json, pathlib, sys
meta_path, state_path = map(pathlib.Path, sys.argv[1:])
meta = json.loads(meta_path.read_text())
tab_id = meta.get("controlled_tab_id")
if meta.get("status") == "completed" and tab_id:
    state_path.write_text(str(tab_id).strip() + "\n")
PY

cat "$meta_output"
python3 - "$meta_output" <<'PY'
import json, pathlib, sys
meta = json.loads(pathlib.Path(sys.argv[1]).read_text())
if meta.get("status") != "completed":
    raise SystemExit(5)
PY
