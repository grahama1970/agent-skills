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
  python3 - "$recovery_json" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
payload["schema"] = "surf.webgpt_recover_finalize.v1"
payload["finalize_attempted"] = False
payload["finalize_reason"] = "no_claim_available"
print(json.dumps(payload, indent=2))
PY
  exit 3
fi

extract_status=0
"${SCRIPT_DIR}/webgpt-extract.sh" \
  --tab-id "$claim_tab_id" \
  --output "$claim_output" \
  --raw-output "$claim_raw" \
  --meta-output "$claim_meta" \
  --sentinel "$claim_sentinel" \
  --wait \
  --timeout "$timeout_s" \
  --stable-polls "$stable_polls" \
  >/dev/null || extract_status=$?

python3 "$TRANSPORT_PY" write-summary \
  --artifact-dir "$artifact_dir" \
  --meta "$claim_meta" \
  --raw "$claim_raw" \
  >/dev/null 2>&1 || true

python3 - "$recovery_json" "$extract_status" "$claim_output" "$claim_raw" "$claim_meta" "$artifact_dir" <<'PY'
import json
import pathlib
import sys

recovery_path, status_s, output, raw, meta, artifact_dir = sys.argv[1:]
payload = json.loads(pathlib.Path(recovery_path).read_text(encoding="utf-8"))
summary_path = pathlib.Path(artifact_dir) / "webgpt_transport_summary.json"
payload["schema"] = "surf.webgpt_recover_finalize.v1"
payload["finalize_attempted"] = True
payload["finalize_exit_code"] = int(status_s)
payload["finalize_output"] = output
payload["finalize_raw_output"] = raw
payload["finalize_meta_output"] = meta
payload["transport_summary"] = str(summary_path) if summary_path.exists() else None
print(json.dumps(payload, indent=2))
PY

exit "$extract_status"
