"""Typed seam contracts for every artifact that crosses an /ask boundary.

Purpose
    Deterministic, unignorable validation at each producer seam. A payload
    either validates, is self-healed with the repairs recorded, or the seam
    raises ``SeamViolation`` — there is no advisory mode a drifting caller can
    skip past.

Inputs
    Raw dict payloads produced at the compile, lifecycle, and execution seams.

Outputs
    ``enforce(kind, payload)`` returns the validated payload dict (with a
    ``seam_validation`` receipt attached) or raises ``SeamViolation``.

Failure modes
    - Unknown seam kind: ``SeamViolation`` naming the registered kinds.
    - Model validation failure after self-heal: ``SeamViolation`` carrying the
      pydantic error list verbatim.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class SeamViolation(RuntimeError):
    """A seam artifact failed typed validation after self-heal."""

    def __init__(self, kind: str, errors: list[dict[str, Any]]) -> None:
        self.kind = kind
        self.errors = errors
        super().__init__(f"seam {kind!r} violated its contract: {errors}")


class _SeamModel(BaseModel):
    # Extra keys pass through untouched: seams grow fields faster than models,
    # and silently dropping a producer's data would itself be drift.
    model_config = ConfigDict(extra="allow")


class TauDagBundle(_SeamModel):
    schema_name: str = Field(alias="schema")
    status: Literal["READY", "BLOCKED", "NEEDS_INTERVIEW"]
    run_dir: str = ""
    dag_path: str = ""
    dag: dict[str, Any] | None = None
    tau_contract_validation: dict[str, Any] | None = None

    def require_ready_artifacts(self) -> list[str]:
        problems: list[str] = []
        if self.status == "READY":
            if not self.run_dir:
                problems.append("READY bundle has no run_dir")
            if not self.dag_path:
                problems.append("READY bundle has no dag_path")
            validation = self.tau_contract_validation or {}
            if validation.get("status") not in {"PASS", "SELF_HEALED", "SKIPPED"}:
                problems.append(
                    "READY bundle without a passing tau_contract_validation "
                    f"(got {validation.get('status')!r})"
                )
        return problems


class LifecycleTab(_SeamModel):
    handler: str
    tab_id: str
    url: str = ""


class BrowserTabLifecycle(_SeamModel):
    schema_name: str = Field(alias="schema")
    status: str
    mode: str = ""
    created_tabs: list[LifecycleTab] = Field(default_factory=list)

    def require_ready_tabs(self) -> list[str]:
        problems: list[str] = []
        if self.status == "READY" and self.mode in {
            "fresh-temporary",
            "fresh-keep",
            "fresh-shared-temporary",
            "fresh-shared-keep",
        }:
            for tab in self.created_tabs:
                if not str(tab.tab_id).isdigit():
                    problems.append(
                        f"READY lifecycle tab for {tab.handler!r} has non-numeric tab_id {tab.tab_id!r}"
                    )
        return problems


class ExecutionResult(_SeamModel):
    schema_name: str = Field(alias="schema")
    status: str
    ok: bool
    receipt_path: str = ""

    def require_receipt_truth(self) -> list[str]:
        if self.ok and self.status != "PASS":
            return [f"ok=true with status {self.status!r}"]
        return []


class LaneDiagnosticCheck(_SeamModel):
    check: str
    status: Literal["PASS", "FAIL", "SKIPPED"]


class LaneDiagnostics(_SeamModel):
    """Live-state evidence for a failed provider lane.

    The seam exists so a lane failure cannot be reported without the fixed
    diagnostic series having actually run. An empty ``checks`` list means the
    probe was skipped, which is the exact drift this contract forbids.
    """

    schema_name: str = Field(alias="schema")
    handler: str
    failure_code: str = ""
    checks: list[LaneDiagnosticCheck] = Field(default_factory=list)
    diagnosis: str = ""

    def require_live_evidence(self) -> list[str]:
        problems: list[str] = []
        if not self.checks:
            problems.append(
                f"lane {self.handler!r} failed with no diagnostic checks run; "
                "a provider failure must carry live state, not a theory"
            )
        if not self.diagnosis:
            problems.append(f"lane {self.handler!r} diagnostics carry no derived diagnosis")
        if self.checks and not any(c.check == "surf_transport" for c in self.checks):
            problems.append(
                f"lane {self.handler!r} diagnostics skipped the surf_transport check; "
                "the series is fixed and may not be partially run"
            )
        return problems


_SEAMS: dict[str, type[_SeamModel]] = {
    "ask.lane_diagnostics.v1": LaneDiagnostics,
    "ask.tau_dag_bundle.v1": TauDagBundle,
    "ask.browser_tab_lifecycle.v1": BrowserTabLifecycle,
    "ask.tau_dag_execution.v1": ExecutionResult,
}

_EXTRA_CHECKS = {
    "ask.tau_dag_bundle.v1": "require_ready_artifacts",
    "ask.browser_tab_lifecycle.v1": "require_ready_tabs",
    "ask.tau_dag_execution.v1": "require_receipt_truth",
    "ask.lane_diagnostics.v1": "require_live_evidence",
}


def enforce(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a seam payload; raise SeamViolation on contract failure.

    On success the payload gains a ``seam_validation`` receipt so downstream
    readers can distinguish "validated" from "never checked".
    """
    model_cls = _SEAMS.get(kind)
    if model_cls is None:
        raise SeamViolation(kind, [{"error": f"unknown seam kind; registered: {sorted(_SEAMS)}"}])
    try:
        model = model_cls.model_validate(payload)
    except ValidationError as exc:
        raise SeamViolation(kind, exc.errors(include_url=False)) from exc
    check_name = _EXTRA_CHECKS.get(kind)
    if check_name:
        problems = getattr(model, check_name)()
        if problems:
            raise SeamViolation(kind, [{"error": p} for p in problems])
    payload["seam_validation"] = {"kind": kind, "status": "PASS"}
    return payload
