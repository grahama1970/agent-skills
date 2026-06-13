"""Regression tests for WebGPT submit target recovery."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

SURF_DIR = Path(__file__).resolve().parents[1]
SUBMIT = SURF_DIR / "scripts" / "webgpt-submit.sh"
URL = "https://chatgpt.com/c/11111111-1111-1111-1111-111111111111"


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
  chatgpt)
    tab_id=""
    sentinel=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --tab-id) tab_id="${2:-}"; shift 2 ;;
        --sentinel) sentinel="${2:-}"; shift 2 ;;
        *) shift ;;
      esac
    done
    printf 'Tab ID: %s\\nActivated: false\\nTabWasCreated: false\\n' "$tab_id" >&2
    printf 'VERDICT: PASS\\n%s\\n' "$sentinel"
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


def _fake_browser_oracle(tmp_path: Path, *, tab_id: str = "100", url: str = URL) -> Path:
    script = tmp_path / "fake-browser-oracle.sh"
    payload = json.dumps(
        {
            "status": "resolved",
            "project": "demo",
            "tab_id": tab_id,
            "conversation_url": url,
        }
    )
    script.write_text(f"#!/usr/bin/env bash\nprintf '%s\\n' {payload!r}\n", encoding="utf-8")
    script.chmod(0o755)
    return script


def _run_submit(tmp_path: Path, tabs: str, *, bo_url: str = URL) -> subprocess.CompletedProcess[str]:
    request = tmp_path / "request.md"
    response = tmp_path / "response.md"
    request.write_text("Review this.", encoding="utf-8")
    env = os.environ.copy()
    env["SURF_RUN_SH"] = str(_fake_surf(tmp_path))
    env["SURF_FAKE_TAB_LIST"] = tabs
    env["BROWSER_ORACLE_RUN"] = str(_fake_browser_oracle(tmp_path, url=bo_url))
    return subprocess.run(
        [
            str(SUBMIT),
            "--input",
            str(request),
            "--output",
            str(response),
            "--project",
            "demo",
            "--no-activate",
            "--timeout",
            "5",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_browser_oracle_stale_tab_recovers_by_unique_url(tmp_path: Path) -> None:
    proc = _run_submit(tmp_path, f"200\tRecovered\t{URL}\n")

    assert proc.returncode == 0, proc.stderr
    meta = json.loads((tmp_path / "response.md.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "completed"
    assert meta["requested_tab_id"] == "200"
    assert meta["controlled_tab_id"] == "200"
    assert meta["requested_url"] == URL
    assert meta["tab_identity_preflight"]["url_recovery_from_browser_oracle_tab_id_failure"] is True
    assert meta["tab_identity_preflight"]["initial_requested_tab_id"] == "100"


def test_browser_oracle_stale_tab_with_duplicate_url_blocks_before_submit(
    tmp_path: Path,
) -> None:
    proc = _run_submit(tmp_path, f"200\tA\t{URL}\n201\tB\t{URL}\n")

    assert proc.returncode == 2
    meta = json.loads((tmp_path / "response.md.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "failed"
    assert meta["failure"] == "tab_identity_preflight_failed"
    recovery = meta["tab_identity_preflight"]["url_recovery_resolution"]
    assert recovery["error"] == "ambiguous_url"
    assert len(recovery["candidates"]) == 2

