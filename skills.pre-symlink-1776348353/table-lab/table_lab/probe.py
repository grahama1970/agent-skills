"""Run a single extraction with specific parameters.

Supports two backends:
  - camelot: wraps camelot.read_pdf() (legacy, requires OpenCV + Ghostscript)
  - rust: wraps pdf_oxide.PdfDocument.read_pdf() (pure Rust, no external deps)
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import fitz  # PyMuPDF — used for page rendering in Camelot backend
except ImportError:
    fitz = None  # type: ignore

try:
    from camelot import io as camelot_io
except ImportError:
    camelot_io = None  # type: ignore

try:
    import pdf_oxide
except ImportError:
    pdf_oxide = None  # type: ignore


@dataclass
class ProbeResult:
    """Result of a single Camelot probe on one page."""
    page_num: int  # 0-based
    flavor: str
    line_scale: int | None = None
    edge_tol: int | None = None
    table_count: int = 0
    cell_count: int = 0
    fragmentation: int = 0
    duration_ms: int = 0
    tables_data: list[list[list[str]]] = field(default_factory=list)
    error: str | None = None


def probe_page(
    pdf_path: Path | str,
    page_num: int,
    flavor: str = "lattice",
    line_scale: int | None = None,
    edge_tol: int | None = None,
    process_background: bool = False,
) -> ProbeResult:
    """Extract tables from a single page with specific Camelot parameters.

    Args:
        pdf_path: Path to the PDF file.
        page_num: 0-based page number.
        flavor: 'lattice' or 'stream'.
        line_scale: line_scale parameter (lattice mode).
        edge_tol: edge_tol parameter (stream mode).
        process_background: Whether to process background (lattice mode).

    Returns:
        ProbeResult with extraction metrics.
    """
    if camelot_io is None:
        return ProbeResult(
            page_num=page_num, flavor=flavor,
            error="camelot not installed"
        )

    result = ProbeResult(
        page_num=page_num,
        flavor=flavor,
        line_scale=line_scale,
        edge_tol=edge_tol,
    )

    params: dict[str, Any] = {}
    if flavor == "lattice":
        if line_scale is not None:
            params["line_scale"] = line_scale
        params["process_background"] = process_background
    elif flavor == "stream":
        if edge_tol is not None:
            params["edge_tol"] = edge_tol

    page_str = str(page_num + 1)  # Camelot uses 1-based

    t0 = time.monotonic()
    try:
        tables = camelot_io.read_pdf(
            str(pdf_path),
            pages=page_str,
            flavor=flavor,
            **params,
        )
        result.duration_ms = int((time.monotonic() - t0) * 1000)
        result.table_count = len(tables)

        total_cells = 0
        total_frag = 0
        tables_data = []

        for table in tables:
            df = table.df
            # Cell count: non-empty cells
            total_cells += int(df.astype(str).ne("").sum().sum())
            # Fragmentation: cells where sanitization would change text
            total_frag += _fragmentation_score(df)
            # Store table data as list of lists
            tables_data.append(df.values.tolist())

        result.cell_count = total_cells
        result.fragmentation = total_frag
        result.tables_data = tables_data

    except Exception as e:
        result.duration_ms = int((time.monotonic() - t0) * 1000)
        result.error = str(e)

    return result


def probe_page_image(
    pdf_path: Path | str,
    page_num: int,
    output_dir: Path | None = None,
    backend: str = "camelot",
) -> str | None:
    """Render a page as an image for visual inspection.

    Returns path to the saved image, or None on error.
    Supports both fitz (camelot backend) and pdf_oxide (rust backend).
    """
    if output_dir is None:
        from .config import DATA_DIR
        output_dir = DATA_DIR / "images"
    output_dir.mkdir(parents=True, exist_ok=True)
    img_path = output_dir / f"page_{page_num + 1}.png"

    if backend == "rust" and pdf_oxide is not None:
        try:
            doc = pdf_oxide.PdfDocument(str(pdf_path))
            png_bytes = doc.render_page(page_num, dpi=150)
            with open(img_path, "wb") as f:
                f.write(png_bytes)
            return str(img_path)
        except Exception:
            return None
    elif fitz is not None:
        try:
            doc = fitz.open(str(pdf_path))
            page = doc[page_num]
            pix = page.get_pixmap(dpi=150)
            pix.save(str(img_path))
            doc.close()
            return str(img_path)
        except Exception:
            return None
    return None


def probe_page_rust(
    pdf_path: Path | str,
    page_num: int,
    flavor: str = "lattice",
    line_scale: int | None = None,
    edge_tol: int | None = None,
) -> ProbeResult:
    """Extract tables from a single page using the Rust pdf_oxide backend.

    Same interface as probe_page() but uses pdf_oxide.PdfDocument.read_pdf()
    instead of Camelot. Parameters map directly to the Rust ExtractConfig.
    """
    if pdf_oxide is None:
        return ProbeResult(
            page_num=page_num, flavor=flavor,
            error="pdf_oxide not installed (pip install pdf_oxide or maturin develop)"
        )

    result = ProbeResult(
        page_num=page_num,
        flavor=flavor,
        line_scale=line_scale,
        edge_tol=edge_tol,
    )

    page_str = str(page_num + 1)  # pdf_oxide read_pdf uses 1-based page strings

    kwargs: dict[str, Any] = {"pages": page_str, "flavor": flavor}
    if line_scale is not None:
        kwargs["line_scale"] = line_scale
    if edge_tol is not None:
        kwargs["edge_tol"] = edge_tol

    t0 = time.monotonic()
    try:
        doc = pdf_oxide.PdfDocument(str(pdf_path))
        tables = doc.read_pdf(**kwargs)
        result.duration_ms = int((time.monotonic() - t0) * 1000)
        result.table_count = len(tables)

        total_cells = 0
        total_frag = 0
        tables_data = []

        for table in tables:
            data = table["data"]
            # Cell count: non-empty cells
            for row in data:
                for cell in row:
                    if str(cell).strip():
                        total_cells += 1
            # Fragmentation: check for OCR-style splitting
            total_frag += _fragmentation_score_from_data(data)
            tables_data.append(data)

        result.cell_count = total_cells
        result.fragmentation = total_frag
        result.tables_data = tables_data

    except Exception as e:
        result.duration_ms = int((time.monotonic() - t0) * 1000)
        result.error = str(e)

    return result


def _fragmentation_score_from_data(data: list[list[str]]) -> int:
    """Count fragmented cells in a list-of-lists table (Rust backend format)."""
    count = 0
    for row in data:
        for cell in row:
            cell_str = str(cell).strip()
            if not cell_str:
                continue
            tokens = cell_str.split()
            if len(tokens) < 2:
                continue
            single_letter_count = sum(1 for t in tokens if len(t) == 1 and t.isalpha())
            if single_letter_count >= 3 and single_letter_count / len(tokens) > 0.4:
                count += 1
    return count


def _fragmentation_score(df: Any) -> int:
    """Count cells where text appears fragmented (OCR splitting).

    Targets real OCR fragmentation patterns:
    - "S u b s y s t e m" (single chars separated by spaces)
    - Multiple isolated single-letter tokens in a cell

    Does NOT flag:
    - Normal multi-line content (newlines in lattice cells)
    - Leading/trailing whitespace
    - Normal word spacing
    """
    count = 0
    for cell in df.astype(str).values.flatten():
        cell_str = str(cell).strip()
        if not cell_str:
            continue

        tokens = cell_str.split()
        if len(tokens) < 2:
            continue

        # Count single-letter alpha tokens
        single_letter_count = sum(1 for t in tokens if len(t) == 1 and t.isalpha())

        # Fragmented if >40% of tokens are single letters (OCR splitting)
        if single_letter_count >= 3 and single_letter_count / len(tokens) > 0.4:
            count += 1

    return count
