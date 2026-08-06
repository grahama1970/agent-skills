"""Two-phase Gmail write planning, execution, locking, and receipts."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import timedelta
from email.utils import make_msgid
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .api import AmbiguousWriteError, GmailApiError, GmailClient
from .auth import access_token, ensure_private_directory, state_root
from .mime import (
    build_raw_message,
    hash_raw_message,
    snapshot_attachment,
    summarize_raw_message,
)
from .models import (
    BatchModifyPayload,
    CreateLabelPayload,
    MessageIdsPayload,
    OAuthProfile,
    Operation,
    OperationPlan,
    OperationReceipt,
    OutboundMessagePayload,
    ReceiptStatus,
    SendDraftPayload,
    build_approval_code,
    sha256_json,
    utc_now,
)


class PlanCommitError(RuntimeError):
    """Raised when a plan fails a deterministic precondition."""


class PartialOperationError(PlanCommitError):
    """A bounded multi-message operation stopped after partial progress."""

    def __init__(
        self,
        message: str,
        *,
        result: dict[str, Any],
        error_code: str,
        status: ReceiptStatus,
    ) -> None:
        super().__init__(message)
        self.result = result
        self.error_code = error_code
        self.status = status


ClientFactory = Callable[[OAuthProfile], GmailClient]


def default_client_factory(profile: OAuthProfile) -> GmailClient:
    """Build a live client from the selected OAuth profile."""

    return GmailClient(access_token=access_token(profile), profile=profile)


def plans_dir() -> Path:
    return state_root() / "plans"


def receipts_dir() -> Path:
    return state_root() / "receipts"


def locks_dir() -> Path:
    return state_root() / "locks"


def _ensure_json_parent(path: Path) -> None:
    """Create the parent without changing arbitrary user-selected directory modes."""

    path.parent.mkdir(parents=True, exist_ok=True)
    state = state_root().expanduser().resolve()
    parent = path.parent.resolve()
    if parent == state or parent.is_relative_to(state):
        ensure_private_directory(path.parent)



def _destination_path(path: Path) -> Path:
    """Resolve the parent while preserving the final path entry."""

    expanded = path.expanduser()
    if not expanded.is_absolute():
        expanded = Path.cwd() / expanded
    return expanded.parent.resolve() / expanded.name


def _atomic_json_write(path: Path, value: dict[str, Any]) -> None:
    _ensure_json_parent(path)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary_path, path)
        except FileExistsError as exc:
            raise FileExistsError(f"refusing to overwrite existing file: {path}") from exc
        temporary_path.unlink()
        path.chmod(0o600)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        temporary_path.unlink(missing_ok=True)


def _account_from_profile(data: dict[str, Any]) -> str:
    account = data.get("emailAddress")
    if not isinstance(account, str) or not account:
        raise PlanCommitError("Gmail profile response did not contain emailAddress")
    return account


def _account_for_profile(profile: OAuthProfile, factory: ClientFactory) -> str:
    with factory(profile) as client:
        data = client.get_profile()
    return _account_from_profile(data)


def create_plan(
    *,
    operation: Operation,
    profile: OAuthProfile,
    account: str,
    payload: Any,
    expires_in_seconds: int = 1800,
    output: Path | None = None,
) -> tuple[OperationPlan, Path]:
    """Create, hash, validate, and persist an immutable operation plan."""

    if not 60 <= expires_in_seconds <= 86_400:
        raise ValueError("expires_in_seconds must be between 60 and 86400")
    created_at = utc_now()
    expires_at = created_at + timedelta(seconds=expires_in_seconds)
    payload_dict = payload.model_dump(mode="json")
    payload_hash = sha256_json(payload_dict)
    plan_id = str(uuid4())
    approval_code = build_approval_code(
        plan_id=plan_id,
        operation=operation,
        profile=profile,
        account=account,
        created_at=created_at,
        expires_at=expires_at,
        payload_sha256=payload_hash,
    )
    plan = OperationPlan.model_validate(
        {
            "schema": "gmail.operation_plan.v1",
            "plan_id": plan_id,
            "operation": operation.value,
            "profile": profile.value,
            "account": account,
            "created_at": created_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "payload": payload_dict,
            "payload_sha256": payload_hash,
            "approval_code": approval_code,
        }
    )
    destination = _destination_path(
        output or plans_dir() / f"{plan.plan_id}.json"
    )
    _atomic_json_write(
        destination,
        plan.model_dump(mode="json", by_alias=True),
    )
    return plan, destination


def prepare_mailbox_plan(
    *,
    action: str,
    message_ids: list[str],
    add_label_ids: list[str] | None = None,
    remove_label_ids: list[str] | None = None,
    expires_in_seconds: int = 1800,
    output: Path | None = None,
    client_factory: ClientFactory = default_client_factory,
) -> tuple[OperationPlan, Path]:
    """Translate a user-facing mailbox action into a manage-profile plan."""

    normalized = action.replace("-", "_").lower()
    add = list(add_label_ids or [])
    remove = list(remove_label_ids or [])
    operation: Operation
    payload: Any

    if normalized == "archive":
        remove.append("INBOX")
        operation = Operation.BATCH_MODIFY
        payload = BatchModifyPayload(
            message_ids=message_ids,
            add_label_ids=add,
            remove_label_ids=remove,
        )
    elif normalized == "unarchive":
        add.append("INBOX")
        operation = Operation.BATCH_MODIFY
        payload = BatchModifyPayload(
            message_ids=message_ids,
            add_label_ids=add,
            remove_label_ids=remove,
        )
    elif normalized == "mark_read":
        remove.append("UNREAD")
        operation = Operation.BATCH_MODIFY
        payload = BatchModifyPayload(
            message_ids=message_ids,
            add_label_ids=add,
            remove_label_ids=remove,
        )
    elif normalized == "mark_unread":
        add.append("UNREAD")
        operation = Operation.BATCH_MODIFY
        payload = BatchModifyPayload(
            message_ids=message_ids,
            add_label_ids=add,
            remove_label_ids=remove,
        )
    elif normalized == "star":
        add.append("STARRED")
        operation = Operation.BATCH_MODIFY
        payload = BatchModifyPayload(
            message_ids=message_ids,
            add_label_ids=add,
            remove_label_ids=remove,
        )
    elif normalized == "unstar":
        remove.append("STARRED")
        operation = Operation.BATCH_MODIFY
        payload = BatchModifyPayload(
            message_ids=message_ids,
            add_label_ids=add,
            remove_label_ids=remove,
        )
    elif normalized == "labels":
        operation = Operation.BATCH_MODIFY
        payload = BatchModifyPayload(
            message_ids=message_ids,
            add_label_ids=add,
            remove_label_ids=remove,
        )
    elif normalized == "trash":
        if add or remove:
            raise ValueError("trash does not accept label changes")
        operation = Operation.TRASH
        payload = MessageIdsPayload(message_ids=message_ids)
    elif normalized == "untrash":
        if add or remove:
            raise ValueError("untrash does not accept label changes")
        operation = Operation.UNTRASH
        payload = MessageIdsPayload(message_ids=message_ids)
    else:
        raise ValueError(f"unsupported mailbox action: {action}")

    account = _account_for_profile(OAuthProfile.MANAGE, client_factory)
    return create_plan(
        operation=operation,
        profile=OAuthProfile.MANAGE,
        account=account,
        payload=payload,
        expires_in_seconds=expires_in_seconds,
        output=output,
    )


def prepare_outbound_plan(
    *,
    mode: str,
    profile: OAuthProfile,
    to: list[str],
    subject: str,
    text_body: str | None,
    html_body: str | None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    attachment_paths: list[Path] | None = None,
    thread_id: str | None = None,
    in_reply_to: str | None = None,
    references: list[str] | None = None,
    expires_in_seconds: int = 1800,
    output: Path | None = None,
    client_factory: ClientFactory = default_client_factory,
) -> tuple[OperationPlan, Path]:
    """Prepare either a Gmail draft creation or direct send plan."""

    if profile not in {OAuthProfile.COMPOSE, OAuthProfile.MANAGE}:
        raise ValueError("outbound plans require compose or manage profile")
    normalized_mode = mode.lower().replace("-", "_")
    operation = {
        "draft": Operation.CREATE_DRAFT,
        "send": Operation.SEND_MESSAGE,
    }.get(normalized_mode)
    if operation is None:
        raise ValueError("mode must be draft or send")
    account = _account_for_profile(profile, client_factory)
    domain = account.split("@", 1)[1] if "@" in account else "gmail.local"
    attachments = [
        snapshot_attachment(path)
        for path in attachment_paths or []
    ]
    payload = OutboundMessagePayload(
        to=to,
        cc=cc or [],
        bcc=bcc or [],
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        attachments=attachments,
        message_id_header=make_msgid(domain=domain),
        thread_id=thread_id,
        in_reply_to=in_reply_to,
        references=references or [],
    )
    return create_plan(
        operation=operation,
        profile=profile,
        account=account,
        payload=payload,
        expires_in_seconds=expires_in_seconds,
        output=output,
    )


def prepare_label_plan(
    *,
    name: str,
    message_list_visibility: str = "show",
    label_list_visibility: str = "labelShow",
    expires_in_seconds: int = 1800,
    output: Path | None = None,
    client_factory: ClientFactory = default_client_factory,
) -> tuple[OperationPlan, Path]:
    """Prepare user-label creation under the manage profile."""

    account = _account_for_profile(OAuthProfile.MANAGE, client_factory)
    payload = CreateLabelPayload(
        name=name,
        message_list_visibility=message_list_visibility,
        label_list_visibility=label_list_visibility,
    )
    return create_plan(
        operation=Operation.CREATE_LABEL,
        profile=OAuthProfile.MANAGE,
        account=account,
        payload=payload,
        expires_in_seconds=expires_in_seconds,
        output=output,
    )


def _draft_snapshot(draft: dict[str, Any]) -> tuple[str, str, str | None, str, dict[str, Any]]:
    """Validate a RAW Draft resource and return immutable snapshot fields."""

    draft_id = draft.get("id")
    message = draft.get("message")
    if not isinstance(draft_id, str) or not draft_id:
        raise PlanCommitError("Gmail draft response omitted draft id")
    if not isinstance(message, dict):
        raise PlanCommitError("Gmail draft response omitted message")
    message_id = message.get("id")
    raw = message.get("raw")
    thread_id = message.get("threadId")
    if not isinstance(message_id, str) or not message_id:
        raise PlanCommitError("Gmail draft response omitted message id")
    if not isinstance(raw, str) or not raw:
        raise PlanCommitError("Gmail draft response omitted raw MIME")
    if thread_id is not None and not isinstance(thread_id, str):
        raise PlanCommitError("Gmail draft response returned invalid thread id")
    return draft_id, message_id, thread_id, hash_raw_message(raw), summarize_raw_message(raw)


def prepare_send_draft_plan(
    *,
    draft_id: str,
    profile: OAuthProfile,
    expires_in_seconds: int = 1800,
    output: Path | None = None,
    client_factory: ClientFactory = default_client_factory,
) -> tuple[OperationPlan, Path]:
    """Prepare sending one existing draft with a commit-time raw-MIME drift check."""

    if profile not in {OAuthProfile.COMPOSE, OAuthProfile.MANAGE}:
        raise ValueError("send-draft requires compose or manage profile")
    with client_factory(profile) as client:
        account = _account_from_profile(client.get_profile())
        draft = client.get_draft(draft_id, format_="RAW")
    (
        live_draft_id,
        message_id,
        thread_id,
        raw_sha256,
        headers,
    ) = _draft_snapshot(draft)
    if live_draft_id != draft_id:
        raise PlanCommitError("Gmail returned a different draft id")
    payload = SendDraftPayload(
        draft_id=live_draft_id,
        message_id=message_id,
        thread_id=thread_id,
        raw_sha256=raw_sha256,
        to=headers["to"],
        cc=headers["cc"],
        bcc=headers["bcc"],
        subject=headers["subject"],
        message_id_header=headers["message_id_header"],
    )
    return create_plan(
        operation=Operation.SEND_DRAFT,
        profile=profile,
        account=account,
        payload=payload,
        expires_in_seconds=expires_in_seconds,
        output=output,
    )


def _receipt_paths(plan_id: str) -> list[Path]:
    root = receipts_dir()
    if not root.exists():
        return []
    return sorted(root.rglob(f"*_{plan_id}.json"))


def _write_receipt(receipt: OperationReceipt) -> Path:
    day = receipt.completed_at.date().isoformat()
    timestamp = receipt.completed_at.strftime("%Y%m%dT%H%M%S%fZ")
    path = receipts_dir() / day / f"{timestamp}_{receipt.plan_id}.json"
    _atomic_json_write(
        path,
        receipt.model_dump(mode="json", by_alias=True),
    )
    return path


def _acquire_plan_lock(plan_id: str) -> Path:
    directory = locks_dir()
    ensure_private_directory(directory)
    path = directory / f"{plan_id}.lock"
    try:
        descriptor = os.open(
            path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
    except FileExistsError as exc:
        raise PlanCommitError(
            f"plan is already being committed: {plan_id}"
        ) from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(f"pid={os.getpid()}\n")
    return path


def _execute_message_sequence(
    *,
    operation: Operation,
    message_ids: list[str],
    call: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    """Execute a bounded idempotent sequence and preserve partial progress."""

    completed: list[str] = []
    for message_id in message_ids:
        try:
            result = call(message_id)
        except AmbiguousWriteError as exc:
            raise PartialOperationError(
                f"{operation.value} lost certainty after "
                f"{len(completed)} of {len(message_ids)} messages",
                result={
                    "reconciliation_required": True,
                    "requested_count": len(message_ids),
                    "completed_count": len(completed),
                    "completed_message_ids": completed,
                    "uncertain_message_id": message_id,
                },
                error_code=exc.code,
                status=ReceiptStatus.INDETERMINATE,
            ) from exc
        except GmailApiError as exc:
            raise PartialOperationError(
                f"{operation.value} stopped after "
                f"{len(completed)} of {len(message_ids)} messages",
                result={
                    "requested_count": len(message_ids),
                    "completed_count": len(completed),
                    "completed_message_ids": completed,
                    "failed_message_id": message_id,
                },
                error_code=exc.code,
                status=ReceiptStatus.FAILURE,
            ) from exc
        completed.append(str(result.get("id", message_id)))
    return {
        "requested_count": len(message_ids),
        "completed_count": len(completed),
        "completed_message_ids": completed,
    }


def _validate_draft_unchanged(
    payload: SendDraftPayload,
    client: GmailClient,
) -> None:
    draft = client.get_draft(payload.draft_id, format_="RAW")
    (
        draft_id,
        message_id,
        thread_id,
        raw_sha256,
        _headers,
    ) = _draft_snapshot(draft)
    if draft_id != payload.draft_id:
        raise PlanCommitError("draft id changed after approval")
    if message_id != payload.message_id:
        raise PlanCommitError("draft message id changed after approval")
    if thread_id != payload.thread_id:
        raise PlanCommitError("draft thread id changed after approval")
    if raw_sha256 != payload.raw_sha256:
        raise PlanCommitError("draft content changed after approval")


def _execute(plan: OperationPlan, client: GmailClient) -> dict[str, Any]:
    payload = plan.payload_model()
    if plan.operation is Operation.BATCH_MODIFY:
        if not isinstance(payload, BatchModifyPayload):
            raise PlanCommitError("invalid batch-modify payload model")
        client.batch_modify(
            payload.message_ids,
            add_label_ids=payload.add_label_ids,
            remove_label_ids=payload.remove_label_ids,
        )
        return {"message_count": len(payload.message_ids)}
    if plan.operation is Operation.TRASH:
        if not isinstance(payload, MessageIdsPayload):
            raise PlanCommitError("invalid message-IDs payload model")
        return _execute_message_sequence(
            operation=plan.operation,
            message_ids=payload.message_ids,
            call=client.trash_message,
        )
    if plan.operation is Operation.UNTRASH:
        if not isinstance(payload, MessageIdsPayload):
            raise PlanCommitError("invalid message-IDs payload model")
        return _execute_message_sequence(
            operation=plan.operation,
            message_ids=payload.message_ids,
            call=client.untrash_message,
        )
    if plan.operation is Operation.CREATE_LABEL:
        if not isinstance(payload, CreateLabelPayload):
            raise PlanCommitError("invalid create-label payload model")
        result = client.create_label(payload.model_dump(mode="json"))
        return {
            "label_id": result.get("id"),
            "label_name": result.get("name"),
        }
    if plan.operation in {Operation.CREATE_DRAFT, Operation.SEND_MESSAGE}:
        if not isinstance(payload, OutboundMessagePayload):
            raise PlanCommitError("invalid outbound payload model")
        raw = build_raw_message(payload, from_address=str(plan.account))
        if plan.operation is Operation.CREATE_DRAFT:
            result = client.create_draft(
                raw=raw,
                thread_id=payload.thread_id,
            )
            message = result.get("message")
            message_data = message if isinstance(message, dict) else {}
            return {
                "draft_id": result.get("id"),
                "message_id": message_data.get("id"),
                "thread_id": message_data.get("threadId"),
                "rfc822_message_id": payload.message_id_header,
            }
        result = client.send_message(raw=raw, thread_id=payload.thread_id)
        return {
            "message_id": result.get("id"),
            "thread_id": result.get("threadId"),
            "label_ids": result.get("labelIds", []),
            "rfc822_message_id": payload.message_id_header,
        }
    if plan.operation is Operation.SEND_DRAFT:
        if not isinstance(payload, SendDraftPayload):
            raise PlanCommitError("invalid send-draft payload model")
        _validate_draft_unchanged(payload, client)
        result = client.send_draft(payload.draft_id)
        return {
            "draft_id": payload.draft_id,
            "message_id": result.get("id"),
            "thread_id": result.get("threadId"),
            "rfc822_message_id": payload.message_id_header,
        }
    raise PlanCommitError(f"unsupported operation: {plan.operation.value}")


def _reconciliation_result(plan: OperationPlan) -> dict[str, Any]:
    """Return non-secret identifiers needed to resolve an ambiguous write."""

    result: dict[str, Any] = {"reconciliation_required": True}
    payload = plan.payload_model()
    if isinstance(payload, OutboundMessagePayload):
        result["rfc822_message_id"] = payload.message_id_header
    elif isinstance(payload, SendDraftPayload):
        result.update(
            {
                "draft_id": payload.draft_id,
                "draft_message_id": payload.message_id,
                "rfc822_message_id": payload.message_id_header,
            }
        )
    return result


def _bounded_error_message(exc: Exception) -> str:
    """Bound error text so receipt validation cannot fail on a huge provider body."""

    return str(exc)[:1000]


def commit_plan(
    plan_path: Path,
    *,
    approval: str,
    client_factory: ClientFactory = default_client_factory,
) -> tuple[OperationReceipt, Path]:
    """Validate and execute exactly one approved plan, writing an outcome receipt."""

    from .models import load_plan

    plan = load_plan(plan_path.expanduser().resolve(strict=True))
    if approval != plan.approval_code:
        raise PlanCommitError("approval code does not match the plan")
    if plan.is_expired():
        raise PlanCommitError("operation plan has expired; prepare a new plan")
    prior = _receipt_paths(plan.plan_id)
    if prior:
        raise PlanCommitError(
            f"plan already has a receipt and cannot be replayed: {prior[-1]}"
        )

    lock_path = _acquire_plan_lock(plan.plan_id)
    started = utc_now()
    try:
        with client_factory(plan.profile) as client:
            profile = client.get_profile()
            live_account = str(profile.get("emailAddress", ""))
            if live_account.lower() != str(plan.account).lower():
                raise PlanCommitError(
                    f"plan account {plan.account} does not match "
                    f"authenticated account {live_account}"
                )
            result = _execute(plan, client)
        receipt = OperationReceipt(
            plan_id=plan.plan_id,
            operation=plan.operation,
            profile=plan.profile,
            account=plan.account,
            status=ReceiptStatus.SUCCESS,
            started_at=started,
            completed_at=utc_now(),
            payload_sha256=plan.payload_sha256,
            result=result,
        )
    except AmbiguousWriteError as exc:
        receipt = OperationReceipt(
            plan_id=plan.plan_id,
            operation=plan.operation,
            profile=plan.profile,
            account=plan.account,
            status=ReceiptStatus.INDETERMINATE,
            started_at=started,
            completed_at=utc_now(),
            payload_sha256=plan.payload_sha256,
            result=_reconciliation_result(plan),
            error_code=exc.code,
            error_message=_bounded_error_message(exc),
        )
    except PartialOperationError as exc:
        receipt = OperationReceipt(
            plan_id=plan.plan_id,
            operation=plan.operation,
            profile=plan.profile,
            account=plan.account,
            status=exc.status,
            started_at=started,
            completed_at=utc_now(),
            payload_sha256=plan.payload_sha256,
            result=exc.result,
            error_code=exc.error_code,
            error_message=_bounded_error_message(exc),
        )
    except Exception as exc:
        code = (
            exc.code
            if isinstance(exc, GmailApiError)
            else type(exc).__name__.lower()
        )
        receipt = OperationReceipt(
            plan_id=plan.plan_id,
            operation=plan.operation,
            profile=plan.profile,
            account=plan.account,
            status=ReceiptStatus.FAILURE,
            started_at=started,
            completed_at=utc_now(),
            payload_sha256=plan.payload_sha256,
            result={},
            error_code=code,
            error_message=_bounded_error_message(exc),
        )

    try:
        receipt_path = _write_receipt(receipt)
    except OSError as exc:
        raise PlanCommitError(
            "receipt write failed; lock retained for manual reconciliation: "
            f"{lock_path}"
        ) from exc
    lock_path.unlink(missing_ok=True)
    return receipt, receipt_path
