#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [learn-voice] Sanity Check ==="

# Check 1: Required files exist
echo "Check 1: Required files..."
for f in SKILL.md run.sh; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL: Missing $f"
        exit 1
    fi
done
echo "  SKILL.md and run.sh present"

# Check 2: run.sh is executable
if [[ ! -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "FAIL: run.sh is not executable"
    exit 1
fi
echo "  run.sh is executable"

# Check 3: Required CLI tools
for cmd in docker jq ffprobe bc; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "FAIL: Required command not found: $cmd"
        exit 1
    fi
done
echo "  CLI tools available (docker, jq, ffprobe, bc)"

# Check 4: Storage paths exist
MODELS_ROOT="/mnt/storage12tb/media/music/rvc-models"
TRAINING_ROOT="/mnt/storage12tb/media/music/rvc-training"
if [[ ! -d "/mnt/storage12tb" ]]; then
    echo "  SKIP: 12TB storage not mounted at /mnt/storage12tb"
    echo "Result: SKIP (storage not available)"
    exit 0
fi
echo "  12TB storage is mounted"

for d in "$MODELS_ROOT" "$TRAINING_ROOT"; do
    if [[ ! -d "$d" ]]; then
        echo "  Creating missing dir: $d"
        mkdir -p "$d"
    fi
done
echo "  Storage paths exist"

# Check 5: run.sh help works
help_output=$("$SCRIPT_DIR/run.sh" help 2>&1)
if ! echo "$help_output" | grep -q "learn-voice"; then
    echo "FAIL: run.sh help did not produce expected output"
    exit 1
fi
echo "  run.sh help works"

# Check 6: list command works (non-destructive, reads model dirs)
list_output=$("$SCRIPT_DIR/run.sh" list 2>&1 || true)
if echo "$list_output" | grep -qi "voice\|model\|instrument"; then
    echo "  list command executes"
else
    echo "  WARN: list command returned unexpected output (may be empty library)"
fi

# Check 7: stats command works
stats_output=$("$SCRIPT_DIR/run.sh" stats 2>&1 || true)
if echo "$stats_output" | grep -q "Voice Library Statistics"; then
    echo "  stats command works"
else
    echo "FAIL: stats command did not produce expected output"
    exit 1
fi

echo "Result: PASS"
