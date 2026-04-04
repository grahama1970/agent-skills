"""Multi-POV archival and skill-chain extraction for episodic archiver.

Codex 5.3 review fixes (2026-03-30):
- Fixed undefined `proc` variable in chain learning error path
- Fixed perspective storage (was using unsupported --data flag, now uses store_perspectives())
- Uses msg_content/msg_role consistently for content extraction
"""

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from loguru import logger

import httpx

from memory_helpers import (
    MEMORY_SOCK,
    _make_memory_client,
    store_perspectives,
    call_llm_simple,
    msg_content,
    msg_role,
    track_error,
)


# ── Skill-chain extraction ─────────────────────────────────────────────────

_KNOWN_SKILLS_CACHE: set = set()


def _cached_known_skills(skills_root: Path, discover_fn) -> set:
    global _KNOWN_SKILLS_CACHE
    if not _KNOWN_SKILLS_CACHE:
        _KNOWN_SKILLS_CACHE = discover_fn(skills_root)
    return _KNOWN_SKILLS_CACHE


def extract_and_learn_chains(session_content: str, session_id: str, success: bool = True):
    """Extract skill chains from archived session and learn to /memory."""
    import sys

    chain_miner_dir = Path(__file__).resolve().parent.parent / "skill-lab" / "scripts"
    if str(chain_miner_dir) not in sys.path:
        sys.path.insert(0, str(chain_miner_dir))

    try:
        from chain_miner import extract_skills_used, extract_user_request, discover_known_skills
    except ImportError:
        logger.debug("chain_miner not available, skipping chain extraction")
        return

    skills_root = Path(__file__).resolve().parent.parent
    known_skills = _cached_known_skills(skills_root, discover_known_skills)
    if not known_skills:
        return

    skills = extract_skills_used(session_content, known_skills)
    if len(skills) < 2:
        return

    request = extract_user_request(session_content)
    if not request:
        return

    try:
        with _make_memory_client() as client:
            from memory_helpers import _retry_request
            resp = _retry_request(client, "post", "/learn", json={
                "problem": f"skill-chain: {request[:500]}",
                "solution": json.dumps({
                    "skills": skills,
                    "source": "episodic",
                    "success": success,
                    "session_id": session_id,
                }),
                "scope": "skill_chains",
            })
        if resp.status_code == 200:
            logger.info(f"Learned chain [{' -> '.join(skills)}] from session {session_id}")
        elif resp.status_code == 422:
            logger.debug(f"Chain learn skipped (no taxonomy): {skills}")
        else:
            logger.warning(f"chain-learn failed (HTTP {resp.status_code}): {resp.text[:200]}")
    except Exception as exc:
        track_error("chain_learn", str(exc))


# ── Multi-POV archival ──────────────────────────────────────────────────────

def archive_multi_pov(
    session_id: str,
    messages: List[Dict],
    categories: List[str],
    personas: List[str] = None,
    max_perspectives: int = 5,
):
    """Generate multi-POV perspective summaries for relevant personas."""
    if not personas:
        personas = detect_relevant_personas(messages)

    if not personas:
        logger.info(f"No relevant personas detected for session {session_id}")
        return []

    personas = personas[:max_perspectives]

    # Build conversation text using canonical content extraction
    conversation_text = "\n".join(
        f"[{msg_role(msg) or 'unknown'}] {msg_content(msg)[:300]}"
        for msg in messages[:30]
    )

    perspectives = []
    for persona_id in personas:
        try:
            prompt = (
                f"Summarize this conversation from the perspective of {persona_id}, "
                f"focusing on what is relevant to their domain expertise. "
                f"Keep it under 200 words.\n\n{conversation_text[:3000]}"
            )
            summary = call_llm_simple(prompt)
            if summary and len(summary) > 10:
                perspectives.append({
                    "persona_id": persona_id,
                    "summary": summary,
                    "relevance_score": score_persona_relevance(persona_id, messages),
                })
        except Exception as e:
            logger.warning(f"Failed to generate perspective for {persona_id}: {e}")

    # Store via store_perspectives (not broken _memory_cmd --data)
    if perspectives:
        store_perspectives(session_id, perspectives)

    return perspectives


# ── Persona detection helpers ───────────────────────────────────────────────

def detect_relevant_personas(messages: List[Dict]) -> List[str]:
    """Detect which personas are relevant based on content keywords."""
    keyword_persona_map = {
        "nist": ["brandon_bailey", "margaret_chen", "jennifer_cheung", "embry"],
        "800-53": ["brandon_bailey", "margaret_chen", "jennifer_cheung", "embry"],
        "sparta": ["brandon_bailey", "jennifer_cheung"],
        "space": ["brandon_bailey", "jennifer_cheung"],
        "satellite": ["brandon_bailey", "jennifer_cheung"],
        "mitre": ["brandon_bailey", "jennifer_cheung", "embry"],
        "att&ck": ["brandon_bailey", "jennifer_cheung"],
        "certification": ["margaret_chen", "rob_armstrong"],
        "do-178": ["margaret_chen", "rob_armstrong"],
        "mil-std": ["margaret_chen", "paul_nakamura", "rob_armstrong"],
        "formal": ["jennifer_cheung", "embry"],
        "lean4": ["jennifer_cheung", "embry"],
        "manufacturing": ["paul_nakamura"],
        "cnc": ["paul_nakamura"],
        "plant": ["paul_nakamura"],
        "safety": ["margaret_chen", "paul_nakamura", "rob_armstrong"],
        "ics": ["paul_nakamura", "brandon_bailey"],
        "scada": ["paul_nakamura", "brandon_bailey"],
        "compliance": ["margaret_chen", "brandon_bailey"],
    }

    all_text = " ".join(msg_content(msg) for msg in messages).lower()

    persona_scores: Counter = Counter()
    for keyword, persona_ids in keyword_persona_map.items():
        if keyword in all_text:
            for pid in persona_ids:
                persona_scores[pid] += 1

    return [pid for pid, score in persona_scores.most_common() if score >= 1]


def score_persona_relevance(persona_id: str, messages: List[Dict]) -> float:
    """Score how relevant a conversation is to a specific persona (0.0-1.0)."""
    persona_keywords = {
        "brandon_bailey": ["sparta", "nist", "800-53", "cyber", "assessment", "control", "threat", "att&ck"],
        "margaret_chen": ["certification", "do-178", "safety", "compliance", "audit", "mil-std", "accreditation"],
        "jennifer_cheung": ["formal", "lean4", "tla+", "bridge", "mapping", "stig", "verification"],
        "paul_nakamura": ["manufacturing", "cnc", "plant", "ics", "scada", "telemetry", "machine"],
        "rob_armstrong": ["system", "engineering", "integration", "test", "mil-std", "certification"],
        "embry": ["nist", "mitre", "formal", "learning", "knowledge", "analysis"],
        "noah_williams": ["video", "media", "production", "camera", "film"],
    }

    keywords = persona_keywords.get(persona_id, [])
    if not keywords:
        return 0.3

    all_text = " ".join(msg_content(msg) for msg in messages).lower()
    hits = sum(1 for kw in keywords if kw in all_text)
    return min(1.0, hits / max(len(keywords) * 0.5, 1))
