"""Canonical primary writer reservation and target-scoped native lifecycle recovery.

An actual held flock excludes all cooperating local writers. Historical issue
labels and settled/orphaned journals only reserve their known target scopes.
They are never remote liveness or foreign release authority.
"""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import json
import os
import shlex
import sys
import time
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, Callable
from . import config, github
from .core import load_json, run_cmd, write_json
from .primary_models import Operation, QueueState, encoded
from .target_content import ContentConflict

_CURRENT: Operation | None = None
_FD: int | None = None
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
    return (_FD,) if _FD is not None else ()


def _lock(root: Path) -> int | None:
    area = _area(root)
    area.mkdir(parents=True, exist_ok=True)
    fd = os.open(area / "execution.flock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except BlockingIOError:
        os.close(fd)
        return None


def writer_active(root: Path) -> bool:
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


def queue_order(root: Path, issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    path = _area(root) / "queue-v2.json"
    queue = QueueState.model_validate(load_json(path)) if path.exists() else QueueState()
    return sorted(issues, key=lambda i: (queue.attempts.get(str(i.get("number")), 0),
                                        str(i.get("createdAt") or ""), str(i.get("number"))))


def _attempt(root: Path, number: int) -> None:
    # Called only while holding the canonical execution flock.
    path = _area(root) / "queue-v2.json"
    queue = QueueState.model_validate(load_json(path)) if path.exists() else QueueState()
    queue.sequence += 1
    queue.attempts[str(number)] = queue.sequence
    write_json(path, encoded(QueueState.model_validate(encoded(queue))))


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
    return {"writer_active": writer_active(root), "operations": operations,
            "invalid_operations": invalid,
            "recovery_command": recovery_command(root)}


def pending(root: Path) -> dict[str, Any] | None:
    observed = observations(root)
    return observed if observed["writer_active"] or observed["operations"] or observed["invalid_operations"] else None


def recovery_command(root: Path) -> str:
    # Real, implemented entrypoint. It never launches replacement Ask/Tau work.
    return shlex.join([config.resolve_uv_bin(), "run", "--project", str(config.SKILL_DIR),
                       "python", str(Path(__file__).with_name("recover_primary.py")),
                       "--root", str(root), "--apply"])


def failure(project: dict[str, Any], issue: dict[str, Any], message: str,
            *, human: bool = False) -> dict[str, Any]:
    from .receipt_schema import _classify_with_triage_error, Triage
    raw_triage = _classify_with_triage_error(message)
    classification = {}
    try:
        classification["triage"] = Triage.model_validate(raw_triage).model_dump()
    except ValueError as exc:
        classification["classification_error"] = str(exc)
        classification["classifier_response"] = raw_triage
    from .registry import project_worktree
    command = recovery_command(project_worktree(project))
    return {"project_id": project["project_id"], "repo": project["repo"],
            "issue_number": int(issue["number"]), "action": issue.get("watchdog_action", "ticket_repair"),
            "ok": False, "status": "NEEDS_ATTENTION", "summary": message,
            "requires_human_input": human, **classification,
            "authorized_agent_next_steps": [command], "commands": [], "artifacts": []}


def _finish_release(record: Operation) -> bool:
    from . import native_ticket
    if record.lease_event is None:
        return record.phase == "reserved"  # An ambiguous acquisition is not safe to release.
    return native_ticket.release(record)


def reconcile(root: Path) -> dict[str, Any] | None:
    """Advance retained native closure/release; inspect the SAME Tau run only.

    No PID/TTL/reboot converts unknown remote execution to settlement. A missing
    native terminal record retains THIS target's claim and a runnable recovery
    command. Other scopes can proceed once the actual local reservation is free.
    """
    global _CURRENT, _FD
    fd = _lock(root)
    if fd is None:
        return observations(root)
    _FD = fd
    try:
        for raw in observations(root)["operations"]:
            record = Operation.model_validate(raw)
            _CURRENT = record
            try:
                from . import native_ticket, handlers
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
                    if not stream.get("terminal"):
                        continue
                    # Native run-level settlement, not process disappearance or a node PASS.
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
        remaining = observations(root)
        remaining["writer_active"] = False
        return remaining if remaining["operations"] or remaining["invalid_operations"] else None
    finally:
        _CURRENT, _FD = None, None
        os.close(fd)


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
        fd = _lock(root)
        if fd is None:
            return {"project_id": project["project_id"], "repo": project["repo"],
                    "issue_number": issue["number"], "action": issue.get("watchdog_action"),
                    "ok": True, "status": "SKIPPED", "stop_reason": "primary_execution_locked",
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
        if fd is not None:
            os.close(fd)
        _CURRENT, _FD = None, None
        return failure(project, issue, str(exc), human=getattr(exc, "human", False))
    if pid:
        os.close(fd)  # Do not LOCK_UN: the child holds this open-file description.
        _CURRENT, _FD = None, None
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
                    result.update(ok=False, status="NEEDS_ATTENTION", summary="owned native release not confirmed")
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
        os.close(fd)
        os._exit(0)
