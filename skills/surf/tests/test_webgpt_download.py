"""Regression tests for ChatGPT generated-file download helper."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def test_webgpt_download_decodes_json_string_and_clicks_role_button(tmp_path: Path) -> None:
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    output = tmp_path / "artifact.zip"
    calls = tmp_path / "calls.log"
    fake_run = tmp_path / "fake-surf-run.sh"
    fake_run.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
cmd="${1:-}"
js="${2:-}"
printf '%s\n---\n' "$js" >> "$FAKE_CALLS_LOG"
if [[ "$cmd" != "js" ]]; then
  echo "unexpected command: $cmd" >&2
  exit 2
fi
if [[ "$js" == *"JSON.stringify(Array.from"* ]]; then
  python3 - <<'PY'
import json
print(json.dumps(json.dumps([{
    "text": "Download monitor-sparta-dewey-stale-embedding-solution.zip",
    "aria": "",
    "href": "",
    "download": "",
    "role": "button",
    "tag": "DIV",
}])))
PY
  exit 0
fi
if [[ "$js" == *"btn.click()"* ]]; then
  printf 'zip-bytes' > "$FAKE_DOWNLOADS_DIR/monitor-sparta-dewey-stale-embedding-solution.zip"
  printf '%s\n' '"clicked"'
  exit 0
fi
echo "unexpected js: $js" >&2
exit 3
""",
        encoding="utf-8",
    )
    fake_run.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "SURF_RUN_SH": str(fake_run),
            "FAKE_DOWNLOADS_DIR": str(downloads),
            "FAKE_CALLS_LOG": str(calls),
        }
    )
    result = subprocess.run(
        [
            "bash",
            "skills/surf/scripts/webgpt-download.sh",
            "--match",
            "monitor-sparta-dewey-stale-embedding-solution.zip",
            "--downloads-dir",
            str(downloads),
            "--output",
            str(output),
            "--poll-interval",
            "1",
            "--timeout",
            "8",
        ],
        cwd=Path(__file__).resolve().parents[3],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert output.read_text(encoding="utf-8") == "zip-bytes"
    call_log = calls.read_text(encoding="utf-8")
    assert "a,button,[role=button]" in call_log
    assert "JSON.stringify(Array.from" in call_log
    assert "btn.click()" in call_log


def test_webgpt_download_ignores_unrelated_new_file_and_selects_exact_basename(
    tmp_path: Path,
) -> None:
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    output = tmp_path / "artifact.zip"
    fake_run = tmp_path / "fake-surf-run.sh"
    fake_run.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
js="${2:-}"
if [[ "$js" == *"JSON.stringify(Array.from"* ]]; then
  printf '%s\n' '"[{\\"text\\":\\"Download expected.zip\\",\\"aria\\":\\"\\",\\"href\\":\\"\\",\\"download\\":\\"\\",\\"role\\":\\"button\\",\\"tag\\":\\"BUTTON\\"}]"'
elif [[ "$js" == *"btn.click()"* ]]; then
  printf 'stale-batch' > "$FAKE_DOWNLOADS_DIR/aaa-unrelated-batch.json"
  printf 'expected-bytes' > "$FAKE_DOWNLOADS_DIR/expected.zip"
  printf '%s\n' '"clicked"'
elif [[ "$js" == *"const download = candidates[0]"* ]]; then
  printf '%s\n' '"{\\"status\\":\\"not-found\\"}"'
else
  exit 3
fi
""",
        encoding="utf-8",
    )
    fake_run.chmod(0o755)
    env = os.environ.copy()
    env.update({"SURF_RUN_SH": str(fake_run), "FAKE_DOWNLOADS_DIR": str(downloads)})

    result = subprocess.run(
        [
            "bash",
            "skills/surf/scripts/webgpt-download.sh",
            "--match",
            "expected.zip",
            "--downloads-dir",
            str(downloads),
            "--output",
            str(output),
            "--poll-interval",
            "1",
            "--timeout",
            "8",
        ],
        cwd=Path(__file__).resolve().parents[3],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert output.read_text(encoding="utf-8") == "expected-bytes"
    assert "Ignoring unrelated download candidate: aaa-unrelated-batch.json" in result.stderr


def test_webgpt_download_fails_closed_when_only_new_file_has_wrong_basename(
    tmp_path: Path,
) -> None:
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    output = tmp_path / "artifact.zip"
    fake_run = tmp_path / "fake-surf-run.sh"
    fake_run.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
js="${2:-}"
if [[ "$js" == *"JSON.stringify(Array.from"* ]]; then
  printf '%s\n' '"[{\\"text\\":\\"Download expected.zip\\",\\"aria\\":\\"\\",\\"href\\":\\"\\",\\"download\\":\\"\\",\\"role\\":\\"button\\",\\"tag\\":\\"BUTTON\\"}]"'
elif [[ "$js" == *"btn.click()"* ]]; then
  printf 'wrong-bytes' > "$FAKE_DOWNLOADS_DIR/wrong.zip"
  printf '%s\n' '"clicked"'
elif [[ "$js" == *"const download = candidates[0]"* ]]; then
  printf '%s\n' '"{\\"status\\":\\"not-found\\"}"'
else
  exit 3
fi
""",
        encoding="utf-8",
    )
    fake_run.chmod(0o755)
    env = os.environ.copy()
    env.update({"SURF_RUN_SH": str(fake_run), "FAKE_DOWNLOADS_DIR": str(downloads)})

    result = subprocess.run(
        [
            "bash",
            "skills/surf/scripts/webgpt-download.sh",
            "--match",
            "expected.zip",
            "--downloads-dir",
            str(downloads),
            "--output",
            str(output),
            "--poll-interval",
            "1",
            "--timeout",
            "3",
        ],
        cwd=Path(__file__).resolve().parents[3],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 5
    assert not output.exists()
    assert "Ignoring unrelated download candidate: wrong.zip" in result.stderr
    assert "Exact download 'expected.zip' did not complete" in result.stderr


def test_webgpt_download_accepts_extension_pattern_without_exact_basename(
    tmp_path: Path,
) -> None:
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    output = tmp_path / "artifact.png"
    fake_run = tmp_path / "fake-surf-run.sh"
    fake_run.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
js="${2:-}"
if [[ "$js" == *"JSON.stringify(Array.from"* ]]; then
  printf '%s\n' '"[{\\"text\\":\\"Download generated-image.png\\",\\"aria\\":\\"\\",\\"href\\":\\"\\",\\"download\\":\\"\\",\\"role\\":\\"button\\",\\"tag\\":\\"BUTTON\\"}]"'
elif [[ "$js" == *"btn.click()"* ]]; then
  printf 'png-bytes' > "$FAKE_DOWNLOADS_DIR/generated-image.png"
  printf '%s\n' '"clicked"'
elif [[ "$js" == *"const download = candidates[0]"* ]]; then
  printf '%s\n' '"{\\"status\\":\\"not-found\\"}"'
else
  exit 3
fi
""",
        encoding="utf-8",
    )
    fake_run.chmod(0o755)
    env = os.environ.copy()
    env.update({"SURF_RUN_SH": str(fake_run), "FAKE_DOWNLOADS_DIR": str(downloads)})

    result = subprocess.run(
        [
            "bash",
            "skills/surf/scripts/webgpt-download.sh",
            "--match",
            ".png",
            "--downloads-dir",
            str(downloads),
            "--output",
            str(output),
            "--poll-interval",
            "1",
            "--timeout",
            "8",
        ],
        cwd=Path(__file__).resolve().parents[3],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert output.read_text(encoding="utf-8") == "png-bytes"


def test_webgpt_download_clicks_title_only_viewer_toolbar_control(tmp_path: Path) -> None:
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    output = tmp_path / "artifact.json"
    calls = tmp_path / "calls.log"
    fake_run = tmp_path / "fake-surf-run.sh"
    fake_run.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
js="${2:-}"
printf '%s\n---\n' "$js" >> "$FAKE_CALLS_LOG"
if [[ "$js" == *"return JSON.stringify(Array.from"* ]]; then
  python3 - <<'PY'
import json
print(json.dumps(json.dumps([{"text":"round-7 artifact.json","aria":"","title":"","href":"","download":"","role":"button","tag":"BUTTON"}])))
PY
elif [[ "$js" == *"btn.click()"* ]]; then
  printf '%s\n' '"clicked"'
elif [[ "$js" == *"const download = candidates[0]"* ]]; then
  printf 'artifact-bytes' > "$FAKE_DOWNLOADS_DIR/artifact.json"
  python3 - <<'PY'
import json
print(json.dumps(json.dumps({"status":"clicked","label":"Download","topRight":True})))
PY
else
  echo "unexpected js" >&2
  exit 3
fi
""",
        encoding="utf-8",
    )
    fake_run.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "SURF_RUN_SH": str(fake_run),
            "FAKE_DOWNLOADS_DIR": str(downloads),
            "FAKE_CALLS_LOG": str(calls),
        }
    )

    result = subprocess.run(
        [
            "bash",
            "skills/surf/scripts/webgpt-download.sh",
            "--match",
            "artifact.json",
            "--downloads-dir",
            str(downloads),
            "--output",
            str(output),
            "--poll-interval",
            "1",
            "--timeout",
            "8",
        ],
        cwd=Path(__file__).resolve().parents[3],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert output.read_text(encoding="utf-8") == "artifact-bytes"
    assert "Clicked artifact viewer Download control" in result.stderr
    call_log = calls.read_text(encoding="utf-8")
    assert "getAttribute('title')" in call_log
    assert "const download = candidates[0]" in call_log
    assert "r.bottom > 0" in call_log
    assert "r.top < innerHeight" in call_log
