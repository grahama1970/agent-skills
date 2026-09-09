"""Canonical primary writer reservation and target-scoped native lifecycle recovery.

Concrete target reservations use scoped lock records, so disjoint cooperating
writers can proceed while overlapping target paths still serialize. Historical
issue labels and settled/orphaned journals only reserve their known target
scopes. They are never remote liveness or foreign release authority.
"""
from __future__ import annotations

import fcntl
import hashlib
import os
import shlex
import time
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from . import config, github
from .core import load_json, run_cmd, write_json
from .primary_models import Operation, QueueState, encoded

_CURRENT: Operation | None = None
_FD: tuple[int, ...] = ()
_TERMINAL = {"finished", "retryable"}
class Refusal(RuntimeError):
    def __init__(self, reason: str, *, human: bool = False):
        super().__init__(reason)
        self.human = human

def checked(argv: list[str], *, cwd: Path | None = None, timeout: int = 60,
            input_text: str | None = None) -> str:
    row = run_cmd(argv, cwd=cwd, timeout_s=timeout, input_text=input_text)
    if row.get("exit_code") != 0:
        raise Refusal(f"{shlex.join(argv)}: {row.get('stderr') or row.get('stdout')}")
    return str(row.get("stdout", ""))

def git(root: Path, *args: str) -> str:
    return checked(["git", "--no-optional-locks", "-C", str(root), *args])

def identity(root: Path) -> tuple[Path, Path]:
    root = root.expanduser().resolve(strict=True)
    top = Path(git(root, "rev-parse", "--show-toplevel").strip()).resolve(strict=True)
    common = Path(git(root, "rev-parse", "--path-format=absolute", "--git-common-dir").strip()).resolve(strict=True)
    local = Path(git(root, "rev-parse", "--absolute-git-dir").strip()).resolve(strict=True)
    if root != top or local != common or not (root / ".git").is_dir():
        raise Refusal("registered authoring path is not the primary checkout", human=True)
    if git(root, "symbolic-ref", "--quiet", "HEAD").strip() != "refs/heads/main":
        raise Refusal("primary checkout is not on main; no automatic branch switch", human=True)
    return root, common

def assert_repository(root: Path, repo: str) -> None:
    from urllib.parse import urlparse
    remote = git(root, "remote", "get-url", "origin").strip()
    if remote.startswith("git@github.com:"):
        slug = remote.split(":", 1)[1]
    else:
        parsed = urlparse(remote)
        if parsed.hostname != "github.com":
            raise Refusal("origin is not the registered GitHub repository", human=True)
        slug = parsed.path.lstrip("/")
    if slug.removesuffix(".git").rstrip("/").casefold() != repo.casefold():
        raise Refusal("registry repository and primary origin disagree", human=True)

def markers(root: Path) -> list[str]:
    found = []
    for name in ("rebase-merge", "rebase-apply", "MERGE_HEAD", "CHERRY_PICK_HEAD",
                 "REVERT_HEAD", "sequencer", "BISECT_LOG", "index.lock"):
        path = Path(git(root, "rev-parse", "--path-format=absolute", "--git-path", name).strip())
        if path.exists():
            found.append(str(path))
    return found

def safe_targets(raw: set[str] | list[str]) -> list[str]:
    result = set()
    for group in raw:
        for item in str(group).split(","):
            item = item.strip().rstrip("/")
            p = PurePosixPath(item)
            if (not item or item in {"?", "."} or p.is_absolute()
                    or any(x in {"..", ".git"} for x in p.parts)
                    or item.startswith(":") or any(c in item for c in "\x00\r\n*?[]")):
                raise Refusal(f"unusable literal repair target: {item!r}")
            result.add(p.as_posix())
    if not result:
        raise Refusal("repair has no concrete authorized targets")
    return sorted(result)

def in_scope(path: str, targets: list[str]) -> bool:
    return any(path == t or path.startswith(t + "/") for t in targets)

def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def legacy_inventory(root: Path, number: int) -> dict[str, Any]:
    """Read from the primary repo only; never execute recovery in an old tree."""
    branch = f"refs/heads/watchdog/issue-{number}"
    refs = git(root, "for-each-ref", "--format=%(refname) %(objectname)", branch).splitlines()
    exact = [line.split() for line in refs if line.split()[0] == branch]
    raw_listing = git(root, "worktree", "list", "--porcelain", "-z")
    listing = []
    for block in raw_listing.split("\0\0"):
        fields = block.strip("\0").split("\0")
        if not fields or not fields[0]:
            continue
        location = fields[0].removeprefix("worktree ")
        if Path(location).resolve() == root.resolve():
            fields = [value for value in fields if not value.startswith("HEAD ")]
        listing.append(fields)
    # Linked operations are read-only retained context, not a global write claim.
    # A detached rebase is observed without entering or modifying that worktree.
    _, common = identity(root)
    pending = []
    for admin in (common / "worktrees").glob("*"):
        for name in ("rebase-merge", "rebase-apply", "MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "sequencer"):
            if (admin / name).exists():
                pending.append(str(admin / name))
    return {"branch": branch, "tip": exact[0][1] if exact else None,
            "registered_worktrees": listing, "in_progress_operations": pending,
            "disposition": "READ_ONLY_RETAINED", "mutation_authorized": False,
            "instruction": "Inspect the immutable tip with git show from primary; do not blindly cherry-pick, archive, unregister, or reset."}

def _area(root: Path) -> Path:
    _, common = identity(root)
    return common / "project-watchdog-primary"

def readonly_preflight(root: Path, targets: list[str]) -> dict[str, Any]:
    root, common = identity(root)
    pending_markers = markers(root)
    if pending_markers:
        raise Refusal("primary Git operation in progress; retain it: " + str(pending_markers))
    return {"ready": True, "worktree": str(root), "git_common_dir": str(common),
            "branch": "main", "scope": targets, "reasons": []}


def current() -> Operation:
    if _CURRENT is None:
        raise Refusal("operation requires canonical primary reservation")
    return _CURRENT


def checkpoint(phase: str, **fields: Any) -> None:
    global _CURRENT
    record = current()
    payload = encoded(record)
    payload.update(fields, phase=phase)
    record = Operation.model_validate(payload)
    write_json(Path(record.journal), encoded(record))
    _CURRENT = record


def inherited_fds() -> tuple[int, ...]:
    return _FD


def _close_fds(fds: tuple[int, ...] | None) -> None:
    for fd in fds or ():
        try:
            os.close(fd)
        except OSError:
            pass


def _try_lock_file(path: Path) -> int | None:
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except BlockingIOError:
        os.close(fd)
        return None


def _global_lock(root: Path) -> tuple[int, ...] | None:
    area = _area(root)
    area.mkdir(parents=True, exist_ok=True)
    fd = _try_lock_file(area / "execution.flock")
    return (fd,) if fd is not None else None


def _metadata_lock(root: Path) -> int | None:
    area = _area(root)
    area.mkdir(parents=True, exist_ok=True)
    return _try_lock_file(area / "metadata.flock")


def _target_lock_name(target: str) -> str:
    return "target-" + hashlib.sha256(target.encode()).hexdigest() + ".flock"


def _scoped_dir(root: Path) -> Path:
    path = _area(root) / "scoped-locks"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _active_scoped_reservations(root: Path) -> list[dict[str, Any]]:
    scoped = _scoped_dir(root)
    active: list[dict[str, Any]] = []
    for record_path in sorted(scoped.glob("reservation-*.json")):
        try:
            raw = load_json(record_path)
            targets = safe_targets(raw.get("targets") or [])
            lock_name = str(raw.get("reservation_lock") or "")
            if "/" in lock_name or not lock_name.endswith(".flock"):
                raise ValueError("invalid scoped reservation lock name")
            lock_path = scoped / lock_name
            probe = _try_lock_file(lock_path)
            if probe is None:
                active.append({"record": str(record_path), "targets": targets})
                continue
            os.close(probe)
            record_path.unlink(missing_ok=True)
            for name in raw.get("target_locks") or []:
                if isinstance(name, str) and "/" not in name:
                    (scoped / name).unlink(missing_ok=True)
            lock_path.unlink(missing_ok=True)
        except (OSError, RuntimeError, ValueError, TypeError) as exc:
            active.append({"record": str(record_path), "targets": [], "invalid": str(exc)})
    return active


def _scoped_lock(root: Path, targets: list[str]) -> tuple[int, ...] | None:
    from .registry import targets_are_blocked
    targets = safe_targets(targets)
    meta_fd = _metadata_lock(root)
    if meta_fd is None:
        return None
    scoped = _scoped_dir(root)
    held: list[int] = []
    try:
        wanted = set(targets)
        for active in _active_scoped_reservations(root):
            if active.get("invalid") or targets_are_blocked(wanted, set(active["targets"])):
                return None
        reservation_id = uuid.uuid4().hex
        reservation_lock = f"reservation-{reservation_id}.flock"
        reservation_fd = _try_lock_file(scoped / reservation_lock)
        if reservation_fd is None:
            return None
        held.append(reservation_fd)
        target_locks: list[str] = []
        for target in sorted(targets):
            name = _target_lock_name(target)
            fd = _try_lock_file(scoped / name)
            if fd is None:
                _close_fds(tuple(held))
                return None
            held.append(fd)
            target_locks.append(name)
        write_json(scoped / f"reservation-{reservation_id}.json", {
            "schema": "agent_skills.project_watchdog.scoped_primary_reservation.v1",
            "targets": targets,
            "reservation_lock": reservation_lock,
            "target_locks": target_locks,
            "pid": os.getpid(),
            "created_at": time.time(),
            "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        })
        return tuple(held)
    finally:
        os.close(meta_fd)


def _lock(root: Path, targets: list[str] | set[str] | None = None) -> tuple[int, ...] | None:
    if targets is None:
        return _global_lock(root)
    return _scoped_lock(root, safe_targets(list(targets)))


def _global_writer_active(root: Path) -> bool:
    path = _area(root) / "execution.flock"
    if not path.exists():
        return False
    fd = os.open(path, os.O_RDWR)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return False
        except BlockingIOError:
            return True
    finally:
        os.close(fd)


def writer_active(root: Path) -> bool:
    return bool(_active_scoped_reservations(root))


def queue_order(root: Path, issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    path = _area(root) / "queue-v2.json"
    queue = QueueState.model_validate(load_json(path)) if path.exists() else QueueState()
    return sorted(issues, key=lambda i: (queue.attempts.get(str(i.get("number")), 0),
                                        str(i.get("createdAt") or ""), str(i.get("number"))))


def _attempt(root: Path, number: int) -> None:
    fd = _metadata_lock(root)
    if fd is None:
        raise Refusal("primary metadata reservation is locked")
    try:
        path = _area(root) / "queue-v2.json"
        queue = QueueState.model_validate(load_json(path)) if path.exists() else QueueState()
        queue.sequence += 1
        queue.attempts[str(number)] = queue.sequence
        write_json(path, encoded(QueueState.model_validate(encoded(queue))))
    finally:
        os.close(fd)


def observations(root: Path) -> dict[str, Any]:
    """Unknown records quarantine their issue, not the entire monorepo."""
    operations, invalid = [], []
    for path in sorted((_area(root) / "operations").glob("*.json")):
        try:
            record = Operation.model_validate(load_json(path))
            if (Path(record.root).resolve() != root.resolve() or
                    Path(record.journal).resolve() != path.resolve() or
                    path.name.split("-", 1)[0] != str(record.issue_number) or
                    safe_targets(record.targets) != record.targets):
                raise ValueError("operation is not bound to this canonical root/journal/issue")
            if record.phase not in _TERMINAL:
                operations.append(encoded(record))
        except (OSError, ValueError) as exc:
            number = path.name.split("-", 1)[0]
            invalid.append({"journal": str(path), "issue_number": int(number) if number.isdigit() else None,
                            "error": str(exc), "disposition": "invalid_operation_quarantined"})
    scoped_reservations = _active_scoped_reservations(root)
    scoped_targets = sorted({target for row in scoped_reservations for target in row.get("targets", [])})
    return {"writer_active": bool(scoped_reservations), "global_writer_active": _global_writer_active(root),
            "writer_targets": scoped_targets, "writer_reservations": scoped_reservations,
            "operations": operations, "invalid_operations": invalid,
            "recovery_command": recovery_command(root)}


def pending(root: Path) -> dict[str, Any] | None:
    observed = observations(root)
    return observed if observed["writer_active"] or observed["operations"] or observed["invalid_operations"] else None


def recovery_command(root: Path) -> str:
    # Real, implemented entrypoint. It never launches replacement Ask/Tau work.
    return shlex.join([config.resolve_uv_bin(), "run", "--project", str(config.SKILL_DIR),
                       "python", str(Path(__file__).with_name("recover_primary.py")),
                       "--root", str(root), "--apply"])


def reattach_command(root: Path, journal: Path) -> str:
    return shlex.join([config.resolve_uv_bin(), "run", "--project", str(config.SKILL_DIR),
                       "python", str(Path(__file__).with_name("recover_primary.py")),
                       "--root", str(root), "--reattach-journal", str(journal), "--apply"])


def _project_command_spec_run(ask_run_dir: Path) -> Path:
    candidates = []
    roots = [ask_run_dir]
    if ask_run_dir.is_dir():
        roots.extend(path for path in ask_run_dir.iterdir() if path.is_dir())
    for root in roots:
        if ((root / "dag.json").is_file()
                and (root / "command-specs").is_dir()
                and (root / "agents").is_dir()
                and (root / "tau-receipts" / "dag-run.sqlite3").is_file()):
            candidates.append(root)
    if len(candidates) != 1:
        raise Refusal(f"expected exactly one command-spec Ask run under {ask_run_dir}, found {len(candidates)}")
    return candidates[0]


def reattach_and_resume(root: Path, journal: Path, *, apply: bool, timeout_s: int = 1200) -> dict[str, Any]:
    """Resume one retryable operation only after reacquiring its native lease.

    This is the watchdog-owned same-run recovery seam: it consumes a retained
    retryable journal, reacquires a fresh native ticket lease, sets the journal
    path in Ask's environment, and lets Ask/Tau resume only the unsettled nodes.
    """
    global _CURRENT, _FD
    root, _ = identity(root)
    journal = journal.expanduser().resolve(strict=True)
    if not apply:
        return {"ok": True, "status": "DRY_RUN", "command": reattach_command(root, journal)}
    fd = None
    try:
        area = _area(root) / "operations"
        if journal.parent.resolve() != area.resolve():
            raise Refusal("reattach journal is not in this primary operation area")
        record = Operation.model_validate(load_json(journal))
        if Path(record.root).resolve() != root or Path(record.journal).resolve() != journal:
            raise Refusal("reattach journal is not bound to this primary checkout")
        if record.phase != "retryable" or not record.tau_settled or not record.lease_released or record.closure is not None:
            raise Refusal("reattach requires retryable settled operation with released lease and no closure")
        if not record.ask_run_dir:
            raise Refusal("reattach requires retained Ask run directory")
        targets = safe_targets(record.targets)
        observed = observations(root)
        if observed["invalid_operations"]:
            raise Refusal("primary has invalid retained operations; run lifecycle recovery first")
        from .registry import targets_are_blocked
        for prior in observed["operations"]:
            if prior["issue_number"] == record.issue_number or targets_are_blocked(set(targets), set(prior["targets"])):
                raise Refusal("retained operation overlaps this reattach target; run lifecycle recovery first")
        fd = _lock(root, targets)
        if fd is None:
            return {"ok": True, "status": "SKIPPED", "stop_reason": "primary_scoped_execution_locked"}
        _FD = fd
        _CURRENT = record
        result: dict[str, Any] = {"ok": False, "status": "RUNNING", "commands": [], "artifacts": []}
        from . import handlers, native_ticket, resume_state
        run_dir = _project_command_spec_run(Path(record.ask_run_dir))
        prior = handlers.inspect_tau_stream(Path(record.ask_run_dir))
        prior_journal = None
        if isinstance(prior.get("resume_journal"), str) and prior.get("resume_journal"):
            prior_journal = Path(prior["resume_journal"]).expanduser().resolve()
        project_path = Path(record.receipt_dir) / "dispatch-project.json"
        project = load_json(project_path) if project_path.is_file() else {}
        creator, reviewer = config.repair_seats(project)
        _, reviewer_handler = handlers.repair_execution_handlers(creator, reviewer)
        recovery_text = "\n".join(str(x or "") for x in [record.recovery, (record.result or {}).get("summary")])
        rerun_reviewer = prior.get("terminal") is True and any(token in recovery_text for token in (
            "VerificationPlan", "verification plan", "review must supply exactly one",
            "proof plan does not cover", "native verification plan omits",
            "independent proof gate failed", "predates this dispatch",
        ))
        finalize_only = (prior.get("terminal") is True
            and prior.get("terminal_status") in {"PASS", "COMPLETED"}
            and prior_journal == journal
            and prior.get("resume_lease_agent") == record.lease_agent
            and not rerun_reviewer)
        native_ticket.acquire(record, result, checkpoint)
        record = current()
        if finalize_only:
            write_json(Path(record.receipt_dir) / "retained-resume-finalization.json", {
                "schema": "agent_skills.project_watchdog.resume_finalization.v1",
                "admitted_generation": prior["resume_generation"],
                "admitted_journal": prior["resume_journal"],
                "admitted_lease_agent": prior["resume_lease_agent"],
                "native_result": prior["terminal_source"],
                "new_lease_event_id": record.lease_event.id,
                "new_lease_agent": record.lease_agent,
                "provider_dispatched": False,
            })
            checkpoint("settled", tau_settled=True)
            return _finalize_reattached_operation()
        generation_path = resume_state.begin(record, run_dir)
        command = [str(config.ask_run_sh()), "runs", "resume", str(run_dir), "--execute", "--json"]
        checkpoint("running", ask_run_dir=record.ask_run_dir, dispatched_at=time.time())
        old_env = os.environ.get("PROJECT_WATCHDOG_OPERATION_JOURNAL")
        old_force = os.environ.get("PROJECT_WATCHDOG_RESUME_RERUN_NODES")
        os.environ["PROJECT_WATCHDOG_OPERATION_JOURNAL"] = str(journal)
        if rerun_reviewer:
            os.environ["PROJECT_WATCHDOG_RESUME_RERUN_NODES"] = f"{handlers.repair_node_id(reviewer_handler)},join"
        try:
            row = handlers.run_ask_tau_dag_with_stream_monitor(
                command, cwd=root, timeout_s=timeout_s, ask_run_dir=Path(record.ask_run_dir),
                monitor_path=Path(record.receipt_dir) / "watchdog-reattach-monitor.json",
            )
        finally:
            if old_env is None:
                os.environ.pop("PROJECT_WATCHDOG_OPERATION_JOURNAL", None)
            else:
                os.environ["PROJECT_WATCHDOG_OPERATION_JOURNAL"] = old_env
            if old_force is None:
                os.environ.pop("PROJECT_WATCHDOG_RESUME_RERUN_NODES", None)
            else:
                os.environ["PROJECT_WATCHDOG_RESUME_RERUN_NODES"] = old_force
        result["commands"].append(row)
        result["artifacts"].append(str(run_dir))
        write_json(Path(record.receipt_dir) / "watchdog-reattach-resume-command.json", row)
        resume_state.complete(generation_path, row)
        stream = handlers.inspect_tau_stream(Path(record.ask_run_dir))
        write_json(Path(record.receipt_dir) / "watchdog-reattach-stream.json", stream)
        if stream.get("invocation_failed"):
            # The failed invocation did not change the native store/prep. It is
            # not the previous run's terminal state and cannot authorize closure.
            result.update(ok=False, status="NEEDS_ATTENTION",
                          summary="Ask resume invocation failed before native state changed",
                          resume_control=stream.get("resume_control"),
                          authorized_agent_next_steps=[reattach_command(root, journal)])
            checkpoint("releasing", result=result)
            if _finish_release(current()):
                checkpoint("retryable", lease_released=True, result=result)
            write_json(Path(current().result_path), result)
            return result
        if not stream.get("terminal"):
            result.update(ok=False, status="NEEDS_ATTENTION", summary=stream.get("reason"),
                          resume_observation=stream,
                          authorized_agent_next_steps=[recovery_command(root)])
            checkpoint("uncertain", result=result)
            return result
        checkpoint("settled", tau_settled=True)
        return _finalize_reattached_operation()
    except (RuntimeError, ValueError, OSError) as exc:
        active = _CURRENT
        if active is not None:
            result = failure({"project_id": active.project_id, "repo": active.repo, "worktree": active.root},
                             {"number": active.issue_number, "watchdog_action": active.action}, str(exc),
                             human=getattr(exc, "human", False))
            checkpoint("retryable" if active.lease_released else active.phase, result=result, recovery=str(exc))
            return result
        raise
    finally:
        _CURRENT, _FD = None, ()
        _close_fds(fd)


def _finalize_reattached_operation() -> dict[str, Any]:
    from . import handlers, native_ticket
    try:
        result = handlers.finish_primary_operation(current())
        checkpoint(current().phase, result=result)
    except (RuntimeError, ValueError, OSError) as exc:
        active = current()
        result = failure({"project_id": active.project_id, "repo": active.repo, "worktree": active.root},
                         {"number": active.issue_number, "watchdog_action": active.action}, str(exc))
        checkpoint("releasing", result=result, recovery=str(exc))
    record = current()
    if record.closure is not None:
        checkpoint("closing")
        result = native_ticket.close(current())
        checkpoint("releasing", result=result)
    elif record.phase in {"leased", "settled"}:
        checkpoint("releasing", result=result)
    if current().phase == "releasing":
        if _finish_release(current()):
            write_json(Path(current().result_path), result)
            checkpoint("finished" if result.get("ok") else "retryable", lease_released=True, result=result)
        else:
            result = _release_pending_result(current(), result)
    return result


def failure(project: dict[str, Any], issue: dict[str, Any], message: str,
            *, human: bool = False) -> dict[str, Any]:
    from .receipt_schema import Triage, _classify_with_triage_error
    raw_triage = _classify_with_triage_error(message)
    classification = {}
    try:
        classification["triage"] = Triage.model_validate(raw_triage).model_dump()
    except ValueError as exc:
        classification["classification_error"] = str(exc)
        classification["classifier_response"] = raw_triage
    from .registry import project_worktree
    command = recovery_command(project_worktree(project))
    action = issue.get("watchdog_action", "ticket_repair")
    labels = [str(label.get("name")) for label in issue.get("labels", []) if isinstance(label, dict) and label.get("name")]
    return {"project_id": project["project_id"], "repo": project["repo"],
            "issue_number": int(issue["number"]), "action": action,
            "ok": False, "status": "NEEDS_ATTENTION", "summary": message,
            "requires_human_input": human, **classification,
            "authorized_agent_next_steps": [command], "commands": [], "artifacts": [],
            "workflow_phases": [
                {"id": "issue_observed", "agent": "GitHub issue", "skill": "ticket", "executor": "issue scan",
                 "status": "OBSERVED", "depends_on": [], "details": [f"issue=#{int(issue['number'])}", f"labels={','.join(labels) or 'none'}"]},
                {"id": "route_classified", "agent": "project-watchdog router", "skill": "project-watchdog",
                 "executor": "registry.classify_issue_with_reason", "status": "OBSERVED", "depends_on": ["issue_observed"],
                 "details": [f"action={action}", "eligible_next_tick=agent-work and no hold labels"]},
                {"id": "failure_triaged", "agent": "triage-error classifier", "skill": "triage-error",
                 "executor": classification.get("triage", {}).get("code", "classification_error"), "status": "NEEDS_ATTENTION",
                 "depends_on": ["route_classified"], "details": [message[:240]]},
                {"id": "ops_discord_alert", "agent": "ops-discord", "skill": "ops-discord notify",
                 "executor": "watchdog alert at core.finish", "status": "PENDING", "depends_on": ["failure_triaged"],
                 "details": ["ops-discord alerts only for explicit human-input BLOCKED, NEEDS_ATTENTION, or idle_streak_exceeded receipts; machine-actionable failures and COMPLETED receipts stay agent-owned"]},
            ]}


def _finish_release(record: Operation) -> bool:
    from . import native_ticket
    if record.lease_event is None:
        return record.phase == "reserved"  # An ambiguous acquisition is not safe to release.
    return native_ticket.release(record)


def _release_pending_result(record: Operation, result: dict[str, Any]) -> dict[str, Any]:
    pending = dict(result)
    pending.update(ok=False, status="NEEDS_ATTENTION",
                   release_pending=True, requires_human_input=False,
                   summary=("ticket close read back, but owned native release is not confirmed"
                            if result.get("ticket_closed")
                            else "owned native release is not confirmed"))
    pending.setdefault("authorized_agent_next_steps", [recovery_command(Path(record.root))])
    checkpoint("releasing", result=pending)
    write_json(Path(record.result_path), pending)
    return pending


def reconcile(root: Path) -> dict[str, Any] | None:
    """Advance retained native closure/release; inspect the SAME Tau run only.

    No PID/TTL/reboot converts unknown remote execution to settlement. A missing
    native terminal record retains THIS target's claim and a runnable recovery
    command. Other target scopes can proceed under independent scoped locks.
    """
    global _CURRENT, _FD
    root, _ = identity(root)
    observed = observations(root)
    if observed["invalid_operations"]:
        return observed
    for raw in observed["operations"]:
        record = Operation.model_validate(raw)
        fd = _lock(root, record.targets)
        if fd is None:
            return observations(root)
        _CURRENT, _FD = record, fd
        try:
            from . import handlers, native_ticket
            if record.phase == "reserved":
                checkpoint("retryable", recovery="no external effect was started")
                continue
            if record.phase == "acquiring_lease":
                issue = github.get_issue(record.repo, record.issue_number)
                event = native_ticket.lease_event(record.repo, record.issue_number)
                if native_ticket.NATIVE_LABEL not in native_ticket.labels(issue):
                    checkpoint("retryable", recovery="acquisition absent; no worker launched")
                    continue
                owns_marker = any(f"\nagent: {record.lease_agent}\n" in (c.get("body") or "")
                                  for c in native_ticket.comments(record.repo, record.issue_number))
                if (event and event != record.lease_before_event and event.actor == record.lease_actor
                        and event.event == "labeled" and owns_marker):
                    checkpoint("leased", lease_event=event.model_dump())
                else:
                    continue  # Unknown/foreign generation is scoped, never cleared.
            record = current()
            if record.phase in {"launching", "running", "uncertain"}:
                if not record.ask_run_dir or record.dispatched_at is None:
                    continue
                stream = handlers.inspect_tau_stream(Path(record.ask_run_dir))
                if stream.get("invocation_failed"):
                    result = failure(
                        {"project_id": record.project_id, "repo": record.repo, "worktree": record.root},
                        {"number": record.issue_number, "watchdog_action": record.action},
                        "Ask resume invocation failed before native state changed",
                    )
                    result.update(resume_control=stream.get("resume_control"),
                                  commands=[stream["command_receipt"]])
                    checkpoint("releasing", result=result)
                elif not stream.get("terminal"):
                    continue
                else:
                    # Only current, native run-level settlement authorizes finalization.
                    checkpoint("settled", tau_settled=True)
            record = current()
            if record.phase == "settled" and record.closure is None:
                result = handlers.finish_primary_operation(record)
                checkpoint(current().phase, result=result)
            record = current()
            if record.closure is not None:
                checkpoint("closing")
                result = native_ticket.close(current())
                checkpoint("releasing", result=result)
            elif record.phase in {"leased", "settled"}:
                checkpoint("releasing")
            record = current()
            if record.phase == "releasing" and _finish_release(record):
                result = record.result or {"ok": False, "status": "NEEDS_ATTENTION",
                                           "summary": "settled retained attempt released; retry eligible"}
                write_json(Path(record.result_path), result)
                checkpoint("finished" if result.get("ok") else "retryable", lease_released=True,
                           result=result)
            elif record.phase == "releasing":
                result = _release_pending_result(record, record.result or {
                    "ok": False, "status": "NEEDS_ATTENTION",
                    "summary": "owned native release is not confirmed"})
        except (RuntimeError, ValueError, OSError) as exc:
            active = current()
            if active.tau_settled and active.closure is None:
                # A failed review/proof after native settlement is retryable work,
                # not an eternal settled-but-unclosable journal.
                result = failure({"project_id": active.project_id, "repo": active.repo,
                    "worktree": active.root}, {"number": active.issue_number,
                    "watchdog_action": active.action}, str(exc))
                checkpoint("releasing", result=result, recovery=str(exc))
                try:
                    if _finish_release(current()):
                        write_json(Path(active.result_path), result)
                        checkpoint("retryable", lease_released=True)
                except (RuntimeError, ValueError, OSError):
                    pass  # The owned release outbox remains executable on next recovery.
            else:
                checkpoint(active.phase, recovery=str(exc))
        finally:
            _CURRENT, _FD = None, ()
            _close_fds(fd)
    remaining = observations(root)
    return remaining if (remaining["writer_active"] or remaining["operations"] or remaining["invalid_operations"]) else None


def dispatch(run_id: str, receipt_dir: Path, project: dict[str, Any], issue: dict[str, Any],
             operation: Callable[..., dict[str, Any]], *, apply: bool) -> dict[str, Any]:
    global _CURRENT, _FD
    from .registry import project_worktree
    root = project_worktree(project)
    if not apply:
        try:
            return operation(run_id, receipt_dir, project, issue, apply=False)
        except (RuntimeError, ValueError, OSError) as exc:
            return failure(project, issue, str(exc), human=getattr(exc, "human", False))
    fd = None
    try:
        targets = safe_targets(issue.get("watchdog_targets") or __import__(
            __package__ + ".registry", fromlist=["issue_targets"]).issue_targets(issue))
        readonly_preflight(root, targets)
        assert_repository(root, project["repo"])
        fd = _lock(root, targets)
        if fd is None:
            return {"project_id": project["project_id"], "repo": project["repo"],
                    "issue_number": issue["number"], "action": issue.get("watchdog_action"),
                    "ok": True, "status": "SKIPPED", "stop_reason": "primary_scoped_execution_locked",
                    "commands": [], "artifacts": []}
        observed = observations(root)
        from .registry import targets_are_blocked
        for prior in observed["operations"]:
            if prior["issue_number"] == issue["number"] or targets_are_blocked(set(targets), set(prior["targets"])):
                raise Refusal("retained operation overlaps this ticket; run " + recovery_command(root))
        if any(row["issue_number"] == issue["number"] for row in observed["invalid_operations"]):
            raise Refusal("this ticket has an invalid operation journal; preserve and inspect it")
        _attempt(root, int(issue["number"]))
        token = uuid.uuid4().hex
        journal = _area(root) / "operations" / f"{issue['number']}-{token}.json"
        journal.parent.mkdir(parents=True, exist_ok=True)
        output = receipt_dir / f"repair-{issue['number']}-result.json"
        _CURRENT = Operation(phase="reserved", run_id=run_id, repo=project["repo"],
            project_id=project["project_id"], issue_number=int(issue["number"]),
            action=str(issue.get("watchdog_action") or "ticket_repair"), owner_token=token,
            root=str(root.resolve()), journal=str(journal), result_path=str(output),
            receipt_dir=str(receipt_dir), targets=targets, task_sha256=digest((issue.get("body") or "").encode()),
            scheduler_pid=os.getpid(), boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip())
        _FD = fd
        checkpoint("reserved")
        # Retain inputs as evidence; recovery checks the live body's digest before any finalization.
        write_json(receipt_dir / "dispatch-project.json", project)
        write_json(receipt_dir / "dispatch-issue.json", issue)
        pid = os.fork()
    except (RuntimeError, ValueError, OSError) as exc:
        _close_fds(fd)
        _CURRENT, _FD = None, ()
        return failure(project, issue, str(exc), human=getattr(exc, "human", False))
    if pid:
        _close_fds(fd)  # Do not LOCK_UN: the child holds these open-file descriptions.
        _CURRENT, _FD = None, ()
        while True:
            waited, _ = os.waitpid(pid, os.WNOHANG)
            if waited:
                break
            time.sleep(0.25)
        try:
            return load_json(output)
        except (OSError, ValueError) as exc:
            return failure(project, issue, f"retained worker result missing: {exc}; {recovery_command(root)}")
    try:
        os.setsid()
        log_fd = os.open(receipt_dir / "primary-worker.log", os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
        os.dup2(log_fd, 1)
        os.dup2(log_fd, 2)
        os.close(log_fd)
        process_stat = Path(f"/proc/{os.getpid()}/stat").read_text()
        checkpoint("reserved", worker_pid=os.getpid(), worker_start_ticks=process_stat[process_stat.rfind(")") + 2:].split()[19])
        try:
            result = operation(run_id, receipt_dir, project, issue, apply=True)
        except BaseException as exc:
            result = failure(project, issue, f"{type(exc).__name__}: {exc}", human=getattr(exc, "human", False))
        record = current()
        if record.closure is not None and not result.get("ticket_closed"):
            checkpoint("closing", result=result)
        elif record.phase == "reserved":
            checkpoint("retryable", result=result)
        elif record.phase in {"leased", "settled", "releasing"} or result.get("ticket_closed"):
            checkpoint("releasing", result=result)
            try:
                if _finish_release(current()):
                    write_json(output, result)
                    checkpoint("finished" if result.get("ok") else "retryable", lease_released=True)
                else:
                    result = _release_pending_result(current(), result)
            except Exception as exc:
                result.update(ok=False, status="NEEDS_ATTENTION", summary=f"native release retry retained: {exc}")
        elif record.phase in {"launching", "running", "uncertain"}:
            result.update(ok=False, status="NEEDS_ATTENTION", requires_human_input=False,
                          authorized_agent_next_steps=[recovery_command(root)])
            checkpoint("uncertain", result=result)
        else:
            checkpoint(record.phase, result=result)
        write_json(output, result)
    finally:
        _close_fds(fd)
        os._exit(0)
