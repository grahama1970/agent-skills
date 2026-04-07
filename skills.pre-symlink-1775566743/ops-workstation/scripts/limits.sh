#!/usr/bin/env bash
# Check system limits that affect development workloads.
# Catches issues like ENOSPC inotify before they break agents.
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Check kernel and user limits that affect development workloads.

Options:
  --fix              Show fix commands for any warnings
  --json             Output as JSON
  --help             Show this message

Checks:
  - inotify watchers (file watching for IDEs, agents, node)
  - inotify instances
  - open file limits (ulimit -n)
  - max user processes
USAGE
}

SHOW_FIX=false
OUTPUT_FORMAT="markdown"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fix) SHOW_FIX=true; shift;;
    --json) OUTPUT_FORMAT="json"; shift;;
    --help|-h) usage; exit 0;;
    *) echo "Unknown option: $1" >&2; usage; exit 1;;
  esac
done

# Thresholds (warn when usage exceeds these percentages)
INOTIFY_WARN_PCT=70
INOTIFY_CRIT_PCT=90
FILES_WARN_PCT=50
FILES_CRIT_PCT=80

warn_count=0
crit_count=0

# =============================================================================
# inotify Watchers
# =============================================================================
check_inotify_watchers() {
  local max_watches=$(cat /proc/sys/fs/inotify/max_user_watches 2>/dev/null || echo 0)

  # Count current watches (approximate - count inotify fds)
  local current_instances=$(find /proc/*/fd -lname 'anon_inode:inotify' 2>/dev/null | wc -l)

  # Estimate watches per instance (conservative: assume 500 avg)
  # This is imprecise but gives a rough idea
  local estimated_watches=$((current_instances * 500))
  local usage_pct=0

  if [[ $max_watches -gt 0 ]]; then
    usage_pct=$((estimated_watches * 100 / max_watches))
  fi

  local status="OK"
  local action="-"

  if [[ $usage_pct -ge $INOTIFY_CRIT_PCT ]]; then
    status="CRITICAL"
    action="Increase limit immediately"
    ((crit_count++))
  elif [[ $usage_pct -ge $INOTIFY_WARN_PCT ]]; then
    status="WARNING"
    action="Consider increasing limit"
    ((warn_count++))
  fi

  echo "| inotify watchers | $max_watches max | ~$current_instances instances | $status |"

  if [[ "$SHOW_FIX" == "true" && "$status" != "OK" ]]; then
    echo ""
    echo "**Fix inotify limit:**"
    echo "\`\`\`bash"
    echo "# Temporary (until reboot)"
    echo "echo 524288 | sudo tee /proc/sys/fs/inotify/max_user_watches"
    echo ""
    echo "# Permanent"
    echo "echo 'fs.inotify.max_user_watches=524288' | sudo tee -a /etc/sysctl.conf"
    echo "sudo sysctl -p"
    echo "\`\`\`"
    echo ""
  fi
}

# =============================================================================
# inotify Instances
# =============================================================================
check_inotify_instances() {
  local max_instances=$(cat /proc/sys/fs/inotify/max_user_instances 2>/dev/null || echo 0)
  local current_instances=$(find /proc/*/fd -lname 'anon_inode:inotify' 2>/dev/null | wc -l)

  local usage_pct=0
  if [[ $max_instances -gt 0 ]]; then
    usage_pct=$((current_instances * 100 / max_instances))
  fi

  local status="OK"
  if [[ $usage_pct -ge $INOTIFY_CRIT_PCT ]]; then
    status="CRITICAL"
    ((crit_count++))
  elif [[ $usage_pct -ge $INOTIFY_WARN_PCT ]]; then
    status="WARNING"
    ((warn_count++))
  fi

  echo "| inotify instances | $max_instances max | $current_instances used (${usage_pct}%) | $status |"
}

# =============================================================================
# Open Files Limit
# =============================================================================
check_open_files() {
  local soft_limit=$(ulimit -Sn 2>/dev/null || echo 0)
  local hard_limit=$(ulimit -Hn 2>/dev/null || echo 0)

  # Count open files for current user
  local current_user=$(whoami)
  local open_files=$(lsof -u "$current_user" 2>/dev/null | wc -l || echo 0)

  local usage_pct=0
  if [[ $soft_limit -gt 0 ]]; then
    usage_pct=$((open_files * 100 / soft_limit))
  fi

  local status="OK"
  if [[ $usage_pct -ge $FILES_CRIT_PCT ]]; then
    status="CRITICAL"
    ((crit_count++))
  elif [[ $usage_pct -ge $FILES_WARN_PCT ]]; then
    status="WARNING"
    ((warn_count++))
  fi

  echo "| open files | $soft_limit soft / $hard_limit hard | $open_files used (${usage_pct}%) | $status |"

  if [[ "$SHOW_FIX" == "true" && "$status" != "OK" ]]; then
    echo ""
    echo "**Fix open files limit:**"
    echo "\`\`\`bash"
    echo "# Add to /etc/security/limits.conf"
    echo "$current_user soft nofile 65536"
    echo "$current_user hard nofile 524288"
    echo "\`\`\`"
    echo ""
  fi
}

# =============================================================================
# Max Processes
# =============================================================================
check_max_procs() {
  local max_procs=$(ulimit -u 2>/dev/null || echo 0)
  local current_procs=$(ps -u "$(whoami)" --no-headers 2>/dev/null | wc -l || echo 0)

  local usage_pct=0
  if [[ $max_procs -gt 0 && $max_procs -lt 1000000 ]]; then
    usage_pct=$((current_procs * 100 / max_procs))
  fi

  local status="OK"
  if [[ $usage_pct -ge $FILES_CRIT_PCT ]]; then
    status="CRITICAL"
    ((crit_count++))
  elif [[ $usage_pct -ge $FILES_WARN_PCT ]]; then
    status="WARNING"
    ((warn_count++))
  fi

  echo "| max processes | $max_procs limit | $current_procs running (${usage_pct}%) | $status |"
}

# =============================================================================
# Recommended Values
# =============================================================================
show_recommended() {
  echo ""
  echo "### Recommended Values for Development Workstation"
  echo ""
  echo "| Setting | Default | Recommended | Why |"
  echo "|---------|---------|-------------|-----|"
  echo "| fs.inotify.max_user_watches | 65536 | 524288 | IDEs, agents, node watchers |"
  echo "| fs.inotify.max_user_instances | 128 | 512 | Multiple agent processes |"
  echo "| nofile (soft) | 1024 | 65536 | Many open sockets/files |"
  echo "| nofile (hard) | 4096 | 524288 | Burst capacity |"
  echo ""
}

# =============================================================================
# Main Output
# =============================================================================
output_markdown() {
  echo "## System Limits Check"
  echo ""
  echo "**Generated:** $(date '+%Y-%m-%d %H:%M:%S')"
  echo ""
  echo "| Limit | Max | Current | Status |"
  echo "|-------|-----|---------|--------|"

  check_inotify_watchers
  check_inotify_instances
  check_open_files
  check_max_procs

  echo ""

  if [[ $crit_count -gt 0 ]]; then
    echo "**CRITICAL:** $crit_count limit(s) near exhaustion. Fix immediately to prevent crashes."
    echo ""
  elif [[ $warn_count -gt 0 ]]; then
    echo "**WARNING:** $warn_count limit(s) approaching threshold. Consider increasing."
    echo ""
  else
    echo "All limits healthy."
    echo ""
  fi

  if [[ "$SHOW_FIX" == "true" ]]; then
    show_recommended
  fi
}

output_json() {
  local max_watches=$(cat /proc/sys/fs/inotify/max_user_watches 2>/dev/null || echo 0)
  local max_instances=$(cat /proc/sys/fs/inotify/max_user_instances 2>/dev/null || echo 0)
  local current_instances=$(find /proc/*/fd -lname 'anon_inode:inotify' 2>/dev/null | wc -l)
  local soft_limit=$(ulimit -Sn 2>/dev/null || echo 0)
  local open_files=$(lsof -u "$(whoami)" 2>/dev/null | wc -l || echo 0)
  local max_procs=$(ulimit -u 2>/dev/null || echo 0)
  local current_procs=$(ps -u "$(whoami)" --no-headers 2>/dev/null | wc -l || echo 0)

  cat <<EOF
{
  "timestamp": "$(date -Iseconds)",
  "inotify": {
    "max_watches": $max_watches,
    "max_instances": $max_instances,
    "current_instances": $current_instances
  },
  "files": {
    "soft_limit": $soft_limit,
    "open": $open_files
  },
  "processes": {
    "max": $max_procs,
    "current": $current_procs
  },
  "warnings": $warn_count,
  "critical": $crit_count
}
EOF
}

# Main
if [[ "$OUTPUT_FORMAT" == "json" ]]; then
  output_json
else
  output_markdown
fi

# Exit with warning/critical status
if [[ $crit_count -gt 0 ]]; then
  exit 2
elif [[ $warn_count -gt 0 ]]; then
  exit 1
fi
exit 0
