#!/usr/bin/env bash
# curate-client front door. Pydantic is the deterministic contract gate.
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec uv run --with pydantic --with PyYAML python "$SKILL_DIR/scripts/curate.py" "$@"
