#!/bin/bash
# Task Complete Gate - Runs quality gate when todo tasks are marked completed
#
# Triggers on PostToolUse for TodoWrite
# Only runs quality gate if a task was marked "completed"

set -e

[[ "${QUALITY_GATE_DISABLED:-0}" == "1" ]] && exit 0

# Read hook input (contains tool_input with todos array)
INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd // "."' 2>/dev/null || echo ".")

# Check if any task was marked completed in this TodoWrite call
TOOL_INPUT=$(echo "$INPUT" | jq -r '.tool_input // empty' 2>/dev/null)
if [[ -z "$TOOL_INPUT" ]]; then
    exit 0
fi

# Check for completed status in the todos
HAS_COMPLETED=$(echo "$TOOL_INPUT" | jq -r '.todos[]? | select(.status == "completed")' 2>/dev/null)
if [[ -z "$HAS_COMPLETED" ]]; then
    # No completed tasks in this update - skip quality gate
    exit 0
fi

# A task was marked completed - run quality gate
echo "" >&2
echo "[Task Complete Gate] Task marked completed - running quality check..." >&2

# Delegate to main quality gate
echo "{\"cwd\": \"$CWD\"}" | /home/graham/.claude/hooks/quality-gate.sh
