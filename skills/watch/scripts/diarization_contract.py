"""Diarization contract constants for Watch.

This module intentionally contains no pyannote imports and no service calls.
It defines the stable vocabulary shared by schemas, tests, reports, and future
client/service code.
"""
from __future__ import annotations

DIARIZATION_SCHEMA = "watch.diarization.v1"
SPEAKER_ATTRIBUTION_SCHEMA = "watch.speaker_attribution.v1"

DIARIZATION_MODES = ("auto", "pyannote", "none")

DIARIZATION_STATUSES = (
    "complete",
    "disabled",
    "unavailable",
    "failed",
)

DIARIZATION_ERROR_CODES = (
    "DIARIZATION_DISABLED",
    "DIARIZATION_SERVICE_UNAVAILABLE",
    "DIARIZATION_AUTH_REQUIRED",
    "DIARIZATION_MODEL_LOAD_FAILED",
    "DIARIZATION_TIMEOUT",
    "DIARIZATION_AUDIO_INVALID",
    "DIARIZATION_DURATION_EXCEEDED",
    "DIARIZATION_NO_SPEECH",
    "DIARIZATION_INFERENCE_FAILED",
)

DIARIZATION_GAPS = tuple(code.lower() for code in DIARIZATION_ERROR_CODES)

SPEAKER_ATTRIBUTION_STATUSES = (
    "assigned",
    "multiple",
    "unassigned",
)

SPEAKER_SOURCE_VALUES = (
    "pyannote_exclusive",
    "pyannote_regular_overlap",
    "none",
)

IDENTITY_BOUNDARY_RULES = (
    "anonymous_speaker_labels_are_not_character_identity",
    "anonymous_speaker_labels_are_not_actor_identity",
    "anonymous_speaker_labels_are_stable_only_within_one_artifact",
    "speaker_to_character_mapping_requires_separate_evidence",
    "speaker_to_character_mapping_must_remain_candidate_until_human_acceptance",
)

DEFAULT_DIARIZATION_MODEL = "pyannote/speaker-diarization-community-1"
PINNED_PYANNOTE_AUDIO_VERSION = "4.0.7"
