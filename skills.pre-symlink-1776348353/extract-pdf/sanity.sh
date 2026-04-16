#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PDF_OXIDE_ROOT="${PDF_OXIDE_ROOT:-$HOME/workspace/experiments/pdf_oxide}"
ERRORS=0
WARNINGS=0

echo "=== /extract-pdf sanity check ==="
echo ""

# --- Critical checks (exit non-zero if any fail) ---

echo "--- Critical: pdf_oxide importable ---"
if uv run --directory "$PDF_OXIDE_ROOT" python -c "
from pdf_oxide import PdfDocument
print('[PASS] pdf_oxide.PdfDocument importable')
" 2>/dev/null; then
  :
else
  echo "[FAIL] Cannot import pdf_oxide.PdfDocument"
  ERRORS=$((ERRORS + 1))
fi

echo ""
echo "--- Critical: extract_document available ---"
if uv run --directory "$PDF_OXIDE_ROOT" python -c "
from pdf_oxide import PdfDocument
assert 'extract_document' in dir(PdfDocument), 'extract_document missing'
print('[PASS] extract_document() method exists')
" 2>/dev/null; then
  :
else
  echo "[FAIL] extract_document() not available on PdfDocument"
  ERRORS=$((ERRORS + 1))
fi

echo ""
echo "--- Critical: survey_document available ---"
if uv run --directory "$PDF_OXIDE_ROOT" python -c "
from pdf_oxide.survey import survey_document
print('[PASS] survey_document importable')
" 2>/dev/null; then
  :
else
  echo "[FAIL] Cannot import survey_document"
  ERRORS=$((ERRORS + 1))
fi

echo ""
echo "--- Critical: CLI entry point ---"
if PYTHONPATH="$SKILL_DIR:${PYTHONPATH:-}" uv run --directory "$PDF_OXIDE_ROOT" python -c "
from extract_pdf.main import app
print('[PASS] extract_pdf.main.app importable')
" 2>/dev/null; then
  :
else
  echo "[FAIL] Cannot import extract_pdf CLI (extract_pdf.main)"
  ERRORS=$((ERRORS + 1))
fi

echo ""
echo "--- Critical: pipeline_adapter importable ---"
if PYTHONPATH="$SKILL_DIR:${PYTHONPATH:-}" uv run --directory "$PDF_OXIDE_ROOT" python -c "
from extract_pdf.pipeline_adapter import run_pipeline_adapter
print('[PASS] pipeline_adapter.run_pipeline_adapter importable')
" 2>/dev/null; then
  :
else
  echo "[FAIL] Cannot import pipeline_adapter"
  ERRORS=$((ERRORS + 1))
fi

echo ""
echo "--- Critical: build_flat_sections available ---"
if uv run --directory "$PDF_OXIDE_ROOT" python -c "
from pdf_oxide import PdfDocument
assert 'build_flat_sections' in dir(PdfDocument), 'build_flat_sections missing'
print('[PASS] build_flat_sections() method exists')
" 2>/dev/null; then
  :
else
  echo "[FAIL] build_flat_sections() not available on PdfDocument"
  ERRORS=$((ERRORS + 1))
fi

# --- Best-effort checks ---

echo ""
echo "--- Best-effort: Rust tests ---"
if [ -f "$PDF_OXIDE_ROOT/Cargo.toml" ]; then
  TEST_COUNT=$(cd "$PDF_OXIDE_ROOT" && cargo test --lib -- --list 2>/dev/null | grep -c "test$" || echo "0")
  echo "[INFO] $TEST_COUNT Rust lib tests available"
else
  echo "[WARN] Cargo.toml not found at PDF_OXIDE_ROOT"
  WARNINGS=$((WARNINGS + 1))
fi

echo ""
echo "--- Best-effort: Python tests ---"
if [ -d "$PDF_OXIDE_ROOT/python/pdf_oxide/tests" ]; then
  TEST_COUNT=$(uv run --directory "$PDF_OXIDE_ROOT" python -m pytest --collect-only -q "$PDF_OXIDE_ROOT/python/pdf_oxide/tests" 2>/dev/null | tail -1 || echo "0 tests")
  echo "[INFO] $TEST_COUNT"
else
  echo "[WARN] Python test directory not found"
  WARNINGS=$((WARNINGS + 1))
fi

# --- Structure checks ---

echo ""
echo "--- Structure ---"
[ -f "$SKILL_DIR/SKILL.md" ] && echo "[PASS] SKILL.md exists" || { echo "[FAIL] SKILL.md missing"; ERRORS=$((ERRORS + 1)); }
[ -f "$SKILL_DIR/run.sh" ] && echo "[PASS] run.sh exists" || { echo "[FAIL] run.sh missing"; ERRORS=$((ERRORS + 1)); }
[ -d "$PDF_OXIDE_ROOT/src" ] && echo "[PASS] Rust src/ exists at PDF_OXIDE_ROOT" || echo "[WARN] Rust src/ not found"
[ -d "$PDF_OXIDE_ROOT/python/pdf_oxide" ] && echo "[PASS] Python package exists at PDF_OXIDE_ROOT" || echo "[WARN] Python package not found"

echo ""
echo "========================================"
if [ $ERRORS -eq 0 ]; then
  echo "Sanity: PASS ($ERRORS errors, $WARNINGS warnings)"
  exit 0
else
  echo "Sanity: FAIL ($ERRORS errors, $WARNINGS warnings)"
  exit 1
fi
