from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "db_repair_session.py"
spec = importlib.util.spec_from_file_location("db_repair_session", SCRIPT)
db_repair_session = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules["db_repair_session"] = db_repair_session
spec.loader.exec_module(db_repair_session)


def test_run_monitor_health_uses_streaming_heartbeat_artifacts(tmp_path: Path, monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    payload = {
        "checks": [
            {"dimension": "qra_coverage_per_control", "ok": False},
            {"dimension": "embedding_gaps", "ok": True},
        ]
    }

    def fake_stream(cmd, **kwargs):
        calls.append({"cmd": cmd, **kwargs})
        proc = subprocess.CompletedProcess(cmd, returncode=1, stdout=json.dumps(payload), stderr="")
        proc.heartbeat_path = str(tmp_path / "monitor_health_final_process.heartbeats.jsonl")  # type: ignore[attr-defined]
        proc.stdout_path = str(tmp_path / "monitor_health_final_process.stdout.txt")  # type: ignore[attr-defined]
        proc.stderr_path = str(tmp_path / "monitor_health_final_process.stderr.txt")  # type: ignore[attr-defined]
        proc.heartbeat_count = 2  # type: ignore[attr-defined]
        proc.timed_out = False  # type: ignore[attr-defined]
        return proc

    monkeypatch.setenv("DEWEY_MONITOR_HEALTH_TIMEOUT_S", "1234")
    monkeypatch.setattr(db_repair_session, "_run_streaming_with_heartbeats", fake_stream)
    monkeypatch.setattr(
        db_repair_session,
        "_run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("_run must not be used")),
    )

    result = db_repair_session.run_monitor_health(tmp_path, "final")

    assert calls
    assert calls[0]["artifact_dir"] == tmp_path
    assert calls[0]["output_stem"] == "monitor_health_final_process"
    assert calls[0]["timeout_s"] == 1234
    assert "health" in calls[0]["cmd"]
    assert result["path"] == str(tmp_path / "monitor_health_final.json")
    assert result["passed"] == 1
    assert result["total"] == 2
    assert json.loads((tmp_path / "monitor_health_final.json").read_text(encoding="utf-8")) == payload


def test_run_backup_uses_streaming_heartbeat_artifacts(tmp_path: Path, monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    backup_dir = tmp_path / "backups" / "20260625-010203"
    backup_dir.mkdir(parents=True)
    (backup_dir / "dump.json").write_text("{}", encoding="utf-8")

    def fake_stream(cmd, **kwargs):
        calls.append({"cmd": cmd, **kwargs})
        proc = subprocess.CompletedProcess(cmd, returncode=0, stdout="backup ok\n", stderr="")
        proc.heartbeat_path = str(tmp_path / "session" / "arango_backup_process.heartbeats.jsonl")  # type: ignore[attr-defined]
        proc.stdout_path = str(tmp_path / "session" / "arango_backup_process.stdout.txt")  # type: ignore[attr-defined]
        proc.stderr_path = str(tmp_path / "session" / "arango_backup_process.stderr.txt")  # type: ignore[attr-defined]
        proc.heartbeat_count = 3  # type: ignore[attr-defined]
        proc.timed_out = False  # type: ignore[attr-defined]
        return proc

    monkeypatch.setenv("DEWEY_ARANGO_BACKUP_TIMEOUT_S", "5678")
    monkeypatch.setattr(db_repair_session, "BACKUP_BASE", tmp_path / "backups")
    monkeypatch.setattr(db_repair_session, "_run_streaming_with_heartbeats", fake_stream)
    monkeypatch.setattr(db_repair_session, "_collection_count", lambda collection: 12491)

    result = db_repair_session.run_backup(tmp_path / "session")

    assert calls
    assert calls[0]["artifact_dir"] == tmp_path / "session"
    assert calls[0]["output_stem"] == "arango_backup_process"
    assert calls[0]["timeout_s"] == 5678
    assert result["backup_dir"] == str(backup_dir)
    assert result["backup_process"]["heartbeat_count"] == 3
    assert result["backup_process"]["timeout_s"] == 5678
    assert result["backup_process"]["timed_out"] is False
