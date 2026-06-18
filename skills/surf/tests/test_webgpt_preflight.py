from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
WEBGPT_PREFLIGHT = REPO_ROOT / "skills/surf/scripts/webgpt-preflight.sh"


def test_preflight_no_activate_allows_active_controlled_tab(tmp_path: Path) -> None:
    fake_run = tmp_path / "surf-run.sh"
    fake_run.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  tab.list)
    printf '837352334\\tAgentic Research - Boris Loop\\thttps://chatgpt.com/c/example\\n'
    ;;
  focus.state)
    printf '{"focusedWindowId":456,"activeTabId":837352334}\\n'
    ;;
  *)
    echo "unexpected command: $*" >&2
    exit 99
    ;;
esac
""",
        encoding="utf-8",
    )
    fake_run.chmod(0o755)
    env = os.environ.copy()
    env["SURF_RUN_SH"] = str(fake_run)

    proc = subprocess.run(
        [
            "bash",
            str(WEBGPT_PREFLIGHT),
            "--tab-id",
            "837352334",
            "--expect-url",
            "https://chatgpt.com/c/example",
            "--no-activate",
            "--json",
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["status"] == "pass"
    assert data["active_tab_id"] == "837352334"
    checks = {check["name"]: check for check in data["checks"]}
    assert checks["foreground_controlled_user_visible"]["ok"] is True
    assert "not_foreground_controlled" not in checks

