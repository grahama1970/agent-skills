"""learn-datalake coverage and gap analysis module.

Sector constants, coverage reporting, URL candidate handling,
and gap-fill manifest generation.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from config import DOC_EXTENSIONS, DOGPILE_DIR
from file_utils import json_load as _json_load

SECTOR_KEYS = [
    "arxiv",
    "dtic",
    "faa",
    "nasa",
    "nist",
    "ietf",
    "industry",
    "adversarial",
    "edge_cases",
]

SECTOR_DOMAIN_HINTS: dict[str, list[str]] = {
    "arxiv": ["arxiv.org"],
    "dtic": ["dtic.mil", "apps.dtic.mil"],
    "faa": ["faa.gov"],
    "nasa": ["nasa.gov", "ntrs.nasa.gov"],
    "nist": ["nist.gov", "nvlpubs.nist.gov"],
    "ietf": ["ietf.org", "rfc-editor.org", "datatracker.ietf.org"],
    "industry": [
        "ti.com",
        "nxp.com",
        "microchip.com",
        "infineon.com",
        "analog.com",
        "st.com",
        "intel.com",
        "amd.com",
        "nvidia.com",
        "qualcomm.com",
    ],
    "adversarial": [
        "courtlistener.com",
        "law.cornell.edu",
        "cia.gov",
        "justice.gov",
        "archive.org",
        "loc.gov",
    ],
    "edge_cases": [],
}

CANDIDATE_URL_FILES = [
    "expansion_manifest.txt",
    "industry_pdfs.txt",
    "finance_pdfs.txt",
    "finance_pdfs_v2.txt",
    "adversarial_pdfs.txt",
    "adversarial_pdfs_v2.txt",
]


def _count_doc_extensions(root: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for ext in sorted(DOC_EXTENSIONS):
        counts[ext] = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix in DOC_EXTENSIONS:
            counts[suffix] = counts.get(suffix, 0) + 1
    return counts


def _sector_pdf_counts(root: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for sector in SECTOR_KEYS:
        sector_dir = root / sector
        if sector_dir.is_dir():
            counts[sector] = len(list(sector_dir.rglob("*.pdf")))
        else:
            counts[sector] = 0
    return counts


def _find_consumer_summaries(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("consumer_summary.json") if path.is_file())


def _summary_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("items")
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    return []


def _domain_from_url(url: str) -> str:
    parsed = urlparse(url)
    return (parsed.netloc or "").lower()


def _sector_for_domain(domain: str) -> str | None:
    for sector, hints in SECTOR_DOMAIN_HINTS.items():
        if any(hint in domain for hint in hints):
            return sector
    return None


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


def _source_domain_pdf_counts(root: Path) -> dict[str, int]:
    domain_counts: dict[str, int] = {}
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


def _sector_gaps(sector_counts: dict[str, int], target_pdf_per_sector: int) -> dict[str, int]:
    gaps: dict[str, int] = {}
    for sector in SECTOR_KEYS:
        current = sector_counts.get(sector, 0)
        gaps[sector] = max(target_pdf_per_sector - current, 0)
    return gaps


def _coverage_report(root: Path, target_pdf_per_sector: int) -> dict[str, Any]:
    extension_counts = _count_doc_extensions(root)
    sector_counts = _sector_pdf_counts(root)
    sector_gap_counts = _sector_gaps(sector_counts, target_pdf_per_sector)
    domain_counts = _source_domain_pdf_counts(root)
    report: dict[str, Any] = {
        "root": str(root),
        "timestamp": int(time.time()),
        "targets": {"pdf_per_sector": target_pdf_per_sector},
        "totals": {
            "pdf": extension_counts.get(".pdf", 0),
            "documents_by_extension": extension_counts,
        },
        "sectors": {
            "pdf_counts": sector_counts,
            "pdf_gap_counts": sector_gap_counts,
            "sectors_below_target": [k for k, v in sector_gap_counts.items() if v > 0],
        },
        "source_domains": {
            "top_pdf_domains": dict(list(domain_counts.items())[:50]),
            "domain_count_total": len(domain_counts),
        },
    }
    return report


def _read_candidate_urls() -> list[str]:
    urls: list[str] = []
    for filename in CANDIDATE_URL_FILES:
        path = DOGPILE_DIR / filename
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            value = line.strip()
            if value.startswith("http://") or value.startswith("https://"):
                urls.append(value)
    # Preserve order while deduping.
    seen: set[str] = set()
    deduped: list[str] = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        deduped.append(url)
    return deduped


def _urls_by_sector(urls: list[str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {sector: [] for sector in SECTOR_KEYS}
    for url in urls:
        sector = _sector_for_domain(_domain_from_url(url))
        if sector is None:
            continue
        grouped[sector].append(url)
    return grouped


def _write_manifest(path: Path, urls: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(urls) + ("\n" if urls else "")
    path.write_text(payload, encoding="utf-8")


def _next_expansion_batch_dir(base_dir: Path) -> Path:
    """Return the next available expansion batch directory under base_dir."""
    base_dir.mkdir(parents=True, exist_ok=True)
    max_index = 0
    for candidate in base_dir.glob("expansion_batch_*"):
        if not candidate.is_dir():
            continue
        suffix = candidate.name.removeprefix("expansion_batch_")
        if not suffix.isdigit():
            continue
        max_index = max(max_index, int(suffix))
    next_index = max_index + 1
    return base_dir / f"expansion_batch_{next_index}"
