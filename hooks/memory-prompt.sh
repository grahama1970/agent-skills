#!/bin/bash
# Memory First - UserPromptSubmit Hook
# Queries memory when user submits a prompt to provide context BEFORE agent starts
#
# Input: JSON via stdin with user_prompt
# Output: Context to stderr (agent sees this), JSON decision to stdout
#
# This is THE key hook for Memory First - it runs before any agent work begins

set -e

# Check if hook is enabled (default: enabled)
if [[ "${MEMORY_HOOK_ENABLED:-1}" == "0" ]]; then
    exit 0
fi

# Read JSON input from stdin
INPUT=$(cat)

# Extract user prompt using jq (or fallback)
if command -v jq &> /dev/null; then
    PROMPT=$(echo "$INPUT" | jq -r '.user_prompt // empty')
    CWD=$(echo "$INPUT" | jq -r '.cwd // empty')
else
    PROMPT=$(echo "$INPUT" | grep -o '"user_prompt"[[:space:]]*:[[:space:]]*"[^"]*"' | cut -d'"' -f4)
    CWD=$(echo "$INPUT" | grep -o '"cwd"[[:space:]]*:[[:space:]]*"[^"]*"' | cut -d'"' -f4)
fi

# Skip if prompt is too short or looks like a simple command
if [[ -z "$PROMPT" ]] || [[ ${#PROMPT} -lt 15 ]]; then
    exit 0
fi

# Skip for certain patterns (greetings, simple commands)
LOWER_PROMPT=$(echo "$PROMPT" | tr '[:upper:]' '[:lower:]')
case "$LOWER_PROMPT" in
    hi|hello|hey|thanks|"thank you"|ok|okay|yes|no|y|n)
        exit 0
        ;;
esac

# Determine scope
SCOPE="${MEMORY_SCOPE:-$(basename "${CWD:-$(pwd)}")}"

# Find the memory skill
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEMORY_SKILL="$SCRIPT_DIR/../../.agents/skills/memory/run.sh"

if [[ ! -x "$MEMORY_SKILL" ]]; then
    if [[ -n "$CWD" ]] && [[ -x "$CWD/.agents/skills/memory/run.sh" ]]; then
        MEMORY_SKILL="$CWD/.agents/skills/memory/run.sh"
    else
        exit 0
    fi
fi

# Query memory with the user's prompt
RESULT=$(timeout 8s "$MEMORY_SKILL" recall --q "$PROMPT" --scope "$SCOPE" --k 5 2>/dev/null) || exit 0

# Check if we got useful results
FOUND=$(echo "$RESULT" | grep -o '"found"[[:space:]]*:[[:space:]]*true' || true)
CONFIDENCE=$(echo "$RESULT" | grep -o '"confidence"[[:space:]]*:[[:space:]]*[0-9.]*' | grep -o '[0-9.]*' || echo "0")

if [[ -n "$FOUND" ]]; then
    # Found relevant context - output it for the agent
    echo "" >&2
    echo "========================================" >&2
    echo "MEMORY CONTEXT (recall before scanning)" >&2
    echo "========================================" >&2
    echo "" >&2

    # Extract and display items
    if command -v jq &> /dev/null; then
        echo "$RESULT" | jq -r '.items[:3][] | "## \(.title // "Lesson")\nProblem: \(.problem // "N/A")\nSolution: \(.solution // .playbook // "N/A")\n"' 2>/dev/null >&2 || echo "$RESULT" | head -40 >&2
    else
        echo "$RESULT" | head -40 >&2
    fi

    echo "" >&2
    echo "Confidence: $CONFIDENCE" >&2
    echo "If these match your task, apply the solution." >&2
    echo "If not, proceed with codebase scan and 'learn' after solving." >&2
    echo "========================================" >&2
    echo "" >&2
fi

# Always allow - we're just providing context
exit 0
