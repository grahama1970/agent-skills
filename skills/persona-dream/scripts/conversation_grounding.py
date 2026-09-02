#!/usr/bin/env python3
"""Ground Persona Dream conversations in the concrete dream, day, and memory residue.

This is deliberately deterministic. The model may phrase the conversation, but
it does not get to decide whether the conversation is about the actual dream or
about generic feelings. Callers provide this source packet in prompts and can
read back the returned anchor terms from receipts.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

STOPWORDS = frozenset(
    """
    about above after again against already anything because before being between
    carry carried carrying comes could dream dreamed entry every feels first from
    have held herself itself journal keeps memory more most only other rather
    said says should something source still synthetic their there these thing
    things this those through together under until voice what where which while
    with without would wrote written
    """.split()
)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_text(path: Path, limit: int = 4000) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[:limit]


def _one_line(text: str, limit: int = 220) -> str:
    text = " ".join(str(text or "").split())
    return text[:limit].rstrip()


def _first_sentence(text: str, limit: int = 220) -> str:
    text = _one_line(text, limit=limit * 2)
    match = re.search(r"^(.+?[.!?])(?:\s|$)", text)
    if match:
        text = match.group(1)
    return text[:limit].rstrip()


def _load_journal_entry(run_dir: Path) -> dict[str, Any]:
    for name in ("dream_journal.v1.json", "persona_journal.json", "journal_entry.json"):
        payload = _read_json(run_dir / name)
        if payload:
            return payload
    return {}


def load_context(run_dir: Path) -> dict[str, Any]:
    """Return the source context a conversation must be about."""
    entry = _load_journal_entry(run_dir)
    journal_text = (
        str(entry.get("journal") or "").strip()
        or _read_text(run_dir / "dream_journal.md")
        or _read_text(run_dir / "journal.md")
    )

    residue = _read_json(run_dir / "residue_links.json")
    items = residue.get("items") if isinstance(residue.get("items"), list) else []

    storyboard = _read_json(run_dir / "storyboard_plan.json")
    panels = storyboard.get("panels") if isinstance(storyboard.get("panels"), list) else []

    observation = _read_json(run_dir / "observation_packet.json")
    frame_evidence = observation.get("frame_evidence") if isinstance(observation.get("frame_evidence"), list) else []

    day_lines: list[str] = []
    day_context = _read_json(run_dir / "day_context.json")
    for item in day_context.get("items") or []:
        if isinstance(item, dict):
            day_lines.append(_one_line(item.get("text"), 180))

    transcript_context = _read_json(run_dir / "transcript_context.json")
    transcript_lines = [
        _one_line(item.get("text"), 220)
        for item in (transcript_context.get("items") or [])
        if isinstance(item, dict) and str(item.get("text") or "").strip()
    ]
    for item in items:
        scope = str(item.get("scope") or "")
        typ = str(item.get("type") or item.get("kind") or "")
        if scope.startswith("episodic:day=") or "Day event" in typ:
            day_lines.append(_one_line(item.get("text"), 180))

    source_lines = [
        f"- {item.get('source_id')}: {_one_line(item.get('text'), 220)}"
        for item in items[:8]
        if str(item.get("text") or "").strip()
    ]
    panel_lines = [
        f"- {panel.get('panel_id')}: {_one_line(panel.get('action') or panel.get('setting') or panel.get('shot'), 200)}"
        for panel in panels[:4]
        if isinstance(panel, dict)
    ]
    observed_lines: list[str] = []
    for frame in frame_evidence[:4]:
        entities = frame.get("observed_entities") if isinstance(frame, dict) else []
        if isinstance(entities, list) and entities:
            observed_lines.append(f"- {frame.get('panel_id')}: {', '.join(str(e) for e in entities[:3])}")

    day_terms = anchor_terms("\n".join(day_lines), limit=12)
    transcript_terms = anchor_terms("\n".join(transcript_lines), limit=12)
    terms = anchor_terms("\n".join([journal_text, storyboard.get("dream_synopsis", "")] + source_lines + panel_lines + day_lines + transcript_lines))
    return {
        "journal_entry": entry,
        "journal_text": journal_text,
        "dream_synopsis": _one_line(storyboard.get("dream_synopsis") or entry.get("journal") or journal_text, 320),
        "unresolved_tension": str(entry.get("unresolved_tension") or "").strip(),
        "expanded_understanding": str(entry.get("expanded_understanding") or "").strip(),
        "session_mood": entry.get("session_mood") if isinstance(entry.get("session_mood"), dict) else {},
        "source_lines": source_lines,
        "day_lines": [line for line in day_lines if line],
        "transcript_lines": [line for line in transcript_lines if line],
        "panel_lines": panel_lines,
        "observed_lines": observed_lines,
        "anchor_terms": terms,
        "day_anchor_terms": day_terms,
        "transcript_anchor_terms": transcript_terms,
        "source_count": len(source_lines),
        "transcript_count": len(transcript_lines),
        "panel_count": len(panel_lines),
        "observation_count": len(observed_lines),
    }


def anchor_terms(text: str, *, limit: int = 24) -> list[str]:
    """Distinctive source words/proper nouns that can prove concrete grounding."""
    found: list[str] = []
    for raw in re.findall(r"[A-Za-z][A-Za-z0-9'_-]{3,}", text or ""):
        token = raw.strip("'_-.,;:!?()[]{}\"")
        low = token.lower()
        if low in STOPWORDS or len(low) < 4:
            continue
        if token[0].isupper() or len(low) >= 6:
            if low not in {t.lower() for t in found}:
                found.append(token)
        if len(found) >= limit:
            break
    return found


def _has_any_term(text: str, terms: list[str]) -> bool:
    lowered = (text or "").lower()
    for term in terms:
        if len(str(term)) >= 4 and re.search(rf"\b{re.escape(str(term).lower())}\b", lowered):
            return True
    return False


def has_anchor(text: str, context: dict[str, Any]) -> bool:
    return _has_any_term(text, list(context.get("anchor_terms") or []))


def has_day_anchor(text: str, context: dict[str, Any]) -> bool:
    return _has_any_term(text, list(context.get("day_anchor_terms") or []))


def grounding_clause(context: dict[str, Any]) -> str:
    """A short phrase that can be injected if a drafted turn is generic."""
    synopsis = str(context.get("dream_synopsis") or "").strip()
    first_source = ""
    lines = context.get("source_lines") or []
    if lines:
        first_source = str(lines[0]).split(":", 1)[-1].strip()
    if synopsis:
        return _first_sentence(synopsis, 220)
    if first_source:
        return _first_sentence(first_source, 180)
    return "the specific dream and the memories that fed it"


def format_for_prompt(context: dict[str, Any], *, max_chars: int = 2600) -> str:
    """Prompt block shared by Horus and Embry generation."""
    sections: list[str] = []
    if context.get("dream_synopsis"):
        sections.append("DREAM SHE WATCHED:\n" + str(context["dream_synopsis"]))
    if context.get("panel_lines"):
        sections.append("DREAM PANELS:\n" + "\n".join(context["panel_lines"]))
    if context.get("observed_lines"):
        sections.append("WHAT THE DREAM OBSERVATION ACTUALLY SAW:\n" + "\n".join(context["observed_lines"]))
    if context.get("source_lines"):
        sections.append("MEMORY RESIDUE / MINED CONTEXT:\n" + "\n".join(context["source_lines"]))
    if context.get("day_lines"):
        sections.append("DAY EVENTS:\n" + "\n".join(context["day_lines"][:4]))
    if context.get("transcript_lines"):
        sections.append("MINED HUMAN TRANSCRIPT / OPERATOR FEEDBACK:\n" + "\n".join(context["transcript_lines"][:5]))
    if context.get("unresolved_tension"):
        sections.append("UNRESOLVED JOURNAL TENSION:\n" + str(context["unresolved_tension"]))
    if context.get("expanded_understanding"):
        sections.append("EXPANDED UNDERSTANDING:\n" + str(context["expanded_understanding"]))
    mood = context.get("session_mood") or {}
    if mood:
        sections.append(
            "SESSION MOOD:\n"
            + str(mood.get("mood_label") or "")
            + " -- "
            + str(mood.get("mood_description") or mood.get("carried_tension") or "")
        )
    block = "\n\n".join(s for s in sections if s.strip())
    return block[:max_chars]


def ground_if_needed(text: str, context: dict[str, Any], *, role: str) -> tuple[str, bool]:
    """Make a generic model draft source-bound without changing tone delivery."""
    clean = " ".join(str(text or "").split())
    if has_anchor(clean, context):
        return clean, False
    clause = grounding_clause(context)
    if role == "horus":
        grounded = f"When the dream held {clause}, {clean[0].lower() + clean[1:] if clean else 'what does that ask of you now?'}"
    else:
        grounded = f"The part I keep returning to is {clause}. {clean}"
    return grounded[:700].rstrip(), True


def ground_day_if_needed(text: str, context: dict[str, Any], *, role: str) -> tuple[str, bool]:
    """Ensure the conversation names one specific day event when the run has one."""
    clean = " ".join(str(text or "").split())
    day_lines = [str(line) for line in context.get("day_lines") or [] if str(line).strip()]
    if not day_lines or has_day_anchor(clean, context):
        return clean, False
    day = _first_sentence(day_lines[0], 180)
    if role == "horus":
        grounded = f"Today is in the room too: {day}. {clean}"
    else:
        grounded = f"Today is in the room too: {day}. {clean}"
    return grounded[:700].rstrip(), True
