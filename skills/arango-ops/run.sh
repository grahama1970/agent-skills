#!/usr/bin/env bash
# Unified entry point for arango-ops skill
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    cat <<EOF
arango-ops: ArangoDB operations and maintenance

Commands:
  dump                   Create database backup with retention
  check [--json]         Run all health checks
  embeddings [--fix]     Find/fix documents missing embeddings
  duplicates [--report]  Detect duplicate lessons
  orphans [--fix]        Find/fix orphaned edges
  integrity              Verify referential integrity
  stats [--json]         Collection statistics
  full [--fix] [--json]  Full maintenance cycle

Environment:
  ARANGO_URL       ArangoDB endpoint (default: http://127.0.0.1:8529)
  ARANGO_DB        Database name (default: memory)
  ARANGO_USER      Username
  ARANGO_PASS      Password
  CONTAINER        Docker container name (for dump)
  RETENTION_N      Backups to keep (default: 7)
  EMBEDDING_SERVICE_URL  Required for embeddings --fix
  DRY_RUN          Set to 1 for preview mode

Examples:
  ./run.sh dump
  ./run.sh check --json
  ./run.sh embeddings --fix
  ./run.sh full --fix
EOF
}

if [[ $# -lt 1 ]]; then
    usage
    exit 1
fi

CMD="$1"
shift

case "$CMD" in
    dump|backup)
        exec "$SCRIPT_DIR/scripts/dump.sh" "$@"
        ;;
    check|embeddings|duplicates|orphans|integrity|stats|full)
        exec python3 "$SCRIPT_DIR/scripts/maintain.py" "$CMD" "$@"
        ;;
    -h|--help|help)
        usage
        exit 0
        ;;
    *)
        echo "Unknown command: $CMD" >&2
        usage
        exit 1
        ;;
esac
