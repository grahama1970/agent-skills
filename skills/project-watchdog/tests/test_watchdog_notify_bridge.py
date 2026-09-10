from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def load_bridge():
    path = Path(__file__).resolve().parents[1] / "scripts" / "watchdog_notify_bridge.py"
    spec = importlib.util.spec_from_file_location("watchdog_notify_bridge", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    import sys
    sys.modules[spec.name] = module  # required for `from __future__ import annotations` resolution
    spec.loader.exec_module(module)
    return module


def test_machine_actionable_needs_attention_does_not_page_human():
    bridge = load_bridge()
    ev = {
        "status": "NEEDS_ATTENTION",
        "requires_human_input": False,
        "next_steps": ["skills/project-watchdog/run.sh recover"],
    }
    assert bridge.requires_human_push(ev) is False
    assert bridge.push_webhook(ev)["reason"] == "not_human_only_blocker"
    assert bridge.switchboard_delivery_decision(ev, fresh=True) is None


def test_machine_actionable_needs_attention_without_next_step_does_not_page_human():
    bridge = load_bridge()
    assert bridge.requires_human_push({"status": "NEEDS_ATTENTION", "requires_human_input": False}) is False


def test_machine_actionable_switchboard_push_is_not_high_alert():
    bridge = load_bridge()
    payload = bridge.switchboard_payload({
        "status": "NEEDS_ATTENTION",
        "requires_human_input": False,
        "repo": "grahama1970/agent-skills",
        "issue": "1640",
        "next_steps": ["recover --apply"],
        "dir": "receipt-dir",
    })
    assert payload["type"] == "info"
    assert payload["priority"] == "normal"
    assert payload["owning_next_action"] == "recover --apply"


def test_human_needed_pages_but_completed_receipts_do_not_page():
    bridge = load_bridge()
    assert bridge.requires_human_push({"status": "NEEDS_ATTENTION", "requires_human_input": True}) is True
    assert bridge.requires_human_push({"status": "COMPLETED", "requires_human_input": False}) is False


def test_summarize_uses_handled_issue_human_flag(tmp_path, monkeypatch):
    bridge = load_bridge()
    monkeypatch.setattr(bridge, "RECEIPTS", tmp_path)
    receipt_dir = tmp_path / "project-watchdog-test"
    receipt_dir.mkdir()
    (receipt_dir / "receipt.json").write_text(json.dumps({
        "run_id": "project-watchdog-test",
        "status": "NEEDS_ATTENTION",
        "requires_human_input": False,
        "handled_issues": [{
            "repo": "grahama1970/agent-skills",
            "issue_number": 1641,
            "action": "ticket_repair",
            "requires_human_input": True,
            "summary": "operator approval required",
        }],
    }))

    ev = bridge.summarize(receipt_dir)

    assert ev["requires_human_input"] is True
    assert bridge.switchboard_payload(ev)["type"] == "alert"


def test_summarize_unsettled_running_operation_names_issue_and_recovery(tmp_path, monkeypatch):
    bridge = load_bridge()
    monkeypatch.setattr(bridge, "RECEIPTS", tmp_path)
    receipt_dir = tmp_path / "project-watchdog-test"
    receipt_dir.mkdir()
    (receipt_dir / "receipt.json").write_text(json.dumps({
        "status": "NEEDS_ATTENTION",
        "stop_reason": "unsettled_execution_or_scan_failure",
        "requires_human_input": False,
        "primary_observations": [
            {
                "writer_active": False,
                "recovery_command": "recover tau --apply",
                "operations": [{"repo": "grahama1970/tau", "issue_number": 343}],
            },
            {
                "writer_active": True,
                "recovery_command": "recover --apply",
                "operations": [{
                    "repo": "grahama1970/agent-skills",
                    "issue_number": 1628,
                    "action": "ticket_repair",
                }],
            },
        ],
    }))

    ev = bridge.summarize(receipt_dir)

    assert ev["repo"] == "grahama1970/agent-skills"
    assert ev["issue"] == "1628"
    assert ev["action"] == "ticket_repair"
    assert ev["next_steps"] == ["recover --apply"]
    assert bridge.switchboard_delivery_decision(ev, fresh=True) is None


def test_switchboard_push_dedupes_same_fingerprint_across_receipts(tmp_path, monkeypatch):
    """2026-09-10 spam: identical (repo,issue,status,triage) from a NEW receipt
    every 5 minutes must not push to Switchboard more than once per window."""
    import time as _time
    bridge = load_bridge()
    monkeypatch.setattr(bridge, "RECEIPTS", tmp_path)
    monkeypatch.setattr(bridge, "SWITCHBOARD_DEDUP", tmp_path / "notify-bridge-dedup.json")
    checkpoint = bridge.BridgeCheckpoint()
    sent: list[dict] = []

    def fake_push(ev):
        sent.append(ev)
        return {"status": "SENT"}

    monkeypatch.setattr(bridge, "push_switchboard", fake_push)
    monkeypatch.setattr(bridge, "_write_agent_action_receipt", lambda *a, **k: None)
    base = {"event_id": "e1", "dir": "d1", "status": "NEEDS_ATTENTION", "repo": "grahama1970/tau",
            "issue": "343", "triage_code": "project_watchdog_target_ownership_conflict",
            "run_id": "r1", "node": "n", "attempt": "1", "phase": "p",
            "source_time": "t", "observed_at": "t", "receipt": "x",
            "identity": {"repo": "grahama1970/tau", "issue_number": 343}}
    first = bridge.deliver(dict(base), checkpoint, fresh=True)
    assert first["switchboard"]["status"] == "SENT" and len(sent) == 1
    replay = dict(base, event_id="e2", dir="d2")  # next tick, new receipt id
    second = bridge.deliver(replay, checkpoint, fresh=True)
    assert second["switchboard"]["status"] == "DEDUPED" and len(sent) == 1
    real_time = _time.time
    monkeypatch.setattr(_time, "time", lambda: real_time() + 90000)
    later = bridge.deliver(dict(base, event_id="e3", dir="d3"), checkpoint, fresh=True)
    assert later["switchboard"]["status"] == "SENT" and len(sent) == 2
