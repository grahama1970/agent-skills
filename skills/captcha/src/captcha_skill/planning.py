"""Typed evaluation-plan compilation and Ask DAG composition.

Planning performs no target/model network calls. It validates local source,
runtime, storage, Surf, and secret-presence prerequisites, then emits an exact
argv/environment allowlist and a hash-bound plan.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .dotenv_helper import load_skill_dotenv
from .constants import (
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_RECAP_ROOT,
    DEFAULT_STORAGE_ROOT,
    LOCAL_MODEL_API_KEY_ENV,
    RECAP_FIXED_ENV_KEYS,
    RECAP_PASSTHROUGH_ENV_KEYS,
    RECAP_SECRET_ENV_KEYS,
    SURF_CAPABILITIES_SCHEMA,
)
from .errors import CaptchaSkillError
from .layout import (
    _is_relative_to,
    _lexical_absolute,
    _safe_resolve,
    build_recap_argv,
    default_recap_python,
    surf_run_path,
    validate_recap_runtime,
)
from .models import (
    ArtifactContract,
    AskDag,
    AskDagNode,
    AskDagNodeInput,
    AuthorizationManifest,
    AuthorizationReceipt,
    EvaluationPlan,
    ExecutionSpec,
    RecapBinding,
    RunStatus,
    SeamValidation,
    SurfBinding,
)
from .policy import canonical_json_bytes, sha256_bytes, utc_now

load_skill_dotenv()


def compute_plan_hash(plan: dict[str, Any]) -> str:
    """Hash a plan with its digest field normalized to zeroes."""

    core = dict(plan)
    core.pop("plan_sha256", None)
    return sha256_bytes(canonical_json_bytes(core))


def build_evaluation_plan(
    manifest: AuthorizationManifest,
    authorization: AuthorizationReceipt,
    *,
    recap_root: Path = DEFAULT_RECAP_ROOT,
    recap_python: Path | None = None,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> EvaluationPlan:
    """Build a typed plan and truthfully report dependency readiness."""

    recap = _safe_resolve(recap_root)
    runtime_python = _lexical_absolute(recap_python or default_recap_python(recap))
    output = _safe_resolve(output_root)
    surf = surf_run_path()
    argv = build_recap_argv(manifest, recap_root=recap, recap_python=runtime_python)

    blockers: list[str] = []
    try:
        validate_recap_runtime(recap, runtime_python)
    except CaptchaSkillError as exc:
        blockers.append(str(exc))
    if not surf.is_file() or not os.access(surf, os.X_OK):
        blockers.append("surf_unavailable: Surf run.sh is missing or not executable")
    storage_root = _safe_resolve(DEFAULT_STORAGE_ROOT)
    if not storage_root.is_dir():
        blockers.append(f"io_error: storage root does not exist: {storage_root}")
    if not _is_relative_to(output, storage_root):
        blockers.append(f"io_error: output_root must be under {storage_root}")
    if not os.environ.get(LOCAL_MODEL_API_KEY_ENV, "").strip():
        blockers.append(
            f"model_credential_missing: {LOCAL_MODEL_API_KEY_ENV} is not set"
        )

    plan_id = f"captcha-{authorization.authorization_id}-{authorization.manifest_sha256[:12]}"
    plan_data: dict[str, Any] = {
        "schema_version": "captcha.evaluation_plan.v1",
        "plan_id": plan_id,
        "created_at": utc_now(),
        "readiness": RunStatus.PASS if not blockers else RunStatus.NEEDS_ATTENTION,
        "blockers": blockers,
        "authorization": authorization,
        "recap": RecapBinding(
            checkout_root=str(recap),
            framework_main=str(recap / "captcha_eval_framework" / "main.py"),
            runtime_python=str(runtime_python),
        ),
        "surf": SurfBinding(
            command=[str(surf), "capabilities", "--json"],
            expected_schema=SURF_CAPABILITIES_SCHEMA,
        ),
        "execution": ExecutionSpec(
            argv=argv,
            cwd=str(recap / "captcha_eval_framework"),
            timeout_seconds=manifest.timeout_seconds,
            output_root=str(output),
            environment_keys=sorted(
                set(RECAP_PASSTHROUGH_ENV_KEYS) | set(RECAP_FIXED_ENV_KEYS)
            ),
            secret_environment_keys=list(RECAP_SECRET_ENV_KEYS),
        ),
        "artifact_contract": ArtifactContract(
            required_files=[
                "request.json",
                "authorization-receipt.json",
                "plan.json",
                "surf-capabilities.json",
                "surf-target-preflight.json",
                "surf-target-preflight.png",
                "target-preflight.json",
                "model-endpoint-preflight.json",
                "events.jsonl",
                "status.json",
                "recap.stdout.log",
                "recap.stderr.log",
                "captcha.run-receipt.json",
            ],
            generated_files=[
                "recap-runs/*/run-configuration.json",
                "recap-runs/*/captcha-benchmark-results.json",
                "recap-runs/*/unified-benchmark-test.log",
                "recap-runs/*/img/*.png",
            ],
            heavy_artifacts_policy=(
                "All benchmark outputs remain under /mnt/storage12tb/skills/captcha."
            ),
        ),
        "plan_sha256": "0" * 64,
        "seam_validation": (
            SeamValidation(kind="captcha.evaluation_plan") if not blockers else None
        ),
    }
    serializable = {
        key: (value.model_dump(mode="json") if hasattr(value, "model_dump") else value)
        for key, value in plan_data.items()
    }
    serializable["created_at"] = plan_data["created_at"].isoformat()
    serializable["readiness"] = plan_data["readiness"].value
    plan_data["plan_sha256"] = compute_plan_hash(serializable)
    return EvaluationPlan.model_validate(plan_data)


def build_ask_dag(
    *,
    manifest_path: Path,
    recap_root: Path,
    recap_python: Path,
    output_root: Path,
    timeout_seconds: int,
) -> AskDag:
    """Emit an Ask-owned DAG that invokes this skill through ``skill.run``."""

    args = [
        "evaluate",
        "--manifest",
        str(_safe_resolve(manifest_path)),
        "--recap-root",
        str(_safe_resolve(recap_root)),
        "--recap-python",
        str(_lexical_absolute(recap_python)),
        "--output-root",
        str(_safe_resolve(output_root)),
        "--execute",
        "--json",
    ]
    return AskDag(
        schema_version="ask.dag.v1",
        graph_id="captcha-authorized-local-recap-evaluation",
        description=(
            "Ask orchestrates one authorization-gated captcha skill run; captcha "
            "validates policy, Surf capabilities, and exact local target identity "
            "before invoking pinned ReCAP."
        ),
        nodes=[
            AskDagNode(
                input=AskDagNodeInput(
                    args=args,
                    timeout=min(7200, max(30, timeout_seconds + 120)),
                )
            )
        ],
    )
