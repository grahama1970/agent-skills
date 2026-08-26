#!/usr/bin/env bash
# curate-client front door. Stdlib-only Python; no venv needed.
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SKILL_DIR/scripts/curate.py" "$@"
