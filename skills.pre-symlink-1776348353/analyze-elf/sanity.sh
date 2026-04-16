#!/usr/bin/env bash
# Sanity check for /analyze-elf skill.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ERRORS=0

echo "=== analyze-elf sanity check ==="

# 1. SKILL.md frontmatter
if ! head -1 "$SCRIPT_DIR/SKILL.md" | grep -q '^---$'; then
    echo "FAIL: SKILL.md missing frontmatter"
    ERRORS=$((ERRORS + 1))
else
    echo "PASS: SKILL.md frontmatter"
fi

# 2. run.sh executable
if [ ! -x "$SCRIPT_DIR/run.sh" ]; then
    echo "FAIL: run.sh not executable"
    ERRORS=$((ERRORS + 1))
else
    echo "PASS: run.sh executable"
fi

# 3. Python imports
if uv run --project "$SCRIPT_DIR" python -c "from elftools.elf.elffile import ELFFile; import typer; from loguru import logger" 2>/dev/null; then
    echo "PASS: Python imports"
else
    echo "FAIL: Python imports"
    ERRORS=$((ERRORS + 1))
fi

# 4. Module structure (two-file split)
for mod in elf_parser.py feature_extractor.py analyze_elf.py; do
    if [ -f "$SCRIPT_DIR/$mod" ]; then
        echo "PASS: $mod exists"
    else
        echo "FAIL: $mod missing"
        ERRORS=$((ERRORS + 1))
    fi
done

# 5. CLI --help
if uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/analyze_elf.py" --help >/dev/null 2>&1; then
    echo "PASS: CLI --help"
else
    echo "FAIL: CLI --help"
    ERRORS=$((ERRORS + 1))
fi

# 6. features --help
if uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/analyze_elf.py" features --help >/dev/null 2>&1; then
    echo "PASS: features --help"
else
    echo "FAIL: features --help"
    ERRORS=$((ERRORS + 1))
fi

# 7. binutils
for tool in readelf nm strings; do
    if command -v "$tool" &>/dev/null; then
        echo "PASS: $tool available"
    else
        echo "FAIL: $tool not found"
        ERRORS=$((ERRORS + 1))
    fi
done

# 8. Quick ELF parse of /usr/bin/ls
if uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/analyze_elf.py" elf /usr/bin/ls >/dev/null 2>&1; then
    echo "PASS: elf /usr/bin/ls"
else
    echo "FAIL: elf /usr/bin/ls"
    ERRORS=$((ERRORS + 1))
fi

# 9. Line counts (800 limit)
for pyfile in "$SCRIPT_DIR"/*.py; do
    LINES=$(wc -l < "$pyfile")
    BASENAME=$(basename "$pyfile")
    if [ "$LINES" -le 800 ]; then
        echo "PASS: $BASENAME ($LINES lines)"
    else
        echo "FAIL: $BASENAME ($LINES lines > 800)"
        ERRORS=$((ERRORS + 1))
    fi
done

echo ""
if [ "$ERRORS" -eq 0 ]; then
    echo "ALL CHECKS PASSED"
else
    echo "FAILED: $ERRORS check(s)"
fi
exit "$ERRORS"
