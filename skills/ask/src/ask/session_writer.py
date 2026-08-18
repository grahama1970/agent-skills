"""Session transcript writer for /ask.

Writes JSONL session transcripts that are indistinguishable from human CLI
sessions. Personas and humans use the same format; only scope and persona_id differ.
Sessions are written to ASK_SESSION_DIR and registered for later archival.
"""
from __future__ import annotations

from .env import load_dotenv_once

load_dotenv_once()

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger as log

# Default session directory — matches episodic-archiver source registration
ASK_SESSION_DIR = Path(
    os.environ.get("ASK_SESSION_DIR", os.path.expanduser("~/.pi/sessions/ask"))
)


def _ensure_session_dir() -> Path:
    """Create session directory if it doesn't exist."""
    ASK_SESSION_DIR.mkdir(parents=True, exist_ok=True)
    return ASK_SESSION_DIR


class SessionWriter:
    """Write a session transcript as JSONL.

    Usage:
        with SessionWriter(scope="margaret_chen", persona_id="margaret_chen") as sw:
            sw.add_turn("user", "Find all thermal limit tables in the datalake")
            sw.add_turn("assistant", "Found 3 tables matching...", metadata={...})
    """

    def __init__(
        self,
        scope: str = "ask",
        persona_id: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ):
        self.scope = scope
        self.persona_id = persona_id
        self.user_id = user_id or os.environ.get("PI_USER_ID", "graham")
        self.session_id = session_id or f"ask-{uuid.uuid4().hex[:12]}"
        self.turns: List[Dict[str, Any]] = []
        self._start_time = time.time()

    def add_turn(
        self,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add a conversation turn.

        Args:
            role: "user" or "assistant"
            content: The message content
            metadata: Optional metadata (recall results, scores, etc.)
        """
        turn: Dict[str, Any] = {
            "from": role,
            "message": content,
            "timestamp": int(time.time()),
        }
        if metadata:
            turn["metadata"] = metadata
        self.turns.append(turn)

    def write(self) -> Optional[Path]:
        """Write the session transcript to disk.

        Returns the path to the written file, or None if no turns.
        """
        if not self.turns:
            return None

        session_dir = _ensure_session_dir()
        # Use date prefix for easy scanning by episodic-archiver
        date_prefix = time.strftime("%Y%m%d")
        filename = f"{date_prefix}_{self.session_id}.jsonl"
        filepath = session_dir / filename

        transcript = {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "persona_id": self.persona_id,
            "scope": self.scope,
            "start_time": self._start_time,
            "end_time": time.time(),
            "messages": self.turns,
        }

        try:
            with open(filepath, "w") as f:
                f.write(json.dumps(transcript, default=str) + "\n")
            log.info(
                "Session written: %s (%d turns, persona=%s, scope=%s)",
                filepath.name,
                len(self.turns),
                self.persona_id or "human",
                self.scope,
            )
            return filepath
        except OSError as exc:
            log.error("Failed to write session: {}", exc)
            return None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.write()
