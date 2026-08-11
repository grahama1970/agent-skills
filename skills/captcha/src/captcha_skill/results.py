"""Semantic validation for ReCAP benchmark summaries.

Pydantic proves the upstream summary's internal arithmetic. This module binds
that summary to the authorized manifest: provider, requested task set, attempts,
call budget, and absence of task-level execution errors.
"""

from __future__ import annotations

from collections import Counter

from .constants import CAPTCHA_TYPES
from .errors import CaptchaSkillError, ErrorCode
from .models import AuthorizationManifest, CaptchaType, RecapSummary, TestMode


def validate_recap_summary_for_manifest(
    summary: RecapSummary,
    manifest: AuthorizationManifest,
) -> None:
    """Reject a well-shaped summary that does not represent the authorized run."""

    tasks = summary.tasks
    expected_total = (
        len(CAPTCHA_TYPES)
        if manifest.test_mode is TestMode.ONCE
        else manifest.test_size
    )
    if len(tasks) != expected_total:
        raise CaptchaSkillError(
            ErrorCode.RESULT_INVALID,
            "ReCAP summary task count does not match the authorized task set",
            {"expected": expected_total, "actual": len(tasks)},
        )

    task_errors = [
        {"task_id": task.task_id, "error": task.error}
        for task in tasks
        if task.error
    ]
    if task_errors:
        raise CaptchaSkillError(
            ErrorCode.RESULT_INVALID,
            "ReCAP task-level errors prevent a bounded capability measurement",
            {"task_errors": task_errors[:10]},
        )

    over_budget = [
        {"task_id": task.task_id, "calls_made": task.calls_made}
        for task in tasks
        if task.calls_made > manifest.max_calls
    ]
    if over_budget:
        raise CaptchaSkillError(
            ErrorCode.RESULT_INVALID,
            "ReCAP summary exceeds the authorized model-call budget",
            {"max_calls": manifest.max_calls, "tasks": over_budget},
        )

    mismatched_resolution = [
        {
            "task_id": task.task_id,
            "requested_type": task.requested_type.value,
            "resolved_type": task.resolved_type.value,
        }
        for task in tasks
        if task.requested_type is not task.resolved_type
    ]
    if mismatched_resolution:
        raise CaptchaSkillError(
            ErrorCode.RESULT_INVALID,
            "dynamic ReCAP tasks resolved to an unexpected CAPTCHA type",
            {"tasks": mismatched_resolution},
        )

    if manifest.test_mode is TestMode.ONCE:
        expected = Counter(CaptchaType(item) for item in CAPTCHA_TYPES)
        actual = Counter(task.requested_type for task in tasks)
        attempts = {task.attempt for task in tasks}
        if actual != expected or attempts != {1}:
            raise CaptchaSkillError(
                ErrorCode.RESULT_INVALID,
                "once-mode summary does not contain each authorized type exactly once",
                {
                    "expected_types": sorted(item.value for item in expected),
                    "actual_types": sorted(item.value for item in actual.elements()),
                    "attempts": sorted(attempts),
                },
            )
        return

    if manifest.captcha_name is None:
        raise CaptchaSkillError(
            ErrorCode.INVALID_MANIFEST,
            "custom mode requires captcha_name",
        )
    wrong_types = [
        task.requested_type.value
        for task in tasks
        if task.requested_type is not manifest.captcha_name
    ]
    expected_attempts = list(range(1, manifest.test_size + 1))
    actual_attempts = sorted(task.attempt for task in tasks)
    if wrong_types or actual_attempts != expected_attempts:
        raise CaptchaSkillError(
            ErrorCode.RESULT_INVALID,
            "custom-mode summary does not match the authorized CAPTCHA type and attempts",
            {
                "expected_type": manifest.captcha_name.value,
                "wrong_types": wrong_types,
                "expected_attempts": expected_attempts,
                "actual_attempts": actual_attempts,
            },
        )
