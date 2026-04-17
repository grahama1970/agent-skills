"""
Memory + Taxonomy integration for /discover-contacts.

Pre-hook: Recalls prior contact research for a person to avoid redundant
/dogpile calls and surface previously gathered intelligence.

Post-hook: Learns enriched contact profiles to memory so future lookups
can leverage accumulated knowledge across sessions.

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
        _spec = importlib.util.spec_from_file_location("discover_contacts_taxonomy", _TAXONOMY_PATH)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _taxonomy_extract = getattr(_mod, "extract_taxonomy", None)
    except Exception as e:
        logger.debug(f"Taxonomy module load failed: {e}")


# ---------------------------------------------------------------------------
# Bridge extraction
# ---------------------------------------------------------------------------

_BRIDGE_KEYWORDS = {
    "Precision": ["verified", "confirmed", "current", "validated", "active", "accurate"],
    "Resilience": ["updated", "refreshed", "enriched", "found", "discovered"],
    "Fragility": ["stale", "outdated", "bounced", "departed", "unknown", "missing"],
    "Corruption": ["impersonation", "fake", "misleading", "spam", "phishing"],
    "Loyalty": ["contract", "program", "partnership", "collaboration", "darpa"],
    "Stealth": ["private", "unlisted", "redacted", "unavailable", "hidden"],
}


def extract_bridges(text: str) -> List[str]:
    """Extract taxonomy bridge attributes from contact research content."""
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


# ---------------------------------------------------------------------------
# Pre-hook: Recall prior contact research
# ---------------------------------------------------------------------------

def recall_prior_research(
    person_name: str,
    k: int = 3,
) -> str:
    """
    Recall prior research for a contact.

    Returns formatted markdown showing previously gathered intelligence
    for this person, enabling agents to avoid redundant research and
    detect changes since last enrichment. Returns empty string if
    memory unavailable.
    """
    if not _HAS_MEMORY:
        return ""

    try:
        client = MemoryClient(scope=MemoryScope.OPERATIONAL)
        result = client.recall(
            f"discover_contacts {person_name} role company enrichment",
            k=k,
        )
        if result.found:
            return result.to_context(max_items=k)
        return ""
    except Exception as e:
        logger.warning(f"Prior contact research recall failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Post-hook: Learn contact enrichment
# ---------------------------------------------------------------------------

def learn_contact(
    person_name: str,
    company: str = "",
    role: str = "",
    sources: Optional[List[str]] = None,
    enrichment_data: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    Learn enriched contact profile to memory.

    Stores:
    1. Contact profile (name, company, role, enrichment date)
    2. Company association (for cross-contact recall)
    3. Source audit trail (for freshness tracking)

    Returns list of learned lesson IDs (empty if memory unavailable).
    """
    if not _HAS_MEMORY:
        logger.info("Memory not available — skipping contact learn")
        return []

    client = MemoryClient(scope=MemoryScope.OPERATIONAL)
    now = datetime.now().isoformat()
    learned_ids = []

    # Build content for bridge extraction
    all_text = " ".join([
        person_name or "",
        company or "",
        role or "",
        " ".join(sources or []),
        json.dumps(enrichment_data or {}),
    ])
    bridges = extract_bridges(all_text)
    base_tags = ["discover_contacts", person_name] + bridges

    # 1. Contact profile
    profile = json.dumps({
        "person_name": person_name,
        "company": company,
        "role": role,
        "sources": sources or [],
        "enrichment_data": enrichment_data or {},
        "enriched_at": now,
        "bridges": bridges,
    })

    try:
        result = client.learn(
            problem=f"Contact enrichment: {person_name} — {role} at {company}",
            solution=profile,
            tags=base_tags + ["profile"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
            logger.info(f"Learned contact profile: {result.lesson_id}")
    except Exception as e:
        logger.warning(f"Failed to learn contact profile: {e}")

    # 2. Company association (for cross-contact recall)
    if company:
        try:
            result = client.learn(
                problem=f"Company contact: {company} — {person_name} ({role})",
                solution=json.dumps({
                    "company": company,
                    "person_name": person_name,
                    "role": role,
                    "date": now,
                }),
                tags=base_tags + ["company_association", company],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
        except Exception as e:
            logger.warning(f"Failed to learn company association: {e}")

    # 3. Source audit trail
    if sources:
        try:
            result = client.learn(
                problem=f"Research sources for {person_name}: {', '.join(sources[:5])}",
                solution=json.dumps({
                    "person_name": person_name,
                    "sources": sources,
                    "date": now,
                }),
                tags=base_tags + ["source_audit"],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
        except Exception as e:
            logger.warning(f"Failed to learn source audit: {e}")

    logger.info(f"Contact learn complete: {len(learned_ids)} entries stored")
    return learned_ids
