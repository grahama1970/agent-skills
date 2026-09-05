"""Executable regression cases for the measured revision counterexamples.

Git cases use disposable repositories initialized on MAIN only. They never use
branch/worktree/reset/stash/rebase/clean commands and never touch a user's repo.
GitHub/provider substitutes are explicitly boundary tests, NOT live proof.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from watchdog import commands, config, core, github, handlers, native_ticket, primary, registry, target_content as content
from watchdog.primary_models import Operation, QueueState, OwnedTargets, TargetSnapshot, encoded


def git(root: Path, *args: str) -> str:
    return content.git_bytes(root, *args).decode().strip()


@pytest.fixture
def repository(tmp_path):
    origin, root = tmp_path / "origin.git", tmp_path / "primary"
    subprocess.run(["git", "init", "--bare", "--initial-branch=main", str(origin)], check=True, capture_output=True)
    subprocess.run(["git", "init", "--initial-branch=main", str(root)], check=True, capture_output=True)
    git(root, "config", "user.name", "Watchdog fixture")
    git(root, "config", "user.email", "fixture@example.invalid")
    for name, text in [("skills/project-watchdog/registry.py", "old\n"), ("skills/battle/task.py", "battle\n"),
                       ("skills/pitchdeck/view.ts", "pitch\n"), ("other/cron.txt", "cron0\n")]:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        git(root, "add", "--", name)
    git(root, "commit", "-m", "Initial fixture on main")
    git(root, "remote", "add", "origin", str(origin))
    git(root, "push", "origin", "HEAD:refs/heads/main")
    return root, origin, tmp_path / "receipts"


def scope_snapshot(root: Path, target="skills/project-watchdog"):
    return content.snapshot(root, [target], content.remote_pin(root))


def ship_fixture(root, receipts, target, text):
    path = root / target
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    state = content.snapshot(root, [target], content.remote_pin(root))
    sha = content.scoped_commit(root, state, state.remote_sha, receipts, "Scoped fixture ship")
    git(root, "push", "origin", f"{sha}:refs/heads/main")
    return sha


def issue(number, target=None, *, lease=False, hold=False):
    labels = ["agent-work", "type:bug", "route:backend_python_or_skill_runtime"]
    if lease:
        labels.append("maintainer-active")
    if hold:
        labels.append("status:deferred")
    return {"number": number, "title": "fixture", "url": f"https://github.com/fixture/repo/issues/{number}",
            "state": "OPEN", "body": (f"<!-- ticket-skill\ntype: bug\ntarget: {target}\nroute: backend_python_or_skill_runtime\n-->"
                                         if target else "No target recorded."),
            "labels": [{"name": label} for label in labels]}


def operation(root, receipts, number=42, phase="reserved"):
    token = "fixture-token"
    return Operation(phase=phase, run_id="revision-fixture", repo="fixture/repo", project_id="fixture",
                     issue_number=number, action="ticket_repair", owner_token=token, root=str(root),
                     journal=str(primary._area(root) / "operations" / f"{number}-{token}.json"),
                     result_path=str(receipts / "result.json"), receipt_dir=str(receipts),
                     targets=["skills/project-watchdog"], task_sha256="task", scheduler_pid=os.getpid(),
                     boot_id="fixture-boot")


def test_remote_identical_shipped_file_is_eligible_despite_stale_head(repository):
    root, _, receipts = repository
    head = git(root, "rev-parse", "HEAD")
    remote = ship_fixture(root, receipts, "skills/project-watchdog/registry.py", "shipped\n")
    assert head != remote and git(root, "diff", "HEAD", "--name-only", "--", "skills/project-watchdog")
    assert git(root, "diff", remote, "--name-only", "--", "skills/project-watchdog") == ""
    current = scope_snapshot(root)
    result = content.classify(root, current, repo="fixture/repo", number=42, task_sha256="task", owned=None)
    assert set(result.values()) == {"verified_remote_identical"}
    assert git(root, "rev-parse", "HEAD") == head


def test_remote_identical_new_untracked_file_and_deletion(repository):
    root, _, receipts = repository
    ship_fixture(root, receipts, "skills/project-watchdog/new.py", "shipped untracked\n")
    before = scope_snapshot(root)
    (root / "skills/project-watchdog/registry.py").unlink()
    deleted = content.snapshot(root, before.targets, before.remote_sha)
    sha = content.scoped_commit(root, deleted, before.remote_sha, receipts, "Shipped deletion")
    git(root, "push", "origin", f"{sha}:refs/heads/main")
    current = scope_snapshot(root)
    result = content.classify(root, current, repo="fixture/repo", number=42, task_sha256="task", owned=None)
    assert result["skills/project-watchdog/new.py"] == "verified_remote_identical"
    assert result["skills/project-watchdog/registry.py"] == "verified_remote_identical"


def test_actual_target_edit_not_owned_is_not_blanket_approved(repository):
    root, _, _ = repository
    (root / "skills/project-watchdog/registry.py").write_text("concurrent foreign edit\n")
    current = scope_snapshot(root)
    result = content.classify(root, current, repo="fixture/repo", number=42, task_sha256="task", owned=None)
    assert result["skills/project-watchdog/registry.py"] == "unowned_target_edit"


def test_owned_bytes_require_same_ticket_task_and_exact_content(repository):
    root, _, _ = repository
    (root / "skills/project-watchdog/registry.py").write_text("retained repair\n")
    current = scope_snapshot(root)
    owned = OwnedTargets(repo="fixture/repo", issue_number=42, task_sha256="task", run_id="prior",
                         targets=current.targets, files=current.files, provenance="settled_attempt")
    good = content.classify(root, current, repo="fixture/repo", number=42, task_sha256="task", owned=owned)
    wrong = content.classify(root, current, repo="fixture/repo", number=43, task_sha256="task", owned=owned)
    assert set(good.values()) == {"verified_current_task_owned"}
    assert "unowned_target_edit" in wrong.values()
    (root / "skills/project-watchdog/registry.py").write_text("later foreign edit\n")
    changed = content.classify(root, scope_snapshot(root), repo="fixture/repo", number=42, task_sha256="task", owned=owned)
    assert "unowned_target_edit" in changed.values()


def test_unrelated_cron_changes_are_not_hashed_or_attributed(repository, monkeypatch):
    root, _, _ = repository
    before = scope_snapshot(root)
    original = content._read_path
    visited = []
    def bounded(repo, name):
        visited.append(name)
        assert name.startswith("skills/project-watchdog/")
        return original(repo, name)
    monkeypatch.setattr(content, "_read_path", bounded)
    (root / "other/cron.txt").write_text("normal concurrent cron\n")
    (root / "other/untracked.txt").write_text("retain me\n")
    git(root, "add", "--", "other/cron.txt")
    after = scope_snapshot(root)
    content.require_unchanged(before, after)
    assert visited and "other/cron.txt" not in visited


def test_target_change_after_authorization_is_rejected(repository):
    root, _, _ = repository
    before = scope_snapshot(root)
    (root / "skills/project-watchdog/registry.py").write_text("raced\n")
    with pytest.raises(content.ContentConflict):
        content.require_unchanged(before, scope_snapshot(root))


def test_private_index_publication_preserves_head_index_and_unrelated_files(repository):
    root, _, receipts = repository
    before = scope_snapshot(root)
    (root / "other/cron.txt").write_text("staged unrelated\n")
    git(root, "add", "--", "other/cron.txt")
    index_before = (root / ".git/index").read_bytes()
    head_before = git(root, "rev-parse", "HEAD")
    (root / "skills/project-watchdog/registry.py").write_text("repair\n")
    reviewed = content.snapshot(root, before.targets, before.remote_sha)
    commit = content.publish(root, before, reviewed, receipts, "revision-fixture", 42, remote_required=True)
    assert commit == content.remote_pin(root)
    assert (root / ".git/index").read_bytes() == index_before
    assert git(root, "rev-parse", "HEAD") == head_before
    assert (root / "other/cron.txt").read_text() == "staged unrelated\n"


def test_disjoint_remote_advance_is_preserved_without_rebase(repository):
    root, _, receipts = repository
    before = scope_snapshot(root)
    (root / "skills/project-watchdog/registry.py").write_text("repair\n")
    reviewed = content.snapshot(root, before.targets, before.remote_sha)
    other = ship_fixture(root, receipts, "other/cron.txt", "independently shipped\n")
    result = content.publish(root, before, reviewed, receipts, "revision-fixture", 42, remote_required=True)
    assert git(root, "show", f"{result}:other/cron.txt") == "independently shipped"
    assert git(root, "rev-parse", f"{result}^") == other


def test_attributable_out_of_scope_commit_is_rejected(repository):
    root, _, receipts = repository
    before = content.snapshot(root, ["other"], content.remote_pin(root))
    (root / "other/cron.txt").write_text("unauthorized worker change\n")
    bad = content.snapshot(root, before.targets, before.remote_sha)
    commit = content.scoped_commit(root, bad, before.remote_sha, receipts, "Watchdog-Run: revision-fixture")
    with pytest.raises(content.ContentConflict, match="unauthorized paths"):
        content.assert_scoped_commit(root, commit, ["skills/project-watchdog"])


def test_pitchdeck_foreign_lease_does_not_block_battle_or_watchdog():
    foreign = issue(1599, "skills/pitchdeck", lease=True, hold=True)
    busy = registry.busy_targets([foreign])
    assert not registry.targets_are_blocked({"skills/battle"}, busy)
    assert not registry.targets_are_blocked({"skills/project-watchdog"}, busy)
    assert registry.targets_are_blocked({"skills/pitchdeck/editor"}, busy)


def test_unknown_foreign_lease_is_not_global_target_authority():
    foreign = issue(1599, lease=True, hold=True)
    assert registry.busy_targets([foreign]) == set()
    assert not registry.targets_are_blocked({"skills/battle"}, registry.busy_targets([foreign]))
    assert registry.classify_issue(foreign) is None


@pytest.mark.parametrize("scope", [None, ["skills/battle"]])
def test_actual_tick_routes_unrelated_issue_despite_foreign_lease(repository, monkeypatch, scope):
    """Real commands._tick_locked routing, mocked network/provider boundaries."""
    root, _, receipts = repository
    receipts.mkdir(parents=True, exist_ok=True)
    project = {"project_id": "fixture", "repo": "fixture/repo", "worktree": str(root), "runner_kind": "tau-command-loop"}
    if scope:
        project["issue_target_prefixes"] = scope
    state = {"global": {"state": "active"}, "projects": {"fixture": {"state": "active"}}}
    state_path, projects_path = receipts / "state.json", receipts / "projects.json"
    state_path.write_text(json.dumps(state)); projects_path.write_text(json.dumps({"projects": [project]}))
    monkeypatch.setattr(config, "state_path", lambda: state_path)
    monkeypatch.setattr(config, "projects_path", lambda: projects_path)
    monkeypatch.setattr(config, "execution_lock_root", lambda: receipts / "execution-locks")
    monkeypatch.setattr(config, "receipt_root", lambda: receipts)
    monkeypatch.setattr(config, "event_log_path", lambda: receipts / "events.jsonl")
    monkeypatch.setattr(commands, "tick_deadline_seconds", lambda: 240)
    monkeypatch.setattr(primary, "reconcile", lambda root: None)
    foreign, target = issue(1599, "skills/pitchdeck", lease=True, hold=True), issue(42, "skills/battle")
    def listing(repo, *, state, label):
        if label == "maintainer-active": return [foreign]
        if label == "agent-active": return []
        return [foreign, target]
    monkeypatch.setattr(github, "list_issues", listing)
    monkeypatch.setattr(github, "issue_comments", lambda *a, **k: [])
    monkeypatch.setattr(registry, "dependency_gate", lambda *a, **k: {"status": "none"})
    monkeypatch.setattr(commands.streaks, "clear_idle", lambda *a: None)
    dispatched, captured = [], {}
    def handle(run_id, receipt_dir, entry, selected, *, apply):
        dispatched.append(selected["number"])
        return {"issue_number": selected["number"], "ok": True, "status": "COMPLETED", "ticket_closed": True}
    monkeypatch.setattr(commands, "handle_issue", handle)
    monkeypatch.setattr(commands, "finish", lambda run, directory, receipt, code, **kw: captured.update(receipt=receipt, code=code) or code)
    commands._tick_locked("fixture-run", receipts, apply=True, project_id="fixture", max_tickets=1,
                          release_scheduler_lock=lambda: None)
    assert dispatched == [42]
    assert captured["receipt"]["handled_issues"][0]["issue_number"] == 42
    assert "maintainer-active" in {x["name"] for x in foreign["labels"]}


def test_canonical_reservation_ignores_configurable_state_root(repository, monkeypatch):
    root, _, _ = repository
    first = primary._lock(root)
    assert first is not None
    try:
        monkeypatch.setenv("PROJECT_WATCHDOG_STATE_ROOT", "/unrelated/alias")
        assert primary._lock(root) is None
        assert primary.writer_active(root)
    finally:
        os.close(first)
    assert not primary.writer_active(root)


def test_recovery_of_prelaunch_crash_releases_local_reservation_not_foreign_labels(repository):
    root, _, receipts = repository
    record = operation(root, receipts)
    core.write_json(Path(record.journal), encoded(record))
    with patch.object(github, "issue_edit", side_effect=AssertionError("must not mutate labels")):
        assert primary.reconcile(root) is None
    assert not primary.writer_active(root)
    assert Operation.model_validate(core.load_json(Path(record.journal))).phase == "retryable"


def test_unknown_operation_retains_only_its_target_and_has_executable_recovery(repository):
    root, _, receipts = repository
    record = operation(root, receipts)
    core.write_json(Path(record.journal), encoded(record))
    observation = primary.observations(root)
    assert not observation["writer_active"]
    assert observation["operations"][0]["targets"] == ["skills/project-watchdog"]
    assert "recover_primary.py" in observation["recovery_command"]
    assert not registry.targets_are_blocked({"skills/battle"}, set(record.targets))


def test_journal_queue_and_owned_state_are_strict(repository):
    root, _, receipts = repository
    raw = encoded(operation(root, receipts))
    with pytest.raises(ValidationError): Operation.model_validate({**raw, "issue_number": "42"})
    with pytest.raises(ValidationError): Operation.model_validate({**raw, "unknown_permission": True})
    with pytest.raises(ValidationError): Operation.model_validate({**raw, "phase": "closing"})
    with pytest.raises(ValidationError): QueueState.model_validate({"attempts": {"42": "yesterday"}})
    with pytest.raises(ValidationError): QueueState.model_validate({"sequence": 1, "unknown": True})


def test_queue_moves_attempted_failure_behind_older_unattempted_issue(repository):
    root, _, _ = repository
    candidates = [issue(42, "skills/project-watchdog"), issue(43, "skills/battle")]
    fd = primary._lock(root)
    try: primary._attempt(root, 42)
    finally: os.close(fd)
    assert [i["number"] for i in primary.queue_order(root, candidates)] == [43, 42]


def test_flock_directory_survives_release_but_status_and_ui_are_unheld(tmp_path, monkeypatch):
    lock = tmp_path / "lock"
    monkeypatch.setattr(config, "lock_dir", lambda: lock)
    assert core.acquire_lock("fixture-lock")
    assert core.lock_holder_alive()
    core.release_lock()
    assert lock.is_dir() and not core.lock_holder_alive()
    from watchdog.ui_export import build_snapshot
    view = build_snapshot({"lock_held": core.lock_holder_alive(), "receipt_root": str(tmp_path / "none")})
    assert view["lock_held"] is False


def test_all_pitchdeck_holds_are_non_mutating(repository, monkeypatch):
    root, _, receipts = repository
    for number in range(1599, 1603):
        assert registry.policy_held("grahama1970/agent-skills", number)
        record = operation(root, receipts, number=number)
        record.repo = "grahama1970/agent-skills"
        monkeypatch.setattr(github, "get_issue", lambda *a: (_ for _ in ()).throw(AssertionError("no mutation/read needed")))
        assert native_ticket.release(record) is False


def test_legacy_routes_reach_same_primary_adapter(repository, monkeypatch):
    root, _, receipts = repository
    project = {"project_id": "fixture", "repo": "fixture/repo", "worktree": str(root)}
    start = root / "start.json"; start.write_text("{}")
    routed = []
    monkeypatch.setattr(primary, "dispatch", lambda run, directory, p, i, function, **kw: routed.append((i, function)) or {"ok": True})
    handoff = issue(42, "skills/battle")
    handoff["body"] += "\nproject-watchdog-action:tau-handoff-dispatch start=start.json max_steps=1 apply_transport=false"
    handlers.handle_tau_handoff_dispatch("fixture", receipts, project, handoff, apply=True)
    handlers.handle_tau_coder_spec("fixture", receipts, project, issue(43, "skills/battle"), apply=True)
    assert [entry[0]["watchdog_action"] for entry in routed] == ["tau_handoff_dispatch", "add_tau_coder_command_spec"]
    assert all(entry[1] is handlers._handle_ticket_repair_primary for entry in routed)


def test_node_pass_cannot_settle_missing_reviewer(tmp_path):
    core.write_json(tmp_path / "dag.json", {"nodes": [{"id": "creator"}, {"id": "reviewer"}]})
    core.write_json(tmp_path / "dag-progress.json", {"status": "PASS"})
    core.write_json(tmp_path / "creator/node-receipt.json", {"node_id": "creator", "status": "PASS"})
    assert handlers.inspect_tau_stream(tmp_path)["terminal"] is False
    core.write_json(tmp_path / "reviewer/node-receipt.json", {"node_id": "reviewer", "status": "PASS"})
    assert handlers.inspect_tau_stream(tmp_path)["terminal"] is True


@pytest.mark.parametrize("payload", [
    {"status": "READY", "cases": [{"status": "FAIL"}]},
    {"status": "USABLE_WITH_GAPS"}, {"status": "PASS", "not_run": 1},
    {"status": "PASS", "skipped": 1}, {"status": "PASS", "failed": 1}])
def test_contradictory_or_incomplete_proof_is_rejected(tmp_path, payload):
    path = tmp_path / "result.json"; path.write_text(json.dumps(payload))
    assert handlers.inspect_proof_artifact(str(path), not_before=time.time())["passed"] is False


def test_fresh_non_json_and_stale_json_are_not_proof(tmp_path):
    txt = tmp_path / "result.txt"; txt.write_text("PASS")
    assert not handlers.inspect_proof_artifact(str(txt), not_before=time.time())["passed"]
    result = tmp_path / "result.json"; result.write_text('{"status":"PASS"}')
    os.utime(result, (1, 1))
    assert not handlers.inspect_proof_artifact(str(result), not_before=time.time())["passed"]


def test_output_pressure_does_not_deadlock_real_subprocess(tmp_path):
    command = [sys.executable, "-c", "import os; os.write(1,b'x'*1048576); os.write(2,b'y'*1048576)"]
    row = handlers.run_ask_tau_dag_with_stream_monitor(command, cwd=tmp_path, timeout_s=20,
        ask_run_dir=tmp_path / "no-tau", monitor_path=tmp_path / "monitor.json", poll_interval_s=0.02)
    assert row["exit_code"] == 0
    assert Path(row["stdout_path"]).stat().st_size == 1048576
    assert Path(row["stderr_path"]).stat().st_size == 1048576
    assert not handlers.inspect_tau_stream(tmp_path / "no-tau")["terminal"]


def test_machine_followup_authority_does_not_turn_failure_into_success():
    row = {"ok": False, "requires_human_input": False}
    assert not commands._handled_result_allows_agent_followup(row)
    assert commands._handled_tick_status(row, preview=False) == "NEEDS_ATTENTION"


@pytest.fixture
def closing_record(repository):
    from watchdog.primary_models import NativeClosure, LeaseEvent
    root, _, receipts = repository
    receipts.mkdir(parents=True, exist_ok=True)
    frozen = scope_snapshot(root)
    proof, review = receipts / "proof.md", receipts / "review.md"
    proof.write_text("<!-- watchdog-proof:fixture-token -->\nActual fixture proof.\n")
    review.write_text("VERDICT: PASS\n")
    lease = LeaseEvent(id=100, event="labeled", actor="fixture-agent", created_at="2026-09-05T00:00:00Z")
    closure = NativeClosure(proof_path=str(proof), proof_sha256=content.digest(proof.read_bytes()),
        review_path=str(review), review_sha256=content.digest(review.read_bytes()), commit=frozen.remote_sha,
        remote_required=True, scope=frozen.targets, content=frozen)
    record = operation(root, receipts).model_copy(update={"phase": "closing", "tau_settled": True,
        "lease_event": lease, "lease_agent": "project-watchdog-fixture-token", "closure": closure})
    return Operation.model_validate(encoded(record))


def test_native_close_lost_response_is_read_back_without_second_close(closing_record, monkeypatch):
    record = closing_record
    state = issue(record.issue_number, "skills/project-watchdog", lease=True)
    posted, calls = [], []
    monkeypatch.setattr(github, "get_issue", lambda *a: dict(state))
    monkeypatch.setattr(native_ticket, "comments", lambda *a: list(posted))
    monkeypatch.setattr(native_ticket, "lease_event", lambda *a: record.lease_event)
    def close_mutation(root, repo, action, number, *args):
        calls.append(action)
        assert action == "close" and "--proof" in args and "--review" in args
        posted.append({"body": Path(record.closure.proof_path).read_text()})
        state.update(state="CLOSED", stateReason="COMPLETED")
        return {"exit_code": 124, "stdout": "", "stderr": "lost reply AFTER mutation"}
    monkeypatch.setattr(native_ticket, "invoke", close_mutation)
    assert native_ticket.close(record)["ticket_closed"] is True
    # Subsequent legitimate target edits must not be rolled back to acknowledge closure.
    (Path(record.root) / "skills/project-watchdog/registry.py").write_text("next task\n")
    assert native_ticket.close(record)["reconciled"] is True
    assert calls == ["close"]


def test_native_close_failed_mutation_never_becomes_completed(closing_record, monkeypatch):
    record = closing_record
    monkeypatch.setattr(github, "get_issue", lambda *a: issue(42, "skills/project-watchdog", lease=True))
    monkeypatch.setattr(native_ticket, "comments", lambda *a: [])
    monkeypatch.setattr(native_ticket, "lease_event", lambda *a: record.lease_event)
    monkeypatch.setattr(native_ticket, "invoke", lambda *a: {"exit_code": 1, "stderr": "offline"})
    with pytest.raises(content.ContentConflict, match="not confirmed"):
        native_ticket.close(record)


def test_native_close_rejects_foreign_generation_and_changed_proof(closing_record, monkeypatch):
    from watchdog.primary_models import LeaseEvent
    record = closing_record
    monkeypatch.setattr(github, "get_issue", lambda *a: issue(42, "skills/project-watchdog", lease=True))
    monkeypatch.setattr(native_ticket, "comments", lambda *a: [])
    monkeypatch.setattr(native_ticket, "lease_event", lambda *a: LeaseEvent(id=101, event="labeled",
        actor="other-agent", created_at="2026-09-05T00:10:00Z"))
    monkeypatch.setattr(native_ticket, "invoke", lambda *a: pytest.fail("must not mutate foreign lease"))
    with pytest.raises(content.ContentConflict, match="generation"):
        native_ticket.close(record)
    Path(record.closure.proof_path).write_text("replacement unreviewed proof")
    with pytest.raises(content.ContentConflict, match="changed after admission"):
        native_ticket.close(record)


def test_owned_release_does_not_remove_foreign_generation(closing_record, monkeypatch):
    record = closing_record
    monkeypatch.setattr(github, "get_issue", lambda *a: issue(42, "skills/project-watchdog", lease=True))
    monkeypatch.setattr(native_ticket, "lease_event", lambda *a: record.lease_event.model_copy(update={"id": 999}))
    monkeypatch.setattr(native_ticket, "invoke", lambda *a: pytest.fail("foreign release forbidden"))
    assert native_ticket.release(record) is False


def test_closure_outbox_recovery_retries_native_close_without_new_provider(closing_record, monkeypatch):
    record = closing_record
    core.write_json(Path(record.journal), encoded(record))
    attempts = []
    def close(row):
        attempts.append(row.run_id)
        if len(attempts) == 1:
            raise content.ContentConflict("temporary native endpoint failure")
        return {"ok": True, "status": "COMPLETED", "ticket_closed": True, "commands": []}
    monkeypatch.setattr(native_ticket, "close", close)
    monkeypatch.setattr(native_ticket, "release", lambda row: True)
    monkeypatch.setattr(handlers, "run_ask_tau_dag_with_stream_monitor", lambda **kw: pytest.fail("no replacement provider"))
    first = primary.reconcile(Path(record.root))
    assert first["writer_active"] is False and len(first["operations"]) == 1
    assert primary.reconcile(Path(record.root)) is None
    final = Operation.model_validate(core.load_json(Path(record.journal)))
    assert final.phase == "finished" and final.result["ticket_closed"] is True
    assert attempts == [record.run_id, record.run_id]


def test_unknown_remote_run_recovery_never_dispatches_duplicate(closing_record, monkeypatch):
    record = closing_record.model_copy(update={"phase": "uncertain", "tau_settled": False,
        "closure": None, "ask_run_dir": str(Path(closing_record.receipt_dir) / "ask"),
        "dispatched_at": time.time()})
    core.write_json(Path(record.journal), encoded(record))
    monkeypatch.setattr(handlers, "inspect_tau_stream", lambda path: {"terminal": False})
    monkeypatch.setattr(native_ticket, "release", lambda row: pytest.fail("unknown execution must not be released"))
    monkeypatch.setattr(handlers, "run_ask_tau_dag_with_stream_monitor", lambda **kw: pytest.fail("duplicate worker forbidden"))
    observed = primary.reconcile(Path(record.root))
    assert len(observed["operations"]) == 1 and observed["writer_active"] is False
    assert not registry.targets_are_blocked({"skills/battle"}, set(observed["operations"][0]["targets"]))


def test_legacy_unknown_owner_metadata_not_reclaimed(tmp_path, monkeypatch):
    lock = tmp_path / "legacy-lock"
    monkeypatch.setattr(config, "lock_dir", lambda: lock)
    core.write_json(lock / "owner.json", {"run_id": "old", "pid": "not-a-pid"})
    before = (lock / "owner.json").read_bytes()
    assert core.acquire_lock("new") is False
    assert (lock / "owner.json").read_bytes() == before
    assert not core._kernel_lock_busy(lock)


def test_retained_315_inventory_is_read_only_even_with_detached_rebase(repository, monkeypatch):
    root, _, _ = repository
    actual_git = primary.git
    calls = []
    def observe(repo, *args):
        calls.append(args)
        if args[0] == "for-each-ref": return "refs/heads/watchdog/issue-315 " + "a" * 40 + "\n"
        if args[:2] == ("worktree", "list"):
            return f"worktree {root}\0HEAD {'b' * 40}\0branch refs/heads/main\0\0worktree /retained/tree\0HEAD {'a' * 40}\0detached\0\0"
        return actual_git(repo, *args)
    monkeypatch.setattr(primary, "git", observe)
    result = primary.legacy_inventory(root, 315)
    assert result["tip"] == "a" * 40 and result["mutation_authorized"] is False
    assert any("worktree /retained/tree" in row for row in result["registered_worktrees"])
    assert {row[0] for row in calls} <= {"for-each-ref", "worktree", "rev-parse", "symbolic-ref"}


@pytest.mark.parametrize("fail_close,audit_fail", [(False, False), (True, False), (False, True)])
def test_native_shell_keeps_lease_until_close_and_never_bypasses_retention(repository, tmp_path, fail_close, audit_fail):
    """Execute the supplied helper with explicit simulated gh/audit boundaries."""
    import shutil
    root, _, receipts = repository
    receipts.mkdir(parents=True, exist_ok=True)
    sandbox = tmp_path / "helper-fixture"; sandbox.mkdir()
    source = Path(__file__).resolve().parents[2] / "best-practices-github-ticket/scripts/gh-ticket-tools.sh"
    helper = sandbox / source.name; shutil.copyfile(source, helper)
    state = sandbox / "state.json"
    state.write_text(json.dumps({"closed": False, "leased": True, "calls": []}))
    fake_gh = sandbox / "gh"
    fake_gh.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
p=Path(os.environ["FIXTURE_STATE"]); state=json.loads(p.read_text()); args=sys.argv[1:]
state["calls"].append(args); p.write_text(json.dumps(state))
if args[:2]==["issue","view"]:
    field=args[args.index("--json")+1]
    if field=="labels": print("maintainer-active" if state["leased"] else "")
    elif field=="body": print("target: skills/project-watchdog")
    elif field=="state": print("CLOSED" if state["closed"] else "OPEN")
    else: raise SystemExit(3)
elif args[:2]==["issue","close"]:
    if os.environ.get("FIXTURE_FAIL_CLOSE")=="1": raise SystemExit(1)
    state["closed"]=True; p.write_text(json.dumps(state))
elif args[:2]==["issue","edit"]:
    assert "--remove-label" in args and state["closed"]
    state["leased"]=False; p.write_text(json.dumps(state))
elif args[:2]==["issue","comment"]: pass
else: raise SystemExit(4)
'''); fake_gh.chmod(0o755)
    audit = sandbox / "audit-worktrees.sh"
    audit.write_text('''#!/bin/sh
printf '%s\\n' "$*" >> "$FIXTURE_AUDIT_LOG"
[ "$FIXTURE_AUDIT_FAIL" != "1" ]
'''); audit.chmod(0o755)
    proof = receipts / "proof.md"; proof.write_text("Explicit simulated proof for helper ordering fixture\n")
    env = dict(os.environ, PATH=str(sandbox) + os.pathsep + os.environ["PATH"],
               FIXTURE_STATE=str(state), FIXTURE_FAIL_CLOSE="1" if fail_close else "0",
               FIXTURE_AUDIT_FAIL="1" if audit_fail else "0", FIXTURE_AUDIT_LOG=str(sandbox / "audit.log"))
    env.pop("GH_TICKET_SKIP_WORKTREE_AUDIT", None)
    result = subprocess.run(["bash", str(helper), "close", "42", "--repo", "fixture/repo",
                             "--proof", str(proof), "--reason", "completed"], cwd=root, env=env,
                            capture_output=True, text=True, check=False)
    data = json.loads(state.read_text())
    assert (sandbox / "audit.log").exists()
    mutation_calls = [row[1] for row in data["calls"] if row[:2] in (["issue", "close"], ["issue", "edit"])]
    if audit_fail:
        assert result.returncode != 0 and mutation_calls == [] and data["leased"]
    elif fail_close:
        assert result.returncode != 0 and mutation_calls == ["close"] and data["leased"]
    else:
        assert result.returncode == 0 and mutation_calls == ["close", "edit"]
        assert data["closed"] and not data["leased"]


@pytest.mark.parametrize("foreign_target_edit", [False, True])
def test_real_repair_handler_admits_shipped_bytes_but_stops_unowned_target(repository, monkeypatch, foreign_target_edit):
    """Real preflight/ownership handler; stop at the explicitly simulated native lease boundary."""
    root, _, receipts = repository
    receipts.mkdir(parents=True, exist_ok=True)
    ship_fixture(root, receipts, "skills/project-watchdog/registry.py", "already shipped\n")
    if foreign_target_edit:
        (root / "skills/project-watchdog/registry.py").write_text("new foreign edit\n")
    project = {"project_id": "fixture", "repo": "fixture/repo", "worktree": str(root)}
    selected = issue(42, "skills/project-watchdog")
    record = operation(root, receipts).model_copy(update={"task_sha256": content.digest(selected["body"].encode())})
    state = receipts / "state.json"
    state.write_text(json.dumps({"global": {"state": "active"}, "projects": {"fixture": {"state": "active"}}}))
    monkeypatch.setattr(config, "state_path", lambda: state)
    monkeypatch.setattr(primary, "_CURRENT", record)
    # Temporary filesystem origin is the explicit GitHub boundary substitute.
    monkeypatch.setattr(primary, "assert_repository", lambda path, repo: None)
    monkeypatch.setattr(registry, "lane_busy_issues", lambda *a: [])
    acquired = []
    class ReachedNativeLease(Exception): pass
    def lease(*args):
        acquired.append(True)
        raise ReachedNativeLease()
    monkeypatch.setattr(native_ticket, "acquire", lease)
    if foreign_target_edit:
        with pytest.raises(primary.Refusal, match="target ownership conflict"):
            handlers._handle_ticket_repair_primary("fixture", receipts, project, selected, apply=True)
        assert acquired == []
    else:
        with pytest.raises(ReachedNativeLease):
            handlers._handle_ticket_repair_primary("fixture", receipts, project, selected, apply=True)
        assert acquired == [True]
        ownership = json.loads((receipts / "target-ownership.json").read_text())
        assert set(ownership.values()) == {"verified_remote_identical"}


def test_aggregate_pass_cannot_erase_failed_required_node(tmp_path):
    core.write_json(tmp_path / "dag.json", {"nodes": [{"id": "creator"}, {"id": "reviewer"}]})
    core.write_json(tmp_path / "dag-progress.json", {"status": "PASS"})
    core.write_json(tmp_path / "creator/node-receipt.json", {"node_id": "creator", "status": "PASS"})
    core.write_json(tmp_path / "reviewer/node-receipt.json", {"node_id": "reviewer", "status": "FAIL"})
    observed = handlers.inspect_tau_stream(tmp_path)
    assert observed["terminal"] is True
    assert observed["terminal_status"] == "NEEDS_ATTENTION"
