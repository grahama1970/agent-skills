#!/usr/bin/env bash
set -euo pipefail
unset VIRTUAL_ENV

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export LIVE_EVIDENCE_DATA_DIR="${LIVE_EVIDENCE_DATA_DIR:-${TMPDIR:-/tmp}/live-evidence-sanity-data}"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/mnt/storage12tb/skills/live-evidence/runtime-venv}"
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"
mkdir -p "$LIVE_EVIDENCE_DATA_DIR"

uv run --project "$SCRIPT_DIR" --extra dev python "$SCRIPT_DIR/scripts/verify_skill.py" "$SCRIPT_DIR"
uv run --project "$SCRIPT_DIR" --extra dev python "$SCRIPT_DIR/scripts/verify_file_size.py" "$SCRIPT_DIR"
uv run --project "$SCRIPT_DIR" --extra dev python "$SCRIPT_DIR/scripts/verify_data_qid.py" "$SCRIPT_DIR/ui/src"
uv run --project "$SCRIPT_DIR" --extra dev python -m pytest "$SCRIPT_DIR/tests" -q
uv run --project "$SCRIPT_DIR" --extra dev python "$SCRIPT_DIR/scripts/sanity_live.py" "$SCRIPT_DIR"
"$SCRIPT_DIR/run.sh" ui-build

echo "live-evidence sanity: PASS"
