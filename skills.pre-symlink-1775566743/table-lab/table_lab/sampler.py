"""Find representative pages with tables in a PDF.

Uses PyMuPDF or pdf_oxide heuristics to quickly identify pages that
likely contain tables -- no Camelot involved, so this is fast.
"""
from __future__ import annotations

from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None  # type: ignore

try:
    import pdf_oxide
except ImportError:
    pdf_oxide = None  # type: ignore

from .config import MAX_SAMPLE_PAGES, MIN_DRAWINGS_FOR_TABLE


def find_pages_with_tables(
    pdf_path: Path | str,
    max_pages: int = MAX_SAMPLE_PAGES,
    backend: str = "camelot",
) -> list[int]:
    """Return 0-based page numbers that likely contain tables.

    Strategy: scan all pages for horizontal/vertical line segments
    (table gridlines). Pick from first third, middle third, last third
    to get representative coverage.

    Supports 'camelot' (fitz) and 'rust' (pdf_oxide) backends.
    """
    if backend == "rust" and pdf_oxide is not None:
        return _find_pages_rust(pdf_path, max_pages)

    if fitz is None:
        # Fallback: try all pages if no scanning library available
        return list(range(min(max_pages, 10)))

    doc = fitz.open(str(pdf_path))
    candidates: list[tuple[int, int]] = []  # (page_num, line_count)

    for page_num in range(len(doc)):
        page = doc[page_num]
        line_count = _count_table_lines(page)
        if line_count >= MIN_DRAWINGS_FOR_TABLE:
            candidates.append((page_num, line_count))

    doc.close()

    if not candidates:
        return []

    # Pick from first/middle/last thirds for representative coverage
    return _spread_sample(candidates, max_pages)


def _find_pages_rust(pdf_path: Path | str, max_pages: int) -> list[int]:
    """Find pages with tables using pdf_oxide text span heuristics.

    Since pdf_oxide doesn't expose drawing/line primitives directly,
    we use a quick probe: try extracting tables on each page with auto
    flavor and keep pages that return results.
    """
    try:
        doc = pdf_oxide.PdfDocument(str(pdf_path))
        page_count = doc.page_count
        candidates: list[tuple[int, int]] = []

        for page_num in range(page_count):
            try:
                tables = doc.read_pdf(pages=str(page_num + 1), flavor="auto")
                if tables:
                    total_cells = sum(
                        len(t["data"]) * t.get("cols", 1) for t in tables
                    )
                    candidates.append((page_num, total_cells))
            except Exception:
                continue

        if not candidates:
            return []
        return _spread_sample(candidates, max_pages)
    except Exception:
        return list(range(min(max_pages, 3)))


def _count_table_lines(page: fitz.Page) -> int:
    """Count horizontal and vertical line segments on a page.

    Table gridlines appear as short straight lines. We count line
    drawings that are either perfectly horizontal or vertical.
    """
    count = 0
    try:
        drawings = page.get_drawings()
    except Exception:
        return 0

    for d in drawings:
        for item in d.get("items", []):
            if item[0] == "l":  # line segment
                p1, p2 = item[1], item[2]
                dx = abs(p1.x - p2.x)
                dy = abs(p1.y - p2.y)
                # Horizontal or vertical line (tolerance 2pt)
                if dx < 2 or dy < 2:
                    count += 1
    return count


def _spread_sample(
    candidates: list[tuple[int, int]],
    max_pages: int,
) -> list[int]:
    """Pick pages spread across the document.

    Divides candidates into thirds and picks the page with the most
    lines from each third.
    """
    if len(candidates) <= max_pages:
        return [c[0] for c in candidates]

    total = candidates[-1][0] + 1  # total pages in doc (approx)
    third = total / 3

    buckets: list[list[tuple[int, int]]] = [[], [], []]
    for page_num, line_count in candidates:
        if page_num < third:
            buckets[0].append((page_num, line_count))
        elif page_num < 2 * third:
            buckets[1].append((page_num, line_count))
        else:
            buckets[2].append((page_num, line_count))

    picked: list[int] = []
    for bucket in buckets:
        if bucket and len(picked) < max_pages:
            # Pick page with most lines in this third
            best = max(bucket, key=lambda x: x[1])
            picked.append(best[0])

    # If we still need more (e.g., all tables in one third), fill from remainder
    if len(picked) < max_pages:
        all_pages = {p for p, _ in candidates}
        remaining = sorted(all_pages - set(picked))
        for p in remaining:
            if len(picked) >= max_pages:
                break
            picked.append(p)

    return sorted(picked)


def page_summary(pdf_path: Path | str, backend: str = "camelot") -> dict:
    """Quick summary: total pages, pages with tables, sample pages."""
    if backend == "rust" and pdf_oxide is not None:
        try:
            doc = pdf_oxide.PdfDocument(str(pdf_path))
            total = doc.page_count
            table_pages = _find_pages_rust(pdf_path, total)
            sample = _spread_sample(
                [(p, 1) for p in table_pages], MAX_SAMPLE_PAGES
            )
            return {
                "total_pages": total,
                "pages_with_tables": len(table_pages),
                "table_page_numbers": table_pages,
                "sample_pages": sample,
            }
        except Exception:
            pass

    if fitz is None:
        return {"total_pages": 0, "pages_with_tables": 0,
                "table_page_numbers": [], "sample_pages": []}

    doc = fitz.open(str(pdf_path))
    total = len(doc)
    table_pages: list[int] = []

    for page_num in range(total):
        if _count_table_lines(doc[page_num]) >= MIN_DRAWINGS_FOR_TABLE:
            table_pages.append(page_num)

    doc.close()
    sample = _spread_sample(
        [(p, 1) for p in table_pages], MAX_SAMPLE_PAGES
    )

    return {
        "total_pages": total,
        "pages_with_tables": len(table_pages),
        "table_page_numbers": table_pages,
        "sample_pages": sample,
    }
