"""Tests for fail-closed WebGPT tab identity checks."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / "scripts" / "lib"
CHECKER = LIB / "webgpt_tab_identity.py"


def _check(tab_id: str, tab_list: str, *args: str) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, str(CHECKER), "check", "--tab-id", tab_id, *args],
        input=tab_list,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, json.loads(proc.stdout)


def test_multiple_chatgpt_tabs_require_identity_evidence():
    tabs = (
        "837346327\tDelegate review\t"
        "https://chatgpt.com/c/11111111-1111-1111-1111-111111111111\n"
        "837346844\tVisual review\t"
        "https://chatgpt.com/c/22222222-2222-2222-2222-222222222222\n"
    )
    code, out = _check("837346327", tabs)
    assert code == 5
    assert out["ok"] is False
    assert out["error"] == "unverified_tab_id_with_multiple_chatgpt_tabs"


def test_expected_url_verifies_requested_tab():
    tabs = (
        "837346327\tDelegate review\t"
        "https://chatgpt.com/c/11111111-1111-1111-1111-111111111111\n"
        "837346844\tVisual review\t"
        "https://chatgpt.com/c/22222222-2222-2222-2222-222222222222\n"
    )
    code, out = _check(
        "837346327",
        tabs,
        "--expect-url",
        "https://chatgpt.com/c/11111111-1111-1111-1111-111111111111",
    )
    assert code == 0
    assert out["ok"] is True
    assert out["tab_id"] == "837346327"


def test_expected_url_matching_different_tab_fails():
    tabs = (
        "837346327\tDelegate review\t"
        "https://chatgpt.com/c/11111111-1111-1111-1111-111111111111\n"
        "837346844\tVisual review\t"
        "https://chatgpt.com/c/22222222-2222-2222-2222-222222222222\n"
    )
    code, out = _check(
        "837346327",
        tabs,
        "--expect-url",
        "https://chatgpt.com/c/22222222-2222-2222-2222-222222222222",
    )
    assert code == 5
    assert out["error"] == "expected_url_mismatch"
    assert out["url_resolution"]["tab_id"] == "837346844"


def test_expected_title_verifies_requested_tab():
    tabs = (
        "837346327\tDelegate review\t"
        "https://chatgpt.com/c/11111111-1111-1111-1111-111111111111\n"
        "837346844\tVisual review\t"
        "https://chatgpt.com/c/22222222-2222-2222-2222-222222222222\n"
    )
    code, out = _check("837346844", tabs, "--expect-title", "visual")
    assert code == 0
    assert out["ok"] is True


def test_single_chatgpt_tab_allows_bare_tab_id():
    tabs = (
        "837346327\tDelegate review\t"
        "https://chatgpt.com/c/11111111-1111-1111-1111-111111111111\n"
    )
    code, out = _check("837346327", tabs)
    assert code == 0
    assert out["ok"] is True


def test_non_chatgpt_tab_id_fails():
    tabs = (
        "837346327\tDocs\t"
        "https://example.com/\n"
        "837346844\tVisual review\t"
        "https://chatgpt.com/c/22222222-2222-2222-2222-222222222222\n"
    )
    code, out = _check("837346327", tabs)
    assert code == 5
    assert out["error"] == "tab_not_open_chatgpt"
