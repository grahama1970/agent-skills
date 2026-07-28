#!/usr/bin/env bash
# Sentinel-proven DeepSeek submit for Ask/Tau browser lanes (agent-skills#1067).
#
# Expert is the default tier: the client selects it and re-reads the app's own
# mode banner, so a lane never reports an Instant-tier answer as webdeepseek.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_SH="${SURF_RUN_SH:-${SKILL_DIR}/run.sh}"

usage() {
  cat <<'EOF'
Usage:
  surf deepseek.submit --input REQUEST.md --output RESPONSE.md [options]

Options:
  --input PATH              Prompt file to submit. Required.
  --output PATH             Clean response path. Required.
  --raw-output PATH         Raw response path. Default: <output>.raw.md
  --meta-output PATH        Proof metadata JSON. Default: <output>.meta.json
  --submitted-output PATH   Submitted prompt with sentinel injection.
  --sentinel auto|MARKER    Completion marker. Default: auto.
  --mode MODE               Instant|Expert|Vision. Default: Expert.
  --timeout SECONDS         Browser wait timeout. Default: 900.
  --stable-polls N          Unchanged polls after the sentinel. Default: 2.
  --tab-id ID               Use this exact live DeepSeek tab.
  --url URL                 Conversation URL recorded in the receipt.
  --keep-tab                Leave the controlled tab open.
  --no-activate             Do not raise the tab (mode selection still needs
                            a foreground moment; see SKILL.md).
  --lock-timeout SECONDS    Accepted for interface parity; forwarded to surf.
  --attach-file PATH        Rejected: DeepSeek attachments are unsupported.
EOF
}

input=""; output=""; raw_output=""; meta_output=""; submitted_output=""
sentinel="auto"; mode="Expert"; timeout_s=900; stable_polls=2
tab_id=""; target_url=""; keep_tab=0; no_activate=0; lock_timeout=""
attach_files=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --input) input="${2:-}"; shift 2 ;;
    --output) output="${2:-}"; shift 2 ;;
    --raw-output) raw_output="${2:-}"; shift 2 ;;
    --meta-output) meta_output="${2:-}"; shift 2 ;;
    --submitted-output) submitted_output="${2:-}"; shift 2 ;;
    --sentinel) sentinel="${2:-}"; shift 2 ;;
    --mode) mode="${2:-}"; shift 2 ;;
    --timeout) timeout_s="${2:-}"; shift 2 ;;
    --stable-polls) stable_polls="${2:-}"; shift 2 ;;
    --tab-id) tab_id="${2:-}"; shift 2 ;;
    --url) target_url="${2:-}"; shift 2 ;;
    --keep-tab) keep_tab=1; shift ;;
    --no-activate) no_activate=1; shift ;;
    --lock-timeout) lock_timeout="${2:-}"; shift 2 ;;
    --attach-file) attach_files+=("${2:-}"); shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$input" || -z "$output" ]]; then
  echo "Error: --input and --output are required." >&2
  exit 2
fi
if [[ ! -f "$input" ]]; then
  echo "Error: input file not found: $input" >&2
  exit 2
fi

raw_output="${raw_output:-${output}.raw.md}"
meta_output="${meta_output:-${output}.meta.json}"
submitted_output="${submitted_output:-${output}.submitted.md}"
mkdir -p "$(dirname "$output")" "$(dirname "$raw_output")" "$(dirname "$meta_output")" "$(dirname "$submitted_output")"

started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

write_meta() {
  python3 - "$meta_output" "$input" "$submitted_output" "$output" "$raw_output" "$sentinel" \
    "$started_at" "$1" "$2" "$3" "$tab_id" "$target_url" "$mode" "$4" <<'PY'
import json, pathlib, sys

(meta, inp, submitted, out, raw, sentinel, started, finished, status, failure,
 tab_id, url, mode, stderr_excerpt) = sys.argv[1:]
raw_text = ""
raw_path = pathlib.Path(raw)
if raw_path.is_file():
    raw_text = raw_path.read_text(encoding="utf-8", errors="replace")
has_sentinel = bool(sentinel) and sentinel in raw_text
proof = {
    "completed": "response_proven" if has_sentinel else "submitted_no_response_proof",
    "failed": "delivery_not_proven",
}[status if status in ("completed", "failed") else "failed"]
pathlib.Path(meta).write_text(json.dumps({
    "status": status,
    "failure": failure or None,
    "proof_status": proof,
    "input": inp,
    "submitted_output": submitted,
    "output": out,
    "raw_output": raw,
    "sentinel": sentinel,
    "raw_contains_sentinel": has_sentinel,
    "raw_chars": len(raw_text),
    "requested_tab_id": tab_id or None,
    "controlled_tab_id": tab_id or None,
    "requested_url": url or None,
    "mode": mode,
    "started_at": started,
    "finished_at": finished,
    "submitted_to_deepseek": status == "completed",
    "stderr_excerpt": stderr_excerpt[:2000],
    "attachment_supported": False,
}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

if [[ ${#attach_files[@]} -gt 0 ]]; then
  finished_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  write_meta "$finished_at" "failed" "deepseek_attachment_unsupported" \
    "DeepSeek submits cannot carry attachments; UPLOAD_FILE_TO_TAB accepts only gemini, chatgpt, and grok."
  echo "deepseek.submit blocked: attachments are not supported for this provider." >&2
  exit 2
fi

if [[ "$sentinel" == "auto" ]]; then
  sentinel="<<<DEEPSEEK_DONE:$(date -u +%Y%m%dT%H%M%SZ):$(head -c 8 /dev/urandom | od -An -tx1 | tr -d ' \n')>>>"
fi

{
  cat "$input"
  printf '\n\nCompletion contract for browser automation:\n'
  printf 'At the very end of your final answer, print exactly:\n\n%s\n\n' "$sentinel"
  printf 'Do not print anything after that marker.\n'
} > "$submitted_output"

args=(deepseek --query "$(cat "$submitted_output")" --sentinel "$sentinel"
      --timeout "$timeout_s" --stable-polls "$stable_polls" --mode "$mode")
[[ -n "$tab_id" ]] && args+=(--target-tab-id "$tab_id")
[[ "$keep_tab" -eq 1 ]] && args+=(--keep-tab)
[[ "$no_activate" -eq 1 ]] && args+=(--no-activate)

stderr_log="$(mktemp -t surf-deepseek-submit-stderr.XXXXXX.log)"
raw_tmp="$(mktemp -t surf-deepseek-submit-raw.XXXXXX)"
set +e
"$RUN_SH" "${args[@]}" > "$raw_tmp" 2> "$stderr_log"
rc=$?
set -e
finished_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

python3 - "$raw_tmp" "$raw_output" "$output" "$sentinel" <<'PY'
import json, pathlib, sys
raw_tmp, raw_out, clean_out, sentinel = sys.argv[1:]
text = pathlib.Path(raw_tmp).read_text(encoding="utf-8", errors="replace").strip()
if text.startswith('"') and text.endswith('"'):
    try:
        text = json.loads(text)
    except json.JSONDecodeError:
        pass
pathlib.Path(raw_out).write_text(text + "\n", encoding="utf-8")
clean = text.split(sentinel)[0].rstrip() if sentinel and sentinel in text else text
pathlib.Path(clean_out).write_text(clean + "\n", encoding="utf-8")
PY

stderr_excerpt="$(tail -c 2000 "$stderr_log" || true)"
if [[ $rc -eq 0 ]]; then
  write_meta "$finished_at" "completed" "" "$stderr_excerpt"
else
  write_meta "$finished_at" "failed" "submit_failed" "$stderr_excerpt"
  cat "$stderr_log" >&2
fi
exit $rc
