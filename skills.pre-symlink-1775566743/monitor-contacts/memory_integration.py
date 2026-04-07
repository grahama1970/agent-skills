"""
Memory + Taxonomy integration for /monitor-contacts.

Pre-hook: Recalls prior contact change history for a person to surface
patterns (e.g., frequent job changes, company instability).

Post-hook: Learns individual change events to memory for trend tracking
and longitudinal analysis of contact freshness.

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
        _spec = importlib.util.spec_from_file_location("monitor_contacts_taxonomy", _TAXONOMY_PATH)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _taxonomy_extract = getattr(_mod, "extract_taxonomy", None)
    except Exception as e:
        logger.debug(f"Taxonomy module load failed: {e}")


# ---------------------------------------------------------------------------
# Bridge extraction
# ---------------------------------------------------------------------------

_BRIDGE_KEYWORDS = {
    "Precision": ["confirmed", "verified", "current", "validated", "accurate"],
    "Resilience": ["stable", "consistent", "retained", "renewed", "active"],
    "Fragility": ["changed", "departed", "stale", "outdated", "bounced", "layoff", "restructuring"],
    "Corruption": ["impersonation", "fake", "misleading", "compromised"],
    "Loyalty": ["promoted", "contract", "program", "partnership", "renewed"],
    "Stealth": ["quiet", "unlisted", "private", "redacted", "unannounced"],
}


def extract_bridges(text: str) -> List[str]:
    """Extract taxonomy bridge attributes from contact change content."""
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
# Pre-hook: Recall prior contact change history
# ---------------------------------------------------------------------------

def recall_contact_changes(
    person_name: str,
    k: int = 5,
) -> str:
    """
    Recall prior change history for a contact.

    Returns formatted markdown showing historical changes detected for
    this person, enabling agents to identify patterns (e.g., frequent
    job moves, company instability). Returns empty string if memory
    unavailable.
    """
    if not _HAS_MEMORY:
        return ""

    try:
        client = MemoryClient(scope=MemoryScope.OPERATIONAL)
        result = client.recall(
            f"monitor_contacts {person_name} change job company drift_tracking",
            k=k,
        )
        if result.found:
            return result.to_context(max_items=k)
        return ""
    except Exception as e:
        logger.warning(f"Prior contact change recall failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Post-hook: Learn contact change event
# ---------------------------------------------------------------------------

def learn_contact_change(
    person_name: str,
    change_type: str = "",
    old_value: str = "",
    new_value: str = "",
    severity: str = "medium",
    source: str = "",
) -> List[str]:
    """
    Learn a contact change event to memory for trend tracking.

    Stores:
    1. Change event (person, type, old/new values, date)
    2. Severity-tagged entry for alerting recall

    Returns list of learned lesson IDs (empty if memory unavailable).
    """
    if not _HAS_MEMORY:
        logger.info("Memory not available — skipping contact change learn")
        return []

    client = MemoryClient(scope=MemoryScope.OPERATIONAL)
    now = datetime.now().isoformat()
    learned_ids = []

    # Build content for bridge extraction
    all_text = " ".join([
        person_name or "",
        change_type or "",
        old_value or "",
        new_value or "",
        severity or "",
    ])
    bridges = extract_bridges(all_text)
    base_tags = ["monitor_contacts", person_name, "drift_tracking"] + bridges

    # 1. Change event
    event = json.dumps({
        "person_name": person_name,
        "change_type": change_type,
        "old_value": old_value,
        "new_value": new_value,
        "severity": severity,
        "source": source,
        "detected_at": now,
        "bridges": bridges,
    })

    try:
        result = client.learn(
            problem=f"Contact change: {person_name} — {change_type}: {old_value[:40]} -> {new_value[:40]}",
            solution=event,
            tags=base_tags + ["change_event", change_type],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
            logger.info(f"Learned contact change: {result.lesson_id}")
    except Exception as e:
        logger.warning(f"Failed to learn contact change: {e}")

    # 2. Severity-tagged entry (for high-priority alerting recall)
    if severity in ("high", "critical"):
        try:
            result = client.learn(
                problem=f"High-priority contact change: {person_name} — {change_type}",
                solution=json.dumps({
                    "person_name": person_name,
                    "change_type": change_type,
                    "old_value": old_value,
                    "new_value": new_value,
                    "severity": severity,
                    "date": now,
                }),
                tags=base_tags + ["high_priority", "alert"],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
        except Exception as e:
            logger.warning(f"Failed to learn high-priority change: {e}")

    logger.info(f"Contact change learn complete: {len(learned_ids)} entries stored")
    return learned_ids
