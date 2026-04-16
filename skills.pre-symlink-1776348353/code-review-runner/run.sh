#!/usr/bin/env bash
# /code-review-runner — deterministic code review with LLM findings
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case "${1:-help}" in
    review)
        shift
        spec_file="${1:-}"
        shift || true
        [[ -n "$spec_file" && -f "$spec_file" ]] || { echo "Usage: ./run.sh review <spec.json> [--max-rounds N] [--backend MODEL]" >&2; exit 1; }
        exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/code_review_runner.py" review "$spec_file" "$@"
        ;;
    dry-run)
        shift
        spec_file="${1:-}"
        [[ -n "$spec_file" && -f "$spec_file" ]] || { echo "Usage: ./run.sh dry-run <spec.json>" >&2; exit 1; }
        exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/code_review_runner.py" dry-run "$spec_file"
        ;;
    result)
        shift
        result_file="${1:-}"
        [[ -n "$result_file" && -f "$result_file" ]] || { echo "Usage: ./run.sh result <result.json>" >&2; exit 1; }
        uv run --project "$SCRIPT_DIR" python -c "
import json, sys
r = json.loads(open('$result_file').read())
print(f\"task_id={r['task_id']}\")
print(f\"status={r['status']}\")
print(f\"score={r['score']:.3f}\")
print(f\"findings_total={r['findings_total']}\")
print(f\"findings_validated={r['findings_validated']}\")
print(f\"t0_violations={r['t0_violation_count']}\")
print(f\"rounds={r['rounds']}\")
sys.exit(0 if r['status'] == 'pass' else 1)
"
        ;;
    help|--help|-h)
        echo "Usage: ./run.sh {review|dry-run|result|help}"
        echo ""
        echo "Commands:"
        echo "  review <spec.json>    Run T0 validators + LLM review"
        echo "  dry-run <spec.json>   T0 validators only (no LLM call)"
        echo "  result <result.json>  Parse result.json into key=value pairs"
        echo ""
        echo "Options:"
        echo "  --max-rounds N        Max review rounds (default: 2)"
        echo "  --backend MODEL       LLM backend: codex, text, gemini, claude (default: codex)"
        ;;
    *)
        echo "Unknown command: $1" >&2
        exit 1
        ;;
esac
