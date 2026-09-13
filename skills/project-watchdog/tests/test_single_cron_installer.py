from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from watchdog import commands, config  # noqa: E402


def test_install_cron_refuses_read_failure_without_write(tmp_path: Path, monkeypatch) -> None:
    writes: list[str] = []
    captured: dict = {}

    def fake_run(cmd, input_text=None, timeout_s=None):
        if cmd == ["crontab", "-l"]:
            return {"exit_code": 1, "stdout": "", "stderr": "permission denied"}
        if cmd == ["crontab", "-"]:
            writes.append(input_text or "")
            return {"exit_code": 0, "stdout": "", "stderr": ""}
        return {"exit_code": 0, "stdout": "", "stderr": ""}

    monkeypatch.setattr(commands, "run_cmd", fake_run)
    monkeypatch.setattr(config, "receipt_root", lambda: tmp_path)
    monkeypatch.setattr(commands, "finish", lambda run_id, d, receipt, code, **k: captured.update(receipt=receipt, code=code) or code)

    assert commands.install_cron(apply=True, minute="*/5") == 1
    assert writes == []
    assert captured["receipt"]["reason"] == "crontab_read_failed"


def test_install_cron_consolidates_owned_jobs_and_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    unrelated = "MAILTO=ops@example.com\n0 3 * * * /bin/true # unrelated\n"
    legacy = (
        "*/5 * * * * old tick # project-watchdog global issue cron\n"
        "*/5 * * * * old notify project-watchdog-notify-bridge\n"
        "*/5 * * * * old ui project-watchdog-ui-snapshot\n"
        "15 4 * * * echo project-watchdog archival note # unrelated\n"
    )
    crontab = {"text": unrelated + legacy}
    captured: dict = {}

    def fake_run(cmd, input_text=None, timeout_s=None):
        if cmd == ["crontab", "-l"]:
            return {"exit_code": 0, "stdout": crontab["text"], "stderr": ""}
        if cmd == ["crontab", "-"]:
            crontab["text"] = input_text or ""
            return {"exit_code": 0, "stdout": "", "stderr": ""}
        return {"exit_code": 0, "stdout": "", "stderr": ""}

    monkeypatch.setattr(commands, "run_cmd", fake_run)
    monkeypatch.setattr(config, "receipt_root", lambda: tmp_path)
    monkeypatch.setattr(config, "cron_log_path", lambda: tmp_path / "cron.log")
    monkeypatch.setattr(commands, "finish", lambda run_id, d, receipt, code, **k: captured.update(receipt=receipt, code=code) or code)

    assert commands.install_cron(apply=True, minute="*/5") == 0
    once = crontab["text"]
    assert "MAILTO=ops@example.com" in once
    assert "# unrelated" in once
    assert "echo project-watchdog archival note" in once
    assert [line for line in once.splitlines() if commands._owned_project_watchdog_cron_line(line)] == [captured["receipt"]["cron_line"]]
    assert "--max-tickets 3" in once
    assert commands.install_cron(apply=True, minute="*/5") == 0
    assert crontab["text"] == once
    assert captured["receipt"]["ok"] is True
