"""Subprocess-level Surf target-proof tests."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from captcha_skill.errors import CaptchaSkillError, ErrorCode
from captcha_skill.models import AuthorizationManifest
from captcha_skill.preflight import preflight_surf_target

SKILL_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = SKILL_ROOT / "fixtures" / "authorization-valid-local.json"


def _manifest() -> AuthorizationManifest:
    return AuthorizationManifest.model_validate(json.loads(FIXTURE.read_text()))


def _fake_surf(tmp_path: Path) -> tuple[Path, Path]:
    script = tmp_path / "surf-run"
    log_path = tmp_path / "surf-calls.jsonl"
    script.write_text(
        """#!/usr/bin/env bash
set -euo pipefail

printf '["%s"]\\n' "${1:-}" >> "${FAKE_SURF_LOG}"
command="${1:-}"
shift || true

case "$command" in
  window.new)
    printf '%s\\n' '{"result":{"tabId":321,"windowId":654}}'
    ;;
  emulate.viewport)
    printf '%s\\n' '{"ok":true}'
    ;;
  js)
    printf '%s\\n' 'surf diagnostic line'
    printf '{"result":{"value":{"final_url":"%s","challenge_id":"%s"}}}\\n' \\
      "${FAKE_SURF_FINAL_URL:-http://127.0.0.1:5000/challenge/text}" \\
      "${FAKE_SURF_CHALLENGE_ID:-fixture-id}"
    ;;
  screenshot)
    output=''
    while (($#)); do
      if [[ "$1" == '--output' ]]; then
        output="$2"
        break
      fi
      shift
    done
    [[ -n "$output" ]]
    printf '\\211PNG\\r\\n\\032\\nfixture' > "$output"
    printf '{"path":"%s"}\\n' "$output"
    ;;
  tab.close)
    if [[ "${FAKE_SURF_CLOSE_FAIL:-0}" == '1' ]]; then
      printf '%s\\n' 'close failed' >&2
      exit 7
    fi
    printf '%s\\n' '{"closed":true,"tabId":321}'
    ;;
  *)
    printf '%s\\n' '{"error":"unsupported"}'
    exit 9
    ;;
esac
""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script, log_path


def _logged_commands(log_path: Path) -> list[list[str]]:
    return [json.loads(line) for line in log_path.read_text().splitlines()]


def test_surf_target_preflight_runs_real_subprocess_and_closes_tab(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_surf, log_path = _fake_surf(tmp_path)
    monkeypatch.setenv("FAKE_SURF_LOG", str(log_path))
    monkeypatch.setattr("captcha_skill.preflight.surf_run_path", lambda: fake_surf)
    screenshot = tmp_path / "surf-target-preflight.png"

    proof = preflight_surf_target(_manifest(), screenshot_path=screenshot)

    assert proof.status == "PASS"
    assert proof.tab_id == 321
    assert proof.challenge_url == "http://127.0.0.1:5000/challenge/text"
    assert proof.final_url == proof.challenge_url
    assert screenshot.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert len(proof.screenshot_sha256) == 64
    commands = [call[0] for call in _logged_commands(log_path)]
    assert commands == [
        "window.new",
        "emulate.viewport",
        "js",
        "screenshot",
        "tab.close",
    ]


def test_surf_target_preflight_rejects_redirect_and_still_closes_tab(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_surf, log_path = _fake_surf(tmp_path)
    monkeypatch.setenv("FAKE_SURF_LOG", str(log_path))
    monkeypatch.setenv("FAKE_SURF_FINAL_URL", "https://captcha.example/challenge/text")
    monkeypatch.setattr("captcha_skill.preflight.surf_run_path", lambda: fake_surf)

    with pytest.raises(CaptchaSkillError) as raised:
        preflight_surf_target(
            _manifest(), screenshot_path=tmp_path / "surf-target-preflight.png"
        )

    assert raised.value.code is ErrorCode.TARGET_UNAVAILABLE
    commands = [call[0] for call in _logged_commands(log_path)]
    assert commands[-1] == "tab.close"
    assert "screenshot" not in commands


def test_surf_target_preflight_fails_when_cleanup_is_unproven(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_surf, log_path = _fake_surf(tmp_path)
    monkeypatch.setenv("FAKE_SURF_LOG", str(log_path))
    monkeypatch.setenv("FAKE_SURF_CLOSE_FAIL", "1")
    monkeypatch.setattr("captcha_skill.preflight.surf_run_path", lambda: fake_surf)

    with pytest.raises(CaptchaSkillError) as raised:
        preflight_surf_target(
            _manifest(), screenshot_path=tmp_path / "surf-target-preflight.png"
        )

    assert raised.value.code is ErrorCode.SURF_UNAVAILABLE
    assert _logged_commands(log_path)[-1][0] == "tab.close"
