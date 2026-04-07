#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [prototype-react-iterate] Sanity Check ==="

ERRORS=0
WARNINGS=0

# --- Required files ---
for f in SKILL.md run.sh; do
  if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
    echo "FAIL: Missing required file: $f"
    ERRORS=$((ERRORS + 1))
  else
    echo "OK: $f exists"
  fi
done

# --- run.sh is executable ---
if [[ -f "$SCRIPT_DIR/run.sh" && ! -x "$SCRIPT_DIR/run.sh" ]]; then
  echo "FAIL: run.sh is not executable"
  ERRORS=$((ERRORS + 1))
else
  echo "OK: run.sh is executable"
fi

# --- run.sh shows usage on no args ---
if [[ -x "$SCRIPT_DIR/run.sh" ]]; then
  usage_output=$("$SCRIPT_DIR/run.sh" 2>&1 || true)
  if echo "$usage_output" | grep -qi "usage"; then
    echo "OK: run.sh prints usage"
  else
    echo "WARN: run.sh does not print usage on no-args"
    WARNINGS=$((WARNINGS + 1))
  fi
fi

# --- Check scripts directory ---
if [[ -d "$SCRIPT_DIR/scripts" ]]; then
  echo "OK: scripts/ directory exists"
  # Check individual scripts
  for script in scripts/create.mjs scripts/simulate_user.py scripts/iterate.mjs scripts/loop.sh; do
    if [[ ! -f "$SCRIPT_DIR/$script" ]]; then
      echo "WARN: Missing script: $script (referenced by run.sh)"
      WARNINGS=$((WARNINGS + 1))
    else
      echo "OK: $script exists"
    fi
  done
  # Python syntax check on any .py files
  for pyfile in "$SCRIPT_DIR"/scripts/*.py; do
    if [[ -f "$pyfile" ]]; then
      fname="$(basename "$pyfile")"
      if python3 -c "import ast; ast.parse(open('$pyfile').read())" 2>/dev/null; then
        echo "OK: scripts/$fname parses"
      else
        echo "FAIL: scripts/$fname has syntax errors"
        ERRORS=$((ERRORS + 1))
      fi
    fi
  done
else
  echo "WARN: scripts/ directory missing (run.sh references scripts/*)"
  WARNINGS=$((WARNINGS + 1))
fi

# --- Node.js available ---
if command -v node &>/dev/null; then
  echo "OK: node available ($(node --version))"
else
  echo "WARN: node not found (needed for create.mjs / iterate.mjs)"
  WARNINGS=$((WARNINGS + 1))
fi

# --- Python3 available ---
if command -v python3 &>/dev/null; then
  echo "OK: python3 available ($(python3 --version 2>&1))"
else
  echo "FAIL: python3 not found"
  ERRORS=$((ERRORS + 1))
fi

# --- SKILL.md frontmatter check ---
if [[ -f "$SCRIPT_DIR/SKILL.md" ]]; then
  if head -1 "$SCRIPT_DIR/SKILL.md" | grep -q "^---"; then
    echo "OK: SKILL.md has YAML frontmatter"
  else
    echo "WARN: SKILL.md missing YAML frontmatter"
    WARNINGS=$((WARNINGS + 1))
  fi
fi

# --- Summary ---
echo ""
echo "Errors: $ERRORS | Warnings: $WARNINGS"
if [[ $ERRORS -gt 0 ]]; then
  echo "Result: FAIL"
  exit 1
fi
echo "Result: PASS"
