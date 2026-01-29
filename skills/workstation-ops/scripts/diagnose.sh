#!/usr/bin/env bash
# Comprehensive system diagnosis for AI agents.
# Analyzes memory, GPU, disk, and logs to identify WHY problems occur.
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Comprehensive system diagnosis: memory leaks, GPU issues, disk health, crash analysis.
Designed to help agents understand WHY problems occur.

Options:
  --process <name>   Focus on specific process type (e.g., python, node)
  --watch <secs>     Monitor for N seconds to detect memory growth
  --quick            Quick scan (skip slow checks)
  --json             Output as JSON instead of markdown
  --help             Show this message

Examples:
  $(basename "$0")                    # Full diagnosis
  $(basename "$0") --process python   # Focus on Python processes
  $(basename "$0") --watch 60         # Monitor 60 seconds for growth
  $(basename "$0") --quick            # Fast overview
USAGE
}

PROCESS_FILTER=""
WATCH_SECS=0
QUICK_MODE=false
OUTPUT_FORMAT="markdown"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --process) PROCESS_FILTER="$2"; shift 2;;
    --watch) WATCH_SECS="$2"; shift 2;;
    --quick) QUICK_MODE=true; shift;;
    --json) OUTPUT_FORMAT="json"; shift;;
    --help|-h) usage; exit 0;;
    *) echo "Unknown option: $1" >&2; usage; exit 1;;
  esac
done

# =============================================================================
# Workstation Specs (static)
# =============================================================================
get_workstation_specs() {
  local cpu_model cpu_cores gpu_name gpu_mem_total ram_total

  cpu_model=$(lscpu 2>/dev/null | grep "Model name" | cut -d: -f2 | xargs || echo "Unknown")
  cpu_cores=$(nproc 2>/dev/null || echo "?")

  if command -v nvidia-smi &>/dev/null; then
    gpu_name=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 || echo "None")
    gpu_mem_total=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader 2>/dev/null | head -1 || echo "?")
  else
    gpu_name="No NVIDIA GPU"
    gpu_mem_total="N/A"
  fi

  ram_total=$(grep MemTotal /proc/meminfo | awk '{printf "%.0f GB", $2/1024/1024}')

  echo "cpu_model|$cpu_model"
  echo "cpu_cores|$cpu_cores"
  echo "gpu_name|$gpu_name"
  echo "gpu_mem|$gpu_mem_total"
  echo "ram_total|$ram_total"
}

# =============================================================================
# Memory Analysis
# =============================================================================
get_memory_state() {
  read -r _ mem_total _ <<<$(grep MemTotal /proc/meminfo)
  read -r _ mem_available _ <<<$(grep MemAvailable /proc/meminfo)
  read -r _ swap_total _ <<<$(grep SwapTotal /proc/meminfo)
  read -r _ swap_free _ <<<$(grep SwapFree /proc/meminfo)

  local used_pct=$(( ((mem_total - mem_available) * 100) / mem_total ))
  local mem_used_gb=$(echo "scale=1; ($mem_total - $mem_available) / 1024 / 1024" | bc)
  local mem_avail_gb=$(echo "scale=1; $mem_available / 1024 / 1024" | bc)
  local swap_used_gb=$(echo "scale=1; ($swap_total - $swap_free) / 1024 / 1024" | bc)

  echo "used_pct|$used_pct"
  echo "used_gb|$mem_used_gb"
  echo "avail_gb|$mem_avail_gb"
  echo "swap_gb|$swap_used_gb"
}

# Find memory leak suspects: long-running with high memory
find_leak_suspects() {
  local filter_pattern="${1:-.*}"

  ps aux --sort=-%mem | awk -v filter="$filter_pattern" '
    NR==1 {next}
    NR<=30 {
      pid=$2
      user=$1
      pct=$4
      rss=$6
      cmd=$11
      gsub(/.*\//, "", cmd)

      # Filter if specified
      if (filter != ".*" && cmd !~ filter) next

      # Only processes using significant memory
      if (rss < 500000) next  # > 500MB

      # Get runtime via ps
      "ps -o etimes= -p " pid | getline etime
      close("ps -o etimes= -p " pid)

      # Flag as suspect if running > 30 min with > 1GB
      if (etime > 1800 && rss > 1000000) {
        rss_gb = rss / 1024 / 1024
        hours = int(etime / 3600)
        mins = int((etime % 3600) / 60)
        printf "%s|%s|%.1f|%dh%dm|%s\n", pid, cmd, rss_gb, hours, mins, pct
      }
    }
  '
}

# Monitor memory growth over time
monitor_memory_growth() {
  local secs=$1
  local filter="${2:-.*}"

  # Get initial snapshot
  declare -A initial_mem
  while IFS='|' read -r pid cmd rss_gb runtime pct; do
    initial_mem["$pid"]="$rss_gb"
  done < <(find_leak_suspects "$filter")

  echo "Monitoring for ${secs}s..." >&2
  sleep "$secs"

  # Get final snapshot and compare
  while IFS='|' read -r pid cmd rss_gb runtime pct; do
    if [[ -n "${initial_mem[$pid]:-}" ]]; then
      initial="${initial_mem[$pid]}"
      delta=$(echo "scale=2; $rss_gb - $initial" | bc)
      if (( $(echo "$delta > 0.1" | bc -l) )); then
        rate=$(echo "scale=2; $delta / $secs * 60" | bc)
        echo "$pid|$cmd|$initial|$rss_gb|+$delta|${rate}/min"
      fi
    fi
  done < <(find_leak_suspects "$filter")
}

# =============================================================================
# GPU Analysis
# =============================================================================
get_gpu_state() {
  if ! command -v nvidia-smi &>/dev/null; then
    echo "available|false"
    return
  fi

  local gpu_util gpu_mem_used gpu_mem_free gpu_temp

  IFS=',' read -r _ gpu_mem_total gpu_mem_used gpu_mem_free gpu_util gpu_temp < <(
    nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu \
      --format=csv,noheader,nounits 2>/dev/null | head -1
  )

  # Trim whitespace
  gpu_util=$(echo "$gpu_util" | xargs)
  gpu_mem_used=$(echo "$gpu_mem_used" | xargs)
  gpu_mem_free=$(echo "$gpu_mem_free" | xargs)
  gpu_temp=$(echo "$gpu_temp" | xargs)

  echo "available|true"
  echo "util_pct|$gpu_util"
  echo "mem_used_mb|$gpu_mem_used"
  echo "mem_free_mb|$gpu_mem_free"
  echo "temp_c|$gpu_temp"

  # Check for GPU processes
  nvidia-smi --query-compute-apps=pid,used_memory,name --format=csv,noheader 2>/dev/null | head -10 | while IFS=',' read -r pid mem name; do
    pid=$(echo "$pid" | xargs)
    mem=$(echo "$mem" | xargs)
    name=$(echo "$name" | xargs | head -c 30)
    echo "gpu_proc|$pid|$mem|$name"
  done
}

# =============================================================================
# Disk Analysis
# =============================================================================
get_disk_state() {
  # Main filesystems (skip loops, tmpfs, etc.)
  df -h 2>/dev/null | awk '
    NR==1 {next}
    /^\/dev\/(sd|nvme|vd)/ {
      fs=$1
      size=$2
      used=$3
      avail=$4
      use_pct=$5
      mount=$6
      gsub(/%/, "", use_pct)
      if (use_pct >= 80) {
        status = "WARNING"
      } else if (use_pct >= 95) {
        status = "CRITICAL"
      } else {
        status = "OK"
      }
      printf "disk|%s|%s|%s|%s|%s|%s\n", mount, size, used, avail, use_pct, status
    }
  '

  # Check for large files in common locations
  if [[ "$QUICK_MODE" == "false" ]]; then
    # Docker disk usage
    if command -v docker &>/dev/null; then
      docker_size=$(docker system df --format '{{.Size}}' 2>/dev/null | head -1 || echo "?")
      echo "docker_disk|$docker_size"
    fi
  fi
}

# =============================================================================
# Recent Crashes (journalctl)
# =============================================================================
get_recent_crashes() {
  local since="${1:-24h ago}"

  # OOM kills
  local oom_count=$(journalctl --since "$since" --no-pager -q 2>/dev/null | grep -ciE "(out of memory|oom-kill|killed process)" || echo 0)

  # Service failures
  local failed_services=$(systemctl --failed --no-pager --no-legend 2>/dev/null | wc -l)

  # Segfaults
  local segfault_count=$(journalctl --since "$since" --no-pager -q 2>/dev/null | grep -ciE "(segfault|core dumped)" || echo 0)

  # Critical kernel errors
  local kernel_errors=$(journalctl -k --since "$since" --no-pager -p crit -q 2>/dev/null | wc -l)

  echo "oom_kills|$oom_count"
  echo "failed_services|$failed_services"
  echo "segfaults|$segfault_count"
  echo "kernel_errors|$kernel_errors"

  # Get recent OOM details
  if [[ $oom_count -gt 0 ]]; then
    journalctl --since "$since" --no-pager -q 2>/dev/null | grep -iE "killed process" | tail -3 | while read -r line; do
      echo "oom_detail|$line"
    done
  fi
}

# =============================================================================
# Generate Diagnosis & Recommendations
# =============================================================================
generate_diagnosis() {
  local mem_used_pct=$1
  local gpu_temp=$2
  local oom_count=$3
  local swap_gb=$4

  local diagnosis=""
  local severity="OK"

  # Memory pressure
  if [[ $mem_used_pct -ge 90 ]]; then
    diagnosis+="CRITICAL: Memory pressure at ${mem_used_pct}%. "
    severity="CRITICAL"
  elif [[ $mem_used_pct -ge 75 ]]; then
    diagnosis+="WARNING: Memory elevated at ${mem_used_pct}%. "
    [[ "$severity" != "CRITICAL" ]] && severity="WARNING"
  fi

  # Swap usage
  if (( $(echo "$swap_gb > 1.0" | bc -l) )); then
    diagnosis+="Swap in use (${swap_gb}GB) indicates memory pressure. "
    [[ "$severity" == "OK" ]] && severity="WARNING"
  fi

  # GPU temperature
  if [[ -n "$gpu_temp" && "$gpu_temp" != "N/A" ]]; then
    if [[ $gpu_temp -ge 85 ]]; then
      diagnosis+="GPU temperature high (${gpu_temp}°C). "
      [[ "$severity" != "CRITICAL" ]] && severity="WARNING"
    fi
  fi

  # OOM events
  if [[ $oom_count -gt 0 ]]; then
    diagnosis+="$oom_count OOM kill(s) in last 24h - system ran out of memory. "
    severity="CRITICAL"
  fi

  [[ -z "$diagnosis" ]] && diagnosis="System appears healthy."

  echo "severity|$severity"
  echo "diagnosis|$diagnosis"
}

generate_recommendations() {
  local mem_used_pct=$1
  local leak_suspects=$2
  local oom_count=$3
  local swap_gb=$4

  local recs=""

  if [[ $mem_used_pct -ge 75 ]]; then
    recs+="- Close unused IDE workspaces (Antigravity, VS Code)\n"
    recs+="- Kill idle Cloud Code duet processes: \`pkill -f 'cloudcode_cli.*duet'\`\n"
  fi

  if [[ -n "$leak_suspects" ]]; then
    recs+="- Investigate leak suspects (long-running processes with high memory)\n"
    recs+="- Consider restarting: \`kill -15 <PID>\` for graceful shutdown\n"
  fi

  if [[ $oom_count -gt 0 ]]; then
    recs+="- URGENT: OOM kills detected. Check \`./run.sh crashes --oom\` for details\n"
    recs+="- Consider adding swap or memory limits to heavy processes\n"
  fi

  if (( $(echo "$swap_gb > 2.0" | bc -l) )); then
    recs+="- High swap usage slows performance. Free memory or add RAM.\n"
  fi

  [[ -z "$recs" ]] && recs="- No immediate action needed. System healthy.\n"

  echo -e "$recs"
}

# =============================================================================
# Output: Markdown
# =============================================================================
output_markdown() {
  echo "## System Diagnosis Report"
  echo ""
  echo "**Generated:** $(date '+%Y-%m-%d %H:%M:%S')"
  echo ""

  # Workstation specs
  echo "### Workstation Specs"
  echo ""
  echo "| Component | Value |"
  echo "|-----------|-------|"
  while IFS='|' read -r key val; do
    case "$key" in
      cpu_model) echo "| CPU | $val |";;
      cpu_cores) echo "| Cores | $val |";;
      gpu_name) echo "| GPU | $val |";;
      gpu_mem) echo "| GPU Memory | $val |";;
      ram_total) echo "| RAM | $val |";;
    esac
  done < <(get_workstation_specs)
  echo ""

  # Memory state
  local mem_used_pct mem_used_gb mem_avail_gb swap_gb
  while IFS='|' read -r key val; do
    case "$key" in
      used_pct) mem_used_pct=$val;;
      used_gb) mem_used_gb=$val;;
      avail_gb) mem_avail_gb=$val;;
      swap_gb) swap_gb=$val;;
    esac
  done < <(get_memory_state)

  echo "### Memory Status"
  echo ""
  echo "| Metric | Value |"
  echo "|--------|-------|"
  echo "| Used | ${mem_used_gb} GB (${mem_used_pct}%) |"
  echo "| Available | ${mem_avail_gb} GB |"
  echo "| Swap Used | ${swap_gb} GB |"
  echo ""

  # GPU state
  echo "### GPU Status"
  echo ""
  local gpu_available gpu_util gpu_mem_used gpu_temp
  gpu_available="false"
  while IFS='|' read -r key val rest; do
    case "$key" in
      available) gpu_available=$val;;
      util_pct) gpu_util=$val;;
      mem_used_mb) gpu_mem_used=$val;;
      temp_c) gpu_temp=$val;;
      gpu_proc)
        if [[ "$gpu_available" == "true" ]]; then
          echo "| PID $val | $rest |"
        fi
        ;;
    esac
  done < <(get_gpu_state)

  if [[ "$gpu_available" == "true" ]]; then
    echo "| Metric | Value |"
    echo "|--------|-------|"
    echo "| Utilization | ${gpu_util}% |"
    echo "| Memory Used | ${gpu_mem_used} MiB |"
    echo "| Temperature | ${gpu_temp}°C |"
  else
    echo "No NVIDIA GPU detected."
  fi
  echo ""

  # Disk state
  echo "### Disk Status"
  echo ""
  echo "| Mount | Size | Used | Available | Status |"
  echo "|-------|------|------|-----------|--------|"
  while IFS='|' read -r type mount size used avail pct status; do
    [[ "$type" == "disk" ]] && echo "| $mount | $size | $used | $avail | $status |"
  done < <(get_disk_state)
  echo ""

  # Recent crashes
  local oom_count failed_services segfault_count kernel_errors
  oom_count=0
  while IFS='|' read -r key val; do
    case "$key" in
      oom_kills) oom_count=$val;;
      failed_services) failed_services=$val;;
      segfaults) segfault_count=$val;;
      kernel_errors) kernel_errors=$val;;
      oom_detail) echo "- OOM: $val";;
    esac
  done < <(get_recent_crashes)

  echo "### Recent Issues (24h)"
  echo ""
  echo "| Type | Count |"
  echo "|------|-------|"
  echo "| OOM Kills | $oom_count |"
  echo "| Failed Services | $failed_services |"
  echo "| Segfaults | $segfault_count |"
  echo "| Kernel Errors | $kernel_errors |"
  echo ""

  # Memory leak suspects
  echo "### Memory Leak Suspects"
  echo ""
  local leak_data
  leak_data=$(find_leak_suspects "$PROCESS_FILTER")

  if [[ -n "$leak_data" ]]; then
    echo "Processes running >30min with >1GB memory:"
    echo ""
    echo "| PID | Process | Memory (GB) | Runtime | %Mem |"
    echo "|-----|---------|-------------|---------|------|"
    echo "$leak_data" | while IFS='|' read -r pid cmd mem runtime pct; do
      echo "| $pid | $cmd | $mem | $runtime | $pct% |"
    done
  else
    echo "No obvious leak suspects found."
  fi
  echo ""

  # Watch mode
  if [[ $WATCH_SECS -gt 0 ]]; then
    echo "### Memory Growth (${WATCH_SECS}s observation)"
    echo ""
    local growth_data
    growth_data=$(monitor_memory_growth "$WATCH_SECS" "$PROCESS_FILTER")
    if [[ -n "$growth_data" ]]; then
      echo "| PID | Process | Before | After | Delta | Rate |"
      echo "|-----|---------|--------|-------|-------|------|"
      echo "$growth_data" | while IFS='|' read -r pid cmd before after delta rate; do
        echo "| $pid | $cmd | ${before}GB | ${after}GB | $delta | $rate |"
      done
    else
      echo "No significant memory growth detected."
    fi
    echo ""
  fi

  # Diagnosis
  echo "### Diagnosis"
  echo ""
  local severity diagnosis
  while IFS='|' read -r key val; do
    case "$key" in
      severity) severity=$val;;
      diagnosis) diagnosis=$val;;
    esac
  done < <(generate_diagnosis "$mem_used_pct" "${gpu_temp:-0}" "$oom_count" "$swap_gb")

  echo "**Status:** $severity"
  echo ""
  echo "$diagnosis"
  echo ""

  # Recommendations
  echo "### Recommendations"
  echo ""
  generate_recommendations "$mem_used_pct" "$leak_data" "$oom_count" "$swap_gb"
}

# =============================================================================
# Output: JSON
# =============================================================================
output_json() {
  echo "{"
  echo "  \"timestamp\": \"$(date -Iseconds)\","

  # Specs
  echo "  \"workstation\": {"
  local first=true
  while IFS='|' read -r key val; do
    $first || echo ","
    first=false
    echo -n "    \"$key\": \"$val\""
  done < <(get_workstation_specs)
  echo ""
  echo "  },"

  # Memory
  echo "  \"memory\": {"
  first=true
  while IFS='|' read -r key val; do
    $first || echo ","
    first=false
    echo -n "    \"$key\": $val"
  done < <(get_memory_state)
  echo ""
  echo "  },"

  # GPU
  echo "  \"gpu\": {"
  first=true
  while IFS='|' read -r key val rest; do
    [[ "$key" == "gpu_proc" ]] && continue
    $first || echo ","
    first=false
    if [[ "$val" == "true" || "$val" == "false" ]]; then
      echo -n "    \"$key\": $val"
    else
      echo -n "    \"$key\": \"$val\""
    fi
  done < <(get_gpu_state)
  echo ""
  echo "  },"

  # Crashes
  echo "  \"recent_issues\": {"
  first=true
  while IFS='|' read -r key val; do
    [[ "$key" == "oom_detail" ]] && continue
    $first || echo ","
    first=false
    echo -n "    \"$key\": $val"
  done < <(get_recent_crashes)
  echo ""
  echo "  }"

  echo "}"
}

# =============================================================================
# Main
# =============================================================================
if [[ "$OUTPUT_FORMAT" == "json" ]]; then
  output_json
else
  output_markdown
fi
