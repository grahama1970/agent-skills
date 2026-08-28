#!/usr/bin/env bash
set -euo pipefail
unset VIRTUAL_ENV

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export LIVE_EVIDENCE_DATA_DIR="${LIVE_EVIDENCE_DATA_DIR:-${TMPDIR:-/tmp}/live-evidence-sanity-data}"
# Local cache first. This previously defaulted to /mnt/storage12tb, which is
# rotational=1 and 87% full, while the NVMe root had 1.2T free. Override by
# exporting UV_PROJECT_ENVIRONMENT explicitly.
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-${XDG_CACHE_HOME:-$HOME/.cache}/live-evidence/venv}"
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"
env_path="$(realpath -m "$UV_PROJECT_ENVIRONMENT")"
root_path="$(realpath -m "$SCRIPT_DIR")"
if [[ "$env_path" == "$root_path" || "$env_path" == "$root_path"/* ]]; then
  echo "Refusing repository-local UV_PROJECT_ENVIRONMENT: $UV_PROJECT_ENVIRONMENT" >&2
  exit 2
fi
mkdir -p "$LIVE_EVIDENCE_DATA_DIR"

uv run --project "$SCRIPT_DIR" --extra dev --extra stt python "$SCRIPT_DIR/scripts/verify_skill.py" "$SCRIPT_DIR"
uv run --project "$SCRIPT_DIR" --extra dev --extra stt python "$SCRIPT_DIR/scripts/verify_file_size.py" "$SCRIPT_DIR"
uv run --project "$SCRIPT_DIR" --extra dev --extra stt python "$SCRIPT_DIR/scripts/verify_data_qid.py" "$SCRIPT_DIR/ui/src"
uv run --project "$SCRIPT_DIR" --extra dev --extra stt python -m pytest "$SCRIPT_DIR/tests" -q
uv run --project "$SCRIPT_DIR" --extra dev --extra stt python "$SCRIPT_DIR/scripts/sanity_live.py" "$SCRIPT_DIR"
"$SCRIPT_DIR/run.sh" ui-build

echo "live-evidence sanity: PASS"
