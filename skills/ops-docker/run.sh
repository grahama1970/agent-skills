#!/usr/bin/env bash
# Unified entry point for ops-docker skill
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    cat <<EOF
ops-docker: Safe Docker cleanup and compose stack management

Commands:
  prune [options]      Prune unused Docker resources (containers, images, volumes)
  redeploy [options]   Redeploy Docker Compose stack with optional service selection

Options for prune:
  --until <duration>   Only prune resources unused since duration (e.g. 24h)
  --execute            Actually prune (default is dry-run)
  --help               Show this message

Options for redeploy:
  --stack <file>       Compose file to use (default: docker-compose.yml)
  --service <name>     Limit operations to the given service (repeatable)
  --health-cmd <cmd>   Command to run after restart to verify health
  --execute            Actually redeploy (default is dry-run)
  --help               Show this message

Environment:
  DOCKER_PRUNE_UNTIL   Default value for prune --until
  STACK_FILE           Default compose file for redeploy
  HEALTH_CMD           Default health command for redeploy

Examples:
  ./run.sh prune
  ./run.sh prune --until 24h --execute
  ./run.sh redeploy --stack docker-compose.yml
  ./run.sh redeploy --stack docker-compose.yml --service web --execute
EOF
}

if [[ $# -lt 1 ]]; then
    usage
    exit 1
fi

CMD="$1"
shift

case "$CMD" in
    prune)
        exec "$SCRIPT_DIR/scripts/prune.sh" "$@"
        ;;
    redeploy)
        exec "$SCRIPT_DIR/scripts/redeploy.sh" "$@"
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
