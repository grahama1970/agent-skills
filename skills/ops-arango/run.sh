#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# Unified entry point for ops-arango skill
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

usage() {
    cat <<EOF
ops-arango: ArangoDB operations and maintenance

Commands:
  dump                   Create database backup with retention
  restore                Print the recommended native arangorestore command
  check [--json]         Run all health checks
  health-check [-m|--markdown] [-o FILE]  SPARTA data integrity (26 checks)
  embeddings [--fix]     Find/fix documents missing embeddings
  duplicates [--report]  Detect duplicate lessons
  orphans [--fix]        Find/fix orphaned edges
  integrity              Verify referential integrity
  stats [--json]         Collection statistics
  full [--fix] [--json]  Full maintenance cycle
  url-coverage [-o FILE] URL content coverage audit

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
  ./run.sh restore
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
    restore)
        cat <<EOF
ops-arango does not automate restores yet.

Use native arangorestore directly and keep progress/logging explicit:

  arangorestore \\
    --progress true \\
    --log.level info \\
    --server.endpoint tcp://127.0.0.1:8529 \\
    --server.username "\${ARANGO_USER:-root}" \\
    --server.password "\$ARANGO_PASS" \\
    --server.database "\${ARANGO_DB:-memory}" \\
    --input-directory /path/to/dump \\
    --overwrite true

When docker exec is unreliable on large restores, prefer:
  docker run --rm --network container:<arangodb-container> -v /path/to/backups:/backups arangodb/arangodb:3.12.6 arangorestore ...

See:
  skills/ops-arango/SKILL.md
  skills/best-practices-arangodb/SKILL.md
EOF
        exit 2
        ;;
    check|health-check|embeddings|duplicates|orphans|integrity|stats|coverage|full|url-coverage)
        # --json is a global Typer callback option on maintain.py; it must
        # precede the subcommand. Hoist it so `run.sh check --json` works.
        JSON_FLAG=()
        REST=()
        for a in "$@"; do
            case "$a" in
                --json) JSON_FLAG=(--json) ;;
                *) REST+=("$a") ;;
            esac
        done
        exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/maintain.py" \
            ${JSON_FLAG[@]+"${JSON_FLAG[@]}"} "$CMD" ${REST[@]+"${REST[@]}"}
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
