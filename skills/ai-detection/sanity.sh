#!/usr/bin/env bash
set -euo pipefail
# Storage policy: keep the venv on the 12TB drive, not inside the skill folder.
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/mnt/storage12tb/skills/ai-detection/.venv}"
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"
mkdir -p "$(dirname "$UV_PROJECT_ENVIRONMENT")"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
# Core behavioral gate: real HTTP transport, strict contracts, model/evidence
# mechanisms, and structural best-practices guards. Browser journey is NOT here —
# it belongs to scripts/verify.sh --profile full and fails closed there.
uv run --project "$SCRIPT_DIR" --extra dev python -m pytest \
  tests/test_api.py tests/test_live_http.py tests/test_contracts.py \
  tests/test_detection.py tests/test_evidence.py tests/test_project.py tests/test_humanize.py tests/test_provenance.py tests/test_battle_judge.py -q
