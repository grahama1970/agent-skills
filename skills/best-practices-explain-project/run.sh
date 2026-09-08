#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
case "${1:-}" in
  validate)
    python3 - <<'PY'
from pathlib import Path
t=Path('SKILL.md').read_text()
for s in ['project.feature_explainer.v1','extra="forbid"','teleprompter_points','source_ranges','debugger_stops','ops-excalidraw','create-svg','End-of-work lifecycle']:
    assert s in t, s
print('BEST_PRACTICES_EXPLAIN_PROJECT_CONTRACT_OK')
PY
    ;;
  *) echo "usage: $0 validate" >&2; exit 2;;
esac
