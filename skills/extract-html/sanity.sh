#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [extract-html] Sanity Check ==="

# Check 1: Required files exist
echo -n "Check 1 - Required files: "
FAIL=0
for f in SKILL.md run.sh pyproject.toml; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL: missing $f"
        FAIL=1
    fi
done
if [[ ! -d "$SCRIPT_DIR/extract_html" ]]; then
    echo "FAIL: missing extract_html/ package directory"
    FAIL=1
fi
[[ $FAIL -eq 0 ]] && echo "PASS"
[[ $FAIL -ne 0 ]] && exit 1

# Check 2: uv available
echo -n "Check 2 - uv available: "
if command -v uv &>/dev/null; then
    echo "PASS"
else
    echo "FAIL: uv not found"
    exit 1
fi

# Check 3: Python syntax check on all .py files
echo -n "Check 3 - Python syntax: "
PY_FAIL=0
for py in "$SCRIPT_DIR"/extract_html/*.py; do
    if [[ -f "$py" ]]; then
        if ! python3 -m py_compile "$py" 2>/dev/null; then
            echo "FAIL: syntax error in $(basename "$py")"
            PY_FAIL=1
        fi
    fi
done
[[ $PY_FAIL -eq 0 ]] && echo "PASS"
[[ $PY_FAIL -ne 0 ]] && exit 1

# Check 4: Core dependencies via uv
echo -n "Check 4 - Core imports (via uv): "
uv run --project "$SCRIPT_DIR" python -c "
import typer
import rich
from loguru import logger
import httpx
import bs4
import lxml
import jsonschema
import pandas
print('PASS')
" || { echo "FAIL: dependency import failed"; exit 1; }

# Check 5: Package internal imports (add skill dir to PYTHONPATH so extract_html is importable)
echo -n "Check 5 - Package imports: "
PYTHONPATH="$SCRIPT_DIR:${PYTHONPATH:-}" uv run --project "$SCRIPT_DIR" python -c "
from extract_html.util import read_json_file, read_text_file
from extract_html.cleaning import clean_html, CleaningMode
from extract_html.validate import validate_or_errors
from extract_html.normalize import normalize_text, NormMode
from extract_html.sectionify import build_section_hierarchy
from extract_html.tables import extract_html_tables_to_json
from extract_html.media import MediaItem
from extract_html.extract import TrafilaturaResult, extract_trafilatura
from extract_html.schematron import schematron_extract_json
from extract_html.pipeline import run_pipeline
from extract_html.cli import app
print('PASS')
" || { echo "FAIL: package import error"; exit 1; }

# Check 6: CLI help smoke test
echo -n "Check 6 - CLI help: "
if PYTHONPATH="$SCRIPT_DIR:${PYTHONPATH:-}" uv run --project "$SCRIPT_DIR" python -m extract_html.cli --help >/dev/null 2>&1; then
    echo "PASS"
else
    echo "WARN: CLI help failed (non-critical)"
fi

# Check 7: YAML frontmatter
echo -n "Check 7 - SKILL.md frontmatter: "
if head -1 "$SCRIPT_DIR/SKILL.md" | grep -q '^---'; then
    echo "PASS"
else
    echo "FAIL: SKILL.md missing YAML frontmatter"
    exit 1
fi

echo ""
echo "SKIP: Full conversion test (requires Ollama with schematron-3b model)"
echo "SKIP: Vision API test (requires API key)"
echo ""
echo "Result: PASS"
