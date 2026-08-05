"""Site-specific ATS inspect, prefill, submit, and reconciliation gates.

The planner separates form inspection, prefill planning, human authorization,
reservation, commit, and reconciliation. It performs no browser automation by
itself and treats every submission as a site-scoped external effect requiring
exact policy and payload receipts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from .contracts import SENSITIVE_FIELD_TYPES
from .util import read_jsonl, sha256_json, stable_id, utc_now, write_jsonl

HUMAN_REQUIRED_FIELD_TYPES = SENSITIVE_FIELD_TYPES | {"choice"}


class ApplicationGateError(ValueError):
    """Stable application gate error."""


class AtsSubmitAdapter(Protocol):
    """Minimal submit/reconcile adapter surface used after all gates pass."""

    def submit(self, plan: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        """Submit an authorized plan or return an indeterminate receipt."""

    def reconcile(self, reservation_id: str) -> dict[str, Any]:
        """Resolve an indeterminate effect without submitting again."""


def inspect_ats_form(form: dict[str, Any], policy_receipt: dict[str, Any] | None) -> dict[str, Any]:
    """Inspect one employer-hosted form without mutation."""

    _require_policy(policy_receipt, "ats_form_inspect", form)
    fields = [_classify_field(field) for field in form.get("fields", [])]
    inspection = {
        "schema": "monitor_opportunities.ats_form_inspection.v1",
        "provider": form["provider"],
        "site": form["site"],
        "posting_id": form["posting_id"],
        "url": form["url"],
        "form_schema_digest": sha256_json(form),
        "fields": fields,
        "accepted_attachments": form.get("accepted_attachments", []),
        "policy_observations": form.get("policy_observations", []),
        "mutation_performed": False,
        "external_effects": False,
        "inspected_at": utc_now(),
    }
    return {**inspection, "inspection_digest": sha256_json(inspection)}


def build_application_plan(
    *,
    inspection: dict[str, Any],
    answer_bank: dict[str, Any],
    resume_digest: str,
    attachment_digests: list[str],
    candidate_profile_digest: str,
) -> dict[str, Any]:
    """Build an exact prefill plan from inspection and exact answer-bank hits."""

    answers = answer_bank.get("answers", {})
    planned_fields = []
    unresolved: list[str] = []
    for field in inspection.get("fields", []):
        planned = _planned_field(field, answers)
        planned_fields.append(planned)
        if planned["required"] and planned["disposition"] == "human_required":
            unresolved.append(planned["name"])
    basis = {
        "schema": "monitor_opportunities.application_plan.v1",
        "posting_id": inspection["posting_id"],
        "provider": inspection["provider"],
        "site": inspection["site"],
        "url": inspection["url"],
        "form_schema_digest": inspection["form_schema_digest"],
        "answer_bank_digest": sha256_json(answer_bank),
        "candidate_profile_digest": candidate_profile_digest,
        "resume_digest": resume_digest,
        "attachment_digests": attachment_digests,
        "fields": planned_fields,
        "unresolved_required_fields": unresolved,
        "state": "PREPARED",
        "external_effects": False,
    }
    return {**basis, "plan_id": stable_id("application-plan", basis), "plan_digest": sha256_json(basis)}


def authorize_application_plan(
    *,
    plan: dict[str, Any],
    actor: str,
    idempotency_key: str,
    approved_plan_digest: str,
) -> dict[str, Any]:
    """Bind a human authorization to one exact complete plan digest."""

    if actor != "human":
        raise ApplicationGateError("APPLICATION_AUTHORIZATION_REQUIRES_HUMAN")
    if plan.get("unresolved_required_fields"):
        raise ApplicationGateError("APPLICATION_PLAN_HAS_UNRESOLVED_REQUIRED_FIELDS")
    if approved_plan_digest != plan.get("plan_digest"):
        raise ApplicationGateError("APPLICATION_PLAN_DIGEST_MISMATCH")
    payload = {
        "schema": "monitor_opportunities.application_authorization.v1",
        "authorization_id": stable_id("application-authorization", {"plan": plan["plan_digest"], "key": idempotency_key}),
        "actor": actor,
        "idempotency_key": idempotency_key,
        "plan_id": plan["plan_id"],
        "plan_digest": plan["plan_digest"],
        "state": "HUMAN_AUTHORIZED",
        "created_at": utc_now(),
        "external_effects": False,
    }
    return {**payload, "authorization_digest": sha256_json(payload)}


def commit_application(
    *,
    plan: dict[str, Any],
    authorization: dict[str, Any],
    adapter: AtsSubmitAdapter,
    ledger_path: Path,
    idempotency_key: str,
    caps: dict[str, int] | None = None,
    current_resume_digest: str | None = None,
    current_form_schema_digest: str | None = None,
) -> dict[str, Any]:
    """Reserve and submit one exact authorized plan once."""

    _require_commit_inputs(plan, authorization, current_resume_digest, current_form_schema_digest)
    rows = read_jsonl(ledger_path)
    for row in rows:
        if row.get("idempotency_key") == idempotency_key:
            return row
    _check_ledger(rows, plan, caps or {})
    reservation = _reservation(plan, idempotency_key)
    rows.append(reservation)
    write_jsonl(ledger_path, rows)

    result = adapter.submit(plan, idempotency_key)
    state = result.get("state")
    if state == "COMMITTED":
        receipt = _effect_receipt(plan, authorization, idempotency_key, "COMMITTED", result, reservation)
    elif state == "INDETERMINATE":
        receipt = _effect_receipt(plan, authorization, idempotency_key, "INDETERMINATE", result, reservation)
    else:
        receipt = _effect_receipt(plan, authorization, idempotency_key, "BLOCKED", result, reservation)
    rows = [row for row in read_jsonl(ledger_path) if row.get("reservation_id") != reservation["reservation_id"]]
    rows.append(receipt)
    write_jsonl(ledger_path, rows)
    return receipt


def reconcile_application(
    *,
    reservation_id: str,
    adapter: AtsSubmitAdapter,
    ledger_path: Path,
) -> dict[str, Any]:
    """Resolve an indeterminate effect without submitting again."""

    rows = read_jsonl(ledger_path)
    prior = next((row for row in rows if row.get("reservation_id") == reservation_id), None)
    if prior is None or prior.get("state") != "INDETERMINATE":
        raise ApplicationGateError("INDETERMINATE_RECEIPT_MISSING")
    result = adapter.reconcile(reservation_id)
    if result.get("state") not in {"COMMITTED", "BLOCKED"}:
        raise ApplicationGateError("RECONCILIATION_NOT_TERMINAL")
    updated = {
        **prior,
        "state": result["state"],
        "reconciled_at": utc_now(),
        "provider_confirmation": result.get("provider_confirmation"),
        "submitted_application": result.get("state") == "COMMITTED",
    }
    rows = [row for row in rows if row.get("reservation_id") != reservation_id]
    rows.append({**updated, "receipt_digest": sha256_json(updated)})
    write_jsonl(ledger_path, rows)
    return rows[-1]


def _require_policy(policy: dict[str, Any] | None, capability: str, form: dict[str, Any]) -> None:
    if policy is None:
        raise ApplicationGateError("ATS_SITE_POLICY_MISSING")
    expected = f"{capability}:{form['provider']}:{form['site']}"
    if policy.get("capability") != expected:
        raise ApplicationGateError("ATS_SITE_POLICY_SCOPE_MISMATCH")
    if policy.get("actor") != "human" or policy.get("decision") != "PROMOTE":
        raise ApplicationGateError("ATS_SITE_POLICY_NOT_HUMAN_PROMOTE")


def _classify_field(field: dict[str, Any]) -> dict[str, Any]:
    field_type = field["field_type"]
    disposition = "human_required" if field_type in HUMAN_REQUIRED_FIELD_TYPES or field.get("ambiguous") else "fillable"
    classified = {
        "name": field["name"],
        "field_type": field_type,
        "required": bool(field.get("required", False)),
        "options": field.get("options", []),
        "classification": disposition,
    }
    if field.get("selector"):
        classified["selector"] = field["selector"]
    return classified


def _planned_field(field: dict[str, Any], answers: dict[str, Any]) -> dict[str, Any]:
    if field["classification"] == "human_required":
        return {**field, "disposition": "human_required", "automated_answer": None}
    answer = answers.get(field["name"])
    if answer is None:
        return {**field, "disposition": "human_required", "automated_answer": None}
    return {**field, "disposition": "exact_approved_answer", "automated_answer": str(answer)}


def _require_commit_inputs(
    plan: dict[str, Any],
    authorization: dict[str, Any],
    current_resume_digest: str | None,
    current_form_schema_digest: str | None,
) -> None:
    if authorization.get("plan_digest") != plan.get("plan_digest"):
        raise ApplicationGateError("APPLICATION_PLAN_CHANGED_AFTER_AUTHORIZATION")
    if plan.get("unresolved_required_fields"):
        raise ApplicationGateError("APPLICATION_PLAN_HAS_UNRESOLVED_REQUIRED_FIELDS")
    if current_resume_digest is not None and current_resume_digest != plan.get("resume_digest"):
        raise ApplicationGateError("APPLICATION_RESUME_CHANGED_AFTER_AUTHORIZATION")
    if current_form_schema_digest is not None and current_form_schema_digest != plan.get("form_schema_digest"):
        raise ApplicationGateError("APPLICATION_FORM_CHANGED_AFTER_AUTHORIZATION")


def _check_ledger(rows: list[dict[str, Any]], plan: dict[str, Any], caps: dict[str, int]) -> None:
    stable_key = _stable_application_key(plan)
    if any(row.get("stable_application_key") == stable_key and row.get("state") in {"RESERVED", "COMMITTED"} for row in rows):
        raise ApplicationGateError("DUPLICATE_OR_ALREADY_APPLIED")
    max_daily = caps.get("max_daily")
    if max_daily is not None and sum(1 for row in rows if row.get("state") == "COMMITTED") >= max_daily:
        raise ApplicationGateError("APPLICATION_CAP_EXCEEDED")


def _reservation(plan: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
    return {
        "schema": "monitor_opportunities.application_effect_receipt.v1",
        "reservation_id": stable_id("application-reservation", {"plan": plan["plan_digest"], "key": idempotency_key}),
        "plan_id": plan["plan_id"],
        "plan_digest": plan["plan_digest"],
        "stable_application_key": _stable_application_key(plan),
        "idempotency_key": idempotency_key,
        "state": "RESERVED",
        "created_at": utc_now(),
        "external_effects": False,
    }


def _effect_receipt(
    plan: dict[str, Any],
    authorization: dict[str, Any],
    idempotency_key: str,
    state: str,
    result: dict[str, Any],
    reservation: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "schema": "monitor_opportunities.application_effect_receipt.v1",
        "reservation_id": reservation["reservation_id"],
        "plan_id": plan["plan_id"],
        "plan_digest": plan["plan_digest"],
        "authorization_digest": authorization["authorization_digest"],
        "stable_application_key": reservation["stable_application_key"],
        "idempotency_key": idempotency_key,
        "state": state,
        "provider_confirmation": result.get("provider_confirmation"),
        "submitted_application": state == "COMMITTED",
        "external_effects": state in {"COMMITTED", "INDETERMINATE"},
        "created_at": utc_now(),
    }
    return {**payload, "receipt_digest": sha256_json(payload)}


def _stable_application_key(plan: dict[str, Any]) -> str:
    return stable_id("application-key", {"site": plan["site"], "posting": plan["posting_id"]})
