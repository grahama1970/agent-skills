#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRANSPORT_PY="${SCRIPT_DIR}/lib/webgpt_transport.py"

usage() {
  cat <<'USAGE'
Usage:
  surf webgpt.recover --artifact-dir DIR [--audit]

Options:
  --artifact-dir DIR   Round/run artifact directory containing meta/raw/receipt files.
  --audit              Alias for recover; prints audit-oriented recovery JSON.
  --finalize           Deprecated compatibility no-op; recover never resubmits.
  --help, -h           Show this help.
USAGE
}

artifact_dir=""
audit=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --artifact-dir) artifact_dir="${2:-}"; shift 2 ;;
    --audit) audit=1; shift ;;
    --finalize) shift ;;
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

python3 "$TRANSPORT_PY" recover --artifact-dir "$artifact_dir"
