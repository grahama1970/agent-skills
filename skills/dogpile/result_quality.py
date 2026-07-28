#!/usr/bin/env python3
"""Result quality improvements for Dogpile.

Provides:
- fuzzy_deduplicate: Remove near-identical results across sources
- blend_domains: Prevent any single domain from monopolizing results
- score_credibility: Simple heuristic credibility scoring
"""
from collections import defaultdict
from difflib import SequenceMatcher
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urlparse
from loguru import logger


def fuzzy_deduplicate(results: List[Dict], threshold: float = 0.85) -> List[Dict]:
    """Remove semantically similar results using string similarity.

    Args:
        results: List of result dicts (must have 'title' and/or 'snippet'/'description')
        threshold: Similarity threshold (0.0-1.0). Higher = stricter dedup.

    Returns:
        Deduplicated list, keeping the result with more metadata.
    """
    unique: List[Dict] = []
    for result in results:
        text = f"{result.get('title', '')} {result.get('snippet', result.get('description', ''))}"
        is_dup = False
        for i, existing in enumerate(unique):
            existing_text = f"{existing.get('title', '')} {existing.get('snippet', existing.get('description', ''))}"
            if SequenceMatcher(None, text.lower(), existing_text.lower()).ratio() >= threshold:
                is_dup = True
                # Keep the one with a URL (prefer richer metadata)
                if result.get("url") and not existing.get("url"):
                    unique[i] = result
                break
        if not is_dup:
            unique.append(result)
    return unique


def blend_domains(results: List[Dict], max_per_domain: int = 3) -> List[Dict]:
    """Limit results from any single domain to ensure source diversity.

    Args:
        results: List of result dicts (must have 'url')
        max_per_domain: Maximum results per domain

    Returns:
        Domain-blended list preserving original order.
    """
    domain_counts: Dict[str, int] = defaultdict(int)
    blended: List[Dict] = []
    for result in results:
        url = result.get("url", "")
        try:
            domain = urlparse(url).netloc
        except Exception:
            domain = ""
        if not domain or domain_counts[domain] < max_per_domain:
            blended.append(result)
            if domain:
                domain_counts[domain] += 1
    return blended


# Credibility tiers
_ACADEMIC_DOMAINS = {".edu", ".gov", "arxiv.org", "ieee.org", "acm.org", "nih.gov", "nist.gov"}
_QUALITY_TECH = {"stackoverflow.com", "github.com", "microsoft.com", "google.com",
                 "docs.python.org", "developer.mozilla.org", "wiki.archlinux.org"}
_SPAM_INDICATORS = {"click here", "buy now", "limited time", "subscribe now", "free download"}


def score_credibility(result: Dict) -> float:
    """Score source credibility using simple heuristics (0.0-1.0).

    Factors:
    - Domain authority (.edu/.gov = +0.3, quality tech = +0.2)
    - Recency (< 1 year = +0.1)
    - Spam indicators (-0.2)

    Args:
        result: Result dict with 'url', optionally 'date', 'snippet'/'description'

    Returns:
        Credibility score clamped to [0.0, 1.0]
    """
    score = 0.5
    url = result.get("url", "").lower()
    try:
        domain = urlparse(url).netloc
    except Exception:
        domain = ""

    # Academic/authoritative domains
    if any(d in domain for d in _ACADEMIC_DOMAINS):
        score += 0.3
    elif any(d in domain for d in _QUALITY_TECH):
        score += 0.2

    # Recency bonus
    date_str = result.get("date") or result.get("published") or result.get("timestamp")
    if date_str:
        try:
            pub = datetime.fromisoformat(str(date_str)[:19])
            if (datetime.now() - pub).days < 365:
                score += 0.1
        except Exception as e:
            logger.warning("scoring failed: {}", e)

    # Spam penalty
    snippet = (result.get("snippet") or result.get("description") or "").lower()
    if any(spam in snippet for spam in _SPAM_INDICATORS):
        score -= 0.2

    return max(0.0, min(1.0, score))


def rank_results(results: List[Dict]) -> List[Dict]:
    """Apply full quality pipeline: dedup -> blend -> score -> sort.

    Args:
        results: Raw aggregated results

    Returns:
        Quality-processed and ranked results
    """
    deduped = fuzzy_deduplicate(results)
    blended = blend_domains(deduped)
    for r in blended:
        r["_credibility"] = score_credibility(r)
    blended.sort(key=lambda r: r.get("_credibility", 0.5), reverse=True)
    return blended
