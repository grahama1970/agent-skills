"""Built-in profiler for comparing native extract-tables vs Camelot.

Profiles per-stage timings, extraction accuracy, and memory usage.
Produces structured JSON results and a markdown report with figures.

Usage:
    from extract_tables.profiler import profile_comparison
    report = profile_comparison("document.pdf", pages="all")
    print(report["markdown"])
"""
from __future__ import annotations

import json
import os
import resource
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
FIXTURES_DIR = SKILL_DIR / "tests" / "fixtures"
REPORTS_DIR = SKILL_DIR / "reports"


@dataclass
class StageTimer:
    """Track per-stage timing within a pipeline."""
    stages: dict[str, float] = field(default_factory=dict)
    _start: float = 0.0
    _current_stage: str = ""

    def start(self, name: str):
        self._current_stage = name
        self._start = time.perf_counter()

    def stop(self):
        if self._current_stage:
            self.stages[self._current_stage] = time.perf_counter() - self._start
            self._current_stage = ""

    @property
    def total(self) -> float:
        return sum(self.stages.values())


def _measure_native(pdf_path: str, pages: str = "all", strategy: str = "auto") -> dict:
    """Profile native extract-tables pipeline with per-stage timing."""
    from .pdf_bridge import get_page_count, render_page_image, extract_text_elements
    from .metrics import compute_accuracy, compute_whitespace
    from .extract_tables import read_pdf

    timer = StageTimer()
    mem_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    # Overall extraction
    timer.start("total")
    result = read_pdf(pdf_path, pages=pages, flavor=strategy)
    timer.stop()

    mem_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    # Per-stage profiling on first page
    total_pages = get_page_count(pdf_path)
    if total_pages > 0:
        timer.start("page_count")
        get_page_count(pdf_path)
        timer.stop()

        timer.start("render_page")
        img = render_page_image(pdf_path, 0)
        timer.stop()

        timer.start("extract_text")
        elements = extract_text_elements(pdf_path, 0)
        timer.stop()

        # Image processing stages (if Rust module available)
        try:
            import extract_tables_rs
            import io
            # Convert PIL to PNG bytes for Rust
            buf = io.BytesIO()
            img.convert("L").save(buf, format="PNG")
            png_bytes = buf.getvalue()

            timer.start("adaptive_threshold")
            thresh = extract_tables_rs.adaptive_threshold_image(png_bytes, 15, 0)
            timer.stop()

            timer.start("morphological_open_h")
            h_mask = extract_tables_rs.morphological_open_image(thresh, "horizontal", 15, 1)
            timer.stop()

            timer.start("morphological_open_v")
            v_mask = extract_tables_rs.morphological_open_image(thresh, "vertical", 15, 1)
            timer.stop()

            timer.start("find_contours")
            contours = extract_tables_rs.find_contours_in_image(v_mask, h_mask)
            timer.stop()

            if contours:
                timer.start("find_joints")
                joints = extract_tables_rs.find_joints(contours[0], v_mask, h_mask)
                timer.stop()

        except (ImportError, Exception):
            pass  # Rust module not available

    # Collect table-level metrics with cell content for accuracy comparison
    tables_data = []
    for t in result:
        # Extract all cell text for content comparison
        cell_texts = []
        if t._data:
            for row in t._data:
                cell_texts.extend(str(c).strip() for c in row if str(c).strip())
        tables_data.append({
            "page": t.page_number,
            "rows": t.rows,
            "cols": t.cols,
            "accuracy": t.accuracy,
            "whitespace": t.whitespace,
            "strategy": t.strategy,
            "bbox": t.bbox,
            "title": t.title,
            "cell_count": len(t.cells) if t.cells else 0,
            "cell_texts": cell_texts,
        })

    return {
        "backend": "native",
        "pdf": os.path.basename(pdf_path),
        "pages": pages,
        "table_count": len(result),
        "total_time_s": round(timer.stages.get("total", 0), 4),
        "stage_times_s": {k: round(v, 4) for k, v in timer.stages.items() if k != "total"},
        "peak_rss_kb": mem_after,
        "rss_delta_kb": mem_after - mem_before,
        "tables": tables_data,
        "strategy_history": result.strategy_history,
    }


def _measure_camelot(pdf_path: str, pages: str = "all", flavor: str = "lattice") -> Optional[dict]:
    """Profile Camelot extraction for comparison. Returns None if Camelot unavailable."""
    try:
        import camelot
    except ImportError:
        return None

    # Convert our pages format to Camelot's
    camelot_pages = pages if pages != "all" else "all"

    mem_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    start = time.perf_counter()
    try:
        tables = camelot.read_pdf(pdf_path, pages=camelot_pages, flavor=flavor)
    except Exception as e:
        return {"backend": "camelot", "error": str(e)}
    elapsed = time.perf_counter() - start

    mem_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    tables_data = []
    for t in tables:
        # Extract cell text from Camelot DataFrame for accuracy comparison
        cell_texts = []
        try:
            df = t.df
            for _, row in df.iterrows():
                cell_texts.extend(str(c).strip() for c in row if str(c).strip())
        except Exception:
            pass
        tables_data.append({
            "page": t.parsing_report.get("page", 0),
            "rows": t.shape[0],
            "cols": t.shape[1],
            "accuracy": t.accuracy,
            "whitespace": t.whitespace,
            "order": t.parsing_report.get("order", 0),
            "cell_texts": cell_texts,
        })

    return {
        "backend": "camelot",
        "pdf": os.path.basename(pdf_path),
        "pages": pages,
        "table_count": len(tables),
        "total_time_s": round(elapsed, 4),
        "peak_rss_kb": mem_after,
        "rss_delta_kb": mem_after - mem_before,
        "tables": tables_data,
    }


def _text_overlap(native_data: list, camelot_data: list) -> dict:
    """Compute text content overlap between native and Camelot results.

    Returns dict with:
    - shape_overlap_pct: % of matching table shapes
    - text_overlap_pct: % of cell texts found in both backends (Jaccard)
    - native_only_count: texts only in native
    - camelot_only_count: texts only in Camelot
    """
    result = {"shape_overlap_pct": 0.0, "text_overlap_pct": 0.0,
              "native_only_count": 0, "camelot_only_count": 0}
    if not native_data or not camelot_data:
        return result

    # Shape overlap
    n_shapes = {(t.get("rows", 0), t.get("cols", 0)) for t in native_data}
    c_shapes = {(t.get("rows", 0), t.get("cols", 0)) for t in camelot_data}
    if n_shapes and c_shapes:
        overlap = len(n_shapes & c_shapes)
        total = len(n_shapes | c_shapes)
        result["shape_overlap_pct"] = round(overlap / total * 100, 1) if total else 0.0

    # Cell-level text overlap (Jaccard similarity on non-empty cell texts)
    native_texts = set()
    for t in native_data:
        for ct in t.get("cell_texts", []):
            if ct:
                native_texts.add(ct.lower().strip())

    camelot_texts = set()
    for t in camelot_data:
        for ct in t.get("cell_texts", []):
            if ct:
                camelot_texts.add(ct.lower().strip())

    if native_texts or camelot_texts:
        intersection = native_texts & camelot_texts
        union = native_texts | camelot_texts
        result["text_overlap_pct"] = round(len(intersection) / len(union) * 100, 1) if union else 0.0
        result["native_only_count"] = len(native_texts - camelot_texts)
        result["camelot_only_count"] = len(camelot_texts - native_texts)

    return result


def profile_comparison(
    pdf_path: str,
    pages: str = "all",
    native_strategy: str = "auto",
    camelot_flavor: str = "lattice",
    runs: int = 3,
) -> dict:
    """Run A/B comparison between native and Camelot backends.

    Args:
        pdf_path: Path to PDF file
        pages: Page range
        native_strategy: Strategy for native backend
        camelot_flavor: Flavor for Camelot backend
        runs: Number of runs for timing (takes median)

    Returns:
        Dict with native_results, camelot_results, comparison, and markdown report.
    """
    pdf_path = os.path.abspath(pdf_path)

    # Multiple runs for stable timing
    native_runs = []
    for _ in range(runs):
        native_runs.append(_measure_native(pdf_path, pages, native_strategy))
    # Use median timing
    native_times = sorted(r["total_time_s"] for r in native_runs)
    native = native_runs[len(native_runs) // 2]  # Median run

    camelot = _measure_camelot(pdf_path, pages, camelot_flavor)

    # Build comparison
    comparison = {
        "pdf": os.path.basename(pdf_path),
        "native_tables": native["table_count"],
        "native_time_s": native["total_time_s"],
        "native_peak_rss_kb": native["peak_rss_kb"],
    }

    if camelot and "error" not in camelot:
        comparison.update({
            "camelot_tables": camelot["table_count"],
            "camelot_time_s": camelot["total_time_s"],
            "camelot_peak_rss_kb": camelot["peak_rss_kb"],
            "speedup": round(camelot["total_time_s"] / native["total_time_s"], 2)
                if native["total_time_s"] > 0 else float("inf"),
            "table_count_match": native["table_count"] == camelot["table_count"],
            **_text_overlap(native["tables"], camelot["tables"]),
        })
    else:
        comparison["camelot_available"] = False

    return {
        "native": native,
        "camelot": camelot,
        "comparison": comparison,
    }


def profile_suite(
    fixture_dir: Optional[str] = None,
    runs: int = 3,
) -> dict:
    """Profile all fixture PDFs and produce full comparison report.

    Returns dict with per-pdf results, summary stats, and markdown report.
    """
    if fixture_dir is None:
        fixture_dir = str(FIXTURES_DIR)

    pdfs = sorted(Path(fixture_dir).glob("*.pdf"))
    if not pdfs:
        return {"error": f"No PDFs found in {fixture_dir}"}

    results = {}
    for pdf in pdfs:
        try:
            results[pdf.name] = profile_comparison(str(pdf), pages="all", runs=runs)
        except Exception as e:
            results[pdf.name] = {"error": str(e)}

    # Summary statistics
    native_times = []
    camelot_times = []
    speedups = []
    for name, r in results.items():
        if "error" in r:
            continue
        comp = r.get("comparison", {})
        if comp.get("native_time_s"):
            native_times.append(comp["native_time_s"])
        if comp.get("camelot_time_s"):
            camelot_times.append(comp["camelot_time_s"])
        if comp.get("speedup"):
            speedups.append(comp["speedup"])

    summary = {
        "pdfs_tested": len(pdfs),
        "pdfs_succeeded": len([r for r in results.values() if "error" not in r]),
        "avg_native_time_s": round(sum(native_times) / len(native_times), 4) if native_times else None,
        "avg_camelot_time_s": round(sum(camelot_times) / len(camelot_times), 4) if camelot_times else None,
        "avg_speedup": round(sum(speedups) / len(speedups), 2) if speedups else None,
        "median_speedup": round(sorted(speedups)[len(speedups) // 2], 2) if speedups else None,
    }

    # Generate markdown report
    markdown = _generate_markdown_report(results, summary)

    # Save results
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / "profile_report.json"
    report_path.write_text(json.dumps({
        "results": {k: _make_serializable(v) for k, v in results.items()},
        "summary": summary,
    }, indent=2))

    md_path = REPORTS_DIR / "profile_report.md"
    md_path.write_text(markdown)

    # Save CSV for /analytics and /create-figure
    csv_path = REPORTS_DIR / "profile_data.csv"
    _write_csv(results, csv_path)

    return {
        "results": results,
        "summary": summary,
        "markdown": markdown,
        "report_path": str(report_path),
        "markdown_path": str(md_path),
        "csv_path": str(csv_path),
    }


def _make_serializable(obj):
    """Make nested dicts/lists JSON-serializable."""
    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_serializable(x) for x in obj]
    if isinstance(obj, float) and (obj != obj):  # NaN
        return None
    return obj


def _write_csv(results: dict, path: Path):
    """Write profiling results as CSV for downstream analysis."""
    rows = []
    for pdf_name, r in results.items():
        if "error" in r:
            continue
        comp = r.get("comparison", {})
        native = r.get("native", {})

        row = {
            "pdf": pdf_name,
            "native_tables": comp.get("native_tables", 0),
            "native_time_s": comp.get("native_time_s", 0),
            "native_peak_rss_kb": comp.get("native_peak_rss_kb", 0),
            "camelot_tables": comp.get("camelot_tables", "N/A"),
            "camelot_time_s": comp.get("camelot_time_s", "N/A"),
            "speedup": comp.get("speedup", "N/A"),
            "shape_overlap_pct": comp.get("shape_overlap_pct", "N/A"),
            "text_overlap_pct": comp.get("text_overlap_pct", "N/A"),
        }

        # Add per-stage native times
        for stage, t in native.get("stage_times_s", {}).items():
            row[f"stage_{stage}"] = t

        rows.append(row)

    if not rows:
        path.write_text("pdf,native_tables,native_time_s\n")
        return

    # Write CSV
    headers = list(rows[0].keys())
    # Collect all possible headers across all rows
    for row in rows[1:]:
        for k in row:
            if k not in headers:
                headers.append(k)

    lines = [",".join(headers)]
    for row in rows:
        lines.append(",".join(str(row.get(h, "")) for h in headers))

    path.write_text("\n".join(lines) + "\n")


def _generate_markdown_report(results: dict, summary: dict) -> str:
    """Generate markdown report with comparison tables."""
    lines = [
        "# Extract-Tables Profiler Report",
        "",
        f"**PDFs tested**: {summary['pdfs_tested']}  ",
        f"**Successful**: {summary['pdfs_succeeded']}",
        "",
    ]

    # Summary section
    lines.append("## Summary")
    lines.append("")
    if summary.get("avg_speedup"):
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Avg Native Time | {summary['avg_native_time_s']}s |")
        lines.append(f"| Avg Camelot Time | {summary['avg_camelot_time_s']}s |")
        lines.append(f"| Avg Speedup | {summary['avg_speedup']}x |")
        lines.append(f"| Median Speedup | {summary['median_speedup']}x |")
        lines.append("")
    else:
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Avg Native Time | {summary.get('avg_native_time_s', 'N/A')}s |")
        lines.append(f"| Camelot | Not available for comparison |")
        lines.append("")

    # Per-PDF comparison table
    lines.append("## Per-PDF Results")
    lines.append("")
    lines.append("| PDF | Native Tbl | Native Time | Camelot Tbl | Camelot Time | Speedup | Shape % | Text % |")
    lines.append("|-----|-----------|-------------|------------|--------------|---------|---------|--------|")

    for pdf_name, r in sorted(results.items()):
        if "error" in r:
            lines.append(f"| {pdf_name} | ERROR | {r['error'][:40]} | - | - | - | - | - |")
            continue
        comp = r.get("comparison", {})
        nt = comp.get("native_tables", "-")
        ntime = comp.get("native_time_s", "-")
        ct = comp.get("camelot_tables", "-")
        ctime = comp.get("camelot_time_s", "-")
        speedup = comp.get("speedup", "-")
        shape = comp.get("shape_overlap_pct", "-")
        text = comp.get("text_overlap_pct", "-")
        lines.append(f"| {pdf_name} | {nt} | {ntime}s | {ct} | {ctime}s | {speedup}x | {shape}% | {text}% |")

    lines.append("")

    # Per-stage timing breakdown
    lines.append("## Pipeline Stage Breakdown (First Page)")
    lines.append("")
    lines.append("| PDF | render | threshold | morph_h | morph_v | contours | joints | text |")
    lines.append("|-----|--------|-----------|---------|---------|----------|--------|------|")

    for pdf_name, r in sorted(results.items()):
        if "error" in r:
            continue
        native = r.get("native", {})
        stages = native.get("stage_times_s", {})
        render = stages.get("render_page", "-")
        thresh = stages.get("adaptive_threshold", "-")
        morph_h = stages.get("morphological_open_h", "-")
        morph_v = stages.get("morphological_open_v", "-")
        contours = stages.get("find_contours", "-")
        joints = stages.get("find_joints", "-")
        text = stages.get("extract_text", "-")
        lines.append(f"| {pdf_name} | {render}s | {thresh}s | {morph_h}s | {morph_v}s | {contours}s | {joints}s | {text}s |")

    lines.append("")

    # Native table details
    lines.append("## Native Table Details")
    lines.append("")
    for pdf_name, r in sorted(results.items()):
        if "error" in r:
            continue
        native = r.get("native", {})
        tables = native.get("tables", [])
        if not tables:
            continue
        lines.append(f"### {pdf_name}")
        lines.append("")
        lines.append("| Page | Rows | Cols | Accuracy | Strategy | Title |")
        lines.append("|------|------|------|----------|----------|-------|")
        for t in tables:
            title = (t.get("title") or "")[:40]
            lines.append(
                f"| {t.get('page', '-')} | {t.get('rows', '-')} | {t.get('cols', '-')} "
                f"| {t.get('accuracy', '-')} | {t.get('strategy', '-')} | {title} |"
            )
        lines.append("")

    # Figure generation hints
    lines.append("## Figures")
    lines.append("")
    lines.append("Generate comparison figures with:")
    lines.append("```bash")
    lines.append(f"/create-figure {REPORTS_DIR / 'profile_data.csv'} --type bar --x pdf --y native_time_s,camelot_time_s --title 'Extraction Time: Native vs Camelot'")
    lines.append(f"/create-figure {REPORTS_DIR / 'profile_data.csv'} --type bar --x pdf --y speedup --title 'Speedup Factor (Native/Camelot)'")
    lines.append("```")
    lines.append("")
    lines.append("Analyze with:")
    lines.append("```bash")
    lines.append(f"/analytics {REPORTS_DIR / 'profile_data.csv'} --question 'Compare native vs camelot extraction performance'")
    lines.append("```")
    lines.append("")

    return "\n".join(lines)
