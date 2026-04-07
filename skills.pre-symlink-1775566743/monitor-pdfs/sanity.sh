#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [monitor-pdfs] Sanity Check ==="

# Check 1: Required files exist
echo "Check 1: Required files..."
for f in SKILL.md run.sh monitor_pdfs.py task_monitor_integration.py; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL: Missing $f"
        exit 1
    fi
done
echo "  All required files present"

# Check 2: uv available
if ! command -v uv &>/dev/null; then
    echo "FAIL: uv not found"
    exit 1
fi
echo "  uv available"

# Check 3: Python imports work
if python3 -c "import typer; import rich; from rich.console import Console; from rich.table import Table; from rich.panel import Panel" 2>/dev/null; then
    echo "  Python imports OK (typer, rich)"
else
    echo "FAIL: Python imports failed (typer, rich)"
    exit 1
fi

# Check 4: Monitor script is parseable
if python3 -c "import ast; ast.parse(open('$SCRIPT_DIR/monitor_pdfs.py').read())" 2>/dev/null; then
    echo "  monitor_pdfs.py parses without errors"
else
    echo "FAIL: monitor_pdfs.py has syntax errors"
    exit 1
fi

# Check 5: task_monitor_integration.py is parseable
if python3 -c "import ast; ast.parse(open('$SCRIPT_DIR/task_monitor_integration.py').read())" 2>/dev/null; then
    echo "  task_monitor_integration.py parses without errors"
else
    echo "FAIL: task_monitor_integration.py has syntax errors"
    exit 1
fi

# Check 6: Corpus path exists (non-blocking)
CORPUS="/mnt/storage12tb/extractor_corpus"
if [[ ! -d "$CORPUS" ]]; then
    echo "  SKIP: Corpus dir not found at $CORPUS (12TB storage may not be mounted)"
else
    pdf_count=$(find "$CORPUS" -maxdepth 1 -name "*.pdf" 2>/dev/null | wc -l)
    echo "  Corpus found: $pdf_count PDFs at top level"
fi

echo "Result: PASS"
