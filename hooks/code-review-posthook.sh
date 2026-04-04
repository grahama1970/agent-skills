#!/bin/bash
# Code Review Post-Hook
# Automatically triggers code-review using Copilot and GPT-5 after significant code changes
# Runs on Stop (before session ends)

set -e

# Configuration (store in env for code-review skill to read)
export CODE_REVIEW_PROVIDERS="copilot,openai"
export CODE_REVIEW_OPENAI_MODEL="gpt-5.2-codex"
export CODE_REVIEW_MAX_ITERATIONS=2
MIN_CHANGES_FOR_REVIEW=50

# Check if we have uncommitted changes worth reviewing
CHANGED_LINES=$(git diff --stat 2>/dev/null | tail -1 | grep -oE '[0-9]+ insertion|[0-9]+ deletion' | grep -oE '[0-9]+' | paste -sd+ | bc 2>/dev/null || echo "0")

if [ "$CHANGED_LINES" -lt "$MIN_CHANGES_FOR_REVIEW" ]; then
    # Not enough changes - skip silently
    exit 0
fi

# Get the list of changed code files
CHANGED_FILES=$(git diff --name-only 2>/dev/null | grep -E '\.(py|js|ts|tsx|go|rs|java|cpp|c|h|rb|php)$' | head -10)

if [ -z "$CHANGED_FILES" ]; then
    # No code files changed - skip silently
    exit 0
fi

# Create context file for the code-review skill
REVIEW_CONTEXT="/tmp/code_review_context_$$.json"
cat > "$REVIEW_CONTEXT" << EOF
{
  "trigger": "post-hook",
  "changed_lines": $CHANGED_LINES,
  "changed_files": $(echo "$CHANGED_FILES" | jq -R -s -c 'split("\n") | map(select(. != ""))'),
  "providers": ["copilot", "openai"],
  "openai_model": "gpt-5.2-codex",
  "max_iterations": 2,
  "review_focus": [
    "security_vulnerabilities",
    "error_handling",
    "performance",
    "code_clarity"
  ]
}
EOF

# Signal that code review should run
# The agent will see this message and invoke /code-review
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  CODE REVIEW RECOMMENDED"
echo "═══════════════════════════════════════════════════════════════"
echo "  Changed files: $(echo "$CHANGED_FILES" | wc -l)"
echo "  Changed lines: $CHANGED_LINES"
echo "  Providers: Copilot, GPT-5.2-codex"
echo "  Iterations: 2 rounds"
echo ""
echo "  Run: /code-review --providers copilot,openai --iterations 2"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Store context path for skill to read
echo "$REVIEW_CONTEXT" > /tmp/code_review_pending

exit 0
