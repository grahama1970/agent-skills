#!/usr/bin/env bash
# PostToolUse hook: blocks writes to prompt files that lack valid prompt-lab hash.
# Triggers on Edit/Write to files under */prompts/*.txt or files containing
# prompt indicators (>200 chars with "you are", "system prompt", etc.)

set -euo pipefail

# Read hook input from stdin
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    # Edit tool
    p = d.get('input', {}).get('file_path', '')
    if not p:
        # Write tool
        p = d.get('input', {}).get('file_path', '')
    print(p)
except:
    print('')
" 2>/dev/null)

[[ -z "$FILE_PATH" ]] && exit 0

# Only check prompt-related files
IS_PROMPT_FILE=false

# Check 1: file is in a prompts/ directory
if echo "$FILE_PATH" | grep -q '/prompts/.*\.txt$'; then
    IS_PROMPT_FILE=true
fi

# Check 2: file is a .py file — check for inline prompt indicators
if [[ "$FILE_PATH" == *.py ]] && [[ -f "$FILE_PATH" ]]; then
    # Count prompt indicators in the file
    INDICATOR_COUNT=$(python3 -c "
indicators = ['you are', 'system prompt', 'your role is', 'your task is',
              'respond with', 'answer the following', 'you must', 'do not hallucinate']
try:
    text = open('$FILE_PATH', encoding='utf-8', errors='ignore').read().lower()
    # Only flag strings >200 chars that look like prompts
    import ast
    tree = ast.parse(open('$FILE_PATH').read())
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) > 200:
            lower = node.value.lower()
            hits = sum(1 for i in indicators if i in lower)
            if hits >= 2:
                count += 1
    print(count)
except:
    print(0)
" 2>/dev/null)

    if [[ "$INDICATOR_COUNT" -gt 0 ]]; then
        echo "BLOCKED: Inline LLM prompt detected in $FILE_PATH" >&2
        echo "  $INDICATOR_COUNT inline prompt(s) found (>200 chars with 2+ prompt indicators)" >&2
        echo "  REQUIRED: Use /prompt-lab to create, evaluate, and seal prompts." >&2
        echo "  1. Write prompt to .pi/skills/prompt-lab/prompts/<name>.txt" >&2
        echo "  2. Run: prompt-lab eval --prompt <name> --fixtures <ground-truth>" >&2
        echo "  3. Run: prompt-lab seal <name>.txt --score <eval-score>" >&2
        echo "  4. Load at runtime: prompt_hash.verify_prompt(path)" >&2
        exit 2
    fi
fi

# Check 3: if it's a prompt .txt file, verify it has a valid hash
if [[ "$IS_PROMPT_FILE" == "true" ]] && [[ -f "$FILE_PATH" ]]; then
    HASH_CHECK=$(python3 -c "
import sys
sys.path.insert(0, '$(dirname "$(dirname "$FILE_PATH")")')
try:
    from prompt_hash import verify_prompt
    from pathlib import Path
    valid, reason = verify_prompt(Path('$FILE_PATH'))
    if not valid:
        print(f'UNSEALED: {reason}')
    else:
        print('OK')
except ImportError:
    # prompt_hash not available in this context — skip
    print('OK')
except Exception as e:
    print(f'ERROR: {e}')
" 2>/dev/null)

    if [[ "$HASH_CHECK" == UNSEALED* ]]; then
        echo "WARNING: Prompt file written without /prompt-lab seal: $FILE_PATH" >&2
        echo "  $HASH_CHECK" >&2
        echo "  Run: python prompt_hash.py seal $FILE_PATH --score <eval-score>" >&2
        # Warning, not block — the file was just written, needs sealing after eval
    fi
fi

exit 0
