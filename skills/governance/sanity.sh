#!/usr/bin/env bash
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ARTIFACT_ROOT="${GOVERNANCE_ARTIFACT_ROOT:-/mnt/storage12tb/skills/governance}"
export UV_PROJECT_ENVIRONMENT="${GOVERNANCE_UV_ENV:-$ARTIFACT_ROOT/.venv}"
export PYTHONDONTWRITEBYTECODE=1
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
UV_PROJECT_ENVIRONMENT="$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).expanduser().resolve(strict=False))' "$UV_PROJECT_ENVIRONMENT")"
export UV_PROJECT_ENVIRONMENT
case "$UV_PROJECT_ENVIRONMENT" in
    "$PROJECT_ROOT"/*)
        if [ "${GOVERNANCE_ALLOW_UNSAFE_ARTIFACT_ROOT:-0}" != "1" ]; then
            echo "Error: GOVERNANCE_UV_ENV points inside the repository: $UV_PROJECT_ENVIRONMENT" >&2
            exit 2
        fi
        ;;
esac
mkdir -p "$(dirname "$UV_PROJECT_ENVIRONMENT")"

bash -n "$SCRIPT_DIR/run.sh"
uv run --project "$SCRIPT_DIR" python - <<PY
import py_compile
py_compile.compile("$SCRIPT_DIR/scripts/governance_loop.py", cfile="/tmp/governance_loop.pyc", doraise=True)
PY
uv run --project "$SCRIPT_DIR" --with loguru --with pyyaml python "$SKILLS_DIR/best-practices-skills/scripts/validate_skill.py" "$SCRIPT_DIR"
uv run --project "$SCRIPT_DIR" --group dev pytest "$SCRIPT_DIR/tests/test_governance_loop.py"

echo "Result: PASS"
