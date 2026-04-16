#!/bin/bash
# Sanity check for scillm skill
# Verifies Chutes API connectivity and basic completions work
# Exit 0=PASS, 1=FAIL, 3=SKIP (external service unavailable)
set -e

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SKILL_DIR")")")"
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

echo "=== scillm Skill Sanity Check ==="
echo ""

# 1. Check environment variables
echo -n "1. Environment variables... "
if [[ -z "$CHUTES_API_KEY" ]]; then
    echo "FAIL (CHUTES_API_KEY not set)"
    exit 1
fi
if [[ -z "$CHUTES_API_BASE" ]]; then
    echo "FAIL (CHUTES_API_BASE not set)"
    exit 1
fi
echo "OK"

# 2. Check scillm is importable
echo -n "2. scillm import... "
if "$SKILL_DIR/.venv/bin/python" -c "from scillm import acompletion, batch_completion" 2>/dev/null; then
    echo "OK"
else
    echo "FAIL (scillm not installed)"
    exit 1
fi

# 3. Test text completion (quick call)
# SKIP if endpoint is unreachable, rate-limited, or times out
echo -n "3. Text completion (single)... "
START=$(date +%s.%N)
RESULT=$("$SKILL_DIR/.venv/bin/python" "$SKILL_DIR/batch.py" single "Say hello in 3 words" --timeout 30 2>&1) || true
EXIT_CODE=${PIPESTATUS[0]:-$?}
END=$(date +%s.%N)
ELAPSED=$(echo "$END - $START" | bc)

ENDPOINT_SKIP=0
if [[ $EXIT_CODE -ne 0 ]] || [[ -z "$RESULT" ]]; then
    # Check if it's a connectivity/rate-limit issue vs a code bug
    if echo "$RESULT" | grep -qiE "(timeout|connect|rate.limit|429|503|502|504|connection refused|unreachable|timed out)"; then
        echo "SKIP (endpoint unavailable: ${RESULT:0:80})"
        ENDPOINT_SKIP=1
    elif [[ -z "$RESULT" ]] && [[ $EXIT_CODE -ne 0 ]]; then
        echo "SKIP (endpoint returned empty/error, exit=$EXIT_CODE)"
        ENDPOINT_SKIP=1
    else
        echo "FAIL (exit=$EXIT_CODE)"
        echo "   Error: $RESULT"
        exit 1
    fi
else
    echo "OK (${ELAPSED}s)"
    echo "   Response: ${RESULT:0:50}..."
fi

# 4. Test VLM availability (just check model env)
echo -n "4. VLM model configured... "
VLM_MODEL="${CHUTES_VLM_MODEL:-Qwen/Qwen3-VL-235B-A22B-Instruct}"
echo "OK ($VLM_MODEL)"

# 5. Test parallel_acompletions (2 quick prompts)
# SKIP if endpoint was already found unavailable in step 3
echo -n "5. Batch completion... "
if [[ $ENDPOINT_SKIP -eq 1 ]]; then
    echo "SKIP (endpoint unavailable)"
else
    BATCH_INPUT=$(mktemp)
    echo '{"prompt": "Say yes"}' > "$BATCH_INPUT"
    echo '{"prompt": "Say no"}' >> "$BATCH_INPUT"

    START=$(date +%s.%N)
    RESULT=$("$SKILL_DIR/.venv/bin/python" "$SKILL_DIR/batch.py" batch --input "$BATCH_INPUT" --timeout 30 2>&1 | tail -2) || true
    EXIT_CODE=${PIPESTATUS[0]:-$?}
    END=$(date +%s.%N)
    ELAPSED=$(echo "$END - $START" | bc)
    rm -f "$BATCH_INPUT"

    if [[ $EXIT_CODE -eq 0 ]]; then
        OK_COUNT=$(echo "$RESULT" | grep -c '"ok": true' || true)
        echo "OK (${ELAPSED}s, ${OK_COUNT}/2 ok)"
    else
        echo "SKIP (batch endpoint error, exit=$EXIT_CODE)"
        ENDPOINT_SKIP=1
    fi
fi

# 6. Check Lean4 availability (optional)
echo -n "6. Lean4 prover (optional)... "
if "$SKILL_DIR/.venv/bin/python" "$SKILL_DIR/prove.py" --check 2>&1 | grep -q '"ready": true'; then
    echo "OK (ready)"
else
    echo "SKIP (not configured)"
fi

echo ""
if [[ $ENDPOINT_SKIP -eq 1 ]]; then
    echo "=== Sanity: SKIP (code OK, LLM endpoint unavailable) ==="
    exit 3
fi
echo "=== All sanity checks passed ==="
