"""Typed contracts for Gmail OAuth profiles, plans, payloads, and receipts.

Inputs from CLI JSON, plan files, and Gmail API responses cross trust boundaries.
Pydantic validates those boundary objects before operation code uses them. Stable
internal helper records remain ordinary Python data structures.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


PLAN_SCHEMA = "gmail.operation_plan.v1"
RECEIPT_SCHEMA = "gmail.operation_receipt.v1"
UUID_PATTERN = (
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12}$"
)
MAX_RESOURCE_ID_LENGTH = 2048
MAX_TOTAL_ATTACHMENT_BYTES = 25_000_000


class OAuthProfile(StrEnum):
    """Named least-privilege OAuth profiles stored independently."""

    READONLY = "readonly"
    COMPOSE = "compose"
    MANAGE = "manage"


PROFILE_SCOPES: dict[OAuthProfile, tuple[str, ...]] = {
    OAuthProfile.READONLY: ("https://www.googleapis.com/auth/gmail.readonly",),
    OAuthProfile.COMPOSE: ("https://www.googleapis.com/auth/gmail.compose",),
    OAuthProfile.MANAGE: ("https://www.googleapis.com/auth/gmail.modify",),
}


class Operation(StrEnum):
    """Closed set of supported Gmail write operations."""

    BATCH_MODIFY = "batch_modify"
    TRASH = "trash"
    UNTRASH = "untrash"
    CREATE_LABEL = "create_label"
    CREATE_DRAFT = "create_draft"
    SEND_MESSAGE = "send_message"
    SEND_DRAFT = "send_draft"


OPERATION_REQUIRED_PROFILE: dict[Operation, tuple[OAuthProfile, ...]] = {
    Operation.BATCH_MODIFY: (OAuthProfile.MANAGE,),
    Operation.TRASH: (OAuthProfile.MANAGE,),
    Operation.UNTRASH: (OAuthProfile.MANAGE,),
    Operation.CREATE_LABEL: (OAuthProfile.MANAGE,),
    Operation.CREATE_DRAFT: (OAuthProfile.COMPOSE, OAuthProfile.MANAGE),
    Operation.SEND_MESSAGE: (OAuthProfile.COMPOSE, OAuthProfile.MANAGE),
    Operation.SEND_DRAFT: (OAuthProfile.COMPOSE, OAuthProfile.MANAGE),
}


class ReceiptStatus(StrEnum):
    """Outcome categories that keep ambiguous network writes distinct."""

    SUCCESS = "success"
    FAILURE = "failure"
    INDETERMINATE = "indeterminate"


def _reject_controls(value: str, *, field_name: str, allow_tab: bool = False) -> str:
    """Reject NUL/newlines and other control characters at trust boundaries."""

    for character in value:
        codepoint = ord(character)
        if character == "\t" and allow_tab:
            continue
        if codepoint < 32 or codepoint == 127:
            raise ValueError(f"{field_name} contains a control character")
    return value


def _normalize_resource_id(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    if len(normalized) > MAX_RESOURCE_ID_LENGTH:
        raise ValueError(f"{field_name} exceeds {MAX_RESOURCE_ID_LENGTH} characters")
    return _reject_controls(normalized, field_name=field_name)


def _normalize_resource_ids(values: list[str], *, field_name: str) -> list[str]:
    normalized = [
        _normalize_resource_id(value, field_name=field_name)
        for value in values
    ]
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"duplicate {field_name} values are not allowed")
    return normalized


class AttachmentSpec(BaseModel):
    """Immutable attachment snapshot checked again immediately before commit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1, max_length=4096)
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=3, max_length=255)
    size_bytes: int = Field(ge=0, le=MAX_TOTAL_ATTACHMENT_BYTES)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("attachment path contains NUL")
        return value

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        return _reject_controls(value, field_name="attachment filename")

    @field_validator("content_type")
    @classmethod
    def validate_content_type(cls, value: str) -> str:
        normalized = _reject_controls(value.strip(), field_name="attachment content type")
        if normalized.count("/") != 1:
            raise ValueError("attachment content type must use type/subtype form")
        main_type, sub_type = normalized.split("/", 1)
        if not main_type or not sub_type:
            raise ValueError("attachment content type must use type/subtype form")
        return normalized


class OutboundMessagePayload(BaseModel):
    """Exact outgoing message content frozen into an operation plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    to: list[EmailStr] = Field(min_length=1, max_length=100)
    cc: list[EmailStr] = Field(default_factory=list, max_length=100)
    bcc: list[EmailStr] = Field(default_factory=list, max_length=100)
    subject: str = Field(min_length=1, max_length=998)
    text_body: str | None = Field(default=None, max_length=2_000_000)
    html_body: str | None = Field(default=None, max_length=2_000_000)
    attachments: list[AttachmentSpec] = Field(default_factory=list, max_length=25)
    message_id_header: str = Field(min_length=3, max_length=998)
    thread_id: str | None = Field(default=None, min_length=1, max_length=MAX_RESOURCE_ID_LENGTH)
    in_reply_to: str | None = Field(default=None, min_length=3, max_length=998)
    references: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def require_body_and_bounded_attachments(self) -> "OutboundMessagePayload":
        if self.text_body is None and self.html_body is None:
            raise ValueError("at least one of text_body or html_body is required")
        total_bytes = sum(item.size_bytes for item in self.attachments)
        if total_bytes > MAX_TOTAL_ATTACHMENT_BYTES:
            raise ValueError(
                "combined attachment size exceeds the conservative 25 MB limit"
            )
        return self

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, value: str) -> str:
        return _reject_controls(value, field_name="subject", allow_tab=True)

    @field_validator("message_id_header", "in_reply_to")
    @classmethod
    def validate_message_id_header(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = _reject_controls(value.strip(), field_name="RFC message ID")
        if not (
            normalized.startswith("<")
            and normalized.endswith(">")
            and "@" in normalized
        ):
            raise ValueError("RFC message IDs must use <local@domain> form")
        return normalized

    @field_validator("references")
    @classmethod
    def validate_references(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            checked = _reject_controls(value.strip(), field_name="reference")
            if not (checked.startswith("<") and checked.endswith(">") and "@" in checked):
                raise ValueError("references must contain RFC message IDs")
            normalized.append(checked)
        return normalized

    @field_validator("thread_id")
    @classmethod
    def validate_thread_id(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _normalize_resource_id(value, field_name="thread ID")


class BatchModifyPayload(BaseModel):
    """Idempotent batch label mutation for up to Gmail's 1000-ID limit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    message_ids: list[str] = Field(min_length=1, max_length=1000)
    add_label_ids: list[str] = Field(default_factory=list, max_length=100)
    remove_label_ids: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def require_change(self) -> "BatchModifyPayload":
        if not self.add_label_ids and not self.remove_label_ids:
            raise ValueError("at least one label must be added or removed")
        overlap = set(self.add_label_ids) & set(self.remove_label_ids)
        if overlap:
            raise ValueError(f"labels cannot be both added and removed: {sorted(overlap)}")
        return self

    @field_validator("message_ids")
    @classmethod
    def validate_message_ids(cls, values: list[str]) -> list[str]:
        return _normalize_resource_ids(values, field_name="message ID")

    @field_validator("add_label_ids", "remove_label_ids")
    @classmethod
    def validate_label_ids(cls, values: list[str]) -> list[str]:
        return _normalize_resource_ids(values, field_name="label ID")


class MessageIdsPayload(BaseModel):
    """Message IDs used by trash and untrash operations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    message_ids: list[str] = Field(min_length=1, max_length=50)

    @field_validator("message_ids")
    @classmethod
    def validate_ids(cls, values: list[str]) -> list[str]:
        return _normalize_resource_ids(values, field_name="message ID")


class CreateLabelPayload(BaseModel):
    """User label creation contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=225)
    message_list_visibility: Literal["show", "hide"] = "show"
    label_list_visibility: Literal[
        "labelShow",
        "labelShowIfUnread",
        "labelHide",
    ] = "labelShow"

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("label name must not be blank")
        return _reject_controls(normalized, field_name="label name")


class SendDraftPayload(BaseModel):
    """Existing Gmail draft snapshot selected for explicit, drift-checked send."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    draft_id: str = Field(min_length=1, max_length=MAX_RESOURCE_ID_LENGTH)
    message_id: str = Field(min_length=1, max_length=MAX_RESOURCE_ID_LENGTH)
    thread_id: str | None = Field(default=None, max_length=MAX_RESOURCE_ID_LENGTH)
    raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    to: list[EmailStr] = Field(min_length=1, max_length=100)
    cc: list[EmailStr] = Field(default_factory=list, max_length=100)
    bcc: list[EmailStr] = Field(default_factory=list, max_length=100)
    subject: str = Field(min_length=1, max_length=998)
    message_id_header: str | None = Field(default=None, max_length=998)

    @field_validator("draft_id", "message_id")
    @classmethod
    def validate_required_ids(cls, value: str) -> str:
        return _normalize_resource_id(value, field_name="draft resource ID")

    @field_validator("thread_id")
    @classmethod
    def validate_optional_thread_id(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _normalize_resource_id(value, field_name="thread ID")

    @field_validator("subject")
    @classmethod
    def validate_draft_subject(cls, value: str) -> str:
        return _reject_controls(value, field_name="subject", allow_tab=True)

    @field_validator("message_id_header")
    @classmethod
    def validate_optional_message_id(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = _reject_controls(value.strip(), field_name="RFC message ID")
        if not (
            normalized.startswith("<")
            and normalized.endswith(">")
            and "@" in normalized
        ):
            raise ValueError("RFC message IDs must use <local@domain> form")
        return normalized


PayloadModel = (
    BatchModifyPayload
    | MessageIdsPayload
    | CreateLabelPayload
    | OutboundMessagePayload
    | SendDraftPayload
)


PAYLOAD_MODEL_BY_OPERATION: dict[Operation, type[BaseModel]] = {
    Operation.BATCH_MODIFY: BatchModifyPayload,
    Operation.TRASH: MessageIdsPayload,
    Operation.UNTRASH: MessageIdsPayload,
    Operation.CREATE_LABEL: CreateLabelPayload,
    Operation.CREATE_DRAFT: OutboundMessagePayload,
    Operation.SEND_MESSAGE: OutboundMessagePayload,
    Operation.SEND_DRAFT: SendDraftPayload,
}


def canonical_json(value: Any) -> str:
    """Serialize stable JSON for hashing without leaking through logs."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(value: Any) -> str:
    """Return the SHA-256 of canonical JSON."""

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


def validate_payload(operation: Operation, payload: dict[str, Any]) -> PayloadModel:
    """Validate a raw plan payload against the operation-specific model."""

    model_type = PAYLOAD_MODEL_BY_OPERATION[operation]
    return model_type.model_validate(payload)  # type: ignore[return-value]


class OperationPlan(BaseModel):
    """Immutable, account-bound, expiring human-approval plan."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, frozen=True)

    schema_: Literal[PLAN_SCHEMA] = Field(alias="schema", default=PLAN_SCHEMA)
    plan_id: str = Field(
        default_factory=lambda: str(uuid4()),
        pattern=UUID_PATTERN,
    )
    operation: Operation
    profile: OAuthProfile
    account: EmailStr
    created_at: datetime
    expires_at: datetime
    payload: dict[str, Any]
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    approval_code: str = Field(min_length=10, max_length=80)

    @field_validator("created_at", "expires_at")
    @classmethod
    def require_aware_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def verify_contract(self) -> "OperationPlan":
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be after created_at")
        if self.profile not in OPERATION_REQUIRED_PROFILE[self.operation]:
            raise ValueError(
                f"profile {self.profile.value} cannot execute {self.operation.value}"
            )
        normalized = validate_payload(self.operation, self.payload)
        normalized_payload = normalized.model_dump(mode="json")
        expected_payload_hash = sha256_json(normalized_payload)
        if self.payload_sha256 != expected_payload_hash:
            raise ValueError("payload_sha256 does not match normalized payload")
        expected_code = build_approval_code(
            plan_id=self.plan_id,
            operation=self.operation,
            profile=self.profile,
            account=str(self.account),
            created_at=self.created_at,
            expires_at=self.expires_at,
            payload_sha256=self.payload_sha256,
        )
        if self.approval_code != expected_code:
            raise ValueError("approval_code does not match plan contract")
        return self

    def is_expired(self, now: datetime | None = None) -> bool:
        """Return whether the plan is past its approval window."""

        current = (now or utc_now()).astimezone(timezone.utc)
        return current >= self.expires_at

    def payload_model(self) -> PayloadModel:
        """Return the validated operation-specific payload model."""

        return validate_payload(self.operation, self.payload)


class OperationReceipt(BaseModel):
    """Write receipt that intentionally excludes bodies, attachments, and tokens."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, frozen=True)

    schema_: Literal[RECEIPT_SCHEMA] = Field(alias="schema", default=RECEIPT_SCHEMA)
    receipt_id: str = Field(
        default_factory=lambda: str(uuid4()),
        pattern=UUID_PATTERN,
    )
    plan_id: str = Field(pattern=UUID_PATTERN)
    operation: Operation
    profile: OAuthProfile
    account: EmailStr
    status: ReceiptStatus
    started_at: datetime
    completed_at: datetime
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    result: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = Field(default=None, max_length=120)
    error_message: str | None = Field(default=None, max_length=1000)

    @field_validator("started_at", "completed_at")
    @classmethod
    def require_aware_receipt_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_timing_and_error(self) -> "OperationReceipt":
        if self.completed_at < self.started_at:
            raise ValueError("completed_at must not precede started_at")
        if self.status is ReceiptStatus.SUCCESS and (
            self.error_code or self.error_message
        ):
            raise ValueError("successful receipts cannot include errors")
        if self.status is not ReceiptStatus.SUCCESS and not self.error_code:
            raise ValueError("non-success receipts require error_code")
        return self


def build_approval_code(
    *,
    plan_id: str,
    operation: Operation,
    profile: OAuthProfile,
    account: str,
    created_at: datetime,
    expires_at: datetime,
    payload_sha256: str,
) -> str:
    """Build a short exact phrase tied to every immutable plan field."""

    contract = {
        "plan_id": plan_id,
        "operation": operation.value,
        "profile": profile.value,
        "account": account.lower(),
        "created_at": created_at.astimezone(timezone.utc).isoformat(),
        "expires_at": expires_at.astimezone(timezone.utc).isoformat(),
        "payload_sha256": payload_sha256,
    }
    digest = sha256_json(contract)[:16]
    return f"approve:{operation.value}:{digest}"


def load_plan(path: Path) -> OperationPlan:
    """Load and validate a plan file."""

    data = json.loads(path.read_text(encoding="utf-8"))
    return OperationPlan.model_validate(data)
