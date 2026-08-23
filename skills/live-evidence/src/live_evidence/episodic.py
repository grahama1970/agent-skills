"""Archive a finished meeting into episodic memory for later recall.

Live Evidence owns building a transcript from the session journal (the turns
heard and the cards surfaced) and handing it to the episodic-archiver skill;
episodic-archiver owns embedding, categorizing, and storing it to ArangoDB.
The handoff is deterministic and testable here; actual storage depends on the
embedding + LLM services being up, which the receipt reports honestly (a run
that stored nothing is not called archived).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


def build_transcript(session_id: str, journal_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Turn the session journal into an episodic-archiver message list: heard
    turns become user messages, surfaced cards become assistant messages. The
    first message carries the session id the archiver keys on."""

    messages: list[dict[str, Any]] = [
        {"session_id": session_id, "role": "system",
         "content": "Live Evidence meeting session"}
    ]
    for row in journal_rows:
        kind = row.get("kind")
        payload = row.get("payload") or {}
        if kind == "transcript" and payload.get("kind") == "final":
            text = str(payload.get("text") or "").strip()
            if text:
                messages.append({"session_id": session_id, "role": "user", "content": text})
        elif kind == "evidence_card":
            answer = str(payload.get("answer") or "").strip()
            query = str(payload.get("query") or "").strip()
            if answer:
                messages.append({"session_id": session_id, "role": "assistant",
                                 "content": f"[card for: {query[:120]}] {answer}"})
    return messages


def archive_session(session_id: str, journal_rows: list[dict[str, Any]], out_dir: Path,
                    *, runner: Path | None = None) -> dict[str, Any]:
    """Build the transcript and hand it to episodic-archiver. Returns a receipt
    with the message count, the archiver summary, and a status. Storage failures
    (embedding/LLM services down) are reported as infra, never as success."""

    messages = build_transcript(session_id, journal_rows)
    receipt: dict[str, Any] = {"schema": "live_evidence.episodic_archive.v1",
                               "session_id": session_id, "messages": len(messages)}
    if len(messages) < 2:
        receipt["status"] = "NOTHING_TO_ARCHIVE"
        return receipt
    runner = runner or (Path(__file__).resolve().parents[3] / "episodic-archiver" / "run.sh")
    if not runner.is_file():
        receipt["status"] = "INFRA_BLOCKED"
        receipt["reason"] = "episodic-archiver not installed"
        return receipt
    out_dir.mkdir(parents=True, exist_ok=True)
    transcript = out_dir / "transcript.json"
    transcript.write_text(json.dumps(messages), encoding="utf-8")
    try:
        proc = subprocess.run([str(runner), "archive", str(transcript)],
                              capture_output=True, text=True, timeout=300)
    except Exception as exc:  # noqa: BLE001
        receipt["status"] = "INFRA_BLOCKED"
        receipt["reason"] = f"{type(exc).__name__}: {exc}"
        return receipt
    out = (proc.stdout or "") + (proc.stderr or "")
    inserted = _parse_inserted(out)
    receipt["invoked"] = proc.returncode == 0
    receipt["inserted"] = inserted
    if inserted and inserted > 0:
        receipt["status"] = "ARCHIVED"
    elif "Connection refused" in out or "HTTP 401" in out or "embedding" in out.lower():
        # The handoff was correct; the storage backend (embedding/LLM) is down.
        receipt["status"] = "INFRA_BLOCKED"
        receipt["reason"] = "embedding/LLM service unavailable"
    else:
        receipt["status"] = "INVOKED_NO_INSERT"
    return receipt


def _parse_inserted(output: str) -> int | None:
    import re

    match = re.search(r"inserted=(\d+)", output)
    return int(match.group(1)) if match else None
