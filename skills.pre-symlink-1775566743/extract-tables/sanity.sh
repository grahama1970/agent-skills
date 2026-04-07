#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
ERRORS=0
WARNINGS=0

echo "=== /extract-tables sanity check ==="
echo ""

# --- Critical checks (exit non-zero if any fail) ---

echo "--- Critical: pdf_oxide ---"
if python3 "$SKILL_DIR/sanity/check_pdf_oxide.py"; then
  :
else
  echo "[FAIL] sanity/check_pdf_oxide.py"
  ERRORS=$((ERRORS + 1))
fi

echo ""
echo "--- Critical: polars ---"
if python3 "$SKILL_DIR/sanity/check_polars.py"; then
  :
else
  echo "[FAIL] sanity/check_polars.py"
  ERRORS=$((ERRORS + 1))
fi

# --- Best-effort checks (warn but don't fail) ---

echo ""
echo "--- Best-effort: maturin (Rust build) ---"
if bash "$SKILL_DIR/sanity/maturin.sh" 2>&1; then
  :
else
  echo "[WARN] sanity/maturin.sh failed (best-effort)"
  WARNINGS=$((WARNINGS + 1))
fi

echo ""
echo "--- Best-effort: mypyc ---"
if bash "$SKILL_DIR/sanity/mypyc.sh" 2>&1; then
  :
else
  echo "[WARN] sanity/mypyc.sh failed (best-effort)"
  WARNINGS=$((WARNINGS + 1))
fi

echo ""
echo "--- Best-effort: imageproc (Rust tests) ---"
if [ -f "$SKILL_DIR/src/rust/Cargo.toml" ]; then
  if cd "$SKILL_DIR/src/rust" && cargo test --lib sanity_imageproc 2>&1; then
    echo "[PASS] imageproc Rust tests"
  else
    echo "[WARN] imageproc Rust tests failed (best-effort)"
    WARNINGS=$((WARNINGS + 1))
  fi
else
  echo "[WARN] Rust crate not scaffolded yet"
  WARNINGS=$((WARNINGS + 1))
fi

echo ""
echo "--- Graceful: scillm VLM ---"
python3 "$SKILL_DIR/sanity/scillm_vlm.py"

# --- Structure checks ---

echo ""
echo "--- Structure ---"
[ -f "$SKILL_DIR/SKILL.md" ] && echo "[PASS] SKILL.md exists" || { echo "[FAIL] SKILL.md missing"; ERRORS=$((ERRORS + 1)); }
[ -f "$SKILL_DIR/src/python/extract_tables.py" ] && echo "[PASS] extract_tables.py exists" || { echo "[FAIL] extract_tables.py missing"; ERRORS=$((ERRORS + 1)); }
[ -f "$SKILL_DIR/src/rust/Cargo.toml" ] && echo "[PASS] Rust Cargo.toml exists" || echo "[WARN] Rust crate not yet scaffolded"
[ -d "$SKILL_DIR/tests/fixtures" ] && echo "[PASS] tests/fixtures/ exists" || echo "[WARN] tests/fixtures/ missing"

FIXTURE_COUNT=$(ls "$SKILL_DIR/tests/fixtures/"*.pdf 2>/dev/null | wc -l)
echo "[INFO] $FIXTURE_COUNT PDF fixtures available"

echo ""
echo "========================================"
if [ $ERRORS -eq 0 ]; then
  echo "Sanity: PASS ($ERRORS errors, $WARNINGS warnings)"
  exit 0
else
  echo "Sanity: FAIL ($ERRORS errors, $WARNINGS warnings)"
  exit 1
fi
