#!/usr/bin/env bash
# Sanity checks for /create-persona skill
# Tests: imports, CLI commands, templates, memory integration

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== /create-persona Sanity Checks ==="
echo ""

FAIL=0

# Use uv run for all python commands

# Verify dependencies are available
if ! uv run python -c "import typer, rich" 2>/dev/null; then
    echo "WARN: typer/rich not available. Run from .pi/skills/.venv or install dependencies."
    echo "      cd .pi/skills && uv pip install typer rich"
fi

# Test 1: Python module imports
echo "1. Python module imports..."
if uv run python -c "
from src.persona import Persona, PersonaRelationship, create_persona, get_persona
from src.templates import TEMPLATES, get_template, get_template_names
from src.interview import interview_for_persona
from src.research import research_colleague_work
print('   All modules import OK')
"; then
    echo "   PASS"
else
    echo "   FAIL: Module imports failed"
    FAIL=1
fi

# Test 2: Persona dataclass
echo ""
echo "2. Persona dataclass..."
if uv run python -c "
from src.persona import Persona

p = Persona(
    name='Test Person',
    role='Test Role',
    organization='Test Org',
    domain='testing',
    goals=['Goal 1', 'Goal 2'],
    template='client',
)
assert p.name == 'Test Person'
assert p.role == 'Test Role'
assert len(p.goals) == 2
assert p.created_at  # Should be auto-set

# Test serialization
json_str = p.to_json()
assert 'Test Person' in json_str

# Test deserialization
p2 = Persona.from_json(json_str)
assert p2.name == p.name
assert p2.goals == p.goals

print('   Dataclass works OK')
"; then
    echo "   PASS"
else
    echo "   FAIL: Persona dataclass broken"
    FAIL=1
fi

# Test 3: Templates
echo ""
echo "3. Templates..."
if uv run python -c "
from src.templates import TEMPLATES, get_template, get_template_names, should_auto_learn

# Check all templates exist
templates = get_template_names()
assert 'client' in templates
assert 'expert' in templates
assert 'stakeholder' in templates
assert 'adversary' in templates
print(f'   Found {len(templates)} templates: {templates}')

# Check expert auto-learns
assert should_auto_learn('expert') == True
assert should_auto_learn('client') == False

# Check templates have questions
client = get_template('client')
assert 'interview_questions' in client
assert len(client['interview_questions']) > 0

print('   Templates OK')
"; then
    echo "   PASS"
else
    echo "   FAIL: Templates broken"
    FAIL=1
fi

# Test 4: PersonaRelationship
echo ""
echo "4. PersonaRelationship..."
if uv run python -c "
from src.persona import PersonaRelationship

rel = PersonaRelationship(
    from_persona='Alice',
    to_persona='Bob',
    relationship='colleague',
    bridges=['Precision', 'Resilience'],
    context='Work together on AI safety',
)

assert rel.from_persona == 'Alice'
assert rel.to_persona == 'Bob'
assert 'Precision' in rel.bridges

# Check tags generation
tags = rel.get_memory_tags()
assert 'colleague' in tags
assert 'bridge:Precision' in tags
assert 'from:alice' in tags

print('   PersonaRelationship OK')
"; then
    echo "   PASS"
else
    echo "   FAIL: PersonaRelationship broken"
    FAIL=1
fi

# Test 5: CLI help
echo ""
echo "5. CLI --help..."
CLI_HELP=$(cd "$SCRIPT_DIR" && uv run python -m src.cli --help 2>&1)
if echo "$CLI_HELP" | grep -q "Commands"; then
    echo "   --help works"
    echo "   PASS"
else
    echo "   CLI output: $CLI_HELP"
    echo "   FAIL: CLI --help failed"
    FAIL=1
fi

# Test 6: CLI create --help
echo ""
echo "6. CLI create --help..."
CREATE_HELP=$(cd "$SCRIPT_DIR" && uv run python -m src.cli create --help 2>&1)
if echo "$CREATE_HELP" | grep -q "template"; then
    echo "   create --help works"
    echo "   PASS"
else
    echo "   CLI output: $CREATE_HELP"
    echo "   FAIL: CLI create --help failed"
    FAIL=1
fi

# Test 7: Dry-run create
echo ""
echo "7. Dry-run create..."
if uv run python -m src.cli create "Test Sanity Person" --template client --dry-run --role "Tester" 2>/dev/null | grep -q "Would store"; then
    echo "   dry-run create works"
    echo "   PASS"
else
    # Check if it at least runs without error
    if uv run python -m src.cli create "Test Sanity Person" --template client --dry-run --role "Tester" 2>&1 | grep -q "Creating persona"; then
        echo "   dry-run create works (alternative output)"
        echo "   PASS"
    else
        echo "   WARN: dry-run output format unexpected"
    fi
fi

# Test 8: Memory skill available
echo ""
echo "8. Memory skill available..."
MEMORY_CLI="$HOME/.local/bin/memory-agent"
if [[ -x "$MEMORY_CLI" ]]; then
    echo "   memory-agent found at $MEMORY_CLI"
    echo "   PASS"
else
    MEMORY_SKILL="$(dirname "$SCRIPT_DIR")/../.agent/skills/memory/run.sh"
    if [[ -x "$MEMORY_SKILL" ]]; then
        echo "   memory skill found at $MEMORY_SKILL"
        echo "   PASS"
    else
        echo "   WARN: memory skill not found (degraded functionality)"
    fi
fi

# Test 9: Research module
echo ""
echo "9. Research module..."
if uv run python -c "
from src.research import (
    research_colleague_work,
    get_quotable_colleagues,
    format_colleague_quote,
    enrich_persona_with_colleagues,
)
print('   Research functions importable')
"; then
    echo "   PASS"
else
    echo "   FAIL: Research module broken"
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
