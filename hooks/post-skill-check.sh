#!/usr/bin/env bash
# Post-tool hook for Write|Edit: verify the agent didn't write bespoke code
# that duplicates an existing skill or violates known conventions.
# Also runs /recommend-skill-chain to surface what skills should be used.

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('tool_input',{}).get('file_path',''))" 2>/dev/null)

[[ -z "$FILE_PATH" ]] && exit 0
[[ -f "$FILE_PATH" ]] || exit 0

# Only check code files
echo "$FILE_PATH" | grep -qE '\.(py|ts|tsx|js|jsx|sh)$' || exit 0

# Locate project root
DIR=$(dirname "$FILE_PATH")
PROJECT_ROOT=""
while [[ "$DIR" != "/" ]]; do
    if [[ -d "$DIR/.git" || -d "$DIR/.pi" ]]; then
        PROJECT_ROOT="$DIR"
        break
    fi
    DIR=$(dirname "$DIR")
done

SKILLS_DIR="$PROJECT_ROOT/.pi/skills"
WARNINGS=""

# 1. Subprocess wrapping a skill's run.sh
if grep -q "subprocess.*run\.sh" "$FILE_PATH" 2>/dev/null; then
    SKILL=$(grep -oP 'skills/\K[^/]+(?=/run\.sh)' "$FILE_PATH" 2>/dev/null | head -1)
    [[ -n "$SKILL" ]] && WARNINGS+="BESPOKE: Calls /$SKILL via subprocess. Use the skill directly.\n"
fi

# 2. Direct ArangoDB access
if grep -qE 'memory\.sock|arangodb|arango_client|8529' "$FILE_PATH" 2>/dev/null; then
    WARNINGS+="BESPOKE: Direct ArangoDB access. Use /memory run.sh recall/learn.\n"
fi

# 3. Hand-written LLM prompts
if grep -qE '(f""".*You are|f"You are a|prompt\s*=\s*f"|system_prompt\s*=\s*f")' "$FILE_PATH" 2>/dev/null; then
    WARNINGS+="BESPOKE: Hand-written LLM prompt. Use /prompt-lab template.\n"
fi

# 4. Direct httpx to scillm (exempt: tool_use.py, code_runner.py, review_prompt.py)
if grep -qE 'httpx\.post.*localhost:4001|httpx\.post.*SCILLM' "$FILE_PATH" 2>/dev/null; then
    BASENAME=$(basename "$FILE_PATH")
    if [[ "$BASENAME" != "tool_use.py" && "$BASENAME" != "code_runner.py" && "$BASENAME" != "review_prompt.py" ]]; then
        WARNINGS+="BESPOKE: Direct httpx to scillm. Use /scillm skill.\n"
    fi
fi

# 5-7. Python conventions
grep -qE '^import logging|^from logging import' "$FILE_PATH" 2>/dev/null && WARNINGS+="CONVENTION: Use loguru, not logging.\n"
grep -qE '^import requests|^from requests import' "$FILE_PATH" 2>/dev/null && WARNINGS+="CONVENTION: Use httpx, not requests.\n"
grep -qE '^import argparse|^import click|^from click import' "$FILE_PATH" 2>/dev/null && WARNINGS+="CONVENTION: Use typer, not argparse/click.\n"

# 8. Banned patterns
grep -qE 'claude\s+-p|codex\s+exec' "$FILE_PATH" 2>/dev/null && WARNINGS+="BANNED: claude -p / codex exec. Use /scillm or /code-runner.\n"

# 9-10. Code quality
grep -qE "re\.(search|match|findall).*import\s" "$FILE_PATH" 2>/dev/null && WARNINGS+="CONVENTION: Regex import detection. Use ast module.\n"
grep -qE '\beval\s*\(' "$FILE_PATH" 2>/dev/null && WARNINGS+="SECURITY: eval() detected. Use safe alternatives.\n"

# 11-12. Skill reimplementation
BASENAME=$(basename "$FILE_PATH")
if [[ "$BASENAME" != "tool_use.py" ]]; then
    grep -qE 'def.*repo.?map|def.*symbol.*extract|def.*parse.*symbols' "$FILE_PATH" 2>/dev/null && WARNINGS+="BESPOKE: Symbol extraction. Use /treesitter.\n"
fi
grep -qE 'sentence.transformers|SentenceTransformer|faiss\.' "$FILE_PATH" 2>/dev/null && WARNINGS+="BESPOKE: Embedding/vector code. Use /embedding skill.\n"

# --- Output warnings ---
if [[ -n "$WARNINGS" ]]; then
    echo ""
    echo "=== POST-EDIT WARNINGS for $BASENAME ==="
    echo -e "$WARNINGS"
fi

# --- Recommend skill chain (non-blocking, concise) ---
if [[ -d "$SKILLS_DIR/recommend-skill-chain" ]]; then
    # Extract a task description from the file's docstring or first comment
    TASK_HINT=$(head -5 "$FILE_PATH" | grep -oP '(?<=""")(.*?)(?=""")' 2>/dev/null | head -1)
    [[ -z "$TASK_HINT" ]] && TASK_HINT=$(head -3 "$FILE_PATH" | grep -oP '(?<=# )(.*)' 2>/dev/null | head -1)
    [[ -z "$TASK_HINT" ]] && TASK_HINT="$BASENAME"

    RECOMMEND=$(cd "$SKILLS_DIR/recommend-skill-chain" && unset VIRTUAL_ENV && timeout 10 uv run --project . python -m src.cli recommend --task "$TASK_HINT" --json 2>/dev/null | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    recs=d.get('recommendations',[])[:2]
    for r in recs:
        chain=r.get('chain','')
        conf=r.get('confidence',0)
        if conf > 0.3:
            print(f'  {chain} (confidence: {conf:.2f})')
except: pass
" 2>/dev/null)

    if [[ -n "$RECOMMEND" ]]; then
        echo ""
        echo "Recommended skill chains for this task:"
        echo "$RECOMMEND"
    fi
fi

exit 0
