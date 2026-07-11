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
    render_event_id: str | None = None,
    artifact_id: str | None = None,
    audio_bytes: int | None = None,
    tau_turn_plan_sha256: str | None = None,
) -> dict[str, Any]:
    """Resolve one artifact only through its matching accepted render event."""
    events = [
        event for event in session_snapshot(journal_path, session_id)["events"]
        if event["turn_id"] == turn_id and event["type"] == "chatterbox.voice_render.completed"
    ]
    matches = [event for event in events if event["payload"].get("audio", {}).get("sha256") == audio_sha256]
    if render_event_id is not None:
        matches = [event for event in matches if event["event_id"] == render_event_id]
    if len(matches) != 1:
        raise LookupError("audio_artifact_not_found")
    audio = matches[0]["payload"]["audio"]
    if artifact_id is not None and audio.get("artifact_id") != artifact_id:
        raise RuntimeError("audio_artifact_id_mismatch")
    if audio_bytes is not None and int(audio.get("bytes", -1)) != audio_bytes:
        raise RuntimeError("audio_artifact_declared_size_mismatch")
    plan_hash = matches[0]["artifact_hashes"].get("tau_turn_plan_sha256")
    if tau_turn_plan_sha256 is not None and plan_hash != tau_turn_plan_sha256:
        raise RuntimeError("audio_artifact_tau_plan_hash_mismatch")
    path = Path(audio["path"])
    if not path.is_file():
        raise RuntimeError("audio_artifact_missing")
    if path.stat().st_size != int(audio["bytes"]):
        raise RuntimeError("audio_artifact_size_mismatch")
    if _digest(path) != audio_sha256:
        raise RuntimeError("audio_artifact_hash_mismatch")
    return {**audio, "path": path, "render_event": matches[0], "render_event_id": matches[0]["event_id"]}
