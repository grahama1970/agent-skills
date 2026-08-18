"""The prompt sanitizer must not rewrite things that are not paths.

A live /ask webgpt review of the project-watchdog cron design was corrupted
because `/project-watchdog`, `/ticket` and `/monitor-sparta` are skill
references and `*/5` is a cron minute field. All four were rewritten to
"[local-only path not attached: ...]", so the reviewer never saw the interval
it had been asked to judge and answered about a placeholder.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import tau_roundtable_worker as worker  # noqa: E402


@pytest.mark.parametrize("skill", ["/project-watchdog", "/ticket", "/monitor-sparta", "/ask", "/tau"])
def test_a_skill_reference_is_not_a_local_path(skill: str) -> None:
    assert worker._local_path_candidates(f"run {skill} now") == []


@pytest.mark.parametrize("field", ["*/5", "*/15", "*/2"])
def test_a_cron_minute_field_is_not_a_local_path(field: str) -> None:
    assert worker._local_path_candidates(f"schedule at {field} * * * *") == []


def test_a_real_absolute_file_is_still_sanitized() -> None:
    """The guard still catches what it was written for."""
    assert "/etc/hostname" in worker._local_path_candidates("see /etc/hostname for the name")


def test_a_multi_segment_path_is_still_sanitized() -> None:
    found = worker._local_path_candidates("the bundle at /tmp/review/bundle.md")
    assert "/tmp/review/bundle.md" in found


def test_a_mixed_prompt_keeps_skills_and_catches_paths() -> None:
    text = "Use /project-watchdog at */5; the log is /etc/hostname"
    found = worker._local_path_candidates(text)
    assert found == ["/etc/hostname"]


def test_urls_are_never_treated_as_local_paths() -> None:
    assert worker._local_path_candidates("see https://example.com/a/b") == []
