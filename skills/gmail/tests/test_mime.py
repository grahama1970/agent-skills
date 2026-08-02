"""MIME and Gmail payload normalization tests."""

from __future__ import annotations

import base64
from email import policy
from email.parser import BytesParser
from pathlib import Path

import pytest

from gmail_skill.mime import (
    GmailMimeError,
    build_raw_message,
    decode_base64url,
    encode_base64url,
    normalize_message,
    snapshot_attachment,
)
from gmail_skill.models import OutboundMessagePayload


def test_build_raw_message_preserves_reviewed_headers_and_attachment(tmp_path: Path) -> None:
    attachment_path = tmp_path / "proof.txt"
    attachment_path.write_text("proof", encoding="utf-8")
    payload = OutboundMessagePayload(
        to=["alice@example.com"],
        cc=["bob@example.com"],
        subject="Reviewed subject",
        text_body="Plain body",
        html_body="<p>HTML body</p>",
        attachments=[snapshot_attachment(attachment_path)],
        message_id_header="<plan-123@example.com>",
    )
    raw = build_raw_message(payload, from_address="owner@example.com")
    parsed = BytesParser(policy=policy.default).parsebytes(decode_base64url(raw))
    assert parsed["From"] == "owner@example.com"
    assert parsed["To"] == "alice@example.com"
    assert parsed["Cc"] == "bob@example.com"
    assert parsed["Subject"] == "Reviewed subject"
    assert parsed["Message-ID"] == "<plan-123@example.com>"
    assert any(part.get_filename() == "proof.txt" for part in parsed.walk())


def test_attachment_hash_drift_fails_closed(tmp_path: Path) -> None:
    attachment_path = tmp_path / "proof.txt"
    attachment_path.write_text("before", encoding="utf-8")
    spec = snapshot_attachment(attachment_path)
    attachment_path.write_text("after", encoding="utf-8")
    payload = OutboundMessagePayload(
        to=["alice@example.com"],
        subject="Subject",
        text_body="Body",
        attachments=[spec],
        message_id_header="<plan-123@example.com>",
    )
    with pytest.raises(GmailMimeError, match="changed"):
        build_raw_message(payload, from_address="owner@example.com")


def test_normalize_nested_gmail_payload() -> None:
    message = {
        "id": "m1",
        "threadId": "t1",
        "labelIds": ["INBOX", "UNREAD"],
        "snippet": "hello",
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [
                {"name": "From", "value": "alice@example.com"},
                {"name": "Subject", "value": "Test"},
                {"name": "Message-ID", "value": "<m1@example.com>"},
            ],
            "parts": [
                {
                    "partId": "0",
                    "mimeType": "text/plain",
                    "filename": "",
                    "body": {"data": encode_base64url(b"hello body")},
                },
                {
                    "partId": "1",
                    "mimeType": "application/pdf",
                    "filename": "file.pdf",
                    "body": {"attachmentId": "a1", "size": 10},
                },
            ],
        },
    }
    normalized = normalize_message(message)
    assert normalized["headers"]["from"] == "alice@example.com"
    assert normalized["headers"]["subject"] == "Test"
    assert normalized["text_body"] == "hello body"
    assert normalized["attachments"][0]["attachment_id"] == "a1"


def test_base64url_accepts_missing_padding() -> None:
    encoded = base64.urlsafe_b64encode(b"abcde").decode("ascii").rstrip("=")
    assert decode_base64url(encoded) == b"abcde"
