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
    monkeypatch.setattr(commands, "_publish_ui_snapshot", lambda run_id: calls.append("ui") or {"status": "OK"})
    monkeypatch.setattr(commands, "finish", _fake_finish)
    monkeypatch.setattr(commands, "log_event", lambda *a, **k: None)

    assert commands.tick(apply=True, project_id="all", max_tickets=3) == 0
    assert calls == ["acquire", "deliver", "ui", "release"]
    receipts = list(tmp_path.glob("*/receipt.json"))
    assert len(receipts) == 1
    assert json.loads(receipts[0].read_text())["stop_reason"] == "quiet_hours"


def test_finalization_fault_preserves_receipt_and_records_degradation(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(config, "receipt_root", lambda: tmp_path)
    monkeypatch.setattr(config, "tick_would_enter_quiet_hours", lambda: True)
    monkeypatch.setattr(config, "quiet_window", lambda: (2, 6))
    monkeypatch.setattr(commands, "acquire_lock", lambda run_id: True)
    monkeypatch.setattr(commands, "release_lock", lambda: calls.append("release"))
    monkeypatch.setattr(commands, "_test_hold_lock_if_requested", lambda run_id: None)
    monkeypatch.setattr(commands, "_deliver_tick_notifications", lambda run_id, receipt_dir: (_ for _ in ()).throw(RuntimeError("bridge down")))
    monkeypatch.setattr(commands, "_publish_ui_snapshot", lambda run_id: (_ for _ in ()).throw(RuntimeError("ui down")))
    monkeypatch.setattr(commands, "finish", _fake_finish)
    monkeypatch.setattr(commands, "log_event", lambda *a, **k: None)

    assert commands.tick(apply=True, project_id="all", max_tickets=3) == 0
    assert calls == ["release"]
    receipts = list(tmp_path.glob("*/receipt.json"))
    assert len(receipts) == 1
    assert json.loads(receipts[0].read_text())["stop_reason"] == "quiet_hours"


def test_quiet_delivery_replays_pending_without_delivering_current_receipt(tmp_path: Path, monkeypatch) -> None:
    receipt_dir = tmp_path / "quiet"
    receipt_dir.mkdir()
    (receipt_dir / "receipt.json").write_text(json.dumps({"stop_reason": "quiet_hours"}), encoding="utf-8")
    seen: list[Path | None] = []

    bridge = types.SimpleNamespace(deliver_due=lambda current=None: seen.append(current) or {"status": "IDLE"})
    monkeypatch.setitem(sys.modules, "watchdog_notify_bridge", bridge)
    monkeypatch.setattr(commands, "log_event", lambda *a, **k: None)

    result = commands._deliver_tick_notifications("run", receipt_dir)
    assert result["status"] == "IDLE"
    assert seen == [None]
    saved = json.loads((receipt_dir / "receipt.json").read_text())
    assert saved["notification_delivery"]["status"] == "IDLE"
