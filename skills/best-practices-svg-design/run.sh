#!/usr/bin/env bash
# CLI entry for best-practices-svg-design deterministic checks.
# Runs from source (PYTHONPATH) so edited code is always the executing code.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$DIR/src${PYTHONPATH:+:$PYTHONPATH}"
exec uv run --quiet --project "$DIR" python -m svg_design_checks.cli "$@"
