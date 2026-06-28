"""
Memory + Taxonomy integration for /battle.

Pre-hook: Recalls prior battle findings for a target or technique —
enables teams to learn from historical attack/defense patterns across battles.

Post-hook: Learns battle outcomes (target, red findings, blue defenses,
winner, lessons) so future battles can leverage accumulated knowledge.

Pattern: delegates to the `/memory` skill through its HTTP API.
"""

import hashlib
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from loguru import logger


MEMORY_SERVICE_URL = os.getenv("MEMORY_SERVICE_URL") or os.getenv("MEMORY_API_URL") or "http://127.0.0.1:8601"


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
    try:
        with httpx.Client(base_url=MEMORY_SERVICE_URL, timeout=httpx.Timeout(10.0, connect=2.0)) as client:
            response = client.post(
                "/recall",
                json={
                    "q": f"battle security {target_or_technique} vulnerability defense patch",
                    "k": k,
                    "tags": ["battle", "security"],
                },
            )
            response.raise_for_status()
            data = response.json()
        if not data.get("found"):
            return ""
        items = data.get("items") or []
        lines = []
        for item in items[:k]:
            problem = item.get("problem") or item.get("title") or item.get("_key", "memory item")
            solution = item.get("solution") or item.get("text") or item.get("content") or ""
            lines.append(f"- {problem}: {str(solution)[:500]}")
        return "\n".join(lines)
    except (httpx.HTTPError, ValueError) as e:
        logger.error("Prior battle recall HTTP request failed: {}", e)
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
        result = _memory_learn(
            problem=f"Battle outcome: {target[:60]} - winner={winner} TDSR={tdsr:.1%}",
            solution=summary,
            tags=base_tags + ["snapshot"],
        )
        if result:
            learned_ids.append(result)
            logger.info("Learned battle snapshot: {}", result)
    except Exception as e:
        logger.error("Failed to learn battle snapshot: {}", e)

    # 2. Red team findings (individual for fine-grained recall)
    for finding in (red_findings or [])[:10]:
        try:
            result = _memory_learn(
                problem=f"Red team finding on {target[:40]}: {finding[:100]}",
                solution=finding,
                tags=base_tags + ["red_finding", "vulnerability"],
            )
            if result:
                learned_ids.append(result)
        except Exception as e:
            logger.error("Failed to learn red finding: {}", e)

    # 3. Blue team defenses (individual for recall)
    for defense in (blue_defenses or [])[:10]:
        try:
            result = _memory_learn(
                problem=f"Blue team defense on {target[:40]}: {defense[:100]}",
                solution=defense,
                tags=base_tags + ["blue_defense", "patch"],
            )
            if result:
                learned_ids.append(result)
        except Exception as e:
            logger.error("Failed to learn blue defense: {}", e)

    # 4. Lessons learned (cross-battle value)
    for lesson in (lessons or []):
        try:
            result = _memory_learn(
                problem=f"Battle lesson from {target[:40]}: {lesson[:100]}",
                solution=lesson,
                tags=base_tags + ["lesson_learned"],
            )
            if result:
                learned_ids.append(result)
        except Exception as e:
            logger.error("Failed to learn battle lesson: {}", e)

    logger.info(f"Battle learn complete: {len(learned_ids)} entries stored")
    return learned_ids


def _memory_learn(*, problem: str, solution: str, tags: list[str]) -> str | None:
    """Store one lesson through the `/memory` HTTP API."""
    key = hashlib.sha256(f"battle:{problem}:{solution}".encode("utf-8")).hexdigest()[:24]
    document = {
        "_key": key,
        "problem": problem,
        "solution": solution,
        "tags": tags,
        "source": "battle",
        "created_at": datetime.now().isoformat(),
    }
    try:
        with httpx.Client(base_url=MEMORY_SERVICE_URL, timeout=httpx.Timeout(10.0, connect=2.0)) as client:
            response = client.post("/store", json={"document": document, "collection": "lessons"})
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.error("Memory store HTTP request failed: {}", e)
        return None
    return str(data.get("_key") or data.get("key") or key)
