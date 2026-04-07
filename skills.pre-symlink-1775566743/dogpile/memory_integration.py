"""
Memory + Taxonomy integration for /dogpile.

Pre-hook: Before starting expensive multi-source research, recalls prior
research on similar topics to avoid redundant API calls and surface what
was already discovered.

Post-hook: After research completes, learns query, sources searched,
findings, synthesis, and key URLs to memory with taxonomy bridge tags.

Pattern: Follows create-context/memory_integration.py with graceful degradation.
"""

import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

# ---------------------------------------------------------------------------
# Lazy imports with graceful degradation
# ---------------------------------------------------------------------------
_SKILLS_DIR = Path(__file__).parent.parent
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

# Memory client
_HAS_MEMORY = False
try:
    from common.memory_client import MemoryClient, MemoryScope, RecallResult
    _HAS_MEMORY = True
except ImportError:
    logger.debug("common.memory_client not available — memory integration disabled")

# Taxonomy (loaded dynamically to avoid name conflicts)
_taxonomy_extract = None
_TAXONOMY_PATH = _SKILLS_DIR / "taxonomy" / "taxonomy.py"
if _TAXONOMY_PATH.exists():
    try:
        _spec = importlib.util.spec_from_file_location("dogpile_taxonomy", _TAXONOMY_PATH)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _taxonomy_extract = getattr(_mod, "extract_taxonomy", None)
    except Exception as e:
        logger.debug(f"Taxonomy module load failed: {e}")


# ---------------------------------------------------------------------------
# Bridge extraction
# ---------------------------------------------------------------------------

_BRIDGE_KEYWORDS = {
    "Precision": ["verified", "confirmed", "source", "cited", "evidence", "proven", "validated"],
    "Resilience": ["multiple sources", "consensus", "corroborated", "redundant", "robust", "reliable"],
    "Fragility": ["contradictory", "uncertain", "unverified", "conflicting", "disputed", "inconclusive"],
    "Corruption": ["security", "vulnerability", "exploit", "injection", "CVE", "malware", "threat"],
    "Loyalty": ["dependency", "integration", "compatibility", "ecosystem", "upstream"],
    "Stealth": ["undocumented", "hidden", "implicit", "side effect", "obscure", "edge case"],
}


def extract_bridges(text: str) -> List[str]:
    """Extract taxonomy bridge attributes from research content."""
    if _taxonomy_extract:
        try:
            result = _taxonomy_extract(text, collection="operational")
            bridges = result.get("bridge_tags", []) if isinstance(result, dict) else []
            if bridges:
                return bridges
        except Exception as e:
            logger.debug(f"Taxonomy extraction failed, using keyword fallback: {e}")

    text_lower = text.lower()
    found = []
    for bridge, keywords in _BRIDGE_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            found.append(bridge)
    return found or ["Precision"]


def _detect_topic_domain(query: str) -> str:
    """Detect a broad topic domain from the query for tagging."""
    query_lower = query.lower()
    domain_keywords = {
        "security": ["cve", "exploit", "vulnerability", "malware", "threat", "attack", "pentest"],
        "ai_ml": ["machine learning", "deep learning", "neural", "llm", "transformer", "model", "training"],
        "devops": ["docker", "kubernetes", "ci/cd", "pipeline", "deploy", "infrastructure"],
        "web": ["react", "javascript", "html", "css", "frontend", "backend", "api"],
        "systems": ["kernel", "os", "memory", "cpu", "network", "protocol", "binary"],
        "data": ["database", "sql", "nosql", "data lake", "etl", "analytics"],
        "crypto": ["blockchain", "cryptography", "encryption", "hash", "signature"],
    }
    for domain, keywords in domain_keywords.items():
        if any(kw in query_lower for kw in keywords):
            return domain
    return "general"


# ---------------------------------------------------------------------------
# Pre-hook: Recall prior research on similar topics
# ---------------------------------------------------------------------------

def recall_prior_research(
    query: str,
    k: int = 5,
) -> str:
    """
    Recall prior research findings for a similar topic.

    Called BEFORE starting expensive multi-source searches. If prior research
    exists on the same or similar topic, returns formatted markdown showing
    what was already discovered -- avoiding redundant API calls.

    Returns empty string if memory unavailable or no prior research found.
    """
    if not _HAS_MEMORY:
        return ""

    try:
        client = MemoryClient(scope=MemoryScope.OPERATIONAL)
        result = client.recall(
            f"dogpile research {query} findings synthesis sources",
            k=k,
        )
        if result.found:
            logger.info(f"Found {len(result.items)} prior research entries for: {query[:60]}")
            return result.to_context(max_items=k)
        return ""
    except Exception as e:
        logger.warning(f"Prior research recall failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Post-hook: Learn research findings to memory
# ---------------------------------------------------------------------------

def learn_research(
    query: str,
    sources_searched: Optional[List[str]] = None,
    findings: Optional[str] = None,
    synthesis: Optional[str] = None,
    key_urls: Optional[List[str]] = None,
) -> List[str]:
    """
    Learn research findings to memory after dogpile search completes.

    Stores:
    1. Research summary (query, sources, date, key metrics)
    2. Synthesis / conclusion (the high-reasoning Codex output)
    3. Key URLs discovered (for future reference)

    Returns list of learned lesson IDs (empty if memory unavailable).
    """
    if not _HAS_MEMORY:
        logger.info("Memory not available — skipping research learn")
        return []

    client = MemoryClient(scope=MemoryScope.OPERATIONAL)
    now = datetime.now().isoformat()
    learned_ids = []

    # Build content for bridge extraction
    all_text = " ".join(filter(None, [
        query,
        findings or "",
        synthesis or "",
    ]))
    bridges = extract_bridges(all_text)
    topic_domain = _detect_topic_domain(query)
    base_tags = ["dogpile_research", topic_domain] + bridges

    # 1. Research summary snapshot
    summary = json.dumps({
        "query": query,
        "date": now,
        "sources_searched": sources_searched or [],
        "sources_count": len(sources_searched or []),
        "has_synthesis": bool(synthesis),
        "key_urls_count": len(key_urls or []),
        "bridges": bridges,
        "topic_domain": topic_domain,
    })

    try:
        result = client.learn(
            problem=f"Research: {query[:120]} ({now[:10]})",
            solution=summary,
            tags=base_tags + ["snapshot"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
            logger.info(f"Learned research snapshot: {result.lesson_id}")
    except Exception as e:
        logger.warning(f"Failed to learn research snapshot: {e}")

    # 2. Synthesis / conclusion (the most valuable piece)
    if synthesis and not synthesis.startswith("Error:"):
        try:
            # Truncate very long synthesis to stay within memory limits
            synth_content = synthesis[:3000] if len(synthesis) > 3000 else synthesis
            result = client.learn(
                problem=f"Synthesis for '{query[:80]}': key conclusions and insights",
                solution=synth_content,
                tags=base_tags + ["synthesis"],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
                logger.info(f"Learned research synthesis: {result.lesson_id}")
        except Exception as e:
            logger.warning(f"Failed to learn synthesis: {e}")

    # 3. Key URLs (for future reference without re-searching)
    if key_urls:
        try:
            result = client.learn(
                problem=f"Key URLs for research on '{query[:80]}'",
                solution=json.dumps({
                    "query": query,
                    "date": now,
                    "urls": key_urls[:20],  # Cap at 20 URLs
                }),
                tags=base_tags + ["key_urls"],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
                logger.info(f"Learned key URLs: {result.lesson_id}")
        except Exception as e:
            logger.warning(f"Failed to learn key URLs: {e}")

    logger.info(f"Research learn complete: {len(learned_ids)} entries stored for '{query[:60]}'")
    return learned_ids


# ---------------------------------------------------------------------------
# Execution metadata batch-learn
# ---------------------------------------------------------------------------

def learn_execution_batch(records: list) -> list[str]:
    """Batch-learn execution metadata records to /memory.

    Args:
        records: List of ExecutionRecord dataclasses from the collector

    Returns:
        List of learned lesson IDs (empty on failure or if memory unavailable)
    """
    if not _HAS_MEMORY or not records:
        return []

    try:
        from dataclasses import asdict

        client = MemoryClient(scope=MemoryScope.OPERATIONAL)
        now = datetime.now().strftime("%Y-%m-%d")

        items = []
        for rec in records:
            rec_dict = asdict(rec)
            items.append({
                "problem": f"dogpile exec: {rec.provider} @ {rec.stage} ({now})",
                "solution": json.dumps(rec_dict),
                "tags": [
                    "dogpile_exec",
                    f"provider:{rec.provider}",
                    f"stage:{rec.stage}",
                    f"outcome:{rec.outcome}",
                ],
            })

        results = client.batch_learn(items, concurrency=4)
        learned = [r.lesson_id for r in results if r and r.success]
        logger.info(f"Learned {len(learned)}/{len(records)} execution records to memory")
        return learned

    except Exception as e:
        logger.warning(f"Execution metadata batch-learn failed: {e}")
        return []
