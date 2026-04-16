#!/usr/bin/env bash
# List installed Ollama models via Docker
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FORMAT="human"
USE_API=0

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

List installed Ollama models from Docker container.

Options:
  --format human|json   Output format (default: human)
  --api                 Use HTTP API instead of CLI
  --help                Show this help message

Examples:
  # List models (human-readable)
  $(basename "$0")

  # List models as JSON
  $(basename "$0") --format json

  # List via HTTP API
  $(basename "$0") --api --format json
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --format)
      FORMAT="$2"
      shift 2
      ;;
    --api)
      USE_API=1
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

# Validate format
if [[ "$FORMAT" != "human" && "$FORMAT" != "json" ]]; then
  echo "Error: Invalid format '$FORMAT'. Must be 'human' or 'json'" >&2
  exit 1
fi

# Check if container is running
if ! docker ps --filter "name=scillm-ollama" --format "{{.Names}}" | grep -q "scillm-ollama"; then
  echo "Error: scillm-ollama container is not running" >&2
  exit 1
fi

if [[ $USE_API -eq 1 ]]; then
  # Use HTTP API
  if [[ "$FORMAT" == "json" ]]; then
    curl -s http://localhost:11434/api/tags
  else
    # Parse JSON for human output
    curl -s http://localhost:11434/api/tags | \
      jq -r '.models[] | "\(.name)\t\(.size | tonumber / 1073741824 | floor)GB\t\(.modified_at)"'
  fi
else
  # Use Docker CLI
  if [[ "$FORMAT" == "json" ]]; then
    # Convert CLI output to JSON
    docker exec scillm-ollama ollama list --format json 2>/dev/null || \
    {
      # Fallback: parse text output to JSON
      docker exec scillm-ollama ollama list | tail -n +2 | \
      awk 'BEGIN{print "{"}
           {printf "%s{\"name\":\"%s\",\"id\":\"%s\",\"size\":\"%s\",\"modified\":\"%s %s %s\"}",
                   (NR>1?",":""), $1, $2, $3, $4, $5, $6}
           END{print "}"}' | \
      jq -s '{"models": .}'
    }
  else
    docker exec scillm-ollama ollama list
  fi
fi
