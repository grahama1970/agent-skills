#!/usr/bin/env python3
"""Query Parquet dataset files for the ClassifierLabView table.

Called by the UX Lab server as a subprocess. Reads Parquet with polars,
applies filters/pagination, returns JSON to stdout.

Handles million-row datasets via lazy evaluation — only materializes
the requested page.

Usage:
    python query_dataset.py /path/to/dataset.parquet \
        --page 0 --page-size 50 \
        --class Business \
        --split train \
        --search "reuters" \
        --sort-by class --sort-dir asc

    # Get metadata (class list, total rows, splits)
    python query_dataset.py /path/to/dataset.parquet --meta
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import typer

app = typer.Typer(no_args_is_help=True)


def _query_samples_jsonl(
    samples_path: Path,
    page: int,
    page_size: int,
    cls: str,
    split: str,
    search: str,
    sort_by: str,
    sort_dir: str,
    meta: bool,
) -> dict:
    rows: list[dict] = []
    with samples_path.open() as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    columns = sorted({k for row in rows for k in row.keys()})
    class_col = "class" if "class" in columns else ("label" if "label" in columns else None)
    split_col = "split" if "split" in columns else None
    text_col = "text" if "text" in columns else ("content" if "content" in columns else None)

    def _match(row: dict) -> bool:
        if cls and class_col and str(row.get(class_col, "")) != cls:
            return False
        if split and split_col and str(row.get(split_col, "")) != split:
            return False
        if search and text_col and search.lower() not in str(row.get(text_col, "")).lower():
            return False
        return True

    filtered = [row for row in rows if _match(row)]
    if sort_by and sort_by in columns:
        filtered.sort(key=lambda r: str(r.get(sort_by, "")), reverse=(sort_dir == "desc"))

    if meta:
        class_counts: dict[str, int] = {}
        if class_col:
            for row in filtered:
                key = str(row.get(class_col, ""))
                class_counts[key] = class_counts.get(key, 0) + 1
        return {
            "total": len(filtered),
            "total_rows": len(filtered),
            "columns": columns,
            "class_col": class_col,
            "text_col": text_col,
            "split_col": split_col,
            "classes": sorted(class_counts.keys()) if class_col else [],
            "class_counts": class_counts,
        }

    offset = page * page_size
    page_rows = filtered[offset: offset + page_size]
    out_rows = []
    for i, row in enumerate(page_rows):
        out_rows.append({
            "filename": str(row.get("filename", f"row_{offset + i}")),
            "className": str(row.get(class_col, "")) if class_col else "",
            "split": str(row.get(split_col, "train")) if split_col else "train",
            "path": str(row.get("path", "")),
            "text": str(row.get(text_col, ""))[:300] if text_col else "",
        })
    return {"rows": out_rows, "total": len(filtered), "page": page, "page_size": page_size}


@app.command()
def query(
    path: str = typer.Argument(..., help="Path to .parquet file"),
    page: int = typer.Option(0, help="Page index (0-based)"),
    page_size: int = typer.Option(50, help="Rows per page"),
    cls: str = typer.Option("", "--class", help="Filter by class label"),
    split: str = typer.Option("", help="Filter by split"),
    search: str = typer.Option("", help="Search text content"),
    sort_by: str = typer.Option("", help="Sort column"),
    sort_dir: str = typer.Option("asc", help="Sort direction: asc or desc"),
    meta: bool = typer.Option(False, help="Return metadata only"),
) -> None:
    """Query a Parquet dataset with filtering and pagination."""
    parquet_path = Path(path)
    if not parquet_path.exists():
        print(json.dumps({"rows": [], "total": 0, "error": f"Not found: {path}"}))
        return

    page = max(page, 0)
    page_size = max(page_size, 1)
    samples_path = parquet_path.with_name("samples.jsonl")

    try:
        import polars as pl
    except ImportError:
        if samples_path.exists():
            result = _query_samples_jsonl(samples_path, page, page_size, cls, split, search, sort_by, sort_dir, meta)
            print(json.dumps(result))
            return
        print(json.dumps({"rows": [], "total": 0, "error": "polars not installed"}))
        return

    # Lazy scan — doesn't load the whole file
    lf = pl.scan_parquet(parquet_path)

    if meta:
        schema = lf.collect_schema()
        cols = schema.names()
        class_col = "class" if "class" in cols else ("label" if "label" in cols else None)
        split_col = "split" if "split" in cols else None
        text_col = "text" if "text" in cols else ("content" if "content" in cols else None)
        total = lf.select(pl.len().alias("total")).collect().item()

        result = {
            "total": total,
            "total_rows": total,
            "columns": cols,
            "class_col": class_col,
            "text_col": text_col,
            "split_col": split_col,
        }
        if class_col:
            class_df = lf.group_by(class_col).agg(pl.len().alias("count")).sort(class_col).collect()
            result["classes"] = class_df[class_col].to_list()
            result["class_counts"] = {str(r[class_col]): int(r["count"]) for r in class_df.to_dicts()}
        if split_col:
            split_df = lf.select(pl.col(split_col)).unique().sort(split_col).collect()
            result["splits"] = split_df[split_col].to_list()
        print(json.dumps(result))
        return

    # Detect column names
    schema = lf.collect_schema()
    col_names = schema.names()
    class_col = "class" if "class" in col_names else ("label" if "label" in col_names else None)
    text_col = "text" if "text" in col_names else ("content" if "content" in col_names else None)
    split_col = "split" if "split" in col_names else None
    filename_col = "filename" if "filename" in col_names else ("file" if "file" in col_names else None)
    path_col = "path" if "path" in col_names else None

    # Apply filters (lazy — pushed down to scan)
    if cls and class_col:
        lf = lf.filter(pl.col(class_col) == cls)
    if split and split_col:
        lf = lf.filter(pl.col(split_col) == split)
    if search and text_col:
        lf = lf.filter(pl.col(text_col).cast(pl.Utf8).str.contains(f"(?i){re.escape(search)}"))

    # Get total after filters
    total = lf.select(pl.len()).collect().item()

    # Sort
    if sort_by and sort_by in col_names:
        lf = lf.sort(sort_by, descending=(sort_dir == "desc"))

    # Paginate
    offset = page * page_size
    df = lf.slice(offset, page_size).collect()

    # Build output rows
    rows = []
    for row in df.to_dicts():
        out = {
            "filename": str(row.get(filename_col, "")) if filename_col else f"row_{offset + len(rows)}",
            "className": str(row.get(class_col, "")) if class_col else "",
            "split": str(row.get(split_col, "train")) if split_col else "train",
            "path": str(row.get(path_col, "")) if path_col else "",
            "text": str(row.get(text_col, ""))[:300] if text_col else "",
        }
        rows.append(out)

    print(json.dumps({"rows": rows, "total": total, "page": page, "page_size": page_size}))


if __name__ == "__main__":
    # Backward-compatible invocation styles:
    #   query_dataset.py /path/file.parquet --meta
    #   query_dataset.py query /path/file.parquet --page 0
    if len(sys.argv) > 1 and sys.argv[1] == "query":
        sys.argv.pop(1)
    app()
