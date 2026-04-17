#!/usr/bin/env bash
# VS Code diagnostics: detect runaway processes, V8 heap OOM, renderer hangs.
# Outputs markdown or JSON with actionable recommendations.
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

VS Code health check: detect runaway extension host processes, V8 OOM,
renderer hangs, and Electron GPU process issues.

Options:
  --fix              Kill runaway VS Code workers (>90% CPU for >2 min)
  --json             Output as JSON instead of markdown
  --help             Show this message

Examples:
  $(basename "$0")              # Diagnose VS Code issues
  $(basename "$0") --fix        # Kill runaway workers automatically
  $(basename "$0") --json       # Agent-parseable JSON
USAGE
}

FIX_MODE=false
OUTPUT_FORMAT="markdown"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fix) FIX_MODE=true; shift;;
    --json) OUTPUT_FORMAT="json"; shift;;
    --help|-h) usage; exit 0;;
    *) echo "Unknown option: $1" >&2; usage; exit 1;;
  esac
done

EXIT_CODE=0

# =============================================================================
# Detect V8 Heap OOM in logs (current + previous boot)
# =============================================================================
get_v8_oom_events() {
  local events=""
  # Check current boot
  local current
  current=$(journalctl -b 0 --no-pager -q 2>/dev/null | grep -iE "OOM error in V8|JavaScript heap out of memory|heap out of memory" | tail -10 || true)
  if [[ -n "$current" ]]; then
    events+="$current"$'\n'
  fi
  # Check previous boot
  local prev
  prev=$(journalctl -b -1 --no-pager -q 2>/dev/null | grep -iE "OOM error in V8|JavaScript heap out of memory|heap out of memory" | tail -10 || true)
  if [[ -n "$prev" ]]; then
    events+="$prev"$'\n'
  fi
  # Also check user journal (VS Code logs here on KDE)
  local user_events
  user_events=$(journalctl --user --since "24h ago" --no-pager -q 2>/dev/null | grep -iE "OOM error in V8|JavaScript heap out of memory|heap out of memory" | tail -10 || true)
  if [[ -n "$user_events" ]]; then
    events+="$user_events"$'\n'
  fi
  echo "$events" | grep -v '^$' | sort -u || true
}

# =============================================================================
# Detect Electron/GPU renderer crashes
# =============================================================================
get_renderer_crashes() {
  local crashes=""
  # Crashpad reports
  local crashpad_dir="$HOME/.config/Code/Crashpad"
  if [[ -d "$crashpad_dir/completed" ]]; then
    local recent_crashes
    recent_crashes=$(find "$crashpad_dir/completed" -type f -mmin -1440 2>/dev/null | wc -l)
    if [[ $recent_crashes -gt 0 ]]; then
      crashes+="crashpad_reports|$recent_crashes"$'\n'
    fi
  fi
  if [[ -d "$crashpad_dir/pending" ]]; then
    local pending_crashes
    pending_crashes=$(find "$crashpad_dir/pending" -type f 2>/dev/null | wc -l)
    if [[ $pending_crashes -gt 0 ]]; then
      crashes+="crashpad_pending|$pending_crashes"$'\n'
    fi
  fi
  echo "$crashes" | grep -v '^$' || true
}

# =============================================================================
# Detect runaway VS Code node workers
# =============================================================================
get_runaway_workers() {
  # Find VS Code node processes using >80% CPU
  ps -eo pid,%cpu,%mem,etime,comm --sort=-%cpu 2>/dev/null | awk '
    /code/ {
      pid=$1; cpu=$2; mem=$3; etime=$4; comm=$5
      # Parse etime (formats: MM:SS, HH:MM:SS, D-HH:MM:SS)
      split(etime, parts, ":")
      if (length(parts) == 2) {
        total_secs = parts[1]*60 + parts[2]
      } else if (length(parts) == 3) {
        # Check for D- prefix
        if (index(parts[1], "-") > 0) {
          split(parts[1], dp, "-")
          total_secs = dp[1]*86400 + dp[2]*3600 + parts[2]*60 + parts[3]
        } else {
          total_secs = parts[1]*3600 + parts[2]*60 + parts[3]
        }
      } else {
        total_secs = 0
      }
      # Flag if >80% CPU for more than 2 minutes
      if (cpu > 80.0 && total_secs > 120) {
        printf "%s|%.1f|%.1f|%s|%s\n", pid, cpu, mem, etime, comm
      }
    }
  ' || true
}

# =============================================================================
# Check VS Code heap settings
# =============================================================================
check_heap_settings() {
  local settings_file="$HOME/.config/Code/User/settings.json"
  local argv_file="$HOME/.config/Code/User/argv.json"
  local has_heap_limit=false
  local heap_size=""

  # Check argv.json for --max-old-space-size
  if [[ -f "$argv_file" ]] && grep -q "max-old-space-size" "$argv_file" 2>/dev/null; then
    has_heap_limit=true
    heap_size=$(grep -oP 'max-old-space-size[=\s]+\K[0-9]+' "$argv_file" || echo "set")
  fi

  # Check NODE_OPTIONS env
  if echo "${NODE_OPTIONS:-}" | grep -q "max-old-space-size" 2>/dev/null; then
    has_heap_limit=true
    heap_size=$(echo "$NODE_OPTIONS" | grep -oP 'max-old-space-size[=\s]+\K[0-9]+' || echo "set")
  fi

  echo "has_heap_limit|$has_heap_limit"
  echo "heap_size|${heap_size:-default}"
}

# =============================================================================
# Check VS Code extension host process count
# =============================================================================
get_extension_host_info() {
  local total_code_procs
  total_code_procs=$(pgrep -f '/usr/share/code/code' 2>/dev/null | wc -l || echo 0)

  local ext_host_procs
  ext_host_procs=$(pgrep -f 'node.mojom.NodeService.*--user-data-dir.*Code' 2>/dev/null | wc -l || echo 0)

  local renderer_procs
  renderer_procs=$(pgrep -f '/usr/share/code/code --type=zygote$' 2>/dev/null | wc -l || echo 0)

  local total_mem_mb
  total_mem_mb=$(ps -eo pid,rss,comm 2>/dev/null | awk '/code/ {sum += $2} END {printf "%.0f", sum/1024}')

  echo "total_procs|$total_code_procs"
  echo "ext_host_procs|$ext_host_procs"
  echo "renderer_procs|$renderer_procs"
  echo "total_mem_mb|$total_mem_mb"
}

# =============================================================================
# Fix: kill runaway workers
# =============================================================================
kill_runaway_workers() {
  local killed=0
  local pids=""
  while IFS='|' read -r pid cpu mem etime comm; do
    [[ -z "$pid" ]] && continue
    pids+="$pid "
    killed=$((killed + 1))
  done < <(get_runaway_workers)

  if [[ $killed -gt 0 ]]; then
    kill $pids 2>/dev/null || true
    echo "killed|$killed|$pids"
  else
    echo "killed|0|"
  fi
}

# =============================================================================
# Output: Markdown
# =============================================================================
output_markdown() {
  echo "## VS Code Health Check"
  echo ""
  echo "**Generated:** $(date '+%Y-%m-%d %H:%M:%S')"
  echo ""

  # Process overview
  echo "### Process Overview"
  echo ""
  echo "| Metric | Value |"
  echo "|--------|-------|"
  while IFS='|' read -r key val; do
    case "$key" in
      total_procs) echo "| Total VS Code processes | $val |";;
      ext_host_procs) echo "| Extension host workers | $val |";;
      renderer_procs) echo "| Renderer processes | $val |";;
      total_mem_mb) echo "| Total memory | ${val} MB |";;
    esac
  done < <(get_extension_host_info)
  echo ""

  # Heap settings
  echo "### V8 Heap Configuration"
  echo ""
  local has_heap_limit="false"
  while IFS='|' read -r key val; do
    case "$key" in
      has_heap_limit) has_heap_limit=$val;;
      heap_size)
        if [[ "$has_heap_limit" == "true" ]]; then
          echo "Heap limit: **${val} MB** (configured)"
        else
          echo "Heap limit: **default** (no override set)"
          echo ""
          echo "> **Recommendation:** Set a heap limit to prevent V8 OOM freezes."
          echo "> Add to \`~/.config/Code/User/argv.json\`:"
          echo '> ```json'
          echo '> { "js-flags": "--max-old-space-size=8192" }'
          echo '> ```'
          EXIT_CODE=1
        fi
        ;;
    esac
  done < <(check_heap_settings)
  echo ""

  # V8 OOM events
  echo "### V8 Heap OOM Events"
  echo ""
  local v8_ooms
  v8_ooms=$(get_v8_oom_events)
  if [[ -n "$v8_ooms" ]]; then
    echo "**V8 JavaScript heap OOM detected:**"
    echo ""
    echo '```'
    echo "$v8_ooms"
    echo '```'
    echo ""
    echo "This causes VS Code to stop accepting input (renderer freeze)."
    echo "The Electron process exhausts its V8 heap and the UI thread stalls."
    EXIT_CODE=2
  else
    echo "No V8 OOM events found in recent logs."
  fi
  echo ""

  # Runaway workers
  echo "### Runaway Workers (>80% CPU, >2 min)"
  echo ""
  local runaways
  runaways=$(get_runaway_workers)
  if [[ -n "$runaways" ]]; then
    echo "| PID | CPU% | Mem% | Runtime | Process |"
    echo "|-----|------|------|---------|---------|"
    while IFS='|' read -r pid cpu mem etime comm; do
      [[ -z "$pid" ]] && continue
      echo "| $pid | $cpu | $mem | $etime | $comm |"
    done <<< "$runaways"
    echo ""
    echo "**These may be causing UI freezes.** Fix with: \`./run.sh vscode --fix\`"
    [[ $EXIT_CODE -lt 1 ]] && EXIT_CODE=1
  else
    echo "No runaway workers detected."
  fi
  echo ""

  # Crashpad reports
  echo "### Crash Reports"
  echo ""
  local crashes
  crashes=$(get_renderer_crashes)
  if [[ -n "$crashes" ]]; then
    while IFS='|' read -r key val; do
      case "$key" in
        crashpad_reports) echo "- **$val** crash report(s) in last 24h";;
        crashpad_pending) echo "- **$val** pending crash report(s)";;
      esac
    done <<< "$crashes"
  else
    echo "No recent crash reports."
  fi
  echo ""

  # Fix mode
  if [[ "$FIX_MODE" == "true" ]]; then
    echo "### Auto-Fix Results"
    echo ""
    local fix_result
    fix_result=$(kill_runaway_workers)
    local killed_count
    killed_count=$(echo "$fix_result" | grep '^killed' | cut -d'|' -f2)
    local killed_pids
    killed_pids=$(echo "$fix_result" | grep '^killed' | cut -d'|' -f3)
    if [[ "$killed_count" -gt 0 ]]; then
      echo "Killed **$killed_count** runaway worker(s): PIDs $killed_pids"
      echo ""
      echo "VS Code will respawn these in a calmer state."
    else
      echo "No runaway workers to kill."
    fi
    echo ""
  fi

  # Summary
  echo "### Summary"
  echo ""
  if [[ $EXIT_CODE -eq 0 ]]; then
    echo "**Status: OK** - VS Code appears healthy."
  elif [[ $EXIT_CODE -eq 1 ]]; then
    echo "**Status: WARNING** - Issues detected, see recommendations above."
  else
    echo "**Status: CRITICAL** - V8 OOM detected. VS Code needs attention."
  fi
}

# =============================================================================
# Output: JSON
# =============================================================================
output_json() {
  local v8_ooms runaways crashes

  v8_ooms=$(get_v8_oom_events | head -5)
  runaways=$(get_runaway_workers)
  crashes=$(get_renderer_crashes)

  echo "{"
  echo "  \"timestamp\": \"$(date -Iseconds)\","

  # Process info
  echo "  \"processes\": {"
  local first=true
  while IFS='|' read -r key val; do
    $first || echo ","
    first=false
    echo -n "    \"$key\": $val"
  done < <(get_extension_host_info)
  echo ""
  echo "  },"

  # Heap config
  echo "  \"heap_config\": {"
  first=true
  while IFS='|' read -r key val; do
    $first || echo ","
    first=false
    if [[ "$val" == "true" || "$val" == "false" ]]; then
      echo -n "    \"$key\": $val"
    else
      echo -n "    \"$key\": \"$val\""
    fi
  done < <(check_heap_settings)
  echo ""
  echo "  },"

  # V8 OOM
  echo "  \"v8_oom_events\": $(echo "$v8_ooms" | jq -R -s 'split("\n") | map(select(length > 0))'),"

  # Runaways
  echo "  \"runaway_workers\": ["
  first=true
  if [[ -n "$runaways" ]]; then
    while IFS='|' read -r pid cpu mem etime comm; do
      [[ -z "$pid" ]] && continue
      $first || echo ","
      first=false
      echo -n "    {\"pid\": $pid, \"cpu\": $cpu, \"mem\": $mem, \"runtime\": \"$etime\"}"
    done <<< "$runaways"
  fi
  echo ""
  echo "  ],"

  # Fix results
  if [[ "$FIX_MODE" == "true" ]]; then
    local fix_result
    fix_result=$(kill_runaway_workers)
    local killed_count
    killed_count=$(echo "$fix_result" | grep '^killed' | cut -d'|' -f2)
    echo "  \"fix_applied\": true,"
    echo "  \"workers_killed\": $killed_count,"
  else
    echo "  \"fix_applied\": false,"
  fi

  # Status
  local status="ok"
  [[ -n "$runaways" ]] && status="warning"
  [[ -n "$v8_ooms" ]] && status="critical"
  echo "  \"status\": \"$status\""
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

exit $EXIT_CODE
