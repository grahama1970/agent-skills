"""
Memory + Taxonomy integration for /dogpile.

Pre-hook: Before starting expensive multi-source research, recalls prior
research on similar topics to avoid redundant API calls and surface what
was already discovered.

Post-hook: After research completes, stores to dedicated `dogpile_research`
collection with query, sources, synthesis, key URLs, and taxonomy bridges.

Pattern: Follows create-context/memory_integration.py with graceful degradation.

Collection: dogpile_research (dedicated, not mixed with lessons_v2)
"""

import hashlib
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from loguru import logger

# Memory daemon socket
_MEMORY_SOCKET = "/run/user/1000/embry/memory.sock"
_DOGPILE_COLLECTION = "dogpile_research"

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
    logger.warning("common.memory_client not available — memory integration disabled")

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
        logger.warning(f"Taxonomy module load failed: {e}")


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
            logger.warning(f"Taxonomy extraction failed, using keyword fallback: {e}")

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

    Queries dedicated `dogpile_research` collection for cleaner retrieval.

    Returns empty string if memory unavailable or no prior research found.
    """
    try:
        transport = httpx.HTTPTransport(uds=_MEMORY_SOCKET)
        client = httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0)

        resp = client.post("/recall", json={
            "q": query,
            "k": k,
            "collections": [_DOGPILE_COLLECTION],
        })
        data = resp.json()

        if data.get("found") and data.get("items"):
            items = data["items"]
            logger.info(f"Found {len(items)} prior research entries for: {query[:60]}")

            # Format as markdown context
            lines = ["## Prior Research Found\n"]
            for i, item in enumerate(items[:k], 1):
                query_text = item.get("query", item.get("problem", ""))[:80]
                synthesis = item.get("synthesis", item.get("solution", ""))[:200]
                score = item.get("scores", {}).get("bm25", 0)
                lines.append(f"{i}. **{query_text}...** (score={score:.2f})")
                if synthesis:
                    lines.append(f"   {synthesis}...")
            return "\n".join(lines)
        return ""
    except Exception as e:
        logger.warning(f"Prior research recall failed: {e}")
        # Fallback to MemoryClient if httpx fails
        if _HAS_MEMORY:
            try:
                client = MemoryClient(scope=MemoryScope.OPERATIONAL)
                result = client.recall(f"dogpile research {query}", k=k)
                if result.found:
                    return result.to_context(max_items=k)
            except Exception as e:
                logger.error("memory recall fallback failed: {}", e)
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
    Learn research findings to dedicated `dogpile_research` collection.

    Stores a single document per research session with:
    - query, sources_searched, synthesis, key_urls, bridges, topic_domain

    Returns list of stored document keys (empty if storage fails).
    """
    now = datetime.now()
    learned_ids = []

    # Build content for bridge extraction
    all_text = " ".join(filter(None, [
        query,
        findings or "",
        synthesis or "",
    ]))
    bridges = extract_bridges(all_text)
    topic_domain = _detect_topic_domain(query)

    # Generate deterministic key from query + date
    key_source = f"{query}:{now.strftime('%Y-%m-%d')}"
    doc_key = hashlib.md5(key_source.encode()).hexdigest()[:16]

    # Build unified research document
    doc = {
        "_key": doc_key,
        "query": query,
        "sources_searched": sources_searched or [],
        "synthesis": (synthesis[:3000] if synthesis and len(synthesis) > 3000 else synthesis) or "",
        "key_urls": (key_urls or [])[:20],
        "bridges": bridges,
        "topic_domain": topic_domain,
        "tags": ["dogpile_research", topic_domain] + bridges,
        "ts": int(now.timestamp()),
        "date": now.strftime("%Y-%m-%d"),
        "type": "research",
    }

    try:
        transport = httpx.HTTPTransport(uds=_MEMORY_SOCKET)
        client = httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0)

        resp = client.post("/store", json={
            "document": doc,
            "collection": _DOGPILE_COLLECTION,
        })

        if resp.status_code == 200:
            result = resp.json()
            if result.get("stored"):
                learned_ids.append(result.get("_key", doc_key))
                logger.info(f"Learned research snapshot: {doc_key}")
        else:
            logger.warning(f"Failed to store research: {resp.status_code} {resp.text}")

    except Exception as e:
        logger.warning(f"Failed to learn research: {e}")
        # Fallback to MemoryClient for lessons_v2
        if _HAS_MEMORY:
            try:
                client = MemoryClient(scope=MemoryScope.OPERATIONAL)
                result = client.learn(
                    problem=f"Research: {query[:120]} ({now.strftime('%Y-%m-%d')})",
                    solution=json.dumps(doc),
                    tags=doc["tags"],
                )
                if result.success:
                    learned_ids.append(result.lesson_id)
            except Exception as e:
                logger.error("memory learn fallback failed: {}", e)

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
