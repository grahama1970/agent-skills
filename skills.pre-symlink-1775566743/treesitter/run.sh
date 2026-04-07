#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# Treesitter skill runner - uses uvx for auto-install
#
# Usage:
#   ./run.sh symbols /path/to/file.py
#   ./run.sh symbols /path/to/file.py --content
#   ./run.sh scan /path/to/dir
#   ./run.sh parse --language python --code "def foo(): pass"
#
# Output is JSON by default.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi
TREESITTER_REPO="git+https://github.com/grahama1970/treesitter-tools.git"

# Handle special "parse" command for code snippets
if [[ "${1:-}" == "parse" ]]; then
    shift
    LANGUAGE=""
    CODE=""
    CONTENT_FLAG=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --language)
                LANGUAGE="$2"
                shift 2
                ;;
            --code)
                CODE="$2"
                shift 2
                ;;
            --content|-c)
                CONTENT_FLAG="--content"
                shift
                ;;
            *)
                shift
                ;;
        esac
    done

    if [[ -z "$CODE" ]]; then
        echo '{"error": "Must provide --code argument"}' >&2
        exit 1
    fi

    # Write code to temp file with appropriate extension
    EXT="txt"
    case "$LANGUAGE" in
        python|py) EXT="py" ;;
        javascript|js) EXT="js" ;;
        typescript|ts) EXT="ts" ;;
        rust|rs) EXT="rs" ;;
        go) EXT="go" ;;
        java) EXT="java" ;;
        c) EXT="c" ;;
        cpp|c++) EXT="cpp" ;;
        ruby|rb) EXT="rb" ;;
        bash|sh) EXT="sh" ;;
    esac

    TMPFILE=$(mktemp "/tmp/treesitter_snippet.XXXXXX.$EXT")
    echo "$CODE" > "$TMPFILE"
    trap "rm -f $TMPFILE" EXIT

    # Run symbols on temp file (output is JSON by default)
    exec uvx --from "$TREESITTER_REPO" treesitter-tools symbols "$TMPFILE" $CONTENT_FLAG
fi

# Prefer local dev install if available, fall back to uvx from GitHub
LOCAL_TREESITTER="/home/graham/workspace/experiments/treesitter-tools"
if [[ -f "$LOCAL_TREESITTER/.venv/bin/treesitter-tools" ]]; then
    exec "$LOCAL_TREESITTER/.venv/bin/treesitter-tools" "$@"
else
    exec uvx --from "$TREESITTER_REPO" treesitter-tools "$@"
fi
