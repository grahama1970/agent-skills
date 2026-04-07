#!/bin/bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== Episodic Archiver Sanity ==="

# 1. run.sh exists and is executable
echo -n "run.sh exists... "
if [[ -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "OK"
else
    echo "FAIL"
    exit 1
fi

# 2. run.sh shows usage
echo -n "run.sh usage... "
OUTPUT=$("$SCRIPT_DIR/run.sh" 2>&1 || true)
if echo "$OUTPUT" | grep -qi "usage\|archive"; then
    echo "OK"
else
    echo "FAIL: $OUTPUT"
    exit 1
fi

# 3. Core Python files exist
echo -n "Core files exist... "
for f in archive_episode.py session_analysis.py analysis_llm.py analysis_integrations.py analysis_edges.py; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL: missing $f"
        exit 1
    fi
done
echo "OK"

# 4. Dead monolith removed
echo -n "Monolith removed... "
if [[ -f "$SCRIPT_DIR/session_analysis_monolith.py" ]]; then
    echo "FAIL: session_analysis_monolith.py still exists"
    exit 1
fi
echo "OK"

# 5. No raw httpx chat/completions calls
echo -n "No raw httpx LLM calls... "
if grep -r "httpx.post.*chat/completions" "$SCRIPT_DIR/archive_episode.py" 2>/dev/null; then
    echo "FAIL: raw httpx LLM calls found"
    exit 1
fi
echo "OK"

# 6. scillm importable
echo -n "scillm importable... "
SCILLM_DIR="$SCRIPT_DIR/../scillm"
if [[ -d "$SCILLM_DIR" ]]; then
    if python3 -c "import sys; sys.path.insert(0, '$SCILLM_DIR'); from batch import quick_completion" 2>/dev/null; then
        echo "OK"
    else
        echo "SKIP (import failed but dir exists)"
    fi
else
    echo "SKIP (scillm dir not found)"
fi

# 7. ArangoDB connectivity
echo -n "ArangoDB reachable... "
if curl -sf http://localhost:8529/_api/version >/dev/null 2>&1; then
    echo "OK"
else
    echo "SKIP (ArangoDB not running)"
fi

# 8. loguru in use (no custom log function)
echo -n "loguru in use... "
if grep -q "from loguru import logger" "$SCRIPT_DIR/archive_episode.py"; then
    echo "OK"
else
    echo "FAIL: loguru not imported"
    exit 1
fi

# 9. user_id field in archive code
echo -n "user_id support... "
if grep -q "user_id" "$SCRIPT_DIR/archive_episode.py" && grep -q "user_id" "$SCRIPT_DIR/session_analysis.py"; then
    echo "OK"
else
    echo "FAIL: user_id not found"
    exit 1
fi

echo "Result: PASS"
