#!/usr/bin/env python3
"""Stratified corpus benchmark for /extract-tables parity validation.

Samples PDFs across categories and size ranges from the 12TB corpus,
runs 2-way evidence matrix (no VLM cost), and produces statistical
parity report.

Usage:
    cd ~/.claude/skills/extract-tables/src
    python -m python.corpus_benchmark --sample 200 --output /tmp/parity_benchmark
    python -m python.corpus_benchmark --sample 50 --quick  # fast smoke test
    python -m python.corpus_benchmark --resume /tmp/parity_benchmark  # resume interrupted run
"""
from __future__ import annotations

import json
import random
import sys
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

import typer

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SKILL_DIR / "src"))

CORPUS_ROOT = Path("/mnt/storage12tb/extractor_corpus")

# Category definitions with relative importance weights
CATEGORIES = {
    "arxiv": {"path": "arxiv", "weight": 3, "desc": "Academic papers with complex tables"},
    "defense": {"path": "defense", "weight": 3, "desc": "Defense/military standards"},
    "nasa": {"path": "nasa", "weight": 2, "desc": "NASA technical reports"},
    "ietf": {"path": "ietf", "weight": 2, "desc": "IETF RFCs and standards"},
    "nist": {"path": "nist", "weight": 3, "desc": "NIST standards (high-value)"},
    "archive_org": {"path": "archive_org", "weight": 1, "desc": "Archive.org documents"},
    "fetcher_results": {"path": "fetcher_results", "weight": 2, "desc": "Web-fetched documents"},
    "inbox": {"path": "inbox", "weight": 2, "desc": "Mixed inbox documents"},
    "stress_test": {"path": "stress_test_pdfs", "weight": 2, "desc": "Known-difficult PDFs"},
    "industry": {"path": "industry", "weight": 2, "desc": "Industry standards"},
    "engineering": {"path": "engineering", "weight": 2, "desc": "Engineering documents"},
    "adversarial": {"path": "adversarial", "weight": 3, "desc": "Adversarial edge cases"},
    "edge_cases": {"path": "edge_cases", "weight": 3, "desc": "Known edge cases"},
    "government": {"path": "government", "weight": 2, "desc": "Government documents"},
    "faa": {"path": "faa", "weight": 2, "desc": "FAA aviation documents"},
    "dtic": {"path": "dtic", "weight": 2, "desc": "DTIC defense reports"},
}

# Size buckets for stratification
SIZE_BUCKETS = [
    ("tiny", 0, 100_000),           # <100KB
    ("small", 100_000, 500_000),     # 100KB-500KB
    ("medium", 500_000, 2_000_000),  # 500KB-2MB
    ("large", 2_000_000, 10_000_000),  # 2-10MB
    ("huge", 10_000_000, float("inf")),  # >10MB
]


@dataclass
class BenchmarkResult:
    """Result for one PDF in the benchmark."""
    pdf_path: str
    pdf_name: str
    category: str
    size_bucket: str
    file_size: int
    # Extraction results
    tables_a: int = 0  # /extract-tables count
    tables_b: int = 0  # Camelot count
    # Per-table grades
    grades: list[str] = field(default_factory=list)
    scores: list[float] = field(default_factory=list)
    # Errors
    error_a: str = ""  # /extract-tables error
    error_b: str = ""  # Camelot error
    # Timing
    time_a: float = 0.0
    time_b: float = 0.0
    # Status
    status: str = ""  # "success" | "no_tables" | "error_a" | "error_b" | "error_both"
    # Cell disagreement count
    cell_diffs: int = 0
    total_cells: int = 0
    elapsed: float = 0.0


@dataclass
class BenchmarkSummary:
    """Aggregate benchmark results."""
    total_pdfs: int = 0
    total_tables: int = 0
    # Grade distribution
    grade_counts: dict[str, int] = field(default_factory=lambda: Counter())
    # Category breakdown
    category_results: dict[str, dict] = field(default_factory=dict)
    # Error analysis
    error_a_only: int = 0  # /extract-tables fails, Camelot succeeds
    error_b_only: int = 0  # Camelot fails, /extract-tables succeeds
    error_both: int = 0
    no_tables: int = 0
    success: int = 0
    # Timing
    avg_time_a: float = 0.0
    avg_time_b: float = 0.0
    total_elapsed: float = 0.0
    # Parity metrics
    shape_match_rate: float = 0.0
    cell_match_rate: float = 0.0
    a_plus_rate: float = 0.0


def discover_corpus() -> dict[str, list[Path]]:
    """Discover all PDFs in the corpus, organized by category."""
    corpus = {}
    for cat_name, cat_info in CATEGORIES.items():
        cat_dir = CORPUS_ROOT / cat_info["path"]
        if not cat_dir.exists():
            continue
        pdfs = list(cat_dir.rglob("*.pdf"))
        if pdfs:
            corpus[cat_name] = pdfs
    return corpus


def stratified_sample(
    corpus: dict[str, list[Path]],
    total_n: int,
    seed: int = 42,
) -> list[tuple[str, Path]]:
    """Stratified random sample across categories and size buckets.

    Allocates samples proportional to category weight, with minimum 1 per
    non-empty category. Within each category, samples across size buckets.
    """
    rng = random.Random(seed)

    # Calculate allocation per category
    total_weight = sum(
        CATEGORIES[cat]["weight"] for cat in corpus if cat in CATEGORIES
    )
    allocations = {}
    remaining = total_n

    for cat in corpus:
        if cat not in CATEGORIES:
            continue
        weight = CATEGORIES[cat]["weight"]
        raw_alloc = max(1, int(total_n * weight / total_weight))
        # Cap at available PDFs
        alloc = min(raw_alloc, len(corpus[cat]))
        allocations[cat] = alloc
        remaining -= alloc

    # Distribute remaining budget to categories with most PDFs
    sorted_cats = sorted(
        allocations.keys(),
        key=lambda c: len(corpus[c]),
        reverse=True,
    )
    for cat in sorted_cats:
        if remaining <= 0:
            break
        extra = min(remaining, len(corpus[cat]) - allocations[cat])
        if extra > 0:
            allocations[cat] += extra
            remaining -= extra

    # Sample within each category, stratified by size
    samples = []
    for cat, n in allocations.items():
        pdfs = corpus[cat]
        # Bucket by size
        buckets = defaultdict(list)
        for pdf in pdfs:
            try:
                size = pdf.stat().st_size
            except OSError:
                continue
            for bname, lo, hi in SIZE_BUCKETS:
                if lo <= size < hi:
                    buckets[bname].append(pdf)
                    break

        # Sample proportionally from each size bucket
        selected = []
        non_empty = [(b, pdfs_in_b) for b, pdfs_in_b in buckets.items() if pdfs_in_b]
        if not non_empty:
            continue

        per_bucket = max(1, n // len(non_empty))
        for bname, pdfs_in_b in non_empty:
            k = min(per_bucket, len(pdfs_in_b))
            selected.extend(rng.sample(pdfs_in_b, k))

        # Fill remainder randomly from all buckets
        all_remaining = [p for p in pdfs if p not in selected]
        extra_needed = n - len(selected)
        if extra_needed > 0 and all_remaining:
            selected.extend(rng.sample(all_remaining, min(extra_needed, len(all_remaining))))

        for pdf in selected[:n]:
            samples.append((cat, pdf))

    rng.shuffle(samples)
    return samples


def _size_bucket(size: int) -> str:
    for bname, lo, hi in SIZE_BUCKETS:
        if lo <= size < hi:
            return bname
    return "unknown"


def run_single_benchmark(
    pdf_path: Path,
    category: str,
    timeout: int = 60,
) -> BenchmarkResult:
    """Run 2-way evidence matrix on a single PDF.

    Uses timeout to skip PDFs that take too long.
    """
    file_size = pdf_path.stat().st_size
    result = BenchmarkResult(
        pdf_path=str(pdf_path),
        pdf_name=pdf_path.name,
        category=category,
        size_bucket=_size_bucket(file_size),
        file_size=file_size,
    )

    t0 = time.monotonic()

    # Evidence A: /extract-tables
    try:
        from python.extract_tables import read_pdf
        ta = time.monotonic()
        tables_a_raw = read_pdf(str(pdf_path), pages="1", flavor="lattice")
        result.time_a = time.monotonic() - ta
        tables_a = []
        for t in tables_a_raw:
            if t._data:
                tables_a.append((t._data, t.bbox))
            elif t.df.shape[0] > 0:
                df = t.df
                grid = [list(df.columns)]
                for row in df.to_dicts():
                    grid.append([str(row[c]) for c in df.columns])
                tables_a.append((grid, t.bbox))
        result.tables_a = len(tables_a)
    except Exception as e:
        result.error_a = str(e)[:200]
        tables_a = []

    # Evidence B: Camelot
    try:
        import camelot
        tb = time.monotonic()
        cam_tables = camelot.read_pdf(str(pdf_path), flavor="lattice", pages="1")
        result.time_b = time.monotonic() - tb
        tables_b = []
        for ct in cam_tables:
            df = ct.df
            grid = []
            for i in range(len(df)):
                row = [str(df.iloc[i][c]) for c in df.columns]
                grid.append(row)
            bbox = ct._bbox if hasattr(ct, "_bbox") else (0, 0, 0, 0)
            tables_b.append((grid, bbox))
        result.tables_b = len(tables_b)
    except Exception as e:
        result.error_b = str(e)[:200]
        tables_b = []

    # Determine status
    if result.error_a and result.error_b:
        result.status = "error_both"
    elif result.error_a:
        result.status = "error_a"
    elif result.error_b:
        result.status = "error_b"
    elif result.tables_a == 0 and result.tables_b == 0:
        result.status = "no_tables"
    else:
        result.status = "success"

    # Cell-level comparison where both extracted tables
    if tables_a and tables_b:
        import re
        def _norm(s):
            return re.sub(r'\s+', ' ', s.strip())

        n_tables = min(len(tables_a), len(tables_b))
        for ti in range(n_tables):
            data_a, _ = tables_a[ti]
            data_b, _ = tables_b[ti]
            if not isinstance(data_a, list) or not isinstance(data_b, list):
                continue

            shape_a = (len(data_a), len(data_a[0]) if data_a else 0)
            shape_b = (len(data_b), len(data_b[0]) if data_b else 0)

            if shape_a == shape_b and shape_a[0] > 0:
                total = shape_a[0] * shape_a[1]
                matches = 0
                for r in range(shape_a[0]):
                    for c in range(shape_a[1]):
                        va = _norm(data_a[r][c]) if r < len(data_a) and c < len(data_a[r]) else ""
                        vb = _norm(data_b[r][c]) if r < len(data_b) and c < len(data_b[r]) else ""
                        if va == vb:
                            matches += 1
                result.total_cells += total
                result.cell_diffs += (total - matches)
                score = matches / total if total > 0 else 0.0
                result.scores.append(score)

                if score >= 1.0:
                    result.grades.append("A+")
                elif score >= 0.98:
                    result.grades.append("A")
                elif score >= 0.95:
                    result.grades.append("B")
                elif score >= 0.90:
                    result.grades.append("C")
                else:
                    result.grades.append("F")
            else:
                # Shape mismatch
                result.grades.append("F")
                result.scores.append(0.0)

    result.elapsed = time.monotonic() - t0
    return result


def aggregate_results(results: list[BenchmarkResult]) -> BenchmarkSummary:
    """Compute aggregate statistics from benchmark results."""
    summary = BenchmarkSummary()
    summary.total_pdfs = len(results)

    times_a = []
    times_b = []

    for r in results:
        # Status counts
        if r.status == "success":
            summary.success += 1
        elif r.status == "no_tables":
            summary.no_tables += 1
        elif r.status == "error_a":
            summary.error_a_only += 1
        elif r.status == "error_b":
            summary.error_b_only += 1
        elif r.status == "error_both":
            summary.error_both += 1

        # Grade counts
        for g in r.grades:
            summary.grade_counts[g] += 1
            summary.total_tables += 1

        # Timing
        if r.time_a > 0:
            times_a.append(r.time_a)
        if r.time_b > 0:
            times_b.append(r.time_b)

        # Category breakdown
        cat = r.category
        if cat not in summary.category_results:
            summary.category_results[cat] = {
                "total": 0, "success": 0, "grades": Counter(),
                "errors_a": 0, "errors_b": 0, "no_tables": 0,
            }
        cr = summary.category_results[cat]
        cr["total"] += 1
        if r.status == "success":
            cr["success"] += 1
        elif r.status == "error_a":
            cr["errors_a"] += 1
        elif r.status == "error_b":
            cr["errors_b"] += 1
        elif r.status == "no_tables":
            cr["no_tables"] += 1
        for g in r.grades:
            cr["grades"][g] += 1

    # Aggregate metrics
    summary.avg_time_a = sum(times_a) / len(times_a) if times_a else 0
    summary.avg_time_b = sum(times_b) / len(times_b) if times_b else 0
    summary.total_elapsed = sum(r.elapsed for r in results)

    total_cells = sum(r.total_cells for r in results)
    total_diffs = sum(r.cell_diffs for r in results)
    summary.cell_match_rate = (total_cells - total_diffs) / total_cells if total_cells > 0 else 0

    # A+ rate
    if summary.total_tables > 0:
        summary.a_plus_rate = summary.grade_counts.get("A+", 0) / summary.total_tables

    # Shape match = tables with any grade (means shape matched enough to compare)
    shape_compared = sum(1 for r in results for g in r.grades if g != "")
    total_table_pairs = sum(min(r.tables_a, r.tables_b) for r in results if r.status == "success")
    summary.shape_match_rate = shape_compared / total_table_pairs if total_table_pairs > 0 else 0

    return summary


def generate_report(
    results: list[BenchmarkResult],
    summary: BenchmarkSummary,
    sample_info: dict,
) -> str:
    """Generate markdown benchmark report."""
    lines = ["# Corpus Parity Benchmark Report\n"]
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Seed: {sample_info.get('seed', 42)}\n")

    # Executive summary
    lines.append("## Executive Summary\n")
    lines.append(f"- **PDFs tested**: {summary.total_pdfs}")
    lines.append(f"- **Tables compared**: {summary.total_tables}")
    lines.append(f"- **Cell match rate**: {summary.cell_match_rate:.1%}")
    lines.append(f"- **A+ tables (perfect match)**: {summary.grade_counts.get('A+', 0)}/{summary.total_tables} ({summary.a_plus_rate:.1%})")
    lines.append(f"- **Avg time /extract-tables**: {summary.avg_time_a:.2f}s")
    lines.append(f"- **Avg time Camelot**: {summary.avg_time_b:.2f}s")
    speedup = summary.avg_time_b / summary.avg_time_a if summary.avg_time_a > 0 else 0
    lines.append(f"- **Speedup**: {speedup:.1f}x")
    lines.append(f"- **Total elapsed**: {summary.total_elapsed:.0f}s ({summary.total_elapsed / 60:.1f}min)\n")

    # Status breakdown
    lines.append("## Status Breakdown\n")
    lines.append("| Status | Count | % |")
    lines.append("| --- | --- | --- |")
    for status, count in [
        ("Success (both extract)", summary.success),
        ("No tables found", summary.no_tables),
        ("/extract-tables error only", summary.error_a_only),
        ("Camelot error only", summary.error_b_only),
        ("Both error", summary.error_both),
    ]:
        pct = count / summary.total_pdfs * 100 if summary.total_pdfs > 0 else 0
        lines.append(f"| {status} | {count} | {pct:.1f}% |")
    lines.append("")

    # Grade distribution
    lines.append("## Grade Distribution\n")
    lines.append("| Grade | Count | % | Meaning |")
    lines.append("| --- | --- | --- | --- |")
    grade_meanings = {
        "A+": "Perfect cell match",
        "A": ">=98% cells match",
        "B": ">=95% cells match",
        "C": ">=90% cells match",
        "F": "<90% or shape mismatch",
    }
    for grade in ["A+", "A", "B", "C", "F"]:
        count = summary.grade_counts.get(grade, 0)
        pct = count / summary.total_tables * 100 if summary.total_tables > 0 else 0
        lines.append(f"| {grade} | {count} | {pct:.1f}% | {grade_meanings.get(grade, '')} |")
    lines.append("")

    # Category breakdown
    lines.append("## Category Breakdown\n")
    lines.append("| Category | PDFs | Success | A+/A | B/C | F | Errors A | Errors B |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for cat in sorted(summary.category_results.keys()):
        cr = summary.category_results[cat]
        grades = cr["grades"]
        a_plus_a = grades.get("A+", 0) + grades.get("A", 0)
        b_c = grades.get("B", 0) + grades.get("C", 0)
        f = grades.get("F", 0)
        lines.append(
            f"| {cat} | {cr['total']} | {cr['success']} "
            f"| {a_plus_a} | {b_c} | {f} "
            f"| {cr['errors_a']} | {cr['errors_b']} |"
        )
    lines.append("")

    # Size bucket analysis
    lines.append("## Size Bucket Analysis\n")
    size_data = defaultdict(lambda: {"count": 0, "grades": Counter(), "errors": 0})
    for r in results:
        sd = size_data[r.size_bucket]
        sd["count"] += 1
        for g in r.grades:
            sd["grades"][g] += 1
        if r.error_a or r.error_b:
            sd["errors"] += 1

    lines.append("| Size | PDFs | A+/A | F | Errors |")
    lines.append("| --- | --- | --- | --- | --- |")
    for bname, _, _ in SIZE_BUCKETS:
        sd = size_data[bname]
        if sd["count"] == 0:
            continue
        a_plus_a = sd["grades"].get("A+", 0) + sd["grades"].get("A", 0)
        lines.append(f"| {bname} | {sd['count']} | {a_plus_a} | {sd['grades'].get('F', 0)} | {sd['errors']} |")
    lines.append("")

    # Failure analysis (top failures)
    failures = [r for r in results if any(g == "F" for g in r.grades)]
    if failures:
        lines.append("## Notable Failures\n")
        lines.append("| PDF | Category | Size | Tables A | Tables B | Grades | Error |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for r in failures[:30]:
            err = r.error_a[:50] or r.error_b[:50] or "shape/cell mismatch"
            lines.append(
                f"| {r.pdf_name[:40]} | {r.category} | {r.size_bucket} "
                f"| {r.tables_a} | {r.tables_b} | {','.join(r.grades)} | {err} |"
            )
        if len(failures) > 30:
            lines.append(f"\n... and {len(failures) - 30} more failures\n")
        lines.append("")

    # Error analysis
    errors_a = [r for r in results if r.error_a and not r.error_b]
    errors_b = [r for r in results if r.error_b and not r.error_a]
    if errors_a:
        lines.append("## /extract-tables Errors (Camelot succeeded)\n")
        err_types = Counter(r.error_a.split(":")[0][:50] for r in errors_a)
        for err, count in err_types.most_common(10):
            lines.append(f"- `{err}`: {count}x")
        lines.append("")

    if errors_b:
        lines.append("## Camelot Errors (/extract-tables succeeded)\n")
        err_types = Counter(r.error_b.split(":")[0][:50] for r in errors_b)
        for err, count in err_types.most_common(10):
            lines.append(f"- `{err}`: {count}x")
        lines.append("")

    # Speed comparison
    paired = [(r.time_a, r.time_b) for r in results if r.time_a > 0 and r.time_b > 0]
    if paired:
        lines.append("## Speed Comparison\n")
        faster_a = sum(1 for a, b in paired if a < b)
        faster_b = sum(1 for a, b in paired if b < a)
        lines.append(f"- /extract-tables faster: {faster_a}/{len(paired)} ({faster_a/len(paired):.1%})")
        lines.append(f"- Camelot faster: {faster_b}/{len(paired)} ({faster_b/len(paired):.1%})")
        avg_ratio = sum(b / a for a, b in paired if a > 0) / len(paired)
        lines.append(f"- Average speed ratio (Camelot/ours): {avg_ratio:.2f}x")
        lines.append("")

    # Sampling info
    lines.append("## Sampling Methodology\n")
    lines.append(f"- Corpus: {sample_info.get('corpus_root', CORPUS_ROOT)}")
    lines.append(f"- Total PDFs in corpus: {sample_info.get('total_corpus', 'unknown')}")
    lines.append(f"- Sample size: {summary.total_pdfs}")
    lines.append(f"- Seed: {sample_info.get('seed', 42)}")
    lines.append(f"- Strategy: Stratified by category (weighted) and file size")
    if "category_counts" in sample_info:
        lines.append(f"- Corpus distribution: {json.dumps(sample_info['category_counts'])}")
    lines.append("")

    return "\n".join(lines)


def run_benchmark(
    sample_size: int = 200,
    seed: int = 42,
    output_dir: str = "/tmp/parity_benchmark",
    quick: bool = False,
    resume: bool = False,
) -> tuple[list[BenchmarkResult], BenchmarkSummary]:
    """Run the full stratified benchmark."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results_file = out_dir / "results.jsonl"
    sample_file = out_dir / "sample.json"

    # Discover corpus
    print("Discovering corpus...")
    corpus = discover_corpus()
    total_corpus = sum(len(pdfs) for pdfs in corpus.values())
    category_counts = {cat: len(pdfs) for cat, pdfs in corpus.items()}
    print(f"Found {total_corpus} PDFs across {len(corpus)} categories")
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")

    # Generate or load sample
    if resume and sample_file.exists():
        print(f"Resuming from {sample_file}")
        sample_data = json.loads(sample_file.read_text())
        samples = [(s["category"], Path(s["path"])) for s in sample_data["samples"]]
        # Load existing results
        completed = set()
        results = []
        if results_file.exists():
            for line in results_file.read_text().strip().split("\n"):
                if not line:
                    continue
                d = json.loads(line)
                results.append(BenchmarkResult(**{
                    k: v for k, v in d.items()
                    if k in BenchmarkResult.__dataclass_fields__
                }))
                completed.add(d["pdf_path"])
        print(f"Loaded {len(results)} existing results, {len(samples) - len(completed)} remaining")
    else:
        print(f"Sampling {sample_size} PDFs (seed={seed})...")
        samples = stratified_sample(corpus, sample_size, seed)

        # Save sample manifest
        sample_data = {
            "seed": seed,
            "total_corpus": total_corpus,
            "category_counts": category_counts,
            "sample_size": len(samples),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "samples": [{"category": cat, "path": str(p)} for cat, p in samples],
        }
        sample_file.write_text(json.dumps(sample_data, indent=2))
        results = []
        completed = set()

    # Print sample distribution
    sample_cats = Counter(cat for cat, _ in samples)
    print(f"\nSample distribution ({len(samples)} PDFs):")
    for cat, count in sample_cats.most_common():
        print(f"  {cat}: {count}")

    # Run benchmark
    print(f"\nRunning benchmark...")
    start = time.monotonic()
    remaining = [(cat, p) for cat, p in samples if str(p) not in completed]

    for i, (cat, pdf_path) in enumerate(remaining):
        if not pdf_path.exists():
            print(f"  [{i+1+len(completed)}/{len(samples)}] SKIP {pdf_path.name} (not found)")
            continue

        # Skip huge files in quick mode
        if quick and pdf_path.stat().st_size > 5_000_000:
            print(f"  [{i+1+len(completed)}/{len(samples)}] SKIP {pdf_path.name} (too large for --quick)")
            continue

        print(f"  [{i+1+len(completed)}/{len(samples)}] {cat}/{pdf_path.name} ({pdf_path.stat().st_size // 1024}KB)...", end=" ", flush=True)

        try:
            result = run_single_benchmark(pdf_path, cat)
            results.append(result)

            # Append to JSONL for resume support
            with open(results_file, "a") as f:
                f.write(json.dumps(asdict(result), default=str) + "\n")

            # Status indicator
            if result.status == "success":
                grades_str = ",".join(result.grades) if result.grades else "no_cmp"
                print(f"OK t_a={result.tables_a} t_b={result.tables_b} [{grades_str}] {result.elapsed:.1f}s")
            elif result.status == "no_tables":
                print(f"NO_TABLES {result.elapsed:.1f}s")
            else:
                print(f"{result.status.upper()} {result.elapsed:.1f}s")

        except Exception as e:
            print(f"CRASH: {e}")
            # Log crash and continue
            result = BenchmarkResult(
                pdf_path=str(pdf_path),
                pdf_name=pdf_path.name,
                category=cat,
                size_bucket=_size_bucket(pdf_path.stat().st_size),
                file_size=pdf_path.stat().st_size,
                error_a=f"CRASH: {e}",
                error_b=f"CRASH: {e}",
                status="error_both",
            )
            results.append(result)
            with open(results_file, "a") as f:
                f.write(json.dumps(asdict(result), default=str) + "\n")

    total_time = time.monotonic() - start

    # Aggregate
    summary = aggregate_results(results)
    summary.total_elapsed = total_time

    sample_info = {
        "seed": seed,
        "total_corpus": total_corpus,
        "category_counts": category_counts,
        "corpus_root": str(CORPUS_ROOT),
    }

    # Generate report
    report = generate_report(results, summary, sample_info)
    report_path = out_dir / "benchmark_report.md"
    report_path.write_text(report)
    print(f"\nReport: {report_path}")

    # Also save summary JSON
    summary_path = out_dir / "summary.json"
    summary_dict = {
        "total_pdfs": summary.total_pdfs,
        "total_tables": summary.total_tables,
        "grade_counts": dict(summary.grade_counts),
        "cell_match_rate": round(summary.cell_match_rate, 4),
        "a_plus_rate": round(summary.a_plus_rate, 4),
        "avg_time_a": round(summary.avg_time_a, 3),
        "avg_time_b": round(summary.avg_time_b, 3),
        "total_elapsed": round(summary.total_elapsed, 1),
        "status": {
            "success": summary.success,
            "no_tables": summary.no_tables,
            "error_a_only": summary.error_a_only,
            "error_b_only": summary.error_b_only,
            "error_both": summary.error_both,
        },
    }
    summary_path.write_text(json.dumps(summary_dict, indent=2))

    return results, summary


app = typer.Typer(help="Stratified corpus benchmark for /extract-tables parity")


@app.command()
def benchmark(
    sample: int = typer.Option(200, help="Number of PDFs to sample"),
    seed: int = typer.Option(42, help="Random seed for reproducibility"),
    output: str = typer.Option("/tmp/parity_benchmark", "-o", help="Output directory"),
    quick: bool = typer.Option(False, help="Quick mode: skip large files, smaller sample"),
    resume: bool = typer.Option(False, help="Resume interrupted benchmark run"),
) -> None:
    """Run stratified parity benchmark across the 12TB corpus."""
    effective_sample = min(sample, 50) if quick else sample

    results, summary = run_benchmark(
        sample_size=effective_sample,
        seed=seed,
        output_dir=output,
        quick=quick,
        resume=resume,
    )

    typer.echo(f"\n{'='*60}")
    typer.echo("PARITY BENCHMARK RESULTS")
    typer.echo(f"{'='*60}")
    typer.echo(f"PDFs tested:     {summary.total_pdfs}")
    typer.echo(f"Tables compared: {summary.total_tables}")
    typer.echo(f"Cell match rate: {summary.cell_match_rate:.1%}")
    typer.echo(f"A+ rate:         {summary.a_plus_rate:.1%}")
    typer.echo("")
    typer.echo(
        f"Grades: A+={summary.grade_counts.get('A+', 0)} "
        f"A={summary.grade_counts.get('A', 0)} "
        f"B={summary.grade_counts.get('B', 0)} "
        f"C={summary.grade_counts.get('C', 0)} "
        f"F={summary.grade_counts.get('F', 0)}"
    )
    typer.echo("")
    typer.echo(f"Speed: ours={summary.avg_time_a:.2f}s  camelot={summary.avg_time_b:.2f}s")
    if summary.avg_time_a > 0:
        typer.echo(f"Speedup: {summary.avg_time_b / summary.avg_time_a:.1f}x")
    typer.echo(f"Total time: {summary.total_elapsed:.0f}s ({summary.total_elapsed / 60:.1f}min)")
    typer.echo("")
    typer.echo(f"Errors: ours_only={summary.error_a_only} camelot_only={summary.error_b_only} both={summary.error_both}")
    typer.echo(f"No tables: {summary.no_tables}")
    typer.echo(f"{'='*60}")


if __name__ == "__main__":
    app()
