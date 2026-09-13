from __future__ import annotations

import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from watchdog import commands, config  # noqa: E402


def _fake_finish(run_id: str, receipt_dir: Path, receipt: dict, code: int, *, persist=None) -> int:
    if persist:
        receipt_dir.mkdir(parents=True, exist_ok=True)
        receipt["receipt_path"] = str(receipt_dir / "receipt.json")
        (receipt_dir / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    return code


def test_quiet_owner_finalizes_without_dispatch(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(config, "receipt_root", lambda: tmp_path)
    monkeypatch.setattr(config, "tick_would_enter_quiet_hours", lambda: True)
    monkeypatch.setattr(config, "quiet_window", lambda: (2, 6))
    monkeypatch.setattr(commands, "acquire_lock", lambda run_id: calls.append("acquire") or True)
    monkeypatch.setattr(commands, "release_lock", lambda: calls.append("release"))
    monkeypatch.setattr(commands, "_test_hold_lock_if_requested", lambda run_id: None)
    monkeypatch.setattr(commands, "_tick_locked", lambda *a, **k: (_ for _ in ()).throw(AssertionError("repair dispatched during quiet hours")))
    monkeypatch.setattr(commands, "_deliver_tick_notifications", lambda run_id, receipt_dir: calls.append("deliver") or {"status": "IDLE"})
    monkeypatch.setattr(commands, "_publish_ui_snapshot", lambda run_id, receipt_dir: calls.append("ui") or {"status": "OK"})
    monkeypatch.setattr(commands, "finish", _fake_finish)
    monkeypatch.setattr(commands, "log_event", lambda *a, **k: None)

    assert commands.tick(apply=True, project_id="all", max_tickets=3) == 0
    assert calls == ["acquire", "deliver", "ui", "release"]
    receipts = list(tmp_path.glob("*/receipt.json"))
    assert len(receipts) == 1
    assert json.loads(receipts[0].read_text())["stop_reason"] == "quiet_hours"


def test_finalization_fault_preserves_receipt_and_records_degradation(tmp_path: Path, monkeypatch) -> None:
    receipt_dir = tmp_path / "run"
    receipt_dir.mkdir()
    receipt_path = receipt_dir / "receipt.json"
    receipt_path.write_text(json.dumps({"run_id": "run", "status": "COMPLETED", "ok": True}), encoding="utf-8")
    before = receipt_path.read_bytes()

    bridge = types.SimpleNamespace(deliver_due=lambda current=None: (_ for _ in ()).throw(RuntimeError("bridge down")))
    monkeypatch.setitem(sys.modules, "watchdog_notify_bridge", bridge)
    monkeypatch.setattr(commands, "log_event", lambda *a, **k: None)

    result = commands._deliver_tick_notifications("run", receipt_dir)

    assert result["status"] == "DELIVERY_FAILED"
    assert receipt_path.read_bytes() == before
    delivery = json.loads((receipt_dir / "notification-delivery.json").read_text())
    assert delivery["source_receipt_sha256"]
    assert delivery["notification_delivery"]["status"] == "DELIVERY_FAILED"


def test_quiet_delivery_replays_pending_without_delivering_current_receipt(tmp_path: Path, monkeypatch) -> None:
    receipt_dir = tmp_path / "quiet"
    receipt_dir.mkdir()
    (receipt_dir / "receipt.json").write_text(json.dumps({"stop_reason": "quiet_hours"}), encoding="utf-8")
    seen: list[Path | None] = []

    bridge = types.SimpleNamespace(deliver_due=lambda current=None: seen.append(current) or {"status": "IDLE"})
    monkeypatch.setitem(sys.modules, "watchdog_notify_bridge", bridge)
    monkeypatch.setattr(commands, "log_event", lambda *a, **k: None)

    before = (receipt_dir / "receipt.json").read_bytes()
    result = commands._deliver_tick_notifications("run", receipt_dir)
    assert result["status"] == "IDLE"
    assert seen == [None]
    assert (receipt_dir / "receipt.json").read_bytes() == before
    delivery = json.loads((receipt_dir / "notification-delivery.json").read_text())
    assert delivery["notification_delivery"]["status"] == "IDLE"
    assert delivery["source_receipt_path"].endswith("receipt.json")


def test_ui_publication_failure_has_durable_source_bound_outcome(tmp_path: Path, monkeypatch) -> None:
    receipt_dir = tmp_path / "run"
    receipt_dir.mkdir()
    receipt_path = receipt_dir / "receipt.json"
    receipt_path.write_text(json.dumps({"run_id": "run", "status": "COMPLETED", "ok": True}), encoding="utf-8")
    snapshot = tmp_path / "ui" / "dist" / "project-watchdog-snapshot.json"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_text('{"previous": true}\n', encoding="utf-8")
    old = 1000
    __import__("os").utime(snapshot, (old, old))
    source_sha = "sha256:" + __import__("hashlib").sha256(receipt_path.read_bytes()).hexdigest()

    monkeypatch.setattr(config, "SKILL_DIR", tmp_path)
    monkeypatch.setattr(commands, "ui_payload", lambda receipt_limit=100: {"new": True})
    real_replace = commands.os.replace
    def fail_snapshot_only(src, dst):
        if Path(dst) == snapshot:
            raise OSError("replace denied")
        return real_replace(src, dst)
    monkeypatch.setattr(commands.os, "replace", fail_snapshot_only)
    monkeypatch.setattr(commands, "log_event", lambda *a, **k: None)

    result = commands._publish_ui_snapshot("run", receipt_dir)

    assert result["status"] == "UI_SNAPSHOT_FAILED"
    assert snapshot.read_text(encoding="utf-8") == '{"previous": true}\n'
    sidecar = json.loads((receipt_dir / "ui-publication.json").read_text())
    assert sidecar["source_receipt_sha256"] == source_sha
    assert sidecar["ui_publication"]["previous_snapshot_sha256"]
    assert sidecar["ui_publication"]["previous_snapshot_age_s"] >= 0


def test_native_singleton_excludes_second_process_through_all_phases(tmp_path: Path) -> None:
    import os
    import subprocess
    import textwrap
    import time

    env = {**os.environ, "PROJECT_WATCHDOG_STATE_ROOT": str(tmp_path)}
    scripts = str(ROOT / "scripts")
    owner_ready = tmp_path / "owner-ready"
    owner = subprocess.Popen([
        sys.executable,
        "-c",
        textwrap.dedent(f"""
            import pathlib, sys, time
            sys.path.insert(0, {scripts!r})
            from watchdog import core
            assert core.acquire_lock('owner') is True
            pathlib.Path({str(owner_ready)!r}).write_text('ready')
            time.sleep(1.5)
            core.release_lock()
        """),
    ], env=env)
    try:
        for _ in range(50):
            if owner_ready.exists():
                break
            time.sleep(0.05)
        assert owner_ready.exists()
        blocked = subprocess.run([
            sys.executable,
            "-c",
            textwrap.dedent(f"""
                import sys
                sys.path.insert(0, {scripts!r})
                from watchdog import core
                print(core.acquire_lock('second'))
            """),
        ], env=env, capture_output=True, text=True, check=False)
        assert blocked.stdout.strip() == "False"
    finally:
        owner.wait(timeout=5)
    acquired = subprocess.run([
        sys.executable,
        "-c",
        textwrap.dedent(f"""
            import sys
            sys.path.insert(0, {scripts!r})
            from watchdog import core
            print(core.acquire_lock('third'))
            core.release_lock()
        """),
    ], env=env, capture_output=True, text=True, check=False)
    assert acquired.stdout.strip() == "True"
