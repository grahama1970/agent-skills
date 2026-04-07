"""URL planning and selection for training datalake ingestion."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List

from datalake_config import DEFAULT_CANDIDATE_FILES, SECTOR_KEYS
from datalake_coverage import (
    _build_coverage_report,
    _domain_from_url,
    _downloaded_url_set,
    _sector_for_domain,
)


def _resolve_candidate_files(extra_files: Iterable[Path]) -> List[Path]:
    result: List[Path] = []
    for path in [*DEFAULT_CANDIDATE_FILES, *list(extra_files)]:
        if path.exists() and path.is_file():
            result.append(path)
    return result


def _read_candidate_urls(files: Iterable[Path]) -> List[str]:
    urls: List[str] = []
    for path in files:
        for line in path.read_text(encoding="utf-8").splitlines():
            value = line.strip()
            if value.startswith("http://") or value.startswith("https://"):
                urls.append(value)
    seen: set[str] = set()
    deduped: List[str] = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        deduped.append(url)
    return deduped


def _group_urls_by_sector(urls: Iterable[str]) -> Dict[str, List[str]]:
    grouped: Dict[str, List[str]] = {sector: [] for sector in SECTOR_KEYS}
    for url in urls:
        domain = _domain_from_url(url)
        sector = _sector_for_domain(domain)
        if sector is None:
            continue
        grouped[sector].append(url)
    return grouped


def _write_manifest(path: Path, urls: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(urls)
    if body:
        body += "\n"
    path.write_text(body, encoding="utf-8")


def _select_gap_urls(
    *,
    root: Path,
    target_pdf_per_sector: int,
    per_sector_limit: int,
    extra_candidate_files: Iterable[Path],
) -> Dict[str, Any]:
    coverage = _build_coverage_report(root, target_pdf_per_sector)
    gaps: Dict[str, int] = coverage["sectors"]["pdf_gap_counts"]
    downloaded = _downloaded_url_set(root)
    candidate_files = _resolve_candidate_files(extra_candidate_files)
    candidates = _read_candidate_urls(candidate_files)
    grouped = _group_urls_by_sector(candidates)

    selected_urls: List[str] = []
    selected_by_sector: Dict[str, int] = {}
    available_by_sector: Dict[str, int] = {}

    for sector in SECTOR_KEYS:
        need = gaps.get(sector, 0)
        pool = [url for url in grouped.get(sector, []) if url not in downloaded]
        available_by_sector[sector] = len(pool)
        if need <= 0:
            selected_by_sector[sector] = 0
            continue
        take = min(need, per_sector_limit, len(pool))
        chosen = pool[:take]
        selected_urls.extend(chosen)
        selected_by_sector[sector] = len(chosen)

    seen: set[str] = set()
    final_urls: List[str] = []
    for url in selected_urls:
        if url in seen:
            continue
        seen.add(url)
        final_urls.append(url)

    return {
        "coverage_report": coverage,
        "candidate_files": [str(path) for path in candidate_files],
        "candidate_url_count": len(candidates),
        "already_downloaded_url_count": len(downloaded),
        "selected_urls": final_urls,
        "selected_by_sector": selected_by_sector,
        "available_by_sector": available_by_sector,
    }
