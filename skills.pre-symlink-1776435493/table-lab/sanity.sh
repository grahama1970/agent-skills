#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PASS=0
FAIL=0

check() {
    local desc="$1"; shift
    if "$@" >/dev/null 2>&1; then
        echo "  [PASS] $desc"
        PASS=$((PASS + 1))
    else
        echo "  [FAIL] $desc"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== table-lab v2 sanity checks ==="

# 1. uv available
check "uv is installed" command -v uv

# 2. venv + deps sync
check "uv sync succeeds" uv sync --quiet

# 3. Python package importable
check "table_lab package imports" uv run python -c "from table_lab import cli; print('ok')"

# 4. Camelot importable
check "camelot importable" uv run python -c "from camelot import io as camelot_io; print('ok')"

# 5. PyMuPDF importable
check "pymupdf importable" uv run python -c "import fitz; print('ok')"

# 6. v1 CLI commands
check "tune --help" uv run python -m table_lab.cli tune --help
check "probe --help" uv run python -m table_lab.cli probe --help
check "show --help" uv run python -m table_lab.cli show --help
check "apply --help" uv run python -m table_lab.cli apply --help

# 7. v2 CLI commands
check "tune-corpus --help" uv run python -m table_lab.cli tune-corpus --help
check "watchdog --help" uv run python -m table_lab.cli watchdog --help

# 8. show command runs (empty state)
check "show runs (empty)" uv run python -m table_lab.cli show

# 9. Config loads with v2 additions
check "config v2 loads" uv run python -c "
from table_lab.config import (
    DATA_DIR, HINTS_DIR, CHECKPOINT_DIR, RESULTS_DIR,
    LATTICE_LINE_SCALES, KNOWN_PRESETS,
    WATCHDOG_WARN_FRAGMENTATION_RATE, WATCHDOG_STOP_FRAGMENTATION_RATE,
    CIRCUIT_BREAKER_MAX_FAILURES, MAX_CONVERGENCE_ITERATIONS,
    CONVERGENCE_SCORE_DELTA, WATCHDOG_CHECKPOINT_INTERVAL,
    CORPUS_TUNE_RESULTS_PATH, CORPUS_MANIFEST_PATH,
)
assert len(LATTICE_LINE_SCALES) >= 4
assert len(KNOWN_PRESETS) >= 3
assert 0 < WATCHDOG_STOP_FRAGMENTATION_RATE < WATCHDOG_WARN_FRAGMENTATION_RATE < 1
print('ok')
"

# 10. v1 modules importable
check "v1 modules importable" uv run python -c "
from table_lab.sampler import find_pages_with_tables, page_summary
from table_lab.probe import probe_page, ProbeResult
from table_lab.evaluate import score_result, compare_results, is_good_enough, quality_grade
from table_lab.tuner import tune, TuneResult
from table_lab.hints import save_hint, load_hint, list_hints, export_to_corpus
print('ok')
"

# 11. v2 modules importable
check "v2 modules importable" uv run python -c "
from table_lab.bridge import tag_extraction_result, tag_collection_dimensions, format_memory_tags
from table_lab.watchdog import WatchdogState, assess, record_result
from table_lab.checkpoint import TuneCheckpoint
from table_lab.monitor import DebugTableTaskClient
from table_lab.corpus import tune_with_convergence, tune_corpus
from table_lab.hints import resolve_preset_category, normalize_hint_key
print('ok')
"

# 12. Watchdog logic check
check "watchdog assess logic" uv run python -c "
from table_lab.watchdog import WatchdogState, assess, record_result
state = WatchdogState()
# Record 3 ok results
for i in range(3):
    v = record_result(state, f'test{i}.pdf', True, 2, 20, 0)
assert v == 'ok', f'Expected ok, got {v}'
assert state.fragmentation_rate == 0.0
# Record fragmented results to trigger warn
for i in range(10):
    record_result(state, f'frag{i}.pdf', True, 1, 5, 3)
assert state.fragmentation_rate > 0.65
v = assess(state)
assert v in ('warn', 'stop'), f'Expected warn/stop, got {v}'
print('ok')
"

# 13. Checkpoint round-trip
check "checkpoint round-trip" uv run python -c "
from table_lab.checkpoint import TuneCheckpoint
cp = TuneCheckpoint.load_or_create('sanity_test', 5)
cp.mark_completed('test.pdf', result={'score': 42})
assert cp.is_completed('test.pdf')
assert not cp.is_completed('other.pdf')
# Reload
cp2 = TuneCheckpoint.load_or_create('sanity_test', 5)
assert cp2.is_completed('test.pdf')
# Cleanup
import os
os.unlink(cp.checkpoint_path)
if cp.results_path.exists():
    os.unlink(cp.results_path)
print('ok')
"

# 14. Bridge tagging
check "bridge tagging" uv run python -c "
from table_lab.tuner import TuneResult
from table_lab.bridge import tag_extraction_result, tag_collection_dimensions, format_memory_tags
r = TuneResult(pdf_path='test.pdf', best_flavor='lattice', best_fragmentation=0, best_cell_count=20,
               all_results=[{'total_tables': 2}])
tags = tag_extraction_result(r)
assert 'Precision' in tags
assert 'Resilience' in tags
dims = tag_collection_dimensions(r)
assert dims['function'] == 'Extraction'
fmt = format_memory_tags(tags, dims)
assert 'bridge_tags' in fmt
print('ok')
"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [[ $FAIL -gt 0 ]]; then
    exit 1
fi
echo "All sanity checks passed."
