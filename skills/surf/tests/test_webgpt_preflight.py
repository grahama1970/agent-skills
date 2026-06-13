"""Fixture-backed regression tests for WebGPT tab preflight targeting."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

SURF_DIR = Path(__file__).resolve().parents[1]
PREFLIGHT = SURF_DIR / "scripts" / "webgpt-preflight.sh"


def _fake_surf(tmp_path: Path) -> Path:
    script = tmp_path / "fake-surf.sh"
    script.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  focus.state)
    printf '{"activeTabId":"999","focusedWindowId":"1"}\\n'
    ;;
  tab.list)
    printf '%s' "${SURF_FAKE_TAB_LIST:-}"
    ;;
  *)
    echo "unexpected fake surf command: $*" >&2
    exit 64
    ;;
esac
""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def _preflight(tmp_path: Path, tabs: str, *args: str) -> tuple[int, dict]:
    env = os.environ.copy()
    env["SURF_RUN_SH"] = str(_fake_surf(tmp_path))
    env["SURF_FAKE_TAB_LIST"] = tabs
    proc = subprocess.run(
        [str(PREFLIGHT), "--json", *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, json.loads(proc.stdout)


def test_url_only_duplicate_same_url_fails_closed(tmp_path: Path) -> None:
    url = "https://chatgpt.com/c/11111111-1111-1111-1111-111111111111"
    tabs = f"1\tReview A\t{url}\n2\tReview B\t{url}\n"

    code, out = _preflight(tmp_path, tabs, "--url", url, "--no-activate")

    assert code == 5
    assert out["status"] == "fail"
    assert out["error"] == "ambiguous_url"
    assert "url_ambiguous" in out["failures"]
    assert len(out["url_resolution"]["candidates"]) == 2


def test_explicit_tab_id_with_expected_url_validates_that_tab_directly(
    tmp_path: Path,
) -> None:
    url = "https://chatgpt.com/c/11111111-1111-1111-1111-111111111111"
    tabs = f"1\tReview A\t{url}\n2\tReview B\t{url}\n"

    code, out = _preflight(
        tmp_path,
        tabs,
        "--tab-id",
        "1",
        "--expect-url",
        url,
        "--no-activate",
    )

    assert code == 0
    assert out["status"] == "pass"
    assert out["requested_tab_id"] == "1"


def test_wrong_explicit_tab_id_with_expected_url_fails(tmp_path: Path) -> None:
    expected = "https://chatgpt.com/c/22222222-2222-2222-2222-222222222222"
    tabs = (
        "1\tWrong\t"
        "https://chatgpt.com/c/11111111-1111-1111-1111-111111111111\n"
        f"2\tExpected\t{expected}\n"
    )

    code, out = _preflight(
        tmp_path,
        tabs,
        "--tab-id",
        "1",
        "--expect-url",
        expected,
        "--no-activate",
    )

    assert code == 5
    assert out["status"] == "fail"
    assert out["error"] == "expected_url_mismatch"
    assert out["requested_tab_id"] == "1"

