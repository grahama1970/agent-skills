#!/bin/bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RULES_DIR="$SKILL_DIR/rules"

case "${1:-help}" in
  list)
    echo "=== D3 Best Practice Rules ==="
    for rule in "$RULES_DIR"/*.md; do
      name=$(basename "$rule" .md)
      severity=$(grep -oP '^\*\*Severity\*\*:\s*\K\w+' "$rule" 2>/dev/null || echo "?")
      category=$(grep -oP '^\*\*Category\*\*:\s*\K[\w-]+' "$rule" 2>/dev/null || echo "?")
      printf "  %-40s  %-6s  %s\n" "$name" "$severity" "$category"
    done
    ;;
  check)
    # Grep-based check for common D3 anti-patterns in TSX/JSX files
    target="${2:-.}"
    echo "=== Checking D3 patterns in $target ==="
    violations=0

    # Check: hardcoded SVG dimensions
    if grep -rn 'append("svg")' "$target" --include="*.tsx" --include="*.ts" --include="*.jsx" 2>/dev/null | grep -E '\.attr\("(width|height)",\s*\d+\)' | grep -v viewBox; then
      echo "[ERROR] Hardcoded SVG width/height found — use viewBox"
      violations=$((violations + 1))
    fi

    # Check: mouseenter/mouseleave instead of pointer events
    if grep -rn 'mouseenter\|mouseleave\|mouseover\|mouseout' "$target" --include="*.tsx" --include="*.ts" --include="*.jsx" 2>/dev/null | grep -v "//"; then
      echo "[WARN] Mouse events found — use pointerenter/pointerleave"
      violations=$((violations + 1))
    fi

    # Check: data join without key function
    if grep -rn '\.data([^,)]*)[^,]*\.join\|\.data([^,)]*)[^,]*\.enter' "$target" --include="*.tsx" --include="*.ts" 2>/dev/null | grep -v 'd =>' | grep -v '(d)'; then
      echo "[WARN] Possible data join without key function"
      violations=$((violations + 1))
    fi

    # Check: long transitions
    if grep -rn '\.duration(\s*[0-9]\{4,\})' "$target" --include="*.tsx" --include="*.ts" 2>/dev/null; then
      echo "[WARN] Transition duration >999ms found — keep under 300ms"
      violations=$((violations + 1))
    fi

    # Check: missing aria-label on SVG
    if grep -rn '<svg' "$target" --include="*.tsx" --include="*.jsx" 2>/dev/null | grep -v 'aria-label\|role=' | head -5; then
      echo "[WARN] SVG without aria-label or role found"
      violations=$((violations + 1))
    fi

    if [[ "$violations" -eq 0 ]]; then
      echo "CLEAN: No D3 anti-patterns found"
    else
      echo ""
      echo "$violations potential violations found"
    fi
    ;;
  help|*)
    echo "best-practices-d3 — D3 visualization best practices"
    echo ""
    echo "Commands:"
    echo "  list              List all rules"
    echo "  check [path]      Check for D3 anti-patterns in TSX/TS files"
    ;;
esac
