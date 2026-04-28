"""Reusable review protocol primitives for /ask and peer-review skills."""

from .adversarial_review import (
    ARGUE_JUDGE_RUBRIC,
    ARGUE_VERDICTS,
    DATE_SENSITIVE_TERMS,
    PROTOCOL_ROLE_PRESETS,
    build_argue_prompt_payload,
    build_moderator_prompt,
    build_parallel_reviewer_prompt,
    build_roundtable_turn_prompt,
    default_parallel_participants,
    is_date_sensitive_question,
    normalize_argue_personas,
    parse_participant_specs,
    parse_protocol_turn,
    summarize_protocol_transcript,
)

__all__ = [
    "ARGUE_JUDGE_RUBRIC",
    "ARGUE_VERDICTS",
    "DATE_SENSITIVE_TERMS",
    "PROTOCOL_ROLE_PRESETS",
    "build_argue_prompt_payload",
    "build_moderator_prompt",
    "build_parallel_reviewer_prompt",
    "build_roundtable_turn_prompt",
    "default_parallel_participants",
    "is_date_sensitive_question",
    "normalize_argue_personas",
    "parse_participant_specs",
    "parse_protocol_turn",
    "summarize_protocol_transcript",
]
