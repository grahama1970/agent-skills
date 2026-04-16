#!/bin/bash
# Blind sanity test for /qra-review skill.
# Tests: imports, CandidateBridge, assess_qra routing, TUI class instantiation.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load .env
if [ -f "$SCRIPT_DIR/.env" ]; then set -a; source "$SCRIPT_DIR/.env"; set +a; fi
if [ -f "$SCRIPT_DIR/../../.env" ]; then set -a; source "$SCRIPT_DIR/../../.env"; set +a; fi

MEMORY_SRC="$(cd "$SCRIPT_DIR/../../../../memory/src" 2>/dev/null && pwd)" || true
export PYTHONPATH="${MEMORY_SRC}:${PYTHONPATH:-}"

echo "=== /qra-review sanity ==="

# 1. Collections exist
uv run --project "$SCRIPT_DIR" python -c "
from graph_memory.arango_client import get_db
db = get_db()
assert db.has_collection('sparta_qra_candidates'), 'missing sparta_qra_candidates'
assert db.has_collection('rejected_qras'), 'missing rejected_qras'
print('PASS: collections exist')
"

# 2. CandidateBridge imports and works
uv run --project "$SCRIPT_DIR" python -c "
from graph_memory.candidate_bridge import CandidateBridge
cb = CandidateBridge()
count = cb.pending_count()
stats = cb.get_stats()
print(f'PASS: CandidateBridge (pending={count}, stats={stats})')
"

# 3. assess_qra routes correctly
uv run --project "$SCRIPT_DIR" python -c "
from graph_memory.quality.assess import assess_qra

# PASS case
r = assess_qra({
    'control_id': 'SV-SP-1',
    'question': 'How does SV-SP-1 protect spacecraft uplink?',
    'answer': 'SV-SP-1 implements spacecraft command authentication for telemetry uplink protection via ground station cryptographic verification of bus-level encryption.',
    'reasoning': 'Per SPARTA SV-SP-1 specification section 3.2, command authentication requires cryptographic key management for uplink channels.',
    'grounding_score': 0.82,
    'citations': ['SPARTA Framework v2.0'],
    'conceptual_tags': ['Resilience'],
    'tactical_tags': ['Harden'],
})
assert r['grade'] == 'PASS', f'Expected PASS, got {r[\"grade\"]}: {r[\"notes\"]}'

# WARN case
r = assess_qra({
    'control_id': 'SV-SP-1',
    'answer': 'SV-SP-1 protects spacecraft uplink command authentication.',
    'grounding_score': 0.65,
})
assert r['grade'] == 'WARN', f'Expected WARN, got {r[\"grade\"]}'

# FAIL case
r = assess_qra({'control_id': 'SV-SP-1', 'answer': 'Yes.', 'grounding_score': 0.30})
assert r['grade'] == 'FAIL', f'Expected FAIL, got {r[\"grade\"]}'

print('PASS: assess_qra 3-way routing')
"

# 4. Full stage/accept/reject cycle
uv run --project "$SCRIPT_DIR" python -c "
from graph_memory.candidate_bridge import CandidateBridge
from graph_memory.quality.assess import assess_qra
from graph_memory.arango_client import get_db

cb = CandidateBridge()
db = get_db()

# Stage a WARN
doc = {'_key': 'sanity_test_001', 'control_id': 'SV-SP-1', 'answer': 'SV-SP-1 protects spacecraft uplink command authentication.', 'grounding_score': 0.65}
assessment = assess_qra(doc)
cb.stage(doc, assessment)
assert cb.pending_count() >= 1

# Accept it
cb.accept('sanity_test_001', 'sanity_test')

# Cleanup
try:
    db.collection('sparta_qra_candidates').delete('sanity_test_001')
except Exception:
    pass
try:
    db.collection('sparta_qra').delete('sanity_test_001')
except Exception:
    pass

print('PASS: stage/accept cycle')
"

# 5. TUI class imports (no display needed) — use package imports
uv run --project "$SCRIPT_DIR" python -c "
from qra_review.tui import QRAReviewApp
from qra_review.tui_widgets import StatsBar, QRACard, AssessmentDetail
from qra_review.tui_chat import EmbryChatHandler
from qra_review.tui_theme import EMBRY_TCSS
print('PASS: TUI imports')
"

echo "=== ALL SANITY TESTS PASSED ==="
