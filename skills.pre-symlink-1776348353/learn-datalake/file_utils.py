"""File I/O utilities for learn-datalake.

Purpose:
- JSON loading, file scanning, state persistence, and non-PDF memory ingestion.

Inputs:
- File paths, extension sets, memory scope strings.

Outputs:
- Loaded JSON, file state dicts, ingestion stats.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from loguru import logger

from config import MEMORY_DIR
from subprocess_exec import run_with_watchdog
from task_monitor_client import write_task_state


def json_load(path: Path) -> Any:
    """Load and parse a JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def scan_files(root: Path, exts: Iterable[str]) -> Dict[str, float]:
    """Scan root recursively for files matching extensions, returning path→mtime map."""
    suffixes = {ext.lower() for ext in exts}
    state: Dict[str, float] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in suffixes:
            state[str(path)] = path.stat().st_mtime
    return state


def changed_files(prev: Dict[str, float], curr: Dict[str, float]) -> List[Path]:
    """Return sorted list of files that are new or modified between two state snapshots."""
    changed = []
    for path_str, mtime in curr.items():
        if prev.get(path_str) != mtime:
            changed.append(Path(path_str))
    return sorted(changed)


def load_state(path: Path) -> Dict[str, float]:
    """Load a previously saved file state snapshot."""
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return {str(k): float(v) for k, v in payload.items()}
    except (json.JSONDecodeError, ValueError, TypeError):
        logger.debug(f"state_load_failed path={path}")
        return {}
    return {}


def save_state(path: Path, state: Dict[str, float]) -> None:
    """Persist a file state snapshot to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def ingest_non_pdf_files(
    files: List[Path],
    memory_scope: str,
    *,
    watchdog_seconds: int,
    watchdog_poll_seconds: int,
    state_file: Optional[Path] = None,
    prior_completed: int = 0,
) -> Dict[str, int]:
    """DEPRECATED: All formats now route through the unified extraction pipeline.

    Non-PDF files (DOCX, HTML, PPTX, etc.) are discovered and extracted by
    review-pdf/verify/discovery.py:_discover_extractable_files() and scored
    through the same quality pipeline as PDFs.

    This function is kept as a no-op for backward compatibility with callers
    that haven't been updated yet. It logs a deprecation warning and returns
    zero counts.
    """
    logger.warning(
        "ingest_non_pdf_files is DEPRECATED — all formats now route through "
        "the unified extraction pipeline. Skipping raw ingest."
    )
    return {"ok": 0, "failed": 0}
