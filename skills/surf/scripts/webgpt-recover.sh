#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRANSPORT_PY="${SCRIPT_DIR}/lib/webgpt_transport.py"

usage() {
  cat <<'USAGE'
Usage:
  surf webgpt.recover --artifact-dir DIR [--audit] [--finalize]

Options:
  --artifact-dir DIR   Round/run artifact directory containing meta/raw/receipt files.
  --audit              Alias for recover; prints audit-oriented recovery JSON.
  --finalize           Run webgpt.extract for submitted orphaned rounds with tab+sentinel.
  --timeout SECONDS    Per extract wait timeout with --finalize. Default: 30.
  --stable-polls N     Stable polls passed to webgpt.extract --wait. Default: 3.
  --help, -h           Show this help.
USAGE
}

artifact_dir=""
audit=0
finalize=0
timeout_s=30
stable_polls=3

while [[ $# -gt 0 ]]; do
  case "$1" in
    --artifact-dir) artifact_dir="${2:-}"; shift 2 ;;
    --audit) audit=1; shift ;;
    --finalize) finalize=1; shift ;;
    --timeout) timeout_s="${2:-}"; shift 2 ;;
    --stable-polls) stable_polls="${2:-}"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$artifact_dir" ]]; then
  usage >&2
  exit 2
fi

if [[ ! -d "$artifact_dir" ]]; then
  echo "artifact dir not found: $artifact_dir" >&2
  exit 2
fi

recovery_json="$(mktemp /tmp/surf-webgpt-recover.XXXXXX.json)"
python3 "$TRANSPORT_PY" recover --artifact-dir "$artifact_dir" > "$recovery_json"

if [[ "$finalize" -eq 0 ]]; then
  cat "$recovery_json"
  exit 0
fi

mapfile -t claim_fields < <(python3 - "$recovery_json" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
claim = payload.get("claim") if isinstance(payload.get("claim"), dict) else {}
print("1" if claim.get("available") else "0")
print(claim.get("tab_id") or "")
print(claim.get("sentinel") or "")
print(claim.get("output") or "")
print(claim.get("raw_output") or "")
print(claim.get("meta_output") or "")
PY
)

claim_available="${claim_fields[0]:-0}"
claim_tab_id="${claim_fields[1]:-}"
claim_sentinel="${claim_fields[2]:-}"
claim_output="${claim_fields[3]:-}"
claim_raw="${claim_fields[4]:-}"
claim_meta="${claim_fields[5]:-}"

if [[ "$claim_available" != "1" || -z "$claim_tab_id" || -z "$claim_sentinel" ]]; then
  python3 - "$recovery_json" "$artifact_dir" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
artifact_dir = pathlib.Path(sys.argv[2])
payload["schema"] = "surf.webgpt_recover_finalize.v1"
payload["finalize_attempted"] = False
if payload.get("state") == "prepared_prompt_only":
    packet_path = artifact_dir / "browser-recovery-packet.json"
    payload.update(
        {
            "status": "NEEDS_ATTENTION",
            "ok": False,
            "terminal": True,
            "failure_code": "browser_submit_not_accepted",
            "submitted_to_chatgpt": False,
            "prepared_prompt_is_transport_proof": False,
            "auto_retry_blocked_reason": "browser_prepared_prompt_requires_attachment_preserving_resubmit",
            "finalize_reason": "prepared_prompt_not_submitted_to_chatgpt",
            "recovery_packet_path": str(packet_path),
        }
    )
    payload["evidence"] = {
        "artifact_dir": str(artifact_dir),
        "state": payload.get("state"),
        "response_meta_path": payload.get("response_meta_path"),
        "response_raw_path": payload.get("response_raw_path"),
    }
    packet_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
else:
    payload["finalize_reason"] = "no_claim_available"
print(json.dumps(payload, indent=2))
PY
  if python3 - "$recovery_json" <<'PY'
import json
import pathlib
import sys
payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
raise SystemExit(0 if payload.get("state") == "prepared_prompt_only" else 1)
PY
  then
    python3 "$TRANSPORT_PY" write-summary --artifact-dir "$artifact_dir" >/dev/null 2>&1 || true
    exit 0
  fi
  exit 3
fi

extract_status=0
attempt_dir="$artifact_dir/webgpt-recover-attempts/$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$attempt_dir"
attempt_output="$attempt_dir/response.md"
attempt_raw="$attempt_dir/response.raw.md"
attempt_meta="$attempt_dir/response.meta.json"
attempt_stderr="$attempt_dir/extract.stderr.log"
"${SCRIPT_DIR}/webgpt-extract.sh" \
  --tab-id "$claim_tab_id" \
  --output "$attempt_output" \
  --raw-output "$attempt_raw" \
  --meta-output "$attempt_meta" \
  --sentinel "$claim_sentinel" \
  --wait \
  --timeout "$timeout_s" \
  --stable-polls "$stable_polls" \
  >"$attempt_dir/extract.stdout.log" 2>"$attempt_stderr" || extract_status=$?

if [[ "$extract_status" -eq 0 ]]; then
  cp "$attempt_output" "$claim_output"
  cp "$attempt_raw" "$claim_raw"
  cp "$attempt_meta" "$claim_meta"
fi

python3 "$TRANSPORT_PY" write-summary \
  --artifact-dir "$artifact_dir" \
  --meta "$claim_meta" \
  --raw "$claim_raw" \
  >/dev/null 2>&1 || true

python3 - "$recovery_json" "$extract_status" "$claim_output" "$claim_raw" "$claim_meta" "$artifact_dir" "$attempt_dir" "$attempt_output" "$attempt_raw" "$attempt_meta" "$attempt_stderr" <<'PY'
import json
import pathlib
import sys

(
    recovery_path,
    status_s,
    output,
    raw,
    meta,
    artifact_dir,
    attempt_dir,
    attempt_output,
    attempt_raw,
    attempt_meta,
    attempt_stderr,
) = sys.argv[1:]
payload = json.loads(pathlib.Path(recovery_path).read_text(encoding="utf-8"))
summary_path = pathlib.Path(artifact_dir) / "webgpt_transport_summary.json"
stderr_path = pathlib.Path(attempt_stderr)
payload["schema"] = "surf.webgpt_recover_finalize.v1"
payload["finalize_attempted"] = True
payload["finalize_exit_code"] = int(status_s)
payload["finalize_output"] = output
payload["finalize_raw_output"] = raw
payload["finalize_meta_output"] = meta
payload["finalize_attempt_artifacts"] = {
    "attempt_dir": attempt_dir,
    "output": attempt_output,
    "raw_output": attempt_raw,
    "meta_output": attempt_meta,
    "stderr_log": attempt_stderr,
}
payload["finalize_preserved_existing_outputs"] = int(status_s) != 0
payload["finalize_stderr_tail"] = (
    stderr_path.read_text(encoding="utf-8", errors="replace")[-4000:]
    if stderr_path.exists()
    else ""
)
payload["transport_summary"] = str(summary_path) if summary_path.exists() else None
print(json.dumps(payload, indent=2))
PY

exit "$extract_status"
