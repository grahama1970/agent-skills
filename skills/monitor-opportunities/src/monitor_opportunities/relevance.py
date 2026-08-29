"""Mandate relevance via Memory /extract-entities — deterministic, NO REGEX.

Replaces substring keyword regex (which mis-fired, e.g. matching "ai" inside
unrelated words) with whole-phrase Flashtext matching against a mandate
vocabulary held in ArangoDB (`opportunity_vocabulary`), per best-practices-python
`correctness-regex-only-known-grammar` and best-practices-arangodb (domain terms
live in ArangoDB, not Python lists). Delegates to the /extract-entities skill
rather than reimplementing Flashtext.

A title/solicitation is mandate-relevant iff it matches >=1 vocabulary concept.
Fail-soft: if /memory is unavailable, returns None so the caller can fall back to
a conservative default instead of crashing the nightly.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

EXTRACT_ENTITIES_RUN = Path(__file__).resolve().parents[3] / "extract-entities" / "run.sh"
VOCABULARY_COLLECTION = "opportunity_vocabulary"
DEFAULT_MEMORY_URL = "http://127.0.0.1:8601"
_MEMORY_ENDPOINT_BACKOFF_UNTIL = 0.0
_NON_AUTHORITATIVE_COLLECTIONS: set[str] = set()


def _memory_url() -> str:
    return (
        os.environ.get("MONITOR_OPPORTUNITIES_MEMORY_URL")
        or os.environ.get("MONITOR_MEMORY_URL")
        or os.environ.get("MEMORY_URL")
        or DEFAULT_MEMORY_URL
    ).rstrip("/")


def _extract_entities_timeout() -> httpx.Timeout:
    return httpx.Timeout(connect=1.0, read=3.0, write=1.0, pool=1.0)


def _truthy_env(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _memory_backoff_seconds() -> float:
    return float(os.environ.get("MONITOR_OPPORTUNITIES_EXTRACT_ENTITIES_BACKOFF_SECONDS", "300"))


def _entity_result_collection(result: dict[str, Any]) -> str | None:
    value = result.get("collection") or result.get("vocabulary_collection") or result.get("source_collection")
    return str(value) if value else None


def _entity_label(entity: Any) -> str | None:
    if not isinstance(entity, dict):
        return None
    for key in ("label", "key", "name", "term", "mention", "control_id"):
        value = entity.get(key)
        if value:
            return str(value)
    return None


def _labels_from_entity_result(result: dict[str, Any], collection: str) -> list[str] | None:
    if _entity_result_collection(result) != collection:
        return None

    labels: set[str] = set()
    for field in ("entities", "resolved_entities", "domain_terms"):
        value = result.get(field)
        if not isinstance(value, list):
            continue
        for entity in value:
            label = _entity_label(entity)
            if label:
                labels.add(label)
    return sorted(labels)


def _mandate_hits_via_memory(text: str, collection: str) -> list[str] | None:
    global _MEMORY_ENDPOINT_BACKOFF_UNTIL

    now = time.monotonic()
    if collection in _NON_AUTHORITATIVE_COLLECTIONS:
        return None
    if now < _MEMORY_ENDPOINT_BACKOFF_UNTIL:
        return None

    payload = {
        "text": text,
        "collection": collection,
        "include_taxonomy": False,
        "view": "legacy",
    }
    try:
        with httpx.Client(base_url=_memory_url(), timeout=_extract_entities_timeout()) as client:
            response = client.post("/extract-entities", json=payload)
            response.raise_for_status()
            result = response.json()
    except (httpx.TimeoutException, httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("opportunity relevance Memory /extract-entities unavailable: {}", exc)
        _MEMORY_ENDPOINT_BACKOFF_UNTIL = now + _memory_backoff_seconds()
        return None
    if not isinstance(result, dict):
        logger.warning("opportunity relevance Memory /extract-entities returned non-object JSON")
        _MEMORY_ENDPOINT_BACKOFF_UNTIL = now + _memory_backoff_seconds()
        return None
    hits = _labels_from_entity_result(result, collection)
    if hits is None and _entity_result_collection(result) != collection:
        logger.warning(
            "opportunity relevance Memory /extract-entities ignored collection {}; disabling endpoint for this process",
            collection,
        )
        _NON_AUTHORITATIVE_COLLECTIONS.add(collection)
    return hits


def _mandate_hits_via_subprocess(text: str, collection: str) -> list[str] | None:
    if not EXTRACT_ENTITIES_RUN.exists():
        return None
    timeout = float(os.environ.get("MONITOR_OPPORTUNITIES_EXTRACT_ENTITIES_SUBPROCESS_TIMEOUT", "10"))
    try:
        # Stdin NLP mode (no subcommand) outputs JSON by default; --json is invalid here.
        proc = subprocess.run(
            [str(EXTRACT_ENTITIES_RUN), "--collection", collection],
            input=text,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    # A run that loaded an empty vocabulary (ArangoDB contention/outage) reports
    # success with zero entities for EVERY text. That is "unavailable", not
    # "irrelevant" — returning [] here silently drops relevant items (observed as
    # flaky test failures 2026-08-12: 'Loaded 0 entities' under concurrent load).
    if "Loaded 0 entities" in (proc.stderr or ""):
        return None
    # The skill logs to stderr and prints one JSON object to stdout.
    start = proc.stdout.find("{")
    if start < 0:
        return None
    try:
        result = json.loads(proc.stdout[start:])
    except (ValueError, json.JSONDecodeError):
        return None
    return _labels_from_entity_result(result, collection)


def mandate_hits(text: str, collection: str = VOCABULARY_COLLECTION) -> list[str] | None:
    """Concept labels the text matches in the mandate vocabulary.

    Returns [] for a real-but-irrelevant title (e.g. "Flooring Abatement"),
    a non-empty list for a relevant one, or None if extraction is unavailable.
    """
    if not text or not text.strip():
        return None
    hits = _mandate_hits_via_memory(text, collection)
    if hits is not None:
        return hits
    if not _truthy_env("MONITOR_OPPORTUNITIES_EXTRACT_ENTITIES_SUBPROCESS"):
        return None
    return _mandate_hits_via_subprocess(text, collection)


def is_mandate_relevant(text: str) -> bool | None:
    hits = mandate_hits(text)
    return None if hits is None else len(hits) > 0
