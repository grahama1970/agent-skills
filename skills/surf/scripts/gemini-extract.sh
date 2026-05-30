#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_SH="${SURF_RUN_SH:-${SKILL_DIR}/run.sh}"

usage() {
  cat <<'EOF'
Usage:
  surf gemini.extract --tab-id ID --output RESPONSE.md [options]

Options:
  --tab-id ID             Existing controlled Gemini tab id. Required.
  --output PATH           Clean response path. Required.
  --raw-output PATH       Raw response path. Default: <output>.raw.md
  --meta-output PATH      Proof metadata JSON. Default: <output>.meta.json
  --sentinel MARKER       Completion marker expected in page text.
  --timeout SECONDS       Extraction timeout. Default: 12.
EOF
}

tab_id=""
output=""
raw_output=""
meta_output=""
sentinel=""
timeout_s=12

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tab-id) tab_id="${2:-}"; shift 2 ;;
    --output) output="${2:-}"; shift 2 ;;
    --raw-output) raw_output="${2:-}"; shift 2 ;;
    --meta-output) meta_output="${2:-}"; shift 2 ;;
    --sentinel) sentinel="${2:-}"; shift 2 ;;
    --timeout) timeout_s="${2:-}"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$tab_id" || -z "$output" ]]; then
  usage >&2
  exit 2
fi

requested_tab_id="$(printf '%s' "$tab_id" | tr -cd '0-9' | head -c 20 || true)"
if [[ -z "$requested_tab_id" ]]; then
  echo "Invalid --tab-id: $tab_id" >&2
  exit 2
fi

raw_output="${raw_output:-${output}.raw.md}"
meta_output="${meta_output:-${output}.meta.json}"
mkdir -p "$(dirname "$output")" "$(dirname "$raw_output")" "$(dirname "$meta_output")"

stderr_log="$(mktemp /tmp/surf-gemini-extract-stderr.XXXXXX.log)"
raw_tmp="$(mktemp /tmp/surf-gemini-extract-raw.XXXXXX.md)"
started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Use surf text to grab current page content
set +e
"$RUN_SH" text --tab-id "$requested_tab_id" > "$raw_tmp" 2> "$stderr_log"
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

raw_text="$(cat "$raw_output")"

if [[ -n "$sentinel" ]] && ! grep -Fq "$sentinel" <<< "$raw_text"; then
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
  echo "Extracted page text did not contain sentinel: $sentinel" >&2
  exit 4
fi

python3 - "$raw_output" "$output" "$sentinel" <<'PY'
import pathlib, sys
raw_path, out_path, sentinel = sys.argv[1:]
text = pathlib.Path(raw_path).read_text()
if sentinel:
    idx = text.rfind(sentinel)
    if idx == -1:
        raise SystemExit("sentinel missing")
    text = text[:idx].rstrip()
    # Extract last Gemini response
    marker = "Gemini said"
    last_idx = text.rfind(marker)
    if last_idx != -1:
        text = text[last_idx + len(marker):].strip()
pathlib.Path(out_path).write_text(text + "\n" if text and not text.endswith("\n") else text)
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
    "response_source": "page-text",
    "raw_contains_sentinel": bool(sentinel and sentinel in raw_text),
    "clean_contains_sentinel": bool(sentinel and sentinel in out_text),
    "raw_chars": len(raw_text),
    "clean_chars": len(out_text),
    "started_at": started,
    "finished_at": finished,
}, indent=2) + "\n")
PY

cat "$meta_output"
