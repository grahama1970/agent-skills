#!/usr/bin/env bash
# Sanity checks for discover-music skill

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== discover-music Sanity Checks ==="
echo ""

# Ensure dependencies
if ! command -v uv &>/dev/null; then
    echo "FAIL: uv not found"
    exit 1
fi

if [[ ! -d ".venv" ]]; then
    echo "Installing dependencies..."
    uv sync --quiet
fi

FAIL=0

# Test 1: MusicBrainz
echo "1. MusicBrainz API..."
if uv run python sanity/musicbrainz.py; then
    echo "   PASS"
else
    echo "   FAIL"
    FAIL=1
fi

# Test 2: ListenBrainz
echo ""
echo "2. ListenBrainz API..."
if uv run python sanity/listenbrainz.py; then
    echo "   PASS"
else
    echo "   FAIL"
    FAIL=1
fi

# Test 3: CLI imports
echo ""
echo "3. CLI imports..."
if uv run python -c "from src.cli import app; print('   Imports OK')"; then
    echo "   PASS"
else
    echo "   FAIL"
    FAIL=1
fi

# Test 4: Taxonomy validation
echo ""
echo "4. Taxonomy mappings..."
if uv run python -c "
from src.taxonomy import BRIDGE_TO_TAGS, BRIDGE_KEYWORDS, extract_bridge_tags, build_taxonomy_output

REQUIRED_BRIDGES = {'Precision', 'Resilience', 'Fragility', 'Corruption', 'Loyalty', 'Stealth'}

# Check all bridges have mappings
missing = REQUIRED_BRIDGES - set(BRIDGE_TO_TAGS.keys())
if missing:
    print(f'ERROR: Missing tag mappings for bridges: {missing}')
    exit(1)

missing = REQUIRED_BRIDGES - set(BRIDGE_KEYWORDS.keys())
if missing:
    print(f'ERROR: Missing keyword mappings for bridges: {missing}')
    exit(1)

# Check each bridge has at least 3 tags
for bridge, tags in BRIDGE_TO_TAGS.items():
    if len(tags) < 3:
        print(f'WARNING: Bridge {bridge} has only {len(tags)} tags')

# Test extract_bridge_tags
tags = extract_bridge_tags(['doom metal', 'industrial'], 'dark and heavy sounds')
assert 'Corruption' in tags, f'Expected Corruption in tags, got {tags}'

# Test build_taxonomy_output
output = build_taxonomy_output([{'tags': ['doom metal']}])
assert 'bridge_tags' in output
assert 'collection_tags' in output

print('   Taxonomy mappings: PASS')
"; then
    echo "   PASS"
else
    echo "   FAIL"
    FAIL=1
fi

# Test 5: Bridge search
echo ""
echo "5. Bridge search (Corruption)..."
if uv run python -c "
from src.musicbrainz_client import search_by_bridge
results = search_by_bridge('Corruption', limit=3)
if results:
    for r in results:
        print(f'   - {r.name}')
    print('   PASS')
else:
    print('   WARN: No results (may be rate limited)')
"; then
    :
else
    echo "   FAIL"
    FAIL=1
fi

echo ""
echo "======================================="
if [[ $FAIL -eq 0 ]]; then
    echo "All sanity checks PASSED"
    exit 0
else
    echo "Some checks FAILED"
    exit 1
fi
