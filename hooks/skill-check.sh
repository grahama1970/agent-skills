#!/usr/bin/env bash
# Pre-tool hook for Write|Edit: BLOCKING plan gate.
# Blocks the first write in a session until a plan file exists
# proving the agent considered existing skills and memory.
#
# Exit 0 = allow, Exit 2 = block with message.

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('tool_input',{}).get('file_path',''))" 2>/dev/null)

[[ -z "$FILE_PATH" ]] && exit 0

# --- Skip non-code files (configs, docs, yaml, json, md) ---
echo "$FILE_PATH" | grep -qE '\.(py|ts|tsx|js|jsx|sh|rs|go|c|cpp|java)$' || exit 0

# --- Locate project root (nearest .git or .pi) ---
DIR=$(dirname "$FILE_PATH")
PROJECT_ROOT=""
while [[ "$DIR" != "/" ]]; do
    if [[ -d "$DIR/.git" || -d "$DIR/.pi" ]]; then
        PROJECT_ROOT="$DIR"
        break
    fi
    DIR=$(dirname "$DIR")
done
[[ -z "$PROJECT_ROOT" ]] && exit 0

PLAN_FILE="$PROJECT_ROOT/.claude/plan.json"
SKILLS_DIR="$PROJECT_ROOT/.pi/skills"

# --- If plan.json exists and is recent (<2 hours), allow ---
if [[ -f "$PLAN_FILE" ]]; then
    AGE=$(( $(date +%s) - $(stat -c %Y "$PLAN_FILE" 2>/dev/null || echo 0) ))
    if [[ $AGE -lt 7200 ]]; then
        # Plan exists and is fresh — allow write
        exit 0
    fi
fi

# --- No plan or stale plan — BLOCK and require planning ---
# But first: check if .pi/skills exists (not all projects have skills)
if [[ ! -d "$SKILLS_DIR" ]]; then
    # No skills directory — just remind, don't block
    echo "REMINDER: Read existing code before writing new code."
    exit 0
fi

# --- BLOCK: require plan.json ---
cat >&2 << 'BLOCK'

═══════════════════════════════════════════════════════════════
  PLAN GATE — No plan.json found. Cannot write code yet.
═══════════════════════════════════════════════════════════════

  Before writing ANY code, create .claude/plan.json with:

  {
    "task": "what you're doing",
    "memory_recalled": true/false,
    "skills_considered": ["skill1", "skill2"],
    "skills_selected": ["skill1"],
    "skills_code_read": ["skill1/main.py"],
    "bespoke_justification": "why no existing skill covers this (or empty)"
  }

  Steps:
  1. Query /memory recall for prior solutions
  2. Check .pi/skills/ for existing skills that do this
  3. READ the skill's actual code (.py files), not just SKILL.md
  4. Write .claude/plan.json with your findings
  5. Then your Write/Edit will be allowed

═══════════════════════════════════════════════════════════════

BLOCK

# Also do a quick memory recall to help the agent
MEMORY_RUN="$SKILLS_DIR/memory/run.sh"
if [[ -x "$MEMORY_RUN" ]]; then
    BASENAME=$(basename "$FILE_PATH" 2>/dev/null)
    RECALL=$(unset VIRTUAL_ENV && bash "$MEMORY_RUN" recall --q "$BASENAME" --k 2 2>/dev/null | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    if d.get('found') and d.get('confidence',0) > 2.0 and d.get('items'):
        for item in d['items'][:2]:
            p=item.get('problem','')[:80]
            s=item.get('solution','')[:120]
            if p: print(f'  Prior: {p}')
            if s: print(f'  Solved: {s}')
except: pass
" 2>/dev/null)

    if [[ -n "$RECALL" ]]; then
        echo "" >&2
        echo "Memory recall for $BASENAME:" >&2
        echo "$RECALL" >&2
    fi
fi

exit 2
