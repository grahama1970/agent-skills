#!/bin/bash
# Continuous Operation Guard
# Prevents the agent from stopping when it has been given continuous work instructions.
#
# This hook runs on the Stop event. If it detects that the agent should be
# running continuously (e.g., /learn-datalake, monitor-* skills), it returns
# non-zero to block the stop and remind the agent to keep working.
#
# The hook checks for active supervisors and continuous tasks.

# Check if learn-datalake supervisor is running
# NOTE: This is advisory only — the supervisor runs independently of the agent.
# The agent CAN stop; the supervisor keeps running regardless.
if pgrep -f "supervise_learn_datalake" > /dev/null 2>&1; then
    cat >&2 << 'EOF'

ℹ️  /learn-datalake supervisor is running independently. It will continue after agent stops.

EOF
    # Allow stop — supervisor is independent
    exit 0
fi

# Check if any monitor-* tasks are explicitly active (via env var or state file)
MONITOR_ACTIVE_FILE="$HOME/.claude/state/continuous_monitors_active"
if [ -f "$MONITOR_ACTIVE_FILE" ]; then
    ACTIVE_MONITORS=$(cat "$MONITOR_ACTIVE_FILE" 2>/dev/null)
    if [ -n "$ACTIVE_MONITORS" ]; then
        cat >&2 << EOF

╭──────────────────────────────────────────────────────────────────────╮
│  ⛔ CONTINUOUS MONITORS ACTIVE — DO NOT STOP                         │
│                                                                      │
│  Active monitors: $ACTIVE_MONITORS
│                                                                      │
│  These monitors run continuously. Keep working.                      │
│  Only stop if genuinely blocked after exhausting /dogpile.           │
╰──────────────────────────────────────────────────────────────────────╯

EOF
        exit 1
    fi
fi

# No continuous tasks detected — allow stop
exit 0
