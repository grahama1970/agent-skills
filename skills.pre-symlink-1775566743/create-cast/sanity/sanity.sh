#!/usr/bin/env bash
# Sanity test for create-cast skill

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
cd "$SKILL_DIR"

echo "=== Create Cast Sanity Check ==="

# 1. Check syntax
echo -n "[1/6] Python syntax... "
uv run python -m py_compile create_cast/cli.py
uv run python -m py_compile create_cast/orchestrator.py
uv run python -m py_compile create_cast/schemas.py
uv run python -m py_compile create_cast/collaboration.py
uv run python -m py_compile create_cast/script_analyzer.py
uv run python -m py_compile create_cast/reference_finder.py
uv run python -m py_compile create_cast/identity_generator.py
uv run python -m py_compile create_cast/identity_pack.py
uv run python -m py_compile create_cast/voice_matcher.py
echo "OK"

# 2. Check imports
echo -n "[2/6] Imports... "
uv run python -c "from create_cast import start_casting_session, CastingSession, CharacterSpec" 2>/dev/null
echo "OK"

# 3. Check CLI help
echo -n "[3/6] CLI help... "
uv run python -m create_cast.cli --help > /dev/null
echo "OK"

# 4. Check subcommand help
echo -n "[4/6] Subcommand help... "
uv run python -m create_cast.cli start --help > /dev/null
uv run python -m create_cast.cli continue-session --help > /dev/null
uv run python -m create_cast.cli status --help > /dev/null
echo "OK"

# 5. Check schemas
echo -n "[5/6] Schema validation... "
uv run python -c "
from create_cast.schemas import (
    CharacterSpec, CharacterRole, PhysicalDescription,
    IdentityPack, VoiceAssignment, CastingSession, CastingPhase
)
# Create a character
char = CharacterSpec(
    name='TEST',
    role=CharacterRole.PROTAGONIST,
    screen_time_estimate=30.0,
    physical=PhysicalDescription(age_range='30s', gender='female'),
    dialogue_count=5,
    scenes=[1, 2, 3]
)
# Convert to dict and back
d = char.to_dict()
assert d['name'] == 'TEST'
assert d['role'] == 'protagonist'
print('OK')
"

# 6. Check collaboration module
echo -n "[6/6] Collaboration module... "
uv run python -c "
from create_cast.collaboration import (
    generate_session_id,
    generate_analysis_questions,
    format_questions_for_display
)
# Test session ID generation
sid = generate_session_id()
assert sid.startswith('casting-'), f'Invalid session ID: {sid}'
print('OK')
"

echo ""
echo "=== All sanity checks passed! ==="

# Optional: Test discover-talent integration
if uv run python -c "from create_cast.reference_finder import is_discover_talent_available; exit(0 if is_discover_talent_available() else 1)" 2>/dev/null; then
    echo ""
    echo "[Optional] discover-talent integration: AVAILABLE"
else
    echo ""
    echo "[Optional] discover-talent integration: NOT AVAILABLE (OK, optional)"
fi
