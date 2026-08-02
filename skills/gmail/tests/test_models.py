"""Contract tests for Gmail plans, payloads, and receipts."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from gmail_skill.models import (
    AttachmentSpec,
    BatchModifyPayload,
    OAuthProfile,
    Operation,
    OperationPlan,
    OperationReceipt,
    OutboundMessagePayload,
    ReceiptStatus,
    utc_now,
)
from gmail_skill.operations import create_plan


def test_plan_hash_and_approval_detect_tampering(tmp_path: Path) -> None:
    plan, path = create_plan(
        operation=Operation.BATCH_MODIFY,
        profile=OAuthProfile.MANAGE,
        account="owner@example.com",
        payload=BatchModifyPayload(
            message_ids=["abc"],
            add_label_ids=["STARRED"],
            remove_label_ids=[],
        ),
        output=tmp_path / "plan.json",
    )
    loaded = OperationPlan.model_validate_json(path.read_text(encoding="utf-8"))
    assert loaded.plan_id == plan.plan_id
    assert loaded.approval_code.startswith("approve:batch_modify:")

    tampered = json.loads(path.read_text(encoding="utf-8"))
    tampered["payload"]["message_ids"] = ["different"]
    with pytest.raises(ValidationError, match="payload_sha256"):
        OperationPlan.model_validate(tampered)


def test_plan_rejects_under_scoped_profile() -> None:
    now = utc_now()
    with pytest.raises(ValidationError, match="cannot execute"):
        OperationPlan.model_validate(
            {
                "schema": "gmail.operation_plan.v1",
                "plan_id": "00000000-0000-0000-0000-000000000000",
                "operation": "trash",
                "profile": "readonly",
                "account": "owner@example.com",
                "created_at": now.isoformat(),
                "expires_at": (now + timedelta(minutes=10)).isoformat(),
                "payload": {"message_ids": ["abc"]},
                "payload_sha256": "0" * 64,
                "approval_code": "approve:trash:0000000000000000",
            }
        )


def test_plan_id_rejects_path_traversal_shape() -> None:
    now = utc_now()
    with pytest.raises(ValidationError, match="plan_id"):
        OperationPlan.model_validate(
            {
                "schema": "gmail.operation_plan.v1",
                "plan_id": "../../../../tmp/receipt-overwrite-00000",
                "operation": "trash",
                "profile": "manage",
                "account": "owner@example.com",
                "created_at": now.isoformat(),
                "expires_at": (now + timedelta(minutes=10)).isoformat(),
                "payload": {"message_ids": ["abc"]},
                "payload_sha256": "0" * 64,
                "approval_code": "approve:trash:0000000000000000",
            }
        )


def test_receipt_requires_error_for_non_success() -> None:
    now = utc_now()
    with pytest.raises(ValidationError, match="error_code"):
        OperationReceipt(
            plan_id="00000000-0000-0000-0000-000000000000",
            operation=Operation.TRASH,
            profile=OAuthProfile.MANAGE,
            account="owner@example.com",
            status=ReceiptStatus.INDETERMINATE,
            started_at=now,
            completed_at=now,
            payload_sha256="0" * 64,
            result={},
        )


def test_trash_payload_is_bounded_to_fifty_messages() -> None:
    from gmail_skill.models import MessageIdsPayload

    with pytest.raises(ValidationError, match="at most 50"):
        MessageIdsPayload(message_ids=[f"m{index}" for index in range(51)])


def test_outbound_headers_reject_newline_injection() -> None:
    with pytest.raises(ValidationError, match="control character"):
        OutboundMessagePayload(
            to=["alice@example.com"],
            subject="safe\nBcc: attacker@example.com",
            text_body="Body",
            message_id_header="<plan@example.com>",
        )


def test_combined_attachment_size_is_bounded() -> None:
    attachments = [
        AttachmentSpec(
            path=f"/tmp/{index}.bin",
            filename=f"{index}.bin",
            content_type="application/octet-stream",
            size_bytes=13_000_000,
            sha256=str(index) * 64,
        )
        for index in (1, 2)
    ]
    with pytest.raises(ValidationError, match="combined attachment size"):
        OutboundMessagePayload(
            to=["alice@example.com"],
            subject="Subject",
            text_body="Body",
            attachments=attachments,
            message_id_header="<plan@example.com>",
        )
