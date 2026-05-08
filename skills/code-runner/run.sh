#!/usr/bin/env bash
# /code-runner — deterministic run-and-debug loop for code tasks
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="${SKILLS_DIR:-$(dirname "$SCRIPT_DIR")}"

case "${1:-help}" in
    run)
        shift
        spec_file="${1:-}"
        shift || true
        [[ -n "$spec_file" && -f "$spec_file" ]] || { echo "Usage: ./run.sh run <task-spec.json> [--max-rounds N] [--backend MODEL]" >&2; exit 1; }
        spec_file="$(realpath "$spec_file")"
        cd "$SCRIPT_DIR/src"
        exec env PYTHONPATH="$SCRIPT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" uv run --project "$SCRIPT_DIR" python -m code_runner.cli run "$spec_file" "$@"
        ;;
    dry-run)
        shift
        spec_file="${1:-}"
        shift || true
        [[ -n "$spec_file" && -f "$spec_file" ]] || { echo "Usage: ./run.sh dry-run <task-spec.json> [--explain-risk] [--json]" >&2; exit 1; }
        spec_file="$(realpath "$spec_file")"
        cd "$SCRIPT_DIR/src"
        exec env PYTHONPATH="$SCRIPT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" uv run --project "$SCRIPT_DIR" python -m code_runner.cli dry-run "$spec_file" "$@"
        ;;
    doctor)
        shift
        cd "$SCRIPT_DIR/src"
        exec env PYTHONPATH="$SCRIPT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" uv run --project "$SCRIPT_DIR" python -m code_runner.cli doctor "$@"
        ;;
    status)
        shift
        target="${1:-}"
        shift || true
        [[ -n "$target" ]] || { echo "Usage: ./run.sh status <output_dir|status.json|task_id> [--tail-events N] [--json]" >&2; exit 1; }
        exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/code_runner.py" status "$target" "$@"
        ;;
    watch)
        shift
        target="${1:-}"
        shift || true
        [[ -n "$target" ]] || { echo "Usage: ./run.sh watch <output_dir|status.json|task_id> [--interval N] [--tail-events N]" >&2; exit 1; }
        exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/code_runner.py" watch "$target" "$@"
        ;;
    review)
        shift
        review_file="${1:-}"
        if [[ -n "$review_file" && -f "$review_file" ]]; then
            # Review a specific hunk.md file
            if command -v hunk &>/dev/null; then
                exec hunk patch "$review_file"
            else
                exec cat "$review_file"
            fi
        else
            # Review latest changes in cwd via hunk diff
            if command -v hunk &>/dev/null; then
                exec hunk diff
            else
                exec git diff
            fi
        fi
        ;;
    result)
        # Parse result.json and output structured summary (for other skills to consume)
        shift
        result_file="${1:-}"
        [[ -n "$result_file" && -f "$result_file" ]] || { echo "Usage: ./run.sh result <result.json>" >&2; exit 1; }
        uv run --project "$SCRIPT_DIR" python -c "
import json, sys
r = json.loads(open('$result_file').read())
print(f\"task_id={r['task_id']}\")
print(f\"status={r['status']}\")
print(f\"dod_passed={r['dod_passed']}\")
print(f\"best_score={r['best_score']:.3f}\")
print(f\"rounds={r['rounds']}\")
print(f\"backend={r['backend']}\")
print(f\"best_commit={r.get('best_commit', '')}\")
sys.exit(0 if r['dod_passed'] else 1)
"
        ;;
    help|--help|-h)
        echo "Usage: ./run.sh {run|dry-run|doctor|status|watch|review|result|help}"
        echo ""
        echo "Commands:"
        echo "  run <spec.json>       Run task with self-improvement loop"
        echo "  dry-run <spec.json>   Show what would execute; add --explain-risk"
        echo "  doctor [--json]       Report environment readiness"
        echo "  status <target>       Show run status from status/events artifacts"
        echo "  watch <target>        Follow run status until terminal"
        echo "  review [file.md]      Review changes with hunk (or git diff fallback)"
        echo "  result <result.json>  Parse result.json into key=value pairs"
        echo ""
        echo "Options:"
        echo "  --max-rounds N        Max fix rounds (default: 5)"
        echo "  --backend MODEL       LLM backend: codex, text, gemini, claude (default: from spec)"
        ;;
    *)
        echo "Unknown command: $1" >&2
        exit 1
        ;;
esac
