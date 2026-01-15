#!/usr/bin/env bash
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

# Pass through to treesitter-tools via uvx
exec uvx --from "$TREESITTER_REPO" treesitter-tools "$@"
