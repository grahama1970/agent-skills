"""Offline verification of CAPTCHA run receipts and cross-artifact truth.

Verification never contacts a target or re-runs ReCAP. It checks exact
run-relative hashes, typed seam contracts, authorization derivation, plan
integrity, and the bounded claim emitted from the ReCAP summary.
"""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from .constants import CAPTCHA_ENDPOINTS
from .errors import CaptchaSkillError, ErrorCode
from .layout import _is_relative_to, _safe_resolve, build_recap_argv
from .models import (
    AuthorizationManifest,
    AuthorizationReceipt,
    EvaluationAction,
    EvaluationPlan,
    ModelEndpointProof,
    RecapSummary,
    RunReceipt,
    RunStatus,
    RunStatusArtifact,
    SurfCapabilities,
    SurfTargetProof,
    TargetProof,
)
from .planning import compute_plan_hash
from .results import validate_recap_summary_for_manifest
from .policy import (
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
    utc_now,
    validate_authorization,
)

ModelT = TypeVar("ModelT", bound=BaseModel)
Mismatch = dict[str, str]


def _read_typed_json(path: Path, model: type[ModelT], *, label: str) -> ModelT:
    """Read one JSON artifact through its declared Pydantic seam model."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return model.model_validate(value)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        details: dict[str, Any] = {"path": str(path), "error": str(exc)}
        if isinstance(exc, ValidationError):
            details["errors"] = exc.errors(include_url=False)
        raise CaptchaSkillError(
            ErrorCode.RECEIPT_INVALID,
            f"{label} failed schema validation",
            details,
        ) from exc


def _resolve_declared_path(root: Path, raw_path: str, *, label: str) -> Path:
    """Resolve a canonical receipt path and require it to stay in this run."""

    relative = PurePosixPath(raw_path)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise CaptchaSkillError(
            ErrorCode.RECEIPT_INVALID,
            f"{label} is not a safe run-relative path",
            {"path": raw_path},
        )
    if relative.as_posix() != raw_path or "\\" in raw_path:
        raise CaptchaSkillError(
            ErrorCode.RECEIPT_INVALID,
            f"{label} is not in canonical POSIX form",
            {"path": raw_path, "canonical": relative.as_posix()},
        )
    resolved = _safe_resolve(root.joinpath(*relative.parts))
    if not _is_relative_to(resolved, root):
        raise CaptchaSkillError(
            ErrorCode.RECEIPT_INVALID,
            f"{label} resolves outside the run directory",
            {"path": raw_path, "run_dir": str(root)},
        )
    return resolved


def _record_mismatch(
    mismatches: list[Mismatch],
    *,
    file: str,
    expected: object,
    actual: object,
) -> None:
    mismatches.append(
        {"file": file, "expected": str(expected), "actual": str(actual)}
    )


def _verify_declared_paths(
    root: Path,
    receipt: RunReceipt,
    mismatches: list[Mismatch],
) -> tuple[dict[str, Path], Path | None]:
    fixed = {
        "authorization_receipt_path": "authorization-receipt.json",
        "plan_path": "plan.json",
        "surf_capabilities_path": "surf-capabilities.json",
        "surf_target_preflight_path": "surf-target-preflight.json",
        "target_preflight_path": "target-preflight.json",
        "model_endpoint_preflight_path": "model-endpoint-preflight.json",
        "stdout_path": "recap.stdout.log",
        "stderr_path": "recap.stderr.log",
    }
    resolved: dict[str, Path] = {}
    for field_name, expected_relative in fixed.items():
        raw = str(getattr(receipt, field_name))
        path = _resolve_declared_path(root, raw, label=field_name)
        resolved[field_name] = path
        if raw != expected_relative:
            _record_mismatch(
                mismatches,
                file=field_name,
                expected=expected_relative,
                actual=raw,
            )

    summary_path: Path | None = None
    if receipt.recap_summary_path is not None:
        raw_summary = receipt.recap_summary_path
        summary_path = _resolve_declared_path(
            root, raw_summary, label="recap_summary_path"
        )
        expected_summary_root = root / "recap-runs"
        if (
            not _is_relative_to(summary_path, expected_summary_root)
            or summary_path.name != "captcha-benchmark-results.json"
        ):
            _record_mismatch(
                mismatches,
                file="recap_summary_path",
                expected="recap-runs/<run>/captcha-benchmark-results.json",
                actual=raw_summary,
            )
    return resolved, summary_path


def _verify_evidence_hashes(
    root: Path,
    receipt: RunReceipt,
    mismatches: list[Mismatch],
) -> None:
    for key, expected in sorted(receipt.evidence_sha256.items()):
        path = _resolve_declared_path(root, key, label="evidence_sha256 key")
        if not path.is_file():
            _record_mismatch(
                mismatches, file=key, expected=expected, actual="missing"
            )
            continue
        actual = sha256_file(path)
        if actual != expected:
            _record_mismatch(
                mismatches, file=key, expected=expected, actual=actual
            )

    required = {
        "request.json",
        "authorization-receipt.json",
        "plan.json",
        "events.jsonl",
    }
    for key in sorted(required - receipt.evidence_sha256.keys()):
        _record_mismatch(
            mismatches,
            file=key,
            expected="hash-bound evidence",
            actual="unbound",
        )


def _verify_authorization_and_plan(
    root: Path,
    mismatches: list[Mismatch],
) -> tuple[AuthorizationManifest, AuthorizationReceipt, EvaluationPlan]:
    manifest = _read_typed_json(
        root / "request.json",
        AuthorizationManifest,
        label="authorization manifest",
    )
    authorization = _read_typed_json(
        root / "authorization-receipt.json",
        AuthorizationReceipt,
        label="authorization receipt",
    )
    plan = _read_typed_json(
        root / "plan.json", EvaluationPlan, label="evaluation plan"
    )

    manifest_hash = sha256_bytes(
        canonical_json_bytes(manifest.model_dump(mode="json"))
    )
    if authorization.manifest_sha256 != manifest_hash:
        _record_mismatch(
            mismatches,
            file="authorization-receipt.json#manifest_sha256",
            expected=manifest_hash,
            actual=authorization.manifest_sha256,
        )
    try:
        expected_authorization = validate_authorization(
            manifest,
            manifest_sha256=manifest_hash,
            required_action=EvaluationAction.EVALUATE,
            now=authorization.validated_at,
        )
    except CaptchaSkillError as exc:
        _record_mismatch(
            mismatches,
            file="authorization-receipt.json",
            expected="authorization policy PASS",
            actual=exc,
        )
    else:
        if expected_authorization.model_dump(mode="json") != authorization.model_dump(
            mode="json"
        ):
            _record_mismatch(
                mismatches,
                file="authorization-receipt.json",
                expected="exact receipt derived from request.json",
                actual="semantic mismatch",
            )

    if plan.authorization.model_dump(mode="json") != authorization.model_dump(
        mode="json"
    ):
        _record_mismatch(
            mismatches,
            file="plan.json#authorization",
            expected="exact authorization-receipt.json",
            actual="semantic mismatch",
        )
    computed_plan_hash = compute_plan_hash(plan.model_dump(mode="json"))
    if computed_plan_hash != plan.plan_sha256:
        _record_mismatch(
            mismatches,
            file="plan.json#plan_sha256",
            expected=computed_plan_hash,
            actual=plan.plan_sha256,
        )

    expected_argv = build_recap_argv(
        manifest,
        recap_root=Path(plan.recap.checkout_root),
        recap_python=Path(plan.recap.runtime_python),
    )
    if plan.execution.argv != expected_argv:
        _record_mismatch(
            mismatches,
            file="plan.json#execution.argv",
            expected=json.dumps(expected_argv),
            actual=json.dumps(plan.execution.argv),
        )
    expected_cwd = _safe_resolve(
        Path(plan.recap.checkout_root) / "captcha_eval_framework"
    )
    if _safe_resolve(Path(plan.execution.cwd)) != expected_cwd:
        _record_mismatch(
            mismatches,
            file="plan.json#execution.cwd",
            expected=expected_cwd,
            actual=plan.execution.cwd,
        )
    if _safe_resolve(Path(plan.execution.output_root)) != root.parent:
        _record_mismatch(
            mismatches,
            file="plan.json#execution.output_root",
            expected=root.parent,
            actual=plan.execution.output_root,
        )
    if plan.execution.timeout_seconds != manifest.timeout_seconds:
        _record_mismatch(
            mismatches,
            file="plan.json#execution.timeout_seconds",
            expected=manifest.timeout_seconds,
            actual=plan.execution.timeout_seconds,
        )
    if plan.readiness is not RunStatus.PASS:
        _record_mismatch(
            mismatches,
            file="plan.json#readiness",
            expected=RunStatus.PASS.value,
            actual=plan.readiness.value,
        )
    return manifest, authorization, plan


def _verify_pass_contracts(
    root: Path,
    receipt: RunReceipt,
    manifest: AuthorizationManifest,
    resolved_paths: dict[str, Path],
    summary_path: Path | None,
    mismatches: list[Mismatch],
) -> None:
    required = {
        "surf-capabilities.json",
        "surf-target-preflight.json",
        "surf-target-preflight.png",
        "target-preflight.json",
        "model-endpoint-preflight.json",
        "recap.stdout.log",
        "recap.stderr.log",
    }
    if summary_path is not None:
        required.add(summary_path.relative_to(root).as_posix())
    for key in sorted(required - receipt.evidence_sha256.keys()):
        _record_mismatch(
            mismatches,
            file=key,
            expected="hash-bound evidence",
            actual="unbound",
        )

    capabilities = _read_typed_json(
        resolved_paths["surf_capabilities_path"],
        SurfCapabilities,
        label="Surf capabilities",
    )
    if not capabilities.engine.dist_present or not capabilities.engine.lock_present:
        _record_mismatch(
            mismatches,
            file="surf-capabilities.json#engine",
            expected="dist_present=true, lock_present=true",
            actual=(
                f"dist_present={capabilities.engine.dist_present}, "
                f"lock_present={capabilities.engine.lock_present}"
            ),
        )
    if not (
        capabilities.transport.extension_socket_present
        or capabilities.transport.cdp_fallback
    ):
        _record_mismatch(
            mismatches,
            file="surf-capabilities.json#transport",
            expected="extension socket or CDP fallback",
            actual="neither",
        )

    surf_target = _read_typed_json(
        resolved_paths["surf_target_preflight_path"],
        SurfTargetProof,
        label="Surf target preflight",
    )
    probe_type = (
        manifest.captcha_name.value
        if manifest.test_mode.value == "custom" and manifest.captcha_name is not None
        else "text"
    )
    expected_target_url = (
        f"{str(manifest.target_url).rstrip('/')}"
        f"{CAPTCHA_ENDPOINTS[probe_type]}"
    )
    if (
        surf_target.challenge_url != expected_target_url
        or surf_target.final_url.rstrip("/") != expected_target_url.rstrip("/")
        or not surf_target.challenge_id_present
    ):
        _record_mismatch(
            mismatches,
            file="surf-target-preflight.json",
            expected=f"isolated Surf proof for {expected_target_url}",
            actual=(
                f"challenge_url={surf_target.challenge_url}, "
                f"final_url={surf_target.final_url}, "
                f"challenge_id_present={surf_target.challenge_id_present}"
            ),
        )
    surf_screenshot = _resolve_declared_path(
        root, surf_target.screenshot_path, label="Surf target screenshot"
    )
    if not surf_screenshot.is_file():
        _record_mismatch(
            mismatches,
            file=surf_target.screenshot_path,
            expected="present",
            actual="missing",
        )
    else:
        actual_screenshot_sha = sha256_file(surf_screenshot)
        if actual_screenshot_sha != surf_target.screenshot_sha256:
            _record_mismatch(
                mismatches,
                file=surf_target.screenshot_path,
                expected=surf_target.screenshot_sha256,
                actual=actual_screenshot_sha,
            )

    target = _read_typed_json(
        resolved_paths["target_preflight_path"],
        TargetProof,
        label="target preflight",
    )
    if (
        target.url != expected_target_url
        or target.status_code != 200
        or not target.challenge_marker_present
    ):
        _record_mismatch(
            mismatches,
            file="target-preflight.json",
            expected=f"HTTP 200 ReCAP marker at {expected_target_url}",
            actual=(
                f"url={target.url}, status={target.status_code}, "
                f"marker={target.challenge_marker_present}"
            ),
        )

    model_endpoint = _read_typed_json(
        resolved_paths["model_endpoint_preflight_path"],
        ModelEndpointProof,
        label="model endpoint preflight",
    )
    expected_model_url = f"{str(manifest.model_base_url).rstrip('/')}/models"
    if (
        model_endpoint.url != expected_model_url
        or model_endpoint.requested_model_id != manifest.model_id
        or manifest.model_id not in model_endpoint.advertised_model_ids
    ):
        _record_mismatch(
            mismatches,
            file="model-endpoint-preflight.json",
            expected=f"exact model {manifest.model_id} at {expected_model_url}",
            actual=(
                f"url={model_endpoint.url}, requested="
                f"{model_endpoint.requested_model_id}, "
                f"advertised={model_endpoint.advertised_model_ids}"
            ),
        )

    if summary_path is None:
        _record_mismatch(
            mismatches,
            file="recap_summary_path",
            expected="present",
            actual="missing",
        )
        return
    summary = _read_typed_json(summary_path, RecapSummary, label="ReCAP summary")
    try:
        validate_recap_summary_for_manifest(summary, manifest)
    except CaptchaSkillError as exc:
        _record_mismatch(
            mismatches,
            file=summary_path.relative_to(root).as_posix(),
            expected="summary matches authorized provider, task set, attempts, and budgets",
            actual=exc,
        )
    total = summary.overall_stats.total_captchas
    if len(summary.tasks) != total:
        _record_mismatch(
            mismatches,
            file=summary_path.relative_to(root).as_posix(),
            expected=total,
            actual=len(summary.tasks),
        )
    expected_tasks = 7 if manifest.test_mode.value == "once" else manifest.test_size
    if total != expected_tasks:
        _record_mismatch(
            mismatches,
            file=f"{summary_path.relative_to(root).as_posix()}#total_captchas",
            expected=expected_tasks,
            actual=total,
        )
    expected_claim = (
        "The pinned ReCAP agent solved "
        f"{summary.overall_stats.total_solved} of {total} authorized "
        "synthetic dynamic CAPTCHA tasks in this run."
    )
    if receipt.claims != [expected_claim]:
        _record_mismatch(
            mismatches,
            file="captcha.run-receipt.json#claims",
            expected=expected_claim,
            actual=json.dumps(receipt.claims),
        )


def verify_run(run_dir: Path) -> dict[str, Any]:
    """Verify hashes and semantic contracts without re-running the benchmark."""

    root = _safe_resolve(run_dir)
    if not root.is_dir():
        raise CaptchaSkillError(
            ErrorCode.RECEIPT_INVALID,
            "run directory does not exist",
            {"run_dir": str(root)},
        )
    receipt_path = root / "captcha.run-receipt.json"
    receipt = _read_typed_json(receipt_path, RunReceipt, label="run receipt")
    status_artifact = _read_typed_json(
        root / "status.json",
        RunStatusArtifact,
        label="run status",
    )

    mismatches: list[Mismatch] = []
    receipt_digest = sha256_file(receipt_path)
    if status_artifact.status is not receipt.status:
        _record_mismatch(
            mismatches,
            file="status.json#status",
            expected=receipt.status.value,
            actual=status_artifact.status.value,
        )
    if status_artifact.phase != "complete":
        _record_mismatch(
            mismatches,
            file="status.json#phase",
            expected="complete",
            actual=status_artifact.phase,
        )
    if status_artifact.receipt_path != receipt_path.name:
        _record_mismatch(
            mismatches,
            file="status.json#receipt_path",
            expected=receipt_path.name,
            actual=status_artifact.receipt_path,
        )
    if status_artifact.receipt_sha256 != receipt_digest:
        _record_mismatch(
            mismatches,
            file="status.json#receipt_sha256",
            expected=receipt_digest,
            actual=status_artifact.receipt_sha256,
        )
    if status_artifact.failure_code != receipt.failure_code:
        _record_mismatch(
            mismatches,
            file="status.json#failure_code",
            expected=receipt.failure_code,
            actual=status_artifact.failure_code,
        )
    resolved_paths, summary_path = _verify_declared_paths(
        root, receipt, mismatches
    )
    _verify_evidence_hashes(root, receipt, mismatches)
    manifest, _authorization, _plan = _verify_authorization_and_plan(
        root, mismatches
    )
    if receipt.status is RunStatus.PASS:
        _verify_pass_contracts(
            root,
            receipt,
            manifest,
            resolved_paths,
            summary_path,
            mismatches,
        )

    if mismatches:
        raise CaptchaSkillError(
            ErrorCode.RECEIPT_INVALID,
            "run evidence or cross-artifact truth does not match the receipt",
            {"mismatches": mismatches},
        )
    return {
        "schema_version": "captcha.verify_receipt.v1",
        "status": "PASS",
        "verified_at": utc_now().isoformat(),
        "run_id": receipt.run_id,
        "run_status": receipt.status.value,
        "receipt_path": str(receipt_path),
        "evidence_files_verified": len(receipt.evidence_sha256),
        "semantic_contracts_verified": [
            "authorization_manifest",
            "authorization_receipt",
            "evaluation_plan",
            "run_status_receipt_binding",
            "exact_evidence_paths",
            *(
                [
                    "surf_capabilities",
                    "surf_target_preflight",
                    "target_preflight",
                    "model_endpoint_preflight",
                    "recap_summary",
                    "bounded_claim",
                ]
                if receipt.status is RunStatus.PASS
                else []
            ),
        ],
        "seam_validation": {"kind": "captcha.verify_run", "status": "PASS"},
    }
