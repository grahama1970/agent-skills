#!/usr/bin/env bash
# ollama_watchdog.sh — Check if Ollama can serve a request; restart if hung.
#
# Usage:
#   ./scripts/ollama_watchdog.sh          # one-shot check
#   WATCHDOG_DRY_RUN=1 ./scripts/ollama_watchdog.sh  # check without restart
#
# Install as cron (every 2 minutes):
#   (crontab -l 2>/dev/null; echo "*/2 * * * * /mnt/storage12tb/experiments/litellm/scripts/ollama_watchdog.sh >> /tmp/ollama_watchdog.log 2>&1") | crontab -
#
set -euo pipefail

OLLAMA_BASE="${OLLAMA_API_BASE:-http://127.0.0.1:11434}"
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5:0.5b}"
TIMEOUT="${OLLAMA_WATCHDOG_TIMEOUT:-8}"
DRY_RUN="${WATCHDOG_DRY_RUN:-0}"
LOG_PREFIX="[ollama-watchdog $(date -Iseconds)]"

# 1) Check Ollama process exists
if ! pgrep -x ollama >/dev/null 2>&1; then
    echo "$LOG_PREFIX WARN: ollama process not found"
    if [ "$DRY_RUN" = "1" ]; then
        echo "$LOG_PREFIX DRY_RUN: would start ollama"
        exit 1
    fi
    echo "$LOG_PREFIX Starting ollama..."
    nohup /bin/ollama serve </dev/null >/tmp/ollama_serve.log 2>&1 &
    sleep 3
fi

# 2) Probe /api/tags (fast, doesn't load model)
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "${OLLAMA_BASE}/api/tags" 2>/dev/null || echo "000")
if [ "$HTTP_CODE" != "200" ]; then
    echo "$LOG_PREFIX FAIL: /api/tags returned $HTTP_CODE"
    exit 1
fi

# 3) Probe chat (catches hung runner — the real failure mode)
RESP=$(curl -s --max-time "$TIMEOUT" -X POST "${OLLAMA_BASE}/api/chat" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"${OLLAMA_MODEL}\",\"messages\":[{\"role\":\"user\",\"content\":\"say ok\"}],\"stream\":false}" 2>&1) || RESP=""

if [ -z "$RESP" ]; then
    echo "$LOG_PREFIX FAIL: chat request timed out after ${TIMEOUT}s (runner likely hung)"
    if [ "$DRY_RUN" = "1" ]; then
        echo "$LOG_PREFIX DRY_RUN: would restart ollama"
        exit 1
    fi
    echo "$LOG_PREFIX Restarting ollama..."
    # Try systemd first, fall back to kill+start
    if systemctl restart ollama 2>/dev/null; then
        echo "$LOG_PREFIX Restarted via systemd"
    else
        # Kill all ollama processes (main + runners)
        pkill -9 -x ollama 2>/dev/null || true
        sleep 2
        nohup /bin/ollama serve </dev/null >/tmp/ollama_serve.log 2>&1 &
        echo "$LOG_PREFIX Restarted via kill+start"
    fi
    sleep 5
    # Verify recovery
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "${OLLAMA_BASE}/api/tags" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        echo "$LOG_PREFIX Recovery OK"
    else
        echo "$LOG_PREFIX Recovery FAILED — /api/tags returned $HTTP_CODE"
        exit 1
    fi
    exit 0
fi

echo "$LOG_PREFIX OK"
exit 0
