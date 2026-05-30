#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

usage() {
  cat <<'USAGE'
Usage:
  surf cursor-browser.submit --input REQUEST.md --output RESPONSE.md --view-id VIEW_ID [options]

Options:
  --input PATH              Prompt file to submit. Required.
  --output PATH             Clean response path. Required.
  --raw-output PATH         Raw response path. Default: <output>.raw.md
  --meta-output PATH        Proof metadata JSON. Default: <output>.meta.json
  --submitted-output PATH   Submitted prompt with sentinel injection.
  --sentinel auto|MARKER    Completion marker. Default: auto.
  --stable-polls N          Unchanged polls after sentinel. Default: 3.
  --timeout SECONDS         Browser wait timeout. Default: 900.
  --view-id ID              Cursor Browser viewId (from browser_tabs list). Required unless --url resolves uniquely.
  --url URL                 Resolve an open chatgpt.com tab by exact URL via cursor-browser-bridge tab list.
USAGE
}

input=""
output=""
raw_output=""
meta_output=""
submitted_output=""
sentinel="auto"
stable_polls=3
timeout_s=900
view_id=""
target_url=""

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
    --view-id) view_id="${2:-}"; shift 2 ;;
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

if [[ -z "$view_id" && -n "$target_url" ]]; then
  view_id="$(
    python3 "$SCRIPT_DIR/cursor_browser_client.py" resolve-url --url "$target_url" 2>/dev/null || true
  )"
fi

if [[ -z "$view_id" ]]; then
  echo "surf cursor-browser.submit requires --view-id (Cursor Browser viewId)." >&2
  echo "In Cursor, list tabs with browser_tabs or: surf cursor-browser.tab.list" >&2
  exit 2
fi

raw_output="${raw_output:-${output}.raw.md}"
meta_output="${meta_output:-${output}.meta.json}"
submitted_output="${submitted_output:-${output}.submitted.md}"
mkdir -p "$(dirname "$output")" "$(dirname "$raw_output")" "$(dirname "$meta_output")" "$(dirname "$submitted_output")"

export PYTHONPATH="${SCRIPT_DIR}${PYTHONPATH:+:$PYTHONPATH}"
python3 "$SCRIPT_DIR/cursor_browser_chatgpt.py" \
  --input "$input" \
  --output "$output" \
  --raw-output "$raw_output" \
  --meta-output "$meta_output" \
  --submitted-output "$submitted_output" \
  --view-id "$view_id" \
  --sentinel "$sentinel" \
  --timeout "$timeout_s" \
  --stable-polls "$stable_polls"
