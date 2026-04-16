#!/usr/bin/env bash
# Pull an Ollama model via Docker
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL=""
DRY_RUN=0
USE_API=0

usage() {
  cat <<USAGE
Usage: $(basename "$0") <model-name> [options]

Pull an Ollama model from registry into Docker container.

Arguments:
  model-name            Model to pull (e.g., llama3.2:1b)

Options:
  --dry-run             Show command without executing
  --api                 Use HTTP API instead of CLI
  --help                Show this help message

Examples:
  # Pull a model
  $(basename "$0") llama3.2:1b

  # Dry-run (show command only)
  $(basename "$0") llama3.2:1b --dry-run

  # Pull via HTTP API
  $(basename "$0") llama3.2:1b --api
USAGE
}

# Parse arguments
if [[ $# -eq 0 ]]; then
  usage
  exit 1
fi

MODEL="$1"
shift

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
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

# Validate model name
if [[ -z "$MODEL" ]]; then
  echo "Error: Model name required" >&2
  usage
  exit 1
fi

# Check if container is running
if ! docker ps --filter "name=scillm-ollama" --format "{{.Names}}" | grep -q "scillm-ollama"; then
  echo "Error: scillm-ollama container is not running" >&2
  exit 1
fi

if [[ $DRY_RUN -eq 1 ]]; then
  if [[ $USE_API -eq 1 ]]; then
    echo "curl -X POST http://localhost:11434/api/pull -H 'Content-Type: application/json' -d '{\"name\": \"$MODEL\"}'"
  else
    echo "docker exec scillm-ollama ollama pull $MODEL"
  fi
  exit 0
fi

if [[ $USE_API -eq 1 ]]; then
  # Use HTTP API (streaming response)
  curl -X POST http://localhost:11434/api/pull \
    -H "Content-Type: application/json" \
    -d "{\"name\": \"$MODEL\"}" \
    --no-buffer
else
  # Use Docker CLI
  docker exec -it scillm-ollama ollama pull "$MODEL"
fi
