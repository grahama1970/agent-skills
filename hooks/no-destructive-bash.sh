#!/usr/bin/env bash
# PreToolUse hook: Block destructive Bash commands.
# Fires on every Bash tool call BEFORE execution.
# Exit 2 = hard block (command will not run).
# Exit 0 = allow.

set -uo pipefail

# The command is passed via $TOOL_INPUT as JSON with a "command" field.
# Use python3 to parse; if parsing fails, allow the command (don't block on hook bugs).
CMD=$(echo "$TOOL_INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('command',''))" 2>/dev/null)
if [ $? -ne 0 ] || [ -z "$CMD" ]; then
    # Could not parse TOOL_INPUT — allow rather than silently block
    exit 0
fi

# --- Destructive git commands ---

# git mv on directories (the exact thing that caused data loss)
if echo "$CMD" | grep -qE 'git\s+mv\s+.*/$'; then
    echo "BLOCKED: git mv on a directory. Check for untracked files first: git status --short"
    exit 2
fi
if echo "$CMD" | grep -qE 'git\s+mv\s+\S+\s+\S+' && echo "$CMD" | grep -qvE 'git\s+mv\s+\S+\.\S+\s'; then
    # git mv source dest where source doesn't have a file extension (likely a directory)
    # Allow single file renames (they have extensions)
    echo "BLOCKED: git mv may affect a directory. Verify no untracked files first: git status --short"
    exit 2
fi

# git reset --hard
if echo "$CMD" | grep -qE 'git\s+reset\s+--hard'; then
    echo "BLOCKED: git reset --hard destroys uncommitted work. Commit first or use git stash."
    exit 2
fi

# git clean -f (deletes untracked files)
if echo "$CMD" | grep -qE 'git\s+clean\s+-[a-zA-Z]*f'; then
    echo "BLOCKED: git clean -f deletes untracked files permanently."
    exit 2
fi

# git checkout . or git checkout -- . (discards all changes)
if echo "$CMD" | grep -qE 'git\s+checkout\s+(--\s+)?\.'; then
    echo "BLOCKED: git checkout . discards all uncommitted changes."
    exit 2
fi

# git push --force (or -f) to main/master
if echo "$CMD" | grep -qE 'git\s+push\s+.*--force|git\s+push\s+-f'; then
    echo "BLOCKED: git push --force can destroy remote history. Use --force-with-lease if necessary."
    exit 2
fi

# git branch -D (force delete branch)
if echo "$CMD" | grep -qE 'git\s+branch\s+-D'; then
    echo "BLOCKED: git branch -D force-deletes a branch. Use -d for safe delete."
    exit 2
fi

# --- Filesystem destruction ---

# rm -rf on directories (not single files)
if echo "$CMD" | grep -qE 'rm\s+-[a-zA-Z]*r[a-zA-Z]*f|rm\s+-[a-zA-Z]*f[a-zA-Z]*r'; then
    echo "BLOCKED: rm -rf is destructive. Use trash-put or move to /tmp/ instead."
    exit 2
fi

# rm on directories
if echo "$CMD" | grep -qE 'rm\s+-r\s'; then
    echo "BLOCKED: rm -r on directories. Use trash-put or move to /tmp/ instead."
    exit 2
fi

# rmdir on project paths
if echo "$CMD" | grep -qE 'rmdir\s+.*(workspace|experiments|src|pipeline)'; then
    echo "BLOCKED: rmdir on project directory. Move to /tmp/ instead."
    exit 2
fi

# --- Allow everything else ---
exit 0
