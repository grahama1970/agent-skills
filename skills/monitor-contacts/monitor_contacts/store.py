"""Contact store over the /memory `contact_snapshots` ArangoDB collection.

This skill does NOT invent storage. The collection already exists and already
holds real contacts (created 2026-08-13 by the nightly opportunity run), so
monitor-contacts operates over the same records rather than starting a rival
one. Reads use /recall/by-keys (exact key) because the semantic recall view
does not index these collections (graph-memory-operator#120).

Everything is fail-soft: a memory-service outage yields empty results and an
honest receipt, never a fabricated contact or change.
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
from typing import Any

from loguru import logger

COLLECTION = "contact_snapshots"
DEFAULT_MEMORY_URL = "http://127.0.0.1:8601"


def contact_key(name: str) -> str:
    """Stable id for a person. Org is excluded on purpose: recognising the same
    person at a DIFFERENT company is the signal this skill exists to catch."""
    norm = " ".join(str(name or "").lower().split())
    return "c-" + hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def _post(memory_url: str, path: str, payload: dict[str, Any], timeout: int = 20) -> dict[str, Any]:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{memory_url}{path}", data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def count(memory_url: str = DEFAULT_MEMORY_URL) -> int:
    try:
        return int(_post(memory_url, "/count", {"collection": COLLECTION}).get("count") or 0)
    except Exception as exc:  # noqa: BLE001 - absence is reported, never guessed
        logger.warning("contact count unavailable: {}", exc)
        return -1


def load(keys: list[str], memory_url: str = DEFAULT_MEMORY_URL) -> dict[str, dict[str, Any]]:
    """Exact-key read of stored contacts. {} on any failure."""
    if not keys:
        return {}
    try:
        data = _post(memory_url, "/recall/by-keys", {"collection": COLLECTION, "keys": keys})
    except Exception as exc:  # noqa: BLE001
        logger.warning("contact read unavailable: {}", exc)
        return {}
    out: dict[str, dict[str, Any]] = {}
    for doc in data.get("documents", []) or []:
        d = doc.get("document") or doc
        if d.get("_key"):
            out[str(d["_key"])] = d
    return out


def save(contacts: list[dict[str, Any]], memory_url: str = DEFAULT_MEMORY_URL) -> int:
    """Upsert contacts. Returns how many were stored."""
    stored = 0
    for c in contacts:
        try:
            res = _post(memory_url, "/store", {"document": c, "collection": COLLECTION})
            stored += 1 if res.get("stored") else 0
        except Exception as exc:  # noqa: BLE001 - persistence never fails a cycle
            logger.warning("contact store skipped for {}: {}", c.get("name"), exc)
    return stored
