#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
RUN_SH="$SKILL_DIR/run.sh"

usage() {
  cat <<'EOF'
Usage: surf webgpt.monitoring-sanity [options]

Runs a live, non-mocked ChatGPT/WebGPT sentinel round trip and verifies that
webgpt.submit writes assistant-stream monitoring artifacts.

Options:
  --output-dir DIR     Artifact directory. Default: /tmp/surf-webgpt-monitoring-sanity-<timestamp>
  --tab-id ID          Use an existing controlled ChatGPT tab.
  --url URL            Resolve an existing ChatGPT tab by URL.
  --expect-url URL     Identity assertion for --tab-id.
  --expect-title TEXT  Identity assertion for --tab-id.
  --no-activate        Keep the controlled tab in the background. Requires target tab/url.
  --timeout SECONDS    WebGPT timeout. Default: 240.
  --json               Print machine-readable result JSON.
EOF
}

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
output_dir="/tmp/surf-webgpt-monitoring-sanity-$timestamp"
tab_id=""
url=""
expect_url=""
expect_title=""
no_activate=0
timeout_s=240
json_out=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir) output_dir="${2:-}"; shift 2 ;;
    --tab-id) tab_id="${2:-}"; shift 2 ;;
    --url) url="${2:-}"; shift 2 ;;
    --expect-url) expect_url="${2:-}"; shift 2 ;;
    --expect-title) expect_title="${2:-}"; shift 2 ;;
    --no-activate) no_activate=1; shift ;;
    --timeout) timeout_s="${2:-}"; shift 2 ;;
    --json) json_out=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

mkdir -p "$output_dir"
request="$output_dir/request.md"
response="$output_dir/response.md"
raw_response="$output_dir/response.raw.md"
meta="$output_dir/response.meta.json"
stderr_log="$output_dir/webgpt-submit.stderr.log"
result_json="$output_dir/monitoring-sanity-result.json"
token="SURF_MONITORING_SANITY_${timestamp}_$$"

cat > "$request" <<EOF
Return exactly three short lines.
Line 1: $token
Line 2: assistant stream monitoring sanity
Line 3: done
EOF

args=(webgpt.submit --input "$request" --output "$response" --raw-output "$raw_response" --meta-output "$meta" --timeout "$timeout_s" --stable-polls 2)
if [[ -n "$tab_id" ]]; then
  args+=(--tab-id "$tab_id")
elif [[ -n "$url" ]]; then
  args+=(--url "$url")
else
  args+=(--create-tab)
fi
if [[ -n "$expect_url" ]]; then
  args+=(--expect-url "$expect_url")
fi
if [[ -n "$expect_title" ]]; then
  args+=(--expect-title "$expect_title")
fi
if [[ "$no_activate" -eq 1 ]]; then
  args+=(--no-activate)
fi

status=0
"$RUN_SH" "${args[@]}" >"$output_dir/webgpt-submit.stdout.log" 2>"$stderr_log" || status=$?

set +e
python3 - "$output_dir" "$status" "$token" "$result_json" <<'PY'
from __future__ import annotations

import json
import pathlib
import sys

artifact_dir = pathlib.Path(sys.argv[1])
submit_status = int(sys.argv[2])
token = sys.argv[3]
result_path = pathlib.Path(sys.argv[4])

heartbeat_path = artifact_dir / "webgpt_heartbeat.json"
events_path = artifact_dir / "webgpt_heartbeat.events.jsonl"
response_path = artifact_dir / "response.md"
raw_path = artifact_dir / "response.raw.md"
meta_path = artifact_dir / "response.meta.json"

checks: list[dict[str, object]] = []

def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append({"name": name, "ok": bool(ok), "detail": detail})

heartbeat = {}
events: list[dict[str, object]] = []
meta = {}
response_text = response_path.read_text(encoding="utf-8") if response_path.exists() else ""
raw_text = raw_path.read_text(encoding="utf-8") if raw_path.exists() else ""

if heartbeat_path.exists():
    heartbeat = json.loads(heartbeat_path.read_text(encoding="utf-8"))
if events_path.exists():
    for line in events_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
if meta_path.exists():
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

check("submit_exit_zero", submit_status == 0, f"exit={submit_status}")
check("response_contains_token", token in response_text or token in raw_text)
check("meta_response_proven", meta.get("proof_status") == "response_proven", str(meta.get("proof_status")))
check("heartbeat_exists", heartbeat_path.exists(), str(heartbeat_path))
check("heartbeat_stream_schema", heartbeat.get("stream_schema") == "surf.webgpt_assistant_stream.v1", str(heartbeat.get("stream_schema")))
check("assistant_chars_positive", int(heartbeat.get("assistant_message_chars") or 0) > 0, str(heartbeat.get("assistant_message_chars")))
check("assistant_hash_present", isinstance(heartbeat.get("assistant_message_sha256"), str) and len(heartbeat.get("assistant_message_sha256", "")) == 64)
check("assistant_tail_present", isinstance(heartbeat.get("assistant_tail_excerpt"), str) and len(heartbeat.get("assistant_tail_excerpt", "")) > 0)
check("assistant_sentinel_seen", heartbeat.get("assistant_sentinel_seen") is True, str(heartbeat.get("assistant_sentinel_seen")))
check("assistant_stable_count_present", isinstance(heartbeat.get("assistant_stable_poll_count"), int), str(heartbeat.get("assistant_stable_poll_count")))
check("events_jsonl_exists", events_path.exists(), str(events_path))
check("events_have_snapshots", any(e.get("event") == "assistant_snapshot" for e in events), f"events={len(events)}")
check(
    "events_chars_progress",
    max([int(((e.get("assistant") or {}).get("message_chars") or 0)) for e in events] or [0]) > 0,
    f"events={len(events)}",
)
check(
    "events_sentinel_seen",
    any((e.get("assistant") or {}).get("sentinel_seen") is True for e in events),
    f"events={len(events)}",
)

ok = all(item["ok"] for item in checks)
result = {
    "schema": "surf.webgpt_monitoring_sanity.v1",
    "status": "pass" if ok else "fail",
    "mocked": False,
    "live": True,
    "artifact_dir": str(artifact_dir),
    "request": str(artifact_dir / "request.md"),
    "response": str(response_path),
    "raw_response": str(raw_path),
    "meta": str(meta_path),
    "heartbeat": str(heartbeat_path),
    "events": str(events_path),
    "checks": checks,
    "claims": {
        "proves": [
            "webgpt.submit executed against a real ChatGPT/WebGPT browser tab",
            "assistant-stream heartbeat fields were written during the live run",
            "assistant-stream JSONL events were written during the live run",
        ] if ok else [],
        "attempted": [
            "live ChatGPT/WebGPT browser submit",
            "assistant-stream heartbeat validation",
            "assistant-stream JSONL validation",
        ],
        "does_not_prove": [
            "all future WebGPT runs will complete",
            "background no-activate mode unless --no-activate was used",
            "semantic quality of the assistant response",
        ],
    },
}
result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
raise SystemExit(0 if ok else 1)
PY
validate_status=$?
set -e

if [[ "$json_out" -eq 1 ]]; then
  cat "$result_json"
else
  if [[ "$validate_status" -eq 0 ]]; then
    echo "WebGPT monitoring sanity PASS"
  else
    echo "WebGPT monitoring sanity FAIL"
  fi
  echo "Artifacts: $output_dir"
  echo "Result: $result_json"
fi

exit "$validate_status"
