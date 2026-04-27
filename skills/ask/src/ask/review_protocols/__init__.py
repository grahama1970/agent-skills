"""Reusable review protocol primitives for /ask and peer-review skills."""

from .adversarial_review import (
    DATE_SENSITIVE_TERMS,
    PROTOCOL_ROLE_PRESETS,
    build_moderator_prompt,
    build_parallel_reviewer_prompt,
    build_roundtable_turn_prompt,
    default_parallel_participants,
    is_date_sensitive_question,
    parse_participant_specs,
    parse_protocol_turn,
    summarize_protocol_transcript,
)

__all__ = [
    "DATE_SENSITIVE_TERMS",
    "PROTOCOL_ROLE_PRESETS",
    "build_moderator_prompt",
    "build_parallel_reviewer_prompt",
    "build_roundtable_turn_prompt",
    "default_parallel_participants",
    "is_date_sensitive_question",
    "parse_participant_specs",
    "parse_protocol_turn",
    "summarize_protocol_transcript",
]
