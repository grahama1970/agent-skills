#!/usr/bin/env bash
# Sanity checks for discover-books skill

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== discover-books sanity checks ==="
echo ""

# Ensure uv is available
if ! command -v uv &>/dev/null; then
    echo "ERROR: uv not found"
    exit 1
fi

# Sync dependencies
uv sync --quiet

# Run OpenLibrary connectivity test
echo "[1/3] Testing OpenLibrary API connectivity..."
if uv run python sanity/openlibrary.py; then
    echo "      OpenLibrary API: PASS"
else
    echo "      OpenLibrary API: FAIL"
    exit 1
fi

# Run taxonomy validation
echo "[2/3] Validating taxonomy mappings..."
uv run python -c "
from src.taxonomy import BRIDGE_TO_SUBJECTS, BRIDGE_KEYWORDS

REQUIRED_BRIDGES = {'Precision', 'Resilience', 'Fragility', 'Corruption', 'Loyalty', 'Stealth'}

# Check all bridges have mappings
missing = REQUIRED_BRIDGES - set(BRIDGE_TO_SUBJECTS.keys())
if missing:
    print(f'ERROR: Missing subject mappings for bridges: {missing}')
    exit(1)

missing = REQUIRED_BRIDGES - set(BRIDGE_KEYWORDS.keys())
if missing:
    print(f'ERROR: Missing keyword mappings for bridges: {missing}')
    exit(1)

# Check each bridge has at least 3 subjects
for bridge, subjects in BRIDGE_TO_SUBJECTS.items():
    if len(subjects) < 3:
        print(f'WARNING: Bridge {bridge} has only {len(subjects)} subjects')

print('Taxonomy mappings: PASS')
"
echo "      Taxonomy: PASS"

# Run a quick functional test
echo "[3/3] Testing bridge search..."
if uv run python -c "
from src.taxonomy import get_subjects_for_bridge, extract_bridge_tags

# Test bridge to subject lookup
subjects = get_subjects_for_bridge('Resilience')
assert len(subjects) > 0, 'No subjects for Resilience'

# Test tag extraction
tags = extract_bridge_tags(['epic fantasy', 'adventure'], 'A heroic quest to save the kingdom')
assert 'Resilience' in tags, f'Expected Resilience in tags, got {tags}'

print('Bridge search: PASS')
"; then
    echo "      Bridge search: PASS"
else
    echo "      Bridge search: FAIL"
    exit 1
fi

echo ""
echo "=== All sanity checks passed ==="
