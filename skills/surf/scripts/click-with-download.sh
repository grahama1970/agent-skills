#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_SH="${SURF_RUN_SH:-${SKILL_DIR}/run.sh}"
DOWNLOAD_SH="${SURF_DOWNLOAD_SH:-${SCRIPT_DIR}/webgpt-download.sh}"

click_args=()
download_output=""
downloads_dir="${HOME}/Downloads"
timeout_s=60
expect_download=0
tab_id=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --expect-download)
      expect_download=1
      shift
      ;;
    --download-output)
      download_output="${2:-}"
      expect_download=1
      shift 2
      ;;
    --download-timeout)
      timeout_s="${2:-}"
      shift 2
      ;;
    --downloads-dir)
      downloads_dir="${2:-}"
      shift 2
      ;;
    --tab-id)
      tab_id="${2:-}"
      click_args+=("$1" "$tab_id")
      shift 2
      ;;
    *)
      click_args+=("$1")
      shift
      ;;
  esac
done

if [[ "$expect_download" -ne 1 ]]; then
  echo "Error: click download wrapper requires --expect-download or --download-output" >&2
  exit 2
fi
if [[ ${#click_args[@]} -eq 0 ]]; then
  echo "Error: click target is required" >&2
  exit 2
fi
if [[ -n "$download_output" && "$download_output" != /* ]]; then
  download_output="$(pwd)/$download_output"
fi

before_manifest="$(mktemp)"
trap 'rm -f "$before_manifest"' EXIT
ls -1 "$downloads_dir" 2>/dev/null | sort > "$before_manifest" || true

if [[ -n "$tab_id" ]]; then
  busy_json="$("$RUN_SH" js "return JSON.stringify({chatgpt:location.hostname==='chatgpt.com',busy:Array.from(document.querySelectorAll('button')).some(e=>/stop (generating|answering|response)/i.test([e.getAttribute('aria-label'),e.textContent].filter(Boolean).join(' ')))})" --tab-id "$tab_id" 2>/dev/null || true)"
  busy="$(printf '%s' "$busy_json" | python3 -c 'import json,sys; value=json.load(sys.stdin); value=json.loads(value) if isinstance(value,str) else value; print("1" if value.get("chatgpt") and value.get("busy") else "0")' 2>/dev/null || printf '0')"
  if [[ "$busy" == "1" ]]; then
    echo "Error: ChatGPT tab is generating; download click blocked until the page is idle" >&2
    exit 6
  fi
fi

"$RUN_SH" click "${click_args[@]}"

download_args=(
  --after-click
  --before-manifest "$before_manifest"
  --downloads-dir "$downloads_dir"
  --timeout "$timeout_s"
)
if [[ -n "$tab_id" ]]; then
  download_args+=(--tab-id "$tab_id")
fi
if [[ -n "$download_output" ]]; then
  download_args+=(--output "$download_output")
fi
"$DOWNLOAD_SH" "${download_args[@]}"
