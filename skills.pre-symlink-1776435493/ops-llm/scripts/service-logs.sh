#!/usr/bin/env bash
# View Docker-based Ollama service logs
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LINES=100
FOLLOW=0

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

View logs for Docker-based Ollama service.

Options:
  --lines <n>           Number of lines to show (default: 100)
  --follow              Follow log output (tail -f behavior)
  --help                Show this help message

Examples:
  # Show last 100 lines
  $(basename "$0")

  # Show last 10 lines
  $(basename "$0") --lines 10

  # Follow logs in real-time
  $(basename "$0") --follow
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --lines)
      LINES="$2"
      shift 2
      ;;
    --follow|-f)
      FOLLOW=1
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

CONTAINER="scillm-ollama"

# Check if container exists
if ! docker ps -a --filter "name=$CONTAINER" --format "{{.Names}}" | grep -q "$CONTAINER"; then
  echo "Error: Container $CONTAINER not found" >&2
  exit 1
fi

# View logs
if [[ $FOLLOW -eq 1 ]]; then
  docker logs "$CONTAINER" --follow --tail "$LINES"
else
  docker logs "$CONTAINER" --tail "$LINES"
fi
