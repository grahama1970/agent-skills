from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from watchdog import commands, config, registry  # noqa: E402


def _issue(num: int, target: str) -> dict:
    return {
        "number": num,
        "body": f"type: bug\ntarget: {target}\nroute: backend_python_or_skill_runtime\n",
        "labels": [{"name": "agent-work"}],
        "watchdog_action": "ticket_repair",
        "watchdog_targets": [target],
    }


def test_production_tick_admits_three_repairs_serially_across_fleet(tmp_path: Path, monkeypatch) -> None:
    projects_path = tmp_path / "projects.json"
    state_path = tmp_path / "state.json"
    receipt_dir = tmp_path / "receipt"
    projects_path.write_text(json.dumps({
        "projects": [
            {"project_id": "alpha", "repo": "o/alpha", "worktree": str(tmp_path / "alpha")},
            {"project_id": "beta", "repo": "o/beta", "worktree": str(tmp_path / "beta")},
        ]
    }))
    state_path.write_text(json.dumps({
        "global": {"state": "active"},
        "projects": {"alpha": {"state": "active"}, "beta": {"state": "active"}},
    }))
    handled: list[tuple[str, int]] = []
    released: list[str] = []
    captured: dict = {}

    def fake_list(run_id, candidate, busy, *, skip_issue_numbers=None, skip_issue_reasons=None, only_issue=None, apply=False):
        registry.LAST_SCAN.clear()
        registry.LAST_SCAN.update({"scanned": 2, "excluded": {}, "excluded_issues": {}, "dependency_unblocks": []})
        if candidate["project_id"] == "alpha":
            return [_issue(1, "skills/alpha"), _issue(2, "skills/alpha-two")]
        return [_issue(3, "skills/beta")]

    def fake_handle(run_id, receipt_dir, project, issue, *, apply):
        handled.append((project["project_id"], int(issue["number"])))
        return {"ok": True, "status": "COMPLETED", "issue_number": int(issue["number"]), "repo": project["repo"]}

    monkeypatch.setattr(config, "projects_path", lambda: projects_path)
    monkeypatch.setattr(config, "state_path", lambda: state_path)
    monkeypatch.setattr(commands.primary, "reconcile", lambda root: {})
    monkeypatch.setattr(commands.registry, "lane_busy_issues", lambda *a, **k: [])
    monkeypatch.setattr(commands, "list_routable_issues", fake_list)
    monkeypatch.setattr(commands, "acquire_execution_lock", lambda run_id, targets: "+".join(sorted(targets)))
    monkeypatch.setattr(commands, "release_execution_lock", lambda lock: released.append(lock))
    monkeypatch.setattr(commands, "handle_issue", fake_handle)
    monkeypatch.setattr(commands.streaks, "clear_idle", lambda *a, **k: None)
    monkeypatch.setattr(commands, "_persist_tick_state", lambda state: None)
    monkeypatch.setattr(commands, "finish", lambda run_id, d, receipt, code, **k: captured.update(receipt=receipt, code=code) or code)

    rc = commands._tick_locked("run", receipt_dir, apply=True, project_id="all", max_tickets=3)

    assert rc == 0
    assert handled == [("alpha", 1), ("alpha", 2), ("beta", 3)]
    assert captured["receipt"]["handled_count"] == 3
    assert captured["receipt"]["rotation"]["admitted_projects"] == ["alpha", "alpha", "beta"]
    assert released == ["skills/alpha", "skills/alpha-two", "skills/beta"]


def test_no_start_refusal_does_not_consume_creator_slot(tmp_path: Path, monkeypatch) -> None:
    projects_path = tmp_path / "projects.json"
    state_path = tmp_path / "state.json"
    projects_path.write_text(json.dumps({"projects": [
        {"project_id": "alpha", "repo": "o/alpha", "worktree": str(tmp_path / "alpha")},
        {"project_id": "beta", "repo": "o/beta", "worktree": str(tmp_path / "beta")},
    ]}))
    state_path.write_text(json.dumps({"global": {"state": "active"}, "projects": {"alpha": {"state": "active"}, "beta": {"state": "active"}}}))
    handled: list[tuple[str, int]] = []
    captured: dict = {}

    def fake_list(run_id, candidate, busy, *, skip_issue_numbers=None, skip_issue_reasons=None, only_issue=None, apply=False):
        registry.LAST_SCAN.clear(); registry.LAST_SCAN.update({"scanned": 1, "excluded": {}, "excluded_issues": {}, "dependency_unblocks": []})
        return [_issue(1, "skills/alpha")] if candidate["project_id"] == "alpha" else [_issue(2, "skills/beta")]

    def fake_handle(run_id, receipt_dir, project, issue, *, apply):
        handled.append((project["project_id"], int(issue["number"])))
        if project["project_id"] == "alpha":
            return {"ok": True, "status": "SKIPPED", "stop_reason": "creator_transport_outage", "issue_number": 1, "repo": project["repo"]}
        return {"ok": True, "status": "COMPLETED", "issue_number": 2, "repo": project["repo"]}

    monkeypatch.setattr(config, "projects_path", lambda: projects_path)
    monkeypatch.setattr(config, "state_path", lambda: state_path)
    monkeypatch.setattr(commands.primary, "reconcile", lambda root: {})
    monkeypatch.setattr(commands.registry, "lane_busy_issues", lambda *a, **k: [])
    monkeypatch.setattr(commands, "list_routable_issues", fake_list)
    monkeypatch.setattr(commands, "acquire_execution_lock", lambda run_id, targets: "+".join(sorted(targets)))
    monkeypatch.setattr(commands, "release_execution_lock", lambda lock: None)
    monkeypatch.setattr(commands, "handle_issue", fake_handle)
    monkeypatch.setattr(commands.streaks, "clear_idle", lambda *a, **k: None)
    monkeypatch.setattr(commands, "_persist_tick_state", lambda state: None)
    monkeypatch.setattr(commands, "finish", lambda run_id, d, receipt, code, **k: captured.update(receipt=receipt, code=code) or code)

    rc = commands._tick_locked("run", tmp_path / "receipt", apply=True, project_id="all", max_tickets=1)

    assert rc == 0
    assert handled == [("alpha", 1), ("beta", 2)]
    assert captured["receipt"]["handled_count"] == 2


def test_reservation_settlement_order_and_exception_cleanup(tmp_path: Path, monkeypatch) -> None:
    import pytest
    projects_path = tmp_path / "projects.json"
    state_path = tmp_path / "state.json"
    projects_path.write_text(json.dumps({"projects": [{"project_id": "alpha", "repo": "o/alpha", "worktree": str(tmp_path / "alpha")}]}))
    state_path.write_text(json.dumps({"global": {"state": "active"}, "projects": {"alpha": {"state": "active"}}}))
    held: set[str] = set()
    released: list[str] = []

    def acquire(run_id, targets):
        lock = "+".join(sorted(targets))
        held.add(lock)
        return lock

    def release(lock):
        if lock:
            released.append(lock)
            held.discard(lock)

    def fake_list(run_id, candidate, busy, *, skip_issue_numbers=None, skip_issue_reasons=None, only_issue=None, apply=False):
        registry.LAST_SCAN.clear(); registry.LAST_SCAN.update({"scanned": 2, "excluded": {}, "excluded_issues": {}, "dependency_unblocks": []})
        return [_issue(1, "skills/a"), _issue(2, "skills/b")]

    def fake_handle(run_id, receipt_dir, project, issue, *, apply):
        assert len(held) == 1
        raise RuntimeError("boom")

    monkeypatch.setattr(config, "projects_path", lambda: projects_path)
    monkeypatch.setattr(config, "state_path", lambda: state_path)
    monkeypatch.setattr(commands.primary, "reconcile", lambda root: {})
    monkeypatch.setattr(commands.registry, "lane_busy_issues", lambda *a, **k: [])
    monkeypatch.setattr(commands, "list_routable_issues", fake_list)
    monkeypatch.setattr(commands, "acquire_execution_lock", acquire)
    monkeypatch.setattr(commands, "release_execution_lock", release)
    monkeypatch.setattr(commands, "handle_issue", fake_handle)

    with pytest.raises(RuntimeError):
        commands._tick_locked("run", tmp_path / "receipt", apply=True, project_id="all", max_tickets=2)
    assert held == set()
    assert released == ["skills/a"]
