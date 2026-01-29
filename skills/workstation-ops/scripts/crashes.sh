#!/usr/bin/env bash
# Analyze journalctl for system crashes, OOM kills, and service failures.
# Outputs markdown or JSON with recommendations.
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Analyze system crashes, OOM kills, and service failures via journalctl.
Use after a crash/reboot to understand what happened.

Options:
  --since <time>     Lookback period (default: 24h, e.g., "2h ago", "yesterday")
  --last-boot        Check previous boot session (what happened before crash)
  --service <name>   Filter by specific service
  --oom              Focus only on OOM killer events
  --gpu              Focus on GPU/NVIDIA issues
  --json             Output as JSON instead of markdown
  --help             Show this message

Examples:
  $(basename "$0")                    # Crashes in last 24h
  $(basename "$0") --last-boot        # What happened before last reboot
  $(basename "$0") --oom              # Only OOM events
  $(basename "$0") --gpu              # GPU driver issues
  $(basename "$0") --service docker   # Docker-related issues
USAGE
}

SINCE="24h ago"
SERVICE=""
OOM_ONLY=false
GPU_ONLY=false
LAST_BOOT=false
OUTPUT_FORMAT="markdown"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --since) SINCE="$2"; shift 2;;
    --service) SERVICE="$2"; shift 2;;
    --oom) OOM_ONLY=true; shift;;
    --gpu) GPU_ONLY=true; shift;;
    --last-boot) LAST_BOOT=true; shift;;
    --json) OUTPUT_FORMAT="json"; shift;;
    --help|-h) usage; exit 0;;
    *) echo "Unknown option: $1" >&2; usage; exit 1;;
  esac
done

# If checking last boot, use journalctl -b -1
BOOT_FLAG=""
if [[ "$LAST_BOOT" == "true" ]]; then
  BOOT_FLAG="-b -1"
  SINCE=""  # Ignore since when checking last boot
fi

# Build journalctl base command
jctl_cmd() {
  local extra_args="$1"
  if [[ -n "$BOOT_FLAG" ]]; then
    journalctl $BOOT_FLAG $extra_args --no-pager -q 2>/dev/null
  elif [[ -n "$SINCE" ]]; then
    journalctl --since "$SINCE" $extra_args --no-pager -q 2>/dev/null
  else
    journalctl $extra_args --no-pager -q 2>/dev/null
  fi
}

# Collect OOM killer events
get_oom_events() {
  jctl_cmd "" | grep -iE "(out of memory|oom-kill|killed process|oom_reaper|invoked oom)" | head -50 || true
}

# Collect GPU/NVIDIA errors
get_gpu_errors() {
  jctl_cmd "" | grep -iE "(nvidia|gpu|nvrm|xid|cuda|nvml)" | grep -iE "(error|fail|fault|timeout|reset)" | head -30 || true
}

# Collect service failures
get_service_failures() {
  if [[ -n "$SERVICE" ]]; then
    if [[ -n "$BOOT_FLAG" ]]; then
      journalctl $BOOT_FLAG -u "$SERVICE" --no-pager -p err -q 2>/dev/null | head -30 || true
    else
      journalctl -u "$SERVICE" --since "$SINCE" --no-pager -p err -q 2>/dev/null | head -30 || true
    fi
  else
    systemctl --failed --no-pager --no-legend 2>/dev/null | head -20 || true
  fi
}

# Collect critical kernel errors
get_kernel_errors() {
  if [[ -n "$BOOT_FLAG" ]]; then
    journalctl $BOOT_FLAG -k --no-pager -p crit -q 2>/dev/null | head -20 || true
  else
    journalctl -k --since "$SINCE" --no-pager -p crit -q 2>/dev/null | head -20 || true
  fi
}

# Collect segfaults
get_segfaults() {
  jctl_cmd "" | grep -iE "(segfault|core dumped|signal 11|SIGSEGV)" | head -20 || true
}

# Get shutdown/crash reason from last boot
get_shutdown_reason() {
  # Check for unexpected shutdown indicators
  journalctl -b -1 --no-pager -q 2>/dev/null | tail -50 | grep -iE "(shutdown|reboot|panic|halt|power)" | tail -5 || true
}

# Parse OOM events into structured data
parse_oom_events() {
  local oom_raw
  oom_raw=$(get_oom_events)

  if [[ -z "$oom_raw" ]]; then
    echo ""
    return
  fi

  # Extract key info: timestamp, killed process, memory info
  echo "$oom_raw" | while IFS= read -r line; do
    # Extract timestamp (first part of journalctl output)
    timestamp=$(echo "$line" | awk '{print $1, $2, $3}')

    # Try to extract process name from "Killed process PID (name)"
    if echo "$line" | grep -qE "Killed process [0-9]+"; then
      pid=$(echo "$line" | grep -oE "Killed process [0-9]+" | grep -oE "[0-9]+")
      proc=$(echo "$line" | grep -oE "\([^)]+\)" | tr -d '()' | head -1)
      echo "${timestamp}|${pid}|${proc:-unknown}"
    fi
  done
}

# Get memory pressure at time of OOM
get_memory_context() {
  # Check current memory as proxy (historical would require more tooling)
  read -r _ mem_total _ <<<$(grep MemTotal /proc/meminfo)
  read -r _ mem_available _ <<<$(grep MemAvailable /proc/meminfo)
  used_pct=$(( ( (mem_total - mem_available) * 100 ) / mem_total ))
  echo "$used_pct"
}

# Generate recommendations based on findings
generate_recommendations() {
  local oom_count=$1
  local service_failures=$2
  local segfaults=$3
  local kernel_errors=$4

  local recs=""

  if [[ $oom_count -gt 0 ]]; then
    recs+="- **OOM Events Detected:** Consider increasing swap, setting memory limits on resource-heavy processes, or adding RAM.\n"
    recs+="- Run \`./run.sh memory\` to identify current memory hogs.\n"
    recs+="- Check if any cgroups have tight memory limits: \`systemd-cgtop\`\n"
  fi

  if [[ -n "$service_failures" ]]; then
    recs+="- **Service Failures:** Check specific service logs with \`journalctl -u <service> -n 100\`\n"
    recs+="- Restart failed services: \`systemctl restart <service>\`\n"
  fi

  if [[ -n "$segfaults" ]]; then
    recs+="- **Segfaults Detected:** Check for corrupt memory, outdated libraries, or bugs in the crashing processes.\n"
    recs+="- Look for core dumps in \`/var/lib/systemd/coredump/\` or \`coredumpctl list\`\n"
  fi

  if [[ -n "$kernel_errors" ]]; then
    recs+="- **Kernel Errors:** Check hardware (RAM, disk). Run \`dmesg -T | tail -100\` for details.\n"
    recs+="- Consider running \`memtest86+\` if memory errors are suspected.\n"
  fi

  if [[ -z "$recs" ]]; then
    recs="- No critical issues found in the analyzed period.\n"
  fi

  echo -e "$recs"
}

# Output markdown report
output_markdown() {
  echo "## System Crash Analysis"
  echo ""
  if [[ "$LAST_BOOT" == "true" ]]; then
    echo "**Analyzing:** Previous boot session (before last reboot)"
  else
    echo "**Period:** Since $SINCE"
  fi
  echo "**Generated:** $(date '+%Y-%m-%d %H:%M:%S')"
  echo ""

  # If checking last boot, show what might have caused the reboot
  if [[ "$LAST_BOOT" == "true" ]]; then
    echo "### Last Shutdown/Crash"
    echo ""
    local shutdown_reason
    shutdown_reason=$(get_shutdown_reason)
    if [[ -n "$shutdown_reason" ]]; then
      echo "\`\`\`"
      echo "$shutdown_reason"
      echo "\`\`\`"
    else
      echo "No shutdown reason found in logs (may have been power loss or hard crash)."
    fi
    echo ""
    echo "**Tip:** If no logs, likely causes: power failure, kernel panic, or GPU lockup."
    echo ""
  fi

  # GPU-only mode
  if [[ "$GPU_ONLY" == "true" ]]; then
    echo "### GPU/NVIDIA Errors"
    echo ""
    local gpu_errors
    gpu_errors=$(get_gpu_errors)
    if [[ -n "$gpu_errors" ]]; then
      echo "\`\`\`"
      echo "$gpu_errors"
      echo "\`\`\`"
      echo ""
      echo "**Common GPU issues:**"
      echo "- XID errors: Check \`nvidia-bug-report.sh\` for details"
      echo "- Timeout: GPU overheating or driver issue"
      echo "- NVRM errors: Driver crash, may need reboot"
      echo ""
      echo "**To generate full GPU report (run as human):**"
      echo "\`\`\`bash"
      echo "sudo nvidia-bug-report.sh"
      echo "\`\`\`"
    else
      echo "No GPU errors found."
    fi
    echo ""
    return
  fi

  # OOM Events
  local oom_events
  oom_events=$(parse_oom_events)
  local oom_count=0

  echo "### OOM Killer Events"
  echo ""

  if [[ -n "$oom_events" ]]; then
    oom_count=$(echo "$oom_events" | grep -c '|' || echo 0)
    echo "| Time | PID | Process |"
    echo "|------|-----|---------|"
    echo "$oom_events" | while IFS='|' read -r ts pid proc; do
      [[ -n "$ts" ]] && echo "| $ts | $pid | $proc |"
    done
    echo ""
    echo "**Memory pressure likely triggered these kills.** Run \`./run.sh memory\` for current state."
  else
    echo "No OOM killer events found."
  fi
  echo ""

  if [[ "$OOM_ONLY" == "true" ]]; then
    # Skip other sections if only OOM requested
    return
  fi

  # Service Failures
  echo "### Service Failures"
  echo ""
  local service_failures
  service_failures=$(get_service_failures)

  if [[ -n "$service_failures" ]]; then
    echo "\`\`\`"
    echo "$service_failures"
    echo "\`\`\`"
  else
    echo "No service failures found."
  fi
  echo ""

  # Kernel Errors
  echo "### Critical Kernel Errors"
  echo ""
  local kernel_errors
  kernel_errors=$(get_kernel_errors)

  if [[ -n "$kernel_errors" ]]; then
    echo "\`\`\`"
    echo "$kernel_errors"
    echo "\`\`\`"
  else
    echo "No critical kernel errors found."
  fi
  echo ""

  # Segfaults
  echo "### Segfaults / Core Dumps"
  echo ""
  local segfaults
  segfaults=$(get_segfaults)

  if [[ -n "$segfaults" ]]; then
    echo "\`\`\`"
    echo "$segfaults"
    echo "\`\`\`"
  else
    echo "No segfaults detected."
  fi
  echo ""

  # Recommendations
  echo "### Recommendations"
  echo ""
  generate_recommendations "$oom_count" "$service_failures" "$segfaults" "$kernel_errors"
}

# Output JSON report
output_json() {
  local oom_events
  oom_events=$(parse_oom_events)
  local service_failures
  service_failures=$(get_service_failures | head -10)
  local kernel_errors
  kernel_errors=$(get_kernel_errors | head -5)
  local segfaults
  segfaults=$(get_segfaults | head -5)

  echo "{"
  echo "  \"timestamp\": \"$(date -Iseconds)\","
  echo "  \"since\": \"$SINCE\","
  echo "  \"oom_events\": ["

  local first=true
  if [[ -n "$oom_events" ]]; then
    echo "$oom_events" | while IFS='|' read -r ts pid proc; do
      if [[ -n "$ts" ]]; then
        $first || echo ","
        first=false
        echo -n "    {\"time\": \"$ts\", \"pid\": \"$pid\", \"process\": \"$proc\"}"
      fi
    done
  fi
  echo ""
  echo "  ],"

  echo "  \"service_failures\": $(echo "$service_failures" | head -5 | jq -R -s 'split("\n") | map(select(length > 0))'),"
  echo "  \"kernel_errors\": $(echo "$kernel_errors" | head -5 | jq -R -s 'split("\n") | map(select(length > 0))'),"
  echo "  \"segfaults\": $(echo "$segfaults" | head -5 | jq -R -s 'split("\n") | map(select(length > 0))')"
  echo "}"
}

# Main
if [[ "$OUTPUT_FORMAT" == "json" ]]; then
  output_json
else
  output_markdown
fi
