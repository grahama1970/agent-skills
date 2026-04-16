#!/usr/bin/env python3
"""Query expansion and zero-results fallback for Dogpile.

When a provider returns fewer than min_results, automatically reformulates
the query using proven strategies: simplification and synonym expansion.
"""
from typing import Callable, Dict, List, Optional


# Common qualifier words that can be removed to broaden search
_QUALIFIERS = {
    "best", "top", "recommended", "ultimate", "complete", "comprehensive",
    "definitive", "advanced", "beginner", "guide", "tutorial", "how to",
    "introduction to", "overview of",
}

# Domain-specific synonym map (word -> alternatives)
_SYNONYMS: Dict[str, List[str]] = {
    "fix": ["resolve", "solve", "repair"],
    "bug": ["error", "issue", "defect"],
    "fast": ["efficient", "performant", "quick"],
    "implement": ["build", "create", "develop"],
    "vulnerability": ["CVE", "exploit", "weakness"],
    "authentication": ["auth", "login", "credentials"],
    "deploy": ["release", "ship", "publish"],
    "monitor": ["observe", "track", "watch"],
    "parse": ["extract", "process", "transform"],
    "config": ["configuration", "settings", "options"],
}


def simplify_query(query: str) -> Optional[str]:
    """Remove qualifiers and filler words to broaden the search.

    Returns simplified query, or None if no simplification possible.
    """
    words = query.split()
    simplified = [w for w in words if w.lower() not in _QUALIFIERS]
    result = " ".join(simplified).strip()
    return result if result and result != query else None


def expand_synonyms(query: str, max_variants: int = 2) -> List[str]:
    """Generate query variants by substituting known synonyms.

    Returns list of variant queries (not including original).
    """
    variants = []
    words = query.lower().split()
    for word in words:
        if word in _SYNONYMS:
            for syn in _SYNONYMS[word][:max_variants]:
                variants.append(query.replace(word, syn))
    return variants[:3]  # Cap at 3 variants


def search_with_fallback(
    search_fn: Callable[[str], List[Dict]],
    query: str,
    min_results: int = 3,
) -> List[Dict]:
    """Run a search with automatic query reformulation on poor results.

    Strategy order:
    1. Try original query
    2. If < min_results: try simplified query (remove qualifiers)
    3. If still < min_results: try synonym expansions

    Args:
        search_fn: Provider search function (query -> results list)
        query: Original search query
        min_results: Minimum acceptable result count

    Returns:
        Best results found across all attempts
    """
    results = search_fn(query)
    if len(results) >= min_results:
        return results

    # Strategy 1: Simplify
    simplified = simplify_query(query)
    if simplified:
        alt_results = search_fn(simplified)
        if len(alt_results) > len(results):
            results = alt_results
            if len(results) >= min_results:
                return results

    # Strategy 2: Synonym expansion
    for variant in expand_synonyms(query):
        alt_results = search_fn(variant)
        if len(alt_results) > len(results):
            results = alt_results
            if len(results) >= min_results:
                return results

    return results
