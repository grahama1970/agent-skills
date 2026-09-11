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


def test_switchboard_routes_to_the_events_own_project_inbox():
    bridge = load_bridge()
    # Each project's alert lands in that project's inbox, not a shared one.
    assert bridge.pi_inbox_for({"repo": "grahama1970/tau"}) == "tau"
    assert bridge.pi_inbox_for({"repo": "grahama1970/chatgpt-lab"}) == "chatgpt-lab"
    assert bridge.pi_inbox_for({"repo": "grahama1970/agent-skills"}) == "agent-skills"
    # A tau alert never addresses the agent-skills inbox that monitor-opp drains.
    assert bridge.switchboard_payload({
        "status": "NEEDS_ATTENTION", "repo": "grahama1970/tau", "issue": "343",
        "dir": "receipt-dir",
    })["to"] == "tau"
    # Unknown/malformed repo falls back to the operator inbox, never dropped.
    assert bridge.pi_inbox_for({"repo": "UNKNOWN(repo:receipt_missing_repo)"}) == bridge.PI_AGENT_INBOX
    assert bridge.pi_inbox_for({}) == bridge.PI_AGENT_INBOX


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


def test_non_ticket_receipts_do_not_push_unknown_alerts():
    """#1648: install/state/fleet-scan receipts have no repo/issue and were
    rendered as UNKNOWN(repo:receipt_missing_repo) NEEDS_ATTENTION pushes."""
    bridge = load_bridge()
    install = {"status": "NEEDS_ATTENTION",
               "repo": "UNKNOWN(repo:receipt_missing_repo)",
               "issue": "UNKNOWN(issue:receipt_missing_issue_number)"}
    assert bridge.requires_agent_push(install) is False
    real = {"status": "NEEDS_ATTENTION", "repo": "grahama1970/tau", "issue": "343"}
    assert bridge.requires_agent_push(real) is True
    malformed = {"status": "NEEDS_ATTENTION", "repo": "UNKNOWN(repo:receipt_missing_repo)", "issue": "343"}
    assert bridge.requires_agent_push(malformed) is True


def test_non_ticket_lifecycle_subject_is_human_readable():
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
    import watchdog_notify_bridge as b
    install_ev = {"run_id": "project-watchdog-install-X", "status": "DRY_RUN",
                  "repo": "UNKNOWN(repo:receipt_missing_repo)",
                  "issue": "UNKNOWN(issue:receipt_missing_issue_number)"}
    state_ev = {"run_id": "project-watchdog-state-Y", "status": "UPDATED",
                "repo": "UNKNOWN(repo:receipt_missing_repo)",
                "issue": "UNKNOWN(issue:receipt_missing_issue_number)"}
    ticket_ev = {"run_id": "r", "status": "NEEDS_ATTENTION", "repo": "grahama1970/tau", "issue": "350"}
    assert b._subject_target(install_ev) == "lifecycle:cron-install (no ticket)"
    assert b._subject_target(state_ev) == "lifecycle:runtime-state-change (no ticket)"
    assert "UNKNOWN(" not in b._subject_target(install_ev)
    assert b._subject_target(ticket_ev) == "grahama1970/tau#350"


def test_dead_run_reports_terminal_status_not_stale_progress(tmp_path, monkeypatch):
    """A finished run (process_running=False) with an old monitor must report its
    terminal status, not STALE_PROGRESS forever (the #1500 post-outage flood)."""
    import json, time, sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
    import watchdog_notify_bridge as b
    run = tmp_path / "project-watchdog-X"; run.mkdir()
    mon = run / "tau-stream-monitor.json"
    mon.write_text(json.dumps({"process_running": False, "current_status": "BLOCKED",
                               "latest_event": {}, "elapsed_seconds": 1}))
    old = time.time() - 4000
    os_utime = __import__("os").utime; os_utime(mon, (old, old))  # make it stale
    monkeypatch.setattr(b, "RECEIPTS", tmp_path)
    hb = b._heartbeat_payload()
    # Superseded contract (2026-09-11): a terminal dead run does not drive the
    # fleet heartbeat AT ALL (not STALE_PROGRESS, not a forever-BLOCKED latch).
    assert hb["state"] == "observer_fresh_no_active_run", hb
    # a live-but-stalled run still flags STALE_PROGRESS
    mon.write_text(json.dumps({"process_running": True, "current_status": "RUNNING",
                               "latest_event": {}, "elapsed_seconds": 1}))
    os_utime(mon, (old, old))
    assert b._heartbeat_payload()["state"] == "STALE_PROGRESS"


def test_heartbeat_skips_terminal_runs_and_latches_nothing_forever(tmp_path, monkeypatch):
    """A terminal (dead) monitor must not be the fleet heartbeat forever; only
    in-flight runs qualify, else observer_fresh_no_active_run (the #1500 case)."""
    import json, time, sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
    import watchdog_notify_bridge as b
    run = tmp_path / "watchdog-run"; run.mkdir()
    mon = run / "tau-stream-monitor.json"
    mon.write_text(json.dumps({"process_running": False, "current_status": "BLOCKED",
                               "latest_event": {}, "elapsed_seconds": 1}))
    old = time.time() - 4000; os_utime = __import__("os").utime; os_utime(mon, (old, old))
    monkeypatch.setattr(b, "RECEIPTS", tmp_path)
    assert b._heartbeat_payload()["state"] == "observer_fresh_no_active_run"
    # an in-flight stale run still flags STALE_PROGRESS
    mon.write_text(json.dumps({"process_running": True, "current_status": "RUNNING",
                               "latest_event": {}, "elapsed_seconds": 1}))
    os_utime(mon, (old, old))
    assert b._heartbeat_payload()["state"] == "STALE_PROGRESS"
