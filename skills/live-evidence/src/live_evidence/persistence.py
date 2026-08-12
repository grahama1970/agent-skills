"""Append-only local session journal.

The journal stores validated transcript events, evidence cards, and operator
commands as JSONL. It never receives or writes raw audio bytes.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import BaseModel


class SessionJournal:
    """Serialize runtime records under one session-bound directory."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._lock = asyncio.Lock()

    async def append(self, session_id: str, kind: str, payload: BaseModel | dict[str, Any]) -> Path:
        """Append one validated record and return the journal path."""

        if not session_id or any(char in session_id for char in {"/", "\\", ".."}):
            raise ValueError("invalid session_id")
        session_dir = self._data_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        target = session_dir / "session.jsonl"
        record_payload = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
        record = {"kind": kind, "payload": record_payload}
        encoded = json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n"
        async with self._lock:
            await asyncio.to_thread(_append_text, target, encoded)
        logger.debug("journal append kind={} path={}", kind, target)
        return target


def _append_text(path: Path, text: str) -> None:
    """Perform the blocking append in a worker thread."""

    with path.open("a", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
