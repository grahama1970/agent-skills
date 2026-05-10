#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_SH="${SURF_RUN_SH:-${SKILL_DIR}/run.sh}"

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
  --tab-id ID               Use this exact Chrome tab as the controlled WebGPT tab.
  --url URL                 Resolve an already-open ChatGPT tab by exact URL.
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
tab_id=""
target_url=""
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
    --tab-id) tab_id="${2:-}"; shift 2 ;;
    --url) target_url="${2:-}"; shift 2 ;;
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
args=(chatgpt "$submitted_prompt" --sentinel "$sentinel" --stable-polls "$stable_polls" --timeout "$timeout_s" --keep-tab)
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
  fi
fi

started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
set +e
"$RUN_SH" "${args[@]}" > "$raw_tmp" 2> "$stderr_log"
status=$?
set -e
finished_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

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
if after:
    raise SystemExit("assistant response contains text after terminal sentinel")
clean = text[:idx].rstrip() + "\n"
pathlib.Path(out_path).write_text(clean)
PY

python3 - "$meta_output" "$input" "$submitted_output" "$output" "$raw_output" "$stderr_log" "$sentinel" "$stable_polls" "$timeout_s" "$started_at" "$finished_at" "${requested_tab_id:-}" "$target_url" <<'PY'
import json, pathlib, sys
meta, inp, submitted, out, raw, err, sentinel, stable, timeout_s, started, finished, requested_tab_id, target_url = sys.argv[1:]
raw_text = pathlib.Path(raw).read_text()
out_text = pathlib.Path(out).read_text()
stderr_text = pathlib.Path(err).read_text() if pathlib.Path(err).exists() else ""
tab_id = None
for line in reversed(stderr_text.splitlines()):
    if line.startswith("Tab ID:"):
        tab_id = line.split(":", 1)[1].strip()
        break
contamination = []
for needle in [
    "Skip to content",
    "Chat history",
    "You said:",
    "At the very end of your final answer, print exactly:",
    "Completion contract for browser automation:",
    "Tab ID:",
]:
    if needle in out_text:
        contamination.append(needle)
tab_mismatch = bool(requested_tab_id and tab_id and requested_tab_id != tab_id)
status = "completed" if (
    tab_id
    and not tab_mismatch
    and not contamination
    and sentinel in raw_text
    and sentinel not in out_text
) else "failed"
pathlib.Path(meta).write_text(json.dumps({
    "status": status,
    "failure": None if status == "completed" else (
        "controlled_tab_id_mismatch" if tab_mismatch else "missing_controlled_tab_id_or_contaminated_clean_output"
    ),
    "input": inp,
    "submitted_output": submitted,
    "output": out,
    "raw_output": raw,
    "stderr_log": err,
    "sentinel": sentinel,
    "requested_tab_id": requested_tab_id or None,
    "requested_url": target_url or None,
    "stable_polls": int(stable),
    "timeout_s": int(timeout_s),
    "raw_contains_sentinel": sentinel in raw_text,
    "clean_contains_sentinel": sentinel in out_text,
    "clean_contamination_markers": contamination,
    "raw_chars": len(raw_text),
    "clean_chars": len(out_text),
    "controlled_tab_id": tab_id,
    "controlled_tab_id_mismatch": tab_mismatch,
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
