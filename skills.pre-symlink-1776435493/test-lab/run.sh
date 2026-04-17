#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SKILL_DIR"

# Ensure venv
if [[ ! -d .venv ]]; then
    uv venv .venv --python 3.11 2>/dev/null || python3 -m venv .venv
fi

# Install deps if needed
if [[ ! -f .venv/.installed ]]; then
    uv pip install -e . 2>/dev/null || .venv/bin/pip install -e .
    touch .venv/.installed
fi

PYTHON="$SKILL_DIR/.venv/bin/python"

usage() {
    cat <<'EOF'
test-lab: Adversarial blind evaluation harness

Usage:
  run.sh generate <plan-file>                          Generate hidden tests from task file
  run.sh run <target-dir> [--domain python|react|kde|skills]  Run hidden tests against target
  run.sh report <results-json>                         Rich table report from results
  run.sh verify-task <task-id> <target-dir> [--max-retries N] Verify task with retry budget

Examples:
  run.sh generate 01_TASKS.md
  run.sh run .pi/skills/ask --domain python
  run.sh verify-task "Task 1" .pi/skills/ask --max-retries 5
EOF
}

CMD="${1:-}"
shift || true

case "$CMD" in
    generate)
        exec "$PYTHON" -m test_lab generate "$@"
        ;;
    run)
        exec "$PYTHON" -m test_lab run "$@"
        ;;
    report)
        exec "$PYTHON" -m test_lab report "$@"
        ;;
    verify-task)
        exec "$PYTHON" -m test_lab verify-task "$@"
        ;;
    serve)
        # Run the blind eval HTTP service (locally, without Docker)
        exec "$PYTHON" -m uvicorn service:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8787}"
        ;;
    docker-up)
        # Build and start the blind eval Docker container
        docker build -t test-lab-blind "$SKILL_DIR" && \
        docker run -d --name test-lab-blind -p 8787:8787 \
            -v "${2:-$(pwd)}:/workspace:ro" \
            test-lab-blind
        echo "test-lab blind eval running on http://localhost:8787"
        ;;
    docker-down)
        docker stop test-lab-blind 2>/dev/null && docker rm test-lab-blind 2>/dev/null
        echo "test-lab stopped"
        ;;
    -h|--help|"")
        usage
        ;;
    *)
        echo "Unknown command: $CMD" >&2
        usage
        exit 1
        ;;
esac
