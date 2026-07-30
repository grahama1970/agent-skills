#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_SH="${SURF_RUN_SH:-${SKILL_DIR}/run.sh}"

usage() {
  cat <<'EOF'
Usage:
  surf grok.extract --tab-id ID --output RESPONSE.md [options]

Options:
  --tab-id ID             Existing controlled Grok/X tab id. Required.
  --output PATH           Clean response path. Required.
  --raw-output PATH       Raw provider-turn path. Default: <output>.raw.md
  --meta-output PATH      Proof metadata JSON. Default: <output>.meta.json
  --sentinel MARKER       Completion marker expected in the Grok assistant turn.
  --timeout SECONDS       Extraction timeout. Default: 12.
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
    --no-activate) shift ;; # accepted for parity; exact --tab-id keeps target stable
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

stderr_log="$(mktemp /tmp/surf-grok-extract-stderr.XXXXXX.log)"
snapshot_tmp="$(mktemp /tmp/surf-grok-extract-snapshot.XXXXXX.json)"
state_tmp="$(mktemp /tmp/surf-grok-extract-state.XXXXXX.json)"
raw_tmp="$(mktemp /tmp/surf-grok-extract-raw.XXXXXX.md)"
js_file="$(mktemp /tmp/surf-grok-extract-js.XXXXXX.js)"
started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

python3 - "$js_file" "$sentinel" <<'PY'
import json
import pathlib
import sys

path, sentinel = sys.argv[1:]
pathlib.Path(path).write_text(
    f"""
(() => {{
  const sentinel = {json.dumps(sentinel)};
  const isVisible = (el) => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
  const norm = (text) => String(text || '').replace(/\\u00a0/g, ' ').trim();
  const lowerBody = norm(document.body && document.body.innerText).toLowerCase();
  const providerRateLimited = [
    'limit is gone',
    'upgrade to supergrok',
    'rate limit',
    'usage limit',
    'message limit',
    'too many requests'
  ].some((needle) => lowerBody.includes(needle));
  const providerCapacityBusy = [
    'system is currently busy',
    'temporarily busy',
    'high demand',
    'under heavy usage',
    'capacity is busy'
  ].some((needle) => lowerBody.includes(needle));
  const selectors = [
    'article',
    '[data-testid*="message"]',
    '[data-testid*="response"]',
    '[data-testid*="conversation"]',
    '[role="main"] article',
    'main article',
    'main'
  ];
  const seen = new Set();
  const candidates = [];
  for (const selector of selectors) {{
    for (const el of Array.from(document.querySelectorAll(selector))) {{
      if (!el || seen.has(el)) continue;
      seen.add(el);
      if (!isVisible(el) && el.tagName !== 'MAIN') continue;
      if (el.querySelector('textarea,[contenteditable="true"][role="textbox"],[data-testid="grokComposerInput"]')) continue;
      const text = norm(el.innerText || el.textContent);
      if (!text) continue;
      const testId = el.getAttribute('data-testid') || '';
      const role = el.getAttribute('role') || '';
      let score = 0;
      if (sentinel && text.includes(sentinel)) score += 2000;
      if (el.tagName === 'ARTICLE') score += 1000;
      if (/assistant|response|message/i.test(testId)) score += 700;
      if (/conversation/i.test(testId)) score += 300;
      if (el.tagName === 'MAIN' || role === 'main') score += 50;
      score += Math.min(text.length, 2000) / 1000;
      candidates.push({{
        tag: el.tagName,
        role,
        testId,
        text,
        textChars: text.length,
        containsSentinel: !!(sentinel && text.includes(sentinel)),
        score
      }});
    }}
  }}
  const sentinelCandidates = sentinel ? candidates.filter((c) => c.containsSentinel) : [];
  const selected = (sentinel ? sentinelCandidates : candidates)
    .sort((a, b) => a.score - b.score)
    .at(-1) || null;
  return JSON.stringify({{
    provider: 'grok',
    providerSpecificExtractor: true,
    genericPageTextFallbackUsed: false,
    url: location.href,
    title: document.title,
    bodyContainsSentinel: !!(sentinel && norm(document.body && document.body.innerText).includes(sentinel)),
    providerRateLimited,
    providerCapacityBusy,
    selected,
    candidateCount: candidates.length,
    sentinelCandidateCount: sentinelCandidates.length,
    candidates: candidates.map((c) => ({{
      tag: c.tag,
      role: c.role,
      testId: c.testId,
      textChars: c.textChars,
      containsSentinel: c.containsSentinel,
      score: c.score
    }})).slice(-20)
  }});
}})()
""".strip()
    + "\n",
    encoding="utf-8",
)
PY

write_failure_meta() {
  local status="$1"
  local failure="$2"
  local proof_status="$3"
  local exit_code="$4"
  local finished_at
  finished_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  python3 - "$meta_output" "$output" "$raw_output" "$stderr_log" "$snapshot_tmp" "$sentinel" "$started_at" "$finished_at" "$requested_tab_id" "$status" "$failure" "$proof_status" "$exit_code" <<'PY'
import json
import pathlib
import sys

meta, out, raw, err, snapshot, sentinel, started, finished, tab_id, status, failure, proof_status, exit_code = sys.argv[1:]
snapshot_payload = {}
snapshot_path = pathlib.Path(snapshot)
if snapshot_path.is_file():
    try:
        snapshot_payload = json.loads(snapshot_path.read_text(encoding="utf-8", errors="replace") or "{}")
        if isinstance(snapshot_payload, str):
            snapshot_payload = json.loads(snapshot_payload or "{}")
        if not isinstance(snapshot_payload, dict):
            snapshot_payload = {"unexpected_payload_type": type(snapshot_payload).__name__}
    except json.JSONDecodeError:
        snapshot_payload = {"parse_error": True}
raw_text = pathlib.Path(raw).read_text(encoding="utf-8", errors="replace") if pathlib.Path(raw).is_file() else ""
pathlib.Path(meta).write_text(json.dumps({
    "status": status,
    "exit_code": int(exit_code),
    "failure": failure,
    "proof_status": proof_status,
    "provider": "grok",
    "provider_specific_extractor": True,
    "generic_page_text_fallback_used": False,
    "output": out,
    "raw_output": raw,
    "stderr_log": err,
    "snapshot_path": snapshot,
    "sentinel": sentinel or None,
    "requested_tab_id": tab_id,
    "controlled_tab_id": tab_id,
    "response_source": "grok-provider-dom",
    "raw_contains_sentinel": bool(sentinel and sentinel in raw_text),
    "raw_chars": len(raw_text),
    "selected_root": (snapshot_payload.get("selected") or {}),
    "body_contains_sentinel": snapshot_payload.get("bodyContainsSentinel"),
    "provider_rate_limited": snapshot_payload.get("providerRateLimited") is True,
    "provider_capacity_busy": snapshot_payload.get("providerCapacityBusy") is True,
    "candidate_count": snapshot_payload.get("candidateCount"),
    "sentinel_candidate_count": snapshot_payload.get("sentinelCandidateCount"),
    "started_at": started,
    "finished_at": finished,
}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

extract_once() {
  set +e
  "$RUN_SH" js --file "$js_file" --tab-id "$requested_tab_id" > "$snapshot_tmp" 2> "$stderr_log"
  local status=$?
  set -e
  if [[ $status -ne 0 ]]; then
    : > "$raw_tmp"
    cp "$raw_tmp" "$raw_output"
    write_failure_meta "failed" "grok_extract_js_failed" "browser_tab_read_timeout" "$status"
    cat "$stderr_log" >&2
    return "$status"
  fi
  python3 - "$snapshot_tmp" "$raw_tmp" "$state_tmp" "$sentinel" <<'PY'
import json
import pathlib
import sys

snapshot_path, raw_path, state_path, sentinel = sys.argv[1:]
text = pathlib.Path(snapshot_path).read_text(encoding="utf-8", errors="replace")
try:
    snapshot = json.loads(text)
    if isinstance(snapshot, str):
        snapshot = json.loads(snapshot or "{}")
except json.JSONDecodeError as exc:
    pathlib.Path(raw_path).write_text("", encoding="utf-8")
    pathlib.Path(state_path).write_text(json.dumps({"ok": False, "failure": "grok_extract_snapshot_invalid_json", "detail": str(exc)}), encoding="utf-8")
    raise SystemExit(0)
if not isinstance(snapshot, dict):
    pathlib.Path(raw_path).write_text("", encoding="utf-8")
    pathlib.Path(state_path).write_text(json.dumps({"ok": False, "failure": "grok_extract_snapshot_invalid_json", "detail": f"unexpected payload type: {type(snapshot).__name__}"}), encoding="utf-8")
    raise SystemExit(0)
selected = snapshot.get("selected") if isinstance(snapshot, dict) else None
raw = str((selected or {}).get("text") or "")
pathlib.Path(raw_path).write_text(raw if raw.endswith("\n") or not raw else raw + "\n", encoding="utf-8")
failure = ""
if snapshot.get("providerRateLimited") is True:
    failure = "grok_provider_rate_limited"
elif snapshot.get("providerCapacityBusy") is True:
    failure = "grok_provider_capacity_busy"
elif not selected:
    failure = "grok_extract_no_provider_turn"
elif sentinel and sentinel not in raw:
    failure = "grok_extract_missing_sentinel"
pathlib.Path(state_path).write_text(json.dumps({
    "ok": not failure,
    "failure": failure or None,
    "raw_chars": len(raw),
    "raw_contains_sentinel": bool(sentinel and sentinel in raw),
    "body_contains_sentinel": snapshot.get("bodyContainsSentinel"),
    "candidate_count": snapshot.get("candidateCount"),
    "sentinel_candidate_count": snapshot.get("sentinelCandidateCount"),
}, sort_keys=True), encoding="utf-8")
PY
  cp "$raw_tmp" "$raw_output"
  return 0
}

deadline=$(( $(date +%s) + timeout_s ))
last_text=""
stable_count=0
extract_once || exit $?
state_ok="$(python3 -c 'import json,sys; print("1" if json.load(open(sys.argv[1])).get("ok") else "0")' "$state_tmp")"
if [[ "$wait_for_sentinel" -eq 1 ]]; then
  while [[ "$state_ok" != "1" && "$(date +%s)" -lt "$deadline" ]]; do
    sleep 1
    extract_once || exit $?
    current_text="$(cat "$raw_output")"
    if [[ "$current_text" == "$last_text" && -n "$current_text" ]]; then
      stable_count=$((stable_count + 1))
    else
      stable_count=0
      last_text="$current_text"
    fi
    state_ok="$(python3 -c 'import json,sys; print("1" if json.load(open(sys.argv[1])).get("ok") else "0")' "$state_tmp")"
    if [[ "$state_ok" == "1" && "$stable_count" -lt "$stable_polls" ]]; then
      state_ok=0
    fi
  done
fi

failure="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("failure") or "")' "$state_tmp")"
if [[ -n "$failure" ]]; then
  if [[ "$failure" == "grok_provider_rate_limited" ]]; then
    write_failure_meta "failed" "$failure" "provider_blocked" 4
    echo "Grok provider rate limited on controlled tab $requested_tab_id." >&2
    exit 4
  fi
  if [[ "$failure" == "grok_provider_capacity_busy" ]]; then
    write_failure_meta "failed" "$failure" "provider_capacity_limited" 4
    echo "Grok provider capacity busy on controlled tab $requested_tab_id." >&2
    exit 4
  fi
  write_failure_meta "missing_sentinel" "$failure" "submitted_no_response_proof" 4
  echo "Grok provider-specific extractor did not find a sentinel-bearing assistant turn: $failure" >&2
  exit 4
fi

python3 - "$raw_output" "$output" "$sentinel" <<'PY'
import pathlib
import sys

raw_path, out_path, sentinel = sys.argv[1:]
text = pathlib.Path(raw_path).read_text(encoding="utf-8", errors="replace")
if sentinel:
    idx = text.rfind(sentinel)
    if idx == -1:
        raise SystemExit("sentinel missing from Grok provider turn")
    after = text[idx + len(sentinel):].strip()
    if after:
        raise SystemExit("Grok provider turn contains text after terminal sentinel")
    text = text[:idx]
    if sentinel in text:
        text = text[text.rfind(sentinel) + len(sentinel):]
    filtered = []
    for line in text.splitlines():
        stripped = line.strip()
        lower = stripped.lower()
        if not stripped:
            filtered.append(line)
            continue
        if lower.startswith("automation-only instruction:"):
            continue
        if lower == "do not print anything after that marker.":
            continue
        if "after your complete answer, append a final line containing only this exact marker" in lower:
            continue
        filtered.append(line)
    text = "\n".join(filtered).strip()
pathlib.Path(out_path).write_text(text + "\n" if text else "", encoding="utf-8")
PY

finished_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
python3 - "$meta_output" "$output" "$raw_output" "$stderr_log" "$snapshot_tmp" "$sentinel" "$started_at" "$finished_at" "$requested_tab_id" <<'PY'
import json
import pathlib
import sys

meta, out, raw, err, snapshot, sentinel, started, finished, tab_id = sys.argv[1:]
raw_text = pathlib.Path(raw).read_text(encoding="utf-8", errors="replace")
out_text = pathlib.Path(out).read_text(encoding="utf-8", errors="replace") if pathlib.Path(out).is_file() else ""
snapshot_payload = json.loads(pathlib.Path(snapshot).read_text(encoding="utf-8", errors="replace"))
if isinstance(snapshot_payload, str):
    snapshot_payload = json.loads(snapshot_payload or "{}")
if not isinstance(snapshot_payload, dict):
    snapshot_payload = {"unexpected_payload_type": type(snapshot_payload).__name__}
pathlib.Path(meta).write_text(json.dumps({
    "status": "completed",
    "proof_status": "response_proven",
    "provider": "grok",
    "provider_specific_extractor": True,
    "generic_page_text_fallback_used": False,
    "output": out,
    "raw_output": raw,
    "stderr_log": err,
    "snapshot_path": snapshot,
    "sentinel": sentinel or None,
    "requested_tab_id": tab_id,
    "controlled_tab_id": tab_id,
    "response_source": "grok-provider-dom",
    "raw_contains_sentinel": bool(sentinel and sentinel in raw_text),
    "clean_contains_sentinel": bool(sentinel and sentinel in out_text),
    "raw_chars": len(raw_text),
    "clean_chars": len(out_text),
    "selected_root": snapshot_payload.get("selected") or {},
    "body_contains_sentinel": snapshot_payload.get("bodyContainsSentinel"),
    "candidate_count": snapshot_payload.get("candidateCount"),
    "sentinel_candidate_count": snapshot_payload.get("sentinelCandidateCount"),
    "started_at": started,
    "finished_at": finished,
}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

cat "$meta_output"
