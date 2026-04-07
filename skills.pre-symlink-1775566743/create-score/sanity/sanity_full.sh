#!/usr/bin/env bash
#
# Full sanity check for create-score skill
# Requires GPU and Docker - tests actual generation
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== create-score Full Sanity Check (GPU Required) ==="
echo ""

# Check prerequisites
echo "[Pre] Checking prerequisites..."
if ! command -v docker >/dev/null 2>&1; then
    echo "[FAIL] Docker not found"
    exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
    echo "[FAIL] Docker Compose not found"
    exit 1
fi

if ! nvidia-smi >/dev/null 2>&1; then
    echo "[WARN] NVIDIA GPU not detected, mock generation will be used"
fi

echo "[OK] Prerequisites met"
echo ""

# Create temp directory for outputs
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

# 1. Start service
echo "[1/4] Starting ACE-Step service..."
cd "$SKILL_DIR"
if ./run.sh up; then
    echo "[OK] Service started"
else
    echo "[FAIL] Service failed to start"
    docker compose -f docker/compose.yml logs --tail=50
    exit 1
fi

# 2. Check health
echo "[2/4] Checking service health..."
MAX_WAIT=60
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    if curl -s http://localhost:${ACE_STEP_PORT:-8015}/healthz | grep -q '"ok":true'; then
        echo "[OK] Service healthy"
        break
    fi
    sleep 2
    ((WAITED+=2))
done

if [ $WAITED -ge $MAX_WAIT ]; then
    echo "[FAIL] Service not healthy after ${MAX_WAIT}s"
    docker compose -f docker/compose.yml logs --tail=50
    exit 1
fi

# 3. Generate test clip
echo "[3/4] Generating test clip (10s)..."
OUTPUT_FILE="$TEMP_DIR/test_output.wav"

if ./run.sh generate \
    --prompt "cinematic test, strings and piano" \
    --duration-s 10 \
    --seed 42 \
    --out "$OUTPUT_FILE" \
    --no-store-memory; then
    echo "[OK] Generation completed"
else
    echo "[FAIL] Generation failed"
    exit 1
fi

# 4. Verify output
echo "[4/4] Verifying output..."
if [ -f "$OUTPUT_FILE" ]; then
    SIZE=$(stat -c%s "$OUTPUT_FILE" 2>/dev/null || stat -f%z "$OUTPUT_FILE")
    if [ "$SIZE" -gt 10000 ]; then
        echo "[OK] Output exists and is ${SIZE} bytes"
    else
        echo "[FAIL] Output too small: ${SIZE} bytes"
        exit 1
    fi
else
    echo "[FAIL] Output file not found"
    exit 1
fi

# Optional: Stop service
# echo "[Cleanup] Stopping service..."
# ./run.sh down

echo ""
echo "=== FULL SANITY CHECK PASSED ==="
echo ""
echo "Output: $OUTPUT_FILE"
echo "Size: $SIZE bytes"
