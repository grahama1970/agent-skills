from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
CLAUDE_SUBMIT = REPO_ROOT / "skills/surf/scripts/claude-submit.py"
SURF_RUN = REPO_ROOT / "skills/surf/run.sh"


def test_surf_run_routes_claude_submit_help() -> None:
    proc = subprocess.run(
        [str(SURF_RUN), "claude.submit", "--help"],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert "usage: surf claude.submit" in proc.stdout
    assert "--attach-file" in proc.stdout


def test_claude_submit_accepts_attach_file_and_records_upload_metadata(tmp_path: Path) -> None:
    request = tmp_path / "request.md"
    response = tmp_path / "response.md"
    meta = tmp_path / "response.meta.json"
    attachment = tmp_path / "prior-response.md"
    fake_run = tmp_path / "surf-run.sh"
    invocation_log = tmp_path / "surf-invocations.log"
    sentinel_file = tmp_path / "sentinel.txt"

    request.write_text("Review the attached prior handler response.\n", encoding="utf-8")
    attachment.write_text("Prior handler response.\n", encoding="utf-8")
    fake_run.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> {str(invocation_log)!r}
case "${{1:-}}" in
  focus.state)
    printf '{{"focusedWindowId":1,"activeTabId":837360812}}\\n'
    ;;
  text)
    sentinel="$(cat {str(sentinel_file)!r} 2>/dev/null || true)"
    printf 'https://claude.ai/chat/example\\nprior-response.md\\nClaude responded:\\nAttached review complete\\n%s\\n' "$sentinel"
    ;;
  read)
    printf 'textbox "Write your prompt to Claude" [e1]\\n'
    printf 'button "Send message" [e2]\\n'
    printf 'button "Upload files" [e3] type="file"\\n'
    printf 'prior-response.md\\n'
    ;;
  js)
    printf '{{"ok":true}}\\n'
    ;;
  upload)
    printf 'uploaded\\n'
    ;;
  click|key)
    printf 'ok\\n'
    ;;
  type)
    python3 - "${{2:-}}" {str(sentinel_file)!r} <<'PY'
import pathlib
import re
import sys

match = re.search(r"<<<CLAUDE_DONE:[^>]+>>>", sys.argv[1], re.S)
if match:
    pathlib.Path(sys.argv[2]).write_text(match.group(0), encoding="utf-8")
PY
    printf 'typed\\n'
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
            "python3",
            str(CLAUDE_SUBMIT),
            "--input",
            str(request),
            "--output",
            str(response),
            "--meta-output",
            str(meta),
            "--tab-id",
            "837360812",
            "--url",
            "https://claude.ai/chat/example",
            "--attach-file",
            str(attachment),
            "--stable-polls",
            "0",
            "--timeout",
            "5",
            "--no-activate",
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert response.read_text(encoding="utf-8").strip() == "Attached review complete"
    payload = json.loads(meta.read_text(encoding="utf-8"))
    assert payload["status"] == "completed"
    assert payload["attach_file"] == str(attachment.resolve())
    assert payload["attachment"] == {
        "path": str(attachment.resolve()),
        "filename": "prior-response.md",
        "upload_ref": "e3",
        "preview_visible": True,
    }
    assert payload["attachment_missing"] is False
    assert payload["attachment_preview_missing"] is False
    invocations = invocation_log.read_text(encoding="utf-8")
    assert "upload --ref e3 --files" in invocations
    assert str(attachment.resolve()) in invocations
