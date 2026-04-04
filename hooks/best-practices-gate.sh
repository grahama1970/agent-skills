#!/bin/bash
set -euo pipefail
# Best Practices Gate - Forces consultation of relevant best-practices skills
#
# Fires on: PostToolUse (Edit|Write)
# Purpose: After a file is modified, remind Claude which best-practices apply
#
# Exit 2 on PostToolUse = stderr shown to Claude (tool already ran, can't undo).
# ONLY exit 2 for actual VIOLATIONS. Reminders use exit 0 with stderr.
# This prevents alert fatigue from benign edits.

INPUT=$(cat)
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.filePath // empty' 2>/dev/null)

[[ -z "$FILE" ]] && exit 0
[[ ! -f "$FILE" ]] && exit 0

VIOLATIONS=""
REMINDERS=""

# ─────────────────────────────────────────────────────────────
# Map file type → required best-practices skill
# ─────────────────────────────────────────────────────────────

case "$FILE" in
    *.py)
        REMINDERS+="BEST PRACTICE: /best-practices-python applies to this file.\n"

        # Check for ArangoDB patterns in the file content
        if grep -qE 'arango|aql|ArangoClient|COSINE_SIMILARITY|BM25|TOKENS|lesson_edges|get_db|hybrid_search' "$FILE" 2>/dev/null; then
            REMINDERS+="BEST PRACTICE: /best-practices-arangodb — this file uses ArangoDB patterns.\n"
        fi

        # Check for imports that violate conventions — these are VIOLATIONS
        if grep -qE '^import logging$|^from logging import' "$FILE" 2>/dev/null; then
            VIOLATIONS+="VIOLATION: Use 'from loguru import logger', NOT 'import logging'. See /best-practices-python.\n"
        fi
        if grep -qE '^import requests$|^from requests import' "$FILE" 2>/dev/null; then
            VIOLATIONS+="VIOLATION: Use 'httpx', NOT 'import requests'. See /best-practices-python.\n"
        fi
        if grep -qE '^import argparse$|^from argparse import' "$FILE" 2>/dev/null; then
            VIOLATIONS+="VIOLATION: Use 'typer', NOT 'argparse'. See /best-practices-python.\n"
        fi
        # Block bespoke AQL in Python — use daemon endpoints via httpx instead
        # EXEMPT: daemon internals (graph_memory/) — these ARE the endpoint implementations
        if ! echo "$FILE" | grep -qE 'src/graph_memory/'; then
            if grep -qE 'FOR\s+\w+\s+IN\s+@@?\w+|db\.aql\.execute|AQL_QUERY|aql\.execute' "$FILE" 2>/dev/null; then
                MATCH=$(grep -nE 'FOR\s+\w+\s+IN\s+@@?\w+|db\.aql\.execute|AQL_QUERY|aql\.execute' "$FILE" | head -3)
                VIOLATIONS+="VIOLATION: Bespoke AQL detected. Use daemon httpx endpoints (/recall, /list, /recall/by-keys), NOT raw AQL.\n$MATCH\n"
            fi
            # Block curl to memory service — use httpx Unix socket
            if grep -qE 'curl.*localhost:(8601|4002)|curl.*/recall|curl.*/learn|curl.*/list' "$FILE" 2>/dev/null; then
                VIOLATIONS+="VIOLATION: Use httpx with Unix socket, NOT curl to memory service. See MEMORY.md.\n"
            fi
        fi
        ;;

    *.rs)
        REMINDERS+="BEST PRACTICE: /best-practices-rust applies to this file.\n"
        ;;

    *.tsx|*.jsx)
        REMINDERS+="BEST PRACTICE: /best-practices-react applies to this file.\n"
        ;;

    *.qml)
        REMINDERS+="BEST PRACTICE: /best-practices-kde applies to this file.\n"
        ;;
esac

# Only match SKILL.md/run.sh/sanity.sh under .pi/skills/ (not ANY run.sh)
if echo "$FILE" | grep -qE '\.pi/skills/[^/]+/(SKILL\.md|run\.sh|sanity\.sh)$'; then
    REMINDERS+="BEST PRACTICE: /best-practices-skills applies to this file.\n"
fi

# ─────────────────────────────────────────────────────────────
# Skills directory checks
# ─────────────────────────────────────────────────────────────

if echo "$FILE" | grep -q '\.pi/skills/'; then
    REMINDERS+="SKILLS GATE: This file is under .pi/skills/. /skills-ci scan is MANDATORY before and after changes.\n"
fi

# ─────────────────────────────────────────────────────────────
# File size check (800 line max for Python)
# ─────────────────────────────────────────────────────────────

if [[ "$FILE" == *.py ]]; then
    LINECOUNT=$(wc -l < "$FILE" 2>/dev/null || echo 0)
    if [[ $LINECOUNT -gt 800 ]]; then
        VIOLATIONS+="SIZE VIOLATION: $FILE is $LINECOUNT lines (max 800). Split into focused modules.\n"
    fi
fi

# ─────────────────────────────────────────────────────────────
# Output: VIOLATIONS = exit 2 (hard block), REMINDERS = exit 0 (advisory)
# ─────────────────────────────────────────────────────────────

if [[ -n "$VIOLATIONS" ]]; then
    cat >&2 <<EOF

═══════════════════════════════════════════════════════════════
  BEST PRACTICES GATE — VIOLATIONS FOUND
═══════════════════════════════════════════════════════════════
  File: $FILE

$(echo -e "$VIOLATIONS")
$(if [[ -n "$REMINDERS" ]]; then echo -e "$REMINDERS"; fi)
  Fix violations before proceeding. The verification gate WILL
  check compliance at session end.
═══════════════════════════════════════════════════════════════

EOF
    exit 2
fi

# Reminders only — no violations. Show on stderr but exit 0 (no block, no fatigue)
if [[ -n "$REMINDERS" ]]; then
    cat >&2 <<EOF
  [best-practices-gate] $FILE — $(echo -e "$REMINDERS" | head -1)
EOF
fi

exit 0
