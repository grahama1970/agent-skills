#!/usr/bin/env python3
"""Retained executable eval entrypoint: boundary suite, read-only observation, live canary.

Nothing runs on import. Live mode is explicit and targets an EXISTING authorized
issue through commands.tick; it never creates fixture tickets, branches or trees.
"""
from __future__ import annotations
import argparse
import json
import os
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))


def save(path: Path, value: dict) -> None:
    from watchdog.core import write_json
    write_json(path, value)


def unit(output: Path) -> int:
    """Real disposable-Git/subprocess tests; simulated GitHub/provider boundaries."""
    xml_path = output.with_suffix(".junit.xml")
    logs = output.with_suffix(".pytest.log")
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-m", "pytest", "-q", str(SKILL / "tests/test_primary_main_revision.py"),
               f"--junitxml={xml_path}"]
    with logs.open("w") as log:
        run = subprocess.run(command, cwd=SKILL, stdout=log, stderr=subprocess.STDOUT, check=False)
    testcases, errors = [], []
    if xml_path.exists():
        tree = ET.parse(xml_path)
        for case in tree.findall(".//testcase"):
            status = "FAIL" if case.find("failure") is not None or case.find("error") is not None else (
                "NOT_TESTED" if case.find("skipped") is not None else "PASS")
            testcases.append({"id": case.get("name"), "status": status, "seconds": case.get("time")})
    else:
        errors.append("pytest produced no result XML")
    passed = bool(testcases) and run.returncode == 0 and all(c["status"] == "PASS" for c in testcases)
    save(output, {"schema": "agent_skills.project_watchdog.primary_revision_eval.v1",
        "lane": "boundary-tests", "mocked": True, "live": False,
        "status": "PASS" if passed else "FAIL", "command": command, "exit_code": run.returncode,
        "cases": testcases, "executed": len(testcases), "errors": errors,
        "log": str(logs), "junit": str(xml_path),
        "proof_limit": "Git and subprocess experiments are real; GitHub/provider fixtures are not live acceptance."})
    return 0 if passed else 1


def context(project_id: str, number: int):
    from watchdog import config, core, github, models, primary, registry
    project = registry.find_project(core.load_json(config.projects_path()), project_id)
    models.validate_project_entry(project)
    root = registry.project_worktree(project).resolve()
    primary.identity(root)
    primary.assert_repository(root, registry.project_repo(project))
    issue = github.get_issue(project["repo"], number)
    models.validate_issue(issue)
    targets = primary.safe_targets(registry.issue_targets(issue))
    return project, root, issue, targets


def observe(project_id: str, number: int, output: Path) -> int:
    from watchdog import commands, config, core, primary, registry, target_content as content
    from watchdog.primary_models import OwnedTargets
    project, root, issue, targets = context(project_id, number)
    if output.resolve().is_relative_to(root):
        raise RuntimeError("eval output must be outside the primary checkout")
    remote = content.remote_pin(root)
    current = content.snapshot(root, targets, remote)
    owned_path = primary._area(root) / "owned" / f"{number}.json"
    owned = OwnedTargets.model_validate_json(owned_path.read_text()) if owned_path.exists() else None
    classification = content.classify(root, current, repo=project["repo"], number=number,
        task_sha256=content.digest((issue.get("body") or "").encode()), owned=owned)
    foreign = registry.lane_busy_issues("revision-observation", project)
    action, excluded = registry.classify_issue_with_reason(issue)
    busy = registry.busy_targets(foreign)
    result = {"schema": "agent_skills.project_watchdog.primary_revision_eval.v1",
        "lane": "read-only-observation", "mocked": False, "live": True,
        "status": "OBSERVED", "authoring_executed": False, "ticket_closed": False,
        "repo": project["repo"], "issue_number": number, "root": str(root), "targets": targets,
        "local_HEAD": current.head, "live_origin_main": remote, "classification": classification,
        "writer_active": primary.writer_active(root), "route": action, "exclusion": excluded,
        "effective_project_state": commands._project_runtime_state(project, core.load_json(config.state_path())),
        "scope_conflict": registry.targets_are_blocked(set(targets), busy),
        "foreign_leases": [{"number": i["number"], "targets": sorted(registry.issue_targets(i))} for i in foreign],
        "recovery": primary.observations(root), "retained_legacy": primary.legacy_inventory(root, number)}
    save(output, result)
    print(json.dumps(result, indent=2))
    return 0


def live(project_id: str, number: int, output: Path, kill_scheduler: bool, timeout: int) -> int:
    """Real tick, optional SIGKILL of ONLY the scheduler process spawned here."""
    from watchdog import primary, registry, target_content as content
    from watchdog.primary_models import Operation
    project, root, issue, targets = context(project_id, number)
    if output.resolve().is_relative_to(root):
        raise RuntimeError("live receipts must be outside the primary checkout")
    if registry.policy_held(project["repo"], number) or registry.classify_issue(issue) is None:
        raise RuntimeError("canary requires an existing eligible, non-held ticket; labels are not changed by the harness")
    if primary.pending(root):
        raise RuntimeError("pre-existing operation/reservation: observe/recover it instead of starting a canary")
    before_legacy = primary.legacy_inventory(root, number)
    operation_dir = primary._area(root) / "operations"
    prior = set(operation_dir.glob("*.json"))
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(Path(__file__).resolve()), "_tick", "--project", project_id, "--issue", str(number)]
    killed, seen, duplicate, record = False, {}, None, None
    started = time.monotonic()
    log_path = output.with_suffix(".scheduler.log")
    with log_path.open("w") as log:
        proc = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        while time.monotonic() - started < timeout:
            for path in set(operation_dir.glob("*.json")) - prior:
                candidate = Operation.model_validate_json(path.read_text())
                if candidate.issue_number == number:
                    seen[candidate.owner_token] = candidate
                    if candidate.scheduler_pid == proc.pid:
                        record = candidate
            if record and record.phase == "running" and primary.writer_active(root):
                if duplicate is None:
                    # Same real CLI path while authority is held: must not launch another author.
                    with output.with_suffix(".duplicate-tick.log").open("w") as extra:
                        check = subprocess.run(command, stdout=extra, stderr=subprocess.STDOUT,
                                               timeout=120, check=False)
                        duplicate = check.returncode
                if kill_scheduler and not killed and proc.poll() is None:
                    # A direct child cannot have its PID reused before it is reaped.
                    assert record.scheduler_pid == proc.pid
                    os.kill(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=10)
                    killed = True
            if record and record.phase in {"finished", "retryable"}:
                break
            if proc.poll() is not None and not primary.writer_active(root):
                # A returned failure/uncertain journal is already the result;
                # waiting out the canary deadline cannot settle that run.
                break
            time.sleep(1)
        # Do not kill the detached author or fabricate remote settlement on timeout.
        if proc.poll() is not None:
            proc.wait()
    for path in set(operation_dir.glob("*.json")) - prior:
        candidate = Operation.model_validate_json(path.read_text())
        if candidate.issue_number == number:
            seen[candidate.owner_token] = candidate
    latest = next((r for r in seen.values() if r.scheduler_pid == proc.pid), record)
    primary.identity(root)
    after_legacy = primary.legacy_inventory(root, number)
    checks = {
        "one_operation_not_duplicate": len(seen) == 1,
        "real_native_verified_closure": bool(latest and latest.phase == "finished" and
            latest.result and latest.result.get("ticket_closed") is True and latest.result.get("ok") is True),
        "retained_legacy_unchanged": before_legacy == after_legacy,
        "primary_still_main": True,
        "duplicate_tick_exercised": duplicate is not None,
        "actual_scheduler_killed_when_requested": killed if kill_scheduler else True,
    }
    passed = all(checks.values())
    result = {"schema": "agent_skills.project_watchdog.primary_revision_eval.v1",
        "lane": "real-tick-with-scheduler-kill" if kill_scheduler else "real-tick",
        "mocked": False, "live": True, "status": "PASS" if passed else "NEEDS_ATTENTION",
        "checks": checks, "repo": project["repo"], "issue_number": number,
        "scheduler_pid": proc.pid, "scheduler_exit_code": proc.poll(),
        "retained_run_id": latest.run_id if latest else None,
        "journals": [r.journal for r in seen.values()], "log": str(log_path),
        "recovery_command": primary.recovery_command(root),
        "proof_limit": "No result asserts unknown remote settlement or attributes unrelated cron edits to this worker."}
    save(output, result)
    print(json.dumps(result, indent=2))
    return 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    p = sub.add_parser("unit"); p.add_argument("--output", type=Path, required=True)
    for name in ("observe", "live", "_tick"):
        p = sub.add_parser(name)
        p.add_argument("--project", required=True)
        p.add_argument("--issue", type=int, required=True)
        if name != "_tick": p.add_argument("--output", type=Path, required=True)
        if name == "live":
            p.add_argument("--kill-scheduler", action="store_true")
            p.add_argument("--timeout", type=int, default=2100)
    args = parser.parse_args()
    if args.mode != "_tick":
        # Never replace another agent's retained eval receipt/log.
        siblings = [args.output, args.output.with_suffix(".junit.xml"),
                    args.output.with_suffix(".pytest.log"), args.output.with_suffix(".scheduler.log"),
                    args.output.with_suffix(".duplicate-tick.log")]
        if any(path.exists() for path in siblings):
            parser.error("choose a new outside-repository output path; existing evidence is never overwritten")
    if args.mode == "unit": return unit(args.output)
    if args.mode == "observe": return observe(args.project, args.issue, args.output)
    if args.mode == "_tick":
        from watchdog.commands import tick
        return tick(apply=True, project_id=args.project, max_tickets=1, only_issue=args.issue)
    return live(args.project, args.issue, args.output, args.kill_scheduler, args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
