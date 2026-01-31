#!/usr/bin/env python3
"""
CLI for analytics skill.

Usage:
    python -m src.cli insights ~/.pi/ingest-yt-history/history.jsonl
    python -m src.cli trends ~/.pi/ingest-yt-history/history.jsonl --window 7
    python -m src.cli export ~/.pi/ingest-yt-history/history.jsonl --for-figure
"""

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.markdown import Markdown

from .insights import (
    load_data,
    load_jsonl,
    viewing_trends,
    session_analysis,
    time_patterns,
    content_evolution,
    generate_insights,
    format_for_horus,
    describe_schema,
    flexible_group_by,
    numerical_stats,
    export_chart_spec,
)

app = typer.Typer(help="Data science analytics for timestamped content")
console = Console()


@app.command()
def insights(
    path: Path = typer.Argument(..., help="Path to JSONL file"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    horus: bool = typer.Option(False, "--horus", help="Format for Horus persona"),
):
    """Generate comprehensive insights from content data."""
    try:
        result = generate_insights(path)

        if json_output:
            print(json.dumps(result, indent=2, default=str))
        elif horus:
            console.print(Markdown(format_for_horus(result)))
        else:
            console.print(Markdown(format_for_horus(result)))

    except FileNotFoundError:
        console.print(f"[red]Error: File not found: {path}[/red]")
        sys.exit(1)


@app.command()
def trends(
    path: Path = typer.Argument(..., help="Path to JSONL file"),
    window: int = typer.Option(7, "--window", "-w", help="Rolling window in days"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Analyze viewing trends over time."""
    try:
        df = load_jsonl(path)
        result = viewing_trends(df, window=window)

        if json_output:
            print(json.dumps(result, indent=2, default=str))
        else:
            table = Table(title=f"Viewing Trends (window={window} days)")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", justify="right")

            table.add_row("Daily Average", f"{result.get('daily_average', 0):.1f}")
            table.add_row("Recent Average", f"{result.get('recent_average', 0):.1f}")
            table.add_row("Trend", result.get("trend", "unknown"))
            table.add_row("Change %", f"{result.get('trend_change_pct', 0):+.1f}%")
            table.add_row("Peak Day", str(result.get("peak_day", "-")))
            table.add_row("Peak Count", str(result.get("peak_count", 0)))

            console.print(table)

    except FileNotFoundError:
        console.print(f"[red]Error: File not found: {path}[/red]")
        sys.exit(1)


@app.command()
def sessions(
    path: Path = typer.Argument(..., help="Path to JSONL file"),
    gap: int = typer.Option(30, "--gap", "-g", help="Session gap in minutes"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Detect and analyze viewing sessions."""
    try:
        df = load_jsonl(path)
        result = session_analysis(df, gap_minutes=gap)

        if json_output:
            print(json.dumps(result, indent=2, default=str))
        else:
            table = Table(title=f"Session Analysis (gap={gap} min)")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", justify="right")

            table.add_row("Total Sessions", str(result.get("total_sessions", 0)))
            table.add_row("Avg Session Length", f"{result.get('avg_session_length', 0):.1f}")
            table.add_row("Max Session", str(result.get("max_session_length", 0)))
            table.add_row("Binge Sessions (5+)", str(result.get("binge_sessions", 0)))
            table.add_row("Binge %", f"{result.get('binge_pct', 0):.1f}%")

            console.print(table)

    except FileNotFoundError:
        console.print(f"[red]Error: File not found: {path}[/red]")
        sys.exit(1)


@app.command("time-patterns")
def time_patterns_cmd(
    path: Path = typer.Argument(..., help="Path to JSONL file"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Analyze time-of-day patterns."""
    try:
        df = load_jsonl(path)
        result = time_patterns(df)

        if json_output:
            print(json.dumps(result, indent=2, default=str))
        else:
            console.print(f"[bold]Peak Hour:[/bold] {result.get('peak_hour')} ({result.get('peak_period')})")

            if result.get("music_peak_hour"):
                console.print(f"[bold]Music Peak:[/bold] {result.get('music_peak_hour')} ({result.get('music_peak_period')})")

            console.print("\n[bold]Period Distribution:[/bold]")
            for period, count in result.get("period_distribution", {}).items():
                bar = "█" * min(int(count / 100), 50)
                console.print(f"  {period:10} {count:5} {bar}")

    except FileNotFoundError:
        console.print(f"[red]Error: File not found: {path}[/red]")
        sys.exit(1)


@app.command()
def evolution(
    path: Path = typer.Argument(..., help="Path to JSONL file"),
    periods: int = typer.Option(4, "--periods", "-p", help="Number of time periods"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Track content preference evolution over time."""
    try:
        df = load_jsonl(path)
        result = content_evolution(df, periods=periods)

        if json_output:
            print(json.dumps(result, indent=2, default=str))
        else:
            if "error" in result:
                console.print(f"[yellow]{result['error']}[/yellow]")
                return

            table = Table(title=f"Content Evolution ({periods} periods)")
            table.add_column("Period")
            table.add_column("Date Range")
            table.add_column("Items", justify="right")
            table.add_column("Music %", justify="right")

            for p in result.get("periods", []):
                music_pct = f"{p.get('music_ratio_pct', 0):.1f}%" if "music_ratio_pct" in p else "-"
                table.add_row(
                    str(p["period"]),
                    f"{p['start']} to {p['end']}",
                    str(p["count"]),
                    music_pct,
                )

            console.print(table)

            if result.get("music_trend"):
                console.print(f"\n[bold]Music Trend:[/bold] {result['music_trend']} ({result.get('music_change_pct', 0):+.1f}%)")

    except FileNotFoundError:
        console.print(f"[red]Error: File not found: {path}[/red]")
        sys.exit(1)


@app.command()
def describe(
    path: Path = typer.Argument(..., help="Path to data file (JSONL, JSON, CSV)"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Discover schema and get chart recommendations.

    Analyzes data to detect column types and suggests visualizations.
    This is the first command to run on any new dataset.
    """
    try:
        df = load_data(path)
        result = describe_schema(df)

        if json_output:
            print(json.dumps(result, indent=2, default=str))
        else:
            console.print(f"\n[bold]Dataset: {path}[/bold]")
            console.print(f"Rows: {result['total_rows']:,}  |  Columns: {result['total_columns']}\n")

            # Column summary table
            table = Table(title="Schema Discovery")
            table.add_column("Column", style="cyan")
            table.add_column("Type", style="green")
            table.add_column("Semantic", style="yellow")
            table.add_column("Nulls", justify="right")
            table.add_column("Unique", justify="right")
            table.add_column("Sample/Stats")

            for col, info in result.get("columns", {}).items():
                sample = ""
                if info.get("semantic_type") == "numerical":
                    sample = f"mean={info.get('mean')}, std={info.get('std')}"
                elif info.get("semantic_type") == "categorical":
                    top = list(info.get("top_values", {}).keys())[:3]
                    sample = ", ".join(str(t) for t in top)
                elif info.get("semantic_type") == "temporal":
                    sample = f"{info.get('min', '?')} → {info.get('max', '?')}"

                table.add_row(
                    col[:20],
                    str(info.get("dtype", "?"))[:10],
                    info.get("semantic_type", "?"),
                    f"{info.get('null_pct', 0)}%",
                    str(info.get("unique_count", 0)),
                    sample[:40],
                )

            console.print(table)

            # Chart recommendations
            if result.get("recommendations"):
                console.print("\n[bold]Recommended Charts:[/bold]")
                for i, rec in enumerate(result["recommendations"][:8], 1):
                    console.print(f"  {i}. [cyan]{rec['name']}[/cyan] - {rec['description']}")
                    console.print(f"     [dim]./run.sh chart {path} --name {rec['name']}[/dim]")

    except FileNotFoundError:
        console.print(f"[red]Error: File not found: {path}[/red]")
        sys.exit(1)


@app.command("group-by")
def group_by_cmd(
    path: Path = typer.Argument(..., help="Path to data file"),
    group_col: str = typer.Option(..., "--by", "-b", help="Column to group by"),
    agg_col: Optional[str] = typer.Option(None, "--agg", "-a", help="Column to aggregate"),
    agg_func: str = typer.Option("count", "--func", "-f", help="Aggregation: count, sum, mean, min, max"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    for_figure: bool = typer.Option(False, "--for-figure", help="Export for create-figure"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file"),
):
    """Group by any column and aggregate.

    Examples:
        ./run.sh group-by data.jsonl --by channel --func count
        ./run.sh group-by data.jsonl --by category --agg price --func sum
    """
    try:
        df = load_data(path)
        result = flexible_group_by(df, group_col, agg_col, agg_func)  # type: ignore

        if "error" in result:
            console.print(f"[red]Error: {result['error']}[/red]")
            sys.exit(1)

        if json_output or for_figure:
            if for_figure:
                # Export in create-figure format
                out_data = {"metrics": result["data"]}
            else:
                out_data = result

            if output:
                output.write_text(json.dumps(out_data, indent=2))
                console.print(f"[green]Exported to {output}[/green]")
                if for_figure:
                    console.print(f"[dim]Usage: ./run.sh metrics -i {output} --type bar[/dim]")
            else:
                print(json.dumps(out_data, indent=2))
        else:
            table = Table(title=f"Group by: {group_col} ({result['aggregation']})")
            table.add_column(group_col, style="cyan")
            table.add_column(result["aggregation"], justify="right")

            for k, v in sorted(result["data"].items(), key=lambda x: -x[1])[:20]:
                table.add_row(str(k), f"{v:,.1f}" if isinstance(v, float) else str(v))

            console.print(table)
            console.print(f"\n[dim]Total groups: {result['total_groups']}[/dim]")

    except FileNotFoundError:
        console.print(f"[red]Error: File not found: {path}[/red]")
        sys.exit(1)


@app.command()
def stats(
    path: Path = typer.Argument(..., help="Path to data file"),
    columns: Optional[str] = typer.Option(None, "--columns", "-c", help="Comma-separated column names"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Compute statistics for numerical columns."""
    try:
        df = load_data(path)
        cols = columns.split(",") if columns else None
        result = numerical_stats(df, cols)

        if "error" in result:
            console.print(f"[red]Error: {result['error']}[/red]")
            sys.exit(1)

        if json_output:
            print(json.dumps(result, indent=2, default=str))
        else:
            # Stats table
            table = Table(title="Numerical Statistics")
            table.add_column("Column", style="cyan")
            table.add_column("Count", justify="right")
            table.add_column("Mean", justify="right")
            table.add_column("Std", justify="right")
            table.add_column("Min", justify="right")
            table.add_column("50%", justify="right")
            table.add_column("Max", justify="right")

            for col, s in result.get("columns", {}).items():
                table.add_row(
                    col[:15],
                    str(s["count"]),
                    f"{s['mean']:.2f}",
                    f"{s['std']:.2f}",
                    f"{s['min']:.2f}",
                    f"{s['50%']:.2f}",
                    f"{s['max']:.2f}",
                )

            console.print(table)

            # Correlation if available
            if "correlation" in result:
                console.print("\n[bold]Correlations:[/bold]")
                corr = result["correlation"]
                for col_a, row in corr.items():
                    for col_b, val in row.items():
                        if col_a < col_b and abs(val) > 0.3:
                            style = "green" if val > 0 else "red"
                            console.print(f"  {col_a} ↔ {col_b}: [{style}]{val:+.3f}[/{style}]")

    except FileNotFoundError:
        console.print(f"[red]Error: File not found: {path}[/red]")
        sys.exit(1)


@app.command()
def chart(
    path: Path = typer.Argument(..., help="Path to data file"),
    name: str = typer.Option(..., "--name", "-n", help="Chart name (from describe recommendations)"),
    x_col: Optional[str] = typer.Option(None, "--x", help="X-axis column (auto from name if not set)"),
    y_col: Optional[str] = typer.Option(None, "--y", help="Y-axis column"),
    chart_type: str = typer.Option("bar", "--type", "-t", help="Chart type: bar, line, heatmap, pie"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output JSON file"),
):
    """Generate chart spec for create-figure.

    Use 'describe' command first to see recommended charts and their names.

    Examples:
        ./run.sh describe data.jsonl  # See recommendations
        ./run.sh chart data.jsonl --name distribution_channel -o chart.json
        create-figure metrics -i chart.json --type bar
    """
    try:
        df = load_data(path)

        # If x_col not specified, try to parse from name
        if not x_col:
            # Handle common patterns: distribution_X, trend_by_X, heatmap_X_x_Y
            if name.startswith("distribution_"):
                x_col = name.replace("distribution_", "")
            elif name.startswith("trend_by_"):
                x_col = name.replace("trend_by_", "")
                chart_type = "line"
            elif "_x_" in name:
                parts = name.replace("heatmap_", "").split("_x_")
                if len(parts) == 2:
                    x_col, y_col = parts
                    chart_type = "heatmap"

        if not x_col:
            console.print("[red]Error: Could not determine x_col from name. Use --x to specify.[/red]")
            sys.exit(1)

        spec = export_chart_spec(df, name, x_col, y_col, chart_type=chart_type)

        if "error" in spec:
            console.print(f"[red]Error: {spec['error']}[/red]")
            sys.exit(1)

        if output:
            output.write_text(json.dumps(spec["data"], indent=2))
            console.print(f"[green]Exported: {output}[/green]")
            console.print(f"[dim]Usage: ./run.sh {spec['create_figure_cmd']} -i {output}[/dim]")
        else:
            print(json.dumps(spec, indent=2))

    except FileNotFoundError:
        console.print(f"[red]Error: File not found: {path}[/red]")
        sys.exit(1)


@app.command()
def export(
    path: Path = typer.Argument(..., help="Path to JSONL file"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o", help="Output directory for chart files"),
    for_figure: bool = typer.Option(False, "--for-figure", help="Export in create-figure compatible format"),
):
    """Export data for visualization with create-figure skill.

    When --for-figure is used, creates individual JSON files in create-figure's expected format:
    - hour_distribution.json - Bar chart data
    - day_distribution.json - Bar chart data
    - daily_trend.json - Line chart data (training-curves format)
    - heatmap.json - Heatmap data (nested dict format)
    """
    try:
        df = load_jsonl(path)

        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)

        charts_created = []

        # Hour distribution (bar chart) - create-figure metrics format: {"label": value}
        if "hour" in df.columns:
            hour_counts = df["hour"].value_counts().sort_index()

            if for_figure:
                # create-figure expects: {"label": value, ...}
                metrics_data = {f"Hour {h}": int(c) for h, c in hour_counts.items()}
                if output_dir:
                    chart_file = output_dir / "hour_distribution.json"
                    chart_file.write_text(json.dumps({"metrics": metrics_data}, indent=2))
                    charts_created.append(("hour_distribution.json", "metrics --type bar"))
            else:
                # Generic format
                if output_dir:
                    chart_file = output_dir / "hour_distribution.json"
                    chart_file.write_text(json.dumps({
                        "x": [str(h) for h in hour_counts.index.tolist()],
                        "y": hour_counts.tolist(),
                    }, indent=2))
                    charts_created.append(("hour_distribution.json", "bar chart"))

        # Day of week distribution (bar chart)
        if "day_of_week" in df.columns:
            day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            day_counts = df["day_of_week"].value_counts().reindex(day_order, fill_value=0)

            if for_figure:
                metrics_data = {day: int(count) for day, count in day_counts.items()}
                if output_dir:
                    chart_file = output_dir / "day_distribution.json"
                    chart_file.write_text(json.dumps({"metrics": metrics_data}, indent=2))
                    charts_created.append(("day_distribution.json", "metrics --type bar"))
            else:
                if output_dir:
                    chart_file = output_dir / "day_distribution.json"
                    chart_file.write_text(json.dumps({
                        "x": day_counts.index.tolist(),
                        "y": day_counts.tolist(),
                    }, indent=2))
                    charts_created.append(("day_distribution.json", "bar chart"))

        # Daily trend (line chart) - create-figure training-curves format: {name: {x, y}}
        if "date" in df.columns:
            daily = df.groupby("date").size()
            rolling = daily.rolling(window=7, min_periods=1).mean()

            if for_figure:
                # create-figure training-curves expects: {name: {x: [...], y: [...]}}
                trend_data = {
                    "7-day average": {
                        "x": list(range(len(rolling))),
                        "y": [round(v, 2) for v in rolling.tolist()],
                    }
                }
                if output_dir:
                    chart_file = output_dir / "daily_trend.json"
                    chart_file.write_text(json.dumps(trend_data, indent=2, default=str))
                    charts_created.append(("daily_trend.json", "training-curves"))
            else:
                if output_dir:
                    chart_file = output_dir / "daily_trend.json"
                    chart_file.write_text(json.dumps({
                        "x": [str(d) for d in rolling.index.tolist()],
                        "y": rolling.tolist(),
                    }, indent=2, default=str))
                    charts_created.append(("daily_trend.json", "line chart"))

        # Hour x Day heatmap - create-figure expects: {row: {col: value}}
        if "hour" in df.columns and "day_of_week" in df.columns:
            pivot = df.pivot_table(index="day_of_week", columns="hour", aggfunc="size", fill_value=0)
            day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            pivot = pivot.reindex(day_order)

            if for_figure:
                # create-figure heatmap expects: {row_label: {col_label: value}}
                heatmap_data = {}
                for day in pivot.index:
                    heatmap_data[day] = {str(hour): int(pivot.loc[day, hour]) for hour in pivot.columns}
                if output_dir:
                    chart_file = output_dir / "heatmap.json"
                    chart_file.write_text(json.dumps(heatmap_data, indent=2))
                    charts_created.append(("heatmap.json", "heatmap"))
            else:
                if output_dir:
                    chart_file = output_dir / "heatmap.json"
                    chart_file.write_text(json.dumps({
                        "x": [str(h) for h in pivot.columns.tolist()],
                        "y": pivot.index.tolist(),
                        "z": pivot.values.tolist(),
                    }, indent=2))
                    charts_created.append(("heatmap.json", "heatmap"))

        # Output summary
        if output_dir and charts_created:
            console.print(f"[green]Exported {len(charts_created)} chart files to {output_dir}/[/green]")
            for filename, chart_type in charts_created:
                console.print(f"  - {filename}")

            if for_figure:
                console.print("\n[dim]Usage with create-figure:[/dim]")
                for filename, cmd in charts_created:
                    console.print(f"  ./run.sh {cmd} -i {output_dir}/{filename} -o {filename.replace('.json', '.pdf')}")
        elif not output_dir:
            # Just print summary to stdout
            console.print(json.dumps({
                "total_items": len(df),
                "charts_available": [c[0] for c in charts_created] if charts_created else ["hour_distribution", "day_distribution", "daily_trend", "heatmap"],
            }, indent=2))

    except FileNotFoundError:
        console.print(f"[red]Error: File not found: {path}[/red]")
        sys.exit(1)


def main():
    app()


if __name__ == "__main__":
    main()
