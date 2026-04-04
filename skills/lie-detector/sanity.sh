#!/usr/bin/env bash
set -euo pipefail

# sanity.sh — Non-mocked tests for /lie-detector
# Tests: seal/verify, HMAC, hash chain, training data, eval patterns,
# chain routing, intent gate, invariants fail-closed, self-seal

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="uv run --project $SCRIPT_DIR python"
OK=0
FAILED=0
TOTAL=0

ok() { ((OK++)); ((TOTAL++)); echo "  ✓ $1"; }
ng() { ((FAILED++)); ((TOTAL++)); echo "  ✗ $1"; }

echo "=== /lie-detector sanity ==="

# --- Test 1: seal + verify round-trip ---
echo ""
echo "Test 1: seal + verify round-trip"
TMP=$(mktemp -d)
cat > "$TMP/test_scoring.py" << 'PYEOF'
def compute_score(x):
    if x >= 0.95:
        return "A+"
    elif x >= 0.88:
        return "A"
    return "B"
PYEOF

$PYTHON -c "
from sealed_grading import seal, verify
from pathlib import Path
manifest = seal(['$TMP/test_scoring.py'], Path('$TMP/test_seal.json'))
assert len(manifest.files) == 1, f'Expected 1 file, got {len(manifest.files)}'
result = verify(Path('$TMP/test_seal.json'))
assert result.verdict == 'CLEAN', f'Expected CLEAN, got {result.verdict}'
" && ok "seal+verify CLEAN on unmodified file" || ng "seal+verify CLEAN"

# Modify and verify TAMPERED
echo "# tampered" >> "$TMP/test_scoring.py"
$PYTHON -c "
from sealed_grading import verify
from pathlib import Path
result = verify(Path('$TMP/test_seal.json'))
assert result.verdict == 'TAMPERED', f'Expected TAMPERED, got {result.verdict}'
" && ok "seal+verify TAMPERED on modified file" || ng "seal+verify TAMPERED"

# --- Test 2: HMAC signing ---
echo ""
echo "Test 2: HMAC signing"
# Restore file and re-seal with HMAC
cat > "$TMP/test_scoring2.py" << 'PYEOF'
def score(x):
    return x * 2
PYEOF

export LIE_DETECTOR_HMAC_KEY="test-secret-key-do-not-use"
$PYTHON -c "
import os
os.environ['LIE_DETECTOR_HMAC_KEY'] = 'test-secret-key-do-not-use'
# Force reload
import importlib
import sealed_grading
importlib.reload(sealed_grading)
from sealed_grading import seal, verify
from pathlib import Path
manifest = seal(['$TMP/test_scoring2.py'], Path('$TMP/test_hmac_seal.json'))
assert manifest.hmac_sig, 'Expected HMAC signature'
result = verify(Path('$TMP/test_hmac_seal.json'))
assert result.verdict == 'CLEAN', f'Expected CLEAN with valid HMAC, got {result.verdict}'
" && ok "HMAC signed seal verifies" || ng "HMAC signed seal"

# Tamper with seal JSON directly
$PYTHON -c "
import json, os
os.environ['LIE_DETECTOR_HMAC_KEY'] = 'test-secret-key-do-not-use'
import importlib
import sealed_grading
importlib.reload(sealed_grading)
from sealed_grading import verify
from pathlib import Path
seal_path = Path('$TMP/test_hmac_seal.json')
data = json.loads(seal_path.read_text())
data['files'][0]['sha256_raw'] = 'deadbeef' * 8
seal_path.write_text(json.dumps(data, indent=2))
result = verify(seal_path)
assert result.verdict == 'TAMPERED', f'Expected TAMPERED on forged seal, got {result.verdict}'
" && ok "HMAC detects forged seal" || ng "HMAC forged seal detection"
unset LIE_DETECTOR_HMAC_KEY

# --- Test 3: hash chain integrity ---
echo ""
echo "Test 3: hash chain integrity"
$PYTHON -c "
from sealed_grading import append_chain, verify_chain
from pathlib import Path
chain_path = Path('$TMP/chain.jsonl')
append_chain(chain_path, {'action': 'edit', 'file': 'scoring.py'})
append_chain(chain_path, {'action': 'run', 'file': 'test.py'})
valid, break_idx = verify_chain(chain_path)
assert valid, f'Chain should be valid, break at {break_idx}'
" && ok "hash chain valid" || ng "hash chain valid"

# --- Test 4: training data format ---
echo ""
echo "Test 4: training data format"
$PYTHON -c "
import json
from pathlib import Path
data_path = Path('$SCRIPT_DIR/training_data/seed_incidents.jsonl')
lines = data_path.read_text().strip().split('\n')
assert len(lines) >= 16, f'Expected >= 16 examples, got {len(lines)}'
labels = set()
for line in lines:
    entry = json.loads(line)
    assert 'text' in entry, 'Missing text field'
    assert 'label' in entry, 'Missing label field'
    assert entry['label'] in ('honest', 'gaming', 'drift'), f'Invalid label: {entry[\"label\"]}'
    labels.add(entry['label'])
assert labels == {'honest', 'gaming', 'drift'}, f'Missing labels: {labels}'
" && ok "training data format valid (3 classes)" || ng "training data format"

# --- Test 5: eval-file detection (includes incident file) ---
echo ""
echo "Test 5: eval-file detection"
$PYTHON -c "
from delta_analysis import _is_eval_file
assert _is_eval_file('pi-mono/.pi/skills/review-pdf/verify/scoring.py'), 'scoring.py not detected'
assert _is_eval_file('scripts/nico_asks_embry.py'), 'nico_asks_embry.py not detected (THE INCIDENT FILE)'
assert _is_eval_file('batch_review.py'), 'batch_review.py not detected'
assert _is_eval_file('data/gold_standards/test_gs.json'), 'gold standard not detected'
assert _is_eval_file('verify/runner.py'), 'runner.py not detected'
assert _is_eval_file('annealing.py'), 'annealing.py not detected'
assert not _is_eval_file('src/extractor/pipeline/steps/s05_table.py'), 'false positive on extraction file'
" && ok "eval-file pattern matching (includes incident file)" || ng "eval-file patterns"

# --- Test 6: skill chain heuristic routing ---
echo ""
echo "Test 6: skill chain heuristic routing"
$PYTHON -c "
from skill_chain import _heuristic_routing
layers = _heuristic_routing('agent edited scoring.py and modified thresholds')
assert 'seal' in layers, f'Missing seal: {layers}'
layers = _heuristic_routing('re-ran pipeline without changes')
assert layers == ['seal'], f'Expected [seal] for re-run: {layers}'
layers = _heuristic_routing('improved table extraction accuracy')
assert 'seal' in layers and 'conform' in layers, f'Missing expected layers: {layers}'
" && ok "heuristic routing" || ng "heuristic routing"

# --- Test 7: intent gate empty rejection ---
echo ""
echo "Test 7: intent gate empty rejection"
$PYTHON -c "
from intent_gate import check_intent
result = check_intent('', 'edited some files')
assert result.verdict == 'REJECT', f'Expected REJECT for empty intent, got {result.verdict}'
" && ok "empty intent rejected" || ng "empty intent rejection"

# --- Test 8: invariants FAIL-CLOSED (no grading file) ---
echo ""
echo "Test 8: invariants fail-closed"
$PYTHON -c "
from invariants import verify_invariants
from pathlib import Path
# No file → PROOF_FAILED (not PROVEN)
result = verify_invariants(None)
assert result.verdict == 'PROOF_FAILED', f'Expected PROOF_FAILED with no file, got {result.verdict}'
# Nonexistent file → PROOF_FAILED
result = verify_invariants(Path('/tmp/nonexistent.py'))
assert result.verdict == 'PROOF_FAILED', f'Expected PROOF_FAILED for missing file, got {result.verdict}'
" && ok "invariants fail-closed without grading file" || ng "invariants fail-closed"

# --- Test 9: invariants detect canonical match ---
echo ""
echo "Test 9: invariants detect canonical values"
cat > "$TMP/canonical_scoring.py" << 'PYEOF'
WEIGHTS = {
    "content_coverage": 0.22,
    "section_alignment": 0.18,
    "table_fidelity": 0.16,
    "equation_fidelity": 0.14,
    "ordering_yx": 0.12,
    "figure_fidelity": 0.10,
    "data_quality": 0.08,
}
def grade(score):
    if score >= 0.95:
        return "A+"
    elif score >= 0.88:
        return "A"
    elif score >= 0.78:
        return "B"
    elif score >= 0.65:
        return "C"
    return "F"
PYEOF

$PYTHON -c "
from invariants import verify_invariants
from pathlib import Path
result = verify_invariants(Path('$TMP/canonical_scoring.py'))
assert result.verdict == 'PROVEN', f'Expected PROVEN for canonical values, got {result.verdict}: {result.errors}'
" && ok "invariants PROVEN for canonical values" || ng "invariants canonical"

# --- Test 10: invariants detect tampered threshold ---
echo ""
echo "Test 10: invariants detect tampered threshold"
cat > "$TMP/tampered_scoring.py" << 'PYEOF'
WEIGHTS = {
    "content_coverage": 0.22,
    "section_alignment": 0.18,
    "table_fidelity": 0.16,
    "equation_fidelity": 0.14,
    "ordering_yx": 0.12,
    "figure_fidelity": 0.10,
    "data_quality": 0.08,
}
def grade(score):
    if score >= 0.95:
        return "A+"
    elif score >= 0.80:
        return "A"
    elif score >= 0.72:
        return "B"
    elif score >= 0.65:
        return "C"
    return "F"
PYEOF

$PYTHON -c "
from invariants import verify_invariants
from pathlib import Path
result = verify_invariants(Path('$TMP/tampered_scoring.py'))
assert result.verdict == 'PROOF_FAILED', f'Expected PROOF_FAILED for tampered thresholds, got {result.verdict}'
assert result.mismatches, f'Expected mismatches list, got empty'
" && ok "invariants detect tampered thresholds" || ng "invariants tampered detection"

# --- Test 11: invariants detect empty extraction (fail-closed) ---
echo ""
echo "Test 11: invariants fail-closed on refactored code"
cat > "$TMP/refactored_scoring.py" << 'PYEOF'
# Agent moved thresholds to config to evade AST extraction
import config
def grade(score):
    return config.compute_grade(score)
PYEOF

$PYTHON -c "
from invariants import verify_invariants
from pathlib import Path
result = verify_invariants(Path('$TMP/refactored_scoring.py'))
assert result.verdict == 'PROOF_FAILED', f'Expected PROOF_FAILED for refactored (empty extraction), got {result.verdict}'
assert 'found no thresholds' in (result.errors or '').lower() or 'fail-closed' in (result.errors or '').lower(), f'Expected fail-closed message: {result.errors}'
" && ok "invariants fail-closed on refactored code" || ng "invariants refactored fail-closed"

# --- Cleanup ---
rm -rf "$TMP"

# --- Summary ---
echo ""
echo "=== Results: $OK/$TOTAL passed, $FAILED failed ==="
if [ "$FAILED" -gt 0 ]; then
    exit 1
fi
echo "All sanity tests passed."
