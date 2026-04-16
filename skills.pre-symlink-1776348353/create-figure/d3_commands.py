#!/usr/bin/env python3
"""
D3-only CLI commands for /create-figure.

These chart types exist only as D3 interactive HTML visualizations.
They route directly to d3_backend.render_d3() and use d3_catalog.get_viz_type()
for type validation.

Registered into the main Typer app via register_d3_commands(app).
"""

from pathlib import Path

import typer

from d3_backend import render_d3
from d3_catalog import get_viz_type


def _d3_only_command(
    viz_name: str,
    input: str,
    output: str,
    title: str,
    canvas: bool,
    discord: bool,
) -> None:
    """Shared handler for D3-only chart types."""
    viz_type = get_viz_type(viz_name)
    if not viz_type:
        typer.echo(f"[ERROR] Unknown viz type: {viz_name}", err=True)
        raise typer.Exit(1)

    input_path = Path(input)
    output_path = Path(output)

    success = render_d3(viz_name, input_path, output_path, title=title, canvas=canvas, discord=discord)
    if success:
        out = output_path.with_suffix(".html")
        typer.echo(f"Generated: {out}")
    else:
        typer.echo(f"[ERROR] D3 rendering failed for {viz_name}", err=True)
        raise typer.Exit(1)


def register_d3_commands(app: typer.Typer) -> None:
    """Register all D3-only visualization commands."""

    # --- Bar variants ---

    @app.command("stacked-bar")
    def stacked_bar(
        input: str = typer.Option(..., "--input", "-i", help="JSON file with grouped data"),
        output: str = typer.Option("stacked_bar.html", "--output", "-o", help="Output HTML file"),
        title: str = typer.Option("Stacked Bar", "--title", "-t", help="Chart title"),
        canvas: bool = typer.Option(False, "--canvas", help="5ft distance-aware responsive HTML output"),
        discord: bool = typer.Option(False, "--discord", help="Phone-optimized 500px Discord output"),
    ) -> None:
        """Generate stacked bar chart (D3). Groups stacked vertically."""
        _d3_only_command("stacked_bar", input, output, title, canvas, discord)

    @app.command("grouped-bar")
    def grouped_bar(
        input: str = typer.Option(..., "--input", "-i", help="JSON file with grouped data"),
        output: str = typer.Option("grouped_bar.html", "--output", "-o", help="Output HTML file"),
        title: str = typer.Option("Grouped Bar", "--title", "-t", help="Chart title"),
        canvas: bool = typer.Option(False, "--canvas", help="5ft distance-aware responsive HTML output"),
        discord: bool = typer.Option(False, "--discord", help="Phone-optimized 500px Discord output"),
    ) -> None:
        """Generate grouped bar chart (D3). Groups side-by-side."""
        _d3_only_command("grouped_bar", input, output, title, canvas, discord)

    @app.command("diverging-bar")
    def diverging_bar(
        input: str = typer.Option(..., "--input", "-i", help="JSON file with positive/negative values"),
        output: str = typer.Option("diverging_bar.html", "--output", "-o", help="Output HTML file"),
        title: str = typer.Option("Diverging Bar", "--title", "-t", help="Chart title"),
        canvas: bool = typer.Option(False, "--canvas", help="5ft distance-aware responsive HTML output"),
        discord: bool = typer.Option(False, "--discord", help="Phone-optimized 500px Discord output"),
    ) -> None:
        """Generate diverging bar chart (D3). Bars extend left/right from center."""
        _d3_only_command("diverging_bar", input, output, title, canvas, discord)

    @app.command("waterfall")
    def waterfall(
        input: str = typer.Option(..., "--input", "-i", help="JSON file with sequential value changes"),
        output: str = typer.Option("waterfall.html", "--output", "-o", help="Output HTML file"),
        title: str = typer.Option("Waterfall", "--title", "-t", help="Chart title"),
        canvas: bool = typer.Option(False, "--canvas", help="5ft distance-aware responsive HTML output"),
        discord: bool = typer.Option(False, "--discord", help="Phone-optimized 500px Discord output"),
    ) -> None:
        """Generate waterfall chart (D3). Shows cumulative effect of sequential values."""
        _d3_only_command("waterfall", input, output, title, canvas, discord)

    # --- Line variants ---

    @app.command("multi-line")
    def multi_line(
        input: str = typer.Option(..., "--input", "-i", help="JSON file with multiple series"),
        output: str = typer.Option("multi_line.html", "--output", "-o", help="Output HTML file"),
        title: str = typer.Option("Multi-Line", "--title", "-t", help="Chart title"),
        canvas: bool = typer.Option(False, "--canvas", help="5ft distance-aware responsive HTML output"),
        discord: bool = typer.Option(False, "--discord", help="Phone-optimized 500px Discord output"),
    ) -> None:
        """Generate multi-line chart (D3). Multiple series on same axes."""
        _d3_only_command("multi_line", input, output, title, canvas, discord)

    @app.command("slope")
    def slope(
        input: str = typer.Option(..., "--input", "-i", help="JSON file with before/after pairs"),
        output: str = typer.Option("slope.html", "--output", "-o", help="Output HTML file"),
        title: str = typer.Option("Slope Chart", "--title", "-t", help="Chart title"),
        canvas: bool = typer.Option(False, "--canvas", help="5ft distance-aware responsive HTML output"),
        discord: bool = typer.Option(False, "--discord", help="Phone-optimized 500px Discord output"),
    ) -> None:
        """Generate slope chart (D3). Compare two time points."""
        _d3_only_command("slope", input, output, title, canvas, discord)

    @app.command("sparkline")
    def sparkline(
        input: str = typer.Option(..., "--input", "-i", help="JSON file with compact time series"),
        output: str = typer.Option("sparkline.html", "--output", "-o", help="Output HTML file"),
        title: str = typer.Option("Sparkline", "--title", "-t", help="Chart title"),
        canvas: bool = typer.Option(False, "--canvas", help="5ft distance-aware responsive HTML output"),
        discord: bool = typer.Option(False, "--discord", help="Phone-optimized 500px Discord output"),
    ) -> None:
        """Generate sparkline (D3). Compact inline trend indicator."""
        _d3_only_command("sparkline", input, output, title, canvas, discord)

    # --- Area variants ---

    @app.command("stacked-area")
    def stacked_area(
        input: str = typer.Option(..., "--input", "-i", help="JSON file with stacked series data"),
        output: str = typer.Option("stacked_area.html", "--output", "-o", help="Output HTML file"),
        title: str = typer.Option("Stacked Area", "--title", "-t", help="Chart title"),
        canvas: bool = typer.Option(False, "--canvas", help="5ft distance-aware responsive HTML output"),
        discord: bool = typer.Option(False, "--discord", help="Phone-optimized 500px Discord output"),
    ) -> None:
        """Generate stacked area chart (D3). Layered area fills."""
        _d3_only_command("stacked_area", input, output, title, canvas, discord)

    @app.command("streamgraph")
    def streamgraph(
        input: str = typer.Option(..., "--input", "-i", help="JSON file with time series categories"),
        output: str = typer.Option("streamgraph.html", "--output", "-o", help="Output HTML file"),
        title: str = typer.Option("Streamgraph", "--title", "-t", help="Chart title"),
        canvas: bool = typer.Option(False, "--canvas", help="5ft distance-aware responsive HTML output"),
        discord: bool = typer.Option(False, "--discord", help="Phone-optimized 500px Discord output"),
    ) -> None:
        """Generate streamgraph (D3). Flowing organic stacked areas."""
        _d3_only_command("streamgraph", input, output, title, canvas, discord)

    @app.command("ridgeline")
    def ridgeline(
        input: str = typer.Option(..., "--input", "-i", help="JSON file with distribution series"),
        output: str = typer.Option("ridgeline.html", "--output", "-o", help="Output HTML file"),
        title: str = typer.Option("Ridgeline", "--title", "-t", help="Chart title"),
        canvas: bool = typer.Option(False, "--canvas", help="5ft distance-aware responsive HTML output"),
        discord: bool = typer.Option(False, "--discord", help="Phone-optimized 500px Discord output"),
    ) -> None:
        """Generate ridgeline plot (D3). Overlapping density distributions."""
        _d3_only_command("ridgeline", input, output, title, canvas, discord)

    @app.command("horizon")
    def horizon(
        input: str = typer.Option(..., "--input", "-i", help="JSON file with dense time series"),
        output: str = typer.Option("horizon.html", "--output", "-o", help="Output HTML file"),
        title: str = typer.Option("Horizon Chart", "--title", "-t", help="Chart title"),
        canvas: bool = typer.Option(False, "--canvas", help="5ft distance-aware responsive HTML output"),
        discord: bool = typer.Option(False, "--discord", help="Phone-optimized 500px Discord output"),
    ) -> None:
        """Generate horizon chart (D3). Compact layered area for dense time series."""
        _d3_only_command("horizon", input, output, title, canvas, discord)

    # --- Scatter variants ---

    @app.command("bubble")
    def bubble(
        input: str = typer.Option(..., "--input", "-i", help="JSON file with x, y, size fields"),
        output: str = typer.Option("bubble.html", "--output", "-o", help="Output HTML file"),
        title: str = typer.Option("Bubble Chart", "--title", "-t", help="Chart title"),
        canvas: bool = typer.Option(False, "--canvas", help="5ft distance-aware responsive HTML output"),
        discord: bool = typer.Option(False, "--discord", help="Phone-optimized 500px Discord output"),
    ) -> None:
        """Generate bubble chart (D3). Scatter with sized circles."""
        _d3_only_command("bubble", input, output, title, canvas, discord)

    @app.command("beeswarm")
    def beeswarm(
        input: str = typer.Option(..., "--input", "-i", help="JSON file with value distributions"),
        output: str = typer.Option("beeswarm.html", "--output", "-o", help="Output HTML file"),
        title: str = typer.Option("Beeswarm", "--title", "-t", help="Chart title"),
        canvas: bool = typer.Option(False, "--canvas", help="5ft distance-aware responsive HTML output"),
        discord: bool = typer.Option(False, "--discord", help="Phone-optimized 500px Discord output"),
    ) -> None:
        """Generate beeswarm plot (D3). Non-overlapping dot distribution."""
        _d3_only_command("beeswarm", input, output, title, canvas, discord)

    @app.command("dot-plot")
    def dot_plot(
        input: str = typer.Option(..., "--input", "-i", help="JSON file with categorical dot data"),
        output: str = typer.Option("dot_plot.html", "--output", "-o", help="Output HTML file"),
        title: str = typer.Option("Dot Plot", "--title", "-t", help="Chart title"),
        canvas: bool = typer.Option(False, "--canvas", help="5ft distance-aware responsive HTML output"),
        discord: bool = typer.Option(False, "--discord", help="Phone-optimized 500px Discord output"),
    ) -> None:
        """Generate dot plot (D3). Dots aligned on categorical axis."""
        _d3_only_command("dot_plot", input, output, title, canvas, discord)

    # --- Pie variant ---

    @app.command("donut")
    def donut(
        input: str = typer.Option(..., "--input", "-i", help="JSON file with {label: value} data"),
        output: str = typer.Option("donut.html", "--output", "-o", help="Output HTML file"),
        title: str = typer.Option("Donut Chart", "--title", "-t", help="Chart title"),
        canvas: bool = typer.Option(False, "--canvas", help="5ft distance-aware responsive HTML output"),
        discord: bool = typer.Option(False, "--discord", help="Phone-optimized 500px Discord output"),
    ) -> None:
        """Generate donut chart (D3). Pie with hollow center."""
        _d3_only_command("donut", input, output, title, canvas, discord)

    # --- Distribution charts ---

    @app.command("box-plot")
    def box_plot(
        input: str = typer.Option(..., "--input", "-i", help="JSON file with distribution data"),
        output: str = typer.Option("box_plot.html", "--output", "-o", help="Output HTML file"),
        title: str = typer.Option("Box Plot", "--title", "-t", help="Chart title"),
        canvas: bool = typer.Option(False, "--canvas", help="5ft distance-aware responsive HTML output"),
        discord: bool = typer.Option(False, "--discord", help="Phone-optimized 500px Discord output"),
    ) -> None:
        """Generate box plot (D3). Quartile distribution summary."""
        _d3_only_command("box_plot", input, output, title, canvas, discord)

    @app.command("violin")
    def violin(
        input: str = typer.Option(..., "--input", "-i", help="JSON file with distribution data"),
        output: str = typer.Option("violin.html", "--output", "-o", help="Output HTML file"),
        title: str = typer.Option("Violin Plot", "--title", "-t", help="Chart title"),
        canvas: bool = typer.Option(False, "--canvas", help="5ft distance-aware responsive HTML output"),
        discord: bool = typer.Option(False, "--discord", help="Phone-optimized 500px Discord output"),
    ) -> None:
        """Generate violin plot (D3). Mirrored density distribution."""
        _d3_only_command("violin", input, output, title, canvas, discord)

    @app.command("histogram")
    def histogram(
        input: str = typer.Option(..., "--input", "-i", help="JSON file with numeric values"),
        output: str = typer.Option("histogram.html", "--output", "-o", help="Output HTML file"),
        title: str = typer.Option("Histogram", "--title", "-t", help="Chart title"),
        canvas: bool = typer.Option(False, "--canvas", help="5ft distance-aware responsive HTML output"),
        discord: bool = typer.Option(False, "--discord", help="Phone-optimized 500px Discord output"),
    ) -> None:
        """Generate histogram (D3). Frequency distribution of numeric data."""
        _d3_only_command("histogram", input, output, title, canvas, discord)
