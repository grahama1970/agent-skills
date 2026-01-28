#!/usr/bin/env bash
# paper-writer sanity check - uses uvx for isolation
set -eo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SKILL_DIR"

echo "=== Paper Writer Sanity Check ==="

# Check SKILL.md exists
if [[ -f "$SKILL_DIR/SKILL.md" ]]; then
    echo "  [PASS] SKILL.md exists"
else
    echo "  [FAIL] SKILL.md missing"
    exit 1
fi

# Check Python script exists
if [[ -f "$SKILL_DIR/paper_writer.py" ]]; then
    echo "  [PASS] paper_writer.py exists"
else
    echo "  [FAIL] paper_writer.py missing"
    exit 1
fi

# Check dependent skills exist
SKILLS_DIR="$(dirname "$SKILL_DIR")"
for skill in assess dogpile arxiv code-review memory fixture-graph; do
    if [[ -d "$SKILLS_DIR/$skill" ]]; then
        echo "  [PASS] Dependency: $skill"
    else
        echo "  [WARN] Dependency missing: $skill (optional)"
    fi
done

# Check LaTeX is installed
if command -v pdflatex &> /dev/null; then
    echo "  [PASS] LaTeX (pdflatex) installed"
else
    echo "  [WARN] LaTeX not installed (required for compilation)"
fi

# Check uvx is available
if ! command -v uvx &> /dev/null; then
    echo "  [FAIL] uvx not found - install with: pip install uv"
    exit 1
fi
echo "  [PASS] uvx available"

# uvx command for running with dependencies
UVX_CMD="uvx --with typer"

# Check CLI help works
if $UVX_CMD python paper_writer.py --help >/dev/null 2>&1; then
    echo "  [PASS] CLI help works"
else
    echo "  [FAIL] CLI help failed"
    exit 1
fi

# Check templates directory
if [[ -d "$SKILL_DIR/templates" ]]; then
    echo "  [PASS] templates directory exists"
else
    echo "  [WARN] templates directory missing (will be created)"
fi

# Run tests with uvx
echo ""
echo "Running tests..."
TEST_DIR="$SKILL_DIR"
[[ -d "$SKILL_DIR/tests" ]] && TEST_DIR="$SKILL_DIR/tests"

if uvx --with typer --with pytest pytest "$TEST_DIR" -v --tb=short 2>/dev/null; then
    echo "  [PASS] All tests passed"
else
    echo "  [FAIL] Some tests failed"
    exit 1
fi

echo ""
echo "Result: PASS"
