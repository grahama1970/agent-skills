#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# Extractor Quality Check — Margaret Chen + Jennifer Cheung datalake assessors
#
# Usage:
#   ./run.sh state                          # Collect datalake state (JSON)
#   ./run.sh review --run-id <id>           # Run batch review
#   ./run.sh review --run-id <id> --json    # JSON output
#   ./run.sh thresholds                     # Show current annealing thresholds
#   ./run.sh help                           # Show this help

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SKILL_DIR"

case "${1:-help}" in
  state)
    uv run --project "$SCRIPT_DIR" python datalake_state_collector.py
    ;;
  review)
    shift
    uv run --project "$SCRIPT_DIR" python batch_review.py "$@"
    ;;
  thresholds)
    uv run --project "$SCRIPT_DIR" python -c "
from annealing import ANNEALING_SCHEDULE
for (lo, hi), t in ANNEALING_SCHEDULE.items():
    hi_s = f'{hi}%' if hi != float('inf') else '+'
    print(f\"{t['phase_name']:15s} {lo:3d}%-{hi_s:5s}  score>={t['min_score']}  fail<={t['max_fail_ratio']}  table>={t['table_fidelity_min']}  section>={t['section_alignment_min']}\")
    print(f\"  Margaret: {t['margaret_says']}\")
    print(f\"  Jennifer: {t['jennifer_says']}\")
    print()
"
    ;;
  help|--help|-h)
    echo "extractor-quality-check — Margaret Chen + Jennifer Cheung datalake assessors"
    echo ""
    echo "Commands:"
    echo "  state                  Collect datalake state (JSON to stdout)"
    echo "  review --run-id <id>   Run persona batch review"
    echo "  review --run-id <id> --json   JSON output"
    echo "  thresholds             Show annealing schedule"
    echo "  help                   This message"
    ;;
  *)
    echo "Unknown command: $1" >&2
    echo "Run './run.sh help' for usage" >&2
    exit 1
    ;;
esac
