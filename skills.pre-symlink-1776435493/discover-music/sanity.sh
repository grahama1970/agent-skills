#!/usr/bin/env bash
# Sanity checks for discover-music skill
# Local checks = hard FAIL, External API checks = graceful SKIP on timeout/error

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

PASS=0
FAIL=0
SKIP=0

# --- LOCAL CHECKS (hard FAIL) ---

# Test 1: CLI imports
echo "1. CLI imports..."
if uv run python -c "from src.cli import app; print('   Imports OK')" 2>/dev/null; then
    echo "   PASS"
    PASS=$((PASS + 1))
else
    echo "   FAIL"
    FAIL=$((FAIL + 1))
fi

# Test 2: Taxonomy validation
echo ""
echo "2. Taxonomy mappings..."
if uv run python -c "
from src.taxonomy import BRIDGE_TO_TAGS, BRIDGE_KEYWORDS, extract_bridge_tags, build_taxonomy_output

REQUIRED_BRIDGES = {'Precision', 'Resilience', 'Fragility', 'Corruption', 'Loyalty', 'Stealth'}

missing = REQUIRED_BRIDGES - set(BRIDGE_TO_TAGS.keys())
if missing:
    print(f'ERROR: Missing tag mappings for bridges: {missing}')
    exit(1)

missing = REQUIRED_BRIDGES - set(BRIDGE_KEYWORDS.keys())
if missing:
    print(f'ERROR: Missing keyword mappings for bridges: {missing}')
    exit(1)

for bridge, tags in BRIDGE_TO_TAGS.items():
    if len(tags) < 3:
        print(f'WARNING: Bridge {bridge} has only {len(tags)} tags')

tags = extract_bridge_tags(['doom metal', 'industrial'], 'dark and heavy sounds')
assert 'Corruption' in tags, f'Expected Corruption in tags, got {tags}'

output = build_taxonomy_output([{'tags': ['doom metal']}])
assert 'bridge_tags' in output
assert 'collection_tags' in output

print('   Taxonomy mappings: PASS')
" 2>/dev/null; then
    echo "   PASS"
    PASS=$((PASS + 1))
else
    echo "   FAIL"
    FAIL=$((FAIL + 1))
fi

# Test 3: Module line counts
echo ""
echo "3. Line count check (max 800)..."
LINE_OK=true
for pyfile in src/*.py; do
    lines=$(wc -l < "$pyfile")
    if [[ $lines -gt 800 ]]; then
        echo "   FAIL: $pyfile is $lines lines (max 800)"
        LINE_OK=false
    fi
done
if $LINE_OK; then
    echo "   PASS"
    PASS=$((PASS + 1))
else
    FAIL=$((FAIL + 1))
fi

# --- EXTERNAL API CHECKS (graceful SKIP on timeout/error) ---

# Test 4: MusicBrainz API (15s timeout)
echo ""
echo "4. MusicBrainz API..."
if timeout 15 uv run python -c "
import musicbrainzngs
musicbrainzngs.set_useragent('HorusAgent', '1.0', 'grahama@me.com')
result = musicbrainzngs.search_artists(artist='Chelsea Wolfe', limit=1)
artists = result.get('artist-list', [])
if artists:
    print(f'   Found: {artists[0].get(\"name\", \"Unknown\")}')
else:
    print('   No results')
" 2>/dev/null; then
    echo "   PASS"
    PASS=$((PASS + 1))
else
    rc=$?
    if [[ $rc -eq 124 ]]; then
        echo "   SKIP: MusicBrainz API timed out (15s)"
    else
        echo "   SKIP: MusicBrainz API unavailable (exit $rc)"
    fi
    SKIP=$((SKIP + 1))
fi

# Test 5: ListenBrainz API (15s timeout)
echo ""
echo "5. ListenBrainz API..."
if timeout 15 uv run python -c "
import httpx
resp = httpx.get('https://api.listenbrainz.org/1/stats/sitewide/artists', params={'count': 1, 'range': 'week'}, timeout=10)
if resp.status_code == 200:
    data = resp.json()
    artists = data.get('payload', {}).get('artists', [])[:1]
    if artists:
        print(f'   Top artist: {artists[0].get(\"artist_name\", \"Unknown\")}')
    else:
        print('   No stats returned')
else:
    print(f'   Status {resp.status_code}')
" 2>/dev/null; then
    echo "   PASS"
    PASS=$((PASS + 1))
else
    rc=$?
    if [[ $rc -eq 124 ]]; then
        echo "   SKIP: ListenBrainz API timed out (15s)"
    else
        echo "   SKIP: ListenBrainz API unavailable (exit $rc)"
    fi
    SKIP=$((SKIP + 1))
fi

echo ""
echo "======================================="
echo "  $PASS passed, $FAIL failed, $SKIP skipped"
echo "======================================="
if [[ $FAIL -gt 0 ]]; then
    echo "Some checks FAILED"
    exit 1
else
    exit 0
fi
