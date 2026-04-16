#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# Unified entry point for ops-docker skill
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

EMBRY_COMPOSE="docker compose -f $PROJECT_ROOT/docker-compose.yml"

usage() {
    cat <<EOF
ops-docker: Docker cleanup, compose stack management, and Embry infrastructure ops

Commands:
  prune [options]      Prune unused Docker resources (containers, images, volumes)
  redeploy [options]   Redeploy Docker Compose stack with optional service selection
  status               Show status of all embry-* containers
  logs <service>       Tail logs for an embry infrastructure service
  dev                  Start infrastructure with dev bind-mounts (override file)
  rebuild <service>    Rebuild and restart a specific embry container

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
  ./run.sh status
  ./run.sh logs embedding
  ./run.sh rebuild scillm
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
    status)
        echo "=== Embry Infrastructure Containers ==="
        docker ps --filter "name=embry-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
        echo ""
        echo "=== Resource Usage ==="
        docker stats --no-stream --filter "name=embry-" --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" 2>/dev/null || true
        ;;
    logs)
        if [[ $# -lt 1 ]]; then
            echo "Usage: ./run.sh logs <service>" >&2
            exit 1
        fi
        $EMBRY_COMPOSE logs -f "$1"
        ;;
    dev)
        echo "Starting infrastructure with dev overrides..."
        $EMBRY_COMPOSE -f "$PROJECT_ROOT/docker-compose.override.yml" up -d --wait
        echo "Infrastructure ready."
        ;;
    rebuild)
        if [[ $# -lt 1 ]]; then
            echo "Usage: ./run.sh rebuild <service>" >&2
            exit 1
        fi
        SERVICE="$1"
        echo "Rebuilding $SERVICE..."
        $EMBRY_COMPOSE build --no-cache "$SERVICE"
        $EMBRY_COMPOSE up -d "$SERVICE"
        echo "$SERVICE rebuilt and restarted."
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
