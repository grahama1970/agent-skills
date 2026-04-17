"""preset_store — persist converged extraction params to ArangoDB via graph_memory."""

from __future__ import annotations

from datetime import datetime

import httpx
from loguru import logger

_BASE = "http://localhost:8601"
_TIMEOUT = 10.0


def store_preset(
    name: str, params: dict, source_doc: str, score: float, audit: dict
) -> str | None:
    """Upsert a converged extraction preset. Returns _key on success."""
    key = f"pdf_extraction_{name}"
    doc = {
        "_key": key,
        "type": "pdf_extraction",
        "title": f"PDF Extraction: {name}",
        "params": params,
        "tags": ["pdf_extraction", "converged", source_doc],
        "taxonomy": {"domain": ["Code"], "function": ["Fix"]},
        "score": score,
        "audit_summary": {
            "rounds": audit.get("total_rounds"),
            "best_strategy": audit.get("best_strategy"),
            "converged_at": datetime.now().isoformat(),
        },
    }
    try:
        r = httpx.post(
            f"{_BASE}/upsert",
            json={"collection": "presets", "documents": [doc]},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        logger.info("stored preset {}", key)
        return key
    except Exception as exc:
        logger.error("store_preset failed: {}", exc)
        return None


def load_preset(name: str) -> dict | None:
    """Load extraction params by preset name. Returns params dict or None."""
    key = f"pdf_extraction_{name}"
    try:
        r = httpx.post(
            f"{_BASE}/recall/by-keys",
            json={"collection": "presets", "keys": [key]},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        docs = r.json().get("documents") or r.json().get("results") or []
        return docs[0]["params"] if docs else None
    except Exception as exc:
        logger.error("load_preset failed: {}", exc)
        return None
