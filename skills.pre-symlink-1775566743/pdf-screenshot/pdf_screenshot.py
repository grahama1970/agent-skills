"""pdf_screenshot - pdf-screenshot.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""


import fitz
import sys
from pathlib import Path
from typing import Optional, List

import typer

def screenshot_page(
    pdf_path: str,
    page_num: int,
    crop_bbox: list[float] | None = None,
    highlight_bbox: list[float] | None = None,
    out_path: str | None = None,
    dpi: int = 150
) -> str:
    """
    Render a single page to PNG.
    page_num: 0-indexed page number.
    """
    doc = fitz.open(pdf_path)

    try:
        page = doc[page_num]
    except IndexError:
        print(f"Error: Page {page_num} not found in document (max index: {len(doc)-1})")
        sys.exit(1)

    # Apply Highlight if requested
    if highlight_bbox:
        rect = fitz.Rect(highlight_bbox)
        # Draw red rectangle: stroke only, width 3
        # color is (r, g, b) floats 0-1
        page.draw_rect(rect, color=(1, 0, 0), width=3)

    # Render
    if crop_bbox:
        rect = fitz.Rect(crop_bbox)
        rect = rect + (-20, -20, 20, 20) # Padding
        pix = page.get_pixmap(clip=rect, dpi=dpi)
    else:
        pix = page.get_pixmap(dpi=dpi)

    # Determine Output Path
    if not out_path:
        out_path = _generate_default_path(pdf_path, page_num, crop_bbox)
    else:
        # If out_path is a directory (ends in / or exists as dir), append filename
        p_out = Path(out_path)
        if out_path.endswith("/") or (p_out.exists() and p_out.is_dir()):
            filename = Path(_generate_default_path(pdf_path, page_num, crop_bbox)).name
            out_path = str(p_out / filename)

    out_path_obj = Path(out_path)
    out_path_obj.parent.mkdir(parents=True, exist_ok=True)

    pix.save(out_path_obj)
    doc.close()
    return str(out_path_obj)

def _generate_default_path(pdf_path: str, page_num: int, bbox: list[float] | None) -> str:
    stem = Path(pdf_path).stem
    suffix = "_crop" if bbox else ""
    return f"/tmp/pdf-screenshot/{stem}_page{page_num}{suffix}.png"

def parse_bbox(s: str) -> List[float]:
    """Parse bbox string 'x0,y0,x1,y1' into list of floats."""
    try:
        return [float(x.strip()) for x in s.split(',')]
    except ValueError:
        raise typer.BadParameter("BBox must be 'x0,y0,x1,y1' floats")

def parse_pages_str(s: str) -> List[int]:
    """Parse comma-separated page numbers."""
    try:
        return [int(x.strip()) for x in s.split(',')]
    except ValueError:
        raise typer.BadParameter("Pages must be comma-separated ints")

app = typer.Typer(help="Screenshot a PDF page or region.")


@app.command()
def main(
    pdf_path: str = typer.Argument(..., help="Path to the PDF file"),
    page: int = typer.Option(None, "--page", help="Single page number (0-indexed)"),
    pages: str = typer.Option(None, "--pages", help="Comma-separated page numbers (e.g. 1,3,5)"),
    all_pages: bool = typer.Option(False, "--all", help="Process all pages"),
    bbox: str = typer.Option(None, "--bbox", help="Crop BBox 'x0,y0,x1,y1'"),
    highlight: str = typer.Option(None, "--highlight", help="Highlight BBox 'x0,y0,x1,y1' (red box)"),
    out_path: str = typer.Option(None, "--out", help="Output path or directory"),
    dpi: int = typer.Option(150, "--dpi", help="DPI for rendering"),
) -> None:
    """Screenshot a PDF page or region."""
    # Validate mutually exclusive page selection
    selections = sum([page is not None, pages is not None, all_pages])
    if selections == 0:
        print("Must specify one of --page, --pages, or --all", file=sys.stderr)
        raise typer.Exit(1)
    if selections > 1:
        print("Only one of --page, --pages, or --all may be specified", file=sys.stderr)
        raise typer.Exit(1)

    # Parse bbox/highlight strings
    crop_bbox = parse_bbox(bbox) if bbox else None
    highlight_bbox = parse_bbox(highlight) if highlight else None

    # Determine pages to process
    pages_to_process: List[int] = []
    if page is not None:
        pages_to_process = [page]
    elif pages is not None:
        pages_to_process = parse_pages_str(pages)
    elif all_pages:
        try:
            doc = fitz.open(pdf_path)
            pages_to_process = list(range(len(doc)))
            doc.close()
        except Exception as e:
            print(f"Error opening PDF: {e}")
            raise typer.Exit(1)

    # Process
    try:
        results = []
        for p in pages_to_process:
            saved = screenshot_page(
                pdf_path,
                p,
                crop_bbox=crop_bbox,
                highlight_bbox=highlight_bbox,
                out_path=out_path,
                dpi=dpi
            )
            print(f"Saved: {saved}")
            results.append(saved)

    except Exception as e:
        print(f"Error: {e}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
