#!/usr/bin/env bash
# /create-qras CLI entry point
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case "${1:-help}" in
    generate)
        shift
        python3 "$SCRIPT_DIR/generator.py" generate "$@"
        ;;
    list-sources)
        python3 "$SCRIPT_DIR/generator.py" list-sources
        ;;
    stats)
        python3 "$SCRIPT_DIR/generator.py" stats
        ;;
    help|--help|-h)
        cat <<'EOF'
/create-qras - Generate QRA pairs from controls, documents, or text

USAGE:
    ./run.sh generate [OPTIONS]
    ./run.sh list-sources
    ./run.sh stats

GENERATE OPTIONS:
    --control ID         Generate QRAs for a specific control (CWE-79, SV-AC-2, AC-17, etc.)
    --source ID          Source control for relationship QRA
    --target ID          Target control for relationship QRA
    --doc KEY            Document key from sparta_url_knowledge
    --collection NAME    Process all docs in collection (default limit: 50)
    --text "..."         Generate from raw text
    --framework NAME     Batch generate for framework (cwe, capec, nist, sparta)
    --limit N            Limit batch size (default: 50)
    --dry-run            Show what would be generated without storing
    --no-verify          Skip /create-evidence-case verification
    --store              Store to sparta_qra (default: true)
    --output FILE        Write results to JSON file

EXAMPLES:
    # Relationship QRA from CWE (uses /create-evidence-case for crosswalk)
    ./run.sh generate --control CWE-79

    # Independent QRA for NIST control (no technique mapping needed)
    ./run.sh generate --control AC-17

    # Standalone QRA from URL knowledge document
    ./run.sh generate --doc sparta_url_knowledge/doc123

    # Batch generate for framework
    ./run.sh generate --framework nist --limit 100

    # Dry run to preview
    ./run.sh generate --control CWE-79 --dry-run
EOF
        ;;
    *)
        echo "Unknown command: $1" >&2
        echo "Run './run.sh help' for usage" >&2
        exit 1
        ;;
esac
