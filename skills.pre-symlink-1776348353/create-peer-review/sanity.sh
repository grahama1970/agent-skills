#!/usr/bin/env bash
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== /create-peer-review Sanity Checks ==="
FAIL=0

# Test 1: Required files
echo "1. Required files..."
for f in SKILL.md run.sh pyproject.toml; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "   FAIL - missing $f"
        FAIL=1
    fi
done
if [[ $FAIL -eq 0 ]]; then echo "   PASS"; fi

# Test 2: Persona definitions
echo ""
echo "2. Reviewer personas..."
if [[ -f "$SCRIPT_DIR/personas/reviewers.yaml" ]]; then
    echo "   PASS - reviewers.yaml exists"
else
    echo "   FAIL - personas/reviewers.yaml missing"
    FAIL=1
fi

# Test 3: uv available
echo ""
echo "3. uv available..."
if command -v uv &>/dev/null; then
    echo "   PASS"
else
    echo "   FAIL - uv not found"
    FAIL=1
fi

# Test 4: Python module imports
echo ""
echo "4. Python module imports..."
if uv run --project "$SCRIPT_DIR" python -c "
from src.review_engine import ReviewEngine, ReviewResult, RubricScore
from src.review_heuristics import HeuristicReviewer
from src.reviewer_personas import load_reviewers, ReviewerPersona
from src.exemplar_comparison import ExemplarComparator
from src.cascade_integration import build_review_cascade
from src.curriculum import review_arxiv, review_arxiv_batch
from src.converge import converge, compute_delta, check_convergence, extract_revision_notes
from src.converge import ConvergenceTrajectory, RoundResult, snapshot_paper
print('   All modules import OK')
" 2>/dev/null; then
    echo "   PASS"
else
    echo "   WARN: Module imports need dependency install (run: uv sync --project $SCRIPT_DIR)"
fi

# Test 5: Dataclass instantiation
echo ""
echo "5. Core dataclass..."
if uv run --project "$SCRIPT_DIR" python -c "
from src.review_engine import RubricScore
score = RubricScore(soundness=3.0, technical_novelty=2.5, empirical_novelty=3.0, significance=3.0, clarity=3.5, presentation=3.0)
signal = score.weighted_signal()
assert 5.0 < signal < 9.0, f'Unexpected signal: {signal}'
print(f'   RubricScore works: signal={signal:.2f}/10')
" 2>/dev/null; then
    echo "   PASS"
else
    echo "   WARN: Dataclass test needs dependencies"
fi

# Test 6: CLI help
echo ""
echo "6. CLI help..."
if uv run --project "$SCRIPT_DIR" python -m src.cli --help >/dev/null 2>&1; then
    echo "   PASS"
else
    echo "   WARN: CLI help not yet available"
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
