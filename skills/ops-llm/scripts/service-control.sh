#!/usr/bin/env bash
# Control Docker-based Ollama service
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACTION=""
DRY_RUN=0

usage() {
  cat <<USAGE
Usage: $(basename "$0") --action <action> [options]

Control Docker-based Ollama service (container operations).

Options:
  --action <action>     Action to perform: status|start|stop|restart
  --dry-run             Show command without executing
  --help                Show this help message

Examples:
  # Check status
  $(basename "$0") --action status

  # Restart container (dry-run)
  $(basename "$0") --action restart --dry-run

  # Stop container
  $(basename "$0") --action stop

Note: start/stop/restart require appropriate Docker permissions
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --action)
      ACTION="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

# Validate action
if [[ -z "$ACTION" ]]; then
  echo "Error: --action required" >&2
  usage
  exit 1
fi

CONTAINER="scillm-ollama"

case "$ACTION" in
  status)
    # Status is read-only, just check
    "$SCRIPT_DIR/service-status.sh" --service ollama
    ;;
  start)
    if [[ $DRY_RUN -eq 1 ]]; then
      echo "docker start $CONTAINER"
    else
      echo "Starting $CONTAINER..."
      docker start "$CONTAINER"
      echo "Started successfully"
    fi
    ;;
  stop)
    if [[ $DRY_RUN -eq 1 ]]; then
      echo "docker stop $CONTAINER"
    else
      echo "Stopping $CONTAINER..."
      docker stop "$CONTAINER"
      echo "Stopped successfully"
    fi
    ;;
  restart)
    if [[ $DRY_RUN -eq 1 ]]; then
      echo "docker restart $CONTAINER"
    else
      echo "Restarting $CONTAINER..."
      docker restart "$CONTAINER"
      echo "Restarted successfully"
    fi
    ;;
  *)
    echo "Error: Invalid action '$ACTION'. Must be status|start|stop|restart" >&2
    exit 1
    ;;
esac
