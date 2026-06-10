"""Unit tests for browser-oracle subprocess client."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ask.browser_oracle_client import (
    BrowserOracleResolveError,
    apply_webgpt_browser_oracle,
    resolve_browser_oracle,
)


def test_apply_skips_when_explicit_tab() -> None:
    project, tab, url, meta = apply_webgpt_browser_oracle(
        from_path="/tmp",
        project="",
        tab_id="123",
        url="",
        create_tab=False,
    )
    assert tab == "123"
    assert meta["status"] == "skipped"


@patch("ask.browser_oracle_client.subprocess.run")
def test_resolve_parses_json(mock_run: MagicMock, tmp_path: Path) -> None:
    payload = {
        "backend": "webgpt",
        "project": "oc-subagent-personas",
        "tab_id": "837352004",
        "conversation_url": "https://chatgpt.com/c/abc",
        "status": "ok",
    }
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=json.dumps(payload),
        stderr="",
    )
    with patch("ask.browser_oracle_client.browser_oracle_run_path", return_value=tmp_path / "run.sh"):
        (tmp_path / "run.sh").write_text("#!/bin/sh\n")
        (tmp_path / "run.sh").chmod(0o755)
        out = resolve_browser_oracle(from_path=str(tmp_path))
    assert out["project"] == "oc-subagent-personas"
    assert out["tab_id"] == "837352004"


@patch("ask.browser_oracle_client.subprocess.run")
def test_resolve_needs_attention(mock_run: MagicMock, tmp_path: Path) -> None:
    payload = {"status": "needs_attention", "reason": "no_registry"}
    mock_run.return_value = MagicMock(returncode=2, stdout=json.dumps(payload), stderr="")
    with patch("ask.browser_oracle_client.browser_oracle_run_path", return_value=tmp_path / "run.sh"):
        (tmp_path / "run.sh").write_text("#!/bin/sh\n")
        (tmp_path / "run.sh").chmod(0o755)
        out = resolve_browser_oracle(from_path=str(tmp_path))
    assert out["status"] == "needs_attention"


@patch("ask.browser_oracle_client.subprocess.run")
def test_apply_fills_project_and_tab(mock_run: MagicMock, tmp_path: Path) -> None:
    payload = {
        "project": "oc-subagent-personas",
        "tab_id": "837352004",
        "conversation_url": "",
        "status": "ok",
    }
    mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(payload), stderr="")
    with patch("ask.browser_oracle_client.browser_oracle_run_path", return_value=tmp_path / "run.sh"):
        (tmp_path / "run.sh").write_text("#!/bin/sh\n")
        (tmp_path / "run.sh").chmod(0o755)
        project, tab, url, meta = apply_webgpt_browser_oracle(
            from_path=str(tmp_path),
            project="",
            tab_id="",
            url="",
            create_tab=False,
        )
    assert project == "oc-subagent-personas"
    assert tab == "837352004"
    assert meta.get("browser_oracle_applied") is True
