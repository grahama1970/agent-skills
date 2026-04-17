#!/usr/bin/env bash
# Install the Ollama watchdog as a cron job (every 2 minutes)
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CHECK_SCRIPT="${SKILL_DIR}/scripts/check.sh"

if ! [ -x "$CHECK_SCRIPT" ]; then
    echo "ERROR: $CHECK_SCRIPT not found or not executable"
    exit 1
fi

CRON_LINE="*/2 * * * * ${CHECK_SCRIPT} >> /tmp/ollama_watchdog.log 2>&1"

# Check if already installed
if crontab -l 2>/dev/null | grep -qF "monitor-ollama" || crontab -l 2>/dev/null | grep -qF "$CHECK_SCRIPT"; then
    echo "Watchdog cron already installed"
    crontab -l 2>/dev/null | grep "$CHECK_SCRIPT"
    exit 0
fi

# Install
(crontab -l 2>/dev/null; echo "# monitor-ollama watchdog"; echo "$CRON_LINE") | crontab -
echo "Installed: $CRON_LINE"
echo "Logs: /tmp/ollama_watchdog.log"
