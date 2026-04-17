#!/bin/bash
# sanity.sh - Full skill validation for ingest-yt-history
set -e

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SKILL_DIR"

echo "=== ingest-yt-history Sanity Check ==="
echo ""

# Track failures
FAILED=0

# 1. Run sanity scripts
echo "[1/5] Running sanity scripts..."
for script in sanity/*.py; do
    script_name=$(basename "$script")
    echo "  - $script_name"
    if ! uv run python "$script" > /dev/null 2>&1; then
        echo "    FAILED: $script_name"
        FAILED=1
    fi
done

if [[ $FAILED -eq 0 ]]; then
    echo "  All sanity scripts passed"
fi
echo ""

# 2. Run tests
echo "[2/5] Running pytest..."
if uv run pytest -q --tb=short 2>&1 | tail -5; then
    echo "  Tests passed"
else
    echo "  FAILED: pytest"
    FAILED=1
fi
echo ""

# 3. Test run.sh commands
echo "[3/5] Testing run.sh commands..."

# Test help
echo "  - help"
if ! ./run.sh help > /dev/null 2>&1; then
    echo "    FAILED: help"
    FAILED=1
fi

# Test parse
echo "  - parse"
if ! ./run.sh parse fixtures/sample_watch_history.json > /dev/null 2>&1; then
    echo "    FAILED: parse"
    FAILED=1
fi

# Test stats
echo "  - stats"
if ! ./run.sh stats fixtures/sample_music_history.jsonl > /dev/null 2>&1; then
    echo "    FAILED: stats"
    FAILED=1
fi

# Test find-music
echo "  - find-music"
if ! ./run.sh find-music fixtures/sample_music_history.jsonl --mood melancholic > /dev/null 2>&1; then
    echo "    FAILED: find-music"
    FAILED=1
fi

# Test sync-memory
echo "  - sync-memory"
if ! ./run.sh sync-memory fixtures/sample_music_history.jsonl > /dev/null 2>&1; then
    echo "    FAILED: sync-memory"
    FAILED=1
fi

# Test profile
echo "  - profile"
TEMP_PROFILE=$(mktemp)
if ! ./run.sh profile fixtures/sample_music_history.jsonl -o "$TEMP_PROFILE" > /dev/null 2>&1; then
    echo "    FAILED: profile"
    FAILED=1
fi
rm -f "$TEMP_PROFILE"

# Test filter
echo "  - filter"
if ! ./run.sh filter fixtures/sample_music_history.jsonl --service "youtube music" > /dev/null 2>&1; then
    echo "    FAILED: filter"
    FAILED=1
fi

# Test export
echo "  - export"
if ! ./run.sh export fixtures/sample_music_history.jsonl --format memory > /dev/null 2>&1; then
    echo "    FAILED: export"
    FAILED=1
fi

if [[ $FAILED -eq 0 ]]; then
    echo "  All run.sh commands passed"
fi
echo ""

# 4. Test enrich (requires API key, may skip)
echo "[4/5] Testing enrich command..."
if [[ -z "${YOUTUBE_API_KEY:-}" ]]; then
    # Try to load from .env files
    for env_file in "$HOME/.env" "$HOME/workspace/experiments/pi-mono/.env" ".env"; do
        if [[ -f "$env_file" ]]; then
            source "$env_file" 2>/dev/null || true
        fi
    done
fi

if [[ -n "${YOUTUBE_API_KEY:-}" ]]; then
    echo "  - enrich (with API key)"
    if ! ./run.sh enrich fixtures/sample_watch_history.json > /dev/null 2>&1; then
        echo "    FAILED: enrich"
        FAILED=1
    else
        echo "  Enrich passed"
    fi
else
    echo "  - enrich: SKIPPED (no YOUTUBE_API_KEY)"
fi
echo ""

# 5. Final check
echo "[5/5] Final check..."
if [[ $FAILED -eq 0 ]]; then
    echo ""
    echo "========================================"
    echo "  SANITY CHECK PASSED"
    echo "========================================"
    exit 0
else
    echo ""
    echo "========================================"
    echo "  SANITY CHECK FAILED"
    echo "========================================"
    exit 1
fi
