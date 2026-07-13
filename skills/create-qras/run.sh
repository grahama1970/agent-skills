#!/usr/bin/env bash
# /create-qras CLI entry point
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case "${1:-help}" in
    generate)
        shift
        python3 "$SCRIPT_DIR/generator.py" generate "$@"
        ;;
    manifest)
        shift
        python3 "$SCRIPT_DIR/generator.py" manifest "$@"
        ;;
    review)
        shift
        python3 "$SCRIPT_DIR/generator.py" review "$@"
        ;;
    f36-review)
        shift
        python3 "$SCRIPT_DIR/f36_requirement_qra.py" review "$@"
        ;;
    f36-webgpt-export)
        shift
        python3 "$SCRIPT_DIR/f36_requirement_qra.py" webgpt-export "$@"
        ;;
    f36-webgpt-import)
        shift
        python3 "$SCRIPT_DIR/f36_requirement_qra.py" webgpt-import "$@"
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
    ./run.sh manifest <path> [OPTIONS]
    ./run.sh review <path> [OPTIONS]
    ./run.sh f36-review <manifest.json> --output <review.json>
    ./run.sh f36-webgpt-export <manifest.json> --batch-ordinal N --batch-size N --output-dir <dir>
    ./run.sh f36-webgpt-import <requirements.json> <complete-family.json> \
        --accepted-output <accepted.json> --quarantine-output <quarantine.json> --receipt <receipt.json> \
        [--transport-receipt <webgpt-transport-receipt.json>]
    ./run.sh list-sources
    ./run.sh stats

F36 WEBGPT EXPORT
    Selects immutable F36 manifest rows in stable order and writes:
      request.md
      requirements.json
      export-receipt.json

F36 WEBGPT IMPORT
    Validates a closed complete-family batch. Any missing, duplicate, malformed,
    expanded, authority-bearing, or SPARTA-resolved family rejects the entire
    batch and writes durable per-family quarantine reasons. The importer makes
    no SciLLM, Chutes, OpenCode, or other model-provider calls.

MANIFEST OPTIONS:
    <path>               Path to execution manifest JSON
    --limit N            Max jobs to process (0=all)
    --prompt-kind NAME   Filter by prompt_kind
    --dry-run            Show what would be processed
    --skip-review        Skip review gate check

REVIEW OPTIONS:
    <path>               Path to execution manifest JSON
    -o, --output FILE    Output path for review JSON

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
    ./run.sh generate --control CWE-79
    ./run.sh generate --control AC-17
    ./run.sh generate --doc sparta_url_knowledge/doc123
    ./run.sh generate --framework nist --limit 100
    ./run.sh generate --control CWE-79 --dry-run
    ./run.sh f36-webgpt-export manifest.json --batch-ordinal 1 --batch-size 200 --output-dir ./webgpt-r01
    ./run.sh f36-webgpt-import ./webgpt-r01/requirements.json ./downloads/complete-family.json \
      --accepted-output ./webgpt-r01/accepted.json \
      --quarantine-output ./webgpt-r01/quarantine.json \
      --receipt ./webgpt-r01/import-receipt.json
EOF
        ;;
    *)
        echo "Unknown command: $1" >&2
        echo "Run './run.sh help' for usage" >&2
        exit 1
        ;;
esac
