#!/bin/bash
set -e

# Project root
PI_MONO_ROOT="/home/graham/workspace/experiments/pi-mono"
HACK_SKILL="$PI_MONO_ROOT/.pi/skills/hack"
MEMORY_SKILL="$PI_MONO_ROOT/.agent/skills/memory"

echo "=== HACK SKILL: Advanced Sanity Test ==="

# 1. Simulate Book Download (Readarr)
echo ""
echo "[1/4] SIMULATING BOOK ACQUISITION..."
READARR_INBOX="$HOME/workspace/experiments/Readarr/inbox"
mkdir -p "$READARR_INBOX"
cp "$HACK_SKILL/tests/stackwarp_guide.md" "$READARR_INBOX/"
echo "[PASS] 'StackWarp Guide' downloaded to $READARR_INBOX"

# 2. Process Content (Knowledge Pipeline)
echo ""
echo "[2/4] PROCESSING CONTENT (Extract -> Memory)..."
$HACK_SKILL/run.sh process "$READARR_INBOX/stackwarp_guide.md" --context "hardware security"
echo "[PASS] processing complete."

# 3. Verify Memory Recall
echo ""
echo "[3/4] VERIFYING MEMORY RECALL..."
RECALL_OUTPUT=$($MEMORY_SKILL/run.sh recall --q "What is StackWarp exploitation?")
if echo "$RECALL_OUTPUT" | grep -q "found\": true"; then
    echo "[PASS] Recall successful!"
    echo " > Debug: $(echo "$RECALL_OUTPUT" | grep "answer" | head -n 1)"
else
    echo "[FAIL] Recall failed. Content not found in memory."
    echo "Output: $RECALL_OUTPUT"
    exit 1
fi

# 4. Run Isolated Exploit (Docker)
echo ""
echo "[4/4] RUNNING ISOLATED EXPLOIT (Docker)..."
$HACK_SKILL/run.sh exploit \
    --target "192.168.1.50" \
    --env "python" \
    --payload "$HACK_SKILL/tests/stackwarp_poc.py"

echo ""
echo "=== ADVANCED SANITY TEST PASSED ==="
