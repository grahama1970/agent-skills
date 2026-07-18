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
  --after-click         Complete a download after another command already
                        clicked the source control.
  --before-manifest PATH  Pre-click sorted download-directory listing.
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
after_click=0
before_manifest=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --match) match="${2:-}"; shift 2 ;;
    --output) output="${2:-}"; shift 2 ;;
    --output-dir) output_dir="${2:-}"; shift 2 ;;
    --downloads-dir) downloads_dir="${2:-}"; shift 2 ;;
    --tab-id) tab_id="${2:-}"; shift 2 ;;
    --poll-interval) poll_interval="${2:-}"; shift 2 ;;
    --timeout) timeout_s="${2:-}"; shift 2 ;;
    --after-click) after_click=1; shift ;;
    --before-manifest) before_manifest="${2:-}"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$match" && "$after_click" -ne 1 ]]; then
  echo "Error: --match is required" >&2
  usage >&2
  exit 2
fi

downloads_dir="${downloads_dir:-$HOME/Downloads}"
tab_args=()
if [[ -n "$tab_id" ]]; then
  tab_args=(--tab-id "$tab_id")
fi

expected_basename=""
if [[ -n "$match" && "$match" != .* && "$match" != *"*"* && "$match" != *"?"* ]]; then
  expected_basename="$(basename -- "$match")"
fi

# Snapshot downloads before the source click. Generic click passes its own
# pre-click manifest because the click has already happened when this starts.
if [[ -n "$before_manifest" && -f "$before_manifest" ]]; then
  before_files="$(cat "$before_manifest")"
else
  before_files=$(ls -1 "$downloads_dir" 2>/dev/null | sort || true)
fi

if [[ "$after_click" -ne 1 ]]; then
  # Encode user input before embedding it in JavaScript.
  match_json="$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$match")"

# 1. Find artifact controls matching the pattern via JS
echo "Searching for download button matching: $match" >&2
find_js="
const match = ${match_json}.toLowerCase();
return JSON.stringify(Array.from(document.querySelectorAll('a,button,[role=button]')).filter(e => {
  const text = [e.textContent, e.getAttribute('aria-label'), e.getAttribute('title'),
    e.getAttribute('download'), e.getAttribute('href')].filter(Boolean).join(' ').toLowerCase();
  return text.includes(match);
}).map(e => ({
  text: e.textContent?.trim().slice(0, 120),
  aria: e.getAttribute('aria-label') || '',
  title: e.getAttribute('title') || '',
  href: e.href || e.getAttribute('href') || '',
  download: e.getAttribute('download') || '',
  role: e.getAttribute('role') || '',
  tag: e.tagName
})), null, 2)"

buttons_json="$("$RUN_SH" js "$find_js" "${tab_args[@]}" 2>/dev/null || true)"

  if [[ -z "$buttons_json" || "$buttons_json" == "[]" || "$buttons_json" == "[]\n" ]]; then
  echo "Error: No download button found matching pattern: $match" >&2
  echo "  Try activating the ChatGPT tab first with: surf tab.activate <id>" >&2
  exit 3
  fi

# 2. Pick the first match and click by aria-label CSS selector.
# ChatGPT download buttons have empty textContent — only aria-label has the
# filename. surf click with a string does text matching, so use the CSS
# attribute selector instead.
button_aria="$(echo "$buttons_json" | python3 -c "import json,sys; data=json.load(sys.stdin); data=json.loads(data) if isinstance(data, str) else data; print(data[0].get('aria') or data[0].get('text') or '')" 2>/dev/null || true)"

  if [[ -z "$button_aria" ]]; then
  echo "Error: Could not parse button aria-label from match" >&2
  echo "$buttons_json" >&2
  exit 3
  fi

echo "Clicking: $button_aria" >&2

# Click via JS: find the first button whose aria-label or text matches the
# pattern, then click it programmatically. This works regardless of whether
# textContent is empty (ChatGPT download buttons use aria-label only).
click_js="
const match = ${match_json}.toLowerCase();
const btn = Array.from(document.querySelectorAll('a,button,[role=button]')).find(e => {
  const label = [e.getAttribute('aria-label'), e.getAttribute('title'), e.textContent,
    e.getAttribute('download'), e.getAttribute('href')].filter(Boolean).join(' ').toLowerCase();
  return label.includes(match);
});
if (btn) { btn.click(); return 'clicked'; } else { return 'no-match'; }
"
click_out=$("$RUN_SH" js "$click_js" "${tab_args[@]}" 2>/dev/null || true)
if [[ "$click_out" == \"*\" ]]; then
  click_out="${click_out#\"}"
  click_out="${click_out%\"}"
fi

  if [[ "$click_out" != "clicked" ]]; then
  echo "Error: Could not find or click download button" >&2
  echo "  Try: surf click 'button' (find ref via surf read --tab-id \$TAB)" >&2
  exit 4
  fi
fi

# Some attachments open ChatGPT's artifact viewer first. Its upper-right
# Download icon may be in a side panel rather than a role=dialog and may expose
# only title/data-testid metadata. Poll briefly for that second-stage toolbar.
viewer_download_js="
const visible = e => {
  const r = e.getBoundingClientRect();
  const s = getComputedStyle(e);
  return r.width > 0 && r.height > 0 && r.bottom > 0 && r.right > 0 &&
    r.top < innerHeight && r.left < innerWidth &&
    s.visibility !== 'hidden' && s.display !== 'none';
};
const candidates = Array.from(document.querySelectorAll('a,button,[role=button]'))
  .filter(visible)
  .map(e => {
    const r = e.getBoundingClientRect();
    const label = [e.getAttribute('aria-label'), e.getAttribute('title'),
      e.getAttribute('data-testid'), e.getAttribute('download'), e.textContent]
      .filter(Boolean).join(' ').trim();
    const inDialog = Boolean(e.closest('[role=dialog],[aria-modal=true]'));
    const inMessage = Boolean(e.closest('[data-message-author-role]'));
    const topRight = r.left > innerWidth * 0.5 && r.top < innerHeight * 0.35;
    let score = 0;
    if (/\\bdownload\\b/i.test(label)) score += 100;
    if (inDialog) score += 40;
    if (!inMessage) score += 30;
    if (topRight) score += 20;
    return { e, label, score, inMessage, topRight };
  })
  .filter(x => x.score >= 130 && !x.inMessage)
  .sort((a, b) => b.score - a.score);
const download = candidates[0];
if (download) {
  download.e.click();
  return JSON.stringify({status:'clicked', label:download.label, topRight:download.topRight});
}
return JSON.stringify({status:'not-found'});
"
for _viewer_attempt in 1 2 3 4 5 6 7 8 9 10; do
  viewer_download_out=$("$RUN_SH" js "$viewer_download_js" "${tab_args[@]}" 2>/dev/null || true)
  viewer_status=$(printf '%s' "$viewer_download_out" | python3 -c 'import json,sys; value=json.load(sys.stdin); value=json.loads(value) if isinstance(value,str) else value; print(value.get("status", ""))' 2>/dev/null || true)
  if [[ "$viewer_status" == "clicked" ]]; then
    echo "Clicked artifact viewer Download control" >&2
    break
  fi
  sleep 0.5
done

echo "Waiting for download to appear in: $downloads_dir" >&2

# 3. Poll for new files matching the pattern
start_time=$SECONDS
downloaded_file=""
while (( SECONDS - start_time < timeout_s )); do
  sleep "$poll_interval"
  after_files=$(ls -1 "$downloads_dir" 2>/dev/null | sort || true)
  new_files=$(comm -13 <(echo "$before_files") <(echo "$after_files") 2>/dev/null || echo "$after_files" | while IFS= read -r f; do echo "$before_files" | grep -qFx "$f" || echo "$f"; done)

  if [[ -n "$new_files" ]]; then
    while IFS= read -r f; do
      if [[ -n "$expected_basename" ]]; then
        if [[ "$f" != "$expected_basename" ]]; then
          echo "Ignoring unrelated download candidate: $f (expected: $expected_basename)" >&2
          continue
        fi
      elif [[ -n "$match" && "$f" != *"$match"* ]]; then
        echo "Ignoring unrelated download candidate: $f (pattern: $match)" >&2
        continue
      fi
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
  if [[ -n "$expected_basename" ]]; then
    echo "Error: Exact download '$expected_basename' did not complete within ${timeout_s}s" >&2
  else
    echo "Error: Download did not complete within ${timeout_s}s" >&2
  fi
  echo "  Check $downloads_dir for the file manually" >&2
  exit 5
fi

if [[ -n "$expected_basename" && "$(basename -- "$downloaded_file")" != "$expected_basename" ]]; then
  echo "Error: Download basename mismatch: expected '$expected_basename', got '$(basename -- "$downloaded_file")'" >&2
  exit 6
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
