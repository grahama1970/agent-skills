"""Corpus coverage analysis and gap-fill fetching for learn-datalake.

Purpose:
- Assess document corpus coverage across sectors.
- Plan and execute gap-fill URL downloads.

Inputs:
- Corpus root directory, candidate URL files, sector configuration.

Outputs:
- Coverage reports (JSON), manifests, fetcher invocations.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from loguru import logger

from config import (
    CANDIDATE_URL_FILES,
    DOC_EXTENSIONS,
    DOGPILE_DIR,
    FETCHER_DIR,
    SECTOR_DOMAIN_HINTS,
    SECTOR_KEYS,
    CommandResult,
)
from file_utils import json_load
from subprocess_exec import run_with_watchdog
from task_monitor_client import write_task_state


def count_doc_extensions(root: Path) -> Dict[str, int]:
    """Count files by document extension under root."""
    counts: Dict[str, int] = {}
    for ext in sorted(DOC_EXTENSIONS):
        counts[ext] = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix in DOC_EXTENSIONS:
            counts[suffix] = counts.get(suffix, 0) + 1
    return counts


def sector_pdf_counts(root: Path) -> Dict[str, int]:
    """Count PDFs in each sector subdirectory."""
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


def _downloaded_url_set(root: Path) -> set[str]:
    seen: set[str] = set()
    for summary in _find_consumer_summaries(root):
        try:
            payload = json_load(summary)
        except (ValueError, OSError):
            continue
        for item in _summary_items(payload):
            url = str(item.get("original_url", "")).strip()
            if url:
                seen.add(url)
    return seen


def source_domain_pdf_counts(root: Path) -> Dict[str, int]:
    """Count successfully-downloaded PDFs by source domain."""
    domain_counts: Dict[str, int] = {}
    for summary in _find_consumer_summaries(root):
        try:
            payload = json_load(summary)
        except (ValueError, OSError):
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


def sector_gaps(sector_counts: Dict[str, int], target_pdf_per_sector: int) -> Dict[str, int]:
    """Compute per-sector PDF deficit relative to target."""
    gaps: Dict[str, int] = {}
    for sector in SECTOR_KEYS:
        current = sector_counts.get(sector, 0)
        gaps[sector] = max(target_pdf_per_sector - current, 0)
    return gaps


def coverage_report(root: Path, target_pdf_per_sector: int) -> Dict[str, Any]:
    """Build a machine-readable corpus coverage report."""
    extension_counts = count_doc_extensions(root)
    sc = sector_pdf_counts(root)
    gap_counts = sector_gaps(sc, target_pdf_per_sector)
    domain_counts = source_domain_pdf_counts(root)
    return {
        "root": str(root),
        "timestamp": int(time.time()),
        "targets": {"pdf_per_sector": target_pdf_per_sector},
        "totals": {
            "pdf": extension_counts.get(".pdf", 0),
            "documents_by_extension": extension_counts,
        },
        "sectors": {
            "pdf_counts": sc,
            "pdf_gap_counts": gap_counts,
            "sectors_below_target": [k for k, v in gap_counts.items() if v > 0],
        },
        "source_domains": {
            "top_pdf_domains": dict(list(domain_counts.items())[:50]),
            "domain_count_total": len(domain_counts),
        },
    }


def read_candidate_urls() -> List[str]:
    """Read and deduplicate candidate URLs from dogpile manifest files."""
    urls: List[str] = []
    for filename in CANDIDATE_URL_FILES:
        path = DOGPILE_DIR / filename
        if not path.exists():
            continue
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


def urls_by_sector(urls: List[str]) -> Dict[str, List[str]]:
    """Group URLs by sector based on domain hints."""
    grouped: Dict[str, List[str]] = {sector: [] for sector in SECTOR_KEYS}
    for url in urls:
        sector = _sector_for_domain(_domain_from_url(url))
        if sector is None:
            continue
        grouped[sector].append(url)
    return grouped


def write_manifest(path: Path, urls: List[str]) -> None:
    """Write a URL manifest file (one URL per line)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(urls) + ("\n" if urls else "")
    path.write_text(payload, encoding="utf-8")


def next_expansion_batch_dir(base_dir: Path) -> Path:
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
    return base_dir / f"expansion_batch_{max_index + 1}"


def downloaded_url_set(root: Path) -> set[str]:
    """Public accessor for the set of already-downloaded URLs."""
    return _downloaded_url_set(root)


def run_fetcher_manifest(
    manifest_path: Path,
    out_dir: Path,
    *,
    watchdog_seconds: int,
    watchdog_poll_seconds: int,
    state_file: Optional[Path] = None,
) -> CommandResult:
    """Invoke the fetcher skill to download URLs from a manifest."""
    cmd = (
        f"cd {FETCHER_DIR} && "
        f"./run.sh get-manifest \"{manifest_path}\" "
        f"--out \"{out_dir}\" --soft-fail"
    )
    return run_with_watchdog(
        cmd,
        timeout=21600,
        watchdog_seconds=watchdog_seconds,
        watchdog_poll_seconds=watchdog_poll_seconds,
        stream_stdout=True,
        progress_callback=(
            (lambda progress: write_task_state(
                state_file,
                {
                    "completed": 0,
                    "stats": {
                        "elapsed_seconds": round(progress["elapsed_seconds"], 2),
                        "last_output_age_seconds": round(progress["last_output_age_seconds"], 2),
                    },
                    "current_item": str(manifest_path),
                },
            ))
            if state_file is not None
            else None
        ),
    )
