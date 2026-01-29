#!/usr/bin/env bash
# Drive health and preventative maintenance checks.
# Some commands require sudo for full information.
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Check drive health and system maintenance status.

Options:
  --drives           Check drive health (SMART)
  --maintenance      Show maintenance recommendations
  --cleanup          Show what can be cleaned up
  --all              Show everything (default)
  --json             Output as JSON
  --help             Show this message

Examples:
  $(basename "$0")                # Full health report
  $(basename "$0") --drives       # Just drive health
  $(basename "$0") --cleanup      # What needs cleaning

Note: Drive SMART data requires sudo for full details:
  sudo ./run.sh health --drives
USAGE
}

SECTION="all"
OUTPUT_FORMAT="markdown"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --drives) SECTION="drives"; shift;;
    --maintenance) SECTION="maintenance"; shift;;
    --cleanup) SECTION="cleanup"; shift;;
    --all) SECTION="all"; shift;;
    --json) OUTPUT_FORMAT="json"; shift;;
    --help|-h) usage; exit 0;;
    *) echo "Unknown option: $1" >&2; usage; exit 1;;
  esac
done

# =============================================================================
# Drive Health (SMART)
# =============================================================================
check_drive_health() {
  echo "### Drive Health (SMART)"
  echo ""

  if ! command -v smartctl &>/dev/null; then
    echo "**smartctl not installed.** Install with: \`sudo apt install smartmontools\`"
    echo ""
    return
  fi

  # Check if we have sudo or are root
  local has_sudo=false
  if [[ $EUID -eq 0 ]] || sudo -n true 2>/dev/null; then
    has_sudo=true
  fi

  echo "| Drive | Model | Health | Temp | Used | Hours |"
  echo "|-------|-------|--------|------|------|-------|"

  # NVMe drives
  for dev in /dev/nvme?n1; do
    [[ -e "$dev" ]] || continue
    local name=$(basename "$dev")
    local model=$(cat /sys/block/${name%n1}/device/model 2>/dev/null | xargs || echo "Unknown")

    if $has_sudo; then
      local smart=$(sudo smartctl -a "$dev" 2>/dev/null)
      local health=$(echo "$smart" | grep -E "SMART overall-health|SMART/Health" | grep -oE "PASSED|FAILED|OK" | head -1 || echo "?")
      local temp=$(echo "$smart" | grep -E "^Temperature:" | awk '{print $2}' || echo "?")
      local used=$(echo "$smart" | grep "Percentage Used" | awk '{print $3}' || echo "?")
      local hours=$(echo "$smart" | grep "Power On Hours" | awk '{print $4}' | tr -d ',' || echo "?")
      echo "| $dev | $model | $health | ${temp}°C | ${used}% | $hours |"
    else
      echo "| $dev | $model | (need sudo) | - | - | - |"
    fi
  done

  # SATA drives
  for dev in /dev/sd?; do
    [[ -e "$dev" ]] || continue
    local name=$(basename "$dev")
    local model=$(cat /sys/block/$name/device/model 2>/dev/null | xargs || echo "Unknown")

    if $has_sudo; then
      local smart=$(sudo smartctl -a "$dev" 2>/dev/null)
      local health=$(echo "$smart" | grep -E "SMART overall-health" | grep -oE "PASSED|FAILED" || echo "?")
      local temp=$(echo "$smart" | grep "Temperature_Celsius" | awk '{print $10}' || echo "?")
      local hours=$(echo "$smart" | grep "Power_On_Hours" | awk '{print $10}' || echo "?")
      local reallocated=$(echo "$smart" | grep "Reallocated_Sector" | awk '{print $10}' || echo "0")

      local status="$health"
      [[ "$reallocated" != "0" ]] && status="WARNING (${reallocated} reallocated)"

      echo "| $dev | $model | $status | ${temp}°C | - | $hours |"
    else
      echo "| $dev | $model | (need sudo) | - | - | - |"
    fi
  done

  echo ""

  if ! $has_sudo; then
    echo "**Note:** Run with sudo for full SMART data: \`sudo ./run.sh health --drives\`"
    echo ""
  fi

  # Quick health indicators without sudo
  echo "### Filesystem Health"
  echo ""
  echo "| Mount | Used | Status |"
  echo "|-------|------|--------|"
  df -h 2>/dev/null | grep -E "^/dev/(sd|nvme)" | while read -r fs size used avail pct mount; do
    pct_num=${pct%\%}
    if [[ $pct_num -ge 95 ]]; then
      status="CRITICAL"
    elif [[ $pct_num -ge 85 ]]; then
      status="WARNING"
    else
      status="OK"
    fi
    echo "| $mount | $pct | $status |"
  done
  echo ""
}

# =============================================================================
# Maintenance Recommendations
# =============================================================================
check_maintenance() {
  echo "### Maintenance Status"
  echo ""

  echo "| Check | Status | Action |"
  echo "|-------|--------|--------|"

  # Last apt update
  local apt_updated="Unknown"
  if [[ -f /var/lib/apt/periodic/update-stamp ]]; then
    local stamp=$(stat -c %Y /var/lib/apt/periodic/update-stamp 2>/dev/null || echo 0)
    local now=$(date +%s)
    local days=$(( (now - stamp) / 86400 ))
    if [[ $days -gt 7 ]]; then
      apt_updated="$days days ago"
      echo "| Package lists | WARNING | \`sudo apt update\` |"
    else
      echo "| Package lists | OK ($days days ago) | - |"
    fi
  else
    echo "| Package lists | Unknown | \`sudo apt update\` |"
  fi

  # Upgradeable packages
  local upgradeable=$(apt list --upgradable 2>/dev/null | grep -c upgradable || echo 0)
  if [[ $upgradeable -gt 10 ]]; then
    echo "| Pending updates | $upgradeable packages | \`sudo apt upgrade\` |"
  else
    echo "| Pending updates | OK ($upgradeable) | - |"
  fi

  # Kernel updates (requires reboot)
  local running_kernel=$(uname -r)
  local latest_kernel=$(ls -1 /boot/vmlinuz-* 2>/dev/null | sort -V | tail -1 | sed 's/.*vmlinuz-//')
  if [[ "$running_kernel" != "$latest_kernel" && -n "$latest_kernel" ]]; then
    echo "| Kernel | Reboot needed | Running: $running_kernel |"
  else
    echo "| Kernel | OK | $running_kernel |"
  fi

  # Journal size
  local journal_size=$(journalctl --disk-usage 2>/dev/null | grep -oE "[0-9]+\.[0-9]+[GM]" | head -1 || echo "?")
  echo "| Journal logs | $journal_size | \`sudo journalctl --vacuum-size=500M\` |"

  # Snap cleanup
  local snap_revisions=$(snap list --all 2>/dev/null | grep disabled | wc -l)
  if [[ $snap_revisions -gt 3 ]]; then
    echo "| Old snaps | $snap_revisions disabled | See cleanup commands |"
  else
    echo "| Old snaps | OK | - |"
  fi

  echo ""

  # Scheduled tasks
  echo "### SMART Self-Tests"
  echo ""
  echo "Run periodic self-tests to catch failing drives early:"
  echo ""
  echo "\`\`\`bash"
  echo "# Short test (2 minutes)"
  echo "sudo smartctl -t short /dev/nvme0n1"
  echo ""
  echo "# Long test (hours, run overnight)"
  echo "sudo smartctl -t long /dev/sda"
  echo ""
  echo "# Check test results"
  echo "sudo smartctl -l selftest /dev/nvme0n1"
  echo "\`\`\`"
  echo ""
}

# =============================================================================
# Cleanup Recommendations
# =============================================================================
check_cleanup() {
  echo "### Cleanup Opportunities"
  echo ""

  echo "| Category | Size | Command |"
  echo "|----------|------|---------|"

  # Docker
  if command -v docker &>/dev/null; then
    local docker_reclaimable=$(docker system df 2>/dev/null | grep "Build cache" | awk '{print $4}' || echo "?")
    local docker_images=$(docker images -f "dangling=true" -q 2>/dev/null | wc -l)
    local docker_containers=$(docker ps -a -f "status=exited" -q 2>/dev/null | wc -l)

    if [[ $docker_images -gt 0 || $docker_containers -gt 0 ]]; then
      echo "| Docker unused | $docker_images images, $docker_containers containers | \`docker system prune -a\` |"
    else
      echo "| Docker | Clean | - |"
    fi
  fi

  # APT cache
  local apt_cache=$(du -sh /var/cache/apt/archives 2>/dev/null | cut -f1 || echo "?")
  echo "| APT cache | $apt_cache | \`sudo apt clean\` |"

  # Pip cache
  local pip_cache=$(du -sh ~/.cache/pip 2>/dev/null | cut -f1 || echo "0")
  [[ "$pip_cache" != "0" ]] && echo "| Pip cache | $pip_cache | \`pip cache purge\` |"

  # npm cache
  local npm_cache=$(du -sh ~/.npm/_cacache 2>/dev/null | cut -f1 || echo "0")
  [[ "$npm_cache" != "0" ]] && echo "| npm cache | $npm_cache | \`npm cache clean --force\` |"

  # Trash
  local trash_size=$(du -sh ~/.local/share/Trash 2>/dev/null | cut -f1 || echo "0")
  [[ "$trash_size" != "0" ]] && echo "| Trash | $trash_size | \`rm -rf ~/.local/share/Trash/*\` |"

  # Thumbnails
  local thumb_size=$(du -sh ~/.cache/thumbnails 2>/dev/null | cut -f1 || echo "0")
  [[ "$thumb_size" != "0" ]] && echo "| Thumbnails | $thumb_size | \`rm -rf ~/.cache/thumbnails/*\` |"

  # Old kernels (count)
  local kernel_count=$(ls /boot/vmlinuz-* 2>/dev/null | wc -l)
  if [[ $kernel_count -gt 2 ]]; then
    echo "| Old kernels | $kernel_count installed | \`sudo apt autoremove\` |"
  fi

  echo ""

  # Cleanup script
  echo "### Quick Cleanup Script"
  echo ""
  echo "\`\`\`bash"
  echo "# Safe cleanup (won't break anything)"
  echo "sudo apt autoremove -y"
  echo "sudo apt clean"
  echo "pip cache purge 2>/dev/null || true"
  echo "npm cache clean --force 2>/dev/null || true"
  echo "docker system prune -f 2>/dev/null || true"
  echo "sudo journalctl --vacuum-size=500M"
  echo "\`\`\`"
  echo ""
}

# =============================================================================
# Main Output
# =============================================================================
output_markdown() {
  echo "## System Health Report"
  echo ""
  echo "**Generated:** $(date '+%Y-%m-%d %H:%M:%S')"
  echo ""

  case "$SECTION" in
    drives)
      check_drive_health
      ;;
    maintenance)
      check_maintenance
      ;;
    cleanup)
      check_cleanup
      ;;
    all)
      check_drive_health
      check_maintenance
      check_cleanup
      ;;
  esac
}

# Main
if [[ "$OUTPUT_FORMAT" == "json" ]]; then
  echo "JSON output not yet implemented for health"
  exit 1
else
  output_markdown
fi
