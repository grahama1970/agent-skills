#!/usr/bin/env python3
"""Operational one-shot notifications for ops-discord."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from discord_ops.keyword_matcher import KeywordMatch
from discord_ops.utils import (
    describe_webhook_url,
    get_bot_token,
    get_env_value,
    load_webhooks,
    webhook_sources,
)
from discord_ops.webhook_monitor import forward_to_webhook, get_feature_status

try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on optional runtime install
    HTTPX_AVAILABLE = False

__all__ = ["notify_webhook", "notify_discord_channel"]


TEXT_CHANNEL_TYPES = {0, 5, 15}


def _notification_match(title: str, content: str) -> KeywordMatch:
    return KeywordMatch(
        timestamp=datetime.now(timezone.utc).isoformat(),
        guild_id="ops-discord",
        guild_name="ops-discord",
        channel_id="notification",
        channel_name="ops-notifications",
        author="ops-discord",
        content=f"{title}\n\n{content}",
        matched_keywords=["ops-discord-notification"],
        message_url="https://discord.com/channels/ops-discord/notification/notification",
    )


def notify_webhook(
    *,
    webhook_name: str,
    title: str,
    content: str,
    dry_run: bool,
) -> dict[str, Any]:
    """Resolve and optionally send a one-shot notification."""
    webhooks = load_webhooks()
    sources = webhook_sources()
    features = get_feature_status()
    webhook_url = webhooks.get(webhook_name)
    receipt: dict[str, Any] = {
        "schema": "ops_discord.notification_receipt.v1",
        "status": "PENDING",
        "webhook": webhook_name,
        "source": sources.get(webhook_name),
        "dry_run": dry_run,
        "external_effects": not dry_run,
    }
    if not webhook_url:
        receipt["status"] = "NO_WEBHOOK"
        return receipt
    receipt["webhook_url"] = describe_webhook_url(webhook_url)
    if dry_run:
        receipt["status"] = "DRY_RUN"
        return receipt
    if not features["httpx"]:
        receipt["status"] = "HTTPX_UNAVAILABLE"
        return receipt

    success = asyncio.run(forward_to_webhook(webhook_url, _notification_match(title, content)))
    receipt["status"] = "SENT" if success else "SEND_FAILED"
    return receipt


def notify_discord_channel(
    *,
    channel_id: str | None,
    channel_name: str | None,
    title: str,
    content: str,
    dry_run: bool,
) -> dict[str, Any]:
    """Send one operational notification through the Discord bot API."""
    receipt: dict[str, Any] = {
        "schema": "ops_discord.notification_receipt.v1",
        "status": "PENDING",
        "transport": "discord_bot",
        "channel_id": channel_id,
        "channel_name": channel_name,
        "dry_run": dry_run,
        "external_effects": not dry_run,
    }
    token = get_bot_token()
    if not token:
        receipt["status"] = "NO_BOT_TOKEN"
        return receipt
    if not HTTPX_AVAILABLE:
        receipt["status"] = "HTTPX_UNAVAILABLE"
        return receipt
    resolved = _resolve_discord_channel_id(
        token=token,
        channel_id=channel_id,
        channel_name=channel_name,
    )
    receipt.update(resolved)
    if resolved.get("ok") is not True:
        receipt["status"] = str(resolved.get("status") or "CHANNEL_RESOLUTION_FAILED")
        return receipt
    resolved_channel_id = str(resolved["channel_id"])
    if dry_run:
        receipt["status"] = "DRY_RUN"
        receipt["ok"] = True
        return receipt

    payload = {"content": f"**{title}**\n\n{content}"[:2000]}
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                f"https://discord.com/api/v10/channels/{resolved_channel_id}/messages",
                headers={"Authorization": f"Bot {token}"},
                json=payload,
            )
    except httpx.HTTPError as exc:
        receipt.update({"status": "SEND_FAILED", "ok": False, "errors": [str(exc)]})
        return receipt
    receipt["http_status"] = response.status_code
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code in {200, 201} and isinstance(body, dict) and body.get("id"):
        receipt.update(
            {
                "status": "SENT",
                "ok": True,
                "message_id": str(body.get("id")),
                "discord_message_id": str(body.get("id")),
                "discord_channel_id": str(body.get("channel_id") or resolved_channel_id),
                "guild_id": str(body.get("guild_id") or resolved.get("guild_id") or ""),
                "message_url": _discord_message_url(
                    guild_id=str(body.get("guild_id") or resolved.get("guild_id") or ""),
                    channel_id=str(body.get("channel_id") or resolved_channel_id),
                    message_id=str(body.get("id")),
                ),
            }
        )
        return receipt
    receipt.update(
        {
            "status": "SEND_FAILED",
            "ok": False,
            "response_excerpt": response.text[:1000],
        }
    )
    return receipt


def _resolve_discord_channel_id(
    *,
    token: str,
    channel_id: str | None,
    channel_name: str | None,
) -> dict[str, Any]:
    if channel_id:
        return {"ok": True, "status": "CHANNEL_RESOLVED", "channel_id": channel_id}
    guild_id = get_env_value("DISCORD_SERVER_ID")
    if not guild_id:
        return {"ok": False, "status": "NO_DISCORD_SERVER_ID"}
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                f"https://discord.com/api/v10/guilds/{guild_id}/channels",
                headers={"Authorization": f"Bot {token}"},
            )
    except httpx.HTTPError as exc:
        return {"ok": False, "status": "CHANNEL_LIST_FAILED", "errors": [str(exc)]}
    if response.status_code != 200:
        return {
            "ok": False,
            "status": "CHANNEL_LIST_FAILED",
            "http_status": response.status_code,
            "response_excerpt": response.text[:1000],
        }
    try:
        channels = response.json()
    except ValueError:
        return {"ok": False, "status": "CHANNEL_LIST_INVALID_JSON"}
    if not isinstance(channels, list):
        return {"ok": False, "status": "CHANNEL_LIST_INVALID"}
    wanted = (channel_name or "horus").strip().lower()
    matches = [
        item
        for item in channels
        if isinstance(item, dict)
        and int(item.get("type", -1)) in TEXT_CHANNEL_TYPES
        and str(item.get("name") or "").lower() == wanted
    ]
    if len(matches) != 1:
        return {
            "ok": False,
            "status": "CHANNEL_NAME_NOT_UNIQUE" if matches else "CHANNEL_NOT_FOUND",
            "channel_name": channel_name or "horus",
            "match_count": len(matches),
            "available_channels": [
                {"id": str(item.get("id")), "name": str(item.get("name"))}
                for item in channels
                if isinstance(item, dict) and int(item.get("type", -1)) in TEXT_CHANNEL_TYPES
            ],
        }
    match = matches[0]
    return {
        "ok": True,
        "status": "CHANNEL_RESOLVED",
        "guild_id": str(guild_id),
        "channel_id": str(match.get("id")),
        "channel_name": str(match.get("name")),
    }


def _discord_message_url(*, guild_id: str, channel_id: str, message_id: str) -> str | None:
    if not guild_id or not channel_id or not message_id:
        return None
    return f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"
