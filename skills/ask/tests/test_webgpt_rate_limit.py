"""Regression tests for skills/ask/src/ask/webgpt_rate_limit.py."""

from __future__ import annotations

import json
import os
import pathlib
import sys
import time

import pytest

THIS_DIR = pathlib.Path(__file__).resolve().parent
SRC_DIR = THIS_DIR.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ask.webgpt_rate_limit import (
    WebgptRateLimitError,
    check_and_record,
)


def _isolate_env(tmp_path, monkeypatch, *, cap=3):
    monkeypatch.setenv("ASK_WEBGPT_RATE_LIMIT_FILE", str(tmp_path / "rl.json"))
    monkeypatch.setenv("ASK_WEBGPT_MAX_ROUNDS_PER_HOUR", str(cap))
    monkeypatch.delenv("ASK_WEBGPT_RATE_LIMIT_DISABLE", raising=False)


def test_first_call_records_and_returns_stats(tmp_path, monkeypatch):
    _isolate_env(tmp_path, monkeypatch, cap=3)
    info = check_and_record()
    assert info["rounds_in_window"] == 1
    assert info["cap"] == 3


def test_within_cap_allows_n_calls(tmp_path, monkeypatch):
    _isolate_env(tmp_path, monkeypatch, cap=3)
    check_and_record()
    check_and_record()
    info = check_and_record()
    assert info["rounds_in_window"] == 3


def test_exceeding_cap_raises(tmp_path, monkeypatch):
    _isolate_env(tmp_path, monkeypatch, cap=3)
    check_and_record()
    check_and_record()
    check_and_record()
    with pytest.raises(WebgptRateLimitError) as exc:
        check_and_record()
    msg = str(exc.value)
    assert "exhausted" in msg
    assert "3/3" in msg or "3 rounds" in msg
    assert "ASK_WEBGPT_MAX_ROUNDS_PER_HOUR" in msg


def test_disabled_env_bypasses(tmp_path, monkeypatch):
    _isolate_env(tmp_path, monkeypatch, cap=1)
    monkeypatch.setenv("ASK_WEBGPT_RATE_LIMIT_DISABLE", "1")
    # Even after exceeding the cap, no error.
    for _ in range(5):
        info = check_and_record()
        assert info["disabled"] is True


def test_old_calls_pruned_outside_window(tmp_path, monkeypatch):
    _isolate_env(tmp_path, monkeypatch, cap=2)
    state_path = tmp_path / "rl.json"
    # Seed with timestamps older than 1 hour.
    state_path.write_text(json.dumps([time.time() - 7200, time.time() - 5400]))
    info = check_and_record()
    # All stale entries pruned; only the new one counts.
    assert info["rounds_in_window"] == 1


def test_corrupt_state_file_does_not_block(tmp_path, monkeypatch):
    _isolate_env(tmp_path, monkeypatch, cap=2)
    state_path = tmp_path / "rl.json"
    state_path.write_text("not valid json {{{")
    info = check_and_record()
    # Corrupt file = treated as empty; current call proceeds.
    assert info["rounds_in_window"] == 1
