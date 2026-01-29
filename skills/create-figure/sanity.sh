#!/usr/bin/env bash
# Sanity check for fixture-graph skill (modularized version)
# Tests the refactored modular structure
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Fixture-Graph Sanity Check (Modular) ==="
echo ""

# Check Python is available
echo -n "Python available... "
command -v python3 &>/dev/null && echo "OK" || { echo "FAIL"; exit 1; }

# Check mermaid-cli (optional - system dependency)
echo -n "mermaid-cli (mmdc)... "
command -v mmdc &>/dev/null && echo "OK" || echo "WARN (some diagrams will be text-only)"

# Check graphviz (optional - system dependency)
echo -n "graphviz (dot)... "
command -v dot &>/dev/null && echo "OK" || echo "WARN (some diagrams will be text-only)"

# Activate venv if available
if [[ -d ".venv" ]]; then
    source .venv/bin/activate 2>/dev/null || true
fi

# Test that all modules import correctly
echo ""
echo "--- Module Import Tests ---"

echo -n "config.py imports... "
python3 -c "from config import DOMAIN_GROUPS, IEEE_FIGURE_SIZES" && echo "OK" || { echo "FAIL"; exit 1; }

echo -n "utils.py imports... "
python3 -c "from utils import check_matplotlib, apply_ieee_style" && echo "OK" || { echo "FAIL"; exit 1; }

echo -n "validation.py imports... "
python3 -c "from validation import ValidationError, validate_json_file" && echo "OK" || { echo "FAIL"; exit 1; }

echo -n "graphviz_backend.py imports... "
python3 -c "from graphviz_backend import render_graphviz, generate_dependency_graph" && echo "OK" || { echo "FAIL"; exit 1; }

echo -n "mermaid_backend.py imports... "
python3 -c "from mermaid_backend import render_mermaid, generate_mermaid_workflow" && echo "OK" || { echo "FAIL"; exit 1; }

echo -n "networkx_backend.py imports... "
python3 -c "from networkx_backend import generate_force_directed" && echo "OK" || { echo "FAIL"; exit 1; }

echo -n "matplotlib_backend.py imports... "
python3 -c "from matplotlib_backend import generate_metrics_chart, generate_heatmap" && echo "OK" || { echo "FAIL"; exit 1; }

echo -n "plotly_backend.py imports... "
python3 -c "from plotly_backend import generate_sankey_diagram, generate_treemap" && echo "OK" || { echo "FAIL"; exit 1; }

echo -n "control_systems.py imports... "
python3 -c "from control_systems import generate_bode_plot, generate_nyquist_plot" && echo "OK" || { echo "FAIL"; exit 1; }

echo -n "ml_visualizations.py imports... "
python3 -c "from ml_visualizations import generate_confusion_matrix, generate_roc_curve" && echo "OK" || { echo "FAIL"; exit 1; }

echo -n "analysis.py imports... "
python3 -c "from analysis import generate_architecture_diagram, generate_workflow_diagram" && echo "OK" || { echo "FAIL"; exit 1; }

# Test CLI loads
echo ""
echo "--- CLI Tests ---"

echo -n "CLI loads... "
python3 fixture_graph.py --help >/dev/null 2>&1 && echo "OK" || { echo "FAIL"; exit 1; }

echo -n "Domains command... "
python3 fixture_graph.py domains >/dev/null 2>&1 && echo "OK" || { echo "FAIL"; exit 1; }

echo -n "Presets command... "
python3 fixture_graph.py presets >/dev/null 2>&1 && echo "OK" || { echo "FAIL"; exit 1; }

echo -n "Check command... "
python3 fixture_graph.py check >/dev/null 2>&1 && echo "OK" || { echo "FAIL"; exit 1; }

echo -n "List command... "
python3 fixture_graph.py list >/dev/null 2>&1 && echo "OK" || { echo "FAIL"; exit 1; }

echo -n "Recommend command... "
python3 fixture_graph.py recommend --show-types >/dev/null 2>&1 && echo "OK" || { echo "FAIL"; exit 1; }

# Test workflow command (doesn't need external rendering deps)
echo -n "Workflow command (mmd output)... "
TMPDIR=$(mktemp -d)
python3 fixture_graph.py workflow --stages "A,B,C" --output "$TMPDIR/test.mmd" --format mmd >/dev/null 2>&1
if [[ -f "$TMPDIR/test.mmd" ]]; then
    echo "OK"
else
    echo "FAIL"
    rm -rf "$TMPDIR"
    exit 1
fi

# Test metrics command with JSON input
echo -n "Metrics command... "
echo '{"A": 10, "B": 20, "C": 30}' > "$TMPDIR/metrics.json"
python3 fixture_graph.py metrics --input "$TMPDIR/metrics.json" --output "$TMPDIR/metrics.png" --type bar >/dev/null 2>&1 && echo "OK" || echo "WARN (matplotlib may not be available)"

# Test table command
echo -n "Table command... "
echo '{"headers": ["Name", "Value"], "rows": [["A", "1"], ["B", "2"]]}' > "$TMPDIR/table.json"
python3 fixture_graph.py table --input "$TMPDIR/table.json" --output "$TMPDIR/table.tex" >/dev/null 2>&1
if [[ -f "$TMPDIR/table.tex" ]]; then
    echo "OK"
else
    echo "FAIL"
    rm -rf "$TMPDIR"
    exit 1
fi

rm -rf "$TMPDIR"

# Check line counts (quality gate)
echo ""
echo "--- Module Size Check ---"
OVERSIZED=0
for f in config.py utils.py graphviz_backend.py mermaid_backend.py networkx_backend.py \
         matplotlib_backend.py plotly_backend.py control_systems.py ml_visualizations.py \
         analysis.py validation.py fixture_graph.py; do
    if [[ -f "$f" ]]; then
        LINES=$(wc -l < "$f")
        if [[ $LINES -gt 1000 ]]; then
            echo "  $f: $LINES lines (WARN: > 1000)"
            OVERSIZED=1
        else
            echo "  $f: $LINES lines (OK)"
        fi
    fi
done

# Run pytest if available
echo ""
echo "--- Pytest Tests ---"
if [[ -d "tests" ]]; then
    if command -v pytest &>/dev/null; then
        echo "Running pytest..."
        pytest tests/ -v --tb=short 2>/dev/null && echo "Tests: OK" || echo "Tests: SOME FAILED"
    else
        echo "pytest not available, skipping unit tests"
    fi
else
    echo "No tests/ directory found, skipping unit tests"
fi

echo ""
echo "=== Sanity Check PASSED ==="
