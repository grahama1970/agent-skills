"""Deterministic seeded text selector from pre-built text banks.

Usage:
    chunks = create_text(content_type="requirement", domain="defense", count=16, seed=42)
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from loguru import logger

BANK_DIR = Path("/mnt/storage12tb/text_banks")


def create_text(
    content_type: str | None = None,
    domain: str | None = None,
    count: int = 10,
    seed: int = 42,
) -> list[dict]:
    """Return deterministic text chunks from pre-built banks.

    Args:
        content_type: Filter by type (prose, bullet_list, requirement, heading,
                      table_cell, glossary, footnote). None = all types.
        domain: Filter by domain (arxiv, defense, nist, wikipedia, ...).
                None = all domains.
        count: Number of chunks to return.
        seed: Random seed for reproducible selection.

    Returns:
        List of dicts with keys: text, content_type, domain, source_doc, block_id
    """
    pool = _load_pool(domain)

    if content_type:
        pool = [c for c in pool if c["content_type"] == content_type]

    if not pool:
        logger.warning(f"No chunks found for content_type={content_type}, domain={domain}")
        return []

    rng = random.Random(seed)
    selected = rng.sample(pool, min(count, len(pool)))
    return selected


def list_banks() -> dict[str, dict]:
    """List available domains with content type counts (reads domain from chunk data)."""
    from collections import Counter
    all_chunks = _load_pool(None)
    by_domain: dict[str, list] = {}
    for c in all_chunks:
        by_domain.setdefault(c.get("domain", "unknown"), []).append(c)
    summary = {}
    for domain, chunks in sorted(by_domain.items()):
        types = Counter(c["content_type"] for c in chunks)
        summary[domain] = {"total": len(chunks), "types": dict(types)}
    return summary


def _load_pool(domain: str | None) -> list[dict]:
    """Load chunks from bank files, filtering by domain field inside chunks."""
    pool = []
    for bank_file in BANK_DIR.glob("*.json"):
        try:
            pool.extend(json.loads(bank_file.read_text()))
        except (json.JSONDecodeError, OSError):
            continue

    if domain:
        filtered = [c for c in pool if c.get("domain") == domain]
        if not filtered:
            logger.error(f"No chunks with domain={domain}. Available: {sorted(set(c.get('domain','?') for c in pool))}")
        return filtered

    return pool
