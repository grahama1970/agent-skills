"""Turn formatting helpers."""
from __future__ import annotations

import json
from typing import Sequence, Tuple

from ccopy.errors import CursorCopyError
from ccopy.models import ROLE_ASSISTANT, ROLE_USER, LastTurn, Message

def find_last_complete_turn(messages: Sequence[Message]) -> Tuple[Message, Message]:
    for i in range(len(messages) - 1, -1, -1):
        assistant = messages[i]
        if assistant.role != ROLE_ASSISTANT or not assistant.text.strip():
            continue
        for j in range(i - 1, -1, -1):
            user = messages[j]
            if user.role == ROLE_USER and user.text.strip():
                return user, assistant
    raise CursorCopyError("no complete user/assistant turn found in the selected conversation")


def format_turn(turn: LastTurn, fmt: str, include_meta: bool = False) -> str:
    meta = {
        "composer_id": turn.composer_id,
        "conversation_name": turn.conversation_name,
        "workspace_id": turn.workspace_id,
        "workspace_path": turn.workspace_path,
        "user_bubble_id": turn.user.bubble_id,
        "assistant_bubble_id": turn.assistant.bubble_id,
    }
    if fmt == "json":
        if include_meta:
            meta = {
                **meta,
                "source": turn.source,
                "transcript_path": turn.transcript_path,
            }
        payload = {
            **({"meta": meta} if include_meta else {}),
            "messages": [
                {"role": "user", "content": turn.user.text},
                {"role": "assistant", "content": turn.assistant.text},
            ],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)
    if fmt == "xml":
        # Minimal XML-ish wrapper for agent prompts. Do not escape aggressively because
        # this is intended as clipboard text, not an XML parser contract.
        meta_text = ""
        if include_meta:
            meta_text = "\n" + "\n".join(f"  <{k}>{v or ''}</{k}>" for k, v in meta.items()) + "\n"
        return f"<cursor_copy>{meta_text}\n<user>\n{turn.user.text}\n</user>\n\n<assistant>\n{turn.assistant.text}\n</assistant>\n</cursor_copy>".strip() + "\n"
    if fmt == "plain":
        meta_text = ""
        if include_meta:
            meta_text = (
                f"Conversation: {turn.conversation_name or '(untitled)'}\n"
                f"Composer ID: {turn.composer_id}\n"
                f"Workspace: {turn.workspace_path or turn.workspace_id or '(unknown)'}\n\n"
            )
        return f"{meta_text}USER:\n{turn.user.text}\n\nASSISTANT:\n{turn.assistant.text}\n"
    # markdown default
    meta_text = ""
    if include_meta:
        meta_text = (
            f"> Conversation: {turn.conversation_name or '(untitled)'}  \n"
            f"> Composer ID: `{turn.composer_id}`  \n"
            f"> Workspace: `{turn.workspace_path or turn.workspace_id or '(unknown)'}`\n\n"
        )
    return f"{meta_text}## User\n\n{turn.user.text}\n\n## Assistant\n\n{turn.assistant.text}\n"
