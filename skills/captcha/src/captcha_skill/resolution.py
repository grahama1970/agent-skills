"""Bounded surf-composed live CAPTCHA resolution and human alerting.

The ``surf`` provider path turns an authorized live target into a typed outcome:
pointer plan, surf pointer dispatch, post-dispatch observation, then
SOLVED / NOT_SOLVED / BLOCKED. When the challenge is not cleared, a human alert
is posted through Surf's ``captcha.alert`` command, which transports the
notification through ops-buzz. Surf owns browser transport and the alert;
captcha owns authorization, the pointer contract, and the outcome receipt.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Literal

from pydantic import Field, ValidationError, model_validator

from .errors import CaptchaSkillError, ErrorCode
from .layout import surf_run_path
from .models import (
    AuthorizationManifest,
    AuthorizationReceipt,
    PointerMotionRequest,
    SeamValidation,
    StrictModel,
)
from .pointer_motion import build_pointer_dispatch_plan, build_pointer_motion_plan
from .policy import sha256_bytes, sha256_file, utc_now, write_json_atomic


class AlertReceipt(StrictModel):
    schema_version: Literal["surf.captcha_alert_receipt.v1"]
    status: Literal["DELIVERED", "DRY_RUN", "BLOCKED"]
    channel: str
    outcome_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    posted_at: datetime
    ops_buzz_receipt: dict[str, Any] | None = None
    failure_message: str | None = None
    # Surf (the transport owner) reports where it wrote the alert message. It
    # added this field to surf.captcha_alert_receipt.v1 after this consumer model
    # was written; StrictModel forbids unknown fields, so a live resolve aborted
    # at alert delivery with "message_path: Extra inputs are not permitted"
    # before ever dispatching the click. Accept the field surf legitimately emits.
    message_path: str | None = None
    seam_validation: SeamValidation

    @model_validator(mode="after")
    def validate_alert_truth(self) -> "AlertReceipt":
        if self.status == "BLOCKED":
            if self.failure_message is None:
                raise ValueError("BLOCKED alert receipt requires a failure message")
            if self.ops_buzz_receipt is not None:
                raise ValueError("BLOCKED alert receipt cannot carry an ops-buzz receipt")
        else:
            if self.ops_buzz_receipt is None:
                raise ValueError("delivered/dry-run alert receipt requires an ops-buzz receipt")
        return self


class ResolutionOutcome(StrictModel):
    schema_version: Literal["captcha.resolution_outcome.v1"]
    status: Literal["SOLVED", "NOT_SOLVED", "BLOCKED"]
    provider: Literal["surf"] = "surf"
    target_url: str
    tab_id: int = Field(gt=0)
    pointer_plan_path: str
    dispatch_plan_path: str
    dispatch_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    observation_passed: bool | None = None
    alert: AlertReceipt | None = None
    failure_code: str | None = None
    failure_message: str | None = None
    created_at: datetime
    evidence_sha256: dict[str, str]
    seam_validation: SeamValidation

    @model_validator(mode="after")
    def validate_outcome_truth(self) -> "ResolutionOutcome":
        if self.status == "SOLVED":
            if self.observation_passed is not True:
                raise ValueError("SOLVED requires observation_passed true")
        elif self.status == "NOT_SOLVED":
            if self.observation_passed is not False:
                raise ValueError("NOT_SOLVED requires observation_passed false")
            if self.failure_code is not None or self.failure_message is not None:
                raise ValueError("NOT_SOLVED cannot carry failure fields")
        else:  # BLOCKED
            if self.observation_passed is not None:
                raise ValueError("BLOCKED cannot carry an observation result")
            if self.failure_code is None or self.failure_message is None:
                raise ValueError("BLOCKED requires failure_code and failure_message")
        return self


def _json_values_from_text(text: str) -> Iterator[Any]:
    """Yield complete JSON values embedded in otherwise noisy command output."""

    stripped = text.strip()
    if not stripped:
        return
    try:
        yield json.loads(stripped)
        return
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    index = 0
    while index < len(text):
        next_object = text.find("{", index)
        next_array = text.find("[", index)
        starts = [item for item in (next_object, next_array) if item >= 0]
        if not starts:
            return
        candidate = min(starts)
        try:
            value, end = decoder.raw_decode(text, candidate)
        except json.JSONDecodeError:
            index = candidate + 1
            continue
        yield value
        index = max(end, candidate + 1)


def _parse_json_object(stdout: str) -> dict[str, Any]:
    objects = [value for value in _json_values_from_text(stdout) if isinstance(value, dict)]
    if not objects:
        raise CaptchaSkillError(
            ErrorCode.SURF_CONTRACT_INVALID,
            "Surf output did not contain a JSON object",
            {"stdout_tail": stdout[-4000:]},
        )
    return objects[-1]


def _run_surf_command(
    argv: list[str],
    *,
    cwd: Path,
    timeout_seconds: int,
    operation: str,
) -> dict[str, Any]:
    """Run one Surf command without a shell and require structured output."""

    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            shell=False,
            env=os.environ.copy(),
        )
    except FileNotFoundError as exc:
        raise CaptchaSkillError(
            ErrorCode.SURF_UNAVAILABLE,
            f"Surf {operation} command could not be started",
            {"argv": argv, "error": str(exc)},
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise CaptchaSkillError(
            ErrorCode.SURF_UNAVAILABLE,
            f"Surf {operation} command timed out",
            {"argv": argv, "timeout_seconds": timeout_seconds},
        ) from exc
    if result.returncode != 0:
        raise CaptchaSkillError(
            ErrorCode.SURF_UNAVAILABLE,
            f"Surf {operation} command failed",
            {
                "argv": argv,
                "exit_code": result.returncode,
                "stderr": result.stderr[-4000:],
                "stdout_tail": result.stdout[-2000:],
            },
        )
    return _parse_json_object(result.stdout)


def _walk_json(value: Any) -> Iterator[Any]:
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk_json(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_json(item)


def _extract_observation(value: dict[str, Any]) -> bool:
    """Interpret the post-dispatch observation result as a cleared challenge."""

    for item in _walk_json(value):
        if not isinstance(item, dict):
            continue
        for key in ("value", "passed", "cleared"):
            candidate = item.get(key)
            if candidate is not None:
                return bool(candidate)
    raise CaptchaSkillError(
        ErrorCode.RESOLUTION_OBSERVATION_INVALID,
        "Surf observation output did not contain a boolean result",
        {"response": value},
    )


def run_live_resolution(
    manifest: AuthorizationManifest,
    authorization: AuthorizationReceipt,
    request: PointerMotionRequest,
    *,
    tab_id: int,
    observe_js: str,
    out_dir: Path,
) -> tuple[ResolutionOutcome, Path]:
    """Run one bounded surf-composed resolution attempt and emit its outcome.

    Deterministic artifacts (pointer plan, dispatch plan) are written to
    ``out_dir``. The surf dispatch and post-dispatch observation run as real
    subprocesses through the sibling ``surf/run.sh``. The outcome receipt is
    written last so a failure can never masquerade as proof.
    """

    out = out_dir.expanduser()
    out.mkdir(parents=True, exist_ok=True)
    pointer_plan_path = out / "pointer-plan.json"
    dispatch_plan_path = out / "pointer-dispatch-plan.json"
    outcome_path = out / "captcha.resolution-outcome.json"

    pointer_plan = build_pointer_motion_plan(manifest, authorization, request)
    write_json_atomic(pointer_plan_path, pointer_plan.model_dump(mode="json"))
    dispatch_plan = build_pointer_dispatch_plan(
        manifest,
        authorization,
        pointer_plan,
        pointer_plan_path,
    )
    write_json_atomic(dispatch_plan_path, dispatch_plan.model_dump(mode="json"))
    dispatch_sha256 = sha256_file(dispatch_plan_path)

    surf = surf_run_path()
    if not surf.is_file() or not os.access(surf, os.X_OK):
        raise CaptchaSkillError(
            ErrorCode.SURF_UNAVAILABLE,
            "Surf run.sh is missing or not executable",
            {"path": str(surf)},
        )

    status: Literal["SOLVED", "NOT_SOLVED", "BLOCKED"]
    observation_passed: bool | None = None
    failure_code: str | None = None
    failure_message: str | None = None
    try:
        _run_surf_command(
            [str(surf), "pointer.dispatch", "--plan", str(pointer_plan_path), "--json"],
            cwd=surf.parent,
            timeout_seconds=60,
            operation="pointer.dispatch",
        )
        observed = _run_surf_command(
            [str(surf), "js", observe_js, "--tab-id", str(tab_id), "--json"],
            cwd=surf.parent,
            timeout_seconds=30,
            operation="js observe",
        )
        observation_passed = _extract_observation(observed)
        status = "SOLVED" if observation_passed else "NOT_SOLVED"
    except CaptchaSkillError as exc:
        status = "BLOCKED"
        failure_code = exc.code.value
        failure_message = exc.message

    outcome = ResolutionOutcome(
        schema_version="captcha.resolution_outcome.v1",
        status=status,
        target_url=str(manifest.target_url),
        tab_id=tab_id,
        pointer_plan_path="pointer-plan.json",
        dispatch_plan_path="pointer-dispatch-plan.json",
        dispatch_sha256=dispatch_sha256,
        observation_passed=observation_passed,
        failure_code=failure_code,
        failure_message=failure_message,
        created_at=utc_now(),
        evidence_sha256={
            "pointer-plan.json": sha256_file(pointer_plan_path),
            "pointer-dispatch-plan.json": sha256_file(dispatch_plan_path),
        },
        seam_validation=SeamValidation(kind="captcha.resolution_outcome"),
    )
    write_json_atomic(outcome_path, outcome.model_dump(mode="json"))
    return outcome, outcome_path


def post_human_alert(
    *,
    outcome_path: Path,
    channel: str,
    out_dir: Path,
    dry_run: bool = False,
) -> AlertReceipt:
    """Deliver a human notification through Surf's ``captcha.alert`` command.

    The alert is Surf-owned transport: captcha invokes the sibling Surf command,
    Surf builds the ops-buzz message and posts it, and the returned typed
    receipt is persisted beside the resolution outcome.
    """

    surf = surf_run_path()
    if not surf.is_file() or not os.access(surf, os.X_OK):
        raise CaptchaSkillError(
            ErrorCode.ALERT_DELIVERY_FAILED,
            "Surf run.sh is missing or not executable; human alert cannot be delivered",
            {"path": str(surf)},
        )
    receipt_path = out_dir / "surf.captcha-alert-receipt.json"
    argv = [
        str(surf),
        "captcha.alert",
        "--outcome",
        str(outcome_path.expanduser().resolve()),
        "--channel",
        channel,
        "--out",
        str(receipt_path.expanduser().resolve()),
    ]
    if dry_run:
        argv.append("--dry-run")
    try:
        value = _run_surf_command(
            argv,
            cwd=surf.parent,
            timeout_seconds=45,
            operation="captcha.alert",
        )
    except CaptchaSkillError as exc:
        raise CaptchaSkillError(
            ErrorCode.ALERT_DELIVERY_FAILED,
            "Surf alert command failed",
            {"surf_error_code": exc.code.value, "message": exc.message},
        ) from exc
    try:
        alert = AlertReceipt.model_validate(value)
    except ValidationError as exc:
        raise CaptchaSkillError(
            ErrorCode.ALERT_DELIVERY_FAILED,
            "Surf alert returned an invalid alert receipt",
            {"errors": exc.errors(include_url=False)},
        ) from exc
    return alert


def run_resolve_with_alert(
    manifest: AuthorizationManifest,
    authorization: AuthorizationReceipt,
    request: PointerMotionRequest,
    *,
    tab_id: int,
    observe_js: str,
    out_dir: Path,
    channel: str,
    alert_dry_run: bool = False,
) -> tuple[ResolutionOutcome, Path]:
    """Run the bounded resolution attempt and alert the human when it fails.

    The outcome is written first, then Surf's alert is invoked when the outcome
    is NOT_SOLVED or BLOCKED. The alert receipt is persisted and returned with
    the outcome so callers can prove delivery.
    """

    outcome, outcome_path = run_live_resolution(
        manifest,
        authorization,
        request,
        tab_id=tab_id,
        observe_js=observe_js,
        out_dir=out_dir,
    )
    if outcome.status in {"NOT_SOLVED", "BLOCKED"}:
        alert = post_human_alert(
            outcome_path=outcome_path,
            channel=channel,
            out_dir=out_dir,
            dry_run=alert_dry_run,
        )
        if alert.status == "BLOCKED":
            raise CaptchaSkillError(
                ErrorCode.ALERT_DELIVERY_FAILED,
                "CAPTCHA was not resolved and the human alert could not be delivered",
                {
                    "target_url": str(manifest.target_url),
                    "resolution_status": outcome.status,
                    "alert_message": alert.failure_message,
                },
            )
        alert_file = out_dir.expanduser() / "surf.captcha-alert-receipt.json"
        evidence = dict(outcome.evidence_sha256)
        if alert_file.is_file():
            evidence[alert_file.name] = sha256_file(alert_file)
        outcome.alert = alert
        outcome.evidence_sha256 = evidence
        write_json_atomic(outcome_path, outcome.model_dump(mode="json"))
    return outcome, outcome_path


__all__ = [
    "AlertReceipt",
    "ResolutionOutcome",
    "post_human_alert",
    "run_live_resolution",
    "run_resolve_with_alert",
]
