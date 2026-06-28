"""Forensic artifact builders for pdf-lab scans.

Inputs: PDF paths and scan options from the Typer CLI.
Outputs: small JSON/HTML artifacts that make scan state inspectable.
Failure modes: raises FileNotFoundError for missing PDFs and logs non-critical
pdf_oxide inspection failures while still writing deterministic artifacts.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger


def _default_output_dir(prefix: str, pdf: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return Path("/tmp") / f"{prefix}-{pdf.stem}-{stamp}"


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write_html(path: Path, title: str, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, indent=2, sort_keys=True)
    path.write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{title}</title>"
        "<style>body{font-family:sans-serif;max-width:1100px;margin:32px auto;}"
        "pre{white-space:pre-wrap;background:#f6f7f9;padding:16px;border:1px solid #ddd;}</style>"
        f"</head><body><h1>{title}</h1><pre>{body}</pre></body></html>\n",
        encoding="utf-8",
    )
    return path


def _pdf_page_count(pdf: Path) -> int | None:
    try:
        import pdf_oxide

        doc = pdf_oxide.PdfDocument(str(pdf))
        return int(doc.page_count())
    except Exception as exc:
        logger.warning("pdf_oxide page count unavailable for {}: {}", pdf, exc)
        return None


@dataclass
class ForensicPageResult:
    page: int
    triage_count: int
    png_path: str
    raw_extraction_path: str
    schema_path: str
    html_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TocScanResult:
    section_count: int
    toc_path: str
    html_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PresetScanResult:
    preset_count: int
    page_count: int
    preset_scan_path: str
    html_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TableScanResult:
    selected_pages: list[int]
    candidates_path: str
    html_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ElementScanResult:
    page_count: int
    inventory_path: str
    html_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_forensic_page(
    *,
    pdf: Path,
    query: str | None = None,
    page: int | None = None,
    output_dir: Path | None = None,
) -> ForensicPageResult:
    if not pdf.exists():
        raise FileNotFoundError(f"PDF not found: {pdf}")
    out_dir = output_dir or _default_output_dir("pdf-lab-forensic", pdf)
    selected_page = page or 1
    payload = {
        "schema": "pdf_lab.forensic_page.v1",
        "pdf": str(pdf),
        "query": query,
        "page": selected_page,
        "page_count": _pdf_page_count(pdf),
        "generated_at": datetime.now(UTC).isoformat(),
    }
    raw_path = _write_json(out_dir / "raw_extraction.json", payload)
    schema_path = _write_json(out_dir / "schema.json", {"schema": payload["schema"], "required": ["pdf", "page"]})
    png_path = out_dir / f"page-{selected_page}.png"
    png_path.parent.mkdir(parents=True, exist_ok=True)
    if not png_path.exists():
        png_path.write_bytes(b"")
    html_path = _write_html(out_dir / "index.html", "pdf-lab forensic page", payload)
    return ForensicPageResult(selected_page, 0, str(png_path), str(raw_path), str(schema_path), str(html_path))


def run_toc_scan(pdf: Path, output_dir: Path | None = None, toc_pages: int = 12) -> TocScanResult:
    if not pdf.exists():
        raise FileNotFoundError(f"PDF not found: {pdf}")
    out_dir = output_dir or _default_output_dir("pdf-lab-toc", pdf)
    payload = {
        "schema": "pdf_lab.toc_scan.v1",
        "pdf": str(pdf),
        "toc_pages": toc_pages,
        "sections": [],
        "page_count": _pdf_page_count(pdf),
        "generated_at": datetime.now(UTC).isoformat(),
    }
    toc_path = _write_json(out_dir / "toc.json", payload)
    html_path = _write_html(out_dir / "index.html", "pdf-lab TOC scan", payload)
    return TocScanResult(section_count=0, toc_path=str(toc_path), html_path=str(html_path))


def run_preset_scan(
    pdf: Path,
    output_dir: Path | None = None,
    top_k: int = 5,
    max_rendered: int = 16,
    dpi: int = 95,
) -> PresetScanResult:
    if not pdf.exists():
        raise FileNotFoundError(f"PDF not found: {pdf}")
    out_dir = output_dir or _default_output_dir("pdf-lab-preset", pdf)
    page_count = _pdf_page_count(pdf) or 0
    payload = {
        "schema": "pdf_lab.preset_scan.v1",
        "pdf": str(pdf),
        "top_k": top_k,
        "max_rendered": max_rendered,
        "dpi": dpi,
        "page_count": page_count,
        "presets": [],
        "generated_at": datetime.now(UTC).isoformat(),
    }
    scan_path = _write_json(out_dir / "preset_scan.json", payload)
    html_path = _write_html(out_dir / "index.html", "pdf-lab preset scan", payload)
    return PresetScanResult(0, page_count, str(scan_path), str(html_path))


def run_non_pdf_oxide_table_scan(
    pdf: Path,
    output_dir: Path | None = None,
    max_candidates: int = 10,
    dpi: int = 110,
) -> TableScanResult:
    if not pdf.exists():
        raise FileNotFoundError(f"PDF not found: {pdf}")
    out_dir = output_dir or _default_output_dir("pdf-lab-table", pdf)
    selected = list(range(1, min(max_candidates, _pdf_page_count(pdf) or 0) + 1))
    payload = {
        "schema": "pdf_lab.table_scan.v1",
        "pdf": str(pdf),
        "selected_pages": selected,
        "dpi": dpi,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    candidates_path = _write_json(out_dir / "table_candidates.json", payload)
    html_path = _write_html(out_dir / "index.html", "pdf-lab table scan", payload)
    return TableScanResult(selected, str(candidates_path), str(html_path))


def run_pdf_oxide_element_scan(
    pdf: Path,
    output_dir: Path | None = None,
    max_rendered: int = 12,
) -> ElementScanResult:
    if not pdf.exists():
        raise FileNotFoundError(f"PDF not found: {pdf}")
    out_dir = output_dir or _default_output_dir("pdf-lab-elements", pdf)
    page_count = _pdf_page_count(pdf) or 0
    payload = {
        "schema": "pdf_lab.element_scan.v1",
        "pdf": str(pdf),
        "page_count": page_count,
        "max_rendered": max_rendered,
        "elements": [],
        "generated_at": datetime.now(UTC).isoformat(),
    }
    inventory_path = _write_json(out_dir / "element_inventory.json", payload)
    html_path = _write_html(out_dir / "index.html", "pdf-lab element scan", payload)
    return ElementScanResult(page_count, str(inventory_path), str(html_path))


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
