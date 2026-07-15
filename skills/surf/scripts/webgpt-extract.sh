#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_SH="${SURF_RUN_SH:-${SKILL_DIR}/run.sh}"

usage() {
  cat <<'EOF'
Usage:
  surf webgpt.extract --tab-id ID --output RESPONSE.md [options]

Options:
  --tab-id ID             Existing controlled ChatGPT tab id. Required.
  --output PATH           Clean response path. Required.
  --raw-output PATH       Raw response path. Default: <output>.raw.md
  --meta-output PATH      Proof metadata JSON. Default: <output>.meta.json
  --sentinel MARKER       Completion marker expected in assistant DOM text.
  --timeout SECONDS       CDP extraction timeout. Default: 12.
  --wait                  Wait for the sentinel on the existing assistant turn.
  --stable-polls COUNT    Stable polls required with --wait. Default: 3.
EOF
}

tab_id=""
output=""
raw_output=""
meta_output=""
sentinel=""
timeout_s=12
wait_for_sentinel=0
stable_polls=3

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tab-id) tab_id="${2:-}"; shift 2 ;;
    --output) output="${2:-}"; shift 2 ;;
    --raw-output) raw_output="${2:-}"; shift 2 ;;
    --meta-output) meta_output="${2:-}"; shift 2 ;;
    --sentinel) sentinel="${2:-}"; shift 2 ;;
    --timeout) timeout_s="${2:-}"; shift 2 ;;
    --wait) wait_for_sentinel=1; shift ;;
    --stable-polls) stable_polls="${2:-}"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$tab_id" || -z "$output" ]]; then
  usage >&2
  exit 2
fi

if [[ ! "$tab_id" =~ ^[0-9]+$ ]]; then
  echo "Invalid --tab-id: $tab_id" >&2
  exit 2
fi
requested_tab_id="$tab_id"

raw_output="${raw_output:-${output}.raw.md}"
meta_output="${meta_output:-${output}.meta.json}"
mkdir -p "$(dirname "$output")" "$(dirname "$raw_output")" "$(dirname "$meta_output")"

stderr_log="$(mktemp /tmp/surf-webgpt-extract-stderr.XXXXXX.log)"
raw_tmp="$(mktemp /tmp/surf-webgpt-extract-raw.XXXXXX.md)"
started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

args=(chatgpt.extract --tab-id "$requested_tab_id" --timeout "$timeout_s")
if [[ -n "$sentinel" ]]; then
  args+=(--sentinel "$sentinel")
fi
if [[ "$wait_for_sentinel" -eq 1 ]]; then
  args+=(--wait --stable-polls "$stable_polls" --no-activate)
fi

set +e
"$RUN_SH" "${args[@]}" > "$raw_tmp" 2> "$stderr_log"
status=$?
set -e
finished_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

cp "$raw_tmp" "$raw_output"

if [[ $status -ne 0 ]]; then
  python3 - "$meta_output" "$output" "$raw_output" "$stderr_log" "$sentinel" "$started_at" "$finished_at" "$status" "$requested_tab_id" <<'PY'
import json, pathlib, sys
meta, out, raw, err, sentinel, started, finished, status, tab_id = sys.argv[1:]
pathlib.Path(meta).write_text(json.dumps({
    "status": "failed",
    "exit_code": int(status),
    "output": out,
    "raw_output": raw,
    "stderr_log": err,
    "sentinel": sentinel or None,
    "requested_tab_id": tab_id,
    "controlled_tab_id": tab_id,
    "started_at": started,
    "finished_at": finished,
}, indent=2) + "\n")
PY
  cat "$stderr_log" >&2
  exit "$status"
fi

if [[ -n "$sentinel" ]] && ! grep -Fq "$sentinel" "$raw_output"; then
  python3 - "$meta_output" "$output" "$raw_output" "$stderr_log" "$sentinel" "$started_at" "$finished_at" "$requested_tab_id" <<'PY'
import json, pathlib, sys
meta, out, raw, err, sentinel, started, finished, tab_id = sys.argv[1:]
raw_text = pathlib.Path(raw).read_text() if pathlib.Path(raw).exists() else ""
pathlib.Path(meta).write_text(json.dumps({
    "status": "missing_sentinel",
    "output": out,
    "raw_output": raw,
    "stderr_log": err,
    "sentinel": sentinel,
    "requested_tab_id": tab_id,
    "controlled_tab_id": tab_id,
    "raw_contains_sentinel": sentinel in raw_text,
    "raw_chars": len(raw_text),
    "started_at": started,
    "finished_at": finished,
}, indent=2) + "\n")
PY
  echo "Extracted assistant response did not contain sentinel: $sentinel" >&2
  exit 4
fi

python3 - "$raw_output" "$output" "$sentinel" <<'PY'
import pathlib, sys
raw_path, out_path, sentinel = sys.argv[1:]
text = pathlib.Path(raw_path).read_text()
if sentinel:
    idx = text.rfind(sentinel)
    if idx == -1:
        raise SystemExit("sentinel missing from assistant response")
    after = text[idx + len(sentinel):].strip()
    if after:
        raise SystemExit("assistant response contains text after terminal sentinel")
    text = text[:idx].rstrip() + "\n"
pathlib.Path(out_path).write_text(text if text.endswith("\n") else text + "\n")
PY

python3 - "$meta_output" "$output" "$raw_output" "$stderr_log" "$sentinel" "$started_at" "$finished_at" "$requested_tab_id" <<'PY'
import json, pathlib, sys
meta, out, raw, err, sentinel, started, finished, tab_id = sys.argv[1:]
raw_text = pathlib.Path(raw).read_text()
out_text = pathlib.Path(out).read_text()
pathlib.Path(meta).write_text(json.dumps({
    "status": "completed",
    "output": out,
    "raw_output": raw,
    "stderr_log": err,
    "sentinel": sentinel or None,
    "requested_tab_id": tab_id,
    "controlled_tab_id": tab_id,
    "response_source": "assistant-dom",
    "raw_contains_sentinel": bool(sentinel and sentinel in raw_text),
    "clean_contains_sentinel": bool(sentinel and sentinel in out_text),
    "raw_chars": len(raw_text),
    "clean_chars": len(out_text),
    "started_at": started,
    "finished_at": finished,
}, indent=2) + "\n")
PY

cat "$meta_output"
