"""Data loading and types for review-conversation.

Loads session JSONL files, shadow.jsonl, and shadow_deltas.jsonl.
All functions are pure — no Rich, no console output.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from loguru import logger

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULT_SESSIONS_DIR = Path(
    os.getenv(
        "SESSIONS_DIR",
        str(
            Path(__file__).resolve().parents[1]
            / "sparta-stress-test"
            / "results"
            / "sessions"
        ),
    )
)
_DEFAULT_SHADOW_PATH = Path(
    os.getenv("SHADOW_JSONL_PATH", str(Path.home() / ".pi" / "assistant" / "shadow.jsonl"))
)
_DEFAULT_DELTA_PATH = Path(
    os.getenv("SHADOW_DELTA_PATH", str(Path.home() / ".pi" / "assistant" / "shadow_deltas.jsonl"))
)
_DEFAULT_AUDIT_PATH = Path(
    os.getenv("LIE_DETECTOR_AUDIT_PATH", "")
)

# ---------------------------------------------------------------------------
# Grade styling
# ---------------------------------------------------------------------------

GRADE_COLORS = {
    "A+": "bold green",
    "A": "green",
    "B": "yellow",
    "C": "dark_orange",
    "F": "bold red",
}


def grade_style(grade: str) -> str:
    return GRADE_COLORS.get(grade, "white")


def composite_bar(score: float, width: int = 20) -> str:
    """Render a score as a visual bar."""
    filled = int(score * width)
    return f"[{'#' * filled}{'.' * (width - filled)}] {score:.2f}"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_sessions(path: Path) -> list[dict]:
    """Load all session records from a JSONL file."""
    if not path.exists():
        logger.warning(f"Session file not found: {path}")
        return []

    sessions = []
    for i, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            sessions.append(json.loads(line))
        except json.JSONDecodeError as e:
            logger.warning(f"Skipping malformed line {i} in {path.name}: {e}")
    return sessions


def load_shadow_index(path: Path) -> dict[str, dict]:
    """Load shadow.jsonl and index by session_id for O(1) lookup."""
    index: dict[str, dict] = {}
    if not path.exists():
        return index

    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            sid = entry.get("input_data", {}).get("session_id", "")
            if not sid:
                sid = entry.get("session_id", "")
            if sid:
                index[sid] = entry
        except json.JSONDecodeError as e:
            logger.debug(f"Skipping malformed shadow line: {e}")
            continue
    return index


def load_delta_index(path: Path) -> dict[str, dict]:
    """Load shadow_deltas.jsonl and index by session_id."""
    index: dict[str, dict] = {}
    if not path.exists():
        return index

    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            sid = entry.get("session_id", "")
            if sid:
                index[sid] = entry
        except json.JSONDecodeError as e:
            logger.debug(f"Skipping malformed delta line: {e}")
            continue
    return index


def load_audit_index(path: Path) -> dict[str, dict]:
    """Load /lie-detector audit JSON and index by session_id.

    Accepts either:
    - Full audit JSON (output of `lie-detector audit --output`): has .sessions[]
    - Flat JSONL with one audit entry per line
    """
    index: dict[str, dict] = {}
    if not path or not path.exists():
        return index

    text = path.read_text().strip()
    if not text:
        return index

    # Try full audit JSON first
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "sessions" in data:
            for s in data["sessions"]:
                sid = s.get("session_id", "")
                if sid:
                    index[sid] = s
            return index
    except json.JSONDecodeError:
        pass

    # Fall back to JSONL
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            sid = entry.get("session_id", "")
            if sid:
                index[sid] = entry
        except json.JSONDecodeError:
            continue
    return index


def find_latest_session_file(sessions_dir: Path) -> Optional[Path]:
    """Find the most recent sessions_*.jsonl file."""
    files = sorted(sessions_dir.glob("sessions_*.jsonl"), reverse=True)
    return files[0] if files else None


def list_session_files(sessions_dir: Path) -> list[Path]:
    """List all session files sorted newest first."""
    return sorted(sessions_dir.glob("sessions_*.jsonl"), reverse=True)


# ---------------------------------------------------------------------------
# Session querying / filtering
# ---------------------------------------------------------------------------


def _get_session_text(session: dict) -> str:
    """Concatenate all searchable text from a session (turns, evaluations, rationales)."""
    parts = []
    for turn in session.get("turns", []):
        parts.append(turn.get("content", ""))
        meta = turn.get("metadata", {})
        if meta.get("evaluation"):
            parts.append(meta["evaluation"])
        if meta.get("reasoning"):
            parts.append(meta["reasoning"])
        sg = meta.get("self_grade_final", {})
        if sg and sg.get("rationale"):
            parts.append(sg["rationale"])
        if sg and sg.get("issues"):
            parts.extend(sg["issues"])
    grade_data = session.get("grade", {}) or {}
    if grade_data.get("rationale"):
        parts.append(grade_data["rationale"])
    seed = session.get("seed_question", {})
    if seed.get("grading_notes"):
        parts.append(seed["grading_notes"])
    return " ".join(parts).lower()


def _get_turn_evaluations(session: dict) -> list[str]:
    """Extract all persona evaluation verdicts from turns."""
    evals = []
    for turn in session.get("turns", []):
        meta = turn.get("metadata", {})
        ev = meta.get("evaluation")
        if ev:
            evals.append(ev.lower())
    return evals


def _get_first_persona_eval(session: dict) -> Optional[str]:
    """Get the first persona evaluation verdict (first follow-up turn)."""
    for turn in session.get("turns", []):
        meta = turn.get("metadata", {})
        ev = meta.get("evaluation")
        if ev:
            return ev.lower()
    return None


def _get_final_composite(session: dict) -> float:
    """Get the final session composite score."""
    grade_data = session.get("grade", {}) or {}
    return float(grade_data.get("composite", 0))


def filter_sessions(
    sessions: list[dict],
    shadow_index: dict[str, dict],
    delta_index: dict[str, dict],
    *,
    grade: Optional[str] = None,
    resolution: Optional[str] = None,
    evaluation: Optional[str] = None,
    first_eval: Optional[str] = None,
    min_composite: Optional[float] = None,
    max_composite: Optional[float] = None,
    difficulty: Optional[str] = None,
    persona: Optional[str] = None,
    min_turns: Optional[int] = None,
    text: Optional[str] = None,
    agreed: Optional[bool] = None,
) -> list[dict]:
    """Filter sessions by structured criteria.

    All filters are AND-combined. Evaluation filters support negation
    with '!' prefix (e.g., '!satisfactory' means NOT satisfactory).
    """
    results = []
    for s in sessions:
        sid = s.get("session_id", "")
        seed = s.get("seed_question", {})
        grade_data = s.get("grade", {}) or {}

        # Grade filter
        if grade is not None:
            sg = grade_data.get("grade", "")
            if sg.upper() != grade.upper():
                continue

        # Resolution filter
        if resolution is not None:
            sr = s.get("resolution", "")
            if sr.lower() != resolution.lower():
                continue

        # Difficulty filter
        if difficulty is not None:
            sd = seed.get("difficulty", "")
            if sd.lower() != difficulty.lower():
                continue

        # Persona filter
        if persona is not None:
            sp = s.get("persona", "")
            if persona.lower() not in sp.lower():
                continue

        # Turn count filter
        if min_turns is not None:
            if len(s.get("turns", [])) < min_turns:
                continue

        # Composite score filters
        if min_composite is not None:
            if _get_final_composite(s) < min_composite:
                continue
        if max_composite is not None:
            if _get_final_composite(s) > max_composite:
                continue

        # Evaluation filter (any turn has this evaluation)
        if evaluation is not None:
            negate = evaluation.startswith("!")
            ev_val = evaluation[1:].lower() if negate else evaluation.lower()
            evals = _get_turn_evaluations(s)
            if negate:
                if ev_val in evals:
                    continue
            else:
                if ev_val not in evals:
                    continue

        # First evaluation filter
        if first_eval is not None:
            negate = first_eval.startswith("!")
            ev_val = first_eval[1:].lower() if negate else first_eval.lower()
            fev = _get_first_persona_eval(s)
            if negate:
                if fev and fev == ev_val:
                    continue
            else:
                if not fev or fev != ev_val:
                    continue

        # Agreement filter
        if agreed is not None:
            shadow = shadow_index.get(sid)
            if shadow is None:
                continue
            if shadow.get("agreed", False) != agreed:
                continue

        # Free-text search
        if text is not None:
            session_text = _get_session_text(s)
            if text.lower() not in session_text:
                continue

        results.append(s)

    return results
