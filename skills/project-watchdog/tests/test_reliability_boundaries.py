"""Focused regressions for project-watchdog reliability boundaries."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from watchdog import alerts  # noqa: E402


def _load_triage_classifier():
    path = Path(__file__).resolve().parents[2] / "triage-error" / "classifier.py"
    spec = importlib.util.spec_from_file_location("triage_error_classifier_regression", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_unknown_project_watchdog_error_mints_validator_safe_code() -> None:
    classifier = _load_triage_classifier()
    result = classifier.classify(
        "novel watchdog failure with no catalog token",
        layer="project-watchdog",
    )
    code = result["code"]
    assert code.startswith("project_watchdog_unclassified_")
    assert "-" not in code
    suffix = code.rsplit("_", 1)[-1]
    assert len(suffix) == 8
    assert all(ch in "0123456789abcdef" for ch in suffix)


def test_dry_run_alert_never_advances_dedupe_state(tmp_path: Path, monkeypatch) -> None:
    fake_runner = tmp_path / "ops-discord-run.sh"
    fake_runner.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(alerts, "OPS_DISCORD_RUN_SH", fake_runner)
    monkeypatch.setattr(alerts, "_alerts_state_path", lambda: tmp_path / "alerts.json")
    monkeypatch.delenv("OPS_DISCORD_WEBHOOK_WATCHDOG_URL", raising=False)

    proc = SimpleNamespace(
        returncode=0,
        stdout=json.dumps(
            {
                "schema": "ops_discord.notification_receipt.v1",
                "status": "DRY_RUN",
                "ok": True,
                "dry_run": True,
                "external_effects": False,
            }
        ),
        stderr="",
    )
    receipt = {
        "schema": "agent_skills.project_watchdog.tick_receipt.v1",
        "run_id": "dry-run-regression",
        "status": "BLOCKED",
        "ok": False,
        "apply": False,
        "handled_issues": [],
        "errors": [],
    }

    with mock.patch.object(subprocess, "run", return_value=proc):
        alerts.maybe_alert(receipt)

    assert receipt["alert"]["status"] == "DRY_RUN"
    assert receipt["alert"]["delivered"] is False
    assert not (tmp_path / "alerts.json").exists()


def test_unverified_sent_alert_does_not_advance_dedupe_state(tmp_path: Path, monkeypatch) -> None:
    fake_runner = tmp_path / "ops-discord-run.sh"
    fake_runner.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(alerts, "OPS_DISCORD_RUN_SH", fake_runner)
    monkeypatch.setattr(alerts, "_alerts_state_path", lambda: tmp_path / "alerts.json")
    monkeypatch.setenv("OPS_DISCORD_WEBHOOK_WATCHDOG_URL", "https://example.invalid/webhook")

    proc = SimpleNamespace(
        returncode=0,
        stdout=json.dumps(
            {
                "schema": "ops_discord.notification_receipt.v1",
                "status": "SENT",
                "dry_run": False,
                "external_effects": True,
            }
        ),
        stderr="",
    )
    receipt = {
        "schema": "agent_skills.project_watchdog.tick_receipt.v1",
        "run_id": "unverified-send-regression",
        "status": "BLOCKED",
        "ok": False,
        "apply": True,
        "handled_issues": [],
        "errors": [],
    }

    with mock.patch.object(subprocess, "run", return_value=proc):
        alerts.maybe_alert(receipt)

    assert receipt["alert"]["status"] == "ACCEPTED_UNVERIFIED"
    assert receipt["alert"]["delivered"] is False
    assert not (tmp_path / "alerts.json").exists()


def test_message_receipt_is_the_only_state_that_advances_dedupe(tmp_path: Path, monkeypatch) -> None:
    fake_runner = tmp_path / "ops-discord-run.sh"
    fake_runner.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(alerts, "OPS_DISCORD_RUN_SH", fake_runner)
    monkeypatch.setattr(alerts, "_alerts_state_path", lambda: tmp_path / "alerts.json")
    monkeypatch.delenv("OPS_DISCORD_WEBHOOK_WATCHDOG_URL", raising=False)

    proc = SimpleNamespace(
        returncode=0,
        stdout=json.dumps(
            {
                "schema": "ops_discord.notification_receipt.v1",
                "status": "SENT",
                "ok": True,
                "message_id": "123",
                "message_url": "https://discord.com/channels/1/2/123",
                "dry_run": False,
                "external_effects": True,
            }
        ),
        stderr="",
    )
    receipt = {
        "schema": "agent_skills.project_watchdog.tick_receipt.v1",
        "run_id": "verified-send-regression",
        "status": "BLOCKED",
        "ok": False,
        "apply": True,
        "handled_issues": [],
        "errors": [],
    }

    with mock.patch.object(subprocess, "run", return_value=proc):
        alerts.maybe_alert(receipt)

    assert receipt["alert"]["status"] == "SENT"
    assert receipt["alert"]["delivered"] is True
    state = json.loads((tmp_path / "alerts.json").read_text(encoding="utf-8"))
    assert receipt["alert"]["fingerprint"] in state
