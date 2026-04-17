#!/usr/bin/env bash
# Show details for an Ollama model via Docker
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL=""
FORMAT="human"
USE_API=0

usage() {
  cat <<USAGE
Usage: $(basename "$0") <model-name> [options]

Show detailed information for an Ollama model.

Arguments:
  model-name            Model to inspect (e.g., llama3.2:1b)

Options:
  --format human|json   Output format (default: human)
  --api                 Use HTTP API instead of CLI
  --help                Show this help message

Examples:
  # Show model details
  $(basename "$0") llama3.2:1b

  # Show as JSON
  $(basename "$0") llama3.2:1b --format json

  # Show via HTTP API
  $(basename "$0") llama3.2:1b --api --format json
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

if [[ $USE_API -eq 1 ]]; then
  # Use HTTP API
  response=$(curl -s -X POST http://localhost:11434/api/show \
    -H "Content-Type: application/json" \
    -d "{\"name\": \"$MODEL\"}")

  if [[ "$FORMAT" == "json" ]]; then
    echo "$response" | jq
  else
    # Parse JSON for human output
    echo "Model: $MODEL"
    echo "$response" | jq -r '
      "Format: \(.details.format)",
      "Family: \(.details.family)",
      "Parameter Size: \(.details.parameter_size)",
      "Quantization: \(.details.quantization_level)",
      "Model File: \(.modelfile | split("\n") | length) lines"
    '
  fi
else
  # Use Docker CLI
  if [[ "$FORMAT" == "json" ]]; then
    # Try to get structured output, fallback to text
    docker exec scillm-ollama ollama show "$MODEL" --format json 2>/dev/null || \
      docker exec scillm-ollama ollama show "$MODEL"
  else
    docker exec scillm-ollama ollama show "$MODEL"
  fi
fi
