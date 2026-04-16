#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
RUST_DIR="$SKILL_DIR/src/rust"
PYTHON_DIR="$SKILL_DIR/src/python"

# ── Subcommands ──────────────────────────────────────────────
CMD="${1:-help}"
shift || true

case "$CMD" in
  extract)
    # Extract tables from a PDF
    # Usage: ./run.sh extract <pdf_path> [--strategy lattice|stream|network|hybrid|auto] [--output json|csv]
    python3 -c "
import sys, importlib.util, os
d = '$PYTHON_DIR'
if d not in sys.path: sys.path.insert(0, d)
# Register as package so relative imports work
spec = importlib.util.spec_from_file_location('extract_tables', os.path.join(d, '__init__.py'), submodule_search_locations=[d])
mod = importlib.util.module_from_spec(spec)
sys.modules['extract_tables'] = mod
spec.loader.exec_module(mod)
from extract_tables.extract_tables import cli
sys.argv = ['extract_tables', 'extract'] + sys.argv[1:]
cli()
" "$@"
    ;;

  batch)
    # Batch extract from a directory of PDFs
    python3 -c "
import sys, importlib.util, os
d = '$PYTHON_DIR'
if d not in sys.path: sys.path.insert(0, d)
spec = importlib.util.spec_from_file_location('extract_tables', os.path.join(d, '__init__.py'), submodule_search_locations=[d])
mod = importlib.util.module_from_spec(spec)
sys.modules['extract_tables'] = mod
spec.loader.exec_module(mod)
from extract_tables.extract_tables import cli
sys.argv = ['extract_tables', 'batch'] + sys.argv[1:]
cli()
" "$@"
    ;;

  build)
    # Build the Rust PyO3 module
    echo "Building Rust module with maturin..."
    cd "$RUST_DIR"
    maturin develop --release
    echo "Rust module built successfully."
    ;;

  build-python)
    # Compile Python parsers with mypyc
    echo "Compiling Python parsers with mypyc..."
    cd "$PYTHON_DIR"
    mypyc parsers/lattice.py parsers/stream.py parsers/network.py parsers/hybrid.py
    echo "Python parsers compiled."
    ;;

  test)
    # Run test suite
    cd "$SKILL_DIR"
    python3 -m pytest tests/ -v "$@"
    ;;

  shadow)
    # Show shadow log (self-correction history)
    if [ -f "$SKILL_DIR/shadow.jsonl" ]; then
      python3 -c "
import json, sys
for line in open('$SKILL_DIR/shadow.jsonl'):
    r = json.loads(line)
    status = 'AGREE' if r.get('agree') else 'DISAGREE'
    print(f\"{r.get('timestamp','')} [{status}] {r.get('strategy_predicted','')} vs {r.get('strategy_actual','')} acc={r.get('accuracy','?')}\")
" | tail -20
    else
      echo "No shadow logs yet."
    fi
    ;;

  profile)
    # Profile native vs Camelot — produces markdown report + CSV + figures
    # Usage: ./run.sh profile [pdf_path] [--runs N]
    python3 -c "
import sys, importlib.util, os
d = '$PYTHON_DIR'
if d not in sys.path: sys.path.insert(0, d)
spec = importlib.util.spec_from_file_location('extract_tables', os.path.join(d, '__init__.py'), submodule_search_locations=[d])
mod = importlib.util.module_from_spec(spec)
sys.modules['extract_tables'] = mod
spec.loader.exec_module(mod)
from extract_tables.profiler import profile_suite, profile_comparison
import json

args = sys.argv[1:]
if args and not args[0].startswith('--'):
    # Single PDF mode
    pdf = args[0]
    runs = 3
    for i, a in enumerate(args):
        if a == '--runs' and i+1 < len(args): runs = int(args[i+1])
    result = profile_comparison(pdf, pages='all', runs=runs)
    print(json.dumps(result['comparison'], indent=2))
else:
    # Suite mode (all fixtures)
    runs = 3
    for i, a in enumerate(args):
        if a == '--runs' and i+1 < len(args): runs = int(args[i+1])
    result = profile_suite(runs=runs)
    print(result['markdown'])
    print(f'\nReport: {result[\"markdown_path\"]}')
    print(f'CSV:    {result[\"csv_path\"]}')
    print(f'JSON:   {result[\"report_path\"]}')
" "$@"
    ;;

  transparency)
    # Generate visual transparency report: screenshot + metadata + extracted text
    # Usage: ./run.sh transparency <pdf_or_dir> [--output <dir>] [--pages 1] [--no-camelot]
    source "$SKILL_DIR/.venv/bin/activate" 2>/dev/null || true
    cd "$SKILL_DIR"
    PYTHONPATH="$SKILL_DIR/src" python3 -m python.parity_report "$@"
    ;;

  dual)
    # Dual extraction: Camelot + pdf_oxide in parallel threads
    # Usage: ./run.sh dual <pdf_path> [pages] [flavor]
    source "$SKILL_DIR/.venv/bin/activate" 2>/dev/null || true
    cd "$SKILL_DIR"
    PYTHONPATH="$SKILL_DIR/src" python3 -m python.dual_extract "$@"
    ;;

  status)
    # Health check
    bash "$SKILL_DIR/sanity.sh"
    ;;

  help|*)
    cat <<HELP
/extract-tables — Composable PDF table extraction (Rust + compiled Python)

Usage:
  ./run.sh extract <pdf> [--strategy auto] [--output json]
  ./run.sh batch <dir> [--output-dir <dir>]
  ./run.sh profile [pdf]   Profile native vs Camelot (markdown + CSV + figures)
  ./run.sh build           Build Rust PyO3 module
  ./run.sh build-python    Compile Python parsers (mypyc)
  ./run.sh test            Run test suite
  ./run.sh shadow          Show self-correction log
  ./run.sh transparency <pdf>  Visual report: screenshot + metadata + table
  ./run.sh dual <pdf>      Dual extract: Camelot + pdf_oxide in parallel
  ./run.sh status          Health check
HELP
    ;;
esac
