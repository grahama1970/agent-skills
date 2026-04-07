#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [learn-artist] Sanity Check ==="

# Check 1: Required files exist
echo -n "Check 1: Required files... "
for f in SKILL.md run.sh; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL - missing $f"
        exit 1
    fi
done
echo "OK"

# Check 2: Docker available (needed for RVC training)
echo -n "Check 2: Docker available... "
if command -v docker &>/dev/null; then
    echo "OK"
else
    echo "SKIP - docker not found (required for RVC training)"
fi

# Check 3: ffmpeg/ffprobe available (needed for audio processing)
echo -n "Check 3: ffmpeg available... "
if command -v ffmpeg &>/dev/null && command -v ffprobe &>/dev/null; then
    echo "OK (ffmpeg $(ffmpeg -version 2>&1 | head -1 | cut -d' ' -f3))"
else
    echo "SKIP - ffmpeg/ffprobe not found (required for audio processing)"
fi

# Check 4: Storage paths accessible
echo -n "Check 4: Storage paths... "
MODELS_ROOT="/mnt/storage12tb/media/music/rvc-models"
TRAINING_ROOT="/mnt/storage12tb/media/music/rvc-training"
if [[ -d "/mnt/storage12tb" ]]; then
    mkdir -p "$MODELS_ROOT/voice" "$MODELS_ROOT/instrument" "$TRAINING_ROOT" 2>/dev/null || true
    if [[ -d "$MODELS_ROOT" ]]; then
        echo "OK ($MODELS_ROOT)"
    else
        echo "WARN - could not create models directory"
    fi
else
    echo "SKIP - /mnt/storage12tb not mounted"
fi

# Check 5: discover-music skill available
echo -n "Check 5: discover-music skill... "
DISCOVER_DIR="$SCRIPT_DIR/../discover-music"
if [[ -f "$DISCOVER_DIR/run.sh" ]]; then
    echo "OK"
else
    echo "SKIP - discover-music skill not found (needed for YouTube search)"
fi

# Check 6: Python available (for sync_memory, enrich_taxonomy)
echo -n "Check 6: Python available... "
if ! command -v python3 &>/dev/null; then
    echo "FAIL - python3 not found"
    exit 1
fi
echo "OK"

# Check 7: jq available (used in list/status commands)
echo -n "Check 7: jq available... "
if command -v jq &>/dev/null; then
    echo "OK"
else
    echo "SKIP - jq not found (needed for JSON output)"
fi

# Check 8: CLI help works
echo -n "Check 8: CLI help... "
output=$("$SCRIPT_DIR/run.sh" help 2>&1 || true)
if echo "$output" | grep -qi "learn-artist\|voice\|train"; then
    echo "OK"
else
    echo "FAIL - run.sh help did not produce expected output"
    exit 1
fi

# Check 9: List command (should work even with no models)
echo -n "Check 9: list command... "
output=$("$SCRIPT_DIR/run.sh" list 2>&1 || true)
if echo "$output" | grep -qi "voice\|instrument\|model"; then
    echo "OK"
else
    echo "WARN - list command produced unexpected output"
fi

echo "Result: PASS"
