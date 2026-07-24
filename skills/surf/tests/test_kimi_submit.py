from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
KIMI_SUBMIT = REPO_ROOT / "skills/surf/scripts/kimi-submit.sh"


def test_kimi_submit_defaults_to_instant_high(tmp_path: Path) -> None:
    request = tmp_path / "request.md"
    response = tmp_path / "response.md"
    meta = tmp_path / "response.meta.json"
    fake_run = tmp_path / "surf-run.sh"
    invocation_log = tmp_path / "surf-invocations.log"

    request.write_text("Reply with exactly: kimi smoke\n", encoding="utf-8")
    fake_run.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> {str(invocation_log)!r}
case "${{1:-}}" in
  focus.state)
    printf '{{"focusedWindowId":1,"activeTabId":837360924}}\\n'
    ;;
  kimi_tab)
    printf 'kimi smoke<<<KIMI_DONE:test>>>\\n'
    printf 'Tab ID: 837360924\\nActivated: false\\nTabWasCreated: false\\n' >&2
    ;;
  *)
    echo "unexpected surf command: $*" >&2
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
            str(KIMI_SUBMIT),
            "--input",
            str(request),
            "--output",
            str(response),
            "--meta-output",
            str(meta),
            "--sentinel",
            "<<<KIMI_DONE:test>>>",
            "--tab-id",
            "837360924",
            "--no-activate",
            "--stable-polls",
            "0",
            "--timeout",
            "5",
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    invocation = invocation_log.read_text(encoding="utf-8")
    assert "--model Instant" in invocation
    assert "--reasoning High" in invocation
    payload = json.loads(meta.read_text(encoding="utf-8"))
    assert payload["requested_model"] == "Instant"
    assert payload["requested_reasoning"] == "High"
