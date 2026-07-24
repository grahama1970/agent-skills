from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
GROK_SUBMIT = REPO_ROOT / "skills/surf/scripts/grok-submit.sh"


def write_fake_surf(path: Path, *, tab_url: str, response: str = "") -> None:
    path.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
case "${{1:-}}" in
  tab.list)
    printf '%s\\n' '[{{"id":123,"title":"Grok","url":"{tab_url}"}}]'
    ;;
  focus.state)
    printf '%s\\n' '{{"activeTabId":999,"activeTabUrl":"https://example.test/"}}'
    ;;
  grok)
    printf '%b\\n' {json.dumps(response)}
    ;;
  *)
    echo "unexpected fake surf command: $*" >&2
    exit 99
    ;;
esac
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def run_grok_submit(tmp_path: Path, fake_surf: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    request = tmp_path / "request.md"
    request.write_text("Say pong.", encoding="utf-8")
    output = tmp_path / "response.md"
    env = os.environ.copy()
    env["SURF_RUN_SH"] = str(fake_surf)
    return subprocess.run(
        [
            "bash",
            str(GROK_SUBMIT),
            "--input",
            str(request),
            "--output",
            str(output),
            "--sentinel",
            "<<<GROK_DONE:TEST>>>",
            *extra,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )


def test_grok_submit_dispatches_from_run_sh_help() -> None:
    proc = subprocess.run(
        ["bash", str(REPO_ROOT / "skills/surf/run.sh"), "--help"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0
    assert "surf grok.submit --input request.md --output response.md" in proc.stdout


def test_grok_submit_cleans_terminal_sentinel_and_writes_meta(tmp_path: Path) -> None:
    fake_surf = tmp_path / "surf"
    write_fake_surf(fake_surf, tab_url="https://grok.com/", response="pong\n<<<GROK_DONE:TEST>>>")

    proc = run_grok_submit(
        tmp_path,
        fake_surf,
        "--tab-id",
        "123",
        "--url",
        "https://grok.com",
        "--no-activate",
    )

    assert proc.returncode == 0, proc.stderr
    response = tmp_path / "response.md"
    meta = json.loads((tmp_path / "response.md.meta.json").read_text(encoding="utf-8"))
    assert response.read_text(encoding="utf-8") == "pong\n"
    assert meta["status"] == "completed"
    assert meta["proof_status"] == "response_proven"
    assert meta["raw_contains_sentinel"] is True
    assert meta["clean_contains_sentinel"] is False
    assert meta["requested_tab_id"] == "123"
    assert meta["tab_identity_preflight"]["ok"] is True
    assert meta["no_activate"] is True


def test_grok_submit_rejects_wrong_tab_before_provider_submit(tmp_path: Path) -> None:
    fake_surf = tmp_path / "surf"
    write_fake_surf(fake_surf, tab_url="https://chatgpt.com/", response="should not run")

    proc = run_grok_submit(tmp_path, fake_surf, "--tab-id", "123", "--url", "https://grok.com")

    assert proc.returncode == 4
    meta = json.loads((tmp_path / "response.md.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "failed"
    assert meta["failure"] == "browser_tab_identity_mismatch"
    assert meta["proof_status"] == "wrong_tab"
    assert meta["tab_identity_preflight"]["provider_ok"] is False
