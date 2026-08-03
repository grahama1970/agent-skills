#!/usr/bin/env bash
# Revert Dewey database session to its committed backup only.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${SCRIPT_DIR}/db_repair_session.py" revert "$@"
