#!/usr/bin/env bash
# Summarize system headroom (CPU, memory, disk) and warn on thresholds.
set -euo pipefail

DISK_THRESHOLD=${DISK_THRESHOLD:-85}
MEM_THRESHOLD=${MEM_THRESHOLD:-90}
usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Options:
  --disk <percent>   Warn if disk usage exceeds this percentage (default: $DISK_THRESHOLD).
  --mem <percent>    Warn if memory usage exceeds this percentage (default: $MEM_THRESHOLD).
  --help             Show this message.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --disk)
      DISK_THRESHOLD="$2"; shift 2;;
    --mem)
      MEM_THRESHOLD="$2"; shift 2;;
    --help|-h)
      usage; exit 0;;
    *)
      echo "Unknown option: $1" >&2
      usage; exit 1;;
  esac
done

printf "System summary (%s)\n" "$(date)"
printf "CPU load: %s\n" "$(uptime)"

df -h

warn=0
while read -r fs size used avail pct mount; do
  pct=${pct%%%}
  if [[ $pct -ge $DISK_THRESHOLD ]]; then
    echo "WARNING: $mount at ${pct}% utilization"
    warn=1
  fi
done < <(df -h | tail -n +2)

read -r _ mem_total _ <<<"$(grep MemTotal /proc/meminfo)"
read -r _ mem_available _ <<<"$(grep MemAvailable /proc/meminfo)"
if [[ -n "$mem_total" && -n "$mem_available" ]]; then
  used_pct=$(( ( (mem_total - mem_available) * 100 ) / mem_total ))
  echo "Memory usage: $used_pct%"
  if [[ $used_pct -ge $MEM_THRESHOLD ]]; then
    echo "WARNING: memory usage above threshold ($MEM_THRESHOLD%)"
    warn=1
  fi
fi

exit $warn
