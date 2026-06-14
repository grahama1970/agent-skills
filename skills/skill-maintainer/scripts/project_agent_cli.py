#!/usr/bin/env python3
"""Project-agent wrapper for the skill-maintainer issue cycle."""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
CYCLE = REPO_ROOT / "scripts" / "skill_maintainer_cycle.py"
SCHEDULER_EVENT_LOG = REPO_ROOT / ".artifacts" / "skill-maintainer" / "scheduler-events.jsonl"
CRON_LOG = REPO_ROOT / ".artifacts" / "skill-maintainer" / "cron.log"
CRON_MARKER = "skill-maintainer-scheduler"

TERMINAL_STATUSES = {
    "fixed_with_deterministic_proof",
    "fixed_with_deterministic_proof_webgpt_advisory",
}

AUDIT_STATUSES = {
    "maintainer_ok",
    "maintainer_degraded",
    "maintainer_bug_detected",
    "maintainer_improvement_opportunity",
}


def append_event_log(event_log: Path, line: str) -> None:
    event_log.parent.mkdir(parents=True, exist_ok=True)
    with event_log.open("a", encoding="utf-8") as fh:
        fh.write(f"{line}\n")


def emit(event: str, *, event_log: Path | None = None, **payload: Any) -> str:
    line = json.dumps({"event": event, **payload}, sort_keys=True)
    if event_log is not None:
        append_event_log(event_log, line)
    print(line, flush=True)
    return line


def read_json_file(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                events.append({"event": "invalid_jsonl", "raw": line})
                continue
            events.append(parsed if isinstance(parsed, dict) else {"event": "non_object_jsonl", "value": parsed})
    except FileNotFoundError:
        pass
    return events


def audit_classification(status: str, closure_decision: str, terminal_disposition: str, events: list[dict[str, Any]]) -> str:
    if status in TERMINAL_STATUSES and terminal_disposition == "completed":
        return "maintainer_ok"
    if status.startswith("cycle_") or status.startswith("blocked_invalid_"):
        return "maintainer_bug_detected"
    if closure_decision.startswith("blocked_review") or closure_decision.startswith("blocked_publication"):
        return "maintainer_bug_detected"
    if status.startswith("blocked_") or closure_decision.startswith("blocked"):
        return "maintainer_degraded"
    if any(event.get("event") == "timeout" for event in events):
        return "maintainer_degraded"
    return "maintainer_improvement_opportunity"


def build_post_job_audit(issue_dir: Path, current: dict[str, Any]) -> dict[str, Any]:
    event_log = issue_dir / "drive-events.jsonl"
    events = read_jsonl(event_log)
    status = str(current.get("status") or "")
    closure_decision = str(current.get("closure_decision") or "")
    terminal_disposition = str(current.get("terminal_disposition_status") or "")
    classification = audit_classification(status, closure_decision, terminal_disposition, events)

    evidence_candidates = [
        "drive-events.jsonl",
        "cycle-result.json",
        "repair-response.json",
        "verifier-response.json",
        "review-response.json",
        "ask-webgpt-result.json",
        "publication-result.json",
    ]
    evidence_paths = [name for name in evidence_candidates if (issue_dir / name).exists()]
    findings: list[dict[str, Any]] = []
    if classification != "maintainer_ok":
        findings.append({
            "kind": classification,
            "status": status,
            "closure_decision": closure_decision,
            "terminal_disposition_status": terminal_disposition,
            "message": "skill-maintainer run ended without a clean deterministic terminal disposition",
        })

    source_issue = current.get("issue")
    if source_issue is None:
        cycle = read_json_file(issue_dir / "cycle-result.json", {})
        if isinstance(cycle, dict):
            source_issue = cycle.get("issue")

    return {
        "schema": "skill-maintainer.post-job-audit.v1",
        "source_issue": source_issue,
        "source_artifact_dir": str(issue_dir),
        "classification": classification,
        "findings": findings,
        "event_log": str(event_log),
        "event_count": len(events),
        "evidence_paths": evidence_paths,
        "recommended_action": "file_self_improvement_issue" if classification in {
            "maintainer_bug_detected",
            "maintainer_improvement_opportunity",
        } else "none",
        "self_improvement_issue_url": None,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def file_self_improvement_issue(audit_path: Path, audit: dict[str, Any]) -> dict[str, Any]:
    title = f"skill-maintainer post-job audit: {audit['classification']}"
    source_issue = audit.get("source_issue")
    if source_issue is not None:
        title = f"skill-maintainer post-job audit for issue #{source_issue}: {audit['classification']}"
    body = "\n".join([
        "A required skill-maintainer post-job audit found a maintainer follow-up.",
        "",
        f"Classification: `{audit['classification']}`",
        f"Source issue: `{source_issue}`",
        f"Source artifact dir: `{audit['source_artifact_dir']}`",
        f"Audit artifact: `{audit_path}`",
        "",
        "Findings:",
        "```json",
        json.dumps(audit.get("findings", []), indent=2, sort_keys=True),
        "```",
        "",
        "Acceptance criteria:",
        "- Add or update a deterministic regression test for the maintainer behavior.",
        "- Patch only the scoped maintainer path needed for the finding.",
        "- Preserve post-job audit artifact creation.",
        "- Do not use WebGPT advisory output as deterministic closure proof.",
    ])
    cp = subprocess.run(
        ["gh", "issue", "create", "--title", title, "--body", body],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    result = {
        "status": "created" if cp.returncode == 0 else "failed",
        "returncode": cp.returncode,
        "stdout": cp.stdout.strip(),
        "stderr": cp.stderr.strip(),
        "command": ["gh", "issue", "create", "--title", title, "--body", "<body>"],
    }
    if cp.returncode == 0 and cp.stdout.strip():
        result["issue_url"] = cp.stdout.strip().splitlines()[-1]
    return result


def run_post_job_audit(issue_dir: Path, current: dict[str, Any], *, file_issue: bool = False) -> dict[str, Any]:
    audit_path = issue_dir / "post-job-audit.json"
    audit = build_post_job_audit(issue_dir, current)
    if file_issue and audit["recommended_action"] == "file_self_improvement_issue":
        filing = file_self_improvement_issue(audit_path, audit)
        audit["self_improvement_issue_filing"] = filing
        audit["self_improvement_issue_url"] = filing.get("issue_url")
    write_json(audit_path, audit)
    return audit


def parse_cycle_stdout(stdout: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def run_cycle(args: list[str]) -> dict[str, Any]:
    cp = subprocess.run(
        [sys.executable, str(CYCLE), *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    parsed = parse_cycle_stdout(cp.stdout)
    if cp.returncode != 0:
        if parsed is not None and isinstance(parsed.get("artifact_dir"), str):
            parsed.setdefault("cycle_returncode", cp.returncode)
            parsed.setdefault("cycle_stderr", cp.stderr)
            parsed.setdefault("cycle_cmd", [sys.executable, str(CYCLE), *args])
            return parsed
        return {
            "status": "cycle_command_failed",
            "returncode": cp.returncode,
            "stdout": cp.stdout,
            "stderr": cp.stderr,
            "cmd": [sys.executable, str(CYCLE), *args],
        }
    if parsed is None:
        return {
            "status": "cycle_json_parse_failed",
            "returncode": cp.returncode,
            "stdout": cp.stdout,
            "stderr": cp.stderr,
            "cmd": [sys.executable, str(CYCLE), *args],
        }
    return parsed


def crontab_read() -> tuple[int, str, str]:
    cp = subprocess.run(
        ["crontab", "-l"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if cp.returncode == 0:
        return 0, cp.stdout, cp.stderr
    if cp.returncode == 1 and "no crontab" in cp.stderr.lower():
        return 0, "", cp.stderr
    return cp.returncode, cp.stdout, cp.stderr


def crontab_write(content: str) -> tuple[int, str, str]:
    cp = subprocess.run(
        ["crontab", "-"],
        cwd=REPO_ROOT,
        input=content,
        text=True,
        capture_output=True,
        check=False,
    )
    return cp.returncode, cp.stdout, cp.stderr


def cron_scheduler_command(max_issues: int, run_webgpt: bool, auto_update: bool) -> str:
    runner = REPO_ROOT / "skills" / "skill-maintainer" / "run.sh"
    parts = [
        shlex.quote(str(runner)),
        "cron-tick",
        "--max-issues",
        str(max_issues),
    ]
    if run_webgpt:
        parts.append("--run-webgpt")
    else:
        parts.append("--no-run-webgpt")
    if auto_update:
        parts.append("--auto-update")
    else:
        parts.append("--no-auto-update")
    return (
        f"cd {shlex.quote(str(REPO_ROOT))} && "
        f"{' '.join(parts)} >> {shlex.quote(str(CRON_LOG))} 2>&1"
    )


def cron_line(schedule: str, max_issues: int, run_webgpt: bool, auto_update: bool) -> str:
    return f"{schedule} {cron_scheduler_command(max_issues, run_webgpt, auto_update)} # {CRON_MARKER}"


def git_output(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def worktree_clean() -> tuple[bool, str]:
    cp = git_output(["status", "--porcelain"])
    if cp.returncode != 0:
        return False, cp.stderr.strip()
    status = cp.stdout.strip()
    return status == "", status


def cron_auto_update(branch: str) -> dict[str, object]:
    clean, status = worktree_clean()
    if not clean:
        return {
            "status": "dirty_worktree",
            "branch": branch,
            "worktree_status": status,
        }
    fetch = git_output(["fetch", "--prune", "origin", branch])
    if fetch.returncode != 0:
        return {
            "status": "fetch_failed",
            "branch": branch,
            "returncode": fetch.returncode,
            "stdout": fetch.stdout,
            "stderr": fetch.stderr,
        }
    checkout = git_output(["checkout", "--detach", f"origin/{branch}"])
    if checkout.returncode != 0:
        return {
            "status": "checkout_failed",
            "branch": branch,
            "returncode": checkout.returncode,
            "stdout": checkout.stdout,
            "stderr": checkout.stderr,
        }
    head = git_output(["rev-parse", "HEAD"])
    return {
        "status": "updated",
        "branch": branch,
        "head": head.stdout.strip() if head.returncode == 0 else None,
    }


def strip_managed_cron(content: str) -> tuple[str, int]:
    kept: list[str] = []
    removed = 0
    for line in content.splitlines():
        if CRON_MARKER in line:
            removed += 1
            continue
        kept.append(line)
    return "\n".join(kept).rstrip(), removed


def command_install_cron(args: argparse.Namespace) -> int:
    if args.interval_minutes < 1 or args.interval_minutes > 59:
        raise SystemExit("--interval-minutes must be between 1 and 59")
    if args.max_issues < 1:
        raise SystemExit("--max-issues must be at least 1")
    schedule = args.schedule or f"*/{args.interval_minutes} * * * *"
    line = cron_line(schedule, args.max_issues, args.run_webgpt, args.auto_update)
    read_code, existing, read_stderr = crontab_read()
    if read_code != 0:
        print(json.dumps({
            "status": "crontab_read_failed",
            "returncode": read_code,
            "stderr": read_stderr,
        }, indent=2, sort_keys=True))
        return 2
    stripped, removed = strip_managed_cron(existing)
    new_content = f"{stripped}\n{line}\n" if stripped else f"{line}\n"
    payload = {
        "status": "dry_run" if args.dry_run else "installed",
        "marker": CRON_MARKER,
        "line": line,
        "removed_existing": removed,
        "event_log": str(SCHEDULER_EVENT_LOG),
        "cron_log": str(CRON_LOG),
        "auto_update": args.auto_update,
    }
    if not args.dry_run:
        write_code, stdout, stderr = crontab_write(new_content)
        payload.update({"returncode": write_code, "stdout": stdout, "stderr": stderr})
        if write_code != 0:
            payload["status"] = "crontab_write_failed"
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 2
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def command_cron_tick(args: argparse.Namespace) -> int:
    if args.auto_update:
        update = cron_auto_update(args.branch)
        print(json.dumps({
            "event": "cron_auto_update",
            **update,
        }, sort_keys=True))
        if update["status"] != "updated":
            return 2
    return command_scheduler(args)


def command_remove_cron(args: argparse.Namespace) -> int:
    read_code, existing, read_stderr = crontab_read()
    if read_code != 0:
        print(json.dumps({
            "status": "crontab_read_failed",
            "returncode": read_code,
            "stderr": read_stderr,
        }, indent=2, sort_keys=True))
        return 2
    stripped, removed = strip_managed_cron(existing)
    payload = {
        "status": "dry_run" if args.dry_run else "removed",
        "marker": CRON_MARKER,
        "removed_existing": removed,
    }
    if not args.dry_run:
        write_code, stdout, stderr = crontab_write(f"{stripped}\n" if stripped else "")
        payload.update({"returncode": write_code, "stdout": stdout, "stderr": stderr})
        if write_code != 0:
            payload["status"] = "crontab_write_failed"
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 2
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def command_cron_status(args: argparse.Namespace) -> int:
    read_code, existing, read_stderr = crontab_read()
    if read_code != 0:
        print(json.dumps({
            "status": "crontab_read_failed",
            "returncode": read_code,
            "stderr": read_stderr,
        }, indent=2, sort_keys=True))
        return 2
    lines = [line for line in existing.splitlines() if CRON_MARKER in line]
    print(json.dumps({
        "status": "installed" if lines else "not_installed",
        "marker": CRON_MARKER,
        "lines": lines,
    }, indent=2, sort_keys=True))
    return 0


def status_for(issue_dir: Path) -> dict[str, Any]:
    return run_cycle(["--status-issue-dir", str(issue_dir)])


def artifact_dir_from(result: dict[str, Any]) -> Path:
    artifact_dir = result.get("artifact_dir")
    if not isinstance(artifact_dir, str) or not artifact_dir:
        raise SystemExit(f"cycle result did not include artifact_dir: {json.dumps(result, indent=2)}")
    return Path(artifact_dir)


def is_terminal(status: dict[str, Any]) -> bool:
    state = str(status.get("status") or "")
    terminal_disposition = str(status.get("terminal_disposition_status") or "")
    if state in TERMINAL_STATUSES and terminal_disposition == "completed":
        return True
    if state.startswith("blocked_invalid_review_receipt:"):
        return False
    if state.startswith("blocked_") or state.startswith("blocked"):
        return True
    if str(status.get("closure_decision") or "").startswith("blocked"):
        return True
    return False


def step(issue_dir: Path, *, run_webgpt: bool) -> dict[str, Any]:
    status = status_for(issue_dir)
    phase = status.get("phase")
    receipt_overall = ((status.get("receipt_gate") or {}).get("overall"))
    if run_webgpt and (phase == "webgpt_external_review" or receipt_overall == "pass"):
        args = ["--continue-issue-dir", str(issue_dir), "--run-webgpt"]
    else:
        args = ["--continue-issue-dir", str(issue_dir), "--dispatch-subagents"]
        if run_webgpt:
            args.append("--run-webgpt")
    return run_cycle(args)


def command_start(args: argparse.Namespace) -> int:
    result = run_cycle(["--issue", str(args.issue), "--dispatch-subagents"])
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not str(result.get("status", "")).startswith("cycle_") else 2


def command_status(args: argparse.Namespace) -> int:
    result = status_for(Path(args.artifact_dir))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def command_step(args: argparse.Namespace) -> int:
    result = step(Path(args.artifact_dir), run_webgpt=args.run_webgpt)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not str(result.get("status", "")).startswith("cycle_") else 2


def command_scheduler(args: argparse.Namespace) -> int:
    line = emit(
        "scheduler_tick",
        event_log=SCHEDULER_EVENT_LOG,
        max_issues=args.max_issues,
        run_webgpt=args.run_webgpt,
        event_log_path=str(SCHEDULER_EVENT_LOG),
    )
    if args.issue is not None:
        cycle_args = ["--issue", str(args.issue), "--dispatch-subagents"]
    else:
        cycle_args = ["--max-issues", str(args.max_issues), "--dispatch-subagents"]
    if args.run_webgpt:
        cycle_args.append("--run-webgpt")
    if args.github_dry_run:
        cycle_args.append("--github-dry-run")
    result = run_cycle(cycle_args)
    emit(
        "scheduler_result",
        event_log=SCHEDULER_EVENT_LOG,
        status=result.get("status"),
        artifact_dir=result.get("artifact_dir"),
        issue=result.get("issue"),
        closure_decision=result.get("closure_decision"),
        prior_event=line,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if str(result.get("status", "")).startswith("cycle_") else 0


def command_drive(args: argparse.Namespace) -> int:
    deadline = time.monotonic() + args.timeout_seconds
    if args.artifact_dir:
        issue_dir = Path(args.artifact_dir).expanduser().resolve()
        event_log = issue_dir / "drive-events.jsonl"
        emit("resume", event_log=event_log, artifact_dir=str(issue_dir), event_log_path=str(event_log))
    else:
        if args.issue is None:
            raise SystemExit("drive requires --issue or --artifact-dir")
        start = run_cycle(["--issue", str(args.issue), "--dispatch-subagents"])
        start_line = emit(
            "start",
            status=start.get("status"),
            artifact_dir=start.get("artifact_dir"),
            issue=start.get("issue"),
        )
        issue_dir = artifact_dir_from(start)
        event_log = issue_dir / "drive-events.jsonl"
        append_event_log(event_log, start_line)
        emit(
            "event_log",
            event_log=event_log,
            artifact_dir=start.get("artifact_dir"),
            event_log_path=str(event_log),
        )

    while True:
        current = status_for(issue_dir)
        emit(
            "status",
            event_log=event_log,
            status=current.get("status"),
            phase=current.get("phase"),
            closure_decision=current.get("closure_decision"),
            terminal_disposition_status=current.get("terminal_disposition_status"),
            artifact_dir=str(issue_dir),
        )
        if is_terminal(current):
            audit = run_post_job_audit(issue_dir, current, file_issue=args.file_audit_issue)
            emit(
                "post_job_audit",
                event_log=event_log,
                artifact_dir=str(issue_dir),
                audit_path=str(issue_dir / "post-job-audit.json"),
                classification=audit.get("classification"),
                recommended_action=audit.get("recommended_action"),
                self_improvement_issue_url=audit.get("self_improvement_issue_url"),
            )
            emit("terminal", event_log=event_log, **current)
            return 0 if str(current.get("status") or "") in TERMINAL_STATUSES else 2
        if time.monotonic() >= deadline:
            emit(
                "timeout",
                event_log=event_log,
                artifact_dir=str(issue_dir),
                last_status=current.get("status"),
                phase=current.get("phase"),
            )
            return 3
        next_result = step(issue_dir, run_webgpt=args.run_webgpt)
        emit(
            "step",
            event_log=event_log,
            status=next_result.get("status"),
            closure_decision=next_result.get("closure_decision"),
        )
        time.sleep(args.poll_seconds)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start")
    start.add_argument("--issue", type=int, required=True)
    start.set_defaults(func=command_start)

    status = sub.add_parser("status")
    status.add_argument("artifact_dir")
    status.set_defaults(func=command_status)

    step_cmd = sub.add_parser("step")
    step_cmd.add_argument("artifact_dir")
    step_cmd.add_argument("--run-webgpt", action=argparse.BooleanOptionalAction, default=True)
    step_cmd.set_defaults(func=command_step)

    scheduler = sub.add_parser("scheduler")
    scheduler.add_argument("--issue", type=int)
    scheduler.add_argument("--max-issues", type=int, default=1)
    scheduler.add_argument("--run-webgpt", action=argparse.BooleanOptionalAction, default=True)
    scheduler.add_argument("--github-dry-run", action="store_true")
    scheduler.set_defaults(func=command_scheduler)

    cron_tick = sub.add_parser("cron-tick")
    cron_tick.add_argument("--issue", type=int)
    cron_tick.add_argument("--max-issues", type=int, default=1)
    cron_tick.add_argument("--run-webgpt", action=argparse.BooleanOptionalAction, default=True)
    cron_tick.add_argument("--github-dry-run", action="store_true")
    cron_tick.add_argument("--auto-update", action=argparse.BooleanOptionalAction, default=True)
    cron_tick.add_argument("--branch", default="main")
    cron_tick.set_defaults(func=command_cron_tick)

    install_cron = sub.add_parser("install-cron")
    install_cron.add_argument("--interval-minutes", type=int, default=5)
    install_cron.add_argument("--schedule")
    install_cron.add_argument("--max-issues", type=int, default=1)
    install_cron.add_argument("--run-webgpt", action=argparse.BooleanOptionalAction, default=True)
    install_cron.add_argument("--auto-update", action=argparse.BooleanOptionalAction, default=True)
    install_cron.add_argument("--dry-run", action="store_true")
    install_cron.set_defaults(func=command_install_cron)

    remove_cron = sub.add_parser("remove-cron")
    remove_cron.add_argument("--dry-run", action="store_true")
    remove_cron.set_defaults(func=command_remove_cron)

    cron_status = sub.add_parser("cron-status")
    cron_status.set_defaults(func=command_cron_status)

    audit = sub.add_parser("audit-run")
    audit.add_argument("artifact_dir")
    audit.add_argument("--file-issue", action="store_true")
    audit.set_defaults(func=command_audit_run)

    drive = sub.add_parser("drive")
    drive.add_argument("--issue", type=int)
    drive.add_argument("--artifact-dir")
    drive.add_argument("--timeout-seconds", type=int, default=1800)
    drive.add_argument("--poll-seconds", type=float, default=15.0)
    drive.add_argument("--run-webgpt", action=argparse.BooleanOptionalAction, default=True)
    drive.add_argument("--file-audit-issue", action="store_true")
    drive.set_defaults(func=command_drive)

    return parser


def command_audit_run(args: argparse.Namespace) -> int:
    issue_dir = Path(args.artifact_dir).expanduser().resolve()
    current = status_for(issue_dir)
    audit = run_post_job_audit(issue_dir, current, file_issue=args.file_issue)
    print(json.dumps(audit, indent=2, sort_keys=True))
    return 0 if audit.get("classification") in AUDIT_STATUSES else 2


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
