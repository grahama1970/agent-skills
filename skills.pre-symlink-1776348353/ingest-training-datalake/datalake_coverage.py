"""Coverage analysis functions for training datalake ingestion."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from datalake_config import DOC_EXTENSIONS, SECTOR_DOMAIN_HINTS, SECTOR_KEYS
from datalake_utils import _json_load


def _count_doc_extensions(root: Path) -> Dict[str, int]:
    counts = {ext: 0 for ext in sorted(DOC_EXTENSIONS)}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix in DOC_EXTENSIONS:
            counts[suffix] = counts.get(suffix, 0) + 1
    return counts


def _sector_pdf_counts(root: Path) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for sector in SECTOR_KEYS:
        sector_dir = root / sector
        if sector_dir.is_dir():
            counts[sector] = len(list(sector_dir.rglob("*.pdf")))
        else:
            counts[sector] = 0
    return counts


def _find_consumer_summaries(root: Path) -> List[Path]:
    return sorted(path for path in root.rglob("consumer_summary.json") if path.is_file())


def _summary_items(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    items = payload.get("items")
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    return []


def _domain_from_url(url: str) -> str:
    parsed = urlparse(url)
    return (parsed.netloc or "").lower()


def _sector_for_domain(domain: str) -> Optional[str]:
    for sector, hints in SECTOR_DOMAIN_HINTS.items():
        if any(hint in domain for hint in hints):
            return sector
    return None


def _sector_pdf_counts_from_source_domains(root: Path) -> Dict[str, int]:
    counts: Dict[str, int] = {sector: 0 for sector in SECTOR_KEYS}
    for summary in _find_consumer_summaries(root):
        try:
            payload = _json_load(summary)
        except Exception:
            continue
        for item in _summary_items(payload):
            if str(item.get("verdict")) != "ok":
                continue
            url = str(item.get("original_url", "")).strip()
            if not url:
                continue
            sector = _sector_for_domain(_domain_from_url(url))
            if sector is None:
                continue
            counts[sector] = counts.get(sector, 0) + 1
    return counts


def _sector_gap_counts(sector_counts: Dict[str, int], target_pdf_per_sector: int) -> Dict[str, int]:
    gaps: Dict[str, int] = {}
    for sector in SECTOR_KEYS:
        gaps[sector] = max(target_pdf_per_sector - sector_counts.get(sector, 0), 0)
    return gaps


def _source_domain_pdf_counts(root: Path) -> Dict[str, int]:
    domain_counts: Dict[str, int] = {}
    for summary in _find_consumer_summaries(root):
        try:
            payload = _json_load(summary)
        except Exception:
            continue
        for item in _summary_items(payload):
            if str(item.get("verdict")) != "ok":
                continue
            url = str(item.get("original_url", "")).strip()
            if not url:
                continue
            domain = _domain_from_url(url)
            if not domain:
                continue
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
    return dict(sorted(domain_counts.items(), key=lambda kv: kv[1], reverse=True))


def _downloaded_url_set(root: Path) -> set[str]:
    seen: set[str] = set()
    for summary in _find_consumer_summaries(root):
        try:
            payload = _json_load(summary)
        except Exception:
            continue
        for item in _summary_items(payload):
            url = str(item.get("original_url", "")).strip()
            if url:
                seen.add(url)
    return seen


def _build_coverage_report(root: Path, target_pdf_per_sector: int) -> Dict[str, Any]:
    extension_counts = _count_doc_extensions(root)
    dir_sector_counts = _sector_pdf_counts(root)
    source_sector_counts = _sector_pdf_counts_from_source_domains(root)
    effective_sector_counts = {
        sector: max(dir_sector_counts.get(sector, 0), source_sector_counts.get(sector, 0))
        for sector in SECTOR_KEYS
    }
    gaps = _sector_gap_counts(effective_sector_counts, target_pdf_per_sector)
    domains = _source_domain_pdf_counts(root)
    return {
        "timestamp": int(time.time()),
        "root": str(root),
        "targets": {"pdf_per_sector": target_pdf_per_sector},
        "totals": {
            "pdf": extension_counts.get(".pdf", 0),
            "documents_by_extension": extension_counts,
        },
        "sectors": {
            "pdf_counts_effective": effective_sector_counts,
            "pdf_counts_by_dir": dir_sector_counts,
            "pdf_counts_by_source_domain": source_sector_counts,
            "pdf_gap_counts": gaps,
            "sectors_below_target": [k for k, v in gaps.items() if v > 0],
        },
        "source_domains": {
            "top_pdf_domains": dict(list(domains.items())[:50]),
            "domain_count_total": len(domains),
        },
    }
