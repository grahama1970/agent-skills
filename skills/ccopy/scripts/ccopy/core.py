"""Backend selection and last-turn orchestration."""
from __future__ import annotations

import pathlib
from typing import Optional

from ccopy.models import SOURCE_SQLITE, SOURCE_TRANSCRIPT, LastTurn
from ccopy.sqlite_backend import build_last_turn_sqlite, sqlite_has_bubble_messages
from ccopy.transcript import build_last_turn_from_transcript

def build_last_turn(
    user_dir: pathlib.Path,
    workspace_selector: Optional[str],
    composer_id: Optional[str],
    latest_global: bool,
    cwd: pathlib.Path,
    source: str = "auto",
) -> LastTurn:
    if source not in ("auto", SOURCE_SQLITE, SOURCE_TRANSCRIPT):
        raise CursorCopyError(f"unsupported --source value: {source}")

    if source == SOURCE_TRANSCRIPT:
        return build_last_turn_from_transcript(
            cwd=cwd,
            workspace_selector=workspace_selector,
            session_id=composer_id,
            latest_global=latest_global,
        )
    if source == SOURCE_SQLITE:
        return build_last_turn_sqlite(
            user_dir=user_dir,
            workspace_selector=workspace_selector,
            composer_id=composer_id,
            latest_global=latest_global,
            cwd=cwd,
        )

    if sqlite_has_bubble_messages(user_dir):
        try:
            return build_last_turn_sqlite(
                user_dir=user_dir,
                workspace_selector=workspace_selector,
                composer_id=composer_id,
                latest_global=latest_global,
                cwd=cwd,
            )
        except CursorCopyError:
            pass
    return build_last_turn_from_transcript(
        cwd=cwd,
        workspace_selector=workspace_selector,
        session_id=composer_id,
        latest_global=latest_global,
    )
