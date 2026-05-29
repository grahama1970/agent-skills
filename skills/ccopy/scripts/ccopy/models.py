"""ccopy data models and constants."""

from __future__ import annotations

import dataclasses
import pathlib
from typing import Optional

ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
USER_TYPE = 1
ASSISTANT_TYPE = 2
SOURCE_SQLITE = "sqlite"
SOURCE_TRANSCRIPT = "agent-transcript"


@dataclasses.dataclass(frozen=True)
class Workspace:
    workspace_id: str
    path: pathlib.Path
    db_path: pathlib.Path
    uri: Optional[str] = None
    fs_path: Optional[str] = None


@dataclasses.dataclass(frozen=True)
class ConversationHeader:
    composer_id: str
    name: str = ""
    workspace_id: Optional[str] = None
    workspace_uri: Optional[str] = None
    workspace_path: Optional[str] = None
    created_at: int = 0
    last_updated_at: int = 0
    unified_mode: str = ""
    source: str = ""


@dataclasses.dataclass(frozen=True)
class Message:
    role: str
    text: str
    bubble_id: Optional[str] = None
    created_at: int = 0


@dataclasses.dataclass(frozen=True)
class LastTurn:
    composer_id: str
    conversation_name: str
    workspace_id: Optional[str]
    workspace_path: Optional[str]
    user: Message
    assistant: Message
    source: str = SOURCE_SQLITE
    transcript_path: Optional[str] = None
