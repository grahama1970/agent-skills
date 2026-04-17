#!/usr/bin/env python3
"""Visual parity report: screenshot + grid overlay + extracted text.

Generates a markdown document comparing extraction results side-by-side
with the actual PDF rendering. Makes debugging transparent — you can SEE
what went wrong instead of staring at terminal diffs.

Usage:
    python -m python.parity_report tests/fixtures/foo.pdf --output report.md
    python -m python.parity_report tests/fixtures/ --output report.md  # all fixtures
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SKILL_DIR / "src"))


def render_page_cropped(
    pdf_path: str, page_num: int, bbox: tuple[float, ...], dpi: int = 150, margin: int = 10,
) -> Image.Image:
    """Render a PDF page and crop to table bounding box."""
    from python.pdf_bridge import render_page_image, get_page_dimensions

    img = render_page_image(pdf_path, page_num, dpi=dpi)
    pdf_w, pdf_h = get_page_dimensions(pdf_path, page_num)
    scale_x = img.width / pdf_w
    scale_y = img.height / pdf_h

    x0, y0, x1, y1 = bbox
    px0 = max(0, int(x0 * scale_x) - margin)
    py0 = max(0, int(y0 * scale_y) - margin)
    px1 = min(img.width, int(x1 * scale_x) + margin)
    py1 = min(img.height, int(y1 * scale_y) + margin)

    return img.crop((px0, py0, px1, py1))


def draw_grid_overlay(
    pdf_path: str, page_num: int, table, dpi: int = 150, margin: int = 10,
) -> Image.Image:
    """Render page with grid lines overlaid on the table."""
    from python.pdf_bridge import render_page_image, get_page_dimensions

    img = render_page_image(pdf_path, page_num, dpi=dpi).convert("RGBA")
    pdf_w, pdf_h = get_page_dimensions(pdf_path, page_num)
    scale_x = img.width / pdf_w
    scale_y = img.height / pdf_h

    overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)

    # Draw cell boundaries from the table's internal grid
    bbox = table.bbox
    cells = getattr(table, "_cells", [])
    for cell in cells:
        cx0 = int(cell.x1 * scale_x)
        cy0 = int(cell.y1 * scale_y)
        cx1 = int(cell.x2 * scale_x)
        cy1 = int(cell.y2 * scale_y)
        draw.rectangle([cx0, cy0, cx1, cy1], outline=(255, 0, 0, 180), width=1)

    # Draw table bbox
    tx0 = int(bbox[0] * scale_x)
    ty0 = int(bbox[1] * scale_y)
    tx1 = int(bbox[2] * scale_x)
    ty1 = int(bbox[3] * scale_y)
    draw.rectangle([tx0, ty0, tx1, ty1], outline=(0, 0, 255, 200), width=2)

    composite = Image.alpha_composite(img, overlay).convert("RGB")

    # Crop to table area
    px0 = max(0, tx0 - margin)
    py0 = max(0, ty0 - margin)
    px1 = min(composite.width, tx1 + margin)
    py1 = min(composite.height, ty1 + margin)

    return composite.crop((px0, py0, px1, py1))


def table_to_markdown(table) -> str:
    """Convert a Table's DataFrame to markdown."""
    import polars as pl

    df = table.df
    cols = df.columns
    rows_data = df.to_dicts()

    lines = []
    # Header
    header = "| " + " | ".join(c.replace("\n", " ").strip()[:25] for c in cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    lines.append(header)
    lines.append(sep)

    # Data rows (cap at 10 for readability)
    max_rows = min(len(rows_data), 10)
    for row in rows_data[:max_rows]:
        cells = []
        for c in cols:
            val = str(row[c]).replace("\n", " ").strip()[:30]
            cells.append(val)
        lines.append("| " + " | ".join(cells) + " |")

    if len(rows_data) > max_rows:
        lines.append(f"| ... ({len(rows_data) - max_rows} more rows) |")

    return "\n".join(lines)


def _camelot_table_to_markdown(cam_table) -> str:
    """Convert a Camelot table to markdown."""
    df = cam_table.df
    cols = list(df.columns)
    lines = []
    header = "| " + " | ".join(str(c).replace("\n", " ").strip()[:25] for c in cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    lines.append(header)
    lines.append(sep)

    max_rows = min(len(df), 10)
    for i in range(max_rows):
        cells = []
        for c in cols:
            val = str(df.iloc[i][c]).replace("\n", " ").strip()[:30]
            cells.append(val)
        lines.append("| " + " | ".join(cells) + " |")

    if len(df) > max_rows:
        lines.append(f"| ... ({len(df) - max_rows} more rows) |")

    return "\n".join(lines)


def generate_report(
    pdf_path: str,
    output_dir: str,
    pages: str = "1",
    include_camelot: bool = True,
) -> str:
    """Generate a visual parity report for a PDF.

    Returns the markdown content.
    """
    from python.extract_tables import read_pdf

    pdf_name = Path(pdf_path).stem
    out_dir = Path(output_dir)
    img_dir = out_dir / "images"
    img_dir.mkdir(parents=True, exist_ok=True)

    md_lines = [f"# Transparency Report: {pdf_name}\n"]

    # Extract with our pipeline
    our_tables = read_pdf(pdf_path, pages=pages, flavor="lattice")

    # Extract with Camelot if available
    cam_tables = None
    if include_camelot:
        try:
            import camelot
            cam_tables = camelot.read_pdf(pdf_path, flavor="lattice", pages=pages)
        except Exception as e:
            md_lines.append(f"> Camelot unavailable: {e}\n")

    md_lines.append(f"- **PDF**: `{pdf_path}`")
    md_lines.append(f"- **Our tables**: {len(our_tables)}")
    if cam_tables is not None:
        md_lines.append(f"- **Camelot tables**: {len(cam_tables)}")
    md_lines.append("")

    for ti, table in enumerate(our_tables):
        md_lines.append(f"## Table {ti}\n")
        md_lines.append("### Metadata\n")
        md_lines.append("| Property | Value |")
        md_lines.append("| -------- | ----- |")
        md_lines.append(f"| Shape | {table.rows} x {table.cols} |")
        md_lines.append(f"| Strategy | {table.strategy} |")
        md_lines.append(f"| Accuracy | {table.accuracy:.1f}% |")
        md_lines.append(f"| Whitespace | {table.whitespace:.1f}% |")
        md_lines.append(f"| Page | {table.page_number} |")
        md_lines.append(f"| BBox | ({table.bbox[0]:.1f}, {table.bbox[1]:.1f}, {table.bbox[2]:.1f}, {table.bbox[3]:.1f}) |")
        if table.title:
            md_lines.append(f"| Title | {table.title} |")
        if table.section_id:
            md_lines.append(f"| Section | {table.section_id} |")
        if table._integrity:
            frag = table._integrity.get("fragmentation_score", 0)
            md_lines.append(f"| Fragmentation | {frag:.3f} |")
        md_lines.append("")

        # 1. Screenshot of the table region
        try:
            screenshot = render_page_cropped(pdf_path, table.page_index, table.bbox)
            img_path = img_dir / f"{pdf_name}_t{ti}_screenshot.png"
            screenshot.save(str(img_path))
            rel_path = os.path.relpath(img_path, out_dir)
            md_lines.append("### 1. PDF Screenshot\n")
            md_lines.append(f"![Table {ti} screenshot]({rel_path})\n")
        except Exception as e:
            md_lines.append(f"### 1. PDF Screenshot\n\n> Render failed: {e}\n")

        # 2. Grid overlay
        try:
            overlay = draw_grid_overlay(pdf_path, table.page_index, table)
            img_path = img_dir / f"{pdf_name}_t{ti}_grid.png"
            overlay.save(str(img_path))
            rel_path = os.path.relpath(img_path, out_dir)
            md_lines.append("### 2. Detected Grid\n")
            md_lines.append(f"![Table {ti} grid]({rel_path})\n")
        except Exception as e:
            md_lines.append(f"### 2. Detected Grid\n\n> Grid overlay failed: {e}\n")

        # 3. Extracted text as markdown table
        md_lines.append("### 3. Our Extracted Text\n")
        md_lines.append(table_to_markdown(table))
        md_lines.append("")

        # 4. Camelot comparison if available
        if cam_tables is not None and ti < len(cam_tables):
            ct = cam_tables[ti]
            md_lines.append("### 4. Camelot Extracted Text\n")
            md_lines.append(_camelot_table_to_markdown(ct))
            md_lines.append("")

            # 5. Cell diff summary
            md_lines.append("### 5. Cell Diffs\n")
            our_df = table.df
            cam_df = ct.df
            if our_df.shape == cam_df.shape:
                diffs = []
                for r in range(our_df.shape[0]):
                    for c in range(our_df.shape[1]):
                        ours_val = str(our_df[r, c]).strip()
                        cam_val = str(cam_df.iloc[r][cam_df.columns[c]]).strip()
                        if ours_val != cam_val:
                            diffs.append((r, c, cam_val[:40], ours_val[:40]))
                if diffs:
                    md_lines.append(f"**{len(diffs)} cell diffs:**\n")
                    md_lines.append("| Row | Col | Camelot | Ours |")
                    md_lines.append("| --- | --- | ------- | ---- |")
                    for r, c, cv, ov in diffs[:20]:
                        md_lines.append(f"| {r} | {c} | `{cv}` | `{ov}` |")
                    if len(diffs) > 20:
                        md_lines.append(f"| ... | ... | ({len(diffs) - 20} more) | |")
                else:
                    md_lines.append("**MATCH** - all cells identical\n")
            else:
                md_lines.append(
                    f"**SHAPE MISMATCH**: ours={our_df.shape} camelot={cam_df.shape}\n"
                )

        md_lines.append("---\n")

    return "\n".join(md_lines)


def generate_full_report(
    fixture_dir: str,
    output_dir: str,
    pages: str = "1",
) -> str:
    """Generate parity report for all PDFs in a directory."""
    fixture_path = Path(fixture_dir)
    pdfs = sorted(fixture_path.glob("*.pdf"))

    all_md = ["# Full Parity Report\n"]
    all_md.append(f"- **Fixtures**: {len(pdfs)} PDFs")
    all_md.append(f"- **Source**: `{fixture_dir}`\n")

    pass_count = 0
    fail_count = 0

    for pdf in pdfs:
        try:
            report = generate_report(str(pdf), output_dir, pages=pages)
            all_md.append(report)
            if "MATCH" in report and "SHAPE MISMATCH" not in report:
                pass_count += 1
            else:
                fail_count += 1
        except Exception as e:
            all_md.append(f"## {pdf.stem}\n\n> FAILED: {e}\n\n---\n")
            fail_count += 1

    summary = f"\n## Summary: {pass_count} PASS / {fail_count} FAIL out of {len(pdfs)} PDFs\n"
    all_md.insert(3, summary)

    return "\n".join(all_md)


def _cli_main(
    input_path: str = typer.Argument(..., help="PDF file or directory of PDFs"),
    output: str = typer.Option("parity_report", "--output", "-o", help="Output directory"),
    pages: str = typer.Option("1", "--pages", help="Pages to extract"),
    no_camelot: bool = typer.Option(False, "--no-camelot", help="Skip Camelot comparison"),
) -> None:
    """Visual parity report: screenshot + grid overlay + extracted text."""
    inp = Path(input_path)
    out_dir = Path(output)
    out_dir.mkdir(parents=True, exist_ok=True)

    if inp.is_dir():
        md = generate_full_report(str(inp), str(out_dir), pages=pages)
    else:
        md = generate_report(str(inp), str(out_dir), pages=pages, include_camelot=not no_camelot)

    report_path = out_dir / "report.md"
    report_path.write_text(md)
    print(f"Report written to {report_path}")


if __name__ == "__main__":
    import typer
    typer.run(_cli_main)
