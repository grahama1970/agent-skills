"""Taxonomy, dogpile, memory, and user profiling integrations for episodic archiver analysis."""

import os
import asyncio
import json
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from loguru import logger

SCRIPT_DIR = Path(__file__).resolve().parent
_SKILLS_DIR = SCRIPT_DIR.parent
# Removed: memory accessed via httpx to Unix socket (see _memory_cmd)


def apply_session_taxonomy(
    assessment: dict,
    high_fidelity: bool = False,
    user_id: str = "",
    persona_id: str = "",
    participants: list = None,
) -> dict:
    """Extract bridge attributes for cross-collection traversal.

    Args:
        assessment: Session assessment from LLM analysis.
        high_fidelity: If True, use LLM-based extraction (slower, higher confidence).
                       If False, use heuristic-only extraction (fast path for real-time).
        user_id: User who participated in the session.
        persona_id: Persona involved in the session.
        participants: All participant IDs (users + personas).
    """
    try:
        from common.taxonomy import extract_taxonomy_features, ContentType
        content = " ".join(
            assessment.get("problems_addressed", [])
            + assessment.get("solutions_found", [])
            + assessment.get("key_learnings", [])
        )
        title = (assessment.get("problems_addressed") or ["Untitled session"])[0]
        result = extract_taxonomy_features(
            content_type=ContentType.SESSION,
            title=title,
            description=content,
            tags=[],
            high_fidelity=high_fidelity,
            user_id=user_id,
            persona_id=persona_id,
            participants=participants or [],
        )
        return {
            "bridge_attributes": result.get("bridge_attributes", []),
            "participants": result.get("participants", {}),
            "taxonomy": {
                "content_type": "session",
                "method": result.get("method", "llm" if high_fidelity else "heuristic"),
                "high_fidelity": high_fidelity,
                "collection_tags": result.get("collection_tags", {}),
                "tactical_tags": result.get("tactical_tags", []),
                "participants": result.get("participants", {}),
            },
        }
    except Exception:
        return {"bridge_attributes": [], "participants": {}, "taxonomy": {"content_type": "session", "method": "failed"}}


async def dogpile_gaps(
    candidates: list, session_id: str, max_per_run: int = 3
) -> list:
    """Run dogpile research on unresolved session gaps."""
    if not candidates:
        return []

    dogpile_script = SCRIPT_DIR.parent / "dogpile" / "run.sh"
    if not dogpile_script.exists():
        logger.debug("dogpile/run.sh not found, skipping gap research")
        return []

    results = []
    for query in candidates[:max_per_run]:
        if not query or len(query) < 10:
            continue
        try:
            proc = await asyncio.to_thread(
                subprocess.run,
                [str(dogpile_script), "search", query, "--no-interactive", "--no-tailor"],
                capture_output=True, text=True, timeout=120,
                env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
            )
            if proc.returncode == 0 and proc.stdout.strip():
                # dogpile outputs markdown + optional JSON; try to parse last line as JSON
                for line in reversed(proc.stdout.strip().split("\n")):
                    line = line.strip()
                    if line.startswith("{"):
                        try:
                            data = json.loads(line)
                            results.append({
                                "query": query[:200],
                                "session_id": session_id,
                                "result": data,
                                "timestamp": int(time.time()),
                            })
                            break
                        except json.JSONDecodeError:
                            continue
                else:
                    # No JSON found, store raw text summary
                    results.append({
                        "query": query[:200],
                        "session_id": session_id,
                        "result": {"text": proc.stdout.strip()[-2000:]},
                        "timestamp": int(time.time()),
                    })
            elif proc.returncode != 0:
                logger.warning(f"dogpile exited {proc.returncode} for '{query[:50]}': {proc.stderr[:200]}")
        except subprocess.TimeoutExpired:
            logger.warning(f"dogpile timed out (120s) for '{query[:50]}'")
        except Exception as e:
            logger.warning(f"dogpile failed for '{query[:50]}': {e}")

    logger.info(f"dogpile gap research: {len(results)}/{len(candidates[:max_per_run])} queries returned results")
    return results


def _detect_scope_from_session(session_id: str, assessment: dict) -> str:
    """Detect memory scope from session content. Works for any persona."""
    combined = (session_id + " " + json.dumps(assessment)).lower()
    if "sparta" in combined or "mitre" in combined or "att&ck" in combined:
        return "sparta"
    if "lore" in combined or "horus" in combined:
        return "lore"
    if "behavioral" in combined or "psychology" in combined:
        return "behavioral"
    return "operational"


def store_lessons_to_memory(
    assessment: dict,
    session_id: str,
    bridge_attributes: list,
    emit=None,
    user_id: str = "",
    persona_id: str = "",
    personas: List[str] = None,
) -> int:
    """Store resolved session lessons to /memory with taxonomy bridge tags.

    Only fires for resolved/partial sessions with problem/solution pairs.
    Memory auto-handles timestamps, decay, contradictions.

    When `personas` is provided, stores lessons to EACH persona's memory
    scope (multi-POV). Lessons are stored sequentially to respect Chutes
    API concurrency limits.

    Args:
        assessment: Session assessment from LLM analysis
        session_id: Session identifier
        bridge_attributes: Taxonomy bridge tags
        emit: Logging callback
        user_id: User ID
        persona_id: Primary persona ID
        personas: Optional list of persona IDs for multi-scope storage.
                  Each persona gets the lesson stored in their scope.

    Returns:
        Number of lessons stored.
    """
    if emit is None:
        emit = lambda msg: None  # noqa: E731

    # Only store from resolved or partially resolved sessions
    resolution = assessment.get("resolution_status", "")
    if resolution not in ("resolved", "partial"):
        emit(f"Session {resolution} -- skipping lesson storage")
        return 0

    # Build list of (scope, persona_id) pairs to store to
    if personas:
        # Multi-POV: store to each persona's scope
        scope_targets = [(pid, pid) for pid in personas]
    else:
        # Single scope: detect from session content
        scope = _detect_scope_from_session(session_id, assessment)
        scope_targets = [(scope, persona_id)]

    stored = 0

    for target_scope, target_persona in scope_targets:
        tags = [f"session:{session_id}", "episodic"] + [b for b in bridge_attributes if b]
        if user_id:
            tags.append(f"user:{user_id}")
        if target_persona:
            tags.append(f"perspective:{target_persona}")

        # Store problem/solution pairs
        problems = assessment.get("problems_addressed", [])
        solutions = assessment.get("solutions_found", [])

        for i, (problem, solution) in enumerate(zip(problems, solutions)):
            if not problem or not solution:
                continue

            try:
                import httpx
                transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
                with httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0) as client:
                    resp = client.post("/learn", json={
                        "problem": problem[:1000],
                        "solution": solution[:2000],
                        "scope": target_scope,
                        "tags": tags[:5],
                    })
                    if resp.status_code == 200:
                        stored += 1
                        emit(f"Stored lesson {i+1} for {target_persona}: {problem[:60]}...")
                    else:
                        emit(f"Failed to store lesson {i+1} for {target_persona}: HTTP {resp.status_code}")
            except Exception as e:
                emit(f"Error storing lesson {i+1} for {target_persona}: {e}")

        # Store key learnings as standalone lessons
        for learning in assessment.get("key_learnings", []):
            if not learning or len(learning) < 20:
                continue

            try:
                import httpx
                transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
                with httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0) as client:
                    resp = client.post("/learn", json={
                        "problem": f"Key learning from session {session_id}",
                        "solution": learning[:2000],
                        "scope": target_scope,
                        "tags": tags[:5],
                    })
                    if resp.status_code == 200:
                        stored += 1
            except Exception as e:
                logger.debug("result extraction failed: {}", e)

    if stored:
        scope_info = f"scopes={[t[0] for t in scope_targets]}" if personas else f"scope={scope_targets[0][0]}"
        emit(f"Stored {stored} lessons to memory ({scope_info})")

    return stored


def update_user_priors(
    user_id: str,
    session_profile: dict,
    session_id: str,
    db=None,
) -> dict:
    """Merge a new session profile into the user's evolving priors (RGMem-style).

    Incremental update rules:
    - bridge_affinities: weighted average across sessions
    - expertise_domains: union (accumulate)
    - communication_style: most-recent-3-sessions voting
    - frustration_triggers/satisfaction_signals: append unique, cap at 20
    - session_count: increment
    """
    if db is None:
        from graph_memory.arango_client import get_db as _get_db
        db = _get_db()

    if not db.has_collection("user_priors"):
        db.create_collection("user_priors")

    collection = db.collection("user_priors")
    doc_key = user_id.replace("/", "_").replace(" ", "_")[:64]

    # Load existing priors
    existing = None
    try:
        existing = collection.get(doc_key)
    except Exception as e:
        logger.debug("value lookup failed: {}", e)

    now = int(time.time())

    if existing is None:
        # First session for this user
        doc = {
            "_key": doc_key,
            "user_id": user_id,
            "session_count": 1,
            "created_at": now,
            "updated_at": now,
            "profile": {
                "communication_style": session_profile.get("communication_style", "mixed"),
                "expertise_domains": session_profile.get("expertise_domains", []),
                "expertise_level": session_profile.get("expertise_level", "intermediate"),
                "response_preferences": session_profile.get("response_preferences", {}),
            },
            "bridge_affinities": session_profile.get("bridge_affinities", {}),
            "frustration_history": session_profile.get("frustration_triggers", [])[:20],
            "satisfaction_history": session_profile.get("satisfaction_signals", [])[:20],
            "recent_styles": [session_profile.get("communication_style", "mixed")],
            "session_ids": [session_id],
        }
        collection.insert(doc)
        return doc

    # Incremental merge
    n = existing.get("session_count", 1)
    new_n = n + 1

    # Bridge affinities: weighted running average
    old_affinities = existing.get("bridge_affinities", {})
    new_affinities = session_profile.get("bridge_affinities", {})
    merged_affinities = {}
    all_bridges = set(list(old_affinities.keys()) + list(new_affinities.keys()))
    for bridge in all_bridges:
        old_val = old_affinities.get(bridge, 0.0)
        new_val = new_affinities.get(bridge, 0.0)
        # Weighted average: existing data weighted by session count
        merged_affinities[bridge] = round((old_val * n + new_val) / new_n, 3)

    # Expertise domains: union
    old_domains = set(existing.get("profile", {}).get("expertise_domains", []))
    new_domains = set(session_profile.get("expertise_domains", []))
    merged_domains = sorted(old_domains | new_domains)

    # Communication style: most-recent-3 voting
    recent_styles = existing.get("recent_styles", [])
    recent_styles.append(session_profile.get("communication_style", "mixed"))
    recent_styles = recent_styles[-3:]  # Keep last 3
    style_votes = Counter(recent_styles)
    dominant_style = style_votes.most_common(1)[0][0]

    # Frustration/satisfaction: append unique, cap at 20
    old_frustration = existing.get("frustration_history", [])
    new_frustration = session_profile.get("frustration_triggers", [])
    merged_frustration = list(dict.fromkeys(old_frustration + new_frustration))[:20]

    old_satisfaction = existing.get("satisfaction_history", [])
    new_satisfaction = session_profile.get("satisfaction_signals", [])
    merged_satisfaction = list(dict.fromkeys(old_satisfaction + new_satisfaction))[:20]

    # Session IDs: append, cap at 50
    session_ids = existing.get("session_ids", [])
    if session_id not in session_ids:
        session_ids.append(session_id)
    session_ids = session_ids[-50:]

    # Expertise level: take highest observed
    level_rank = {"beginner": 0, "intermediate": 1, "advanced": 2, "expert": 3}
    old_level = existing.get("profile", {}).get("expertise_level", "intermediate")
    new_level = session_profile.get("expertise_level", "intermediate")
    merged_level = old_level if level_rank.get(old_level, 1) >= level_rank.get(new_level, 1) else new_level

    update = {
        "session_count": new_n,
        "updated_at": now,
        "profile": {
            "communication_style": dominant_style,
            "expertise_domains": merged_domains,
            "expertise_level": merged_level,
            "response_preferences": session_profile.get("response_preferences",
                existing.get("profile", {}).get("response_preferences", {})),
        },
        "bridge_affinities": merged_affinities,
        "frustration_history": merged_frustration,
        "satisfaction_history": merged_satisfaction,
        "recent_styles": recent_styles,
        "session_ids": session_ids,
    }

    collection.update({"_key": doc_key, **update})
    return {**existing, **update}
