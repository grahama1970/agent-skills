#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASS=0
FAIL=0

check() {
    local desc="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        echo "  PASS: $desc"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $desc"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== /thunderdome sanity checks ==="

echo ""
echo "--- Module imports ---"
check "manifest.py" uv run --project "$SCRIPT_DIR" python -c "from scripts.manifest import ThunderdomeManifest, Strategy, load_manifest; print('OK')"
check "dispatch.py" uv run --project "$SCRIPT_DIR" python -c "from scripts.dispatch import dispatch_strategies, StrategyResult; print('OK')"
check "scoring.py" uv run --project "$SCRIPT_DIR" python -c "from scripts.scoring import score_round, detect_plateau, detect_regression, RoundResult; print('OK')"
check "tracking.py" uv run --project "$SCRIPT_DIR" python -c "from scripts.tracking import store_round, store_dogpile, recall_prior; print('OK')"
check "diagnosis.py" uv run --project "$SCRIPT_DIR" python -c "from scripts.diagnosis import diagnose_round, round_dogpile; print('OK')"
check "research.py" uv run --project "$SCRIPT_DIR" python -c "from scripts.research import analyze_dataset, pick_strategies, STRATEGY_POOL; print('OK')"
check "thunderdome.py" uv run --project "$SCRIPT_DIR" python -c "from scripts.thunderdome import app; print('OK')"

echo ""
echo "--- CLI ---"
check "run.sh --help" bash "$SCRIPT_DIR/run.sh" --help
check "run --help" bash "$SCRIPT_DIR/run.sh" run --help

echo ""
echo "--- Manifest ---"
check "classifier-table-merge.yaml loads" uv run --project "$SCRIPT_DIR" python -c "
from scripts.manifest import load_manifest
m = load_manifest('$SCRIPT_DIR/examples/classifier-table-merge.yaml')
assert m.name == 'table-merge-classifier'
assert len(m.strategies) == 0
assert len(m.reviewers) == 2
print('OK')
"

echo ""
echo "--- Scoring ---"
check "score_round works" uv run --project "$SCRIPT_DIR" python -c "
from scripts.scoring import score_round
rr = score_round([('a', 0.85, {}), ('b', 0.90, {}), ('c', 0.70, {})], 0.90, 1)
assert rr.winner_name == 'b'
assert rr.winner_score == 0.90
assert rr.gate_passed == True
print('OK')
"
check "detect_plateau" uv run --project "$SCRIPT_DIR" python -c "
from scripts.scoring import detect_plateau, RoundResult
rounds = [RoundResult(round_num=i, winner_score=0.81) for i in range(1,4)]
assert detect_plateau(rounds, window=3, epsilon=0.02)
print('OK')
"
check "detect_regression" uv run --project "$SCRIPT_DIR" python -c "
from scripts.scoring import detect_regression, RoundResult
rounds = [RoundResult(round_num=1, winner_score=0.90), RoundResult(round_num=2, winner_score=0.85), RoundResult(round_num=3, winner_score=0.80)]
assert detect_regression(rounds, window=2)
print('OK')
"

echo ""
echo "--- Strategy pool ---"
check "pick_strategies returns N" uv run --project "$SCRIPT_DIR" python -c "
from scripts.research import pick_strategies
s = pick_strategies(3, round_num=1)
assert len(s) == 3
s2 = pick_strategies(3, round_num=2)
assert s[0].name != s2[0].name, 'round 2 should pick different strategies'
print('OK')
"

echo ""
echo "--- Dry run ---"
check "dry-run" bash "$SCRIPT_DIR/run.sh" run "$SCRIPT_DIR/examples/classifier-table-merge.yaml" --dry-run

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
echo "All sanity checks passed."
