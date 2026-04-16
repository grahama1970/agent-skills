#!/usr/bin/env bash
# Remove the Ollama watchdog cron job
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CHECK_SCRIPT="${SKILL_DIR}/scripts/check.sh"

if ! crontab -l 2>/dev/null | grep -qF "$CHECK_SCRIPT"; then
    echo "No watchdog cron found"
    exit 0
fi

crontab -l 2>/dev/null | grep -vF "$CHECK_SCRIPT" | grep -v "# monitor-ollama" | crontab -
echo "Removed Ollama watchdog cron"
