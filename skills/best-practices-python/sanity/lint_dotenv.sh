#!/usr/bin/env bash
# lint_dotenv.sh — Detect Python entry points that call os.getenv() without loading dotenv.
#
# Usage:
#   bash lint_dotenv.sh [directory]             # defaults to .pi/skills/
#   bash lint_dotenv.sh [directory] --all       # check ALL files, not just entry points
#   bash lint_dotenv.sh [directory] --strict    # same as --all (alias)
#
# Exit codes:
#   0  All files OK
#   1  Violations found
#
# This enforces conventions-dotenv-required.md:
#   Entry point .py files (with __main__ or app()) that use os.getenv() must also
#   contain load_dotenv or dotenv_helper before the first usage.
#
# "Entry points" = files that are executed directly (not just imported).
# Detection: files containing `if __name__` or `app()` or `typer.run` or `click.command`.
set -euo pipefail

SEARCH_DIR="${1:-.pi/skills}"
CHECK_ALL=false
[[ "${2:-}" == "--all" || "${2:-}" == "--strict" ]] && CHECK_ALL=true

VIOLATIONS=0
ENTRY_VIOLATIONS=0
INTERIOR_VIOLATIONS=0
CHECKED=0

# Find all .py files that read env vars
while IFS= read -r pyfile; do
    # Skip __pycache__, .venv, test fixtures, vendored code
    [[ "$pyfile" == *__pycache__* ]] && continue
    [[ "$pyfile" == */.venv/* ]] && continue
    [[ "$pyfile" == */node_modules/* ]] && continue
    [[ "$pyfile" == */sanity/* ]] && continue

    # Check if file reads env vars
    if grep -qE 'os\.getenv\(|os\.environ\[|os\.environ\.get\(' "$pyfile" 2>/dev/null; then
        CHECKED=$((CHECKED + 1))

        # Check if file loads dotenv (any of the accepted patterns)
        if grep -qE 'load_dotenv|dotenv_helper|load_env' "$pyfile" 2>/dev/null; then
            : # OK
        else
            # Determine if this is an entry point or interior module
            is_entry=false
            if grep -qE 'if __name__|\.run\(|app\(\)|@click\.command|@app\.command' "$pyfile" 2>/dev/null; then
                is_entry=true
            fi
            # config.py files are also critical (imported early, set module-level vars)
            if [[ "$(basename "$pyfile")" == "config.py" ]]; then
                is_entry=true
            fi

            if $is_entry; then
                echo "ENTRY POINT VIOLATION: $pyfile"
                echo "  Uses os.getenv() but never loads dotenv."
                echo "  Fix: Add load_dotenv(find_dotenv(usecwd=True), override=False)"
                echo ""
                ENTRY_VIOLATIONS=$((ENTRY_VIOLATIONS + 1))
                VIOLATIONS=$((VIOLATIONS + 1))
            elif $CHECK_ALL; then
                echo "INTERIOR VIOLATION: $pyfile"
                echo "  Uses os.getenv() but never loads dotenv."
                echo ""
                INTERIOR_VIOLATIONS=$((INTERIOR_VIOLATIONS + 1))
                VIOLATIONS=$((VIOLATIONS + 1))
            fi
        fi
    fi
done < <(find "$SEARCH_DIR" -name '*.py' -type f 2>/dev/null)

echo "---"
echo "Checked $CHECKED files that read environment variables."
echo "Entry point violations: $ENTRY_VIOLATIONS"
if $CHECK_ALL; then
    echo "Interior module violations: $INTERIOR_VIOLATIONS"
fi
echo "Total violations: $VIOLATIONS"

if [ "$ENTRY_VIOLATIONS" -gt 0 ]; then
    echo ""
    echo "FAIL: $ENTRY_VIOLATIONS entry point(s) missing dotenv loading."
    echo "See: best-practices-python/rules/conventions-dotenv-required.md"
    exit 1
elif [ "$VIOLATIONS" -gt 0 ] && $CHECK_ALL; then
    echo ""
    echo "WARN: $INTERIOR_VIOLATIONS interior module(s) missing dotenv loading."
    echo "These are lower priority but should be fixed for standalone usage."
    exit 1
else
    echo ""
    echo "PASS: All entry points load dotenv before reading env vars."
    exit 0
fi
