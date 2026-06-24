#!/usr/bin/env bash
set -euo pipefail
unset VIRTUAL_ENV 2>/dev/null || true
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SKILL_DIR/scripts/pipeline.py" "$@"
