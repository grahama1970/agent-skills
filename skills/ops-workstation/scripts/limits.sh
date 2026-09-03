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
INOTIFY_SNAPSHOT="${TMPDIR:-/tmp}/ops-workstation-inotify-$$.tsv"
trap 'rm -f "$INOTIFY_SNAPSHOT"' EXIT

collect_inotify() {
  [[ -s "$INOTIFY_SNAPSHOT" ]] && return 0
  python3 - "$INOTIFY_SNAPSHOT" <<'PYI'
import os, sys
out = sys.argv[1]
uid = os.getuid()
rows = []
total = 0
instances = 0
for pid in filter(str.isdigit, os.listdir('/proc')):
    try:
        if os.stat(f'/proc/{pid}').st_uid != uid:
            continue
        comm = open(f'/proc/{pid}/comm').read().strip()
        cmd = open(f'/proc/{pid}/cmdline', 'rb').read().replace(b'\0', b' ').decode('utf-8', 'ignore').strip()
        watches = 0
        fds = 0
        for fd in os.listdir(f'/proc/{pid}/fdinfo'):
            try:
                data = open(f'/proc/{pid}/fdinfo/{fd}', errors='ignore').read()
            except Exception:
                continue
            count = data.count('inotify wd:')
            if count:
                watches += count
                fds += 1
        if watches:
            total += watches
            instances += fds
            rows.append((watches, fds, int(pid), comm, cmd[:160]))
    except Exception:
        pass
with open(out, 'w') as fh:
    fh.write(f'TOTAL\t{total}\t{instances}\n')
    for row in sorted(rows, reverse=True):
        fh.write('%s\t%s\t%s\t%s\t%s\n' % row)
PYI
}

inotify_total() { collect_inotify; awk -F'\t' '$1=="TOTAL" {print $2}' "$INOTIFY_SNAPSHOT"; }
inotify_instances() { collect_inotify; awk -F'\t' '$1=="TOTAL" {print $3}' "$INOTIFY_SNAPSHOT"; }

# =============================================================================
# inotify Watchers
# =============================================================================
check_inotify_watchers() {
  local max_watches=$(cat /proc/sys/fs/inotify/max_user_watches 2>/dev/null || echo 0)
  local current_watches=$(inotify_total)
  local usage_pct=0

  if [[ $max_watches -gt 0 ]]; then
    usage_pct=$((current_watches * 100 / max_watches))
  fi

  local status="OK"

  if [[ $usage_pct -ge $INOTIFY_CRIT_PCT ]]; then
    status="CRITICAL"
    ((crit_count++))
  elif [[ $usage_pct -ge $INOTIFY_WARN_PCT ]]; then
    status="WARNING"
    ((warn_count++))
  fi

  echo "| inotify watchers | $max_watches max | $current_watches used (${usage_pct}%) | $status |"

  if [[ "$SHOW_FIX" == "true" && "$status" != "OK" ]]; then
    echo ""
    echo "**Fix inotify limit:**"
    echo "```bash"
    echo "echo 'fs.inotify.max_user_watches=2097152' | sudo tee /etc/sysctl.d/99-local-inotify-watches.conf"
    echo "sudo sysctl --system"
    echo "```"
    echo ""
  fi
}

show_inotify_top() {
  collect_inotify
  echo "### Top inotify watch users"
  echo ""
  echo "| Watches | PID | Process | Command |"
  echo "|---------|-----|---------|---------|"
  awk -F'\t' '$1!="TOTAL" {gsub(/\|/, " ", $5); printf "| %s | %s | %s | `%s` |\n", $1, $3, $4, $5}' "$INOTIFY_SNAPSHOT" | head -10
  echo ""
}

inotify_top_json() {
  collect_inotify
  python3 - "$INOTIFY_SNAPSHOT" <<'PYJ'
import json, sys
rows = []
with open(sys.argv[1]) as fh:
    for line in fh:
        if line.startswith('TOTAL\t'):
            continue
        watches, fds, pid, comm, cmd = line.rstrip('\n').split('\t', 4)
        rows.append({"watches": int(watches), "instances": int(fds), "pid": int(pid), "process": comm, "command": cmd})
        if len(rows) == 10:
            break
print(json.dumps(rows))
PYJ
}

# =============================================================================
# inotify Instances
# =============================================================================
check_inotify_instances() {
  local max_instances=$(cat /proc/sys/fs/inotify/max_user_instances 2>/dev/null || echo 0)
  local current_instances=$(inotify_instances)

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
  echo "| fs.inotify.max_user_watches | 65536 | 2097152 | IDEs, agents, node watchers |"
  echo "| fs.inotify.max_user_instances | 128 | 4096 | Multiple agent processes |"
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
  show_inotify_top

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
  local current_watches=$(inotify_total)
  local current_instances=$(inotify_instances)
  local watch_pct=0
  if [[ $max_watches -gt 0 ]]; then watch_pct=$((current_watches * 100 / max_watches)); fi
  if [[ $watch_pct -ge $INOTIFY_CRIT_PCT ]]; then ((crit_count++)); elif [[ $watch_pct -ge $INOTIFY_WARN_PCT ]]; then ((warn_count++)); fi
  local top_watchers=$(inotify_top_json)
  local soft_limit=$(ulimit -Sn 2>/dev/null || echo 0)
  local open_files=$(lsof -u "$(whoami)" 2>/dev/null | wc -l || echo 0)
  local max_procs=$(ulimit -u 2>/dev/null || echo 0)
  local current_procs=$(ps -u "$(whoami)" --no-headers 2>/dev/null | wc -l || echo 0)

  cat <<EOF
{
  "timestamp": "$(date -Iseconds)",
  "inotify": {
    "max_watches": $max_watches,
    "current_watches": $current_watches,
    "watch_usage_pct": $watch_pct,
    "max_instances": $max_instances,
    "current_instances": $current_instances,
    "top_watchers": $top_watchers
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
