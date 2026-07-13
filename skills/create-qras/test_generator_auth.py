from __future__ import annotations

from pathlib import Path

import pytest

import generator


SCILLM_KEY_NAMES = (
    "SCILLM_API_KEY",
    "SCILLM_MASTER_KEY",
    "LITELLM_MASTER_KEY",
    "SCILLM_PROXY_KEY",
)


def _clear_scillm_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for key_name in SCILLM_KEY_NAMES:
        monkeypatch.delenv(key_name, raising=False)


def test_scillm_api_key_reads_master_key_from_configured_env_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _clear_scillm_keys(monkeypatch)
    env_path = tmp_path / ".env"
    env_path.write_text("SCILLM_MASTER_KEY='file-master-key'\n")
    monkeypatch.setenv("SCILLM_ENV", str(env_path))

    assert generator._scillm_api_key() == "file-master-key"


def test_scillm_api_key_honors_explicit_api_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _clear_scillm_keys(monkeypatch)
    env_path = tmp_path / ".env"
    env_path.write_text("SCILLM_MASTER_KEY=file-master-key\n")
    monkeypatch.setenv("SCILLM_ENV", str(env_path))
    monkeypatch.setenv("SCILLM_API_KEY", "explicit-api-key")

    assert generator._scillm_api_key() == "explicit-api-key"


def test_scillm_api_key_fails_closed_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _clear_scillm_keys(monkeypatch)
    monkeypatch.setenv("SCILLM_ENV", str(tmp_path / "missing.env"))

    with pytest.raises(RuntimeError, match="SciLLM credential unavailable"):
        generator._scillm_api_key()
