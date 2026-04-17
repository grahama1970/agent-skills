"""Utility helpers for filesystem, JSON, and numeric coercion.

Purpose:
- centralize common helpers used by audit modules.

Inputs:
- filesystem paths, generic JSON-like values.

Outputs:
- parsed JSON payloads, stable ids, and serialized report files.

Failure modes:
- malformed JSON yields empty dict with warning-level fallback behavior.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

from .models import DOMAIN_HINTS


def safe_json(path: Optional[Path]) -> Dict[str, Any]:
    """Read JSON file into dict, returning empty dict on parse errors."""
    if path is None:
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"Could not parse JSON {path}: {exc}")
        return {}


def to_float(value: Any, default: float = 0.0) -> float:
    """Best-effort numeric conversion with fallback default."""
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def detect_domain(pdf_path: Optional[Path], run_dir: Path) -> str:
    """Infer corpus domain from known directory hints."""
    candidates = []
    if pdf_path:
        candidates.extend(part.lower() for part in pdf_path.parts)
    candidates.extend(part.lower() for part in run_dir.parts)
    for key, value in DOMAIN_HINTS.items():
        if key in candidates:
            return value
    return "unknown"


def doc_id_from_path(pdf_path: Optional[Path], run_dir: Path) -> str:
    """Create stable doc id from pdf stem or run dir."""
    base = pdf_path.stem if pdf_path else run_dir.name
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", base)


def write_json(path: Path, data: Any) -> None:
    """Write pretty JSON to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def append_jsonl(path: Path, record: Dict[str, Any]) -> None:
    """Append one JSON object line to jsonl file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")

