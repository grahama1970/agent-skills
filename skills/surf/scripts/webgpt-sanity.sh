#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_SH="${SKILL_DIR}/run.sh"

usage() {
  cat <<'EOF'
Usage:
  surf webgpt.sanity [options]

Runs a real ChatGPT/WebGPT sentinel round trip using a compact but complex
technical-infographic prompt. Requires the surf browser extension and a signed-in
ChatGPT session.

Options:
  --output-dir PATH    Artifact directory. Default: /tmp/surf-webgpt-sanity-<timestamp>
  --timeout SECONDS    Browser wait timeout. Default: 900.
  --model MODEL        Optional ChatGPT model selector label.
  --tab-id ID          Use this exact Chrome tab as the controlled WebGPT tab.
  --url URL            Resolve an already-open ChatGPT tab by exact URL.
EOF
}

output_dir=""
timeout_s=900
model=""
tab_id=""
target_url=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir) output_dir="${2:-}"; shift 2 ;;
    --timeout) timeout_s="${2:-}"; shift 2 ;;
    --model) model="${2:-}"; shift 2 ;;
    --tab-id) tab_id="${2:-}"; shift 2 ;;
    --url) target_url="${2:-}"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$output_dir" ]]; then
  output_dir="/tmp/surf-webgpt-sanity-$(date -u +%Y%m%dT%H%M%SZ)"
fi
mkdir -p "$output_dir"

request="$output_dir/01_request.md"
response="$output_dir/02_response.md"
meta="$output_dir/02_response.meta.json"
bottom_screenshot="$output_dir/bottom-sentinel.png"

cat > "$request" <<'EOF'
Create a concise style-lock specification for a technical editorial infographic.

Subject: SPARTA / Embry OS Auto-Updating Evidence Workbench.

The infographic must explain:
- F-36 source corpora entering an evidence graph.
- Embry OS daemons and memory services supporting SPARTA.
- extract-entities and create-evidence-case turning a user question into typed evidence artifacts.
- Sparta Chat as the central operator workbench.
- auto-updating coverage, posture, supply-chain, sources, QRA review, and threat-matrix pages.
- human review, failure retention, course-correction candidates, and bounded memory upserts.

Return Markdown with these exact sections:

## Poster Title
## Numbered Bands
## Central Object
## Connector Logic
## Human Review Loop
## Dashboard-Theater Rejection Rules

Keep it under 650 words. Do not include HTML or SVG code. This is a real-world completion-sentinel test, so finish normally and obey the final marker instruction that the browser automation appends.
EOF

args=(webgpt.submit --input "$request" --output "$response" --meta-output "$meta" --timeout "$timeout_s" --stable-polls 3)
if [[ -n "$model" ]]; then
  args+=(--model "$model")
fi
if [[ -n "$tab_id" ]]; then
  args+=(--tab-id "$tab_id")
fi
if [[ -n "$target_url" ]]; then
  args+=(--url "$target_url")
fi

set +e
"$RUN_SH" "${args[@]}"
submit_status=$?
set -e

# Visual proof is part of the sanity check: after the response returns or fails,
# capture the visible bottom of the controlled ChatGPT tab only. Scanning other
# tabs is diagnostic and must never turn a run green.
sentinel=""
controlled_tab_id=""
if [[ -f "$meta" ]]; then
  read -r sentinel controlled_tab_id < <(python3 - "$meta" <<'PY'
import json, pathlib, sys
try:
    meta = json.loads(pathlib.Path(sys.argv[1]).read_text())
    print(meta.get("sentinel", ""), meta.get("controlled_tab_id", "") or "")
except Exception:
    print("", "")
PY
)
fi

diagnostic_found_sentinel_tab_id=""
if [[ -n "$controlled_tab_id" ]]; then
  tab_text="$("$RUN_SH" page.text --tab-id "$controlled_tab_id" 2>/dev/null || true)"
  if [[ -n "$sentinel" ]] && grep -Fq "$sentinel" <<<"$tab_text"; then
    printf '%s\n' "$tab_text" > "$output_dir/bottom-sentinel-page-text.txt"
  fi
fi
if [[ -n "$sentinel" && -z "$controlled_tab_id" ]]; then
  while IFS=$'\t' read -r tab_id _title url; do
    [[ "$url" == *"chatgpt.com"* ]] || continue
    tab_text="$("$RUN_SH" page.text --tab-id "$tab_id" 2>/dev/null || true)"
    if grep -Fq "$sentinel" <<<"$tab_text"; then
      diagnostic_found_sentinel_tab_id="$tab_id"
      printf '%s\n' "$tab_text" > "$output_dir/diagnostic-sentinel-page-text.txt"
      break
    fi
  done < <("$RUN_SH" tab.list 2>/dev/null || true)
fi

if [[ -n "$controlled_tab_id" ]]; then
  set +e
  "$RUN_SH" scroll.bottom --tab-id "$controlled_tab_id" --no-screenshot >/dev/null 2>"$output_dir/bottom-scroll.stderr.log"
  "$RUN_SH" js "(() => { window.scrollTo(0, document.body.scrollHeight); for (const el of Array.from(document.querySelectorAll('*'))) { try { if (el.scrollHeight > el.clientHeight) el.scrollTop = el.scrollHeight; } catch (_) {} } return 'scrolled'; })()" --tab-id "$controlled_tab_id" --no-screenshot >/dev/null 2>"$output_dir/bottom-js-scroll.stderr.log"
  "$RUN_SH" screenshot --tab-id "$controlled_tab_id" --output "$bottom_screenshot" --full >/dev/null 2>"$output_dir/bottom-screenshot.stderr.log"
  screenshot_status=$?
  set -e
else
  screenshot_status=97
fi

python3 - "$meta" "$response" "$request" "$output_dir" "$bottom_screenshot" "$screenshot_status" "$controlled_tab_id" "$diagnostic_found_sentinel_tab_id" "$output_dir/bottom-sentinel-page-text.txt" "$submit_status" <<'PY'
import json, pathlib, sys
import re
meta_path, response_path, request_path, output_dir, screenshot_path = map(pathlib.Path, sys.argv[1:6])
screenshot_status = int(sys.argv[6])
controlled_tab_id = sys.argv[7]
diagnostic_found_sentinel_tab_id = sys.argv[8]
page_text_path = pathlib.Path(sys.argv[9])
submit_status = int(sys.argv[10])
meta = json.loads(meta_path.read_text())
text = response_path.read_text()
required = [
    "Poster Title",
    "Numbered Bands",
    "Central Object",
    "Connector Logic",
    "Human Review Loop",
    "Dashboard-Theater Rejection Rules",
]
missing = [
    item for item in required
    if not re.search(rf"(?m)^\s*#{{0,6}}\s*{re.escape(item)}\s*$", text)
]
bad_text = []
for needle in ["Skip to content", "Chat history", "You said:", "Completion contract for browser automation:", "At the very end of your final answer, print exactly:"]:
    if needle in text:
        bad_text.append(needle)
sentinel_page_text = page_text_path.read_text() if page_text_path.exists() else ""
bad_page = []
for needle in ["Verify you are human", "Cloudflare", "Google Search"]:
    if needle.lower() in sentinel_page_text.lower():
        bad_page.append(needle)
same_tab_proof = bool(controlled_tab_id) and screenshot_status == 0 and page_text_path.exists()
status = "pass" if (
    submit_status == 0
    and meta.get("status") == "completed"
    and controlled_tab_id
    and same_tab_proof
    and not missing
    and not bad_text
    and not bad_page
    and meta.get("raw_contains_sentinel")
    and not meta.get("clean_contains_sentinel")
) else "fail"
result = {
    "status": status,
    "artifact_dir": str(output_dir),
    "request": str(request_path),
    "response": str(response_path),
    "meta": str(meta_path),
    "missing_sections": missing,
    "bad_clean_response_markers": bad_text,
    "bad_page_markers": bad_page,
    "submit_exit_code": submit_status,
    "meta_status": meta.get("status"),
    "controlled_tab_id": controlled_tab_id or None,
    "requested_tab_id": meta.get("requested_tab_id"),
    "requested_url": meta.get("requested_url"),
    "raw_contains_sentinel": meta.get("raw_contains_sentinel"),
    "clean_contains_sentinel": meta.get("clean_contains_sentinel"),
    "clean_chars": meta.get("clean_chars"),
    "bottom_screenshot": str(screenshot_path) if screenshot_path.exists() else None,
    "bottom_screenshot_status": screenshot_status,
    "screenshot_tab_id": controlled_tab_id if screenshot_status == 0 else None,
    "sentinel_page_text": str(page_text_path) if page_text_path.exists() else None,
    "sentinel_page_text_contains_sentinel": page_text_path.exists() and meta.get("sentinel", "") in page_text_path.read_text(),
    "diagnostic_found_sentinel_in_tab": diagnostic_found_sentinel_tab_id or None,
}
(output_dir / "sanity-result.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
if result["status"] != "pass":
    raise SystemExit(1)
PY
