#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_SH="${SURF_RUN_SH:-${SKILL_DIR}/run.sh}"

usage() {
  cat <<'EOF'
Usage:
  surf webgpt.download --match PATTERN [--tab-id ID] [--output PATH] [--timeout SECONDS]

Download a file attachment from a ChatGPT conversation by finding and clicking
the download button whose text matches PATTERN, then waiting for the browser
download to land in ~/Downloads.

Options:
  --match PATTERN       Text pattern to match the download button (e.g. "solution.zip").
                        Required.
  --tab-id ID           Chrome tab id for the ChatGPT conversation.
  --output PATH         Destination path for the downloaded file. If omitted,
                        prints the downloaded file path to stdout.
  --output-dir DIR      Destination directory (copies file with original name).
  --downloads-dir PATH  Browser downloads directory. Default: ~/Downloads.
  --poll-interval SECONDS  How often to check for new files. Default: 2.
  --timeout SECONDS     Max wait for download to complete. Default: 60.
  --help|-h             Show this message.
EOF
}

match=""
tab_id=""
output=""
output_dir=""
downloads_dir=""
poll_interval=2
timeout_s=60

while [[ $# -gt 0 ]]; do
  case "$1" in
    --match) match="${2:-}"; shift 2 ;;
    --output) output="${2:-}"; shift 2 ;;
    --output-dir) output_dir="${2:-}"; shift 2 ;;
    --downloads-dir) downloads_dir="${2:-}"; shift 2 ;;
    --tab-id) tab_id="${2:-}"; shift 2 ;;
    --poll-interval) poll_interval="${2:-}"; shift 2 ;;
    --timeout) timeout_s="${2:-}"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$match" ]]; then
  echo "Error: --match is required" >&2
  usage >&2
  exit 2
fi

downloads_dir="${downloads_dir:-$HOME/Downloads}"
tab_args=()
if [[ -n "$tab_id" ]]; then
  tab_args=(--tab-id "$tab_id")
fi

# 1. Find download buttons matching the pattern via JS
echo "Searching for download button matching: $match" >&2
find_js="return JSON.stringify(Array.from(document.querySelectorAll('a,button,[role=button]')).filter(e => { const t = (e.textContent || e.getAttribute('aria-label') || '').toLowerCase(); return t.includes('${match,,}'); }).map(e => ({ text: e.textContent?.trim().slice(0, 120), aria: e.getAttribute('aria-label') || '', href: e.href || e.getAttribute('href') || '', download: e.getAttribute('download') || '' })), null, 2)"

buttons_json="$("$RUN_SH" js "$find_js" "${tab_args[@]}" 2>/dev/null || true)"

if [[ -z "$buttons_json" || "$buttons_json" == "[]" || "$buttons_json" == "[]\n" ]]; then
  echo "Error: No download button found matching pattern: $match" >&2
  echo "  Try activating the ChatGPT tab first with: surf tab.activate <id>" >&2
  exit 3
fi

# 2. Pick the first match and click it
button_text="$(echo "$buttons_json" | python3 -c "import json,sys; data=json.load(sys.stdin); print(data[0].get('text') or data[0].get('aria') or '')" 2>/dev/null || true)"

if [[ -z "$button_text" ]]; then
  echo "Error: Could not parse button text from match" >&2
  echo "$buttons_json" >&2
  exit 3
fi

echo "Clicking: $button_text" >&2

# Snapshot downloads dir before click
before_files=$(ls -1 "$downloads_dir" 2>/dev/null || true)

click_out=$("$RUN_SH" click "$button_text" "${tab_args[@]}" 2>&1) || {
  echo "Error: Failed to click download button: $click_out" >&2
  # Try clicking the raw element if text click fails
  echo "  The button may need a different click method (use 'surf click eN' with the element ref)" >&2
  exit 4
}

echo "Waiting for download to appear in: $downloads_dir" >&2

# 3. Poll for new files matching the pattern
start_time=$SECONDS
downloaded_file=""
while (( SECONDS - start_time < timeout_s )); do
  sleep "$poll_interval"
  after_files=$(ls -1 "$downloads_dir" 2>/dev/null || true)
  new_files=$(comm -13 <(echo "$before_files") <(echo "$after_files") 2>/dev/null || echo "$after_files" | while IFS= read -r f; do echo "$before_files" | grep -qFx "$f" || echo "$f"; done)

  if [[ -n "$new_files" ]]; then
    while IFS= read -r f; do
      candidate="$downloads_dir/$f"
      if [[ -f "$candidate" ]]; then
        # Check file age — wait for download to finish (file not modified for 1s)
        age=0
        for _ in 1 2 3 4 5; do
          prev_size=$(stat -c%s "$candidate" 2>/dev/null || echo 0)
          sleep 0.5
          curr_size=$(stat -c%s "$candidate" 2>/dev/null || echo 0)
          if [[ "$prev_size" == "$curr_size" && "$curr_size" -gt 0 ]]; then
            age=$((age + 1))
            if [[ "$age" -ge 2 ]]; then
              downloaded_file="$candidate"
              break 3
            fi
          else
            age=0
          fi
        done
      fi
    done <<< "$new_files"
  fi
done

if [[ -z "$downloaded_file" ]]; then
  echo "Error: Download did not complete within ${timeout_s}s" >&2
  echo "  Check $downloads_dir for the file manually" >&2
  exit 5
fi

echo "Downloaded: $downloaded_file" >&2

if [[ -n "$output" ]]; then
  mkdir -p "$(dirname "$output")"
  cp "$downloaded_file" "$output"
  echo "Copied to: $output" >&2
elif [[ -n "$output_dir" ]]; then
  mkdir -p "$output_dir"
  _dl_basename="$(basename "$downloaded_file")"
  cp "$downloaded_file" "$output_dir/$_dl_basename"
  echo "$output_dir/$_dl_basename"
else
  echo "$downloaded_file"
fi
