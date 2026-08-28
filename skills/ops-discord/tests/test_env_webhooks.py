#!/usr/bin/env python3
"""Regression tests for environment-backed webhook configuration."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parent.parent


def test_load_webhooks_discovers_supported_env_names(monkeypatch, tmp_path: Path) -> None:
    sys.path.insert(0, str(SKILL_DIR))
    from discord_ops import utils

    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"webhooks": {"file": "http://localhost/file"}}))
    monkeypatch.setattr(utils, "CONFIG_FILE", config_file)
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/TSECRET/BSECRET/CSECRET")
    monkeypatch.setenv(
        "OPS_DISCORD_WEBHOOK_ALERTS_URL",
        "https://discord.com/api/webhooks/1234567890/secret-token",
    )

    webhooks = utils.load_webhooks()
    sources = utils.webhook_sources()

    assert webhooks["file"] == "http://localhost/file"
    assert webhooks["slack"].startswith("https://hooks.slack.com/services/")
    assert webhooks["alerts"].startswith("https://discord.com/api/webhooks/")
    assert sources["file"] == "config"
    assert sources["slack"] == "env:SLACK_WEBHOOK_URL"
    assert sources["alerts"] == "env:OPS_DISCORD_WEBHOOK_ALERTS_URL"


def test_load_webhooks_discovers_supported_zshrc_exports(monkeypatch, tmp_path: Path) -> None:
    sys.path.insert(0, str(SKILL_DIR))
    from discord_ops import utils

    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"webhooks": {}}))
    zshrc = tmp_path / ".zshrc"
    zshrc.write_text(
        "export SLACK_WEBHOOK_URL='https://hooks.slack.com/services/TZSH/BZSH/CZSH'\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(utils, "CONFIG_FILE", config_file)
    monkeypatch.setenv("OPS_DISCORD_ZSHRC", str(zshrc))
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)

    webhooks = utils.load_webhooks()
    sources = utils.webhook_sources()

    assert webhooks["slack"] == "https://hooks.slack.com/services/TZSH/BZSH/CZSH"
    assert sources["slack"] == "zshrc:SLACK_WEBHOOK_URL"


def test_webhook_list_redacts_env_url() -> None:
    env = os.environ.copy()
    env["SLACK_WEBHOOK_URL"] = "https://hooks.slack.com/services/TSECRET/BSECRET/CSECRET"
    proc = subprocess.run(
        ["uv", "run", "--project", ".", "python", "discord_ops.py", "webhook", "list"],
        cwd=SKILL_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined
    assert "slack" in combined
    assert "env:SLACK_WEBHOOK_URL" in combined
    assert "https://hooks.slack.com/<redacted>" in combined
    assert "TSECRET" not in combined
    assert "BSECRET" not in combined
    assert "CSECRET" not in combined


def test_notify_dry_run_resolves_env_webhook_without_sending() -> None:
    env = os.environ.copy()
    env["SLACK_WEBHOOK_URL"] = "https://hooks.slack.com/services/TSECRET/BSECRET/CSECRET"
    proc = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            ".",
            "python",
            "discord_ops.py",
            "notify",
            "--webhook",
            "slack",
            "--content",
            "monitor-opportunities self-repair regression smoke",
            "--dry-run",
            "--json",
        ],
        cwd=SKILL_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined
    payload = json.loads(proc.stdout)
    assert payload["status"] == "DRY_RUN"
    assert payload["webhook"] == "slack"
    assert payload["source"] == "env:SLACK_WEBHOOK_URL"
    assert payload["external_effects"] is False
    assert "TSECRET" not in combined
    assert "BSECRET" not in combined
    assert "CSECRET" not in combined


def test_describe_webhook_url_redacts_discord_token() -> None:
    sys.path.insert(0, str(SKILL_DIR))
    from discord_ops.utils import describe_webhook_url

    assert (
        describe_webhook_url("https://discord.com/api/webhooks/1234567890/secret-token")
        == "https://discord.com/api/webhooks/<redacted>"
    )
