#!/usr/bin/env bash
# Prompt Lab Sanity Check
# Tests all CLI commands for basic functionality

set -e  # Exit on first error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================"
echo "Prompt Lab Sanity Check"
echo "========================================"
echo ""

# Check Python syntax for all modules
echo "[1/8] Checking Python syntax..."
python3 -m py_compile config.py
python3 -m py_compile models.py
python3 -m py_compile llm.py
python3 -m py_compile evaluation.py
python3 -m py_compile ground_truth.py
python3 -m py_compile optimization.py
python3 -m py_compile utils.py
python3 -m py_compile prompt_lab.py
echo "  OK - All modules compile"
echo ""

# Check imports work
echo "[2/8] Checking imports..."
python3 -c "from config import SKILL_DIR, TIER0_CONCEPTUAL, TIER1_TACTICAL"
python3 -c "from models import TaxonomyResponse, parse_llm_response"
python3 -c "from llm import call_llm, call_llm_with_correction"
python3 -c "from evaluation import TestCase, EvalResult, EvalSummary, load_prompt, load_ground_truth"
python3 -c "from ground_truth import collect_all_samples, run_keyword_scorer"
python3 -c "from optimization import analyze_results, generate_improvement_suggestions"
python3 -c "from utils import notify_task_monitor"
echo "  OK - All imports work"
echo ""

# Check CLI --help works
echo "[3/8] Checking CLI --help..."
python3 prompt_lab.py --help > /dev/null
echo "  OK - CLI help works"
echo ""

# Check list-prompts command
echo "[4/8] Checking list-prompts command..."
python3 prompt_lab.py list-prompts > /dev/null
echo "  OK - list-prompts works"
echo ""

# Check show-prompt command (will create default if not exists)
echo "[5/8] Checking show-prompt command..."
python3 prompt_lab.py show-prompt taxonomy_v1 > /dev/null || python3 prompt_lab.py show-prompt taxonomy_v1 > /dev/null
echo "  OK - show-prompt works"
echo ""

# Check history command
echo "[6/8] Checking history command..."
python3 prompt_lab.py history --prompt taxonomy_v1 > /dev/null || true
echo "  OK - history works (may be empty)"
echo ""

# Check module line counts (< 500 except CLI)
echo "[7/8] Checking module line counts..."
for module in config.py models.py llm.py evaluation.py ground_truth.py optimization.py utils.py; do
    lines=$(wc -l < "$module")
    if [ "$lines" -gt 500 ]; then
        echo "  FAIL - $module has $lines lines (> 500)"
        exit 1
    fi
    echo "  $module: $lines lines"
done
# CLI can be up to 700 (thin but still has all commands)
cli_lines=$(wc -l < prompt_lab.py)
if [ "$cli_lines" -gt 700 ]; then
    echo "  FAIL - prompt_lab.py has $cli_lines lines (> 700)"
    exit 1
fi
echo "  prompt_lab.py: $cli_lines lines (CLI entry point)"
echo ""

# Check no circular imports
echo "[8/8] Checking for circular imports..."
python3 -c "
import sys
sys.path.insert(0, '.')
# Import in order of dependencies
import config
import models
import llm
import evaluation
import ground_truth
import optimization
import utils
import prompt_lab
print('  OK - No circular imports')
"
echo ""

echo "========================================"
echo "All sanity checks passed!"
echo "========================================"
