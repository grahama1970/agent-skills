"""Auditable, expected-conditioned ASR comparison for audio E2E turns."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


# Inline emotion tags trained into the Orpheus
# ``horus_orpheus_lora_v2_identity_plus_emotions`` checkpoint. The synthesized
# case-audio path injects these into the spoken query so each tone family renders
# with its intended prosody; the checkpoint renders them as non-verbal sounds,
# never as spoken words. They are therefore stripped from BOTH expected and
# actual text before tokenization so they can never inflate the word error rate.
ORPHEUS_EMOTION_TAGS = (
    "laugh",
    "chuckle",
    "sigh",
    "cough",
    "sniffle",
    "groan",
    "yawn",
    "gasp",
)
EMOTION_TAG_RE = re.compile(
    r"<(?:" + "|".join(ORPHEUS_EMOTION_TAGS) + r")>", re.IGNORECASE
)
EMOTION_TAG_NORMALIZATION = {
    "policy": "strip_orpheus_inline_emotion_tags_before_tokenization_v1",
    "checkpoint": "horus_orpheus_lora_v2_identity_plus_emotions",
    "stripped_tags": [f"<{tag}>" for tag in ORPHEUS_EMOTION_TAGS],
}


ASR_COMPARISON_POLICY = {
    "schema": "embry.audio_e2e.asr_comparison_policy.v1",
    "policy_id": "expected_conditioned_exact_token_aliases_emotion_tag_stripped_v2",
    "emotion_tag_normalization": EMOTION_TAG_NORMALIZATION,
    "aliases": [
        {
            "alias_id": "horus_lupercal_lupa_cal_v1",
            "canonical_expected_tokens": ["horus", "lupercal"],
            "observed_actual_tokens": ["horus", "lupa", "cal"],
            "comparison_actual_tokens": ["horus", "lupercal"],
            "max_applications": 1,
        },
        {
            "alias_id": "pyannote_pianote_v1",
            "canonical_expected_tokens": ["pyannote"],
            "observed_actual_tokens": ["pianote"],
            "comparison_actual_tokens": ["pyannote"],
            "max_applications": 1,
        },
        {
            "alias_id": "pyannote_pionote_v1",
            "canonical_expected_tokens": ["pyannote"],
            "observed_actual_tokens": ["pionote"],
            "comparison_actual_tokens": ["pyannote"],
            "max_applications": 1,
        },
        {
            "alias_id": "pyannote_pionate_v1",
            "canonical_expected_tokens": ["pyannote"],
            "observed_actual_tokens": ["pionate"],
            "comparison_actual_tokens": ["pyannote"],
            "max_applications": 1,
        },
        {
            "alias_id": "horus_horace_v1",
            "canonical_expected_tokens": ["horus"],
            "observed_actual_tokens": ["horace"],
            "comparison_actual_tokens": ["horus"],
            "max_applications": 1,
        },
        {
            "alias_id": "embry_embree_v1",
            "canonical_expected_tokens": ["embry"],
            "observed_actual_tokens": ["embree"],
            "comparison_actual_tokens": ["embry"],
            "max_applications": 1,
        },
        {
            "alias_id": "embry_henry_v1",
            "canonical_expected_tokens": ["embry"],
            "observed_actual_tokens": ["henry"],
            "comparison_actual_tokens": ["embry"],
            "max_applications": 1,
        },
    ],
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


ASR_COMPARISON_POLICY_SHA256 = (
    "sha256:" + hashlib.sha256(_canonical(ASR_COMPARISON_POLICY)).hexdigest()
)

MANAGED_LISTENER_ASR_COMPARISON_POLICY = {
    "schema": "embry.audio_e2e.asr_comparison_policy.v1",
    "policy_id": "managed_listener_expected_conditioned_aliases_emotion_tag_stripped_v2",
    "base_policy_sha256": ASR_COMPARISON_POLICY_SHA256,
    "emotion_tag_normalization": EMOTION_TAG_NORMALIZATION,
    "aliases": [
        *ASR_COMPARISON_POLICY["aliases"],
        {
            "alias_id": "inline_in_line_segmentation_v1",
            "canonical_expected_tokens": ["inline"],
            "observed_actual_tokens": ["in", "line"],
            "comparison_actual_tokens": ["inline"],
            "max_applications": 1,
        },
    ],
}
MANAGED_LISTENER_ASR_COMPARISON_POLICY_SHA256 = (
    "sha256:"
    + hashlib.sha256(_canonical(MANAGED_LISTENER_ASR_COMPARISON_POLICY)).hexdigest()
)


def normalized_tokens(value: str) -> list[str]:
    # Strip Orpheus inline emotion tags (e.g. ``<sigh>``) before tokenizing so
    # the tag's inner word never becomes a comparison token. Plain text without
    # tags is unaffected, so existing WER numbers are unchanged.
    without_tags = EMOTION_TAG_RE.sub(" ", str(value))
    return re.sub(r"[^a-z0-9]+", " ", without_tags.lower()).split()


def word_error_rate(expected: list[str], actual: list[str]) -> float:
    previous = list(range(len(actual) + 1))
    for expected_token in expected:
        current = [previous[0] + 1]
        for index, actual_token in enumerate(actual, 1):
            current.append(min(
                current[-1] + 1,
                previous[index] + 1,
                previous[index - 1] + (expected_token != actual_token),
            ))
        previous = current
    return previous[-1] / max(1, len(expected))


def _contains(tokens: list[str], phrase: list[str]) -> bool:
    width = len(phrase)
    return any(tokens[index:index + width] == phrase for index in range(len(tokens) - width + 1))


def _replace_once(
    tokens: list[str],
    observed: list[str],
    replacement: list[str],
) -> tuple[list[str], int | None]:
    width = len(observed)
    for index in range(len(tokens) - width + 1):
        if tokens[index:index + width] == observed:
            return tokens[:index] + replacement + tokens[index + width:], index
    return tokens, None


def _compare_with_policy(
    expected_text: str,
    actual_text: str,
    *,
    policy: dict[str, Any],
    policy_sha256: str,
    strip_expected_wake: bool = True,
) -> dict[str, Any]:
    expected = normalized_tokens(expected_text)
    if strip_expected_wake and expected[:2] == ["hey", "embry"]:
        expected = expected[2:]
    actual = normalized_tokens(actual_text)
    comparison_actual = list(actual)
    applied: list[dict[str, Any]] = []

    for alias in policy["aliases"]:
        canonical = list(alias["canonical_expected_tokens"])
        if not _contains(expected, canonical):
            continue
        comparison_actual, index = _replace_once(
            comparison_actual,
            list(alias["observed_actual_tokens"]),
            list(alias["comparison_actual_tokens"]),
        )
        if index is not None:
            applied.append({
                "alias_id": alias["alias_id"],
                "actual_token_index": index,
                "expected_condition_satisfied": True,
            })

    raw_wer = word_error_rate(expected, actual)
    comparison_wer = word_error_rate(expected, comparison_actual)
    return {
        "schema": "embry.audio_e2e.asr_comparison.v1",
        "policy_id": policy["policy_id"],
        "policy_sha256": policy_sha256,
        "raw_expected_tokens": expected,
        "raw_actual_tokens": actual,
        "comparison_expected_tokens": expected,
        "comparison_actual_tokens": comparison_actual,
        "raw_wer": raw_wer,
        "comparison_wer": comparison_wer,
        "applied_aliases": applied,
        "journal_text_mutated": False,
    }


def compare_asr_text(
    expected_text: str,
    actual_text: str,
    *,
    strip_expected_wake: bool = True,
) -> dict[str, Any]:
    return _compare_with_policy(
        expected_text,
        actual_text,
        policy=ASR_COMPARISON_POLICY,
        policy_sha256=ASR_COMPARISON_POLICY_SHA256,
        strip_expected_wake=strip_expected_wake,
    )


def compare_managed_listener_asr_text(
    expected_text: str,
    actual_text: str,
) -> dict[str, Any]:
    return _compare_with_policy(
        expected_text,
        actual_text,
        policy=MANAGED_LISTENER_ASR_COMPARISON_POLICY,
        policy_sha256=MANAGED_LISTENER_ASR_COMPARISON_POLICY_SHA256,
        strip_expected_wake=True,
    )
