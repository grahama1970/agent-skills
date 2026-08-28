#!/usr/bin/env python3
"""Operational one-shot notifications for ops-discord."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from discord_ops.keyword_matcher import KeywordMatch
from discord_ops.utils import describe_webhook_url, load_webhooks, webhook_sources
from discord_ops.webhook_monitor import forward_to_webhook, get_feature_status

__all__ = ["notify_webhook"]


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
