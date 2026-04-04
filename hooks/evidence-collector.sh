#!/bin/bash
set -euo pipefail
# Evidence Collector - Logs every file modification for verification
#
# Fires on: PostToolUse (Edit|Write)
# Purpose: Ground truth of what was actually modified, not what Claude claims
# Output: Appends to ~/.claude/state/evidence_{session_id}.jsonl
#
# This hook is the foundation of the verification system.
# The verification-gate agent reads this file to cross-check claims.

INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // "unknown"' 2>/dev/null)
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.filePath // empty' 2>/dev/null)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)
CWD=$(echo "$INPUT" | jq -r '.cwd // "."' 2>/dev/null)

[[ -z "$FILE" ]] && exit 0

STATE_DIR="$HOME/.claude/state"
mkdir -p "$STATE_DIR"

# Compute file metadata
LINE_COUNT=0
[[ -f "$FILE" ]] && LINE_COUNT=$(wc -l < "$FILE" 2>/dev/null || echo 0)

# Detect file type for downstream verification
FILE_TYPE="other"
case "$FILE" in
    *.py) FILE_TYPE="python" ;;
    *.rs) FILE_TYPE="rust" ;;
    *.ts|*.tsx|*.js|*.jsx) FILE_TYPE="javascript" ;;
    *.qml) FILE_TYPE="qml" ;;
    *.md) FILE_TYPE="markdown" ;;
    *.sh) FILE_TYPE="shell" ;;
    *.toml|*.json|*.yaml|*.yml) FILE_TYPE="config" ;;
esac

# Detect if under .pi/skills/
IN_SKILLS="false"
echo "$FILE" | grep -q '\.pi/skills/' && IN_SKILLS="true"

# Append evidence (one JSON line per modification)
TS=$(date +%s)
jq -n -c \
    --arg file "$FILE" \
    --arg tool "$TOOL" \
    --arg type "$FILE_TYPE" \
    --argjson ts "$TS" \
    --argjson lines "$LINE_COUNT" \
    --arg skills "$IN_SKILLS" \
    --arg cwd "$CWD" \
    '{file: $file, tool: $tool, type: $type, ts: $ts, lines: $lines, in_skills: ($skills == "true"), cwd: $cwd}' \
    >> "$STATE_DIR/evidence_${SESSION_ID}.jsonl"

exit 0
