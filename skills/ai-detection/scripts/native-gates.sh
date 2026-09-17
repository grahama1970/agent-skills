#!/usr/bin/env bash
set -euo pipefail
# Storage policy: keep the venv on the 12TB drive, not inside the skill folder.
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/mnt/storage12tb/skills/ai-detection/.venv}"
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"
mkdir -p "$(dirname "$UV_PROJECT_ENVIRONMENT")"
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# Both commands are attempted; neither a missing checkout nor a failed native gate is success.
status=0
uv run --project "$ROOT" python -m ai_detection native-setup || status=1
uv run --project "$ROOT" python -m ai_detection native-evals --release || status=1
exit "$status"
