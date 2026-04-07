#!/usr/bin/env bash
# Identify processes with sustained high CPU usage.
# Flags processes that have been consuming >CPU_THRESHOLD% for >MIN_MINUTES.
# This catches runaway dev tools (uvicorn --reload, webpack --watch, etc.)
# that peg a core indefinitely without the user noticing.
set -euo pipefail

CPU_THRESHOLD=${CPU_THRESHOLD:-80}
MIN_MINUTES=${MIN_MINUTES:-30}
JSON_OUTPUT=false
FIX_MODE=false
TOP_N=10

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Finds processes with sustained high CPU usage.

Options:
  --cpu <percent>    CPU threshold (default: $CPU_THRESHOLD)
  --min <minutes>    Minimum runtime to flag (default: $MIN_MINUTES)
  --top <n>          Show top N CPU consumers (default: $TOP_N)
  --json             JSON output for agents
  --fix              Offer to kill flagged processes
  --help             Show this message

Examples:
  $(basename "$0")                # Find sustained CPU hogs (>80% for >30min)
  $(basename "$0") --cpu 50       # Lower threshold to 50%
  $(basename "$0") --min 5        # Flag anything >5 minutes
  $(basename "$0") --json         # Agent-parseable output
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --cpu)      CPU_THRESHOLD="$2"; shift 2;;
    --min)      MIN_MINUTES="$2"; shift 2;;
    --top)      TOP_N="$2"; shift 2;;
    --json)     JSON_OUTPUT=true; shift;;
    --fix)      FIX_MODE=true; shift;;
    --help|-h)  usage; exit 0;;
    *)          echo "Unknown option: $1" >&2; usage; exit 1;;
  esac
done

# Collect process data: PID, %CPU, elapsed time, command
# ps elapsed format: [[DD-]HH:]MM:SS
parse_elapsed_minutes() {
  local elapsed="$1"
  local days=0 hours=0 mins=0

  # Handle DD-HH:MM:SS
  if [[ "$elapsed" == *-* ]]; then
    days="${elapsed%%-*}"
    elapsed="${elapsed#*-}"
  fi

  # Count colons to determine format
  local colons="${elapsed//[^:]}"
  if [[ ${#colons} -eq 2 ]]; then
    # HH:MM:SS
    IFS=: read -r hours mins _ <<< "$elapsed"
  elif [[ ${#colons} -eq 1 ]]; then
    # MM:SS
    IFS=: read -r mins _ <<< "$elapsed"
  fi

  # Strip leading zeros to avoid octal interpretation
  days=$((10#$days))
  hours=$((10#$hours))
  mins=$((10#$mins))

  echo $(( days * 1440 + hours * 60 + mins ))
}

exit_code=0
hog_count=0
declare -a hog_pids=()
declare -a hog_lines=()
declare -a json_entries=()

# Get top CPU consumers, skip header and kernel threads
while IFS= read -r line; do
  pid=$(echo "$line" | awk '{print $1}')
  cpu=$(echo "$line" | awk '{print $2}')
  elapsed=$(echo "$line" | awk '{print $3}')
  cmd=$(echo "$line" | awk '{for(i=4;i<=NF;i++) printf "%s ", $i; print ""}' | sed 's/ *$//')

  # Skip kernel threads and zombies
  [[ -z "$pid" || "$pid" == "PID" ]] && continue
  [[ "$cmd" == \[* ]] && continue

  # Parse CPU (handle decimal)
  cpu_int=${cpu%%.*}
  [[ -z "$cpu_int" ]] && cpu_int=0

  # Parse elapsed to minutes
  mins=$(parse_elapsed_minutes "$elapsed")

  if [[ $cpu_int -ge $CPU_THRESHOLD && $mins -ge $MIN_MINUTES ]]; then
    hog_count=$((hog_count + 1))
    hog_pids+=("$pid")
    exit_code=1

    # Identify common culprits
    diagnosis=""
    if echo "$cmd" | grep -q '\-\-reload'; then
      diagnosis="Dev reload flag causing filesystem polling loop"
    elif echo "$cmd" | grep -q '\-\-watch'; then
      diagnosis="File watcher in hot loop"
    elif echo "$cmd" | grep -q 'webpack'; then
      diagnosis="Webpack dev server (consider production build)"
    elif echo "$cmd" | grep -q 'node.*inspector'; then
      diagnosis="Node inspector debug session left running"
    elif echo "$cmd" | grep -q 'python.*-m pytest'; then
      diagnosis="Stuck test runner"
    fi

    if $JSON_OUTPUT; then
      json_entries+=("{\"pid\":$pid,\"cpu\":$cpu,\"runtime_minutes\":$mins,\"command\":\"$(echo "$cmd" | sed 's/"/\\"/g' | head -c 200)\",\"diagnosis\":\"$diagnosis\"}")
    else
      hog_lines+=("$(printf "  PID %-8s │ CPU %5s%% │ Running %s │ %s" "$pid" "$cpu" "${mins}min" "$(echo "$cmd" | head -c 120)")")
      if [[ -n "$diagnosis" ]]; then
        hog_lines+=("$(printf "               │ Diagnosis: %s" "$diagnosis")")
      fi
    fi
  fi
done < <(ps -eo pid,%cpu,etime,args --sort=-%cpu --no-headers 2>/dev/null | head -"$((TOP_N + 5))")

if $JSON_OUTPUT; then
  printf '{"timestamp":"%s","threshold_cpu":%d,"threshold_minutes":%d,"hogs":[%s],"exit_code":%d}\n' \
    "$(date -Iseconds)" "$CPU_THRESHOLD" "$MIN_MINUTES" \
    "$(IFS=,; echo "${json_entries[*]:-}")" "$exit_code"
  exit $exit_code
fi

# Markdown output
printf "## CPU Hogs Report (%s)\n\n" "$(date '+%Y-%m-%d %H:%M')"
printf "Threshold: >%d%% CPU sustained for >%d minutes\n\n" "$CPU_THRESHOLD" "$MIN_MINUTES"

if [[ $hog_count -eq 0 ]]; then
  echo "No sustained CPU hogs found. System is clean."
  echo ""
  # Still show top consumers for context
  echo "### Top CPU Consumers (current snapshot)"
  echo ""
  ps -eo pid,%cpu,etime,args --sort=-%cpu --no-headers 2>/dev/null | head -5 | while IFS= read -r line; do
    pid=$(echo "$line" | awk '{print $1}')
    cpu=$(echo "$line" | awk '{print $2}')
    elapsed=$(echo "$line" | awk '{print $3}')
    cmd=$(echo "$line" | awk '{for(i=4;i<=NF;i++) printf "%s ", $i; print ""}' | sed 's/ *$//' | head -c 100)
    printf "  PID %-8s │ %5s%% │ %s │ %s\n" "$pid" "$cpu" "$elapsed" "$cmd"
  done
else
  printf "### Found %d sustained CPU hog(s)\n\n" "$hog_count"
  for line in "${hog_lines[@]}"; do
    echo "$line"
  done
  echo ""

  if $FIX_MODE; then
    echo "### Fix Mode"
    echo ""
    for pid in "${hog_pids[@]}"; do
      cmd=$(ps -p "$pid" -o args= 2>/dev/null || echo "already gone")
      echo "Sending SIGTERM to PID $pid ($cmd)"
      kill "$pid" 2>/dev/null || echo "  Failed (process may have exited)"
    done
    echo ""
    echo "Sent SIGTERM to ${#hog_pids[@]} process(es). Check with: ps -p ${hog_pids[*]} 2>/dev/null"
  else
    echo "Run with --fix to send SIGTERM to flagged processes."
    echo "Or investigate manually: ps -p ${hog_pids[*]} -o pid,%cpu,etime,args"
  fi
fi

echo ""
printf "Load average: %s\n" "$(cut -d' ' -f1-3 /proc/loadavg)"

exit $exit_code
