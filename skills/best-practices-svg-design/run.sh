#!/usr/bin/env bash
# CLI entry for best-practices-svg-design deterministic checks.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec uv run --quiet --project "$DIR" svg-design-check "$@"
