#!/usr/bin/env bash
# GitHub Search - deep search plus Brave-backed executable repository evaluation.
set -euo pipefail
unset VIRTUAL_ENV

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load project credentials without forwarding them to evaluated repositories.
if [[ -f "$PROJECT_ROOT/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_ROOT/.env"
    set +a
fi

if [[ ! -d "$SCRIPT_DIR/.venv" ]]; then
    if command -v uv >/dev/null 2>&1; then
        uv venv "$SCRIPT_DIR/.venv" >/dev/null
        uv pip install -p "$SCRIPT_DIR/.venv/bin/python" -q typer rich
    else
        python3 -m venv "$SCRIPT_DIR/.venv"
        "$SCRIPT_DIR/.venv/bin/pip" install -q typer rich
    fi
fi

export PYTHONPATH="${SCRIPT_DIR}:${PYTHONPATH:-}"

case "${1:-}" in
    evaluate|evaluate-repos)
        shift
        exec "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/evaluate_repos.py" "$@"
        ;;
    *)
        exec "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/github_search.py" "$@"
        ;;
esac
