"""Typer CLI for corpus-report.  Five commands, all fast."""
from __future__ import annotations

from typing import Optional

import typer

from .config import CORPUS_ROOT, MANIFEST_PATH, PATTERN_REGISTRY_PATH, RESULTS_DIR
from .formatters import (
    render_bottlenecks,
    render_patterns,
    render_quality,
    render_summary,
    render_trends,
)
from .manifest import (
    compute_quality,
    compute_summary,
    compute_trends,
    filter_entries,
    load_manifest,
)
from loguru import logger
from .patterns import analyze_patterns, load_pattern_registry
from .timings import aggregate_timings, scan_timings

# Memory + Taxonomy integration (graceful degradation)
_HAS_MEMORY_INTEGRATION = False
try:
    import sys as _sys
    from pathlib import Path as _Path
    _mi_path = str(_Path(__file__).parent.parent)
    if _mi_path not in _sys.path:
        _sys.path.insert(0, _mi_path)
    from memory_integration import recall_prior_reports, learn_report
    _HAS_MEMORY_INTEGRATION = True
except ImportError:
    pass

app = typer.Typer(
    name="corpus-report",
    help="Extractor corpus statistics and quality analysis.",
    add_completion=False,
)


# ---------------------------------------------------------------------------
# Common options
# ---------------------------------------------------------------------------

JsonOpt = typer.Option(False, "--json", help="Machine-readable JSON output")
CategoryOpt = typer.Option(None, "--category", help="Filter by PDF category")


# ---------------------------------------------------------------------------
# summary (default)
# ---------------------------------------------------------------------------

@app.command()
def summary(
    json_out: bool = JsonOpt,
    category: Optional[str] = CategoryOpt,
) -> None:
    """Quick corpus stats: counts, categories, presets, label distribution."""
    # Pre-hook: Recall prior reports for trend comparison
    if _HAS_MEMORY_INTEGRATION:
        try:
            prior = recall_prior_reports(k=3)
            if prior:
                logger.info(
                    f"Recalled prior report context ({len(prior)} chars)"
                )
        except Exception as e:
            logger.debug("import failed: {}", e)

    entries = load_manifest(MANIFEST_PATH)
    if category:
        entries = filter_entries(entries, category=category)
    s = compute_summary(entries)
    render_summary(s, as_json=json_out)

    # Post-hook: Learn report snapshot
    if _HAS_MEMORY_INTEGRATION:
        try:
            learn_report(
                total_pdfs=s.get("total", 0) if isinstance(s, dict) else getattr(s, "total", 0),
                success_rate=s.get("completed", 0) / max(s.get("total", 1), 1) if isinstance(s, dict) else getattr(s, "completed", 0) / max(getattr(s, "total", 1), 1),
                failure_patterns=[],
                top_issues=[],
                category_breakdown=s.get("categories", {}) if isinstance(s, dict) else getattr(s, "categories", {}),
            )
        except Exception as e:
            logger.debug("value lookup failed: {}", e)


# ---------------------------------------------------------------------------
# quality
# ---------------------------------------------------------------------------

@app.command()
def quality(
    json_out: bool = JsonOpt,
    category: Optional[str] = CategoryOpt,
) -> None:
    """S00/S04 ratio analysis, label distribution, worst offenders."""
    entries = load_manifest(MANIFEST_PATH)
    if category:
        entries = filter_entries(entries, category=category)
    q = compute_quality(entries)
    render_quality(q, as_json=json_out)


# ---------------------------------------------------------------------------
# patterns
# ---------------------------------------------------------------------------

@app.command()
def patterns(
    json_out: bool = JsonOpt,
    category: Optional[str] = CategoryOpt,
) -> None:
    """Failure pattern frequency, affected files, categories."""
    registry = load_pattern_registry(PATTERN_REGISTRY_PATH)
    entries = load_manifest(MANIFEST_PATH)
    if category:
        entries = filter_entries(entries, category=category)
    result = analyze_patterns(registry, entries)
    render_patterns(result, as_json=json_out)


# ---------------------------------------------------------------------------
# bottlenecks
# ---------------------------------------------------------------------------

@app.command()
def bottlenecks(
    json_out: bool = JsonOpt,
    sample: Optional[int] = typer.Option(None, "--sample", help="Limit result dirs scanned"),
) -> None:
    """Pipeline stage timing analysis (scans result directories)."""
    raw = scan_timings(RESULTS_DIR, sample=sample)
    report = aggregate_timings(raw)
    render_bottlenecks(report, as_json=json_out)


# ---------------------------------------------------------------------------
# trends
# ---------------------------------------------------------------------------

@app.command()
def trends(
    json_out: bool = JsonOpt,
    category: Optional[str] = CategoryOpt,
    since: Optional[float] = typer.Option(None, "--since", help="Only PDFs finished in last N hours"),
    window: float = typer.Option(6.0, "--window", help="Time window grouping size in hours"),
) -> None:
    """Quality metrics over time windows."""
    entries = load_manifest(MANIFEST_PATH)
    entries = filter_entries(entries, category=category, since_hours=since)
    points = compute_trends(entries, window_hours=window)
    render_trends(points, as_json=json_out)


# ---------------------------------------------------------------------------
# __main__ entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()
