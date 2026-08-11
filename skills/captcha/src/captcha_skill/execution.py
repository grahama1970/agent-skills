"""Bounded ReCAP execution, durable events, receipts, and verification."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import ValidationError

from .constants import DEFAULT_OUTPUT_ROOT, DEFAULT_RECAP_ROOT
from .errors import CaptchaSkillError, ErrorCode
from .models import (
    AuthorizationManifest,
    AuthorizationReceipt,
    BoundedJudgment,
    RecapSummary,
    RunReceipt,
    RunStatus,
    SeamValidation,
)
from .policy import sha256_file, utc_now, write_json_atomic
from .layout import (
    _is_relative_to,
    _safe_resolve,
    default_recap_python,
    validate_recap_runtime,
    validate_storage_path,
)
from .planning import build_evaluation_plan
from .results import validate_recap_summary_for_manifest
from .preflight import (
    build_recap_environment,
    collect_surf_capabilities,
    preflight_model_endpoint,
    preflight_surf_target,
    preflight_target,
)


def _append_event(path: Path, event: str, **details: Any) -> None:
    record = {
        "schema_version": "captcha.event.v1",
        "timestamp": utc_now().isoformat(),
        "event": event,
        "details": details,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise CaptchaSkillError(
            ErrorCode.IO_ERROR,
            "could not append run event",
            {"path": str(path), "error": str(exc)},
        ) from exc


def _write_status(path: Path, status: RunStatus, **details: Any) -> None:
    write_json_atomic(
        path,
        {
            "schema_version": "captcha.run_status.v1",
            "status": status.value,
            "updated_at": utc_now().isoformat(),
            **details,
        },
    )


def _run_recap_process(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    stdout_path: Path,
    stderr_path: Path,
    timeout_seconds: int,
) -> int:
    """Run ReCAP in its own process group and enforce a hard timeout."""

    try:
        with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
            process = subprocess.Popen(
                argv,
                cwd=cwd,
                env=env,
                stdout=stdout_handle,
                stderr=stderr_handle,
                shell=False,
                start_new_session=True,
            )
            try:
                return process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=10)
                raise CaptchaSkillError(
                    ErrorCode.EXECUTION_TIMEOUT,
                    "ReCAP benchmark exceeded its authorized timeout",
                    {"timeout_seconds": timeout_seconds},
                ) from exc
    except FileNotFoundError as exc:
        raise CaptchaSkillError(
            ErrorCode.RECAP_RUNTIME_MISSING,
            "ReCAP runtime could not be started",
            {"argv0": argv[0], "error": str(exc)},
        ) from exc
    except OSError as exc:
        raise CaptchaSkillError(
            ErrorCode.EXECUTION_FAILED,
            "ReCAP subprocess failed before completion",
            {"error": str(exc)},
        ) from exc


def _find_and_validate_summary(
    recap_runs_root: Path,
    manifest: AuthorizationManifest,
) -> tuple[Path, RecapSummary]:
    paths = sorted(recap_runs_root.glob("*/captcha-benchmark-results.json"))
    if len(paths) != 1:
        raise CaptchaSkillError(
            ErrorCode.RESULT_MISSING,
            "expected exactly one ReCAP benchmark summary",
            {"matches": [str(path) for path in paths]},
        )
    path = paths[0]
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        summary = RecapSummary.model_validate(value)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        details: dict[str, Any] = {"path": str(path), "error": str(exc)}
        if isinstance(exc, ValidationError):
            details["errors"] = exc.errors(include_url=False)
        raise CaptchaSkillError(
            ErrorCode.RESULT_INVALID,
            "ReCAP summary failed schema validation",
            details,
        ) from exc
    validate_recap_summary_for_manifest(summary, manifest)
    stats = summary.overall_stats
    if len(summary.tasks) != stats.total_captchas:
        raise CaptchaSkillError(
            ErrorCode.RESULT_INVALID,
            "ReCAP summary task count disagrees with overall_stats",
            {
                "task_records": len(summary.tasks),
                "total_captchas": stats.total_captchas,
            },
        )
    return path, summary


def _run_relative_path(root: Path, path: Path) -> str:
    """Return one canonical POSIX evidence key and reject path escape."""

    resolved = _safe_resolve(path)
    if not _is_relative_to(resolved, root):
        raise CaptchaSkillError(
            ErrorCode.IO_ERROR,
            "evidence file escapes the run directory",
            {"path": str(resolved), "run_dir": str(root)},
        )
    return resolved.relative_to(root).as_posix()


def _evidence_hashes(paths: list[Path], *, root: Path) -> dict[str, str]:
    """Hash evidence under exact run-relative paths, never ambiguous basenames."""

    run_root = _safe_resolve(root)
    evidence: dict[str, str] = {}
    for path in paths:
        if not path.is_file():
            continue
        key = _run_relative_path(run_root, path)
        if key in evidence:
            raise CaptchaSkillError(
                ErrorCode.IO_ERROR,
                "duplicate evidence path in run receipt",
                {"path": key},
            )
        evidence[key] = sha256_file(path)
    return evidence


def _blocked_receipt(
    *,
    run_id: str,
    started_at: datetime,
    run_dir: Path,
    authorization_path: Path,
    plan_path: Path,
    surf_path: Path,
    surf_target_path: Path,
    surf_target_screenshot_path: Path,
    target_path: Path,
    model_endpoint_path: Path,
    stdout_path: Path,
    stderr_path: Path,
    error: CaptchaSkillError,
    exit_code: int | None,
) -> RunReceipt:
    evidence_paths = [
        authorization_path,
        plan_path,
        surf_path,
        surf_target_path,
        surf_target_screenshot_path,
        target_path,
        model_endpoint_path,
        stdout_path,
        stderr_path,
        run_dir / "request.json",
        run_dir / "events.jsonl",
    ]
    return RunReceipt(
        schema_version="captcha.run_receipt.v1",
        run_id=run_id,
        status=RunStatus.BLOCKED,
        started_at=started_at,
        finished_at=utc_now(),
        authorization_receipt_path="authorization-receipt.json",
        plan_path="plan.json",
        surf_capabilities_path="surf-capabilities.json",
        surf_target_preflight_path="surf-target-preflight.json",
        target_preflight_path="target-preflight.json",
        model_endpoint_preflight_path="model-endpoint-preflight.json",
        recap_summary_path=None,
        stdout_path="recap.stdout.log",
        stderr_path="recap.stderr.log",
        exit_code=exit_code,
        bounded_judgment=BoundedJudgment.NOT_MEASURED,
        claims=[],
        limitations=[
            "No CAPTCHA-solving capability claim is permitted from this run.",
            "Inspect failure_code and preserved evidence before retrying.",
        ],
        evidence_sha256=_evidence_hashes(evidence_paths, root=run_dir),
        failure_code=error.code.value,
        failure_message=error.message,
    )


def execute_evaluation(
    manifest: AuthorizationManifest,
    authorization: AuthorizationReceipt,
    *,
    recap_root: Path = DEFAULT_RECAP_ROOT,
    recap_python: Path | None = None,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> tuple[RunReceipt, Path]:
    """Execute one authorized ReCAP run and return its durable receipt."""

    recap = _safe_resolve(recap_root)
    runtime_python = _safe_resolve(recap_python or default_recap_python(recap))
    output = validate_storage_path(output_root)
    validate_recap_runtime(recap, runtime_python)

    plan = build_evaluation_plan(
        manifest,
        authorization,
        recap_root=recap,
        recap_python=runtime_python,
        output_root=output,
    )
    if plan.readiness is not RunStatus.PASS:
        raise CaptchaSkillError(
            ErrorCode.EXECUTION_FAILED,
            "evaluation plan is not execution-ready",
            {"blockers": plan.blockers},
        )

    output.mkdir(parents=True, exist_ok=True)
    started_at = utc_now()
    stamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{stamp}-{authorization.authorization_id}-{uuid.uuid4().hex[:8]}"
    run_dir = output / run_id
    run_dir.mkdir(parents=False, exist_ok=False)

    request_path = run_dir / "request.json"
    authorization_path = run_dir / "authorization-receipt.json"
    plan_path = run_dir / "plan.json"
    surf_path = run_dir / "surf-capabilities.json"
    surf_target_path = run_dir / "surf-target-preflight.json"
    surf_target_screenshot_path = run_dir / "surf-target-preflight.png"
    target_path = run_dir / "target-preflight.json"
    model_endpoint_path = run_dir / "model-endpoint-preflight.json"
    events_path = run_dir / "events.jsonl"
    status_path = run_dir / "status.json"
    stdout_path = run_dir / "recap.stdout.log"
    stderr_path = run_dir / "recap.stderr.log"
    receipt_path = run_dir / "captcha.run-receipt.json"
    recap_runs_root = run_dir / "recap-runs"

    write_json_atomic(request_path, manifest.model_dump(mode="json"))
    write_json_atomic(authorization_path, authorization.model_dump(mode="json"))
    write_json_atomic(plan_path, plan.model_dump(mode="json"))
    _write_status(status_path, RunStatus.NEEDS_ATTENTION, phase="preflight")
    _append_event(events_path, "run_created", run_id=run_id)

    exit_code: int | None = None
    try:
        capabilities = collect_surf_capabilities()
        write_json_atomic(surf_path, capabilities.model_dump(mode="json", by_alias=True))
        _append_event(
            events_path,
            "surf_capabilities_validated",
            schema=capabilities.contract_schema,
            extension_socket_present=capabilities.transport.extension_socket_present,
            cdp_fallback=capabilities.transport.cdp_fallback,
        )

        surf_target_proof = preflight_surf_target(
            manifest,
            screenshot_path=surf_target_screenshot_path,
        )
        write_json_atomic(
            surf_target_path,
            surf_target_proof.model_dump(mode="json"),
        )
        _append_event(
            events_path,
            "surf_target_preflight_passed",
            challenge_url=surf_target_proof.challenge_url,
            final_url=surf_target_proof.final_url,
            tab_id=surf_target_proof.tab_id,
            screenshot_sha256=surf_target_proof.screenshot_sha256,
        )

        target_proof = preflight_target(manifest)
        write_json_atomic(target_path, target_proof.model_dump(mode="json"))
        _append_event(
            events_path,
            "target_preflight_passed",
            url=target_proof.url,
            body_sha256=target_proof.body_sha256,
        )

        model_endpoint_proof = preflight_model_endpoint(manifest)
        write_json_atomic(
            model_endpoint_path,
            model_endpoint_proof.model_dump(mode="json"),
        )
        _append_event(
            events_path,
            "model_endpoint_preflight_passed",
            url=model_endpoint_proof.url,
            requested_model_id=model_endpoint_proof.requested_model_id,
            response_sha256=model_endpoint_proof.response_sha256,
        )

        recap_runs_root.mkdir(parents=True, exist_ok=False)
        env = build_recap_environment(manifest, recap_runs_root=recap_runs_root)
        _write_status(status_path, RunStatus.NEEDS_ATTENTION, phase="recap_running")
        _append_event(
            events_path,
            "recap_started",
            argv=plan.execution.argv,
            environment_keys=plan.execution.environment_keys,
            secret_environment_keys=plan.execution.secret_environment_keys,
        )
        logger.info("running bounded ReCAP benchmark: {}", run_id)
        exit_code = _run_recap_process(
            plan.execution.argv,
            cwd=Path(plan.execution.cwd),
            env=env,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            timeout_seconds=manifest.timeout_seconds,
        )
        _append_event(events_path, "recap_finished", exit_code=exit_code)
        if exit_code != 0:
            raise CaptchaSkillError(
                ErrorCode.EXECUTION_FAILED,
                "ReCAP benchmark exited non-zero",
                {"exit_code": exit_code},
            )

        summary_path, summary = _find_and_validate_summary(recap_runs_root, manifest)
        _append_event(
            events_path,
            "recap_summary_validated",
            summary_path=str(summary_path),
            total_captchas=summary.overall_stats.total_captchas,
            total_solved=summary.overall_stats.total_solved,
            success_rate=summary.overall_stats.overall_success_rate,
        )
        evidence_paths = [
            request_path,
            authorization_path,
            plan_path,
            surf_path,
            surf_target_path,
            surf_target_screenshot_path,
            target_path,
            model_endpoint_path,
            events_path,
            stdout_path,
            stderr_path,
            summary_path,
        ]
        receipt = RunReceipt(
            schema_version="captcha.run_receipt.v1",
            run_id=run_id,
            status=RunStatus.PASS,
            started_at=started_at,
            finished_at=utc_now(),
            authorization_receipt_path="authorization-receipt.json",
            plan_path="plan.json",
            surf_capabilities_path="surf-capabilities.json",
            surf_target_preflight_path="surf-target-preflight.json",
            target_preflight_path="target-preflight.json",
            model_endpoint_preflight_path="model-endpoint-preflight.json",
            recap_summary_path=_run_relative_path(run_dir, summary_path),
            stdout_path="recap.stdout.log",
            stderr_path="recap.stderr.log",
            exit_code=0,
            bounded_judgment=BoundedJudgment.CAPABILITY_MEASURED,
            claims=[
                (
                    "The pinned ReCAP agent solved "
                    f"{summary.overall_stats.total_solved} of "
                    f"{summary.overall_stats.total_captchas} authorized synthetic "
                    "dynamic CAPTCHA tasks in this run."
                )
            ],
            limitations=[
                (
                    "Result applies only to the pinned ReCAP commit, local model, "
                    "manifest, and synthetic tasks recorded here."
                ),
                (
                    "It does not demonstrate permission or capability to bypass "
                    "a live third-party CAPTCHA."
                ),
                (
                    "Surf proof establishes capabilities plus an isolated local "
                    "challenge navigation, identity check, screenshot, and tab close; "
                    "ReCAP owns model-driven benchmark interaction through Playwright."
                ),
            ],
            evidence_sha256=_evidence_hashes(evidence_paths, root=run_dir),
            seam_validation=SeamValidation(kind="captcha.run_receipt"),
        )
        write_json_atomic(receipt_path, receipt.model_dump(mode="json"))
        _write_status(
            status_path,
            RunStatus.PASS,
            phase="complete",
            receipt_path=receipt_path.name,
            receipt_sha256=sha256_file(receipt_path),
        )
        return receipt, run_dir
    except CaptchaSkillError as exc:
        _append_event(
            events_path,
            "run_blocked",
            failure_code=exc.code.value,
            message=exc.message,
        )
        receipt = _blocked_receipt(
            run_id=run_id,
            started_at=started_at,
            run_dir=run_dir,
            authorization_path=authorization_path,
            plan_path=plan_path,
            surf_path=surf_path,
            surf_target_path=surf_target_path,
            surf_target_screenshot_path=surf_target_screenshot_path,
            target_path=target_path,
            model_endpoint_path=model_endpoint_path,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            error=exc,
            exit_code=exit_code,
        )
        write_json_atomic(receipt_path, receipt.model_dump(mode="json"))
        _write_status(
            status_path,
            RunStatus.BLOCKED,
            phase="complete",
            failure_code=exc.code.value,
            receipt_path=receipt_path.name,
            receipt_sha256=sha256_file(receipt_path),
        )
        return receipt, run_dir
