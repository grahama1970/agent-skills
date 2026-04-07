#!/usr/bin/env bash
# Monitor Ollama performance metrics
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FORMAT="human"

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Monitor Ollama performance metrics (GPU, running models, container stats).

Options:
  --format human|json   Output format (default: human)
  --help                Show this help message

Examples:
  # Show performance metrics
  $(basename "$0")

  # Show as JSON
  $(basename "$0") --format json
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
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

CONTAINER="scillm-ollama"

# Check if nvidia-smi is available
HAS_GPU=0
if command -v nvidia-smi &> /dev/null; then
  HAS_GPU=1
fi

# Get running models
RUNNING_MODELS=$(curl -s http://localhost:11434/api/ps 2>/dev/null || echo '{"models":[]}')

# Get container stats
CONTAINER_STATS=$(docker stats "$CONTAINER" --no-stream --format "{{.CPUPerc}},{{.MemUsage}},{{.NetIO}},{{.BlockIO}}" 2>/dev/null || echo "0%,0B / 0B,0B / 0B,0B / 0B")

if [[ "$FORMAT" == "json" ]]; then
  # Build JSON output
  JSON_OUTPUT='{"container": "'$CONTAINER'"'

  # Add container stats
  IFS=',' read -r cpu mem net block <<< "$CONTAINER_STATS"
  JSON_OUTPUT+=', "container_stats": {"cpu": "'$cpu'", "memory": "'$mem'", "network": "'$net'", "block_io": "'$block'"}'

  # Add running models
  JSON_OUTPUT+=', "running_models": '$RUNNING_MODELS

  # Add GPU info if available
  if [[ $HAS_GPU -eq 1 ]]; then
    GPU_INFO=$(nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits 2>/dev/null || echo "")
    if [[ -n "$GPU_INFO" ]]; then
      GPU_JSON='['
      while IFS=',' read -r index name mem_used mem_total util; do
        [[ "$GPU_JSON" != '[' ]] && GPU_JSON+=','
        GPU_JSON+='{"index":'$index',"name":"'"$(echo $name | xargs)"'","memory_used_mb":'$mem_used',"memory_total_mb":'$mem_total',"utilization_pct":'$util'}'
      done <<< "$GPU_INFO"
      GPU_JSON+=']'
      JSON_OUTPUT+=', "gpus": '$GPU_JSON
    fi
  fi

  JSON_OUTPUT+='}'
  echo "$JSON_OUTPUT" | jq
else
  # Human-readable output
  echo "=== Ollama Performance Monitor ==="
  echo
  echo "Container: $CONTAINER"

  # Container stats
  IFS=',' read -r cpu mem net block <<< "$CONTAINER_STATS"
  echo "CPU: $cpu"
  echo "Memory: $mem"
  echo "Network: $net"
  echo "Block I/O: $block"
  echo

  # Running models
  MODEL_COUNT=$(echo "$RUNNING_MODELS" | jq '.models | length' 2>/dev/null || echo 0)
  echo "Running Models: $MODEL_COUNT"
  if [[ $MODEL_COUNT -gt 0 ]]; then
    echo "$RUNNING_MODELS" | jq -r '.models[] | "  - \(.name) (\(.size / 1073741824 | floor)GB)"' 2>/dev/null || echo "  (unable to parse)"
  fi
  echo

  # GPU info
  if [[ $HAS_GPU -eq 1 ]]; then
    echo "=== GPU Status ==="
    nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu --format=table 2>/dev/null || echo "GPU info unavailable"
  else
    echo "GPU: Not available (nvidia-smi not found)"
  fi
fi
