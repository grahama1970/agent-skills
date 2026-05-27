#!/usr/bin/env bash
# /phart-dag-chart — Validate DAG JSON and render PHART ASCII decision trees (Python 3.14+)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
unset VIRTUAL_ENV

if [[ -x "$SCRIPT_DIR/scripts/ensure_venv.sh" ]]; then
  "$SCRIPT_DIR/scripts/ensure_venv.sh" || true
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "error [uv_missing]: uv is required. Install uv before running this skill." >&2
  exit 2
fi

cmd="${1:-}"
shift || true

case "$cmd" in
  chart|validate)
    exec uv run --project "$SCRIPT_DIR" phart-dag-chart "$cmd" "$@"
    ;;
  ""|help|-h|--help)
    cat <<'EOF'
/phart-dag-chart — DAG JSON validate + PHART ASCII chart

Usage:
  ./run.sh validate <dag.json> [--json]
  ./run.sh chart <dag.json>

Exit codes:
  0  success
  1  validation or render error (helpful message on stderr)
  2  usage / missing uv

Contract: DAG.json in → chart on stdout or fix errors on stderr (no tracebacks).
Requires Python >=3.14 (PHART 1.5 from github.com/scottvr/phart).
EOF
    ;;
  *)
    echo "error [usage]: unknown command: $cmd" >&2
    echo "hint: use chart or validate. Run ./run.sh help" >&2
    exit 2
    ;;
esac
