"""Hash-bound read-only artifact authority for journaled Embry turns."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from embry_voice_control.event_journal import session_snapshot


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def resolve_audio_artifact(
    journal_path: Path,
    *,
    session_id: str,
    turn_id: str,
    audio_sha256: str,
) -> dict[str, Any]:
    """Resolve one artifact only through its matching accepted render event."""
    events = [
        event for event in session_snapshot(journal_path, session_id)["events"]
        if event["turn_id"] == turn_id and event["type"] == "chatterbox.voice_render.completed"
    ]
    matches = [event for event in events if event["payload"].get("audio", {}).get("sha256") == audio_sha256]
    if len(matches) != 1:
        raise LookupError("audio_artifact_not_found")
    audio = matches[0]["payload"]["audio"]
    path = Path(audio["path"])
    if not path.is_file():
        raise RuntimeError("audio_artifact_missing")
    if path.stat().st_size != int(audio["bytes"]):
        raise RuntimeError("audio_artifact_size_mismatch")
    if _digest(path) != audio_sha256:
        raise RuntimeError("audio_artifact_hash_mismatch")
    return {**audio, "path": path, "render_event_id": matches[0]["event_id"]}
