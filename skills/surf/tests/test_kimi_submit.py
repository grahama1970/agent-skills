from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
KIMI_SUBMIT = REPO_ROOT / "skills/surf/scripts/kimi-submit.sh"


def test_kimi_submit_defaults_to_current_kimi_settings(tmp_path: Path) -> None:
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
    assert "--model" not in invocation
    assert "--reasoning" not in invocation
    payload = json.loads(meta.read_text(encoding="utf-8"))
    assert payload["requested_model"] is None
    assert payload["requested_reasoning"] is None


def test_kimi_submit_passes_explicit_model_and_reasoning(tmp_path: Path) -> None:
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
            "--model",
            "Instant",
            "--reasoning",
            "High",
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


def test_kimi_submit_uses_requested_tab_id_when_upstream_omits_metadata(tmp_path: Path) -> None:
    request = tmp_path / "request.md"
    response = tmp_path / "response.md"
    meta = tmp_path / "response.meta.json"
    fake_run = tmp_path / "surf-run.sh"

    request.write_text("Reply with exactly: kimi smoke\n", encoding="utf-8")
    fake_run.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  focus.state)
    printf '{"focusedWindowId":1,"activeTabId":837360924}\\n'
    ;;
  kimi_tab)
    printf 'kimi smoke<<<KIMI_DONE:test>>>\\n'
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
    payload = json.loads(meta.read_text(encoding="utf-8"))
    assert payload["status"] == "completed"
    assert payload["controlled_tab_id"] == "837360924"
    assert payload["controlled_tab_id_source"] == "requested_tab_id_fallback"
    assert payload["controlled_tab_id_mismatch"] is False


def test_kimi_submit_classifies_missing_attachment_ui_before_submit(tmp_path: Path) -> None:
    request = tmp_path / "request.md"
    response = tmp_path / "response.md"
    meta = tmp_path / "response.meta.json"
    attachment = tmp_path / "bundle.md"
    fake_run = tmp_path / "surf-run.sh"

    request.write_text("Use the attached bundle and reply with exactly: kimi attachment smoke\n", encoding="utf-8")
    attachment.write_text("# Evidence\n\nReadable attachment text.\n", encoding="utf-8")
    fake_run.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  focus.state)
    printf '{"focusedWindowId":1,"activeTabId":837360924}\\n'
    ;;
  kimi_tab)
    echo 'Error: Kimi file input (input[type="file"]) not present in the DOM; Kimi may require opening the attachment menu first.' >&2
    exit 1
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
            "--attach-file",
            str(attachment),
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 1
    payload = json.loads(meta.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["failure"] == "attachment_ui_missing"
    assert payload["blocker"] == "BLOCKED_ATTACHMENT_UI_MISSING"
    assert payload["proof_status"] == "file_upload_unavailable"
    assert payload["attachment_ui_missing"] is True
    assert payload["attachment_missing"] is True
    assert payload["attach_file"] == str(attachment.resolve())


def test_kimi_submit_classifies_missing_attachment_metadata_after_response(tmp_path: Path) -> None:
    request = tmp_path / "request.md"
    response = tmp_path / "response.md"
    raw = tmp_path / "response.raw.md"
    meta = tmp_path / "response.meta.json"
    attachment = tmp_path / "bundle.md"
    fake_run = tmp_path / "surf-run.sh"

    request.write_text("Use the attached bundle and reply with exactly: kimi attachment smoke\n", encoding="utf-8")
    attachment.write_text("# Evidence\n\nReadable attachment text.\n", encoding="utf-8")
    fake_run.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  focus.state)
    printf '{"focusedWindowId":1,"activeTabId":837360924}\\n'
    ;;
  kimi_tab)
    printf 'KIMI_ATTACHMENT_RESULT: missing\\n<<<KIMI_DONE:test>>>\\n'
    echo 'Tab ID: 837360924' >&2
    echo 'ControlledTabID: 837360924' >&2
    echo 'Activated: false' >&2
    echo 'TabWasCreated: false' >&2
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
            "--raw-output",
            str(raw),
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
            "--attach-file",
            str(attachment),
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 5
    payload = json.loads(meta.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["failure"] == "attachment_ui_missing"
    assert payload["blocker"] == "BLOCKED_ATTACHMENT_UI_MISSING"
    assert payload["proof_status"] == "file_upload_unavailable"
    assert payload["attachment_ui_missing"] is True
    assert payload["attachment_missing"] is True
    assert payload["attach_file"] == str(attachment.resolve())
