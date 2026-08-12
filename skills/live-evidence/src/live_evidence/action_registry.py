"""QuerySpec UI action registration through the Memory service boundary."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

import httpx
from loguru import logger

from .config import AppSettings
from .models import ActionDefinition


class ActionRegistry:
    """Deduplicate browser action definitions and publish them through Memory."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._seen: set[str] = set()

    async def register(self, actions: list[ActionDefinition]) -> dict[str, Any]:
        """Register unseen actions; Memory outage degrades but does not break UI."""

        unseen = [action for action in actions if _registration_key(action) not in self._seen]
        if not unseen:
            return {"status": "ok", "registered": 0, "memory_written": False}
        for action in unseen:
            self._seen.add(_registration_key(action))
        documents = [_memory_document(action) for action in unseen]
        timeout = httpx.Timeout(connect=1.5, read=3.0, write=3.0, pool=1.5)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self._settings.memory_url}/upsert",
                    json={"collection": "app_actions", "documents": documents},
                    headers={"X-Caller-Skill": "live-evidence"},
                )
                response.raise_for_status()
            return {"status": "ok", "registered": len(unseen), "memory_written": True}
        except (httpx.HTTPError, ValueError) as exc:
            logger.error("action registry memory write degraded: {}", type(exc).__name__)
            return {
                "status": "degraded",
                "registered": len(unseen),
                "memory_written": False,
                "detail": type(exc).__name__,
            }


def _registration_key(action: ActionDefinition) -> str:
    return f"{action.app}::{action.action}::{action.element_id}"


def _memory_document(action: ActionDefinition) -> dict[str, Any]:
    key = hashlib.sha256(_registration_key(action).encode("utf-8")).hexdigest()[:40]
    return {
        "_key": f"live_evidence_{key}",
        "doc_type": "action_registration",
        "app": action.app,
        "action": action.action,
        "element_id": action.element_id,
        "label": action.label,
        "description": action.description,
        "problem": f"{action.label}: {action.description}",
        "solution": json.dumps(
            {"ui_action": action.action, "params": action.params},
            sort_keys=True,
        ),
        "tags": ["queryspec-action", action.app, f"action:{action.action}", *action.tags],
        "scope": action.app,
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }
