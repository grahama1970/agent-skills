"""Auditable, expected-conditioned ASR comparison for audio E2E turns."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


ASR_COMPARISON_POLICY = {
    "schema": "embry.audio_e2e.asr_comparison_policy.v1",
    "policy_id": "expected_conditioned_exact_token_aliases_v1",
    "aliases": [
        {
            "alias_id": "horus_lupercal_lupa_cal_v1",
            "canonical_expected_tokens": ["horus", "lupercal"],
            "observed_actual_tokens": ["horus", "lupa", "cal"],
            "comparison_actual_tokens": ["horus", "lupercal"],
            "max_applications": 1,
        }
    ],
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


ASR_COMPARISON_POLICY_SHA256 = (
    "sha256:" + hashlib.sha256(_canonical(ASR_COMPARISON_POLICY)).hexdigest()
)


def normalized_tokens(value: str) -> list[str]:
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).split()


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


def compare_asr_text(
    expected_text: str,
    actual_text: str,
    *,
    strip_expected_wake: bool = True,
) -> dict[str, Any]:
    expected = normalized_tokens(expected_text)
    if strip_expected_wake and expected[:2] == ["hey", "embry"]:
        expected = expected[2:]
    actual = normalized_tokens(actual_text)
    comparison_actual = list(actual)
    applied: list[dict[str, Any]] = []

    for alias in ASR_COMPARISON_POLICY["aliases"]:
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
        "policy_id": ASR_COMPARISON_POLICY["policy_id"],
        "policy_sha256": ASR_COMPARISON_POLICY_SHA256,
        "raw_expected_tokens": expected,
        "raw_actual_tokens": actual,
        "comparison_expected_tokens": expected,
        "comparison_actual_tokens": comparison_actual,
        "raw_wer": raw_wer,
        "comparison_wer": comparison_wer,
        "applied_aliases": applied,
        "journal_text_mutated": False,
    }
