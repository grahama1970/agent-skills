"""Rich table and JSON formatters for all corpus-report commands."""
from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.text import Text

from .models import BottleneckReport, CorpusSummary, QualityReport, TrendPoint

console = Console()

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

_LABEL_COLORS = {
    "GOOD": "green",
    "ACCEPTABLE": "yellow",
    "OVERESTIMATE": "red",
    "UNDERESTIMATE": "red",
    "SEVERE_OVERESTIMATE": "bright_red",
    "SEVERE_UNDERESTIMATE": "bright_red",
}

_STATUS_COLORS = {
    "completed": "green",
    "pending": "yellow",
    "failed": "red",
    "processing": "cyan",
}


def _color(label: str) -> str:
    return _LABEL_COLORS.get(label, "white")


def _status_color(status: str) -> str:
    return _STATUS_COLORS.get(status, "white")


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------

def emit_json(data: Any) -> None:
    """Print compact JSON to stdout."""
    console.print_json(json.dumps(data, default=str))


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def render_summary(s: CorpusSummary, *, as_json: bool = False) -> None:
    if as_json:
        emit_json({
            "total": s.total,
            "completed": s.completed,
            "pending": s.pending,
            "failed": s.failed,
            "processing": s.processing,
            "total_pages": s.total_pages,
            "total_size_mb": s.total_size_mb,
            "median_duration_sec": s.median_duration_sec,
            "categories": s.categories,
            "presets": s.presets,
            "label_distribution": s.label_distribution,
        })
        return

    # Header panel
    pct = (s.completed / s.total * 100) if s.total else 0
    bar_width = 40
    filled = int(pct / 100 * bar_width)
    bar = f"[green]{'█' * filled}[/green][dim]{'░' * (bar_width - filled)}[/dim]"

    header = Text.from_markup(
        f"[bold]Corpus:[/bold] {s.total} PDFs  "
        f"[green]{s.completed}[/green] done  "
        f"[yellow]{s.pending}[/yellow] pending  "
        f"[red]{s.failed}[/red] failed  "
        f"[cyan]{s.processing}[/cyan] active\n"
        f"{bar} {pct:.1f}%\n"
        f"[dim]{s.total_pages:,} pages · {s.total_size_mb:,.1f} MB"
        + (f" · median {s.median_duration_sec:.0f}s per PDF" if s.median_duration_sec else "")
        + "[/dim]"
    )
    console.print(Panel(header, title="Corpus Summary", border_style="blue"))

    # Categories table
    if s.categories:
        t = Table(title="Categories", show_lines=False, pad_edge=False)
        t.add_column("Category", style="bold")
        t.add_column("Count", justify="right")
        t.add_column("Share", justify="right", style="dim")
        for cat, count in s.categories.items():
            share = f"{count / s.total * 100:.1f}%" if s.total else "—"
            t.add_row(cat, str(count), share)
        console.print(t)

    # Presets table
    if s.presets:
        t = Table(title="S00 Presets", show_lines=False, pad_edge=False)
        t.add_column("Preset", style="bold")
        t.add_column("Count", justify="right")
        for preset, count in s.presets.items():
            t.add_row(preset, str(count))
        console.print(t)

    # Label distribution
    if s.label_distribution:
        t = Table(title="S00/S04 Labels", show_lines=False, pad_edge=False)
        t.add_column("Label", style="bold")
        t.add_column("Count", justify="right")
        for label, count in s.label_distribution.items():
            t.add_row(f"[{_color(label)}]{label}[/{_color(label)}]", str(count))
        console.print(t)


# ---------------------------------------------------------------------------
# Quality
# ---------------------------------------------------------------------------

def render_quality(q: QualityReport, *, as_json: bool = False) -> None:
    if as_json:
        emit_json({
            "total_with_ratio": q.total_with_ratio,
            "good_pct": q.good_pct,
            "acceptable_pct": q.acceptable_pct,
            "label_counts": q.label_counts,
            "ratio_histogram": q.ratio_histogram,
            "worst_offenders": q.worst_offenders,
        })
        return

    if q.total_with_ratio == 0:
        console.print("[dim]No entries with S00/S04 ratio data yet.[/dim]")
        return

    # Accuracy panel
    console.print(Panel(
        Text.from_markup(
            f"[bold]S00 Estimation Accuracy[/bold]  ({q.total_with_ratio} PDFs with ratio)\n"
            f"  Good   [0.8–1.2): [green]{q.good_pct}%[/green]\n"
            f"  Accept [0.5–2.0): [yellow]{q.acceptable_pct}%[/yellow]"
        ),
        border_style="green" if q.good_pct >= 60 else "yellow" if q.good_pct >= 40 else "red",
    ))

    # Ratio histogram
    max_count = max(q.ratio_histogram.values()) if q.ratio_histogram else 1
    t = Table(title="Ratio Histogram", show_lines=False, pad_edge=False)
    t.add_column("Bucket", style="bold")
    t.add_column("Count", justify="right")
    t.add_column("Bar")
    for bucket, count in q.ratio_histogram.items():
        bar_len = int(count / max_count * 30) if max_count else 0
        bar = "█" * bar_len
        t.add_row(bucket, str(count), bar)
    console.print(t)

    # Label counts
    if q.label_counts:
        t = Table(title="Labels", show_lines=False, pad_edge=False)
        t.add_column("Label", style="bold")
        t.add_column("Count", justify="right")
        for label, count in q.label_counts.items():
            t.add_row(f"[{_color(label)}]{label}[/{_color(label)}]", str(count))
        console.print(t)

    # Worst offenders
    if q.worst_offenders:
        t = Table(title="Worst Offenders (furthest from 1.0)", show_lines=False)
        t.add_column("File", style="bold", max_width=40, no_wrap=True)
        t.add_column("Ratio", justify="right")
        t.add_column("Label")
        t.add_column("Est", justify="right", style="dim")
        t.add_column("Act", justify="right", style="dim")
        t.add_column("Cat", style="dim")
        for w in q.worst_offenders:
            ratio_str = f"{w['ratio']:.2f}" if w["ratio"] is not None else "—"
            lbl = w["label"]
            t.add_row(
                w["filename"],
                ratio_str,
                f"[{_color(lbl)}]{lbl}[/{_color(lbl)}]",
                str(w["estimated"] or "—"),
                str(w["actual"] or "—"),
                w["category"] or "—",
            )
        console.print(t)


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

def render_patterns(patterns: list[dict], *, as_json: bool = False) -> None:
    if as_json:
        emit_json({"patterns": patterns})
        return

    if not patterns:
        console.print("[dim]No failure patterns recorded yet.[/dim]")
        return

    t = Table(title="Failure Patterns", show_lines=True)
    t.add_column("Pattern", style="bold", max_width=30)
    t.add_column("Count", justify="right")
    t.add_column("Files", max_width=50)
    t.add_column("First Seen", style="dim")
    t.add_column("Last Seen", style="dim")

    for p in patterns:
        files = ", ".join(p.get("files", [])[:5])
        if len(p.get("files", [])) > 5:
            files += f" (+{len(p['files']) - 5} more)"
        t.add_row(
            p.get("name", "—"),
            str(p.get("count", 0)),
            files,
            p.get("first_seen", "—"),
            p.get("last_seen", "—"),
        )
    console.print(t)


# ---------------------------------------------------------------------------
# Bottlenecks
# ---------------------------------------------------------------------------

def render_bottlenecks(report: BottleneckReport, *, as_json: bool = False) -> None:
    if as_json:
        emit_json({
            "files_sampled": report.files_sampled,
            "avg_total_ms": report.avg_total_ms,
            "stages": [
                {
                    "name": st.name,
                    "avg_ms": st.avg_ms,
                    "median_ms": st.median_ms,
                    "max_ms": st.max_ms,
                    "pct_of_total": st.pct_of_total,
                }
                for st in report.stages
            ],
        })
        return

    if not report.stages:
        console.print("[dim]No timing data found. Run pipeline on some PDFs first.[/dim]")
        return

    console.print(Panel(
        f"[bold]Pipeline Bottlenecks[/bold]  "
        f"({report.files_sampled} files sampled, avg total {report.avg_total_ms:.0f}ms)",
        border_style="blue",
    ))

    t = Table(show_lines=False)
    t.add_column("Stage", style="bold")
    t.add_column("Avg (ms)", justify="right")
    t.add_column("Median (ms)", justify="right")
    t.add_column("Max (ms)", justify="right")
    t.add_column("% Total", justify="right")
    t.add_column("Bar")

    for i, st in enumerate(report.stages):
        bar_len = int(st.pct_of_total / 100 * 30)
        color = "red" if i == 0 else "yellow" if i == 1 else "white"
        bar = f"[{color}]{'█' * bar_len}[/{color}]"
        t.add_row(
            st.name,
            f"{st.avg_ms:.0f}",
            f"{st.median_ms:.0f}",
            f"{st.max_ms:.0f}",
            f"{st.pct_of_total:.1f}%",
            bar,
        )
    console.print(t)


# ---------------------------------------------------------------------------
# Trends
# ---------------------------------------------------------------------------

def render_trends(points: list[TrendPoint], *, as_json: bool = False) -> None:
    if as_json:
        emit_json({
            "windows": [
                {
                    "label": p.window_label,
                    "count": p.count,
                    "good_pct": p.good_pct,
                    "acceptable_pct": p.acceptable_pct,
                    "median_ratio": p.median_ratio,
                    "median_duration_sec": p.median_duration_sec,
                }
                for p in points
            ],
        })
        return

    if not points:
        console.print("[dim]No completed entries with timestamps for trend analysis.[/dim]")
        return

    t = Table(title="Quality Trends", show_lines=False)
    t.add_column("Window", style="bold")
    t.add_column("Count", justify="right")
    t.add_column("Good %", justify="right")
    t.add_column("Accept %", justify="right")
    t.add_column("Med Ratio", justify="right")
    t.add_column("Med Dur (s)", justify="right", style="dim")

    for p in points:
        good_color = "green" if p.good_pct >= 60 else "yellow" if p.good_pct >= 40 else "red"
        t.add_row(
            p.window_label,
            str(p.count),
            f"[{good_color}]{p.good_pct:.1f}[/{good_color}]",
            f"{p.acceptable_pct:.1f}",
            f"{p.median_ratio:.3f}" if p.median_ratio is not None else "—",
            f"{p.median_duration_sec:.0f}" if p.median_duration_sec is not None else "—",
        )
    console.print(t)
