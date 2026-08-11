"""Typed contracts for CAPTCHA authorization, plans, Surf proof, and receipts.

Inputs arrive from JSON manifests, Surf, Ask, the ReCAP subprocess, and durable
run artifacts. Pydantic validates each boundary before business logic consumes
it. Authorization and captcha-owned artifacts reject unknown fields; upstream
Surf payloads accept additional producer fields while requiring a strict typed
subset.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Any, Literal

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from .constants import CAPTCHA_TYPES, RECAP_COMMIT, RECAP_REPOSITORY


class StrictModel(BaseModel):
    """Captcha-owned model that rejects unknown fields."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class AllowExtraModel(BaseModel):
    """Typed subset for a versioned producer that may add compatible fields."""

    model_config = ConfigDict(extra="allow", validate_assignment=True)


class EvaluationAction(StrEnum):
    STATUS = "status"
    PLAN = "plan"
    EVALUATE = "evaluate"
    VERIFY = "verify"
    ASK_DAG = "ask-dag"


class TestMode(StrEnum):
    ONCE = "once"
    CUSTOM = "custom"


class CaptchaType(StrEnum):
    TEXT = "text"
    COMPACT_TEXT = "compact_text"
    ICON_SELECTION = "icon_selection"
    ICON_MATCH = "icon_match"
    SLIDER = "slider"
    IMAGE_GRID = "image_grid"
    PAGED = "paged"


class ModelFamily(StrEnum):
    QWEN3 = "qwen3"


class RunStatus(StrEnum):
    PASS = "PASS"
    BLOCKED = "BLOCKED"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    NOT_ESTABLISHED = "NOT_ESTABLISHED"


class BoundedJudgment(StrEnum):
    CAPABILITY_MEASURED = "CAPABILITY_MEASURED"
    NOT_MEASURED = "NOT_MEASURED"


class Acknowledgements(StrictModel):
    owns_or_controls_target: bool
    local_synthetic_only: bool
    no_third_party_bypass: bool
    defensive_or_research_use: bool


class AuthorizationManifest(StrictModel):
    """Authorization required before planning or executing a ReCAP run."""

    schema_version: Literal["captcha.target_authorization.v1"]
    authorization_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    project: str = Field(min_length=1, max_length=200)
    operator: str = Field(min_length=1, max_length=200)
    purpose: str = Field(min_length=10, max_length=1000)
    target_url: AnyHttpUrl
    model_base_url: AnyHttpUrl
    model_id: Literal[
        "ReCAP-Agent/ReCAP-8B",
        "ReCAP-Agent/ReCAP-32B",
    ] = "ReCAP-Agent/ReCAP-8B"
    model_family: ModelFamily = ModelFamily.QWEN3
    provider: Literal["dynamic"] = "dynamic"
    test_mode: TestMode = TestMode.ONCE
    captcha_name: CaptchaType | None = None
    test_size: int = Field(default=1, ge=1, le=50)
    seed: int = Field(default=42, ge=0, le=2_147_483_647)
    workers: int = Field(default=1, ge=1, le=2)
    max_calls: int = Field(default=4, ge=1, le=8)
    max_tasks: int = Field(default=7, ge=1, le=50)
    timeout_seconds: int = Field(default=1800, ge=30, le=3600)
    allowed_actions: set[EvaluationAction] = Field(min_length=1)
    allowed_captcha_types: set[CaptchaType] = Field(
        default_factory=lambda: {CaptchaType(item) for item in CAPTCHA_TYPES},
        min_length=1,
    )
    recap_commit: Literal[RECAP_COMMIT] = RECAP_COMMIT
    expires_at: datetime
    acknowledgements: Acknowledgements

    @field_serializer("allowed_actions", "allowed_captcha_types")
    def serialize_enum_sets(self, value: set[StrEnum]) -> list[str]:
        """Serialize authorization sets in deterministic lexical order."""

        return sorted(item.value for item in value)

    @model_validator(mode="after")
    def validate_task_selection(self) -> "AuthorizationManifest":
        """Keep ReCAP task selection and authorization scope exactly aligned."""

        all_types = {CaptchaType(item) for item in CAPTCHA_TYPES}
        if self.test_mode is TestMode.ONCE:
            if self.captcha_name is not None:
                raise ValueError("captcha_name must be omitted when test_mode is once")
            if self.max_tasks != len(CAPTCHA_TYPES):
                raise ValueError(f"once mode requires max_tasks == {len(CAPTCHA_TYPES)}")
            if self.allowed_captcha_types != all_types:
                raise ValueError("once mode requires authorization for all seven CAPTCHA types")
        elif self.test_mode is TestMode.CUSTOM:
            if self.captcha_name is None:
                raise ValueError("custom mode requires captcha_name")
            if self.captcha_name not in self.allowed_captcha_types:
                raise ValueError("captcha_name is outside allowed_captcha_types")
            if self.test_size > self.max_tasks:
                raise ValueError("test_size exceeds max_tasks")
        return self


class SeamValidation(StrictModel):
    kind: str = Field(min_length=1, max_length=120)
    status: Literal["PASS"] = "PASS"


class AuthorizationReceipt(StrictModel):
    schema_version: Literal["captcha.authorization_receipt.v1"]
    authorization_id: str
    action: EvaluationAction
    status: Literal["PASS"] = "PASS"
    validated_at: datetime
    expires_at: datetime
    manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    target_url: str
    model_base_url: str
    provider: Literal["dynamic"] = "dynamic"
    policy_version: str
    limitations: list[str]
    seam_validation: SeamValidation

    @model_validator(mode="after")
    def validate_truthfulness(self) -> "AuthorizationReceipt":
        if self.expires_at <= self.validated_at:
            raise ValueError("authorization receipt must be validated before expiry")
        if not self.limitations:
            raise ValueError("authorization receipt requires explicit limitations")
        return self


class RecapBinding(StrictModel):
    repository: Literal[RECAP_REPOSITORY] = RECAP_REPOSITORY
    commit: Literal[RECAP_COMMIT] = RECAP_COMMIT
    checkout_root: str
    framework_main: str
    runtime_python: str
    provider: Literal["dynamic"] = "dynamic"
    model_family: Literal["qwen3"] = "qwen3"


class SurfBinding(StrictModel):
    command: list[str]
    expected_schema: Literal["surf.capabilities.v1"] = "surf.capabilities.v1"
    required: Literal[True] = True
    role: Literal["browser_transport_and_target_identity_proof"] = (
        "browser_transport_and_target_identity_proof"
    )


class ExecutionSpec(StrictModel):
    argv: list[str]
    cwd: str
    timeout_seconds: int
    output_root: str
    environment_keys: list[str]
    secret_environment_keys: list[str]
    shell: Literal[False] = False


class ArtifactContract(StrictModel):
    required_files: list[str]
    generated_files: list[str]
    heavy_artifacts_policy: str


class EvaluationPlan(StrictModel):
    schema_version: Literal["captcha.evaluation_plan.v1"]
    plan_id: str
    created_at: datetime
    readiness: RunStatus
    blockers: list[str]
    authorization: AuthorizationReceipt
    recap: RecapBinding
    surf: SurfBinding
    execution: ExecutionSpec
    artifact_contract: ArtifactContract
    plan_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    seam_validation: SeamValidation | None = None

    @model_validator(mode="after")
    def validate_readiness_truth(self) -> "EvaluationPlan":
        if self.readiness is RunStatus.PASS:
            if self.blockers:
                raise ValueError("PASS plan cannot contain blockers")
            if self.seam_validation is None:
                raise ValueError("PASS plan requires seam_validation")
        else:
            if not self.blockers:
                raise ValueError("non-PASS plan requires blockers")
            if self.seam_validation is not None:
                raise ValueError("non-PASS plan cannot carry a PASS seam stamp")
        return self


class RecapRuntimeProbe(StrictModel):
    schema_version: Literal["captcha.recap_runtime_probe.v1"]
    executable: str
    prefix: str
    base_prefix: str
    version: tuple[int, int, int]


class SurfSkillIdentity(AllowExtraModel):
    name: Literal["surf"]
    path: str
    skill_md_sha256: str | None
    contract_references: list[str]


class SurfEngine(AllowExtraModel):
    kind: Literal["vendored_surf_cli"]
    package_version: str | None
    path: str
    dist_present: bool
    dist_fresh: bool | None = None
    lock_present: bool
    content_identity_matches: bool | None = None


class SurfTransport(AllowExtraModel):
    extension_socket_path: str
    extension_socket_present: bool
    cdp_fallback: bool


class SurfContracts(AllowExtraModel):
    capabilities_schema: Literal["surf.capabilities.v1"]
    provider_result_schema: Literal["surf.provider_result.v1"]
    immutable_submit_schema: Literal["surf.immutable_submit.v1"]
    vendor_update_gate: Literal["surf.vendor_update_gate.v1"]


class SurfCapabilities(AllowExtraModel):
    """Typed subset of Surf's versioned capabilities contract."""

    model_config = ConfigDict(extra="allow", populate_by_name=True, validate_assignment=True)

    contract_schema: Literal["surf.capabilities.v1"] = Field(alias="schema")
    schema_version: str
    skill: SurfSkillIdentity
    engine: SurfEngine
    transport: SurfTransport
    providers: dict[str, Any]
    contracts: SurfContracts


class TargetProof(StrictModel):
    schema_version: Literal["captcha.target_preflight.v1"]
    checked_at: datetime
    url: str
    status_code: int = Field(ge=100, le=599)
    content_type: str | None
    body_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    challenge_marker_present: bool
    status: Literal["PASS"] = "PASS"
    seam_validation: SeamValidation


class SurfTargetProof(StrictModel):
    """Surf-created browser proof for the exact local synthetic target."""

    schema_version: Literal["captcha.surf_target_preflight.v1"]
    checked_at: datetime
    challenge_url: str
    final_url: str
    tab_id: int = Field(gt=0)
    challenge_id_present: Literal[True] = True
    screenshot_path: Literal["surf-target-preflight.png"] = "surf-target-preflight.png"
    screenshot_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: Literal["PASS"] = "PASS"
    seam_validation: SeamValidation


class ModelEndpointProof(StrictModel):
    schema_version: Literal["captcha.model_endpoint_preflight.v1"]
    checked_at: datetime
    url: str
    requested_model_id: str
    advertised_model_ids: list[str]
    response_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    exact_model_match: Literal[True] = True
    status: Literal["PASS"] = "PASS"
    seam_validation: SeamValidation


class RecapOverallStats(StrictModel):
    total_captchas: int = Field(ge=0, le=50)
    total_solved: int = Field(ge=0, le=50)
    overall_success_rate: float = Field(ge=0, le=100)
    average_solve_steps: float | None = Field(default=None, ge=0, le=8)

    @model_validator(mode="after")
    def validate_counts(self) -> "RecapOverallStats":
        if self.total_solved > self.total_captchas:
            raise ValueError("total_solved cannot exceed total_captchas")
        expected_rate = (
            (self.total_solved / self.total_captchas) * 100
            if self.total_captchas
            else 0.0
        )
        if not math.isclose(self.overall_success_rate, expected_rate, abs_tol=1e-9):
            raise ValueError("overall_success_rate disagrees with total counts")
        return self


class RecapTypeStats(StrictModel):
    individual_results: list[bool]
    solved_count: int = Field(ge=0, le=50)
    total_count: int = Field(ge=0, le=50)
    success_rate: float = Field(ge=0, le=100)
    average_solve_steps: float | None = Field(default=None, ge=0, le=8)

    @model_validator(mode="after")
    def validate_counts(self) -> "RecapTypeStats":
        solved = sum(self.individual_results)
        if self.total_count != len(self.individual_results):
            raise ValueError("total_count disagrees with individual_results")
        if self.solved_count != solved:
            raise ValueError("solved_count disagrees with individual_results")
        expected_rate = (solved / self.total_count) * 100 if self.total_count else 0.0
        if not math.isclose(self.success_rate, expected_rate, abs_tol=1e-9):
            raise ValueError("success_rate disagrees with individual_results")
        return self


class RecapTaskResult(StrictModel):
    task_id: str = Field(min_length=1, max_length=300)
    provider_name: Literal["dynamic"]
    requested_type: CaptchaType
    resolved_type: CaptchaType
    sample_id: int | None = None
    attempt: int = Field(ge=1, le=50)
    solved: bool
    calls_made: int = Field(ge=0, le=8)
    finished_flag: bool
    solve_step: int | None = Field(default=None, ge=1, le=8)
    error: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def validate_outcome(self) -> "RecapTaskResult":
        if self.solved and self.solve_step is None:
            raise ValueError("solved task requires solve_step")
        if not self.solved and self.solve_step is not None:
            raise ValueError("unsolved task cannot carry solve_step")
        if self.solve_step is not None and self.solve_step > self.calls_made:
            raise ValueError("solve_step cannot exceed calls_made")
        return self


class RecapSummary(StrictModel):
    overall_stats: RecapOverallStats
    by_type: dict[CaptchaType, RecapTypeStats]
    tasks: list[RecapTaskResult] = Field(max_length=50)

    @model_validator(mode="after")
    def validate_aggregate_truth(self) -> "RecapSummary":
        if self.overall_stats.total_captchas != len(self.tasks):
            raise ValueError("overall total_captchas disagrees with task records")
        solved = sum(task.solved for task in self.tasks)
        if self.overall_stats.total_solved != solved:
            raise ValueError("overall total_solved disagrees with task records")
        if len({task.task_id for task in self.tasks}) != len(self.tasks):
            raise ValueError("task_id values must be unique")

        grouped: dict[CaptchaType, list[RecapTaskResult]] = defaultdict(list)
        for task in self.tasks:
            grouped[task.resolved_type].append(task)
        if set(self.by_type) != set(grouped):
            raise ValueError("by_type keys disagree with task resolved_type values")
        for captcha_type, tasks in grouped.items():
            stats = self.by_type[captcha_type]
            outcomes = [task.solved for task in tasks]
            if stats.individual_results != outcomes:
                raise ValueError(f"{captcha_type.value} individual_results disagree with tasks")
            solved_steps = [task.solve_step for task in tasks if task.solve_step is not None]
            expected_average = (
                sum(solved_steps) / len(solved_steps) if solved_steps else None
            )
            if expected_average is None:
                if stats.average_solve_steps is not None:
                    raise ValueError(f"{captcha_type.value} average_solve_steps must be null")
            elif stats.average_solve_steps is None or not math.isclose(
                stats.average_solve_steps,
                expected_average,
                abs_tol=1e-9,
            ):
                raise ValueError(f"{captcha_type.value} average_solve_steps disagree")

        solved_steps = [task.solve_step for task in self.tasks if task.solve_step is not None]
        expected_overall_average = (
            sum(solved_steps) / len(solved_steps) if solved_steps else None
        )
        if expected_overall_average is None:
            if self.overall_stats.average_solve_steps is not None:
                raise ValueError("overall average_solve_steps must be null")
        elif self.overall_stats.average_solve_steps is None or not math.isclose(
            self.overall_stats.average_solve_steps,
            expected_overall_average,
            abs_tol=1e-9,
        ):
            raise ValueError("overall average_solve_steps disagree with task records")
        return self


class RunReceipt(StrictModel):
    schema_version: Literal["captcha.run_receipt.v1"]
    run_id: str = Field(min_length=1, max_length=200)
    status: RunStatus
    started_at: datetime
    finished_at: datetime
    authorization_receipt_path: Literal["authorization-receipt.json"]
    plan_path: Literal["plan.json"]
    surf_capabilities_path: Literal["surf-capabilities.json"]
    surf_target_preflight_path: Literal["surf-target-preflight.json"]
    target_preflight_path: Literal["target-preflight.json"]
    model_endpoint_preflight_path: Literal["model-endpoint-preflight.json"]
    recap_summary_path: str | None
    stdout_path: Literal["recap.stdout.log"]
    stderr_path: Literal["recap.stderr.log"]
    exit_code: int | None
    bounded_judgment: BoundedJudgment
    claims: list[str]
    limitations: list[str]
    evidence_sha256: dict[str, str]
    failure_code: str | None = None
    failure_message: str | None = None
    seam_validation: SeamValidation | None = None

    @field_validator("recap_summary_path")
    @classmethod
    def validate_summary_path(cls, value: str | None) -> str | None:
        if value is None:
            return value
        relative = PurePosixPath(value)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or relative.as_posix() != value
            or "\\" in value
            or len(relative.parts) < 3
            or relative.parts[0] != "recap-runs"
            or relative.name != "captcha-benchmark-results.json"
        ):
            raise ValueError(
                "recap_summary_path must match "
                "recap-runs/<run>/captcha-benchmark-results.json"
            )
        return value

    @field_validator("evidence_sha256")
    @classmethod
    def validate_evidence_map(cls, value: dict[str, str]) -> dict[str, str]:
        for key, digest in value.items():
            relative = PurePosixPath(key)
            if (
                relative.is_absolute()
                or not relative.parts
                or ".." in relative.parts
                or relative.as_posix() != key
                or "\\" in key
            ):
                raise ValueError(f"unsafe evidence path: {key}")
            if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                raise ValueError(f"invalid SHA-256 digest for evidence path: {key}")
        return value

    @model_validator(mode="after")
    def validate_truthfulness(self) -> "RunReceipt":
        if self.finished_at < self.started_at:
            raise ValueError("finished_at cannot precede started_at")
        if not self.limitations:
            raise ValueError("run receipt requires explicit limitations")
        if self.status is RunStatus.PASS:
            if self.exit_code != 0:
                raise ValueError("PASS requires exit_code 0")
            if not self.recap_summary_path:
                raise ValueError("PASS requires recap_summary_path")
            if self.bounded_judgment is not BoundedJudgment.CAPABILITY_MEASURED:
                raise ValueError("PASS requires CAPABILITY_MEASURED")
            if self.failure_code or self.failure_message:
                raise ValueError("PASS cannot carry failure fields")
            if self.seam_validation is None:
                raise ValueError("PASS requires seam_validation")
            if not self.claims:
                raise ValueError("PASS requires at least one bounded claim")
            if not self.evidence_sha256:
                raise ValueError("PASS requires hash-bound evidence")
        else:
            if not self.failure_code:
                raise ValueError("non-PASS receipt requires failure_code")
            if self.bounded_judgment is not BoundedJudgment.NOT_MEASURED:
                raise ValueError("non-PASS receipt cannot claim a measurement")
            if self.claims:
                raise ValueError("non-PASS receipt cannot carry capability claims")
        return self


class RunStatusArtifact(StrictModel):
    schema_version: Literal["captcha.run_status.v1"]
    status: RunStatus
    updated_at: datetime
    phase: str
    receipt_path: Literal["captcha.run-receipt.json"] | None = None
    receipt_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    failure_code: str | None = None

    @model_validator(mode="after")
    def validate_terminal_truth(self) -> "RunStatusArtifact":
        if self.phase == "complete":
            if self.receipt_path is None or self.receipt_sha256 is None:
                raise ValueError("complete status requires receipt path and digest")
            if self.status is RunStatus.BLOCKED and not self.failure_code:
                raise ValueError("BLOCKED complete status requires failure_code")
            if self.status is RunStatus.PASS and self.failure_code is not None:
                raise ValueError("PASS complete status cannot carry failure_code")
        return self


class StatusReport(StrictModel):
    schema_version: Literal["captcha.status.v1"]
    status: RunStatus
    skill_root: str
    ask_skill_present: bool
    ask_declares_captcha: bool
    ask_runtime_present: bool
    surf_run_present: bool
    recap_checkout_present: bool
    recap_repository_matches: bool | None
    recap_commit_matches: bool | None
    recap_source_clean: bool | None
    recap_runtime_present: bool
    model_api_key_present: bool
    storage_root_present: bool
    blockers: list[str]
    next_actions: list[str]
    limitations: list[str]


class AskDagNodeInput(StrictModel):
    skill: Literal["captcha"] = "captcha"
    args: list[str]
    timeout: int = Field(ge=30, le=7200)


class AskDagNode(StrictModel):
    id: Literal["captcha_evaluate"] = "captcha_evaluate"
    type: Literal["skill.run"] = "skill.run"
    depends_on: list[str] = Field(default_factory=list, max_length=0)
    input: AskDagNodeInput
    max_attempts: Literal[1] = 1
    allow_failure: Literal[False] = False


class AskDag(StrictModel):
    schema_version: Literal["ask.dag.v1"]
    description: str
    source_graph_version: Literal[""] = ""
    graph_id: str
    max_concurrency: Literal[1] = 1
    nodes: list[AskDagNode] = Field(min_length=1, max_length=1)
