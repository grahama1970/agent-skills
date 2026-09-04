"""Small helpers for RuntimeState."""
from __future__ import annotations

import re

from datetime import datetime

from .models import CapabilityPolicy, CardStatus, EvidenceCard, SessionStatus, Speaker, TranscriptEvent, utc_now

ROLE_PREFIX_RE = re.compile(
    r"^\s*(?P<role>interviewer|candidate|graham)(?P<sep>\s*(?:[:\-–—,.]|\band\b)?\s+|[.:]\s*$)",
    re.IGNORECASE,
)

ROLE_PREFIX_PRONOUNS = {
    "i", "i'm", "im", "we", "we're", "were", "you", "you're", "youre",
    "what", "how", "why", "when", "where", "can", "could", "would", "should",
    "the", "an", "a", "let", "let's", "lets", "thanks", "thank",
    "right", "good", "sure", "absolutely", "yes", "yeah",
    "live", "implement", "write", "design", "define", "build", "use", "give",
}


NEW_QUESTION_MARKERS = (
    "second question",
    "third question",
    "next question",
    "another question",
    "separate question",
    "different question",
    "last question",
    "last thing",
    "next thing",
)


def normalize_spoken_role_prefix(event: TranscriptEvent) -> TranscriptEvent:
    """Move spoken role labels out of transcript text and into speaker metadata.

    Synthetic meeting audio often says ``Interviewer:`` / ``Candidate:`` before
    each turn. RealtimeSTT may hear the separator as punctuation, whitespace, or
    the word ``and``. Leaving that prefix in text polluted the transcript and,
    worse, let candidate answers arrive as interviewer questions when the
    listener was a single PipeWire channel labeled interviewer.
    """

    match = ROLE_PREFIX_RE.match(event.text)
    if not match:
        return event
    role = match.group("role").casefold()
    remainder = event.text[match.end():].strip(" ,:;.-–—")
    if not remainder:
        return event
    first = remainder.split(maxsplit=1)[0].casefold().strip(".,:;!?\"'()[]{}")
    sep = match.group("sep") or ""
    explicit_separator = bool(sep.strip() and (sep.strip().casefold() == "and" or any(char in sep for char in ":-–—,.")))
    if not explicit_separator and first not in ROLE_PREFIX_PRONOUNS:
        return event
    speaker = {
        "interviewer": Speaker.INTERVIEWER,
        "candidate": Speaker.CANDIDATE,
        "graham": Speaker.GRAHAM,
    }[role]
    if role == "interviewer" and remainder[:1].islower():
        remainder = remainder[:1].upper() + remainder[1:]
    return event.model_copy(update={
        "speaker": speaker,
        "text": remainder,
        "attribution_source": "transport",
        "attribution_confidence": 0.95,
    })


def _explicit_new_question_marker(text: str) -> bool:
    lower = text.casefold()
    return any(marker in lower for marker in NEW_QUESTION_MARKERS)


def _card_should_replace(displayed: EvidenceCard | None, incoming: EvidenceCard) -> bool:
    """Keep a source-backed card visible over later weak revisions.

    Live STT often keeps emitting cumulative explanatory fragments after the
    useful problem statement has already produced a supported card. Those later
    fragments may resolve to an insufficient card for the same question id; the
    HUD should not lose the useful card to a weaker same-question revision.
    """

    if displayed is None:
        return True
    if incoming.status is CardStatus.SUPPORTED:
        return True
    return displayed.status is CardStatus.INSUFFICIENT


def _newer_displayed_blocks(displayed: EvidenceCard | None, incoming: EvidenceCard) -> bool:
    if displayed is None:
        return False
    if (displayed.question_revision or 0) <= (incoming.question_revision or 0):
        return False
    return not (
        displayed.status is CardStatus.INSUFFICIENT
        and incoming.status is CardStatus.SUPPORTED
    )


def listener_snapshot(
    info: dict[str, str] | None,
    session_status: SessionStatus,
    last_report_at: datetime | None,
    last_audio_at: datetime | None,
    last_transcript_at: datetime | None,
) -> dict[str, str] | None:
    if info is None:
        return None
    now = utc_now()
    age = (now - last_report_at).total_seconds() if last_report_at else 999999.0
    reason = info.get("resolve_reason", "")
    level = int(str(info.get("level") or "0") or 0)
    health = "quiet"
    if session_status is not SessionStatus.LISTENING:
        health = "stopped"
    elif reason == "restarting":
        health = "reconnecting"
    elif reason == "transcription_error":
        health = "error"
    elif age > 3.0:
        health = "stalled"
    elif level > 8:
        health = "active"
    return {
        **info,
        "health": health,
        "last_report_age_ms": str(int(age * 1000)),
        "last_audio_at": last_audio_at.isoformat() if last_audio_at else "",
        "last_transcript_at": last_transcript_at.isoformat() if last_transcript_at else "",
        "capture_mode": info.get("mode", ""),
    }


def _status_for_session(consent_confirmed: bool, policy: CapabilityPolicy) -> SessionStatus:
    """Never report LISTENING for a session that may not capture audio.

    Two independent gates: consent (the human agreed) and the frozen policy's
    capture_audio capability (this session KIND is allowed to capture --
    post_interview_review, for example, is post-hoc and never listens). Either
    one absent keeps the session ARMED, and the coordinator refuses retrieval
    for any non-LISTENING session.
    """

    if consent_confirmed and policy.capture_audio:
        return SessionStatus.LISTENING
    return SessionStatus.ARMED
