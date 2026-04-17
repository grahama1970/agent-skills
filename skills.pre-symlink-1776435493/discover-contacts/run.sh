#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Enforce skill-local uv environment for python invocations.
shopt -s expand_aliases
alias python='uv run --project "$SCRIPT_DIR" python'
alias python3='uv run --project "$SCRIPT_DIR" python'


PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

cd "$SCRIPT_DIR"

# Ensure venv
if [[ ! -d .venv ]]; then
    uv venv .venv
    uv pip install -r pyproject.toml --python .venv/bin/python 2>/dev/null || true
fi

CMD="${1:-help}"
shift || true

case "$CMD" in
    research)
        .venv/bin/python -m discover_contacts research "$@"
        ;;
    company)
        .venv/bin/python -m discover_contacts company "$@"
        ;;
    enrich)
        .venv/bin/python -m discover_contacts enrich "$@"
        ;;
    freshness)
        .venv/bin/python -m discover_contacts freshness "$@"
        ;;
    export)
        .venv/bin/python -m discover_contacts export "$@"
        ;;
    help|--help|-h)
        echo "discover-contacts — Contact and prospect research"
        echo ""
        echo "Commands:"
        echo "  research <name> [--org <org>]   Research a single contact"
        echo "  company <name>                   Research a company"
        echo "  enrich <csv>                     Batch enrich a CSV contact list"
        echo "  freshness <csv>                  Check enrichment freshness"
        echo "  export <csv> --format yaml       Export enriched profiles"
        echo ""
        echo "Options:"
        echo "  --concurrency N   Parallel /dogpile calls (default: 2)"
        echo "  --delay N         Seconds between batches (default: 10)"
        echo "  --budget N        Max /dogpile calls (default: 20)"
        ;;
    *)
        echo "Unknown command: $CMD (try: research, company, enrich, freshness, export)"
        exit 1
        ;;
esac
