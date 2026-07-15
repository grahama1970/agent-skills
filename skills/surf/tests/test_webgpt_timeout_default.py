"""Configuration contract for long-running WebGPT responses."""

from pathlib import Path
import subprocess


SURF_SKILL = Path(__file__).resolve().parents[1]
SUBMIT_SCRIPT = SURF_SKILL / "scripts" / "webgpt-submit.sh"


def test_webgpt_submit_defaults_to_forty_minutes() -> None:
    script = SUBMIT_SCRIPT.read_text(encoding="utf-8")
    help_result = subprocess.run(
        ["bash", str(SUBMIT_SCRIPT), "--help"],
        capture_output=True,
        text=True,
        check=True,
    )

    assert 'timeout_s="${SURF_WEBGPT_TIMEOUT:-2400}"' in script
    assert "Default: 2400 (40 minutes)." in help_result.stdout
