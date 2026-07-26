from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
GEMINI_SUBMIT = REPO_ROOT / "skills/surf/scripts/gemini-submit.sh"


def test_gemini_submit_uses_requested_tab_id_when_upstream_omits_metadata(
    tmp_path: Path,
) -> None:
    request = tmp_path / "request.md"
    response = tmp_path / "response.md"
    meta = tmp_path / "response.meta.json"
    fake_run = tmp_path / "surf-run.sh"

    request.write_text("Reply with exactly: gemini smoke\n", encoding="utf-8")
    fake_run.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  focus.state)
    printf '{"focusedWindowId":1,"activeTabId":837361258}\\n'
    ;;
  gemini_tab)
    printf 'gemini smoke<<<GEMINI_DONE:test>>>\\n'
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
            str(GEMINI_SUBMIT),
            "--input",
            str(request),
            "--output",
            str(response),
            "--meta-output",
            str(meta),
            "--sentinel",
            "<<<GEMINI_DONE:test>>>",
            "--tab-id",
            "837361258",
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
    payload = json.loads(meta.read_text(encoding="utf-8"))
    assert payload["status"] == "completed"
    assert payload["controlled_tab_id"] == "837361258"
    assert payload["controlled_tab_id_source"] == "requested_tab_id_fallback"
    assert payload["controlled_tab_id_mismatch"] is False


def test_gemini_submit_retries_stalled_exact_tab_after_cooldown(tmp_path: Path) -> None:
    request = tmp_path / "request.md"
    response = tmp_path / "response.md"
    meta = tmp_path / "response.meta.json"
    fake_run = tmp_path / "surf-run.sh"
    attempts = tmp_path / "attempts"
    invocations = tmp_path / "invocations"

    request.write_text("Reply with exactly: gemini smoke\n", encoding="utf-8")
    fake_run.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> {invocations}
case "${{1:-}}" in
  focus.state)
    printf '{{"focusedWindowId":1,"activeTabId":837361258}}\\n'
    ;;
  gemini_tab)
    count=0
    [[ -f {attempts} ]] && count=$(cat {attempts})
    count=$((count + 1))
    printf '%s' "$count" > {attempts}
    if [[ "$count" -eq 1 ]]; then
      echo 'Error: Response timeout' >&2
      exit 1
    fi
    printf 'gemini smoke<<<GEMINI_DONE:test>>>\\n'
    ;;
  go)
    exit 0
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
    env["SURF_GEMINI_STALL_COOLDOWN_SECONDS"] = "0"
    proc = subprocess.run(
        [
            "bash",
            str(GEMINI_SUBMIT),
            "--input",
            str(request),
            "--output",
            str(response),
            "--meta-output",
            str(meta),
            "--sentinel",
            "<<<GEMINI_DONE:test>>>",
            "--tab-id",
            "837361258",
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
    payload = json.loads(meta.read_text(encoding="utf-8"))
    assert payload["status"] == "completed"
    assert payload["stall_retry_count"] == 1
    assert payload["stall_retry_attempts"] == 1
    assert payload["stall_cooldown_seconds"] == 0
    assert attempts.read_text(encoding="utf-8") == "2"
    assert "go https://gemini.google.com/app --tab-id 837361258 --json" in invocations.read_text(
        encoding="utf-8"
    )
