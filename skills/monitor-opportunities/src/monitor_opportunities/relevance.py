"""Mandate relevance via Memory-backed FlashText — deterministic, NO REGEX.

Replaces substring keyword regex (which mis-fired, e.g. matching "ai" inside
unrelated words) with whole-phrase Flashtext matching against a mandate
vocabulary held in ArangoDB (`opportunity_vocabulary`), per best-practices-python
`correctness-regex-only-known-grammar` and best-practices-arangodb (domain terms
live in ArangoDB, not Python lists). Loads that vocabulary through the Memory
daemon's bounded `/list` endpoint once per process, then reuses the trie for the
nightly batch.

A title/solicitation is mandate-relevant iff it matches >=1 vocabulary concept.
Fail-soft: if Memory is unavailable, returns None so the caller can
fall back to a conservative default instead of crashing the nightly.
"""

from __future__ import annotations

import os
import string
from typing import Any

VOCABULARY_COLLECTION = "opportunity_vocabulary"
_MEMORY_LIST_PAGE_LIMIT = 500
_DEFAULT_VOCABULARY_LIMIT = 5000
_MATCHER_CACHE: dict[tuple[str, int], tuple[Any, bool]] = {}


def clear_mandate_cache() -> None:
    """Clear the process-local vocabulary matcher cache.

    Exists for focused tests and for future long-lived service runners that need
    to force a refresh after a vocabulary ingest.
    """

    _MATCHER_CACHE.clear()


def _memory_base_url() -> str:
    value = (
        os.getenv("MEMORY_API_BASE")
        or os.getenv("MEMORY_SERVICE_URL")
        or os.getenv("MEMORY_API_URL")
        or os.getenv("MEMORY_SERVER_URL")
        or ""
    ).strip()
    if value.startswith(("unix://", "http+unix://")):
        return ""
    return value


def _make_memory_client() -> Any:
    import httpx

    base_url = _memory_base_url()
    if base_url:
        return httpx.Client(base_url=base_url.rstrip("/"), timeout=15)
    socket_path = os.getenv("MEMORY_SOCKET", "").strip()
    service_url = os.getenv("MEMORY_SERVICE_URL", "").strip()
    if not socket_path and service_url.startswith("unix://"):
        socket_path = service_url.removeprefix("unix://")
    if not socket_path:
        socket_path = "/run/user/1000/embry/memory.sock"
    return httpx.Client(
        transport=httpx.HTTPTransport(uds=socket_path),
        base_url="http://localhost",
        timeout=15,
    )


def _vocabulary_limit() -> int:
    raw = os.getenv("MONITOR_OPPORTUNITIES_VOCABULARY_LIMIT", str(_DEFAULT_VOCABULARY_LIMIT))
    try:
        return max(1, int(raw))
    except ValueError:
        return _DEFAULT_VOCABULARY_LIMIT


def _load_vocabulary_docs(collection: str, limit: int) -> list[dict[str, Any]] | None:
    docs: list[dict[str, Any]] = []
    client = None
    try:
        client = _make_memory_client()
        for offset in range(0, limit, _MEMORY_LIST_PAGE_LIMIT):
            batch_limit = min(_MEMORY_LIST_PAGE_LIMIT, limit - offset)
            response = client.post(
                "/list",
                json={
                    "collection": collection,
                    "limit": batch_limit,
                    "offset": offset,
                    "return_fields": [
                        "_id",
                        "_key",
                        "name",
                        "label",
                        "control_id",
                        "key",
                        "aliases",
                        "category",
                        "node_type",
                        "source_framework",
                    ],
                },
            )
            response.raise_for_status()
            batch = response.json().get("documents", [])
            if not isinstance(batch, list):
                return None
            docs.extend([doc for doc in batch if isinstance(doc, dict)])
            if len(batch) < batch_limit:
                break
    except Exception:
        return None
    finally:
        close = getattr(client, "close", None) if client is not None else None
        if callable(close):
            close()
    return docs


def _doc_label(doc: dict[str, Any]) -> str:
    for field in ("label", "control_id", "name", "key", "_key"):
        value = doc.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return ""


def _doc_keywords(doc: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for field in ("name", "label", "control_id", "key", "category"):
        value = doc.get(field)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    aliases = doc.get("aliases")
    if isinstance(aliases, list):
        values.extend(str(alias).strip() for alias in aliases if str(alias).strip())
    return list(dict.fromkeys(values))


def _matcher(collection: str, limit: int) -> tuple[Any, bool]:
    cache_key = (collection, limit)
    cached = _MATCHER_CACHE.get(cache_key)
    if cached is not None:
        return cached

    try:
        from flashtext import KeywordProcessor
    except Exception:
        unavailable = (None, False)
        _MATCHER_CACHE[cache_key] = unavailable
        return unavailable

    docs = _load_vocabulary_docs(collection, limit)
    if docs is None:
        return None, False

    processor = KeywordProcessor(case_sensitive=False)
    processor.set_non_word_boundaries(set(string.ascii_letters + string.digits + "_-"))
    keyword_count = 0
    for doc in docs:
        label = _doc_label(doc)
        if not label:
            continue
        for keyword in _doc_keywords(doc):
            if len(keyword) < 2:
                continue
            processor.add_keyword(keyword, label)
            keyword_count += 1

    ready = keyword_count > 0
    value = (processor, ready)
    _MATCHER_CACHE[cache_key] = value
    return value


def mandate_hits(text: str, collection: str = VOCABULARY_COLLECTION) -> list[str] | None:
    """Concept labels the text matches in the mandate vocabulary.

    Returns [] for a real-but-irrelevant title (e.g. "Flooring Abatement"),
    a non-empty list for a relevant one, or None if extraction is unavailable.
    """
    if not text or not text.strip():
        return None
    processor, ready = _matcher(collection, _vocabulary_limit())
    if not ready or processor is None:
        return None
    return sorted({str(hit) for hit in processor.extract_keywords(text)})


def is_mandate_relevant(text: str) -> bool | None:
    hits = mandate_hits(text)
    return None if hits is None else len(hits) > 0
