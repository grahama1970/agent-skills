#!/usr/bin/env bash
# Check Docker-based Ollama service status
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE="ollama"
FORMAT="human"

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Check status of Docker-based Ollama service.

Options:
  --service ollama       Service to check (default: ollama)
  --format human|json    Output format (default: human)
  --help                 Show this help message

Examples:
  # Check Ollama status
  $(basename "$0")

  # Check status as JSON
  $(basename "$0") --format json
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --service)
      SERVICE="$2"
      shift 2
      ;;
    --format)
      FORMAT="$2"
      shift 2
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

# Validate format
if [[ "$FORMAT" != "human" && "$FORMAT" != "json" ]]; then
  echo "Error: Invalid format '$FORMAT'. Must be 'human' or 'json'" >&2
  exit 1
fi

# Determine container name based on service
case "$SERVICE" in
  ollama)
    CONTAINER="scillm-ollama"
    ;;
  *)
    echo "Error: Unknown service '$SERVICE'" >&2
    exit 1
    ;;
esac

# Get container status
if docker ps --filter "name=$CONTAINER" --format "{{.Names}}" | grep -q "$CONTAINER"; then
  STATUS="running"
  PID=$(docker inspect -f '{{.State.Pid}}' "$CONTAINER" 2>/dev/null || echo "")
  UPTIME=$(docker inspect -f '{{.State.StartedAt}}' "$CONTAINER" 2>/dev/null || echo "")
  HEALTH=$(docker inspect -f '{{.State.Health.Status}}' "$CONTAINER" 2>/dev/null || echo "none")

  if [[ "$FORMAT" == "json" ]]; then
    jq -n \
      --arg status "$STATUS" \
      --arg pid "$PID" \
      --arg container "$CONTAINER" \
      --arg uptime "$UPTIME" \
      --arg health "$HEALTH" \
      '{status: $status, pid: $pid, container: $container, started_at: $uptime, health: $health}'
  else
    echo "Service: $SERVICE ($CONTAINER)"
    echo "Status: $STATUS"
    [[ -n "$PID" ]] && echo "PID: $PID"
    echo "Started: $UPTIME"
    [[ "$HEALTH" != "none" ]] && echo "Health: $HEALTH"
  fi
elif docker ps -a --filter "name=$CONTAINER" --format "{{.Names}}" | grep -q "$CONTAINER"; then
  STATUS="stopped"

  if [[ "$FORMAT" == "json" ]]; then
    jq -n \
      --arg status "$STATUS" \
      --arg container "$CONTAINER" \
      '{status: $status, container: $container}'
  else
    echo "Service: $SERVICE ($CONTAINER)"
    echo "Status: $STATUS"
  fi
else
  STATUS="not_found"

  if [[ "$FORMAT" == "json" ]]; then
    jq -n \
      --arg status "$STATUS" \
      --arg container "$CONTAINER" \
      '{status: $status, container: $container}'
  else
    echo "Service: $SERVICE ($CONTAINER)"
    echo "Status: Container not found"
  fi
  exit 1
fi
