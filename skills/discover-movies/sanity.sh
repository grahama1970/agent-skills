#!/usr/bin/env bash
# Sanity checks for discover-movies skill

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== discover-movies sanity checks ==="
echo ""

# Ensure uv is available
if ! command -v uv &>/dev/null; then
    echo "ERROR: uv not found"
    exit 1
fi

# Sync dependencies
uv sync --quiet

# Run TMDB connectivity test
echo "[1/3] Testing TMDB API connectivity..."
if uv run python sanity/tmdb.py; then
    echo "      TMDB API: PASS"
else
    echo "      TMDB API: FAIL"
    exit 1
fi

# Run taxonomy validation
echo "[2/3] Validating taxonomy mappings..."
uv run python -c "
from src.taxonomy import BRIDGE_TO_GENRE_IDS, BRIDGE_TO_GENRES

REQUIRED_BRIDGES = {'Precision', 'Resilience', 'Fragility', 'Corruption', 'Loyalty', 'Stealth'}

# Check all bridges have mappings
missing = REQUIRED_BRIDGES - set(BRIDGE_TO_GENRE_IDS.keys())
if missing:
    print(f'ERROR: Missing genre ID mappings for bridges: {missing}')
    exit(1)

missing = REQUIRED_BRIDGES - set(BRIDGE_TO_GENRES.keys())
if missing:
    print(f'ERROR: Missing genre name mappings for bridges: {missing}')
    exit(1)

# Check genre IDs are valid
from src.tmdb_client import _GENRE_CACHE
for bridge, ids in BRIDGE_TO_GENRE_IDS.items():
    for gid in ids:
        if gid not in _GENRE_CACHE:
            print(f'WARNING: Unknown genre ID {gid} in bridge {bridge}')

print('Taxonomy mappings: PASS')
"
echo "      Taxonomy: PASS"

# Run a quick functional test
echo "[3/3] Testing bridge search..."
if uv run python -c "
from src.taxonomy import get_genre_ids_for_bridge, extract_bridge_tags

# Test bridge to genre lookup
ids = get_genre_ids_for_bridge('Corruption')
assert len(ids) > 0, 'No genre IDs for Corruption'

# Test tag extraction
tags = extract_bridge_tags(['Horror', 'Crime'], 'A dark and twisted tale')
assert 'Corruption' in tags, f'Expected Corruption in tags, got {tags}'

print('Bridge search: PASS')
"; then
    echo "      Bridge search: PASS"
else
    echo "      Bridge search: FAIL"
    exit 1
fi

echo ""
echo "=== All sanity checks passed ==="
