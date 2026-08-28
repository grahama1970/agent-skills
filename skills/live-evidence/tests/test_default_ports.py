"""Default port/backend URL regressions."""

import inspect

from live_evidence import cli
from live_evidence.config import DEFAULT_BACKEND_URL, DEFAULT_PORT, AppSettings


def test_settings_default_to_live_evidence_port(monkeypatch) -> None:
    monkeypatch.delenv("LIVE_EVIDENCE_PORT", raising=False)
    settings = AppSettings.from_env()

    assert DEFAULT_PORT == 8799
    assert settings.port == 8799


def test_cli_backend_defaults_avoid_task_monitor_port() -> None:
    assert inspect.signature(cli.serve).parameters["port"].default == 8799
    for command in (cli.listen, cli.replay, cli.search, cli.status):
        assert inspect.signature(command).parameters["backend_url"].default == DEFAULT_BACKEND_URL
        assert "8765" not in inspect.signature(command).parameters["backend_url"].default
