#!/bin/bash
# Memory First Pre-Hook for Claude Code
# Queries memory before codebase operations to provide context
#
# Input: JSON via stdin with tool_name and tool_input
# Output: JSON decision or exit code
#
# Environment:
#   MEMORY_SCOPE - Project scope (default: from cwd in input)
#   MEMORY_HOOK_ENABLED - Set to "0" to disable (default: "1")

set -e

# Check if hook is enabled
if [[ "${MEMORY_HOOK_ENABLED:-0}" == "0" ]]; then
    # Output allow decision
    echo '{"decision": "allow"}'
    exit 0
fi

# Read JSON input from stdin
INPUT=$(cat)

# Extract tool name and input using jq (or fallback to grep)
if command -v jq &> /dev/null; then
    TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
    TOOL_INPUT=$(echo "$INPUT" | jq -r '.tool_input | tostring // empty')
    CWD=$(echo "$INPUT" | jq -r '.cwd // empty')
else
    # Fallback: basic extraction
    TOOL_NAME=$(echo "$INPUT" | grep -o '"tool_name"[[:space:]]*:[[:space:]]*"[^"]*"' | cut -d'"' -f4)
    CWD=$(echo "$INPUT" | grep -o '"cwd"[[:space:]]*:[[:space:]]*"[^"]*"' | cut -d'"' -f4)
    TOOL_INPUT="$INPUT"
fi

# Only trigger for exploration tools, not simple file reads
case "$TOOL_NAME" in
    Grep|Task)
        # These are good candidates for memory context
        ;;
    Read|Glob)
        # Skip - these are usually direct file access, not problem-solving
        echo '{"decision": "allow"}'
        exit 0
        ;;
    *)
        echo '{"decision": "allow"}'
        exit 0
        ;;
esac

# Extract search query from tool input
QUERY=""
if command -v jq &> /dev/null; then
    # Try to get pattern from Grep or prompt from Task
    QUERY=$(echo "$INPUT" | jq -r '.tool_input.pattern // .tool_input.prompt // empty' 2>/dev/null)
fi

# Skip if no query or query is too short
if [[ -z "$QUERY" ]] || [[ ${#QUERY} -lt 10 ]]; then
    echo '{"decision": "allow"}'
    exit 0
fi

# Determine scope
SCOPE="${MEMORY_SCOPE:-$(basename "${CWD:-$(pwd)}")}"

# Find the memory skill
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEMORY_SKILL="$SCRIPT_DIR/../../.agents/skills/memory/run.sh"

if [[ ! -x "$MEMORY_SKILL" ]]; then
    # Try project root
    if [[ -n "$CWD" ]] && [[ -x "$CWD/.agents/skills/memory/run.sh" ]]; then
        MEMORY_SKILL="$CWD/.agents/skills/memory/run.sh"
    else
        echo '{"decision": "allow"}'
        exit 0
    fi
fi

# Query memory (with timeout to avoid blocking)
RESULT=$(timeout 5s "$MEMORY_SKILL" recall --q "$QUERY" --scope "$SCOPE" --k 3 2>/dev/null) || {
    echo '{"decision": "allow"}'
    exit 0
}

# Check if we got useful results
FOUND=$(echo "$RESULT" | grep -o '"found"[[:space:]]*:[[:space:]]*true' || true)

if [[ -n "$FOUND" ]]; then
    # Found relevant context - output it as a message
    # The agent will see this and can use the context
    echo "MEMORY CONTEXT: Found relevant lessons for query '$QUERY'" >&2
    echo "$RESULT" | head -30 >&2
fi

# Always allow the tool call, we're just providing context
echo '{"decision": "allow"}'
exit 0
