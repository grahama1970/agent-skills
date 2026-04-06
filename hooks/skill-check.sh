#!/usr/bin/env bash
# Pre-tool hook for Write|Edit: BLOCKING plan gate with semantic validation.
# Validates plan.json binds to the file being edited, has valid schema,
# and hasn't gone stale. Shows memory recall + skill recommendations.
#
# Session-aware: looks for .claude/plans/plan-{session_id}.json first,
# falls back to .claude/plan.json for backwards compatibility.
#
# Exit 0 = allow, Exit 2 = block.

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('tool_input',{}).get('file_path',''))" 2>/dev/null)
# Session isolation: each Claude Code instance passes a unique session_id via stdin
SESSION_ID=$(echo "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null)

[[ -z "$FILE_PATH" ]] && exit 0

# --- Skip non-code files ---
echo "$FILE_PATH" | grep -qE '\.(py|ts|tsx|js|jsx|sh|rs|go|c|cpp|java)$' || exit 0

# --- Skip temp files (tests, scratch, one-offs) ---
echo "$FILE_PATH" | grep -qE '^/tmp/|^/var/tmp/' && exit 0

# --- Skip hook files (can't gate the gate) ---
echo "$FILE_PATH" | grep -qE '\.claude/hooks/' && exit 0

# --- Locate project root ---
DIR=$(dirname "$(realpath "$FILE_PATH" 2>/dev/null || echo "$FILE_PATH")")
PROJECT_ROOT=""
while [[ "$DIR" != "/" ]]; do
    if [[ -d "$DIR/.git" || -d "$DIR/.pi" ]]; then
        PROJECT_ROOT="$DIR"
        break
    fi
    DIR=$(dirname "$DIR")
done
[[ -z "$PROJECT_ROOT" ]] && exit 0

# Session-aware plan files: each Claude Code session gets its own plan.
# Priority: 1) session_id from hook input, 2) PPID (Claude Code PID), 3) shared fallback
mkdir -p "$PROJECT_ROOT/.claude/plans" 2>/dev/null
if [[ -n "$SESSION_ID" && -f "$PROJECT_ROOT/.claude/plans/plan-${SESSION_ID}.json" ]]; then
    PLAN_FILE="$PROJECT_ROOT/.claude/plans/plan-${SESSION_ID}.json"
elif [[ -f "$PROJECT_ROOT/.claude/plans/plan-${PPID}.json" ]]; then
    PLAN_FILE="$PROJECT_ROOT/.claude/plans/plan-${PPID}.json"
elif [[ -f "$PROJECT_ROOT/.claude/plan.json" ]]; then
    PLAN_FILE="$PROJECT_ROOT/.claude/plan.json"
else
    PLAN_FILE="$PROJECT_ROOT/.claude/plans/plan-${PPID}.json"  # will trigger NO_PLAN path
fi
SKILLS_DIR="$PROJECT_ROOT/.pi/skills"
LOG_DIR="$PROJECT_ROOT/.claude/hook-logs"
mkdir -p "$LOG_DIR" 2>/dev/null

# --- No skills directory — remind only ---
if [[ ! -d "$SKILLS_DIR" ]]; then
    echo "REMINDER: Read existing code before writing new code."
    exit 0
fi

# --- Validate plan.json: exists + fresh + binds to this file ---
BASENAME=$(basename "$FILE_PATH" 2>/dev/null)
REL_PATH=$(realpath --relative-to="$PROJECT_ROOT" "$FILE_PATH" 2>/dev/null || echo "$BASENAME")

validate_plan() {
    python3 -c "
import json, sys, time, os

plan_file = '$PLAN_FILE'
rel_path = '$REL_PATH'
project_root = '$PROJECT_ROOT'
skills_dir = '$SKILLS_DIR'

try:
    plan = json.loads(open(plan_file).read())
except:
    print('NO_PLAN')
    sys.exit(0)

errors = []

# 1. Freshness: 30 min TTL
age = time.time() - os.path.getmtime(plan_file)
if age > 1800:
    errors.append(f'STALE: plan.json is {int(age/60)}min old (max 30min)')

# 2. Required fields
for field in ['task', 'memory_recalled', 'skills_considered', 'skills_code_read']:
    if field not in plan or not plan[field]:
        errors.append(f'MISSING: {field} is empty or missing')

# 3. skills_considered must be non-empty list
sc = plan.get('skills_considered', [])
if not isinstance(sc, list) or len(sc) == 0:
    errors.append('EMPTY: skills_considered must list at least 1 skill')

# 4. skills_code_read must reference real files
for code_ref in plan.get('skills_code_read', []):
    full = os.path.join(skills_dir, code_ref)
    if not os.path.exists(full):
        errors.append(f'NOT_FOUND: skills_code_read \"{code_ref}\" does not exist')

# 5. target_files binding: if declared, current file must be in list
targets = plan.get('target_files', [])
if targets:
    matched = any(rel_path == t or rel_path.endswith(t) or t.endswith(os.path.basename(rel_path)) for t in targets)
    if not matched:
        errors.append(f'UNBOUND: {rel_path} not in target_files {targets}')

if errors:
    print('INVALID')
    for e in errors:
        print(e)
else:
    print('VALID')
" 2>/dev/null
}

RESULT=$(validate_plan)
FIRST_LINE=$(echo "$RESULT" | head -1)

# --- Log decision ---
echo "{\"ts\":$(date +%s),\"file\":\"$REL_PATH\",\"result\":\"$FIRST_LINE\"}" >> "$LOG_DIR/plan-gate.jsonl" 2>/dev/null

# --- VALID plan → allow ---
if [[ "$FIRST_LINE" == "VALID" ]]; then
    exit 0
fi

# --- INVALID plan → show errors and block ---
if [[ "$FIRST_LINE" == "INVALID" ]]; then
    echo "" >&2
    echo "═══════════════════════════════════════════════════════════════" >&2
    echo "  PLAN GATE — plan.json INVALID for $BASENAME" >&2
    echo "═══════════════════════════════════════════════════════════════" >&2
    echo "$RESULT" | tail -n +2 | sed 's/^/  /' >&2
    echo "" >&2
    echo "  Fix: $(basename "$PLAN_FILE"), then retry." >&2
    echo "═══════════════════════════════════════════════════════════════" >&2
    exit 0
fi

# --- NO_PLAN → show full instructions + memory + recommendations ---
mkdir -p "$PROJECT_ROOT/.claude/plans" 2>/dev/null

if [[ -n "$SESSION_ID" ]]; then
    SUGGESTED_PLAN=".claude/plans/plan-${SESSION_ID}.json"
else
    SUGGESTED_PLAN=".claude/plan.json"
fi

cat >&2 << BLOCK

═══════════════════════════════════════════════════════════════
  PLAN GATE — No plan found. Cannot write code yet.
═══════════════════════════════════════════════════════════════

  Create ${SUGGESTED_PLAN}:

  {
    "task": "what you're doing",
    "target_files": ["path/to/file.py"],
    "memory_recalled": true,
    "skills_considered": ["skill1", "skill2"],
    "skills_selected": ["skill1"],
    "skills_code_read": ["skill1/main.py"],
    "bespoke_justification": ""
  }

  Steps:
  1. /memory recall for prior solutions
  2. Check .pi/skills/ for existing skills
  3. READ the skill's .py code (not just SKILL.md)
  4. Write plan file with target_files matching what you'll edit
  5. Then Write/Edit will be allowed

═══════════════════════════════════════════════════════════════

BLOCK

# --- Memory recall ---
MEMORY_RUN="$SKILLS_DIR/memory/run.sh"
if [[ -x "$MEMORY_RUN" ]]; then
    RECALL=$(unset VIRTUAL_ENV && timeout 5 bash "$MEMORY_RUN" recall --q "$BASENAME" --k 2 2>/dev/null | python3 -c "
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

# --- Skill chain recommendation ---
RECOMMEND_DIR="$SKILLS_DIR/recommend-skill-chain"
if [[ -d "$RECOMMEND_DIR" ]]; then
    RECOMMEND=$(cd "$RECOMMEND_DIR" && unset VIRTUAL_ENV && timeout 10 uv run --project . python -m src.cli recommend --task "$BASENAME" --json 2>/dev/null | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    for r in d.get('recommendations',[])[:3]:
        chain=r.get('chain','')
        conf=r.get('confidence',0)
        if conf > 0.3: print(f'  {chain} (confidence: {conf:.2f})')
except: pass
" 2>/dev/null)

    if [[ -n "$RECOMMEND" ]]; then
        echo "" >&2
        echo "Recommended skill chains:" >&2
        echo "$RECOMMEND" >&2
    fi
fi

exit 0
