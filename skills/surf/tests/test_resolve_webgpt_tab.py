"""Tests for ChatGPT tab URL resolution."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / "scripts" / "lib"
RESOLVER = LIB / "resolve_webgpt_tab.py"


def _resolve(url: str, tab_list: str) -> dict:
    proc = subprocess.run(
        [sys.executable, str(RESOLVER), "resolve-url", "--url", url],
        input=tab_list,
        capture_output=True,
        text=True,
        check=False,
    )
    return json.loads(proc.stdout)


def test_exact_url_match():
    tabs = "837344525\tReview\t\thttps://chatgpt.com/c/6a0097ff-e7e0-83ea-93c2-3a6b88e2a67f\n"
    out = _resolve("https://chatgpt.com/c/6a0097ff-e7e0-83ea-93c2-3a6b88e2a67f", tabs)
    assert out["ok"] is True
    assert out["tab_id"] == "837344525"


def test_trailing_slash_and_uuid_case():
    tabs = "99\tX\thttps://chatgpt.com/c/ABCDEF12-3456-7890-ABCD-EF1234567890\n"
    out = _resolve(
        "https://www.chatgpt.com/c/abcdef12-3456-7890-abcd-ef1234567890/",
        tabs,
    )
    assert out["ok"] is True
    assert out["tab_id"] == "99"


def test_ambiguous_duplicate_conversation():
    tabs = (
        "1\ta\thttps://chatgpt.com/c/11111111-1111-1111-1111-111111111111\n"
        "2\tb\thttps://chatgpt.com/c/11111111-1111-1111-1111-111111111111\n"
    )
    out = _resolve("https://chatgpt.com/c/11111111-1111-1111-1111-111111111111", tabs)
    assert out["ok"] is False
    assert out["error"] == "ambiguous_url"
    assert len(out["candidates"]) == 2
