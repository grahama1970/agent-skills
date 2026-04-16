"""Helpers for session comparison and merging during convergence."""
from __future__ import annotations


def _get_composite(session: dict) -> float:
    """Extract composite score from a session."""
    grade = session.get("grade", {})
    return grade.get("composite", 0) if isinstance(grade, dict) else 0


def _get_session_key(session: dict) -> str:
    """Get a unique key for a session — prefer session_id, fall back to question text."""
    sid = session.get("session_id", "")
    if sid:
        return sid
    return session.get("seed_question", {}).get("question", "")


def _is_satisfied(session: dict) -> bool:
    """Check if persona evaluated this session as satisfactory."""
    for turn in session.get("turns", []):
        ev = turn.get("evaluation", {})
        if isinstance(ev, dict) and ev.get("verdict", "").upper() == "SATISFACTORY":
            return True
    return False


def compare_sessions(
    original: list[dict], new: list[dict]
) -> tuple[int, int]:
    """Compare new sessions against originals. Returns (improved, regressed)."""
    orig_map = {}
    for s in original:
        key = _get_session_key(s)
        if key:
            orig_map[key] = s

    improved = 0
    regressed = 0
    for ns in new:
        key = _get_session_key(ns)
        orig = orig_map.get(key)
        if not orig:
            continue
        orig_comp = _get_composite(orig)
        new_comp = _get_composite(ns)
        orig_sat = _is_satisfied(orig)
        new_sat = _is_satisfied(ns)
        # Improved: better composite OR newly satisfied
        if new_comp > orig_comp + 0.05 or (new_sat and not orig_sat):
            improved += 1
        elif new_comp < orig_comp - 0.05 or (orig_sat and not new_sat):
            regressed += 1

    return improved, regressed


def merge_sessions(
    original: list[dict], new: list[dict]
) -> list[dict]:
    """Replace original sessions with improved new ones. Keep originals if regressed."""
    orig_by_key = {}
    for i, s in enumerate(original):
        key = _get_session_key(s)
        if key:
            orig_by_key[key] = i

    result = list(original)
    for ns in new:
        key = _get_session_key(ns)
        idx = orig_by_key.get(key)
        if idx is None:
            continue
        new_comp = _get_composite(ns)
        old_comp = _get_composite(result[idx])
        new_sat = _is_satisfied(ns)
        old_sat = _is_satisfied(result[idx])
        # Replace if better composite OR newly satisfied with same-or-better composite
        if new_comp > old_comp or (new_sat and not old_sat and new_comp >= old_comp):
            result[idx] = ns

    return result
