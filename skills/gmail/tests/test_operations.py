"""Two-phase operation execution, drift checks, and receipt tests."""

from __future__ import annotations

import json
import stat
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import pytest

import gmail_skill.operations as operations
from gmail_skill.api import AmbiguousWriteError
from gmail_skill.mime import encode_base64url
from gmail_skill.models import OAuthProfile, Operation, ReceiptStatus


def _draft_raw(*, subject: str = "Reviewed draft", body: str = "Draft body") -> str:
    message = EmailMessage()
    message["From"] = "owner@example.com"
    message["To"] = "alice@example.com"
    message["Subject"] = subject
    message["Message-ID"] = "<draft-message@example.com>"
    message.set_content(body)
    return encode_base64url(message.as_bytes())


class FakeClient:
    def __init__(
        self,
        profile: OAuthProfile,
        *,
        ambiguous_send: bool = False,
        fail_trash_id: str | None = None,
        ambiguous_trash_id: str | None = None,
    ) -> None:
        self.profile = profile
        self.ambiguous_send = ambiguous_send
        self.fail_trash_id = fail_trash_id
        self.ambiguous_trash_id = ambiguous_trash_id
        self.calls: list[tuple[str, Any]] = []
        self.draft_raw = _draft_raw()
        self.draft_message_id = "draft-message-1"

    def __enter__(self) -> "FakeClient":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def get_profile(self) -> dict[str, Any]:
        return {"emailAddress": "owner@example.com"}

    def get_draft(self, draft_id: str, *, format_: str = "FULL") -> dict[str, Any]:
        self.calls.append(("get_draft", (draft_id, format_)))
        return {
            "id": draft_id,
            "message": {
                "id": self.draft_message_id,
                "threadId": "draft-thread-1",
                "raw": self.draft_raw,
            },
        }

    def batch_modify(
        self,
        message_ids: list[str],
        *,
        add_label_ids: list[str],
        remove_label_ids: list[str],
    ) -> dict[str, Any]:
        self.calls.append(
            (
                "batch_modify",
                (message_ids, add_label_ids, remove_label_ids),
            )
        )
        return {}

    def send_message(
        self,
        *,
        raw: str,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(("send_message", (raw, thread_id)))
        if self.ambiguous_send:
            raise AmbiguousWriteError(
                "lost response",
                code="transport_ambiguous",
            )
        return {
            "id": "sent-1",
            "threadId": "thread-1",
            "labelIds": ["SENT"],
        }

    def create_draft(
        self,
        *,
        raw: str,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "id": "draft-1",
            "message": {
                "id": "message-1",
                "threadId": "thread-1",
            },
        }

    def trash_message(self, message_id: str) -> dict[str, Any]:
        if message_id == self.ambiguous_trash_id:
            raise AmbiguousWriteError(
                "lost response",
                code="transport_ambiguous",
            )
        if message_id == self.fail_trash_id:
            from gmail_skill.api import GmailApiError

            raise GmailApiError(
                "denied",
                code="http_403",
                status_code=403,
            )
        return {"id": message_id}

    def untrash_message(self, message_id: str) -> dict[str, Any]:
        return {"id": message_id}

    def create_label(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"id": "Label_1", "name": payload["name"]}

    def send_draft(self, draft_id: str) -> dict[str, Any]:
        self.calls.append(("send_draft", draft_id))
        return {"id": "sent-draft", "threadId": "thread-1"}


def _factory(client: FakeClient):
    def build(profile: OAuthProfile) -> FakeClient:
        assert profile == client.profile
        return client

    return build


def test_mailbox_commit_requires_exact_approval_and_is_not_replayable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(operations, "state_root", lambda: tmp_path / "state")
    client = FakeClient(OAuthProfile.MANAGE)
    plan, path = operations.prepare_mailbox_plan(
        action="archive",
        message_ids=["m1", "m2"],
        output=tmp_path / "archive-plan.json",
        client_factory=_factory(client),
    )

    with pytest.raises(operations.PlanCommitError, match="approval"):
        operations.commit_plan(
            path,
            approval="wrong",
            client_factory=_factory(client),
        )

    receipt, receipt_path = operations.commit_plan(
        path,
        approval=plan.approval_code,
        client_factory=_factory(client),
    )
    assert receipt.status is ReceiptStatus.SUCCESS
    assert receipt.result == {"message_count": 2}
    assert receipt_path.is_file()
    receipt_text = receipt_path.read_text(encoding="utf-8")
    assert "Authorization" not in receipt_text
    assert "message body" not in receipt_text

    with pytest.raises(operations.PlanCommitError, match="already has a receipt"):
        operations.commit_plan(
            path,
            approval=plan.approval_code,
            client_factory=_factory(client),
        )


def test_ambiguous_send_writes_indeterminate_non_replayable_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(operations, "state_root", lambda: tmp_path / "state")
    client = FakeClient(OAuthProfile.COMPOSE, ambiguous_send=True)
    plan, path = operations.prepare_outbound_plan(
        mode="send",
        profile=OAuthProfile.COMPOSE,
        to=["alice@example.com"],
        subject="Subject",
        text_body="Sensitive body",
        html_body=None,
        output=tmp_path / "send-plan.json",
        client_factory=_factory(client),
    )
    receipt, receipt_path = operations.commit_plan(
        path,
        approval=plan.approval_code,
        client_factory=_factory(client),
    )
    assert receipt.status is ReceiptStatus.INDETERMINATE
    stored = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert stored["result"]["reconciliation_required"] is True
    assert stored["result"]["rfc822_message_id"].startswith("<")
    assert "Sensitive body" not in receipt_path.read_text(encoding="utf-8")
    with pytest.raises(operations.PlanCommitError, match="already has a receipt"):
        operations.commit_plan(
            path,
            approval=plan.approval_code,
            client_factory=_factory(client),
        )


def test_partial_trash_receipt_preserves_progress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(operations, "state_root", lambda: tmp_path / "state")
    client = FakeClient(OAuthProfile.MANAGE, fail_trash_id="m2")
    plan, path = operations.prepare_mailbox_plan(
        action="trash",
        message_ids=["m1", "m2", "m3"],
        output=tmp_path / "trash-plan.json",
        client_factory=_factory(client),
    )
    receipt, _ = operations.commit_plan(
        path,
        approval=plan.approval_code,
        client_factory=_factory(client),
    )
    assert receipt.status is ReceiptStatus.FAILURE
    assert receipt.result == {
        "requested_count": 3,
        "completed_count": 1,
        "completed_message_ids": ["m1"],
        "failed_message_id": "m2",
    }
    assert receipt.error_code == "http_403"


def test_partial_trash_ambiguity_is_not_reported_as_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(operations, "state_root", lambda: tmp_path / "state")
    client = FakeClient(OAuthProfile.MANAGE, ambiguous_trash_id="m2")
    plan, path = operations.prepare_mailbox_plan(
        action="trash",
        message_ids=["m1", "m2", "m3"],
        output=tmp_path / "trash-plan.json",
        client_factory=_factory(client),
    )
    receipt, _ = operations.commit_plan(
        path,
        approval=plan.approval_code,
        client_factory=_factory(client),
    )
    assert receipt.status is ReceiptStatus.INDETERMINATE
    assert receipt.result["completed_message_ids"] == ["m1"]
    assert receipt.result["uncertain_message_id"] == "m2"
    assert receipt.result["reconciliation_required"] is True


def test_send_draft_revalidates_raw_mime_before_send(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(operations, "state_root", lambda: tmp_path / "state")
    client = FakeClient(OAuthProfile.COMPOSE)
    plan, path = operations.prepare_send_draft_plan(
        draft_id="draft-1",
        profile=OAuthProfile.COMPOSE,
        output=tmp_path / "draft-plan.json",
        client_factory=_factory(client),
    )
    receipt, _ = operations.commit_plan(
        path,
        approval=plan.approval_code,
        client_factory=_factory(client),
    )
    assert receipt.status is ReceiptStatus.SUCCESS
    assert ("send_draft", "draft-1") in client.calls


def test_send_draft_fails_when_content_changed_after_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(operations, "state_root", lambda: tmp_path / "state")
    client = FakeClient(OAuthProfile.COMPOSE)
    plan, path = operations.prepare_send_draft_plan(
        draft_id="draft-1",
        profile=OAuthProfile.COMPOSE,
        output=tmp_path / "draft-plan.json",
        client_factory=_factory(client),
    )
    client.draft_raw = _draft_raw(body="Changed after approval")
    receipt, _ = operations.commit_plan(
        path,
        approval=plan.approval_code,
        client_factory=_factory(client),
    )
    assert receipt.status is ReceiptStatus.FAILURE
    assert receipt.error_code == "plancommiterror"
    assert "changed after approval" in str(receipt.error_message)
    assert ("send_draft", "draft-1") not in client.calls


def test_custom_plan_output_does_not_chmod_parent_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(operations, "state_root", lambda: tmp_path / "state")
    output_directory = tmp_path / "shared"
    output_directory.mkdir(mode=0o755)
    operations.create_plan(
        operation=Operation.BATCH_MODIFY,
        profile=OAuthProfile.MANAGE,
        account="owner@example.com",
        payload=operations.BatchModifyPayload(
            message_ids=["m1"],
            add_label_ids=["STARRED"],
        ),
        output=output_directory / "plan.json",
    )
    assert stat.S_IMODE(output_directory.stat().st_mode) == 0o755


def test_receipt_write_failure_retains_lock_for_manual_reconciliation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(operations, "state_root", lambda: tmp_path / "state")
    client = FakeClient(OAuthProfile.MANAGE)
    plan, path = operations.prepare_mailbox_plan(
        action="archive",
        message_ids=["m1"],
        output=tmp_path / "archive-plan.json",
        client_factory=_factory(client),
    )

    def fail_receipt_write(_receipt: object) -> Path:
        raise OSError("disk full")

    monkeypatch.setattr(operations, "_write_receipt", fail_receipt_write)
    with pytest.raises(operations.PlanCommitError, match="lock retained"):
        operations.commit_plan(
            path,
            approval=plan.approval_code,
            client_factory=_factory(client),
        )
    assert (
        tmp_path / "state" / "locks" / f"{plan.plan_id}.lock"
    ).is_file()
