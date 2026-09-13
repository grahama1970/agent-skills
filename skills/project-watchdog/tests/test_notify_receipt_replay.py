"""WebGPT review next-step 13: deterministic replay coverage for the notify bridge.

Duplicate/out-of-order receipts, stale heartbeats, terminal transitions, and
malformed non-ticket events must produce idempotent derived state and never
render None#None subjects or agent alerts for non-ticket lifecycle receipts.
"""
import importlib.util, json, sys, time
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1] / "scripts" / "watchdog_notify_bridge.py"
spec = importlib.util.spec_from_file_location("wd_bridge_replay", BRIDGE)
b = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = b
spec.loader.exec_module(b)


def test_malformed_receipts_never_render_none_subject():
    shapes = [
        {},  # fully empty receipt
        {"status": "NEEDS_ATTENTION"},  # no repo/issue/run_id
        {"repo": None, "issue": None, "status": "SKIPPED"},  # explicit None
        {"repo": "receipt_missing_repo", "issue": "receipt_missing_issue", "status": "BLOCKED"},
    ]
    for ev in shapes:
        s = b._subject_target(ev)
        assert "None" not in s, f"subject {s!r} rendered None for {ev}"


def test_terminal_transition_beats_replayed_progress(tmp_path, monkeypatch):
    # A COMPLETED ticket event must clear a prior alert fingerprint for the same
    # ticket instead of inheriting old progress/blocker state.
    monkeypatch.setattr(b, "SWITCHBOARD_DEDUP", tmp_path / "dedup.json")
    prior = json.dumps(["acme/api", "42", "STALE_PROGRESS", "stalled"], sort_keys=True)
    b.SWITCHBOARD_DEDUP.write_text(json.dumps({prior: time.time()}))
    done = {"repo": "acme/api", "issue": "42", "status": "COMPLETED", "triage_code": "resolved"}
    assert b._all_clear_fingerprint(done) == prior


def test_all_clear_requires_ticket_shape():
    for bad in [
        {"status": "COMPLETED"},  # no repo/issue
        {"repo": "", "issue": "", "status": "CLOSED_ON_GITHUB"},
        {"repo": "receipt_missing", "issue": "7", "status": "COMPLETED"},
        {"repo": "acme/api", "issue": "42", "status": "STALE_PROGRESS"},  # non-terminal
    ]:
        assert b._all_clear_fingerprint(bad) is None, f"cleared alert for non-ticket shape: {bad}"


def test_replayed_event_is_byte_identical_derivation():
    ev = {"repo": "acme/api", "issue": "42", "status": "NEEDS_ATTENTION",
          "triage": "t", "run_id": "r1", "requires_human_input": False}
    s1, s2 = b._subject_target(ev), b._subject_target(ev)
    assert s1 == s2 == "acme/api#42"  # duplicate replay derives identical subject


def test_wip_isolation_skips_busy_project_without_blocking_fleet():
    """WebGPT next-step 14: a non-active/busy project is skipped for dispatch
    while an active sibling candidate still proceeds in the same scan."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from watchdog import commands as m
    state = {"projects": {"busy-lane": {"state": "paused"}, "ready-lane": {"state": "active"}}}
    busy = {"project_id": "busy-lane"}
    ready = {"project_id": "ready-lane"}
    assert m._project_runtime_state(busy, state) != "active"
    assert m._project_runtime_state(ready, state) == "active"
    skipped = [p for p in (busy, ready) if m._project_runtime_state(p, state) != "active"]
    progressed = [p for p in (busy, ready) if m._project_runtime_state(p, state) == "active"]
    assert [p["project_id"] for p in skipped] == ["busy-lane"]
    assert [p["project_id"] for p in progressed] == ["ready-lane"]


def test_park_on_quota_carries_backlog_snapshot():
    """#1661: a quota park event records the deferred backlog; no lease burn."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from watchdog import transport_health as th
    th.parked_backlog_snapshot = lambda: {"routable_count": 25, "oldest_age_hours": 72.0,
                                          "issue_refs": ["agent-skills#1658"]}
    res = th.park_on_quota("codex", "rate limit exceeded; resets 2026-09-14T21:36:00Z")
    assert res["parked"] is True and res["code"] == th.QUOTA_CODE
    assert res["parked_backlog"]["routable_count"] == 25
    assert res["parked_backlog"]["issue_refs"] == ["agent-skills#1658"]
    assert th.park_on_quota("codex", "unrelated hard failure")["parked"] is False


def test_ticket_card_renders_plain_spoken_dry_run(monkeypatch):
    monkeypatch.setattr(b, "_issue_card", lambda repo, issue: {
        "title": "Share one terminal-status parser with the renderer",
        "target": "extensions/pi/lazy-report-shame-shame-shame",
        "current_state": "Checker can skip an invalid final status.",
        "requested_outcome": "A single terminal JSON control-frame selector.",
        "required_proof": "skills/agentic-evals/run.sh run skills/shame/fixtures/agentic_eval.json",
    })
    ev = {
        "repo": "grahama1970/agent-skills", "issue": 1620,
        "status": "DRY_RUN", "action": "ticket_repair", "summary": "would reserve primary/main",
        "dir": "project-watchdog-test", "apply": False,
        "ticket": b._issue_card("grahama1970/agent-skills", "1620"),
        "agents": "classifier=project-watchdog router; fixer=$ask tau-dag; reviewer=Tau reviewer",
    }
    out = b._fmt(ev)
    assert "ticket: Share one terminal-status parser with the renderer" in out
    assert "problem: Checker can skip an invalid final status." in out
    assert "dispatch: no work was started; this was a dry-run preview" in out
    assert "agents: classifier=project-watchdog router; fixer=$ask tau-dag; reviewer=Tau reviewer" in out


def test_human_blocker_message_names_required_action():
    ev = {"repo": "acme/api", "issue": 7, "status": "NEEDS_ATTENTION", "action": "ticket_repair",
          "summary": "operator approval required", "dir": "project-watchdog-test",
          "requires_human_input": True, "next_steps": ["approve canary queue then rerun watchdog eval"]}
    out = b._fmt(ev)
    assert "human needed: approve canary queue then rerun watchdog eval" in out


def test_restart_recovers_committed_unregistered_receipt(tmp_path, monkeypatch):
    bridge = b
    monkeypatch.setattr(bridge, "STATE_ROOT", tmp_path)
    monkeypatch.setattr(bridge, "RECEIPTS", tmp_path / "receipts")
    monkeypatch.setattr(bridge, "CURSOR", tmp_path / "notify-bridge-cursor.json")
    monkeypatch.setattr(bridge, "CHECKPOINTS", tmp_path / "notify-bridge-checkpoints.json")
    monkeypatch.setattr(bridge, "BRIDGE_LOCK", tmp_path / "notify-bridge.lock")
    monkeypatch.setattr(bridge, "SWITCHBOARD_DEDUP", tmp_path / "notify-bridge-dedup.json")
    monkeypatch.setattr(bridge, "push_switchboard", lambda ev, **k: {"status": "SENT", "message_id": "m1"})
    monkeypatch.setattr(bridge, "_write_agent_action_receipt", lambda *a, **k: None)
    bridge.RECEIPTS.mkdir(parents=True)
    old = bridge.RECEIPTS / "project-watchdog-old"
    old.mkdir()
    (old / "receipt.json").write_text(json.dumps({
        "run_id": "project-watchdog-old",
        "status": "NEEDS_ATTENTION",
        "handled_issues": [{
            "repo": "grahama1970/agent-skills",
            "issue_number": 99,
            "action": "ticket_repair",
            "status": "NEEDS_ATTENTION",
            "requires_human_input": False,
            "authorized_agent_next_steps": ["recover --apply"],
            "summary": "machine retry needed",
        }],
    }))
    bridge.CURSOR.write_text(json.dumps({"last_mtime": 0}))

    result = bridge.deliver_due()

    assert result["status"] == "DELIVERED"
    assert result["pushed"][0]["switchboard"]["status"] == "SENT"
    checkpoint = bridge._load_checkpoint()
    assert checkpoint.pending_dirs == []
    event_row = json.loads((tmp_path / "events.jsonl").read_text().splitlines()[0])
    assert event_row["issue"] == "99"
    assert event_row["phase"] == "ticket_repair"


def test_idle_tick_retries_human_alert_after_source_commit(tmp_path, monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from watchdog import alerts, core

    bridge = b
    monkeypatch.setattr(bridge, "STATE_ROOT", tmp_path)
    monkeypatch.setattr(bridge, "RECEIPTS", tmp_path / "receipts")
    monkeypatch.setattr(bridge, "CURSOR", tmp_path / "notify-bridge-cursor.json")
    monkeypatch.setattr(bridge, "CHECKPOINTS", tmp_path / "notify-bridge-checkpoints.json")
    monkeypatch.setattr(bridge, "BRIDGE_LOCK", tmp_path / "notify-bridge.lock")
    monkeypatch.setattr(bridge, "SWITCHBOARD_DEDUP", tmp_path / "notify-bridge-dedup.json")
    bridge.RECEIPTS.mkdir(parents=True)
    first_attempts: list[bool] = []

    def fake_alert(receipt):
        receipt_path = Path(receipt["receipt_path"])
        assert receipt_path.is_file(), "source receipt must be committed before human send"
        assert "alert" not in json.loads(receipt_path.read_text())
        first_attempts.append(True)
        receipt["alert"] = {"status": "ALERT_DELIVERY_FAILED", "delivered": False}

    monkeypatch.setattr(alerts, "maybe_alert", fake_alert)
    receipt_dir = bridge.RECEIPTS / "run-r6"
    receipt = core.base_receipt("run-r6", receipt_dir, True)
    receipt.update({
        "status": "NEEDS_ATTENTION", "ok": False,
        "handled_issues": [{"issue_number": 1, "repo": "acme/api", "status": "NEEDS_ATTENTION", "requires_human_input": True}],
    })

    assert core.finish("run-r6", receipt_dir, receipt, 1, persist=True) == 1
    source_bytes = (receipt_dir / "receipt.json").read_bytes()
    assert first_attempts == [True]
    assert json.loads((receipt_dir / "alert-delivery.json").read_text())["alert"]["status"] == "ALERT_DELIVERY_FAILED"

    agent_pushes: list[str] = []
    human_pushes: list[str] = []
    monkeypatch.setattr(bridge, "push_switchboard", lambda ev, **k: agent_pushes.append(ev["event_id"]) or {"status": "SENT", "message_id": "agent"})
    monkeypatch.setattr(bridge, "push_webhook", lambda ev, **k: human_pushes.append(ev["event_id"]) or {"status": "SENT", "message_id": "human"})
    monkeypatch.setattr(bridge, "_write_agent_action_receipt", lambda *a, **k: None)

    retried = bridge.deliver_due()
    assert retried["status"] == "DELIVERED"
    assert len(agent_pushes) == 1
    assert len(human_pushes) == 1
    assert (receipt_dir / "receipt.json").read_bytes() == source_bytes
    checkpoint = bridge._load_checkpoint()
    event_id = human_pushes[0]
    assert event_id in checkpoint.destinations["ops_discord"]["delivered_event_ids"]

    again = bridge.deliver_due()
    assert again["attempts"] == 0
    assert len(human_pushes) == 1


def test_drain_budget_and_acknowledgment_status(tmp_path, monkeypatch):
    bridge = b
    monkeypatch.setenv("PROJECT_WATCHDOG_NOTIFY_DRAIN_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("PROJECT_WATCHDOG_NOTIFY_DRAIN_MAX_SECONDS", "60")
    monkeypatch.setattr(bridge, "STATE_ROOT", tmp_path)
    monkeypatch.setattr(bridge, "RECEIPTS", tmp_path / "receipts")
    monkeypatch.setattr(bridge, "CURSOR", tmp_path / "notify-bridge-cursor.json")
    monkeypatch.setattr(bridge, "CHECKPOINTS", tmp_path / "notify-bridge-checkpoints.json")
    monkeypatch.setattr(bridge, "BRIDGE_LOCK", tmp_path / "notify-bridge.lock")
    monkeypatch.setattr(bridge, "SWITCHBOARD_DEDUP", tmp_path / "notify-bridge-dedup.json")
    sent: list[str] = []

    def fake_push(ev, **k):
        sent.append(ev["event_id"])
        return {"status": "AGENT_PUSH_FAILED", "error": "network down"}

    monkeypatch.setattr(bridge, "push_switchboard", fake_push)
    monkeypatch.setattr(bridge, "_write_agent_action_receipt", lambda *a, **k: None)
    bridge.RECEIPTS.mkdir(parents=True)
    for i in range(1, 5):
        d = bridge.RECEIPTS / f"project-watchdog-{i}"
        d.mkdir()
        (d / "receipt.json").write_text(json.dumps({
            "run_id": f"project-watchdog-{i}",
            "status": "NEEDS_ATTENTION",
            "handled_issues": [{
                "repo": "grahama1970/agent-skills", "issue_number": i,
                "action": "ticket_repair", "status": "NEEDS_ATTENTION",
                "requires_human_input": False, "summary": "machine retry",
            }],
        }))

    result = bridge.deliver_due()

    assert result["attempts"] == 2
    assert result["status"] == "PARTIAL"
    assert len(sent) == 2
    checkpoint = bridge._load_checkpoint()
    assert checkpoint.pending or checkpoint.pending_dirs


def test_acknowledged_history_cannot_starve_new_receipt(tmp_path, monkeypatch):
    bridge = b
    monkeypatch.setenv("PROJECT_WATCHDOG_NOTIFY_DRAIN_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("PROJECT_WATCHDOG_NOTIFY_DRAIN_MAX_SECONDS", "60")
    monkeypatch.setattr(bridge, "STATE_ROOT", tmp_path)
    monkeypatch.setattr(bridge, "RECEIPTS", tmp_path / "receipts")
    monkeypatch.setattr(bridge, "CURSOR", tmp_path / "notify-bridge-cursor.json")
    monkeypatch.setattr(bridge, "CHECKPOINTS", tmp_path / "notify-bridge-checkpoints.json")
    monkeypatch.setattr(bridge, "BRIDGE_LOCK", tmp_path / "notify-bridge.lock")
    monkeypatch.setattr(bridge, "SWITCHBOARD_DEDUP", tmp_path / "notify-bridge-dedup.json")
    monkeypatch.setattr(bridge, "_write_agent_action_receipt", lambda *a, **k: None)
    bridge.RECEIPTS.mkdir(parents=True)
    dirs = []
    for i in range(1, 4):
        d = bridge.RECEIPTS / f"project-watchdog-{i}"
        d.mkdir()
        (d / "receipt.json").write_text(json.dumps({
            "run_id": f"project-watchdog-{i}",
            "status": "NEEDS_ATTENTION",
            "handled_issues": [{
                "repo": "grahama1970/agent-skills", "issue_number": i,
                "action": "ticket_repair", "status": "NEEDS_ATTENTION",
                "requires_human_input": False, "summary": "machine retry",
            }],
        }))
        dirs.append(d)
    checkpoint = bridge.BridgeCheckpoint(last_mtime=0)
    for d in dirs[:2]:
        ev = bridge.summarize_events(d)[0]
        bridge._mark_delivered(checkpoint, "terminal", ev["event_id"], {"status": "ACK"})
        bridge._mark_delivered(checkpoint, "pi_agent", ev["event_id"], {"status": "SENT"})
    bridge._save_checkpoint(checkpoint)
    sent: list[str] = []
    monkeypatch.setattr(bridge, "push_switchboard", lambda ev, **k: sent.append(str(ev["issue"])) or {"status": "SENT", "message_id": ev["issue"]})

    result = bridge.deliver_due()

    assert result["attempts"] == 1
    assert sent == ["3"]
    assert result["status"] == "DELIVERED"


def test_drain_deadline_includes_discovery_and_transport(tmp_path, monkeypatch):
    bridge = b
    monkeypatch.setenv("PROJECT_WATCHDOG_NOTIFY_DRAIN_MAX_ATTEMPTS", "1")
    monkeypatch.setenv("PROJECT_WATCHDOG_NOTIFY_DRAIN_MAX_SECONDS", "0.5")
    monkeypatch.setattr(bridge, "STATE_ROOT", tmp_path)
    monkeypatch.setattr(bridge, "RECEIPTS", tmp_path / "receipts")
    monkeypatch.setattr(bridge, "CURSOR", tmp_path / "notify-bridge-cursor.json")
    monkeypatch.setattr(bridge, "CHECKPOINTS", tmp_path / "notify-bridge-checkpoints.json")
    monkeypatch.setattr(bridge, "BRIDGE_LOCK", tmp_path / "notify-bridge.lock")
    monkeypatch.setattr(bridge, "SWITCHBOARD_DEDUP", tmp_path / "notify-bridge-dedup.json")
    monkeypatch.setattr(bridge, "_write_agent_action_receipt", lambda *a, **k: None)
    bridge.RECEIPTS.mkdir(parents=True)
    d = bridge.RECEIPTS / "project-watchdog-deadline"
    d.mkdir()
    (d / "receipt.json").write_text(json.dumps({
        "run_id": "project-watchdog-deadline",
        "status": "NEEDS_ATTENTION",
        "handled_issues": [{"repo": "grahama1970/agent-skills", "issue_number": 7, "action": "ticket_repair", "status": "NEEDS_ATTENTION", "requires_human_input": False}],
    }))
    timeouts: list[float] = []
    monkeypatch.setattr(bridge, "push_switchboard", lambda ev, **k: timeouts.append(k["timeout_s"]) or {"status": "AGENT_PUSH_FAILED"})

    result = bridge.deliver_due()

    assert result["attempts"] == 1
    assert timeouts and 0 < timeouts[0] <= 0.5


def test_restart_recovers_unregistered_receipt_at_or_before_cursor(tmp_path, monkeypatch):
    bridge = b
    monkeypatch.setattr(bridge, "STATE_ROOT", tmp_path)
    monkeypatch.setattr(bridge, "RECEIPTS", tmp_path / "receipts")
    monkeypatch.setattr(bridge, "CURSOR", tmp_path / "notify-bridge-cursor.json")
    monkeypatch.setattr(bridge, "CHECKPOINTS", tmp_path / "notify-bridge-checkpoints.json")
    monkeypatch.setattr(bridge, "BRIDGE_LOCK", tmp_path / "notify-bridge.lock")
    monkeypatch.setattr(bridge, "SWITCHBOARD_DEDUP", tmp_path / "notify-bridge-dedup.json")
    monkeypatch.setattr(bridge, "push_switchboard", lambda ev, **k: {"status": "SENT", "message_id": f"m{ev['issue']}"})
    monkeypatch.setattr(bridge, "_write_agent_action_receipt", lambda *a, **k: None)
    bridge.RECEIPTS.mkdir(parents=True)
    receipt_dir = bridge.RECEIPTS / "project-watchdog-old-cursor"
    receipt_dir.mkdir()
    (receipt_dir / "receipt.json").write_text(json.dumps({
        "run_id": "project-watchdog-old-cursor",
        "status": "NEEDS_ATTENTION",
        "handled_issues": [{
            "repo": "grahama1970/agent-skills", "issue_number": 123,
            "action": "ticket_repair", "status": "NEEDS_ATTENTION",
            "requires_human_input": False, "summary": "machine retry",
        }],
    }))
    old = time.time() - 1000
    __import__("os").utime(receipt_dir, (old, old))
    bridge.CURSOR.write_text(json.dumps({"last_mtime": time.time()}))

    result = bridge.deliver_due()

    assert result["status"] == "DELIVERED"
    assert result["pushed"][0]["switchboard"]["status"] == "SENT"
    assert "123" in (tmp_path / "events.jsonl").read_text()
