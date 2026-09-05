"""Pydantic validation for watchdog tick receipts at the finish() boundary.

Ownership per the agent-ecosystem rule "component owns its schema":

- project-watchdog owns ``agent_skills.project_watchdog.tick_receipt.v1`` and
  validates it here with pydantic, the same make-invalid-states-unrepresentable
  pattern $shame (pi.agent_status.v1) and $project-state
  (project_state.report.v1) already enforce.
- project-watchdog does NOT own failure vocabulary. Every ``code`` in a receipt
  must be a $triage-error catalog code (``failure_codes.json``, read from the
  sibling skill) or a minted ``*_unclassified_<8hex>`` code. A hand-invented
  classification fails validation instead of flowing into receipts, shame
  ledgers, and Discord alerts.

Fail-closed, never crashing: an invalid receipt is downgraded to
``NEEDS_ATTENTION`` with the exact validation error recorded under
``schema_validation`` — it still persists and still alerts.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any, Literal

import subprocess

from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import config

TRIAGE_RUN_SH = config.SKILL_DIR.parent / "triage-error" / "run.sh"

MINTED_CODE_RE = re.compile(r"^[a-z0-9_]+_unclassified_[0-9a-f]{8}$")

TRIAGE_CATALOG_PATH = config.SKILL_DIR.parent / "triage-error" / "failure_codes.json"

RECEIPT_STATUSES = (
    "COMPLETED",
    "NOOP",
    "SKIPPED",
    "BLOCKED",
    "NEEDS_ATTENTION",
    "DRY_RUN",
)


@lru_cache(maxsize=1)
def catalog_codes() -> frozenset[str]:
    """Canonical codes from $triage-error. Empty set if the catalog is absent
    (minted-shape codes then remain the only valid codes)."""
    try:
        data = json.loads(TRIAGE_CATALOG_PATH.read_text())
        return frozenset(e["code"] for e in data.get("codes", []))
    except (OSError, ValueError, KeyError, TypeError):
        return frozenset()


def is_valid_failure_code(code: str) -> bool:
    return code in catalog_codes() or bool(MINTED_CODE_RE.fullmatch(code))


class Triage(BaseModel):
    model_config = ConfigDict(extra="allow")
    code: str = Field(min_length=1)
    cause: str = Field(min_length=1)
    #: The triage-error contract is {code, cause, next_command}. next_command
    #: may be null (some catalog entries have none) but the field must exist
    #: so consumers can rely on its presence.
    next_command: str | None = None

    @field_validator("code")
    @classmethod
    def code_must_be_canonical(cls, value: str) -> str:
        if not is_valid_failure_code(value):
            raise ValueError(
                f"failure code {value!r} is not in the $triage-error catalog "
                f"({TRIAGE_CATALOG_PATH}) and does not match the minted "
                "*_unclassified_<8hex> shape. Route the raw signal through "
                "'triage-error/run.sh triage' instead of inventing a code."
            )
        return value


class HandledIssue(BaseModel):
    model_config = ConfigDict(extra="allow")
    issue_number: int | None = None
    status: str | None = None
    triage: Triage | None = None
    failure_code: str | None = None

    @field_validator("failure_code")
    @classmethod
    def failure_code_must_be_canonical(cls, value: str | None) -> str | None:
        if value is not None and not is_valid_failure_code(value):
            raise ValueError(
                f"failure_code {value!r} is not a catalog or minted code"
            )
        return value


#: Every receipt family finish() emits. An unknown schema string is a defect,
#: not forward-compat (reviewer finding 2026-09-03).
RECEIPT_SCHEMA_RE = re.compile(
    r"^agent_skills\.project_watchdog\."
    r"(tick_receipt|activate_receipt|cron_install_receipt|state_change_receipt|status)\.v1$"
)


class OtherReceipt(BaseModel):
    """Non-tick receipt families (activate, cron install, state change) have
    their own shapes. finish() still validates the schema string and any
    triage/failure codes they carry, but not the tick-specific fields."""

    model_config = ConfigDict(extra="allow")
    schema_: str = Field(alias="schema")
    triage: Triage | None = None

    @field_validator("schema_")
    @classmethod
    def schema_must_be_known(cls, value: str) -> str:
        if not RECEIPT_SCHEMA_RE.fullmatch(value):
            raise ValueError(f"unknown watchdog receipt schema {value!r}")
        return value


class TickReceipt(BaseModel):
    """Invariants of every tick receipt. extra='allow' keeps forward-compat;
    the typed fields are the ones downstream consumers dispatch on."""

    model_config = ConfigDict(extra="allow")

    schema_: str = Field(alias="schema")
    run_id: str = Field(min_length=1)
    status: Literal[RECEIPT_STATUSES]  # type: ignore[valid-type]
    ok: bool | None = None
    apply: bool | None = None
    handled_issues: list[HandledIssue] = []
    errors: list[Any] = []
    triage: Triage | None = None

    @field_validator("schema_")
    @classmethod
    def schema_must_be_tick(cls, value: str) -> str:
        if value != "agent_skills.project_watchdog.tick_receipt.v1":
            raise ValueError(f"expected tick_receipt.v1, got {value!r}")
        return value


def _classify_with_triage_error(error_text: str) -> dict[str, Any]:
    """Self-heal hook: map the raw validation error to one canonical
    {code, cause, next_command} via $triage-error. Best effort, never raises;
    an unreachable classifier is itself recorded, not hidden."""
    try:
        proc = subprocess.run(
            [
                str(TRIAGE_RUN_SH),
                "classify",
                "--text",
                error_text[:1000],
                "--layer",
                "project-watchdog",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"native triage classifier exited {proc.returncode}: {proc.stderr[:300]}")
        payload = json.loads(proc.stdout)
        Triage.model_validate(payload)
        return payload
    except Exception as exc:  # noqa: BLE001 - validation must not fail on triage IO
        # This fallback code is itself in the triage-error catalog so the
        # "codes come only from the catalog or minted shape" invariant holds
        # even when the classifier is down.
        return {
            "code": "triage_classifier_unreachable",
            "cause": "triage-error classify could not be invoked",
            "next_command": None,
            "error": str(exc)[:300],
        }


def validate_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    """Validate in place. Returns the ``schema_validation`` record it attaches.

    Invalid receipts are downgraded to NEEDS_ATTENTION (fail-closed) with the
    original status preserved; this function never raises.
    """
    schema_value = receipt.get("schema", "")
    is_tick = schema_value == "agent_skills.project_watchdog.tick_receipt.v1"
    model = TickReceipt if is_tick else OtherReceipt
    try:
        model.model_validate(receipt)
        record: dict[str, Any] = {"valid": True, "model": model.__name__}
    except Exception as exc:  # pydantic ValidationError or catalog IO surprise
        record = {
            "valid": False,
            "model": model.__name__,
            "error": str(exc)[:1500],
            "original_status": receipt.get("status"),
            "triage": _classify_with_triage_error(str(exc)),
        }
        receipt["status"] = "NEEDS_ATTENTION"
        receipt["ok"] = False
        receipt.setdefault("stop_reason", "receipt_schema_invalid")
    receipt["schema_validation"] = record
    return record
