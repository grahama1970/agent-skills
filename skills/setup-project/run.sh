#!/usr/bin/env bash
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec uv run --with pydantic --with PyYAML python "$SKILL_DIR/scripts/setup_project.py" "$@"
