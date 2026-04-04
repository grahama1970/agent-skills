#!/bin/bash
set -euo pipefail
# Session Context - Injects dynamic context at session start
#
# Fires on: SessionStart
# Purpose: Provide situational awareness and clean up old evidence files
#
# Returns additionalContext with:
#   - Current skill count
#   - Active system services
#   - Disk usage warnings

CWD=$(cat | jq -r '.cwd // "."' 2>/dev/null)

CONTEXT=""

# ─────────────────────────────────────────────────────────────
# Skill count (if in pi-mono or skills are accessible)
# ─────────────────────────────────────────────────────────────

SKILLS_DIR="$HOME/workspace/experiments/pi-mono/.pi/skills"
if [[ -d "$SKILLS_DIR" ]]; then
    # Use -maxdepth without -L to avoid symlink loops (skills-broadcast lesson)
    SKILL_COUNT=$(find "$SKILLS_DIR" -maxdepth 2 -name "SKILL.md" 2>/dev/null | wc -l || true)
    CONTEXT+="Skills: $SKILL_COUNT available in canonical dir.\n"
fi

# ─────────────────────────────────────────────────────────────
# NVMe disk usage warning
# ─────────────────────────────────────────────────────────────

DISK_PCT=$(df / 2>/dev/null | awk 'NR==2 {gsub(/%/,""); print $5}')
if [[ -n "$DISK_PCT" ]] && [[ "$DISK_PCT" -gt 80 ]]; then
    CONTEXT+="WARNING: NVMe at ${DISK_PCT}% — heavy artifacts go on /mnt/storage12tb.\n"
fi

# ─────────────────────────────────────────────────────────────
# Active services
# ─────────────────────────────────────────────────────────────

ACTIVE_SERVICES=""
systemctl --user is-active embry-agent.service &>/dev/null && ACTIVE_SERVICES+="embry-agent "
systemctl --user is-active embry-memory.service &>/dev/null && ACTIVE_SERVICES+="embry-memory "
systemctl --user is-active embry-scillm.service &>/dev/null && ACTIVE_SERVICES+="embry-scillm "
systemctl --user is-active embry-scheduler.service &>/dev/null && ACTIVE_SERVICES+="scheduler "
if [[ -n "$ACTIVE_SERVICES" ]]; then
    CONTEXT+="Active services: $ACTIVE_SERVICES\n"
fi

# ─────────────────────────────────────────────────────────────
# Clean up old evidence files (>7 days)
# ─────────────────────────────────────────────────────────────

STATE_DIR="$HOME/.claude/state"
if [[ -d "$STATE_DIR" ]] && [[ "$STATE_DIR" == "$HOME/.claude/state" ]]; then
    # Guard: only delete evidence files, not arbitrary paths
    find "$STATE_DIR" -maxdepth 1 -name "evidence_*.jsonl" -mtime +7 -delete 2>/dev/null || true
fi

# ─────────────────────────────────────────────────────────────
# Output
# ─────────────────────────────────────────────────────────────

if [[ -n "$CONTEXT" ]]; then
    jq -n --arg ctx "$(echo -e "$CONTEXT")" '{
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": $ctx
        }
    }'
else
    exit 0
fi
