"""MIME construction, Gmail payload normalization, and attachment snapshots."""

from __future__ import annotations

import base64
import binascii
import hashlib
import mimetypes
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses
from pathlib import Path
from typing import Any

from .models import AttachmentSpec, OutboundMessagePayload


class GmailMimeError(ValueError):
    """Raised when a MIME body or attachment violates the frozen plan."""


def decode_base64url(value: str) -> bytes:
    """Decode Gmail base64url data with optional omitted padding."""

    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding)
    except (binascii.Error, ValueError) as exc:
        raise GmailMimeError("invalid Gmail base64url payload") from exc


def encode_base64url(value: bytes) -> str:
    """Encode bytes in Gmail's base64url representation."""

    return base64.urlsafe_b64encode(value).decode("ascii")


def hash_raw_message(raw: str) -> str:
    """Hash decoded RFC 822 bytes from a Gmail Message.raw field."""

    return hashlib.sha256(decode_base64url(raw)).hexdigest()


def summarize_raw_message(raw: str) -> dict[str, Any]:
    """Extract reviewable headers from Gmail raw MIME without returning body data."""

    message = BytesParser(policy=policy.default).parsebytes(decode_base64url(raw))

    def addresses(header_name: str) -> list[str]:
        values = message.get_all(header_name, [])
        return [address for _, address in getaddresses(values) if address]

    return {
        "to": addresses("To"),
        "cc": addresses("Cc"),
        "bcc": addresses("Bcc"),
        "subject": str(message.get("Subject", "")),
        "message_id_header": (
            str(message.get("Message-ID")) if message.get("Message-ID") else None
        ),
    }


def snapshot_attachment(path: Path) -> AttachmentSpec:
    """Hash one attachment and capture immutable metadata for commit-time checks."""

    resolved = path.expanduser().resolve(strict=True)
    if not resolved.is_file():
        raise GmailMimeError(f"attachment is not a regular file: {resolved}")
    size = resolved.stat().st_size
    if size > 25_000_000:
        raise GmailMimeError(
            f"attachment exceeds the skill's conservative 25 MB limit: {resolved}"
        )
    digest = hashlib.sha256()
    with resolved.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    content_type = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
    return AttachmentSpec(
        path=str(resolved),
        filename=resolved.name,
        content_type=content_type,
        size_bytes=size,
        sha256=digest.hexdigest(),
    )


def verify_attachment(spec: AttachmentSpec) -> bytes:
    """Read an attachment only when path, size, and SHA-256 still match the plan."""

    path = Path(spec.path)
    if not path.is_file():
        raise GmailMimeError(f"planned attachment is missing: {path}")
    data = path.read_bytes()
    if len(data) != spec.size_bytes:
        raise GmailMimeError(f"planned attachment size changed: {path}")
    digest = hashlib.sha256(data).hexdigest()
    if digest != spec.sha256:
        raise GmailMimeError(f"planned attachment content changed: {path}")
    return data


def build_raw_message(payload: OutboundMessagePayload, *, from_address: str) -> str:
    """Build an RFC-compliant outgoing message and return Gmail base64url data."""

    message = EmailMessage()
    message["From"] = from_address
    message["To"] = ", ".join(str(value) for value in payload.to)
    if payload.cc:
        message["Cc"] = ", ".join(str(value) for value in payload.cc)
    if payload.bcc:
        message["Bcc"] = ", ".join(str(value) for value in payload.bcc)
    message["Subject"] = payload.subject
    message["Message-ID"] = payload.message_id_header
    if payload.in_reply_to:
        message["In-Reply-To"] = payload.in_reply_to
    if payload.references:
        message["References"] = " ".join(payload.references)

    if payload.text_body is not None:
        message.set_content(payload.text_body)
        if payload.html_body is not None:
            message.add_alternative(payload.html_body, subtype="html")
    elif payload.html_body is not None:
        message.set_content("This message contains HTML content.")
        message.add_alternative(payload.html_body, subtype="html")

    for attachment in payload.attachments:
        data = verify_attachment(attachment)
        main_type, sub_type = attachment.content_type.split("/", 1)
        message.add_attachment(
            data,
            maintype=main_type,
            subtype=sub_type,
            filename=attachment.filename,
        )

    return encode_base64url(message.as_bytes())


def _headers(payload: dict[str, Any]) -> dict[str, str]:
    headers = payload.get("headers", [])
    if not isinstance(headers, list):
        return {}
    return {
        str(item.get("name", "")).lower(): str(item.get("value", ""))
        for item in headers
        if isinstance(item, dict)
    }


def _walk_parts(part: dict[str, Any], output: dict[str, Any]) -> None:
    mime_type = str(part.get("mimeType", ""))
    filename = str(part.get("filename", ""))
    body = part.get("body") if isinstance(part.get("body"), dict) else {}
    data = body.get("data")
    attachment_id = body.get("attachmentId")

    if filename or attachment_id:
        output["attachments"].append(
            {
                "part_id": part.get("partId"),
                "filename": filename,
                "mime_type": mime_type,
                "attachment_id": attachment_id,
                "size": body.get("size", 0),
            }
        )
    elif isinstance(data, str) and data:
        decoded = decode_base64url(data).decode("utf-8", errors="replace")
        if mime_type == "text/plain":
            output["text_parts"].append(decoded)
        elif mime_type == "text/html":
            output["html_parts"].append(decoded)

    children = part.get("parts", []) or []
    if not isinstance(children, list):
        return
    for child in children:
        if isinstance(child, dict):
            _walk_parts(child, output)


def normalize_message(
    message: dict[str, Any],
    *,
    include_bodies: bool = True,
) -> dict[str, Any]:
    """Normalize a Gmail Message resource without returning raw MIME bytes."""

    payload = message.get("payload") if isinstance(message.get("payload"), dict) else {}
    headers = _headers(payload)
    parts: dict[str, Any] = {
        "text_parts": [],
        "html_parts": [],
        "attachments": [],
    }
    if include_bodies:
        _walk_parts(payload, parts)

    return {
        "id": message.get("id"),
        "thread_id": message.get("threadId"),
        "label_ids": message.get("labelIds", []),
        "snippet": message.get("snippet"),
        "history_id": message.get("historyId"),
        "internal_date": message.get("internalDate"),
        "size_estimate": message.get("sizeEstimate"),
        "headers": {
            "from": headers.get("from"),
            "to": headers.get("to"),
            "cc": headers.get("cc"),
            "bcc": headers.get("bcc"),
            "subject": headers.get("subject"),
            "date": headers.get("date"),
            "message_id": headers.get("message-id"),
            "in_reply_to": headers.get("in-reply-to"),
            "references": headers.get("references"),
        },
        "text_body": "\n".join(parts["text_parts"]) if include_bodies else None,
        "html_body": "\n".join(parts["html_parts"]) if include_bodies else None,
        "attachments": parts["attachments"] if include_bodies else [],
    }
