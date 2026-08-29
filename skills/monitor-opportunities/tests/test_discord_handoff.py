"""Morning Discord handoff guards."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

import monitor_opportunities.cli as cli
from monitor_opportunities.cli import app
from monitor_opportunities.discord_handoff import (
    build_morning_discord_message,
    send_morning_discord_handoff,
)

runner = CliRunner()


def _write_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True)
    (run_dir / "nightly-receipt.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "mode": "DIAGNOSTIC",
                "steps": {
                    "browser_capture_linkedin": {
                        "top_applicant_count": 7,
                        "easy_apply_count": 1,
                        "captured": 7,
                    },
                    "memory_sync": {
                        "exit_code": 0,
                        "readback_found": True,
                        "relationship_readback_found": True,
                    },
                    "suggested_contacts": {"suggestions": 8, "mandate_relevant": 66},
                },
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "morning-digest.json").write_text(
        json.dumps(
            {
                "counts": {"employment": 7, "consulting": 3, "total": 10},
                "top": [
                    {
                        "candidate_id": "candidate:a:moog",
                        "organization": "Moog",
                        "title": "AI Program Manager",
                        "opportunity_type": "employment",
                        "response_score": 0.6128,
                        "inmail_target": {"name": "George Small"},
                        "action": {
                            "apply_on_site": "https://moog.example/jobs/AI-Program-Manager"
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_morning_discord_message_has_counts_top_rows_and_authorization_boundary(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_run(run_dir)

    payload = build_morning_discord_message(run_dir, report_url="file:///tmp/report.html")

    assert payload["schema"] == "monitor_opportunities.morning_discord_handoff.v1"
    assert payload["counts"] == {"employment": 7, "consulting": 3, "total": 10}
    assert payload["linkedin"] == {
        "top_applicant_count": 7,
        "easy_apply_count": 1,
        "captured": 7,
    }
    assert "Moog - AI Program Manager" in payload["content"]
    assert "contact=George Small" in payload["content"]
    assert "Easy Apply is a signal, not automatic submit" in payload["content"]


def test_morning_discord_send_uses_ops_discord_dry_run(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run"
    _write_run(run_dir)
    ops = tmp_path / "ops-discord" / "run.sh"
    ops.parent.mkdir()
    ops.write_text("#!/bin/sh\n", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=json.dumps(
                {
                    "schema": "ops_discord.notification_receipt.v1",
                    "status": "DRY_RUN",
                    "webhook": "discord",
                    "source": "env:DISCORD_WEBHOOK_URL",
                }
            ),
            stderr="",
        )

    monkeypatch.setattr("monitor_opportunities.discord_handoff.subprocess.run", fake_run)
    receipt = send_morning_discord_handoff(
        run_dir=run_dir,
        workdir=tmp_path,
        ops_discord_run=ops,
        out=run_dir / "discord-handoff" / "morning-discord-receipt.json",
        webhook="discord",
    )

    assert receipt["status"] == "PASS"
    assert receipt["dry_run"] is True
    assert receipt["external_effects"] is False
    assert "--dry-run" in captured["cmd"]
    assert captured["cmd"][:2] == [str(ops), "notify"]
    assert captured["cmd"][captured["cmd"].index("--webhook") + 1] == "discord"


def test_schedule_morning_discord_registers_8am_handoff(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    captured: dict[str, str] = {}

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if cmd[:3] == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="abc123\n", stderr="")
        if "register" in cmd:
            captured["cron"] = cmd[cmd.index("--cron") + 1]
            captured["command"] = cmd[cmd.index("--command") + 1]
            captured["workdir"] = cmd[cmd.index("--workdir") + 1]
            return subprocess.CompletedProcess(cmd, 0, stdout="Registered job: monitor-opportunities-morning-discord\n", stderr="")
        if cmd == [str(repo / "skills" / "scheduler" / "run.sh"), "list", "--json"]:
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=json.dumps(
                    {
                        "monitor-opportunities-morning-discord": {
                            "cron": captured["cron"],
                            "command": captured["command"],
                            "workdir": captured["workdir"],
                            "enabled": True,
                        }
                    }
                ),
                stderr="",
            )
        raise AssertionError(cmd)

    monkeypatch.setattr(cli, "_canonical_repo_root", lambda: repo)
    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    monkeypatch.setenv("SCHEDULER_DATA_DIR", str(tmp_path / "scheduler"))

    result = runner.invoke(app, ["schedule-morning-discord", "--dry-run"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "PASS"
    assert payload["cron"] == "0 8 * * *"
    assert payload["post"] is False
    assert "morning-discord" in payload["command"]
    assert "--post" not in payload["command"]
