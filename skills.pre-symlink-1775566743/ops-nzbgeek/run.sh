#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# ops-nzbgeek dispatcher script
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

# Export PYTHONPATH to include skill directory
export PYTHONPATH="$SCRIPT_DIR:${PYTHONPATH:-}"

# Handle sanity command separately
if [[ "${1:-}" == "sanity" ]]; then
    echo "=== Running ops-nzbgeek sanity checks ==="
    bash "$SCRIPT_DIR/sanity.sh"
    exit $?
fi

# Handle help command
if [[ "${1:-}" == "help" ]] || [[ "${1:-}" == "--help" ]] || [[ "${1:-}" == "-h" ]] || [[ $# -eq 0 ]]; then
    cat <<EOF
ops-nzbgeek - General-Purpose NZBGeek/SABnzbd Integration

USAGE:
    ./run.sh <command> [options]

COMMANDS:
    search <query>              Search NZBGeek for content
    download <nzb_url>          Download via SABnzbd
    status [--nzb-id ID]        Check SABnzbd queue status
    pause <nzb_id>              Pause download
    resume <nzb_id>             Resume download
    cancel <nzb_id>             Cancel download
    sanity                      Run sanity checks
    help                        Show this help

SEARCH OPTIONS:
    --category <cat>            Category filter (movies, tv, music, apps, books, all)
    --limit <N>                 Max results (default: 10)
    --json                      Output JSON

DOWNLOAD OPTIONS:
    --monitor                   Enable task-monitor progress tracking
    --dry-run                   Show API call without executing
    --category <cat>            SABnzbd category
    --priority <0-2>            Priority (0=normal, 1=high, 2=force)

EXAMPLES:
    ./run.sh search "ubuntu iso" --category apps
    ./run.sh download "<nzb_url>" --monitor
    ./run.sh status
    ./run.sh pause <nzb_id>

ENVIRONMENT:
    NZBD_GEEK_API_KEY          NZBGeek API key
    NZBD_GEEK_BASE_URL         NZBGeek API URL
    SABNZBD_API_KEY            SABnzbd API key
    SABNZBD_BASE_URL           SABnzbd API URL

See SKILL.md for full documentation.
EOF
    exit 0
fi

# Delegate to Python CLI
uv run python -m ops_nzbgeek.cli "$@"
