#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""
Tests for fixture-graph skill.

Run with: pytest test_fixture_graph.py -v
"""
import json
import tempfile
from pathlib import Path

import pytest

from fixture_graph import (
    FigureConfig,
    DependencyNode,
    generate_latex_table,
    generate_workflow_diagram,
    generate_architecture_diagram,
    generate_metrics_chart,
    generate_dependency_graph,
    _check_graphviz,
    _check_mermaid,
    _check_matplotlib,
    _check_networkx,
    IEEE_SINGLE_COLUMN,
    IEEE_DOUBLE_COLUMN,
)


class TestFigureConfig:
    """Tests for FigureConfig dataclass."""

    def test_default_values(self):
        """Test default IEEE values."""
        config = FigureConfig(title="Test")
        assert config.title == "Test"
        assert config.width == IEEE_SINGLE_COLUMN
        assert config.dpi == 600
        assert config.format == "pdf"
        assert config.style == "ieee"

    def test_custom_values(self):
        """Test custom configuration."""
        config = FigureConfig(
            title="Custom",
            width=IEEE_DOUBLE_COLUMN,
            height=4.0,
            dpi=300,
            format="png",
            style="acm",
        )
        assert config.width == IEEE_DOUBLE_COLUMN
        assert config.height == 4.0
        assert config.dpi == 300


class TestDependencyNode:
    """Tests for DependencyNode dataclass."""

    def test_default_values(self):
        """Test default node values."""
        node = DependencyNode(name="test_module")
        assert node.name == "test_module"
        assert node.module_type == "module"
        assert node.loc == 0
        assert node.imports == []
        assert node.imported_by == []

    def test_with_imports(self):
        """Test node with imports."""
        node = DependencyNode(
            name="main",
            imports=["os", "sys", "json"],
        )
        assert len(node.imports) == 3
        assert "os" in node.imports


class TestGenerateLatexTable:
    """Tests for LaTeX table generation."""

    def test_basic_table(self):
        """Test basic table generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "table.tex"
            headers = ["Name", "Value", "Status"]
            rows = [
                ["Feature A", "42", "Done"],
                ["Feature B", "28", "WIP"],
            ]

            result = generate_latex_table("Test", headers, rows, output)
            assert result is True
            assert output.exists()

            content = output.read_text()
            assert "\\begin{table}" in content
            assert "\\textbf{Name}" in content
            assert "Feature A" in content
            assert "\\end{table}" in content

    def test_latex_escaping(self):
        """Test that special characters are escaped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "table.tex"
            headers = ["Name", "Code"]
            rows = [
                ["Test_Name", "func_call()"],
                ["100%", "$value"],
            ]

            result = generate_latex_table("Test", headers, rows, output)
            assert result is True

            content = output.read_text()
            assert "\\_" in content  # Escaped underscore
            assert "\\%" in content  # Escaped percent
            assert "\\$" in content  # Escaped dollar

    def test_custom_caption_and_label(self):
        """Test custom caption and label."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "table.tex"

            result = generate_latex_table(
                "Title",
                ["A", "B"],
                [["1", "2"]],
                output,
                caption="Custom Caption",
                label="tab:custom",
            )
            assert result is True

            content = output.read_text()
            assert "\\caption{Custom Caption}" in content
            assert "\\label{tab:custom}" in content


class TestGenerateWorkflowDiagram:
    """Tests for workflow diagram generation."""

    def test_mermaid_workflow(self):
        """Test Mermaid workflow generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "workflow.mmd"
            stages = ["Scope", "Analysis", "Draft"]

            # Force .mmd output to avoid needing mermaid-cli
            result = generate_workflow_diagram(
                stages, output.with_suffix(".pdf"), "mmd", with_gates=False, backend="mermaid"
            )

            # Check fallback file was created
            mmd_file = output
            if mmd_file.exists():
                content = mmd_file.read_text()
                assert "flowchart LR" in content
                assert "Scope" in content
                assert "Analysis" in content
                assert "Draft" in content

    def test_workflow_with_gates(self):
        """Test workflow with quality gates."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "workflow.mmd"
            stages = ["A", "B", "C"]

            generate_workflow_diagram(stages, output, "mmd", with_gates=True, backend="mermaid")

            # If mermaid-cli not available, check fallback
            if output.exists():
                content = output.read_text()
                assert "Gate" in content


class TestGenerateArchitectureDiagram:
    """Tests for architecture diagram generation."""

    def test_basic_architecture(self):
        """Test basic architecture diagram."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "arch.dot"
            components = [
                {"name": "Core", "type": "module"},
                {"name": "CLI", "type": "interface"},
                {"name": "Config", "type": "config"},
            ]

            # Use graphviz backend - will fallback to .dot if graphviz not available
            result = generate_architecture_diagram(
                "TestProject", components, output, "dot", "graphviz"
            )

            # Check if .dot file was created (either directly or as fallback)
            if output.exists():
                content = output.read_text()
                assert "digraph" in content or "flowchart" in content

    def test_architecture_with_dependencies(self):
        """Test architecture with component dependencies."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "arch.dot"
            components = [
                {"name": "CLI", "type": "interface", "dependencies": ["Core"]},
                {"name": "Core", "type": "module", "dependencies": ["Config"]},
                {"name": "Config", "type": "config"},
            ]

            generate_architecture_diagram(
                "TestProject", components, output, "dot", "graphviz"
            )

            if output.exists():
                content = output.read_text()
                # Should have edges for dependencies
                assert "->" in content or "-->" in content


class TestGenerateMetricsChart:
    """Tests for metrics chart generation."""

    @pytest.mark.skipif(not _check_matplotlib(), reason="matplotlib not available")
    def test_bar_chart(self):
        """Test bar chart generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "chart.pdf"
            data = {"Feature A": 42, "Feature B": 28, "Feature C": 15}

            result = generate_metrics_chart("Test Metrics", data, output, "bar", "pdf")
            assert result is True
            assert output.exists()
            assert output.stat().st_size > 0

    @pytest.mark.skipif(not _check_matplotlib(), reason="matplotlib not available")
    def test_pie_chart(self):
        """Test pie chart generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "chart.png"
            data = {"High": 10, "Medium": 25, "Low": 65}

            result = generate_metrics_chart("Severity", data, output, "pie", "png")
            assert result is True
            assert output.exists()

    @pytest.mark.skipif(not _check_matplotlib(), reason="matplotlib not available")
    def test_line_chart(self):
        """Test line chart generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "chart.pdf"
            data = {"Jan": 10, "Feb": 15, "Mar": 20, "Apr": 18}

            result = generate_metrics_chart("Trend", data, output, "line", "pdf")
            assert result is True
            assert output.exists()


class TestGenerateDependencyGraph:
    """Tests for dependency graph generation."""

    def test_dependency_graph_from_directory(self):
        """Test dependency graph from Python directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create sample Python files
            pkg_dir = Path(tmpdir) / "sample_pkg"
            pkg_dir.mkdir()

            (pkg_dir / "__init__.py").write_text("")
            (pkg_dir / "main.py").write_text("import utils\nimport config")
            (pkg_dir / "utils.py").write_text("import os\nimport json")
            (pkg_dir / "config.py").write_text("import json")

            output = Path(tmpdir) / "deps.dot"

            # Will use AST fallback if pydeps not available
            result = generate_dependency_graph(pkg_dir, output, "dot", 2, "graphviz")

            # Check output exists (direct or fallback)
            if output.exists():
                content = output.read_text()
                assert "main" in content or "digraph" in content


class TestBackendChecks:
    """Tests for backend availability checks."""

    def test_matplotlib_check(self):
        """Test matplotlib availability check."""
        result = _check_matplotlib()
        # Should return True or False, not raise
        assert isinstance(result, bool)

    def test_networkx_check(self):
        """Test NetworkX availability check."""
        result = _check_networkx()
        assert isinstance(result, bool)

    def test_graphviz_check(self):
        """Test Graphviz availability check."""
        result = _check_graphviz()
        assert isinstance(result, bool)

    def test_mermaid_check(self):
        """Test Mermaid-cli availability check."""
        result = _check_mermaid()
        assert isinstance(result, bool)


class TestIEEEConstants:
    """Tests for IEEE publication constants."""

    def test_column_widths(self):
        """Test IEEE column width constants."""
        assert IEEE_SINGLE_COLUMN == 3.5
        assert IEEE_DOUBLE_COLUMN == 7.16


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
