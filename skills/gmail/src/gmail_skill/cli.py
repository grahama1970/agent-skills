"""Typer CLI for API-first Gmail search, read, planning, and commit workflows."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import typer
from loguru import logger

from .api import GmailApiError, GmailClient
from .auth import (
    GmailAuthError,
    access_token,
    login,
    profile_status,
    safe_token_metadata,
    state_root,
)
from .mime import decode_base64url, normalize_message
from .models import (
    BatchModifyPayload,
    CreateLabelPayload,
    MessageIdsPayload,
    OAuthProfile,
    OperationPlan,
    OutboundMessagePayload,
    SendDraftPayload,
    load_plan,
)
from .operations import (
    PlanCommitError,
    commit_plan,
    prepare_label_plan,
    prepare_mailbox_plan,
    prepare_outbound_plan,
    prepare_send_draft_plan,
)


app = typer.Typer(
    name="gmail",
    help="API-first Gmail control with least-privilege OAuth and two-phase writes.",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)
auth_app = typer.Typer(
    help="Authorize and inspect isolated OAuth profiles.",
    no_args_is_help=True,
)
message_app = typer.Typer(
    help="Read messages and download selected attachments.",
    no_args_is_help=True,
)
thread_app = typer.Typer(
    help="Read Gmail conversation threads.",
    no_args_is_help=True,
)
label_app = typer.Typer(
    help="List labels. Label creation is plan-gated.",
    no_args_is_help=True,
)
draft_app = typer.Typer(
    help="Read/list drafts. Sending a draft is plan-gated.",
    no_args_is_help=True,
)
plan_app = typer.Typer(
    help="Prepare, review, and commit external-effect operations.",
    no_args_is_help=True,
)
app.add_typer(auth_app, name="auth")
app.add_typer(message_app, name="message")
app.add_typer(thread_app, name="thread")
app.add_typer(label_app, name="label")
app.add_typer(draft_app, name="draft")
app.add_typer(plan_app, name="plan")


def _emit(value: Any) -> None:
    typer.echo(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
    )


def _require_profile(
    profile: OAuthProfile,
    allowed: set[OAuthProfile],
    task: str,
) -> None:
    if profile not in allowed:
        names = ", ".join(sorted(item.value for item in allowed))
        raise typer.BadParameter(f"{task} requires one of these profiles: {names}")


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError):
        return False


def _destination_path(path: Path) -> Path:
    """Resolve the parent while preserving the final path entry for safe replacement."""

    expanded = path.expanduser()
    if not expanded.is_absolute():
        expanded = Path.cwd() / expanded
    return expanded.parent.resolve() / expanded.name


def _atomic_private_bytes(
    path: Path,
    content: bytes,
    *,
    overwrite: bool,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if overwrite:
            os.replace(temporary_path, path)
        else:
            try:
                os.link(temporary_path, path)
            except FileExistsError as exc:
                raise FileExistsError(f"output already exists: {path}") from exc
            temporary_path.unlink()
        path.chmod(0o600)
    finally:
        temporary_path.unlink(missing_ok=True)


def _client(profile: OAuthProfile) -> GmailClient:
    return GmailClient(access_token=access_token(profile), profile=profile)


def _read_optional_file(path: Path | None) -> str | None:
    if path is None:
        return None
    resolved = path.expanduser().resolve(strict=True)
    if not resolved.is_file():
        raise typer.BadParameter(f"not a regular file: {resolved}")
    if resolved.stat().st_size > 2_000_000:
        raise typer.BadParameter(f"body file exceeds 2 MB: {resolved}")
    return resolved.read_text(encoding="utf-8")


def _plan_summary(plan: OperationPlan, path: Path) -> dict[str, Any]:
    payload = plan.payload_model()
    summary: dict[str, Any] = {
        "status": "approval_required",
        "plan_path": str(path),
        "plan_id": plan.plan_id,
        "operation": plan.operation.value,
        "profile": plan.profile.value,
        "account": str(plan.account),
        "expires_at": plan.expires_at.isoformat(),
        "payload_sha256": plan.payload_sha256,
        "approval_code": plan.approval_code,
    }
    if isinstance(payload, (BatchModifyPayload, MessageIdsPayload)):
        summary["message_count"] = len(payload.message_ids)
    elif isinstance(payload, OutboundMessagePayload):
        summary.update(
            {
                "recipients": {
                    "to": [str(value) for value in payload.to],
                    "cc": [str(value) for value in payload.cc],
                    "bcc": [str(value) for value in payload.bcc],
                },
                "subject": payload.subject,
                "attachment_count": len(payload.attachments),
                "rfc822_message_id": payload.message_id_header,
            }
        )
    elif isinstance(payload, SendDraftPayload):
        summary.update(
            {
                "draft_id": payload.draft_id,
                "draft_message_id": payload.message_id,
                "draft_raw_sha256": payload.raw_sha256,
                "recipients": {
                    "to": [str(value) for value in payload.to],
                    "cc": [str(value) for value in payload.cc],
                    "bcc": [str(value) for value in payload.bcc],
                },
                "subject": payload.subject,
                "rfc822_message_id": payload.message_id_header,
            }
        )
    elif isinstance(payload, CreateLabelPayload):
        summary["label_name"] = payload.name
    return summary


def _message_entries(listing: dict[str, Any]) -> list[dict[str, Any]]:
    raw_entries = listing.get("messages", []) or []
    if not isinstance(raw_entries, list):
        raise GmailApiError(
            "Gmail message list returned an invalid messages field",
            code="invalid_shape",
        )
    entries: list[dict[str, Any]] = []
    for entry in raw_entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            raise GmailApiError(
                "Gmail message list returned an entry without an id",
                code="invalid_shape",
            )
        entries.append(entry)
    return entries


def _thread_messages(thread: dict[str, Any]) -> list[dict[str, Any]]:
    raw_messages = thread.get("messages", []) or []
    if not isinstance(raw_messages, list):
        raise GmailApiError(
            "Gmail thread returned an invalid messages field",
            code="invalid_shape",
        )
    messages: list[dict[str, Any]] = []
    for message in raw_messages:
        if not isinstance(message, dict):
            raise GmailApiError(
                "Gmail thread returned a non-object message",
                code="invalid_shape",
            )
        messages.append(message)
    return messages


@auth_app.command("login")
def auth_login(
    client_secret: Path = typer.Option(
        ...,
        "--client-secret",
        exists=True,
        dir_okay=False,
    ),
    profile: OAuthProfile = typer.Option(OAuthProfile.READONLY, "--profile"),
    port: int = typer.Option(0, min=0, max=65535),
    open_browser: bool = typer.Option(
        True,
        "--open-browser/--no-open-browser",
    ),
) -> None:
    """Run installed-app OAuth consent for one exact Gmail scope profile."""

    path = login(
        profile,
        client_secret.expanduser().resolve(),
        port=port,
        open_browser=open_browser,
    )
    with _client(profile) as client:
        gmail_profile = client.get_profile()
    _emit(
        {
            "status": "authorized",
            "profile": profile.value,
            "account": gmail_profile.get("emailAddress"),
            "token_path": str(path),
            "token_metadata": safe_token_metadata(profile),
        }
    )


@auth_app.command("status")
def auth_status(
    profile: OAuthProfile | None = typer.Option(None, "--profile"),
    validate: bool = typer.Option(
        False,
        "--validate",
        help="Refresh when needed and validate the stored credential.",
    ),
) -> None:
    """Show non-secret OAuth profile status."""

    profiles = [profile] if profile else list(OAuthProfile)
    _emit(
        {
            "profiles": [
                profile_status(item, validate=validate)
                for item in profiles
            ]
        }
    )


@app.command("profile")
def gmail_profile(
    profile: OAuthProfile = typer.Option(OAuthProfile.READONLY, "--profile"),
) -> None:
    """Return the current Gmail account profile."""

    with _client(profile) as client:
        _emit(client.get_profile())


@app.command("search")
def search_messages(
    query: str = typer.Argument("", help="Gmail search-box query syntax."),
    label_id: list[str] | None = typer.Option(None, "--label-id"),
    max_results: int = typer.Option(10, min=1, max=100),
    page_token: str | None = typer.Option(None),
    include_spam_trash: bool = typer.Option(False),
    hydrate: str = typer.Option("metadata", help="none, metadata, or full"),
    profile: OAuthProfile = typer.Option(OAuthProfile.READONLY, "--profile"),
) -> None:
    """Search messages, optionally fetching normalized metadata or bodies."""

    _require_profile(
        profile,
        {OAuthProfile.READONLY, OAuthProfile.MANAGE},
        "search",
    )
    hydrate_mode = hydrate.lower()
    if hydrate_mode not in {"none", "metadata", "full"}:
        raise typer.BadParameter("hydrate must be none, metadata, or full")
    labels = list(label_id or [])
    with _client(profile) as client:
        listing = client.list_messages(
            query=query,
            label_ids=labels or None,
            max_results=max_results,
            page_token=page_token,
            include_spam_trash=include_spam_trash,
        )
        messages: list[dict[str, Any]] = _message_entries(listing)
        if hydrate_mode != "none":
            format_ = "FULL" if hydrate_mode == "full" else "METADATA"
            messages = [
                normalize_message(
                    client.get_message(str(item["id"]), format_=format_),
                    include_bodies=hydrate_mode == "full",
                )
                for item in messages
            ]
    _emit(
        {
            "query": query,
            "label_ids": labels,
            "coverage": {
                "returned": len(messages),
                "result_size_estimate": listing.get("resultSizeEstimate"),
                "next_page_token": listing.get("nextPageToken"),
                "hydrate": hydrate_mode,
            },
            "messages": messages,
        }
    )


@message_app.command("get")
def get_message(
    message_id: str,
    metadata_only: bool = typer.Option(False, "--metadata-only"),
    profile: OAuthProfile = typer.Option(OAuthProfile.READONLY, "--profile"),
) -> None:
    """Read one Gmail message as normalized JSON."""

    _require_profile(
        profile,
        {OAuthProfile.READONLY, OAuthProfile.MANAGE},
        "message get",
    )
    format_ = "METADATA" if metadata_only else "FULL"
    with _client(profile) as client:
        message = client.get_message(message_id, format_=format_)
    _emit(normalize_message(message, include_bodies=not metadata_only))


@message_app.command("attachment")
def get_attachment(
    message_id: str,
    attachment_id: str,
    output: Path = typer.Option(..., "--output", dir_okay=False),
    overwrite: bool = typer.Option(False, "--overwrite"),
    profile: OAuthProfile = typer.Option(OAuthProfile.READONLY, "--profile"),
) -> None:
    """Download one explicitly selected Gmail attachment."""

    _require_profile(
        profile,
        {OAuthProfile.READONLY, OAuthProfile.MANAGE},
        "attachment read",
    )
    destination = _destination_path(output)
    with _client(profile) as client:
        data = client.get_attachment(message_id, attachment_id)
    encoded = data.get("data")
    if not isinstance(encoded, str):
        raise GmailApiError(
            "attachment response omitted data",
            code="invalid_attachment",
        )
    content = decode_base64url(encoded)
    expected_size = data.get("size")
    if isinstance(expected_size, int) and expected_size != len(content):
        raise GmailApiError(
            "attachment response size did not match decoded data",
            code="invalid_attachment",
        )
    _atomic_private_bytes(destination, content, overwrite=overwrite)
    _emit({"output": str(destination), "size_bytes": len(content)})


@thread_app.command("get")
def get_thread(
    thread_id: str,
    metadata_only: bool = typer.Option(False, "--metadata-only"),
    profile: OAuthProfile = typer.Option(OAuthProfile.READONLY, "--profile"),
) -> None:
    """Read all messages returned for one Gmail thread."""

    _require_profile(
        profile,
        {OAuthProfile.READONLY, OAuthProfile.MANAGE},
        "thread get",
    )
    format_ = "METADATA" if metadata_only else "FULL"
    with _client(profile) as client:
        thread = client.get_thread(thread_id, format_=format_)
    messages = [
        normalize_message(item, include_bodies=not metadata_only)
        for item in _thread_messages(thread)
    ]
    _emit(
        {
            "thread_id": thread.get("id", thread_id),
            "history_id": thread.get("historyId"),
            "messages": messages,
        }
    )


@label_app.command("list")
def list_labels(
    profile: OAuthProfile = typer.Option(OAuthProfile.READONLY, "--profile"),
) -> None:
    """List Gmail system and user labels with counts."""

    _require_profile(
        profile,
        {OAuthProfile.READONLY, OAuthProfile.MANAGE},
        "label list",
    )
    with _client(profile) as client:
        _emit(client.list_labels())


@draft_app.command("list")
def list_drafts(
    query: str = typer.Option("", "--query"),
    max_results: int = typer.Option(10, min=1, max=100),
    page_token: str | None = typer.Option(None),
    profile: OAuthProfile = typer.Option(OAuthProfile.COMPOSE, "--profile"),
) -> None:
    """List draft IDs without sending or modifying them."""

    with _client(profile) as client:
        _emit(
            client.list_drafts(
                query=query,
                max_results=max_results,
                page_token=page_token,
            )
        )


@draft_app.command("get")
def get_draft(
    draft_id: str,
    metadata_only: bool = typer.Option(False, "--metadata-only"),
    profile: OAuthProfile = typer.Option(OAuthProfile.COMPOSE, "--profile"),
) -> None:
    """Read one existing Gmail draft for human review; never send it."""

    format_ = "METADATA" if metadata_only else "FULL"
    with _client(profile) as client:
        draft = client.get_draft(draft_id, format_=format_)
    message = draft.get("message")
    if not isinstance(message, dict):
        raise GmailApiError(
            "Gmail draft response omitted message",
            code="invalid_shape",
        )
    _emit(
        {
            "draft_id": draft.get("id", draft_id),
            "message": normalize_message(
                message,
                include_bodies=not metadata_only,
            ),
        }
    )


@plan_app.command("mailbox")
def plan_mailbox(
    action: str = typer.Option(
        ...,
        help=(
            "archive, unarchive, mark-read, mark-unread, star, unstar, "
            "labels, trash, untrash"
        ),
    ),
    message_id: list[str] = typer.Option(..., "--message-id"),
    add_label_id: list[str] | None = typer.Option(None, "--add-label-id"),
    remove_label_id: list[str] | None = typer.Option(None, "--remove-label-id"),
    expires_in: int = typer.Option(1800, min=60, max=86400),
    output: Path | None = typer.Option(None, "--output", dir_okay=False),
) -> None:
    """Prepare a mailbox mutation; this command never changes Gmail."""

    plan, path = prepare_mailbox_plan(
        action=action,
        message_ids=message_id,
        add_label_ids=list(add_label_id or []),
        remove_label_ids=list(remove_label_id or []),
        expires_in_seconds=expires_in,
        output=output,
    )
    _emit(_plan_summary(plan, path))


@plan_app.command("outbound")
def plan_outbound(
    mode: str = typer.Option(..., help="draft or send"),
    to: list[str] = typer.Option(..., "--to"),
    subject: str = typer.Option(..., "--subject"),
    body: str | None = typer.Option(
        None,
        "--body",
        help="Inline body; --body-file is safer for shell history.",
    ),
    body_file: Path | None = typer.Option(
        None,
        "--body-file",
        exists=True,
        dir_okay=False,
    ),
    html_file: Path | None = typer.Option(
        None,
        "--html-file",
        exists=True,
        dir_okay=False,
    ),
    cc: list[str] | None = typer.Option(None, "--cc"),
    bcc: list[str] | None = typer.Option(None, "--bcc"),
    attachment: list[Path] | None = typer.Option(
        None,
        "--attachment",
        exists=True,
        dir_okay=False,
    ),
    thread_id: str | None = typer.Option(None, "--thread-id"),
    in_reply_to: str | None = typer.Option(None, "--in-reply-to"),
    reference: list[str] | None = typer.Option(None, "--reference"),
    profile: OAuthProfile = typer.Option(OAuthProfile.COMPOSE, "--profile"),
    expires_in: int = typer.Option(1800, min=60, max=86400),
    output: Path | None = typer.Option(None, "--output", dir_okay=False),
) -> None:
    """Prepare exact draft/send content; this command never writes Gmail."""

    if body is not None and body_file is not None:
        raise typer.BadParameter("use either --body or --body-file, not both")
    text_body = body if body is not None else _read_optional_file(body_file)
    html_body = _read_optional_file(html_file)
    plan, path = prepare_outbound_plan(
        mode=mode,
        profile=profile,
        to=to,
        cc=list(cc or []),
        bcc=list(bcc or []),
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        attachment_paths=list(attachment or []),
        thread_id=thread_id,
        in_reply_to=in_reply_to,
        references=list(reference or []),
        expires_in_seconds=expires_in,
        output=output,
    )
    _emit(_plan_summary(plan, path))


@plan_app.command("label-create")
def plan_label_create(
    name: str,
    message_list_visibility: str = typer.Option("show"),
    label_list_visibility: str = typer.Option("labelShow"),
    expires_in: int = typer.Option(1800, min=60, max=86400),
    output: Path | None = typer.Option(None, "--output", dir_okay=False),
) -> None:
    """Prepare creation of one Gmail user label."""

    plan, path = prepare_label_plan(
        name=name,
        message_list_visibility=message_list_visibility,
        label_list_visibility=label_list_visibility,
        expires_in_seconds=expires_in,
        output=output,
    )
    _emit(_plan_summary(plan, path))


@plan_app.command("send-draft")
def plan_send_draft(
    draft_id: str,
    profile: OAuthProfile = typer.Option(OAuthProfile.COMPOSE, "--profile"),
    expires_in: int = typer.Option(1800, min=60, max=86400),
    output: Path | None = typer.Option(None, "--output", dir_okay=False),
) -> None:
    """Prepare sending a reviewed draft and snapshot its raw MIME hash."""

    plan, path = prepare_send_draft_plan(
        draft_id=draft_id,
        profile=profile,
        expires_in_seconds=expires_in,
        output=output,
    )
    _emit(_plan_summary(plan, path))


@plan_app.command("show")
def plan_show(
    path: Path = typer.Argument(..., exists=True, dir_okay=False),
) -> None:
    """Review the complete local plan, including exact direct-outbound content."""

    plan = load_plan(path.expanduser().resolve())
    _emit(plan.model_dump(mode="json", by_alias=True))


@plan_app.command("commit")
def plan_commit(
    path: Path = typer.Argument(..., exists=True, dir_okay=False),
    approval: str = typer.Option(..., "--approval"),
) -> None:
    """Execute one reviewed plan exactly once and emit its receipt."""

    receipt, receipt_path = commit_plan(path, approval=approval)
    result = receipt.model_dump(mode="json", by_alias=True)
    result["receipt_path"] = str(receipt_path)
    _emit(result)
    if receipt.status.value != "success":
        raise typer.Exit(code=1)


@app.command("doctor")
def doctor(
    live_profile: OAuthProfile | None = typer.Option(None, "--live-profile"),
) -> None:
    """Check dependencies, private state, token posture, and optional reachability."""

    dependency_names = [
        "httpx",
        "pydantic",
        "typer",
        "loguru",
        "email_validator",
        "google.auth",
        "google_auth_oauthlib",
    ]
    dependencies = {
        name: _module_available(name)
        for name in dependency_names
    }
    report: dict[str, Any] = {
        "state_root": str(state_root()),
        "dependencies": dependencies,
        "profiles": [
            profile_status(profile, validate=False)
            for profile in OAuthProfile
        ],
        "live": None,
    }
    if live_profile is not None:
        with _client(live_profile) as client:
            report["live"] = {
                "profile": live_profile.value,
                "gmail_profile": client.get_profile(),
            }
    report["ready"] = all(dependencies.values()) and (
        live_profile is None or report["live"] is not None
    )
    _emit(report)
    if not report["ready"]:
        raise typer.Exit(code=1)


def main() -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level="WARNING",
        backtrace=False,
        diagnose=False,
    )
    try:
        app()
    except (
        GmailAuthError,
        GmailApiError,
        PlanCommitError,
        ValueError,
        OSError,
    ) as exc:
        error_code = (
            exc.code
            if isinstance(exc, GmailApiError)
            else type(exc).__name__
        )
        typer.echo(
            json.dumps(
                {
                    "status": "error",
                    "error_code": error_code,
                    "message": str(exc),
                },
                ensure_ascii=False,
            ),
            err=True,
        )
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    main()
