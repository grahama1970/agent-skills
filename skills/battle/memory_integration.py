"""
Memory + Taxonomy integration for /battle.

Pre-hook: Recalls prior battle findings for a target or technique —
enables teams to learn from historical attack/defense patterns across battles.

Post-hook: Learns battle outcomes (target, red findings, blue defenses,
winner, lessons) so future battles can leverage accumulated knowledge.

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
        _spec = importlib.util.spec_from_file_location("battle_taxonomy", _TAXONOMY_PATH)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _taxonomy_extract = getattr(_mod, "extract_taxonomy", None)
    except Exception as e:
        logger.debug(f"Taxonomy module load failed: {e}")


# ---------------------------------------------------------------------------
# Bridge extraction
# ---------------------------------------------------------------------------

_BRIDGE_KEYWORDS = {
    "Precision": ["verified", "confirmed", "validated", "tested", "proof", "exploit"],
    "Resilience": ["patched", "defended", "hardened", "mitigated", "remediated", "recovery"],
    "Fragility": ["vulnerability", "weakness", "flaw", "crash", "overflow", "injection"],
    "Corruption": ["exploit", "rce", "privilege", "escalation", "bypass", "backdoor"],
    "Loyalty": ["dependency", "supply chain", "third party", "library", "integration"],
    "Stealth": ["hidden", "obfuscated", "zero day", "evasion", "undetected", "lateral"],
}


def extract_bridges(text: str) -> List[str]:
    """Extract taxonomy bridge attributes from battle content."""
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
# Pre-hook: Recall prior battle findings
# ---------------------------------------------------------------------------

def recall_prior_battles(
    target_or_technique: str,
    k: int = 5,
) -> str:
    """
    Recall prior battle findings for a target or technique.

    Returns formatted markdown showing historical attack/defense patterns,
    enabling teams to build on accumulated security knowledge.
    Returns empty string if memory unavailable.
    """
    if not _HAS_MEMORY:
        return ""

    try:
        client = MemoryClient(scope=MemoryScope.OPERATIONAL)
        result = client.recall(
            f"battle security {target_or_technique} vulnerability defense patch",
            k=k,
        )
        if result.found:
            return result.to_context(max_items=k)
        return ""
    except Exception as e:
        logger.warning(f"Prior battle recall failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Post-hook: Learn battle outcome
# ---------------------------------------------------------------------------

def learn_battle(
    target: str,
    red_findings: Optional[List[str]] = None,
    blue_defenses: Optional[List[str]] = None,
    winner: str = "",
    lessons: Optional[List[str]] = None,
    battle_id: str = "",
    rounds: int = 0,
    red_score: float = 0.0,
    blue_score: float = 0.0,
    tdsr: float = 0.0,
) -> List[str]:
    """
    Learn battle outcomes to memory after battle completes.

    Stores:
    1. Battle summary (target, winner, scores, rounds)
    2. Red team findings (individual vulnerabilities)
    3. Blue team defenses (successful patches)
    4. Lessons learned (cross-battle value)

    Returns list of learned lesson IDs (empty if memory unavailable).
    """
    if not _HAS_MEMORY:
        logger.info("Memory not available — skipping battle learn")
        return []

    client = MemoryClient(scope=MemoryScope.OPERATIONAL)
    now = datetime.now().isoformat()
    learned_ids = []

    # Build content for bridge extraction
    all_text = " ".join([
        target or "",
        " ".join(red_findings or []),
        " ".join(blue_defenses or []),
        " ".join(lessons or []),
        winner or "",
    ])
    bridges = extract_bridges(all_text)
    base_tags = ["battle", "security"] + bridges

    # 1. Battle summary
    summary = json.dumps({
        "battle_id": battle_id,
        "target": target,
        "winner": winner,
        "rounds": rounds,
        "red_score": red_score,
        "blue_score": blue_score,
        "tdsr": tdsr,
        "red_findings_count": len(red_findings or []),
        "blue_defenses_count": len(blue_defenses or []),
        "date": now,
        "bridges": bridges,
    })

    try:
        result = client.learn(
            problem=f"Battle outcome: {target[:60]} — winner={winner} TDSR={tdsr:.1%}",
            solution=summary,
            tags=base_tags + ["snapshot"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
            logger.info(f"Learned battle snapshot: {result.lesson_id}")
    except Exception as e:
        logger.warning(f"Failed to learn battle snapshot: {e}")

    # 2. Red team findings (individual for fine-grained recall)
    for finding in (red_findings or [])[:10]:
        try:
            result = client.learn(
                problem=f"Red team finding on {target[:40]}: {finding[:100]}",
                solution=finding,
                tags=base_tags + ["red_finding", "vulnerability"],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
        except Exception as e:
            logger.warning(f"Failed to learn red finding: {e}")

    # 3. Blue team defenses (individual for recall)
    for defense in (blue_defenses or [])[:10]:
        try:
            result = client.learn(
                problem=f"Blue team defense on {target[:40]}: {defense[:100]}",
                solution=defense,
                tags=base_tags + ["blue_defense", "patch"],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
        except Exception as e:
            logger.warning(f"Failed to learn blue defense: {e}")

    # 4. Lessons learned (cross-battle value)
    for lesson in (lessons or []):
        try:
            result = client.learn(
                problem=f"Battle lesson from {target[:40]}: {lesson[:100]}",
                solution=lesson,
                tags=base_tags + ["lesson_learned"],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
        except Exception as e:
            logger.warning(f"Failed to learn battle lesson: {e}")

    logger.info(f"Battle learn complete: {len(learned_ids)} entries stored")
    return learned_ids
