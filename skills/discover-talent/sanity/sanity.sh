#!/usr/bin/env bash
# Sanity test for discover-talent skill

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
cd "$SKILL_DIR"

echo "=== Discover Talent Sanity Check ==="

# 1. Check syntax
echo -n "[1/5] Python syntax... "
uv run python -m py_compile discover_talent/cli.py
uv run python -m py_compile discover_talent/tmdb_client.py
uv run python -m py_compile discover_talent/taxonomy.py
echo "OK"

# 2. Check imports
echo -n "[2/5] Imports... "
uv run python -c "from discover_talent import search_people, TMDBPerson, build_taxonomy_output" 2>/dev/null
echo "OK"

# 3. Check CLI help
echo -n "[3/5] CLI help... "
uv run python -m discover_talent.cli --help > /dev/null
echo "OK"

# 4. Check subcommand help
echo -n "[4/5] Subcommand help... "
uv run python -m discover_talent.cli search --help > /dev/null
uv run python -m discover_talent.cli filmography --help > /dev/null
uv run python -m discover_talent.cli by-movie --help > /dev/null
uv run python -m discover_talent.cli bridge --help > /dev/null
echo "OK"

# 5. Check taxonomy module
echo -n "[5/5] Taxonomy module... "
uv run python -c "
from discover_talent.taxonomy import (
    BRIDGE_TO_GENRE_IDS,
    BRIDGE_TO_ACTOR_TYPES,
    extract_bridge_tags_for_person,
    build_taxonomy_output
)
# Test extraction
tags = extract_bridge_tags_for_person([80, 53])  # Crime + Thriller
assert 'Corruption' in tags or 'Stealth' in tags or 'Precision' in tags, f'Expected bridge tag, got {tags}'
print('OK')
"

echo ""
echo "=== All sanity checks passed! ==="

# Optional: API connectivity test if TMDB_API_KEY is set
if [[ -n "${TMDB_API_KEY:-}" ]]; then
    echo ""
    echo "[Optional] Testing API connectivity..."
    uv run python -m discover_talent.cli check
fi
