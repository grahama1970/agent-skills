#!/usr/bin/env bash
# Sanity check for fixture-graph skill using uvx
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Fixture-Graph Sanity Check (uvx) ==="

# Check uvx is available
echo -n "uvx available... "
command -v uvx &>/dev/null && echo "OK" || { echo "FAIL (install uv: curl -LsSf https://astral.sh/uv/install.sh | sh)"; exit 1; }

# Check mermaid-cli (optional - system dependency)
echo -n "mermaid-cli (mmdc)... "
command -v mmdc &>/dev/null && echo "OK" || echo "WARN (some diagrams will be text-only)"

# Check graphviz (optional - system dependency)
echo -n "graphviz (dot)... "
command -v dot &>/dev/null && echo "OK" || echo "WARN (some diagrams will be text-only)"

# Define uvx command with all dependencies
UVX_CMD="uvx --with typer --with numpy --with matplotlib --with networkx --with pandas --with scipy --with seaborn"

# Test CLI loads
echo -n "CLI loads... "
$UVX_CMD python fixture_graph.py --help >/dev/null 2>&1 && echo "OK" || { echo "FAIL"; exit 1; }

# Test domains command (new feature)
echo -n "Domains command... "
$UVX_CMD python fixture_graph.py domains >/dev/null 2>&1 && echo "OK" || { echo "FAIL"; exit 1; }

# Test workflow command (doesn't need external deps)
echo -n "Workflow command... "
TMPDIR=$(mktemp -d)
$UVX_CMD python fixture_graph.py workflow --stages "A,B,C" --output "$TMPDIR/test.mmd" --format mmd >/dev/null 2>&1
if [[ -f "$TMPDIR/test.mmd" ]]; then
    echo "OK"
else
    echo "FAIL"
    rm -rf "$TMPDIR"
    exit 1
fi
rm -rf "$TMPDIR"

# Run tests with uvx (tests are in tests/ subdirectory)
echo -n "Running tests... "
if uvx --with typer --with numpy --with matplotlib --with networkx --with pandas --with scipy --with seaborn --with pytest \
    pytest tests/ -v --tb=short 2>/dev/null; then
    echo "OK"
else
    echo "FAIL"
    exit 1
fi

echo ""
echo "=== Sanity Check PASSED ==="
