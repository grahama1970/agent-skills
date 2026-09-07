#!/usr/bin/env bash
# land — scoped commit+push of named paths onto origin/main.
# Delegates entirely to ops-worktrees land.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$SCRIPT_DIR/../ops-worktrees/scripts/land.sh" "$@"
