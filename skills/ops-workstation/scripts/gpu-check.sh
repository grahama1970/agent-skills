#!/usr/bin/env bash
# GPU status check for AI agents - especially useful before model training.
# Provides clear signals about GPU memory availability and health.
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Check GPU status before model training or inference.
Provides clear guidance on whether GPU has enough memory.

Options:
  --need <MB>        Check if GPU has at least N MB free (exits 1 if not)
  --watch            Monitor GPU until memory stabilizes (useful after launching tasks)
  --processes        Show what's using the GPU
  --json             Output as JSON instead of markdown
  --help             Show this message

Agent Examples:
  $(basename "$0")                   # Quick GPU health check
  $(basename "$0") --need 8000       # Do I have 8GB free for training?
  $(basename "$0") --processes       # What's using my GPU?
  $(basename "$0") --watch           # Wait for GPU memory to stabilize

Exit Codes:
  0 = GPU healthy, sufficient resources
  1 = Warning - low memory or high temperature
  2 = Critical - GPU unavailable or insufficient memory for --need
USAGE
}

NEED_MB=0
WATCH_MODE=false
SHOW_PROCESSES=false
OUTPUT_FORMAT="markdown"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --need) NEED_MB="$2"; shift 2;;
    --watch) WATCH_MODE=true; shift;;
    --processes|-p) SHOW_PROCESSES=true; shift;;
    --json) OUTPUT_FORMAT="json"; shift;;
    --help|-h) usage; exit 0;;
    *) echo "Unknown option: $1" >&2; usage; exit 1;;
  esac
done

# Check if nvidia-smi is available
if ! command -v nvidia-smi &>/dev/null; then
  echo "## GPU Check"
  echo ""
  echo "**Status:** No NVIDIA GPU detected (nvidia-smi not found)"
  echo ""
  echo "If you have a GPU, ensure NVIDIA drivers are installed."
  exit 2
fi

# Get GPU info
get_gpu_info() {
  nvidia-smi --query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu,power.draw,power.limit \
    --format=csv,noheader,nounits 2>/dev/null
}

# Get processes using GPU
get_gpu_processes() {
  nvidia-smi --query-compute-apps=gpu_uuid,pid,used_memory,name \
    --format=csv,noheader 2>/dev/null || true
}

# Wait for GPU memory to stabilize
watch_gpu() {
  local prev_mem=0
  local stable_count=0
  local max_wait=60  # Max 60 seconds

  echo "Monitoring GPU memory..." >&2

  for ((i=0; i<max_wait; i++)); do
    local current_mem
    current_mem=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1 | xargs)

    if [[ "$current_mem" == "$prev_mem" ]]; then
      ((stable_count++))
      if [[ $stable_count -ge 3 ]]; then
        echo "GPU memory stabilized at ${current_mem} MiB" >&2
        return 0
      fi
    else
      stable_count=0
      prev_mem=$current_mem
    fi

    sleep 1
  done

  echo "Warning: GPU memory did not stabilize after ${max_wait}s" >&2
  return 1
}

# Determine status and exit code
determine_status() {
  local mem_free=$1
  local mem_total=$2
  local temp=$3
  local need=$4

  local exit_code=0
  local status="OK"
  local message=""

  local free_pct=$((mem_free * 100 / mem_total))

  # Check if we have enough for --need
  if [[ $need -gt 0 && $mem_free -lt $need ]]; then
    status="INSUFFICIENT"
    message="Need ${need} MiB but only ${mem_free} MiB free. "
    exit_code=2
  fi

  # Temperature warning
  if [[ $temp -ge 85 ]]; then
    status="WARNING"
    message+="Temperature critical (${temp}°C). "
    [[ $exit_code -lt 1 ]] && exit_code=1
  elif [[ $temp -ge 75 ]]; then
    [[ "$status" == "OK" ]] && status="WARNING"
    message+="Temperature elevated (${temp}°C). "
    [[ $exit_code -lt 1 ]] && exit_code=1
  fi

  # Memory pressure warning
  if [[ $free_pct -lt 10 && $need -eq 0 ]]; then
    status="WARNING"
    message+="GPU memory very low (${free_pct}% free). "
    [[ $exit_code -lt 1 ]] && exit_code=1
  fi

  [[ -z "$message" ]] && message="GPU healthy with ${mem_free} MiB (${free_pct}%) free."

  echo "$exit_code|$status|$message"
}

# Training recommendations based on free memory
get_training_recommendation() {
  local mem_free=$1

  if [[ $mem_free -ge 20000 ]]; then
    echo "Can train: Large models (LLaMA-70B LoRA, SD-XL fine-tune)"
  elif [[ $mem_free -ge 12000 ]]; then
    echo "Can train: Medium models (LLaMA-7B full, Whisper-large)"
  elif [[ $mem_free -ge 8000 ]]; then
    echo "Can train: Small models (Whisper-medium, LoRA adapters)"
  elif [[ $mem_free -ge 4000 ]]; then
    echo "Can train: Tiny models only, or inference-only workloads"
  else
    echo "CRITICAL: Insufficient GPU memory for most training tasks"
  fi
}

# Output markdown
output_markdown() {
  echo "## GPU Status"
  echo ""
  echo "**Checked:** $(date '+%Y-%m-%d %H:%M:%S')"
  echo ""

  local gpu_data exit_code status message
  local name mem_total mem_used mem_free util temp power_draw power_limit

  while IFS=',' read -r idx name mem_total mem_used mem_free util temp power_draw power_limit; do
    # Trim whitespace
    name=$(echo "$name" | xargs)
    mem_total=$(echo "$mem_total" | xargs)
    mem_used=$(echo "$mem_used" | xargs)
    mem_free=$(echo "$mem_free" | xargs)
    util=$(echo "$util" | xargs)
    temp=$(echo "$temp" | xargs)
    power_draw=$(echo "$power_draw" | xargs)
    power_limit=$(echo "$power_limit" | xargs)

    # Get status
    IFS='|' read -r exit_code status message < <(determine_status "$mem_free" "$mem_total" "$temp" "$NEED_MB")

    echo "### GPU $idx: $name"
    echo ""
    echo "| Metric | Value |"
    echo "|--------|-------|"
    echo "| Memory Total | ${mem_total} MiB |"
    echo "| Memory Used | ${mem_used} MiB |"
    echo "| Memory Free | **${mem_free} MiB** |"
    echo "| Utilization | ${util}% |"
    echo "| Temperature | ${temp}°C |"
    echo "| Power | ${power_draw}W / ${power_limit}W |"
    echo ""
    echo "**Status:** $status"
    echo ""
    echo "$message"
    echo ""

    # Training recommendation
    echo "**Training Capacity:** $(get_training_recommendation "$mem_free")"
    echo ""

    # Show processes if requested or if memory is low
    if [[ "$SHOW_PROCESSES" == "true" ]] || [[ $mem_free -lt 4000 ]]; then
      echo "### GPU Processes"
      echo ""
      local procs
      procs=$(get_gpu_processes)
      if [[ -n "$procs" ]]; then
        echo "| PID | Memory | Process |"
        echo "|-----|--------|---------|"
        echo "$procs" | while IFS=',' read -r uuid pid mem proc; do
          pid=$(echo "$pid" | xargs)
          mem=$(echo "$mem" | xargs)
          proc=$(echo "$proc" | xargs | rev | cut -d'/' -f1 | rev | head -c 40)
          echo "| $pid | $mem | $proc |"
        done
        echo ""
        echo "To free memory, kill processes: \`kill -15 <PID>\`"
      else
        echo "No GPU processes running."
      fi
      echo ""
    fi

  done < <(get_gpu_info)

  # Return appropriate exit code
  return "${exit_code:-0}"
}

# Output JSON
output_json() {
  echo "{"
  echo "  \"timestamp\": \"$(date -Iseconds)\","
  echo "  \"gpus\": ["

  local first=true
  while IFS=',' read -r idx name mem_total mem_used mem_free util temp power_draw power_limit; do
    $first || echo ","
    first=false

    name=$(echo "$name" | xargs)
    mem_total=$(echo "$mem_total" | xargs)
    mem_used=$(echo "$mem_used" | xargs)
    mem_free=$(echo "$mem_free" | xargs)
    util=$(echo "$util" | xargs)
    temp=$(echo "$temp" | xargs)

    IFS='|' read -r exit_code status message < <(determine_status "$mem_free" "$mem_total" "$temp" "$NEED_MB")

    echo -n "    {"
    echo -n "\"index\": $idx, "
    echo -n "\"name\": \"$name\", "
    echo -n "\"memory_total_mib\": $mem_total, "
    echo -n "\"memory_used_mib\": $mem_used, "
    echo -n "\"memory_free_mib\": $mem_free, "
    echo -n "\"utilization_pct\": $util, "
    echo -n "\"temperature_c\": $temp, "
    echo -n "\"status\": \"$status\", "
    echo -n "\"message\": \"$message\""
    echo -n "}"

  done < <(get_gpu_info)

  echo ""
  echo "  ]"
  echo "}"
}

# Main
if [[ "$WATCH_MODE" == "true" ]]; then
  watch_gpu
fi

if [[ "$OUTPUT_FORMAT" == "json" ]]; then
  output_json
else
  output_markdown
fi
