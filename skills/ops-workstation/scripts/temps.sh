#!/usr/bin/env bash
# Temperature monitoring: CPU, GPU, NVMe with configurable thresholds and exit codes.
# Exit codes: 0=OK, 1=WARNING, 2=CRITICAL
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Temperature monitoring for key components.

Options:
  --json           Output as JSON (single object) or set OUTPUT=json env
  --warn <C>       Warning threshold (default: 75, or WARN_THRESHOLD env)
  --crit <C>       Critical threshold (default: 85, or CRIT_THRESHOLD env)
  --help           Show this message

Exit Codes:
  0 = All temps OK
  1 = Warning (temp >= warn threshold)
  2 = Critical (temp >= crit threshold)
USAGE
}

OUTPUT="${OUTPUT:-markdown}"
WARN="${WARN_THRESHOLD:-75}"
CRIT="${CRIT_THRESHOLD:-85}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --json) OUTPUT="json"; shift;;
    --warn) WARN="$2"; shift 2;;
    --crit) CRIT="$2"; shift 2;;
    --help|-h) usage; exit 0;;
    *) echo "Unknown option: $1" >&2; usage; exit 1;;
  esac
done

gpu_temp() {
  if command -v nvidia-smi >/dev/null 2>&1; then
    local gtemp vramtemp
    gtemp=$(nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits 2>/dev/null | head -1 | xargs || echo "")
    vramtemp=$(nvidia-smi --query-gpu=temperature.memory --format=csv,noheader,nounits 2>/dev/null | head -1 | xargs 2>/dev/null || echo "")
    echo "${gtemp:-}|${vramtemp:-}"
  else
    echo "|"
  fi
}

cpu_temps_fallback() {
  if command -v sensors >/dev/null 2>&1; then
    # Extract CPU temps from lm-sensors output
    sensors 2>/dev/null | awk -F'[:+ ]+' '/Package id|Tdie|Tctl|CPU|Core [0-9]/ {
      gsub(/°C/,"",$0)
      gsub(/\xc2\xb0C/,"",$0)
      # Get the temperature value (usually field 2 or 3)
      for(i=2; i<=NF; i++) {
        if($i ~ /^[0-9]+(\.[0-9]+)?$/) {
          printf "%s|%s\n", $1, int($i)
          break
        }
      }
    }' | head -10
  else
    echo ""
  fi
}

nvme_temps() {
  for dev in /dev/nvme?n1; do
    [[ -e "$dev" ]] || continue
    if command -v smartctl >/dev/null 2>&1; then
      local temp
      temp=$(smartctl -a "$dev" 2>/dev/null | awk '/^Temperature:/ {print $2}' | head -1)
      [[ -z "$temp" ]] && temp=$(smartctl -a "$dev" 2>/dev/null | awk '/Temperature.*Celsius/ {for(i=1;i<=NF;i++) if($i ~ /^[0-9]+$/) {print $i; exit}}' | head -1)
      [[ -n "$temp" ]] && echo "$(basename "$dev")|$temp"
    fi
  done
}

status_for() {
  local t="$1"
  if [[ -z "$t" || ! "$t" =~ ^[0-9]+$ ]]; then echo "UNKNOWN"; return; fi
  if (( t >= CRIT )); then echo "CRITICAL"
  elif (( t >= WARN )); then echo "WARNING"
  else echo "OK"
  fi
}

aggregate_status=0
update_exit() {
  local t="$1"
  if [[ -z "$t" || ! "$t" =~ ^[0-9]+$ ]]; then return; fi
  if (( t >= CRIT )); then aggregate_status=2
  elif (( t >= WARN && aggregate_status < 2 )); then aggregate_status=1
  fi
}

output_markdown() {
  echo "## Temperature Report"
  echo ""
  echo "**Generated:** $(date '+%Y-%m-%d %H:%M:%S')"
  echo "**Thresholds:** Warning=${WARN}C, Critical=${CRIT}C"
  echo ""
  echo "| Component | Temp (C) | Status |"
  echo "|-----------|----------|--------|"

  # CPU
  local cpu_lines
  cpu_lines=$(cpu_temps_fallback)
  if [[ -n "$cpu_lines" ]]; then
    while IFS='|' read -r label temp; do
      [[ -z "$temp" ]] && continue
      echo "| CPU ($label) | $temp | $(status_for "$temp") |"
      update_exit "$temp"
    done <<< "$cpu_lines"
  else
    echo "| CPU | - | sensors not installed (sudo apt install lm-sensors) |"
  fi

  # GPU
  local gt vt
  IFS='|' read -r gt vt < <(gpu_temp)
  if [[ -n "$gt" ]]; then
    echo "| GPU Core | $gt | $(status_for "$gt") |"
    update_exit "$gt"
    if [[ -n "$vt" ]]; then
      echo "| GPU VRAM | $vt | $(status_for "$vt") |"
      update_exit "$vt"
    fi
  else
    echo "| GPU | - | nvidia-smi not available |"
  fi

  # NVMe
  local nvme_lines
  nvme_lines=$(nvme_temps)
  if [[ -n "$nvme_lines" ]]; then
    while IFS='|' read -r dev temp; do
      [[ -z "$temp" ]] && continue
      echo "| NVMe ($dev) | $temp | $(status_for "$temp") |"
      update_exit "$temp"
    done <<< "$nvme_lines"
  fi

  echo ""
  case $aggregate_status in
    0) echo "**Status:** All temperatures OK" ;;
    1) echo "**Status:** WARNING - Some temps elevated" ;;
    2) echo "**Status:** CRITICAL - Temps too high!" ;;
  esac

  exit "$aggregate_status"
}

output_json() {
  echo "{"
  echo "  \"timestamp\": \"$(date -Iseconds)\","
  echo "  \"thresholds\": {\"warn\": $WARN, \"crit\": $CRIT},"
  echo "  \"cpu\": ["
  local first=true
  local cpu_lines
  cpu_lines=$(cpu_temps_fallback)
  if [[ -n "$cpu_lines" ]]; then
    while IFS='|' read -r label temp; do
      [[ -z "$temp" ]] && continue
      $first || echo ","
      first=false
      echo -n "    {\"label\":\"$label\",\"temp_c\": $temp, \"status\":\"$(status_for "$temp")\"}"
      update_exit "$temp"
    done <<< "$cpu_lines"
  fi
  echo ""
  echo "  ],"

  local gt vt
  IFS='|' read -r gt vt < <(gpu_temp)
  if [[ -n "$gt" ]]; then
    echo "  \"gpu\": {\"core_c\": $gt, \"vram_c\": ${vt:-null}, \"status_core\": \"$(status_for "$gt")\"},"
    update_exit "$gt"
    [[ -n "$vt" ]] && update_exit "$vt"
  else
    echo "  \"gpu\": {\"core_c\": null, \"vram_c\": null, \"status_core\": \"UNKNOWN\"},"
  fi

  echo "  \"nvme\": ["
  local firstn=true
  local nvme_lines
  nvme_lines=$(nvme_temps)
  if [[ -n "$nvme_lines" ]]; then
    while IFS='|' read -r dev temp; do
      [[ -z "$temp" ]] && continue
      $firstn || echo ","
      firstn=false
      echo -n "    {\"device\":\"$dev\",\"temp_c\": $temp, \"status\":\"$(status_for "$temp")\"}"
      update_exit "$temp"
    done <<< "$nvme_lines"
  fi
  echo ""
  echo "  ],"
  echo "  \"exit_code\": $aggregate_status"
  echo "}"
  exit "$aggregate_status"
}

if [[ "$OUTPUT" == "json" ]]; then
  output_json
else
  output_markdown
fi
