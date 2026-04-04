#!/bin/bash
# no-bespoke-arango: Block Claude from writing bespoke ArangoDB scripts
#
# Fires on Edit/Write. Catches the pattern where Claude writes throwaway
# Python scripts that directly import ArangoClient instead of using
# existing daemon endpoints or skill run.sh commands.
#
# This is Claude's #1 regression: it forgets about the daemon/skills
# and writes raw AQL scripts to /tmp/ every single time.
#
# What's ALLOWED:
#   - Files inside embry-os/services/memory-daemon/ (the daemon itself)
#   - Files inside src/graph_memory/ (the library the daemon wraps)
#   - Files inside .agents/skills/memory/ or .claude/skills/memory/
#   - Test files for the daemon
#
# What's BLOCKED:
#   - Any other .py file that imports arango/ArangoClient directly
#   - Especially /tmp/*.py scripts (Claude's favorite bespoke hack location)

INPUT=$(cat)
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.filePath // empty' 2>/dev/null)

# Only check Python files
[[ "$FILE" != *.py ]] && exit 0
[[ ! -f "$FILE" ]] && exit 0

# Allow the daemon, graph_memory library, and memory skill themselves
case "$FILE" in
    */memory-daemon/*) exit 0 ;;
    */graph_memory/*) exit 0 ;;
    */skills/memory/*) exit 0 ;;
    */setup_schema*) exit 0 ;;
    */arango_client*) exit 0 ;;
    */sanity/arango_bulk_rename*) exit 0 ;;  # migration sanity: direct DB mechanics test
    */scripts/migrate_tactical_to_mind*) exit 0 ;;  # Wave 3 taxonomy migration: tactical_tags -> mind
esac

WARNINGS=""

# 1. Direct ArangoClient import
if grep -qE '^from arango import|^import arango|ArangoClient\(' "$FILE" 2>/dev/null; then
    MATCH=$(grep -nE '^from arango import|^import arango|ArangoClient\(' "$FILE" | head -5)
    WARNINGS+="HARD BLOCK: Direct ArangoDB client usage in bespoke script.\n"
    WARNINGS+="$MATCH\n\n"
    WARNINGS+="USE THE EXISTING INFRASTRUCTURE:\n"
    WARNINGS+="  - Daemon /recall endpoint: httpx.HTTPTransport(uds='/run/user/1000/embry/memory.sock')\n"
    WARNINGS+="  - Daemon /taxonomy/batch-tag: for taxonomy tagging\n"
    WARNINGS+="  - Daemon /store, /learn: for ingestion\n"
    WARNINGS+="  - /embedding skill: for embedding backfill\n"
    WARNINGS+="  - /ops-arango skill: for admin operations\n"
    WARNINGS+="  - setup_schema.py: for index/view creation\n\n"
    WARNINGS+="NEVER write throwaway /tmp/*.py scripts with raw AQL.\n"
    WARNINGS+="The daemon + skills already have BM25, semantic search, multihop traversal,\n"
    WARNINGS+="taxonomy tagging, and embedding — all tested and production-ready.\n"
fi

# 2. Raw AQL execution outside allowed locations
if grep -qE 'db\.aql\.execute|\.execute\(.*FOR doc IN' "$FILE" 2>/dev/null; then
    if ! grep -qE 'ArangoClient' "$FILE" 2>/dev/null; then
        # Only warn if it's not already caught by rule 1
        :
    else
        MATCH=$(grep -nE 'db\.aql\.execute' "$FILE" | head -3)
        WARNINGS+="Raw AQL execution detected. Use daemon endpoints instead.\n"
        WARNINGS+="$MATCH\n"
    fi
fi

# 3. Hardcoded ArangoDB passwords
if grep -qE 'password.*openSesame|openSesame' "$FILE" 2>/dev/null; then
    MATCH=$(grep -nE 'openSesame' "$FILE" | head -3)
    WARNINGS+="Hardcoded ArangoDB password detected.\n"
    WARNINGS+="$MATCH\n"
    WARNINGS+="Use the daemon (Unix socket, no auth needed) or env vars.\n"
fi

if [[ -n "$WARNINGS" ]]; then
    cat >&2 <<EOF

==== NO-BESPOKE-ARANGO HOOK ====
File: $FILE

$WARNINGS
REMEMBER: You have these endpoints on the daemon socket:
  /recall, /learn, /store, /clarify, /intent
  /taxonomy/coverage, /taxonomy/batch-tag, /taxonomy/sample
  /db/audit, /analytics/run, /drift
  /tom/{user_id}

And these skills:
  /embedding backfill, /ops-arango, /monitor-taxonomy
  /memory recall, /memory learn

Stop writing bespoke scripts. Use what exists.
================================

EOF
    exit 2
fi

exit 0
