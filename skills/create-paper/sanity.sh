#!/usr/bin/env bash
# create-paper sanity check - tests modular CLI commands
set -eo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SKILL_DIR"

echo "=== Paper Writer Sanity Check (Modular) ==="

PASS_COUNT=0
FAIL_COUNT=0

pass() {
    echo "  [PASS] $1"
    PASS_COUNT=$((PASS_COUNT + 1))
}

fail() {
    echo "  [FAIL] $1"
    FAIL_COUNT=$((FAIL_COUNT + 1))
}

warn() {
    echo "  [WARN] $1"
}

# Check SKILL.md exists
if [[ -f "$SKILL_DIR/SKILL.md" ]]; then
    pass "SKILL.md exists"
else
    fail "SKILL.md missing"
fi

# Check Python modules exist (modular structure)
MODULES=(
    "paper_writer.py"
    "config.py"
    "utils.py"
    "research.py"
    "analysis.py"
    "rag.py"
    "mimic.py"
    "citations.py"
    "critique.py"
    "compliance.py"
)

echo ""
echo "Checking modular structure..."
for module in "${MODULES[@]}"; do
    if [[ -f "$SKILL_DIR/$module" ]]; then
        # Check line count is under 500 (except config which has data)
        lines=$(wc -l < "$SKILL_DIR/$module")
        if [[ "$module" == "config.py" ]]; then
            # config.py can be larger due to data definitions
            if [[ $lines -lt 1000 ]]; then
                pass "$module exists ($lines lines)"
            else
                warn "$module is large ($lines lines)"
            fi
        else
            if [[ $lines -lt 500 ]]; then
                pass "$module exists ($lines lines)"
            else
                fail "$module exceeds 500 lines ($lines lines)"
            fi
        fi
    else
        fail "$module missing"
    fi
done

# Check backup exists
if [[ -f "$SKILL_DIR/paper_writer_monolith.py" ]]; then
    pass "paper_writer_monolith.py backup exists"
else
    warn "paper_writer_monolith.py backup missing"
fi

# Check dependent skills exist
echo ""
echo "Checking dependencies..."
SKILLS_DIR="$(dirname "$SKILL_DIR")"
for skill in assess dogpile arxiv code-review memory fixture-graph; do
    if [[ -d "$SKILLS_DIR/$skill" ]]; then
        pass "Dependency: $skill"
    else
        warn "Dependency missing: $skill (optional)"
    fi
done

# Check LaTeX is installed
if command -v pdflatex &> /dev/null; then
    pass "LaTeX (pdflatex) installed"
else
    warn "LaTeX not installed (required for compilation)"
fi

# Check uvx is available
echo ""
echo "Checking runtime..."
if ! command -v uvx &> /dev/null; then
    fail "uvx not found - install with: pip install uv"
    exit 1
fi
pass "uvx available"

# uvx command for running with dependencies
UVX_CMD="uvx --with typer"

# Check CLI help works
echo ""
echo "Testing CLI commands..."
if $UVX_CMD python paper_writer.py --help >/dev/null 2>&1; then
    pass "CLI help works"
else
    fail "CLI help failed"
fi

# Test individual commands (help only - no side effects)
COMMANDS=(
    "phrases --help"
    "templates --help"
    "disclosure --help"
    "quality --help"
    "critique --help"
    "check-citations --help"
    "weakness-analysis --help"
    "pre-submit --help"
    "sanitize --help"
    "ai-ledger --help"
    "claim-graph --help"
    "domains --help"
    "list --help"
    "workflow --help"
    "figure-presets --help"
)

for cmd in "${COMMANDS[@]}"; do
    if $UVX_CMD python paper_writer.py $cmd >/dev/null 2>&1; then
        pass "Command: $cmd"
    else
        fail "Command: $cmd"
    fi
done

# Test a few commands that produce output
echo ""
echo "Testing command output..."

if $UVX_CMD python paper_writer.py templates 2>/dev/null | grep -q "AVAILABLE TEMPLATES"; then
    pass "templates command produces output"
else
    fail "templates command output"
fi

if $UVX_CMD python paper_writer.py domains 2>/dev/null | grep -q "Command Domains"; then
    pass "domains command produces output"
else
    fail "domains command output"
fi

if $UVX_CMD python paper_writer.py workflow 2>/dev/null | grep -q "Workflow Recommendations"; then
    pass "workflow command produces output"
else
    fail "workflow command output"
fi

if $UVX_CMD python paper_writer.py phrases intro 2>/dev/null | grep -q "ACADEMIC PHRASES"; then
    pass "phrases intro command produces output"
else
    fail "phrases intro command output"
fi

if $UVX_CMD python paper_writer.py disclosure arxiv 2>/dev/null | grep -q "LLM DISCLOSURE"; then
    pass "disclosure arxiv command produces output"
else
    fail "disclosure arxiv command output"
fi

# Check for circular imports
echo ""
echo "Checking for circular imports..."
if $UVX_CMD python -c "import paper_writer" 2>/dev/null; then
    pass "No circular imports in paper_writer"
else
    fail "Circular import detected in paper_writer"
fi

if $UVX_CMD python -c "import config" 2>/dev/null; then
    pass "No circular imports in config"
else
    fail "Circular import detected in config"
fi

if $UVX_CMD python -c "import citations" 2>/dev/null; then
    pass "No circular imports in citations"
else
    fail "Circular import detected in citations"
fi

if $UVX_CMD python -c "import critique" 2>/dev/null; then
    pass "No circular imports in critique"
else
    fail "Circular import detected in critique"
fi

if $UVX_CMD python -c "import compliance" 2>/dev/null; then
    pass "No circular imports in compliance"
else
    fail "Circular import detected in compliance"
fi

# Summary
echo ""
echo "============================================"
echo "SUMMARY: $PASS_COUNT passed, $FAIL_COUNT failed"
echo "============================================"

if [[ $FAIL_COUNT -gt 0 ]]; then
    echo ""
    echo "Result: FAIL"
    exit 1
fi

echo ""
echo "Result: PASS"
