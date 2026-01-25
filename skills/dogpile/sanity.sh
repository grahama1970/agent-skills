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

echo "Result: PASS"
