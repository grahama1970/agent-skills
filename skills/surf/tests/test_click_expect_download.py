from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_run_sh_routes_explicit_download_click_to_wrapper(tmp_path: Path) -> None:
    calls = tmp_path / "calls"
    wrapper = tmp_path / "wrapper.sh"
    wrapper.write_text(
        "#!/usr/bin/env bash\nprintf '%s\\n' \"$@\" > \"$CALLS\"\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    env = os.environ.copy()
    env.update({"SURF_CLICK_DOWNLOAD_SH": str(wrapper), "CALLS": str(calls)})

    result = subprocess.run(
        [
            "bash",
            "skills/surf/run.sh",
            "click",
            "e12",
            "--tab-id",
            "837358033",
            "--download-output",
            "artifact.json",
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert calls.read_text(encoding="utf-8").splitlines() == [
        "e12",
        "--tab-id",
        "837358033",
        "--download-output",
        "artifact.json",
    ]


def test_click_wrapper_snapshots_then_completes_download(tmp_path: Path) -> None:
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    output = tmp_path / "result.json"
    calls = tmp_path / "calls.log"
    fake_run = tmp_path / "run.sh"
    fake_download = tmp_path / "download.sh"
    fake_run.write_text(
        """#!/usr/bin/env bash
if [[ "$1" == "js" ]]; then printf '%s\n' '"{\\"chatgpt\\":true,\\"busy\\":false}"'; exit 0; fi
printf 'click:%s\n' "$*" >> "$CALLS"
""",
        encoding="utf-8",
    )
    fake_download.write_text(
        """#!/usr/bin/env bash
printf 'download:%s\n' "$*" >> "$CALLS"
while [[ $# -gt 0 ]]; do
  if [[ "$1" == "--output" ]]; then output="$2"; shift 2; else shift; fi
done
printf '{"downloaded":true}\n' > "$output"
""",
        encoding="utf-8",
    )
    fake_run.chmod(0o755)
    fake_download.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "SURF_RUN_SH": str(fake_run),
            "SURF_DOWNLOAD_SH": str(fake_download),
            "CALLS": str(calls),
        }
    )

    result = subprocess.run(
        [
            "bash",
            "skills/surf/scripts/click-with-download.sh",
            "e12",
            "--tab-id",
            "837358033",
            "--download-output",
            str(output),
            "--downloads-dir",
            str(downloads),
            "--download-timeout",
            "8",
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert output.read_text(encoding="utf-8") == '{"downloaded":true}\n'
    lines = calls.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "click:click e12 --tab-id 837358033"
    assert "--after-click" in lines[1]
    assert "--before-manifest" in lines[1]
    assert f"--output {output}" in lines[1]


def test_click_wrapper_blocks_busy_chatgpt_before_click(tmp_path: Path) -> None:
    calls = tmp_path / "calls.log"
    fake_run = tmp_path / "run.sh"
    fake_run.write_text(
        """#!/usr/bin/env bash
printf '%s\n' "$*" >> "$CALLS"
printf '%s\n' '"{\\"chatgpt\\":true,\\"busy\\":true}"'
""",
        encoding="utf-8",
    )
    fake_run.chmod(0o755)
    env = os.environ.copy()
    env.update({"SURF_RUN_SH": str(fake_run), "CALLS": str(calls)})

    result = subprocess.run(
        [
            "bash",
            "skills/surf/scripts/click-with-download.sh",
            "e12",
            "--tab-id",
            "837358033",
            "--expect-download",
            "--downloads-dir",
            str(tmp_path / "Downloads"),
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 6
    assert "download click blocked until the page is idle" in result.stderr
    assert calls.read_text(encoding="utf-8").splitlines() == [
        "js return JSON.stringify({chatgpt:location.hostname==='chatgpt.com',busy:Array.from(document.querySelectorAll('button')).some(e=>/stop (generating|answering|response)/i.test([e.getAttribute('aria-label'),e.textContent].filter(Boolean).join(' ')))}) --tab-id 837358033"
    ]
