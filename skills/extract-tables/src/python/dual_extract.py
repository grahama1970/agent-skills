"""Dual extraction: Camelot + pdf_oxide in parallel threads.

Runs both extractors concurrently, compares results by bbox location within
hierarchical sections, and quarantines disagreements for /interview review
before ArangoDB storage.

Usage:
    from python.dual_extract import dual_extract
    result = dual_extract("document.pdf", pages="1")
    # result.agreed   — tables where both extractors match
    # result.quarantined — tables needing human review
    # result.best     — best table for each position (auto-selected or human-resolved)
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from loguru import logger


@dataclass
class TableComparison:
    """Comparison of a single table position between extractors."""
    page: int
    bbox: tuple[float, float, float, float]
    native_table: Optional[object] = None  # Table from pdf_oxide
    camelot_table: Optional[object] = None  # Table from Camelot
    agreement: str = "unknown"  # "match", "shape_match", "disagree", "native_only", "camelot_only"
    native_shape: tuple[int, int] = (0, 0)
    camelot_shape: tuple[int, int] = (0, 0)
    native_accuracy: float = 0.0
    camelot_accuracy: float = 0.0
    cell_diffs: int = 0
    best_source: str = ""  # "native", "camelot", "unresolved"
    section_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "page": self.page,
            "bbox": self.bbox,
            "agreement": self.agreement,
            "native_shape": self.native_shape,
            "camelot_shape": self.camelot_shape,
            "native_accuracy": self.native_accuracy,
            "camelot_accuracy": self.camelot_accuracy,
            "cell_diffs": self.cell_diffs,
            "best_source": self.best_source,
            "section_id": self.section_id,
        }


@dataclass
class DualExtractionResult:
    """Result of dual extraction with agreement/quarantine classification."""
    pdf_path: str
    comparisons: list[TableComparison] = field(default_factory=list)
    native_elapsed: float = 0.0
    camelot_elapsed: float = 0.0
    native_error: Optional[str] = None
    camelot_error: Optional[str] = None

    @property
    def agreed(self) -> list[TableComparison]:
        return [c for c in self.comparisons if c.agreement in ("match", "shape_match")]

    @property
    def quarantined(self) -> list[TableComparison]:
        return [c for c in self.comparisons if c.agreement == "disagree"]

    @property
    def native_only(self) -> list[TableComparison]:
        return [c for c in self.comparisons if c.agreement == "native_only"]

    @property
    def camelot_only(self) -> list[TableComparison]:
        return [c for c in self.comparisons if c.agreement == "camelot_only"]

    @property
    def best(self) -> list:
        """Best table objects for each position, ordered by bbox."""
        tables = []
        for c in self.comparisons:
            if c.best_source == "native" and c.native_table:
                tables.append(c.native_table)
            elif c.best_source == "camelot" and c.camelot_table:
                tables.append(c.camelot_table)
            elif c.native_table:
                tables.append(c.native_table)
            elif c.camelot_table:
                tables.append(c.camelot_table)
        return tables

    def summary(self) -> str:
        lines = [f"Dual Extraction: {Path(self.pdf_path).name}"]
        lines.append(f"  Native: {self.native_elapsed:.1f}s | Camelot: {self.camelot_elapsed:.1f}s")
        lines.append(f"  Agreed: {len(self.agreed)} | Quarantined: {len(self.quarantined)}")
        lines.append(f"  Native-only: {len(self.native_only)} | Camelot-only: {len(self.camelot_only)}")
        if self.native_error:
            lines.append(f"  Native error: {self.native_error}")
        if self.camelot_error:
            lines.append(f"  Camelot error: {self.camelot_error}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "pdf_path": self.pdf_path,
            "native_elapsed": self.native_elapsed,
            "camelot_elapsed": self.camelot_elapsed,
            "native_error": self.native_error,
            "camelot_error": self.camelot_error,
            "comparisons": [c.to_dict() for c in self.comparisons],
            "agreed": len(self.agreed),
            "quarantined": len(self.quarantined),
        }


def _bbox_iou(a: tuple, b: tuple) -> float:
    """Compute intersection-over-union between two bboxes."""
    x0 = max(a[0], b[0])
    y0 = max(a[1], b[1])
    x1 = min(a[2], b[2])
    y1 = min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = (x1 - x0) * (y1 - y0)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _extract_native(pdf_path: str, pages: str, flavor: str) -> dict:
    """Run pdf_oxide extraction in a thread."""
    import sys
    from pathlib import Path
    skill_dir = Path(__file__).resolve().parent.parent.parent
    if str(skill_dir / "src") not in sys.path:
        sys.path.insert(0, str(skill_dir / "src"))

    from python.extract_tables import read_pdf

    t0 = time.monotonic()
    try:
        result = read_pdf(pdf_path, pages=pages, flavor=flavor)
        tables = list(result)
        elapsed = time.monotonic() - t0
        return {"tables": tables, "elapsed": elapsed, "error": None}
    except Exception as e:
        return {"tables": [], "elapsed": time.monotonic() - t0, "error": str(e)}


def _extract_camelot(pdf_path: str, pages: str, flavor: str) -> dict:
    """Run Camelot extraction in a thread."""
    t0 = time.monotonic()
    try:
        # Ensure camelot is importable — try installed package first,
        # then fall back to source at ~/workspace/experiments/camelot
        import sys
        try:
            import camelot
        except ImportError:
            camelot_src = str(Path.home() / "workspace" / "experiments" / "camelot")
            if camelot_src not in sys.path:
                sys.path.append(camelot_src)
            import camelot

        cam_tables = camelot.read_pdf(pdf_path, flavor=flavor, pages=pages)
        elapsed = time.monotonic() - t0
        return {"tables": cam_tables, "elapsed": elapsed, "error": None}
    except Exception as e:
        return {"tables": [], "elapsed": time.monotonic() - t0, "error": str(e)}


def _compare_cells(native_data, cam_df) -> int:
    """Count cell-level differences between native and Camelot tables."""
    cam_data = cam_df.values.tolist() if not cam_df.empty else []
    if not native_data or not cam_data:
        return -1

    n_rows = min(len(native_data), len(cam_data))
    n_cols = min(
        len(native_data[0]) if native_data else 0,
        len(cam_data[0]) if cam_data else 0,
    )
    diffs = 0
    for r in range(n_rows):
        for c in range(n_cols):
            nat = str(native_data[r][c]).strip() if isinstance(native_data[r], list) else ""
            cam = str(cam_data[r][c]).strip()
            if nat != cam:
                diffs += 1
    return diffs


def _cam_bbox(cam_table, page_height: float = 0.0) -> tuple[float, float, float, float]:
    """Extract bbox from Camelot table, converting to top-left origin.

    Camelot uses bottom-left origin (PDF default). pdf_oxide uses top-left.
    Convert: top_left_y = page_height - bottom_left_y
    """
    bb = getattr(cam_table, "_bbox", None)
    if not bb or len(bb) != 4:
        return (0.0, 0.0, 0.0, 0.0)
    x0, bl_y0, x1, bl_y1 = bb
    if page_height > 0:
        # Convert: y_top = page_height - y_bottom
        tl_y0 = page_height - bl_y1  # top of table
        tl_y1 = page_height - bl_y0  # bottom of table
        return (x0, tl_y0, x1, tl_y1)
    return tuple(bb)


def dual_extract(
    pdf_path: str,
    pages: str = "1",
    flavor: str = "lattice",
    iou_threshold: float = 0.3,
) -> DualExtractionResult:
    """Run both extractors in parallel and compare results.

    Tables are matched by bbox overlap (IoU > threshold).
    Matched tables are compared cell-by-cell.
    Unmatched tables are classified as native-only or camelot-only.

    Args:
        pdf_path: Path to PDF file
        pages: Page specification (e.g. "1", "1,2,3", "all")
        flavor: Extraction flavor ("lattice", "stream", "auto")
        iou_threshold: Minimum bbox IoU to consider tables as matching

    Returns:
        DualExtractionResult with comparison details
    """
    result = DualExtractionResult(pdf_path=pdf_path)

    # Run both extractors in parallel threads
    with ThreadPoolExecutor(max_workers=2) as executor:
        native_future = executor.submit(_extract_native, pdf_path, pages, flavor)
        camelot_future = executor.submit(_extract_camelot, pdf_path, pages, flavor)

        native_result = native_future.result()
        camelot_result = camelot_future.result()

    result.native_elapsed = native_result["elapsed"]
    result.camelot_elapsed = camelot_result["elapsed"]
    result.native_error = native_result["error"]
    result.camelot_error = camelot_result["error"]

    native_tables = native_result["tables"]
    cam_tables = camelot_result["tables"]

    logger.info(
        "Dual extract {}: native={} tables ({:.1f}s), camelot={} tables ({:.1f}s)",
        Path(pdf_path).name, len(native_tables), result.native_elapsed,
        len(cam_tables), result.camelot_elapsed,
    )

    # Get page height for coordinate conversion (Camelot uses bottom-left origin)
    page_height = 0.0
    try:
        from python.pdf_bridge import get_page_dimensions
        _, page_height = get_page_dimensions(pdf_path, 0)
    except Exception:
        # Fallback: standard letter page height
        page_height = 792.0

    # Match tables by bbox IoU
    native_matched = set()
    cam_matched = set()

    for ni, nt in enumerate(native_tables):
        best_iou = 0.0
        best_ci = -1
        for ci, ct in enumerate(cam_tables):
            if ci in cam_matched:
                continue
            cam_bb = _cam_bbox(ct, page_height)
            iou = _bbox_iou(nt.bbox, cam_bb)
            if iou > best_iou:
                best_iou = iou
                best_ci = ci

        if best_iou >= iou_threshold and best_ci >= 0:
            # Matched pair
            ct = cam_tables[best_ci]
            native_matched.add(ni)
            cam_matched.add(best_ci)

            cam_df = ct.df
            nat_rows = nt.rows
            nat_cols = nt.cols
            cam_rows = cam_df.shape[0]
            cam_cols = cam_df.shape[1]

            comp = TableComparison(
                page=nt.page_number,
                bbox=nt.bbox,
                native_table=nt,
                camelot_table=ct,
                native_shape=(nat_rows, nat_cols),
                camelot_shape=(cam_rows, cam_cols),
                native_accuracy=nt.accuracy,
                camelot_accuracy=ct.parsing_report.get("accuracy", 0),
                section_id=nt.section_id,
            )

            if nat_rows == cam_rows and nat_cols == cam_cols:
                # Same shape — compare cells
                cell_diffs = _compare_cells(nt._data, cam_df)
                comp.cell_diffs = cell_diffs
                if cell_diffs == 0:
                    comp.agreement = "match"
                    # Pick higher accuracy
                    comp.best_source = "native" if comp.native_accuracy >= comp.camelot_accuracy else "camelot"
                elif cell_diffs <= 5:
                    comp.agreement = "shape_match"
                    comp.best_source = "native" if comp.native_accuracy >= comp.camelot_accuracy else "camelot"
                else:
                    comp.agreement = "disagree"
                    comp.best_source = "unresolved"
            else:
                # Different shapes
                comp.agreement = "disagree"
                comp.best_source = "unresolved"

            result.comparisons.append(comp)

    # Unmatched native tables
    for ni, nt in enumerate(native_tables):
        if ni not in native_matched:
            # Check for degenerate tables (1x1)
            if nt.rows <= 1 and nt.cols <= 1:
                continue  # Skip noise
            comp = TableComparison(
                page=nt.page_number,
                bbox=nt.bbox,
                native_table=nt,
                agreement="native_only",
                native_shape=(nt.rows, nt.cols),
                native_accuracy=nt.accuracy,
                best_source="native",
                section_id=nt.section_id,
            )
            result.comparisons.append(comp)

    # Unmatched Camelot tables
    for ci, ct in enumerate(cam_tables):
        if ci not in cam_matched:
            cam_df = ct.df
            cam_bb = _cam_bbox(ct, page_height)
            comp = TableComparison(
                page=ct.parsing_report.get("page", 0),
                bbox=cam_bb,
                camelot_table=ct,
                agreement="camelot_only",
                camelot_shape=(cam_df.shape[0], cam_df.shape[1]),
                camelot_accuracy=ct.parsing_report.get("accuracy", 0),
                best_source="camelot",
            )
            result.comparisons.append(comp)

    # Sort comparisons by reading order (page, y0, x0)
    result.comparisons.sort(key=lambda c: (c.page, c.bbox[1], c.bbox[0]))

    return result


def quarantine_to_jsonl(result: DualExtractionResult, output_path: str):
    """Write quarantined comparisons to JSONL for /interview review."""
    quarantined = result.quarantined
    if not quarantined:
        return

    with open(output_path, "a") as f:
        for comp in quarantined:
            entry = {
                "pdf_path": result.pdf_path,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "reason": "extractor_disagreement",
                "page": comp.page,
                "bbox": comp.bbox,
                "native_shape": comp.native_shape,
                "camelot_shape": comp.camelot_shape,
                "native_accuracy": comp.native_accuracy,
                "camelot_accuracy": comp.camelot_accuracy,
                "cell_diffs": comp.cell_diffs,
                "questions": [
                    {
                        "id": f"table_p{comp.page}_resolve",
                        "text": (
                            f"Table on page {comp.page} at bbox {comp.bbox}: "
                            f"Native extracted {comp.native_shape[0]}x{comp.native_shape[1]} "
                            f"(acc={comp.native_accuracy:.0f}%), "
                            f"Camelot extracted {comp.camelot_shape[0]}x{comp.camelot_shape[1]} "
                            f"(acc={comp.camelot_accuracy:.0f}%). "
                            f"Which extraction is correct?"
                        ),
                        "type": "select",
                        "options": [
                            f"Native ({comp.native_shape[0]}x{comp.native_shape[1]})",
                            f"Camelot ({comp.camelot_shape[0]}x{comp.camelot_shape[1]})",
                            "Neither — skip this table",
                            "Both wrong — needs manual extraction",
                        ],
                    }
                ],
            }
            f.write(json.dumps(entry) + "\n")

    logger.info("Quarantined %d tables to %s", len(quarantined), output_path)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m python.dual_extract <pdf_path> [pages] [flavor]")
        sys.exit(1)

    pdf = sys.argv[1]
    pages = sys.argv[2] if len(sys.argv) > 2 else "1"
    flavor = sys.argv[3] if len(sys.argv) > 3 else "lattice"

    result = dual_extract(pdf, pages=pages, flavor=flavor)
    print(result.summary())
    print(json.dumps(result.to_dict(), indent=2))
