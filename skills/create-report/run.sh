#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ "${1:-}" =~ ^(schema|sample|validate|repair|render)$ ]]; then
  if command -v uv >/dev/null 2>&1; then
    exec uv run --with pydantic python "$SCRIPT_DIR/scripts/report_contract.py" "$@"
  fi
  exec python3 "$SCRIPT_DIR/scripts/report_contract.py" "$@"
fi

echo "usage: run.sh schema|sample|validate|repair|render ..." >&2
exit 2
