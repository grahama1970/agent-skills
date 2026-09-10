"""Compose the supplied native lifecycle, including its retention audit.

No raw close, TTL-based foreign release, made-up handoff consumer or CI default.
The watchdog strengthens the helper with exact lease-generation and proof readback.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import time
from pathlib import Path
from typing import Any

from . import config, github
from .core import run_cmd, write_json
from .primary_models import LeaseEvent, Operation, VerificationPlan
from .target_content import (
    ContentConflict,
    digest,
    remote_entries,
    remote_pin,
    require_unchanged,
    snapshot,
    versions,
)

NATIVE_LABEL = "maintainer-active"


def helper() -> Path:
    return config.SKILL_DIR.parent / "best-practices-github-ticket/scripts/gh-ticket-tools.sh"


def comments(repo: str, number: int) -> list[dict[str, Any]]:
    result = run_cmd(["gh", "api", "--paginate", "--slurp",
                      f"repos/{repo}/issues/{number}/comments?per_page=100"], timeout_s=120)
    if result.get("exit_code") != 0:
        raise ContentConflict("complete native ticket comment readback failed")
    pages = json.loads(result["stdout"])
    if not isinstance(pages, list) or any(not isinstance(page, list) for page in pages):
        raise ContentConflict("native ticket comments were not complete pages")
    return [item for page in pages for item in page]


def lease_event(repo: str, number: int) -> LeaseEvent | None:
    result = run_cmd(["gh", "api", "--paginate", "--slurp",
                      f"repos/{repo}/issues/{number}/events?per_page=100"], timeout_s=120)
    if result.get("exit_code") != 0:
        raise ContentConflict("lease generation read failed; do not infer an empty lease")
    pages = json.loads(result["stdout"])
    if not isinstance(pages, list) or any(not isinstance(p, list) for p in pages):
        raise ContentConflict("lease event read is incomplete")
    events = [LeaseEvent(id=e["id"], event=e["event"], actor=e["actor"]["login"],
                         created_at=e["created_at"])
              for page in pages for e in page
              if e.get("event") in {"labeled", "unlabeled"} and
              e.get("label", {}).get("name") == NATIVE_LABEL]
    return events[-1] if events else None


def invoke(root: Path, repo: str, action: str, number: int, *args: str) -> dict[str, Any]:
    if os.environ.get("GH_TICKET_SKIP_WORKTREE_AUDIT") == "1":
        raise ContentConflict("refusing native lifecycle with worktree retention audit bypass enabled")
    return run_cmd([str(helper()), action, str(number), "--repo", repo, *args],
                   cwd=root, timeout_s=180)


def labels(issue: dict[str, Any]) -> set[str]:
    return {label["name"] for label in issue["labels"]}


def assert_mutable(record: Operation, *, closing: bool = False) -> dict[str, Any]:
    from .registry import policy_held
    now = github.get_issue(record.repo, record.issue_number)
    if policy_held(record.repo, record.issue_number) or labels(now) & (
            config.HUMAN_HOLD_LABELS | {"external-owner"}):
        raise ContentConflict("standing/native human hold preserved")
    if now["state"] != "OPEN" and not closing:
        raise ContentConflict("ticket is no longer open")
    return now


def acquire(record: Operation, result: dict[str, Any], checkpoint) -> None:
    now = assert_mutable(record)
    if labels(now) & config.LEASE_LABELS:
        raise ContentConflict("ticket already has a foreign/native lease; no takeover")
    if digest((now.get("body") or "").encode()) != record.task_sha256:
        raise ContentConflict("ticket body changed after route authorization")
    before = lease_event(record.repo, record.issue_number)
    actor_result = run_cmd(["gh", "api", "user", "--jq", ".login"], timeout_s=60)
    if actor_result.get("exit_code") != 0 or not actor_result.get("stdout", "").strip():
        raise ContentConflict("cannot bind authenticated native lease actor")
    agent = "project-watchdog-" + record.owner_token
    checkpoint("acquiring_lease", lease_before_event=before.model_dump() if before else None,
               lease_actor=actor_result["stdout"].strip(), lease_agent=agent,
               lease_released=False)
    command = invoke(Path(record.root), record.repo, "lease", record.issue_number, "--agent", agent)
    result["commands"].append(command)
    event = lease_event(record.repo, record.issue_number)
    now = github.get_issue(record.repo, record.issue_number)
    # The unique native --agent marker is stronger than actor/time alone.
    owned_comment = any(f"\nagent: {agent}\n" in (c.get("body") or "")
                        for c in comments(record.repo, record.issue_number))
    event_owned = (
        event is not None
        and event != before
        and event.event == "labeled"
        and event.actor == actor_result["stdout"].strip()
    )
    if NATIVE_LABEL not in labels(now) or not owned_comment or (not event_owned and event != before):
        raise ContentConflict("native lease mutation is ambiguous; exact acquisition must be reconciled")
    checkpoint("leased", lease_event=event.model_dump() if event else None)


def owns(record: Operation) -> bool:
    now = github.get_issue(record.repo, record.issue_number)
    return (record.lease_event is not None and NATIVE_LABEL in labels(now)
            and lease_event(record.repo, record.issue_number) == record.lease_event)


def _scope_args(paths: list[str]) -> list[str]:
    args: list[str] = []
    for path in paths:
        args.extend(["--scope-path", path])
    return args


def release(record: Operation) -> bool:
    from .registry import policy_held
    if policy_held(record.repo, record.issue_number):
        return False
    now = github.get_issue(record.repo, record.issue_number)
    if NATIVE_LABEL not in labels(now):
        return True  # Observation, NOT a claim to have removed another owner's label.
    if not owns(record):
        return False
    # Holds added while work ran must not be cleared; native release preserves them.
    reason = Path(record.receipt_dir) / "native-release.md"
    body = (f"<!-- watchdog-release:{record.owner_token} -->\n"
            f"Run {record.run_id} has no unsettled authoring authority.\n"
            "Release only this native lease; retain all files, refs and worktrees.\n")
    reason.write_text(body)
    result = invoke(Path(record.root), record.repo, "release", record.issue_number,
                    "--agent", record.lease_agent, "--reason", str(reason),
                    *_scope_args(record.targets))
    write_json(Path(record.receipt_dir) / "native-release-command.json", result)
    now = github.get_issue(record.repo, record.issue_number)
    return result.get("exit_code") == 0 and NATIVE_LABEL not in labels(now)


def _prepare_reusable_output(command: str) -> None:
    """Make fixed-output Battle proof commands repeatable for native verification."""
    try:
        parts = shlex.split(command)
    except ValueError:
        return
    if "skills/battle/run.sh" not in parts or "adaptive-red-blue-lineage-canary" not in parts:
        return
    if "--out" not in parts:
        return
    out_index = parts.index("--out") + 1
    if out_index >= len(parts):
        return
    out = Path(parts[out_index]).expanduser()
    if out.exists():
        backup = out.with_name(f"{out.name}.verify-prev-{int(time.time())}")
        shutil.move(str(out), str(backup))


def _fix_common_jq_precedence(command: str) -> str:
    return re.sub(
        r"\((\.content\.targets\|sort)==(\[[^\]]+\])\|sort\)",
        r"((\1)==(\2|sort))",
        command,
    )


def verify(root: Path, number: int, plan: VerificationPlan, *, timeout_s: int) -> list[dict[str, Any]]:
    """Execute each reviewed proof through ticket verify; process PASS is not closure."""
    results = []
    for raw_command in plan.commands:
        command = _fix_common_jq_precedence(raw_command)
        _prepare_reusable_output(command)
        row = run_cmd([str(config.SKILL_DIR.parent / "ticket/run.sh"), "verify", str(number),
                       "--cmd", command], cwd=root, timeout_s=timeout_s)
        results.append(row)
        from . import primary
        from .core import write_json
        try:
            directory = Path(primary.current().receipt_dir)
        except RuntimeError:
            directory = None
        if directory is not None:
            write_json(directory / "native-verification-commands.json", {"commands": results})
        if row.get("exit_code") != 0:
            raise ContentConflict("native ticket verify failed; ticket remains open")
    return results


def _write_closure_receipt_v2(record: Operation, issue: dict[str, Any], *, helper_result: dict[str, Any] | None,
                              proof_posted: bool, remote_sha: str) -> Path:
    closure = record.closure
    if closure is None:
        raise ContentConflict("closure receipt requires frozen proof")
    path = Path(record.receipt_dir) / "ticket-closure-receipt-v2.json"
    payload = {
        "schema": "agent_skills.ticket_closure_receipt.v2",
        "repo": record.repo,
        "issue": record.issue_number,
        "state": issue.get("state"),
        "state_reason": issue.get("stateReason"),
        "run_id": record.run_id,
        "lease_agent": record.lease_agent,
        "lease_event": record.lease_event.model_dump(mode="json") if record.lease_event else None,
        "tau_settled": record.tau_settled,
        "proof_path": closure.proof_path,
        "proof_sha256": closure.proof_sha256,
        "review_path": closure.review_path,
        "review_sha256": closure.review_sha256,
        "commit": closure.commit,
        "remote_sha": remote_sha,
        "remote_required": closure.remote_required,
        "scope": closure.scope,
        "proof_comment_read_back": proof_posted,
        "helper_exit_code": None if helper_result is None else helper_result.get("exit_code"),
    }
    write_json(path, payload)
    return path


def close(record: Operation) -> dict[str, Any]:
    closure = record.closure
    if closure is None or not record.tau_settled:
        raise ContentConflict("native close requires a settled run and frozen proof")
    root = Path(record.root)
    proof, review = Path(closure.proof_path), Path(closure.review_path)
    if digest(proof.read_bytes()) != closure.proof_sha256 or digest(review.read_bytes()) != closure.review_sha256:
        raise ContentConflict("native proof/review changed after admission")
    now = assert_mutable(record, closing=True)
    posted = any(c.get("body") == proof.read_text() for c in comments(record.repo, record.issue_number))
    if now["state"] == "CLOSED":
        if now.get("stateReason") != "COMPLETED" or not posted:
            raise ContentConflict("foreign/unproved closure observed; do not claim it")
        receipt = _write_closure_receipt_v2(record, now, helper_result=None, proof_posted=posted,
                                           remote_sha=remote_pin(root))
        # Reconcile the already verified historical closure. Later target work
        # does not reopen it or grant authority to restore its older bytes.
        return {"ok": True, "status": "COMPLETED", "ticket_closed": True,
                "summary": "verified completed closure read back", "commands": [],
                "commit": closure.commit, "reconciled": True, "closure_receipt_v2": str(receipt)}
    pin = remote_pin(root)
    require_unchanged(closure.content, snapshot(root, closure.scope, pin))
    if closure.remote_required and remote_entries(root, pin, closure.scope) != versions(closure.content):
        raise ContentConflict("remote target no longer matches verified closure bytes")
    if not owns(record):
        raise ContentConflict("native closure no longer owns the exact lease generation")
    row = invoke(root, record.repo, "close", record.issue_number,
                 "--proof", str(proof), "--review", str(review), "--reason", "completed",
                 *_scope_args(closure.scope))
    # Read back even after a nonzero/lost response: mutation may already have occurred.
    now = github.get_issue(record.repo, record.issue_number)
    posted = any(c.get("body") == proof.read_text() for c in comments(record.repo, record.issue_number))
    if now["state"] != "CLOSED" or now.get("stateReason") != "COMPLETED" or not posted:
        raise ContentConflict("native close not confirmed; durable closure outbox retained")
    receipt = _write_closure_receipt_v2(record, now, helper_result=row, proof_posted=posted, remote_sha=pin)
    return {"ok": True, "status": "COMPLETED", "ticket_closed": True,
            "summary": "native ticket verification and completed closure read back",
            "commands": [row], "commit": closure.commit, "closure_receipt_v2": str(receipt)}
