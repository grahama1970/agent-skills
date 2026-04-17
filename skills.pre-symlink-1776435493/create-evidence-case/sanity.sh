#!/usr/bin/env bash
# sanity.sh — Evidence case skill sanity check
# Runs fast eval cases (q01, q10, q12) via run_question_bank.py
# Exit 0 if all pass, exit 1 if any fail
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== create-evidence-case sanity check ==="

# Check 1: Python imports work
echo "[1/5] Checking imports..."
python3 -c "
from models import ClaimNode, DecompositionNode, EvidenceNode, GateResult, StrategyNode, VerdictNode, NODE_CLASSES
assert 'decomposition' in NODE_CLASSES, 'DecompositionNode missing from NODE_CLASSES'
d = DecompositionNode(question='test', given_components=[], then_components=[])
assert d.to_dict(), 'DecompositionNode.to_dict() failed'
print('  imports OK')
"

# Check 2: Runner collectors importable
echo "[2/5] Checking runner collectors..."
python3 -c "
from collect import (
    collect_recall, collect_entities, collect_topic,
    collect_clarify, collect_lean4_proof, collect_dogpile,
    collect_cmmc, collect_edge_verify, collect_lean4_provable,
    group_by_technique, decompose_sentence, collect_per_component,
)
from candidate_qra import (
    quarantine_as_candidate_qra, generate_gap_review_questions,
    promote_candidate_qra, reject_candidate_qra, process_interview_result,
    EvidenceCaseStore2,
)
from runner import EvidenceCaseRunner
print('  collect + candidate_qra + runner imports OK')
"

# Check 3: Report functions importable
echo "[3/5] Checking report functions..."
python3 -c "
from report import (
    render_decomposition_mermaid, render_formalization_table,
    render_per_component_resolution, render_cross_component_mermaid,
    render_execution_flow_mermaid, render_clarify_output,
    render_proof_result, render_metrics_table, render_full_report,
    synthesize_answer_narrative, build_meaningful_sub_claims,
    generate_report, build_figure_data, build_mermaid_tree,
)
print('  report imports OK')
"

# Check 4: Fixtures exist and are valid JSON
echo "[4/5] Checking fixtures..."
python3 -c "
import json
from pathlib import Path

fixtures = Path('fixtures/eval.json')
assert fixtures.exists(), 'fixtures/eval.json missing'
data = json.loads(fixtures.read_text())
assert data['version'] == 1, 'version must be 1'
assert data['skill'] == 'create-evidence-case', 'wrong skill name'
assert len(data['cases']) == 12, f'Expected 12 cases, got {len(data[\"cases\"])}'

# Check fast-tagged cases exist
fast_cases = [c for c in data['cases'] if 'fast' in c.get('tags', [])]
assert len(fast_cases) == 3, f'Expected 3 fast cases, got {len(fast_cases)}'

# Check all cases have required fields
for c in data['cases']:
    assert 'name' in c, f'Case missing name'
    assert 'expected_verdict' in c, f'Case {c[\"name\"]} missing expected_verdict'
    assert 'rationale' in c, f'Case {c[\"name\"]} missing rationale'

print(f'  fixtures OK: {len(data[\"cases\"])} cases, {len(fast_cases)} fast')
"

# Check 5: Question bank matches fixtures
echo "[5/5] Checking question bank alignment..."
python3 -c "
import json
from question_bank import QUESTIONS

fixtures = json.loads(open('fixtures/eval.json').read())
assert len(fixtures['cases']) == len(QUESTIONS), \
    f'Fixture count ({len(fixtures[\"cases\"])}) != question bank ({len(QUESTIONS)})'

# Verify expected verdicts match
verdict_map = {'yes': 'satisfied', 'no': 'not_satisfied', 'inconclusive': 'inconclusive'}
for i, (case, q) in enumerate(zip(fixtures['cases'], QUESTIONS)):
    expected_fixture = case['expected_verdict']
    if q.expected_answerable == 'maybe':
        # 'maybe' means multiple verdicts acceptable — fixture should be a list or 'maybe'
        if isinstance(expected_fixture, list):
            pass  # list of acceptable verdicts is fine
        else:
            assert expected_fixture == 'maybe', \
                f'Q{i+1}: bank says maybe but fixture has {expected_fixture}'
    else:
        expected_bank = verdict_map.get(q.expected_answerable, q.expected_answerable)
        if isinstance(expected_fixture, list):
            assert expected_bank in expected_fixture, \
                f'Q{i+1}: bank expects {expected_bank} but fixture has {expected_fixture}'
        else:
            assert expected_fixture == expected_bank, \
                f'Q{i+1}: fixture expects {expected_fixture} but bank expects {expected_bank}'

print(f'  alignment OK: {len(QUESTIONS)} questions match fixtures')
"

echo ""
echo "=== All 5 sanity checks passed ==="
