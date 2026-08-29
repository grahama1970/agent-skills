#!/usr/bin/env bash
# /phart-dag-chart — Validate DAG JSON and render PHART ASCII decision trees (Python 3.14+)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
unset VIRTUAL_ENV

if [[ -f "$SCRIPT_DIR/scripts/ensure_venv.sh" ]]; then
  # shellcheck source=scripts/ensure_venv.sh
  source "$SCRIPT_DIR/scripts/ensure_venv.sh"
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "error [uv_missing]: uv is required. Install uv before running this skill." >&2
  exit 2
fi

# Self-heal an impossible requires-python. A cross-checkout sync periodically
# copies a stale pre-fix pyproject.toml over this one, reverting requires-python
# to ">=3.14,<3.13" -- an empty range that makes `uv run` refuse with
# "conflicting Python requirements", silently breaking every caller (e.g. the
# agentic-evals self-heal DAG gate). The canonical value is ">=3.14" (PHART 1.5).
# Idempotent: rewrites only when the broken range is present, and back to the
# value HEAD already holds, so a healthy tree stays clean.
PYPROJECT="$SCRIPT_DIR/pyproject.toml"
if [[ -f "$PYPROJECT" ]] && grep -q 'requires-python *= *">=3\.14,<3\.13"' "$PYPROJECT"; then
  sed -i 's/requires-python *= *">=3\.14,<3\.13"/requires-python = ">=3.14"/' "$PYPROJECT"
  echo "note [phart]: repaired impossible requires-python in pyproject.toml (was >=3.14,<3.13)" >&2
fi

cmd="${1:-}"
shift || true

case "$cmd" in
  chart|validate|watch|research-round)
    exec uv run --project "$SCRIPT_DIR" phart-dag-chart "$cmd" "$@"
    ;;
  ""|help|-h|--help)
    cat <<'EOF'
/phart-dag-chart — DAG JSON validate + PHART ASCII chart

Usage:
  ./run.sh validate <dag.json> [--json]
  ./run.sh chart <dag.json>
  ./run.sh watch <dag.json> --progress <dag-progress.json> [--once]

Exit codes:
  0  success
  1  validation or render error (helpful message on stderr)
  2  usage / missing uv

Contract: DAG.json in → chart on stdout or fix errors on stderr (no tracebacks).
Watch mode reads Tau dag-progress.json and refreshes a compact terminal status until terminal state.
Requires Python >=3.14 (PHART 1.5 from github.com/scottvr/phart).
EOF
    ;;
  *)
    echo "error [usage]: unknown command: $cmd" >&2
    echo "hint: use chart or validate. Run ./run.sh help" >&2
    exit 2
    ;;
esac
