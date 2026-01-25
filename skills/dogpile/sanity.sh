#!/bin/bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Dogpile Skill Sanity ==="

# Check run.sh
if [[ -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "  [PASS] run.sh exists"
else
    echo "  [FAIL] run.sh missing"
    exit 1
fi

# Check --help
if "$SCRIPT_DIR/run.sh" --help >/dev/null; then
    echo "  [PASS] run.sh --help works"
else
    echo "  [FAIL] run.sh --help failed"
    exit 1
fi

# Check dependencies
MISSING=0
for cmd in gh yt-dlp python3; do
    if command -v "$cmd" &> /dev/null; then
        echo "  [PASS] Dependency '$cmd' found"
    else
        echo "  [WARN] Dependency '$cmd' missing (some sources will fail)"
        # Note: We don't exit 1 here as some sources might still work
    fi
done

# Check sub-skills
for skill in arxiv perplexity brave-search codex youtube-transcripts; do
    if [[ -d "$SCRIPT_DIR/../$skill" ]]; then
        echo "  [PASS] Sub-skill '$skill' found"
    else
        echo "  [FAIL] Sub-skill '$skill' missing in $(dirname "$SCRIPT_DIR")"
        MISSING=1
    fi
done

if [[ $MISSING -eq 1 ]]; then
    echo "Result: FAIL"
    exit 1
fi

# Functional Check: Mock/Quick Search
echo "  [INFO] Running functional search test (AI agent memory)..."
# We use --no-interactive to skip the user interview and test the search stage
# We use a timeout to prevent hanging if a source is stuck
REPORT=$(timeout 60 "$SCRIPT_DIR/run.sh" search "AI agent memory" --no-interactive || echo "TIMEOUT")

if echo "$REPORT" | grep -q "Dogpile Report"; then
    echo "  [PASS] Functional search: Report generated"
else
    echo "  [FAIL] Functional search: Report missing or failed"
    echo "         Output: $REPORT"
    exit 1
fi

if echo "$REPORT" | grep -q "Codex Synthesis"; then
    echo "  [PASS] Functional search: Codex Synthesis present"
else
    echo "  [FAIL] Functional search: Codex Synthesis missing"
    exit 1
fi

# Check state file
if [[ -f "dogpile_state.json" ]]; then
    if grep -q "DONE" "dogpile_state.json"; then
        echo "  [PASS] Functional search: State file updated correctly"
    else
        echo "  [FAIL] Functional search: State file has no 'DONE' status"
        exit 1
    fi
else
    echo "  [FAIL] Functional search: dogpile_state.json not created"
    exit 1
fi

echo "Result: PASS"

