#!/usr/bin/env bash
# Generate memory usage report for project agents.
# Outputs markdown table with top consumers and leak detection.
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Generate a memory usage report with top consumers and leak detection.

Options:
  --top <n>        Show top N processes (default: 15)
  --json           Output as JSON instead of markdown
  --watch <secs>   Watch mode: sample every N seconds to detect leaks
  --help           Show this message

Examples:
  $(basename "$0")                    # Markdown report
  $(basename "$0") --top 20           # Show top 20 processes
  $(basename "$0") --watch 30         # Sample every 30s for leak detection
  $(basename "$0") --json             # JSON output for programmatic use
USAGE
}

TOP_N=15
OUTPUT_FORMAT="markdown"
WATCH_INTERVAL=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --top) TOP_N="$2"; shift 2;;
    --json) OUTPUT_FORMAT="json"; shift;;
    --watch) WATCH_INTERVAL="$2"; shift 2;;
    --help|-h) usage; exit 0;;
    *) echo "Unknown option: $1" >&2; usage; exit 1;;
  esac
done

# Get memory info
get_memory_info() {
  read -r _ mem_total _ <<<"$(grep MemTotal /proc/meminfo)"
  read -r _ mem_available _ <<<"$(grep MemAvailable /proc/meminfo)"
  read -r _ mem_free _ <<<"$(grep MemFree /proc/meminfo)"
  read -r _ buffers _ <<<"$(grep Buffers /proc/meminfo)"
  read -r _ cached _ <<<"$(grep "^Cached:" /proc/meminfo)"
  read -r _ swap_total _ <<<"$(grep SwapTotal /proc/meminfo)"
  read -r _ swap_free _ <<<"$(grep SwapFree /proc/meminfo)"

  mem_total_gb=$(echo "scale=1; $mem_total / 1024 / 1024" | bc)
  mem_used_gb=$(echo "scale=1; ($mem_total - $mem_available) / 1024 / 1024" | bc)
  mem_available_gb=$(echo "scale=1; $mem_available / 1024 / 1024" | bc)
  buffer_cache_gb=$(echo "scale=1; ($buffers + $cached) / 1024 / 1024" | bc)
  swap_used_gb=$(echo "scale=1; ($swap_total - $swap_free) / 1024 / 1024" | bc)
  swap_total_gb=$(echo "scale=1; $swap_total / 1024 / 1024" | bc)
  used_pct=$(( ( (mem_total - mem_available) * 100 ) / mem_total ))
}

# Get top processes by memory
get_top_processes() {
  ps aux --sort=-%mem | awk -v top="$TOP_N" '
    NR==1 {next}
    NR<=top+1 {
      pid=$2
      pct=$4
      rss=$6
      rss_gb=rss/1024/1024
      # Extract command name (simplified)
      cmd=$11
      gsub(/.*\//, "", cmd)
      # Truncate long commands
      if (length(cmd) > 40) cmd=substr(cmd,1,37)"..."
      printf "%s|%s|%.1f|%.1f\n", pid, cmd, rss_gb, pct
    }
  '
}

# Categorize memory usage
get_categories() {
  declare -A categories

  # ArangoDB
  arangodb=$(ps aux | grep -E "arangod" | grep -v grep | awk '{sum+=$6} END {printf "%.1f", sum/1024/1024}')

  # Claude Code CLI
  claudecode=$(ps aux | grep -E "cloudcode_cli" | grep -v grep | awk '{sum+=$6} END {printf "%.1f", sum/1024/1024}')
  claudecode_count=$(ps aux | grep -E "cloudcode_cli" | grep -v grep | wc -l)

  # Antigravity IDE
  antigravity=$(ps aux | grep -E "antigravity|language_server_linux" | grep -v grep | awk '{sum+=$6} END {printf "%.1f", sum/1024/1024}')
  antigravity_count=$(ps aux | grep -E "antigravity|language_server_linux" | grep -v grep | wc -l)

  # VS Code
  vscode=$(ps aux | grep -E "/usr/share/code" | grep -v grep | awk '{sum+=$6} END {printf "%.1f", sum/1024/1024}')
  vscode_count=$(ps aux | grep -E "/usr/share/code" | grep -v grep | wc -l)

  # Python processes
  python_mem=$(ps aux | grep -E "python|\.venv" | grep -v grep | awk '{sum+=$6} END {printf "%.1f", sum/1024/1024}')
  python_count=$(ps aux | grep -E "python|\.venv" | grep -v grep | wc -l)

  # Node.js
  node_mem=$(ps aux | grep -E "node " | grep -v grep | awk '{sum+=$6} END {printf "%.1f", sum/1024/1024}')
  node_count=$(ps aux | grep -E "node " | grep -v grep | wc -l)

  # Whisper/ML
  whisper=$(ps aux | grep -E "whisper|faster-whisper" | grep -v grep | awk '{sum+=$6} END {printf "%.1f", sum/1024/1024}')

  echo "ArangoDB|${arangodb:-0}|1|Database"
  echo "Claude Code|${claudecode:-0}|${claudecode_count:-0}|AI Agent Sessions"
  echo "Antigravity IDE|${antigravity:-0}|${antigravity_count:-0}|IDE + Language Servers"
  echo "VS Code|${vscode:-0}|${vscode_count:-0}|IDE"
  echo "Python|${python_mem:-0}|${python_count:-0}|Scripts/Skills"
  echo "Node.js|${node_mem:-0}|${node_count:-0}|Various"
  echo "Whisper/ML|${whisper:-0}|1|Transcription"
}

# Check for potential memory leaks (processes with high and growing memory)
check_leaks() {
  local leak_suspects=""

  # Look for long-running processes with high memory
  while IFS='|' read -r pid cmd rss_gb pct; do
    # Skip if RSS is small
    if (( $(echo "$rss_gb < 1.0" | bc -l) )); then
      continue
    fi

    # Get process start time and calculate runtime
    start_time=$(ps -o lstart= -p "$pid" 2>/dev/null || echo "")
    if [[ -z "$start_time" ]]; then
      continue
    fi

    # Get elapsed time in seconds
    etime=$(ps -o etimes= -p "$pid" 2>/dev/null | tr -d ' ' || echo "0")

    # If running > 1 hour and using > 2GB, flag as potential leak
    if [[ $etime -gt 3600 ]] && (( $(echo "$rss_gb > 2.0" | bc -l) )); then
      hours=$((etime / 3600))
      leak_suspects+="${pid}|${cmd}|${rss_gb}|${hours}h\n"
    fi
  done < <(get_top_processes)

  echo -e "$leak_suspects"
}

# Output markdown report
output_markdown() {
  get_memory_info

  echo "## Memory Usage Report"
  echo ""
  echo "**Generated:** $(date '+%Y-%m-%d %H:%M:%S')"
  echo ""
  echo "### Summary"
  echo ""
  echo "| Metric | Value |"
  echo "|--------|-------|"
  echo "| Total Memory | ${mem_total_gb} GB |"
  echo "| Used | ${mem_used_gb} GB (${used_pct}%) |"
  echo "| Available | ${mem_available_gb} GB |"
  echo "| Buffer/Cache | ${buffer_cache_gb} GB |"
  echo "| Swap Used | ${swap_used_gb} / ${swap_total_gb} GB |"
  echo ""

  # Status indicator
  if [[ $used_pct -ge 90 ]]; then
    echo "**Status:** CRITICAL - Memory pressure detected"
  elif [[ $used_pct -ge 75 ]]; then
    echo "**Status:** WARNING - Memory usage elevated"
  else
    echo "**Status:** OK - Sufficient headroom"
  fi
  echo ""

  echo "### Memory by Category"
  echo ""
  echo "| Category | Memory (GB) | Processes | Notes |"
  echo "|----------|-------------|-----------|-------|"
  while IFS='|' read -r cat mem count notes; do
    if (( $(echo "$mem > 0.1" | bc -l) )); then
      echo "| $cat | $mem | $count | $notes |"
    fi
  done < <(get_categories)
  echo ""

  echo "### Top $TOP_N Processes"
  echo ""
  echo "| PID | Process | Memory (GB) | % of Total |"
  echo "|-----|---------|-------------|------------|"
  while IFS='|' read -r pid cmd rss_gb pct; do
    printf "| %s | %s | %s | %s%% |\n" "$pid" "$cmd" "$rss_gb" "$pct"
  done < <(get_top_processes)
  echo ""

  echo "### Potential Memory Leaks"
  echo ""
  leak_data=$(check_leaks)
  if [[ -n "$leak_data" ]]; then
    echo "Processes running >1h with >2GB memory (may indicate leaks):"
    echo ""
    echo "| PID | Process | Memory (GB) | Runtime |"
    echo "|-----|---------|-------------|---------|"
    echo -e "$leak_data" | while IFS='|' read -r pid cmd mem runtime; do
      [[ -n "$pid" ]] && echo "| $pid | $cmd | $mem | $runtime |"
    done
  else
    echo "No obvious memory leak suspects detected."
  fi
  echo ""

  echo "### Recommendations"
  echo ""
  if (( $(echo "$swap_used_gb > 1.0" | bc -l) )); then
    echo "- **Swap in use:** ${swap_used_gb}GB swapped - consider freeing memory"
  fi
  if [[ $used_pct -ge 75 ]]; then
    echo "- Consider closing unused IDE workspaces"
    echo "- Kill idle Claude Code sessions if not needed"
  fi
  if (( $(echo "${claudecode:-0} > 20" | bc -l) )); then
    echo "- **Claude Code** using ${claudecode}GB - normal during heavy agent work"
  fi
  echo "- Buffer/cache (${buffer_cache_gb}GB) is reclaimable if needed"
}

# Output JSON report
output_json() {
  get_memory_info

  echo "{"
  echo "  \"timestamp\": \"$(date -Iseconds)\","
  echo "  \"summary\": {"
  echo "    \"total_gb\": $mem_total_gb,"
  echo "    \"used_gb\": $mem_used_gb,"
  echo "    \"available_gb\": $mem_available_gb,"
  echo "    \"used_pct\": $used_pct,"
  echo "    \"buffer_cache_gb\": $buffer_cache_gb,"
  echo "    \"swap_used_gb\": $swap_used_gb"
  echo "  },"
  echo "  \"categories\": ["
  first=true
  while IFS='|' read -r cat mem count notes; do
    if (( $(echo "$mem > 0.1" | bc -l) )); then
      $first || echo ","
      first=false
      echo -n "    {\"name\": \"$cat\", \"memory_gb\": $mem, \"processes\": $count}"
    fi
  done < <(get_categories)
  echo ""
  echo "  ],"
  echo "  \"top_processes\": ["
  first=true
  while IFS='|' read -r pid cmd rss_gb pct; do
    $first || echo ","
    first=false
    echo -n "    {\"pid\": $pid, \"command\": \"$cmd\", \"memory_gb\": $rss_gb, \"pct\": $pct}"
  done < <(get_top_processes)
  echo ""
  echo "  ]"
  echo "}"
}

# Main
if [[ "$OUTPUT_FORMAT" == "json" ]]; then
  output_json
else
  output_markdown
fi
