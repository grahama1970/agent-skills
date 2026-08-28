#!/usr/bin/env python3
"""Run a Persona Dream step manifest through pipeline-self-repair.

This controller is intentionally thin: Persona Dream owns step order and receipt
semantics; pipeline-self-repair owns immutable-goal preflight, triage, category,
ledger, ticket/watchdog projection, and provider-effect safety.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence


SKILL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_ROOT.parents[1]
PIPELINE_SELF_REPAIR = REPO_ROOT / "skills" / "pipeline-self-repair" / "run.sh"
GOAL_DRIFT = REPO_ROOT / "skills" / "goal-drift" / "run.sh"
DEFAULT_REPO = "grahama1970/agent-skills"


PASS_PREFIXES = ("PASS", "ACCEPTED", "PROVIDER_READY")
FAIL_PREFIXES = ("BLOCKED", "FAILED", "FAIL", "ERROR", "DRY_RUN_NOT_LIVE_SUBMITTABLE")


class ManifestError(ValueError):
    pass


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def slug(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in value.strip().lower()).strip("-") or "step"


def sha_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def sha_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def goal_hash(goal_payload: Mapping[str, Any]) -> str:
    stripped = {key: value for key, value in goal_payload.items() if key not in {"registered_at", "goal_hash", "seam_validation", "parent_goal_hash"}}
    return sha_json(stripped)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def resolve_path(value: str | None, *, base: Path) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def resolve_path_list(values: Sequence[str], *, base: Path) -> list[Path]:
    return [path for value in values if (path := resolve_path(value, base=base)) is not None]


def load_manifest(path: Path) -> dict[str, Any]:
    manifest = read_json(path)
    if not isinstance(manifest, dict):
        raise ManifestError("manifest must be a JSON object")
    if manifest.get("schema") != "persona_dream.self_repair_manifest.v1":
        raise ManifestError(f"wrong manifest schema: {manifest.get('schema')}")
    steps = manifest.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ManifestError("manifest.steps must be a non-empty list")
    seen: set[str] = set()
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            raise ManifestError(f"step[{index}] must be an object")
        step_id = step.get("step_id")
        command = step.get("command")
        if not isinstance(step_id, str) or not step_id.strip():
            raise ManifestError(f"step[{index}] missing step_id")
        if step_id in seen:
            raise ManifestError(f"duplicate step_id: {step_id}")
        seen.add(step_id)
        if not isinstance(command, list) or not command or not all(isinstance(part, str) and part for part in command):
            raise ManifestError(f"step[{step_id}] command must be a non-empty string list")
    return manifest


def immutable_goal_preflight(project: str) -> dict[str, Any]:
    proc = subprocess.run(
        [str(GOAL_DRIFT), "goal", "--project", project],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise ManifestError(f"immutable goal preflight output was not JSON: {exc}") from exc
    if proc.returncode != 0 or payload.get("status") == "NOT_ESTABLISHED":
        raise ManifestError(f"immutable goal preflight failed for {project}: {payload.get('reason') or proc.stderr[-500:] or 'no goal'}")
    if payload.get("schema") != "goal_drift.goal.v1":
        raise ManifestError(f"immutable goal preflight wrong schema: {payload.get('schema')}")
    if payload.get("source") != "human_prompt":
        raise ManifestError(f"immutable goal preflight source is not human_prompt: {payload.get('source')}")
    if not payload.get("goal_text"):
        raise ManifestError("immutable goal preflight returned empty goal_text")
    return {
        "status": "PASS_IMMUTABLE_GOAL_PREFLIGHT",
        "project": project,
        "goal_hash": goal_hash(payload),
        "source": payload.get("source"),
        "criteria_count": len(payload.get("criteria") or []),
        "command": [str(GOAL_DRIFT), "goal", "--project", project],
    }


def status_passed(status: str | None, allowed: Sequence[str]) -> bool:
    if status is None:
        return False
    if allowed:
        return status in set(allowed)
    return status.startswith(PASS_PREFIXES) and not status.startswith(FAIL_PREFIXES)


def artifact_status(paths: Sequence[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        rows.append({"path": str(path), "exists": path.exists(), "is_file": path.is_file()})
    return rows


def raw_failure_signal(*, step: Mapping[str, Any], command_result: subprocess.CompletedProcess[str], receipt_path: Path | None, receipt: Any, required_artifacts: list[dict[str, Any]], reason: str) -> str:
    payload = {
        "reason": reason,
        "step_id": step.get("step_id"),
        "returncode": command_result.returncode,
        "stdout_tail": command_result.stdout[-4000:],
        "stderr_tail": command_result.stderr[-4000:],
        "receipt_path": str(receipt_path) if receipt_path else None,
        "receipt": receipt if isinstance(receipt, dict) else None,
        "required_artifacts": required_artifacts,
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def build_record_failure_command(*, manifest: Mapping[str, Any], step: Mapping[str, Any], run_id: str, run_root: Path, ledger: Path, raw_signal: str, receipt_path: Path | None, manifest_base: Path, attempt: int, options: argparse.Namespace, goal_hash_value: str) -> list[str]:
    cmd = [
        str(PIPELINE_SELF_REPAIR),
        "record-failure",
        "--pipeline",
        "persona-dream",
        "--step-id",
        str(step["step_id"]),
        "--run-id",
        run_id,
        "--target",
        str(step.get("target") or "skills/persona-dream"),
        "--run-root",
        str(run_root),
        "--ledger",
        str(ledger),
        "--raw-signal",
        raw_signal,
        "--goal-project",
        str(manifest.get("goal_project") or "persona-dream"),
        "--goal-hash",
        goal_hash_value,
        "--repo",
        str(manifest.get("repo") or DEFAULT_REPO),
        "--attempt",
        str(attempt),
        "--json",
    ]
    if receipt_path is not None and receipt_path.exists():
        cmd.extend(["--receipt", str(receipt_path)])
    if step.get("layer"):
        cmd.extend(["--layer", str(step["layer"])])
    if step.get("checkpoint_id"):
        cmd.extend(["--checkpoint-id", str(step["checkpoint_id"])])
    if step.get("goal_context"):
        contexts = step["goal_context"]
        if isinstance(contexts, str):
            contexts = [contexts]
        for value in contexts:
            cmd.extend(["--goal-context", str(value)])
    for opt_name, flag in (
        ("request_body", "--request-body"),
        ("provider_response", "--provider-response"),
        ("agentic_eval_report", "--agentic-eval-report"),
    ):
        path = resolve_path(str(step.get(opt_name)), base=manifest_base) if step.get(opt_name) else None
        if path is not None:
            cmd.extend([flag, str(path)])
    if step.get("provider_task_id"):
        cmd.extend(["--provider-task-id", str(step["provider_task_id"])])
    if step.get("spend_state"):
        cmd.extend(["--spend-state", str(step["spend_state"])])
    for value in step.get("media_url") or []:
        cmd.extend(["--media-url", str(value)])
    for path in resolve_path_list([str(value) for value in (step.get("local_artifact") or [])], base=manifest_base):
        cmd.extend(["--local-artifact", str(path)])
    if options.skip_memory:
        cmd.append("--skip-memory")
    if options.skip_github:
        cmd.append("--skip-github")
    if options.no_ticket:
        cmd.append("--no-ticket")
    if options.apply_ticket:
        cmd.append("--apply-ticket")
    if options.dispatch_watchdog:
        cmd.append("--dispatch-watchdog")
    return cmd


def run_step(*, step: Mapping[str, Any], manifest_base: Path, run_root: Path, attempt: int) -> tuple[dict[str, Any], subprocess.CompletedProcess[str], Any, str]:
    step_id = str(step["step_id"])
    cwd = resolve_path(str(step.get("cwd")), base=manifest_base) if step.get("cwd") else REPO_ROOT
    assert cwd is not None
    command = [str(part) for part in step["command"]]
    started = time.time()
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, timeout=int(step.get("timeout_seconds") or 1800), check=False)
    elapsed = round(time.time() - started, 3)

    log_root = run_root / "self_repair_logs" / slug(step_id)
    log_root.mkdir(parents=True, exist_ok=True)
    (log_root / f"attempt_{attempt:02d}.stdout.txt").write_text(completed.stdout, encoding="utf-8", errors="replace")
    (log_root / f"attempt_{attempt:02d}.stderr.txt").write_text(completed.stderr, encoding="utf-8", errors="replace")

    receipt_path = resolve_path(str(step.get("receipt")), base=manifest_base) if step.get("receipt") else None
    receipt: Any = None
    receipt_status: str | None = None
    reason = "pass"
    if receipt_path is not None and receipt_path.exists():
        try:
            receipt = read_json(receipt_path)
            if isinstance(receipt, dict):
                receipt_status = str(receipt.get("status")) if receipt.get("status") is not None else None
        except Exception as exc:  # noqa: BLE001 - preserve receipt parse failure in output.
            receipt = {"parse_error": str(exc)}
            reason = "receipt_invalid_json"
    elif receipt_path is not None:
        reason = "receipt_missing"

    required_artifacts = artifact_status(resolve_path_list([str(value) for value in (step.get("required_artifacts") or [])], base=manifest_base))
    missing_artifacts = [row for row in required_artifacts if not row["exists"]]
    pass_statuses = [str(value) for value in (step.get("pass_statuses") or [])]
    passed = completed.returncode == 0
    if receipt_path is not None:
        passed = passed and status_passed(receipt_status, pass_statuses)
    if missing_artifacts:
        passed = False
        reason = "required_artifact_missing"
    if completed.returncode != 0:
        reason = "command_nonzero"
    elif receipt_path is not None and not status_passed(receipt_status, pass_statuses):
        reason = reason if reason != "pass" else f"receipt_status_not_pass:{receipt_status}"

    result = {
        "step_id": step_id,
        "attempt": attempt,
        "status": "PASS" if passed else "FAILED",
        "reason": reason,
        "command": command,
        "cwd": str(cwd),
        "returncode": completed.returncode,
        "elapsed_seconds": elapsed,
        "receipt": str(receipt_path) if receipt_path else None,
        "receipt_status": receipt_status,
        "required_artifacts": required_artifacts,
        "stdout_sha256": sha_text(completed.stdout),
        "stderr_sha256": sha_text(completed.stderr),
        "stdout_log": str(log_root / f"attempt_{attempt:02d}.stdout.txt"),
        "stderr_log": str(log_root / f"attempt_{attempt:02d}.stderr.txt"),
    }
    return result, completed, receipt, reason


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--start-at")
    parser.add_argument("--max-steps", type=int)
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--skip-memory", action="store_true")
    parser.add_argument("--skip-github", action="store_true")
    parser.add_argument("--no-ticket", action="store_true")
    parser.add_argument("--apply-ticket", action="store_true")
    parser.add_argument("--dispatch-watchdog", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        manifest_path = args.manifest.resolve()
        manifest_base = manifest_path.parent
        manifest = load_manifest(manifest_path)
        goal_project = str(manifest.get("goal_project") or "persona-dream")
        goal_preflight = immutable_goal_preflight(goal_project)
        run_id = args.run_id or str(manifest.get("run_id") or f"self-repair-{int(time.time())}")
        run_root = (args.run_root or resolve_path(str(manifest.get("run_root")), base=manifest_base) or (Path("/tmp") / f"persona-dream-{run_id}"))
        run_root = run_root.resolve()
        ledger = (args.ledger or run_root / "replay_ledger.jsonl").resolve()
        run_root.mkdir(parents=True, exist_ok=True)

        steps = list(manifest["steps"])
        if args.start_at:
            try:
                start_index = next(i for i, step in enumerate(steps) if step.get("step_id") == args.start_at)
            except StopIteration as exc:
                raise ManifestError(f"--start-at step not found: {args.start_at}") from exc
            steps = steps[start_index:]
        if args.max_steps is not None:
            steps = steps[: args.max_steps]

        receipt: dict[str, Any] = {
            "schema": "persona_dream.self_repair_run_receipt.v1",
            "status": "PASS_SELF_REPAIR_RUN",
            "generated_at": now_iso(),
            "manifest": str(manifest_path),
            "run_id": run_id,
            "run_root": str(run_root),
            "ledger": str(ledger),
            "goal_project": goal_project,
            "goal_preflight": goal_preflight,
            "steps": [],
            "failure_record": None,
            "stop_reason": "all_steps_passed",
            "kling_authorization": manifest.get("kling_authorization"),
            "policy": {
                "required_step_failure_blocks_next_step": True,
                "record_failure_uses_pipeline_self_repair": True,
                "immutable_goal_project_required": True,
                "automatic_paid_resubmit_allowed": False,
            },
        }

        for step in steps:
            step_result, completed, step_receipt, reason = run_step(
                step=step,
                manifest_base=manifest_base,
                run_root=run_root,
                attempt=args.attempt,
            )
            receipt["steps"].append(step_result)
            if step_result["status"] == "PASS":
                continue

            raw_signal = raw_failure_signal(
                step=step,
                command_result=completed,
                receipt_path=Path(step_result["receipt"]) if step_result.get("receipt") else None,
                receipt=step_receipt,
                required_artifacts=step_result["required_artifacts"],
                reason=reason,
            )
            record_cmd = build_record_failure_command(
                manifest=manifest,
                step=step,
                run_id=run_id,
                run_root=run_root,
                ledger=ledger,
                raw_signal=raw_signal,
                receipt_path=Path(step_result["receipt"]) if step_result.get("receipt") else None,
                manifest_base=manifest_base,
                attempt=args.attempt,
                options=args,
                goal_hash_value=str(goal_preflight["goal_hash"]),
            )
            record = subprocess.run(record_cmd, cwd=REPO_ROOT, text=True, capture_output=True, timeout=600, check=False)
            record_log = run_root / "self_repair_logs" / slug(str(step["step_id"])) / f"attempt_{args.attempt:02d}.pipeline_self_repair.json"
            record_log.write_text(record.stdout or record.stderr, encoding="utf-8", errors="replace")
            receipt["status"] = "BLOCKED_REPAIR_RECORDED" if record.returncode == 0 else "BLOCKED_REPAIR_RECORD_FAILED"
            receipt["stop_reason"] = "step_failed_repair_branch_started" if record.returncode == 0 else "pipeline_self_repair_record_failure_failed"
            receipt["failure_record"] = {
                "step_id": step["step_id"],
                "pipeline_self_repair_returncode": record.returncode,
                "pipeline_self_repair_command": record_cmd,
                "pipeline_self_repair_output": str(record_log),
                "pipeline_self_repair_stdout_tail": record.stdout[-4000:],
                "pipeline_self_repair_stderr_tail": record.stderr[-4000:],
            }
            break

    except Exception as exc:  # noqa: BLE001 - fail closed with machine-readable receipt.
        receipt = {
            "schema": "persona_dream.self_repair_run_receipt.v1",
            "status": "BLOCKED_SELF_REPAIR_RUN",
            "generated_at": now_iso(),
            "failure": str(exc),
        }

    if args.output:
        write_json(args.output, receipt)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
    return 0 if receipt["status"] == "PASS_SELF_REPAIR_RUN" else 2


if __name__ == "__main__":
    raise SystemExit(main())
