#!/usr/bin/env python3
"""Append one turn to a run's conversation, durably (#1210).

The chat pane reads `conversation.jsonl` and nothing has ever written it. So a
discussion about a dream lives exactly as long as the browser tab: it cannot
survive a reload, cannot be reviewed later, and cannot feed tomorrow's recall.
That is the open joint in the loop -- the journal reaches a person, and nothing
the person says gets back.

Append-only on purpose. A conversation is a record of what was said, and
rewriting it later would make the record worth less than not keeping one.
Every turn is appended with `O_APPEND` under an exclusive lock, so two writers
(a human in one terminal, an agent in another) cannot interleave a half-line.

An `embry` turn carries more than a human turn, and the asymmetry is deliberate.
When she says something it must be bound the same way her journal is: a
requested delivery tone, and a reference to the audio that was actually
rendered. Her journal is hash-bound to its spoken text; a claim she said
something, with no audio and no tone, would be a weaker artifact than the thing
it is commenting on.

What this does NOT do is write the conversation back into memory. That needs a
memory service where a stored document is retrievable, which today it is not
(graph-memory-operator#99). The file is the durable half; the return arc into
memory stays open and is not pretended otherwise.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]

#: Who can speak. `agent` is the project agent reading the journal alongside the
#: human; `embry` is the persona herself; `horus` is the second persona, voiced
#: and bound exactly as she is (2026-08-20: his audio is first-class, not a
#: sidecar artifact).
ROLES = ("human", "agent", "embry", "horus")

#: Roles whose turns must carry a requested tone and rendered audio.
VOICED_ROLES = ("embry", "horus")


def utc_now() -> str:
    return datetime.now().astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def rel(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path)


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def build_turn(args: argparse.Namespace, run_dir: Path) -> tuple[dict[str, Any], list[str]]:
    """The turn to append, plus any gate failures that should block the write."""
    failed: list[str] = []
    text = (args.text or "").strip()
    if not text:
        failed.append("empty_text")

    turn: dict[str, Any] = {
        "schema": "persona_dream.conversation_turn.v1",
        "role": args.role,
        "text": text,
        "created_at": args.created_at or utc_now(),
    }

    # Bind the turn to the entry it is about, so a conversation can never drift
    # onto a different run's journal without it being visible in the record.
    spoken = run_dir / "journal_spoken.txt"
    if spoken.is_file():
        turn["journal_spoken_sha256"] = sha_file(spoken)

    if args.role in VOICED_ROLES:
        # A voiced persona turn must carry the same binding the journal does.
        if not args.tone:
            failed.append(f"{args.role}_turn_requires_tone")
        if not args.audio:
            failed.append(f"{args.role}_turn_requires_audio")
        turn["requested_delivery_tone"] = args.tone
        turn["tone_boundary"] = (
            "requested of the renderer, not achieved in the audio; the delivery "
            "tone was measured inaudible on this engine"
        )
        if args.audio:
            audio = Path(args.audio)
            if not audio.is_absolute():
                audio = run_dir / audio
            if not audio.is_file():
                failed.append(f"audio_not_found:{audio}")
            else:
                turn["audio"] = audio.name if audio.parent == run_dir else str(audio)
                turn["audio_sha256"] = sha_file(audio)
    elif args.tone or args.audio:
        # A human/agent turn does not have a delivery tone. Silently dropping
        # the flag would make the record claim less than the caller thinks it
        # does. Keep the historical embry_only token for the retained #1210
        # contract while the allowed voiced-role set now includes Horus too.
        failed.append(f"embry_only_delivery_tone_rejected_for_role:{args.role}")

    return turn, failed


def append_turn(path: Path, turn: dict[str, Any]) -> int:
    """Append one JSON line under an exclusive lock. Returns the new line count."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(turn, sort_keys=True) + "\n"
    with path.open("a", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            fh.write(line)
            fh.flush()
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    return sum(1 for _ in path.open(encoding="utf-8"))


def run(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir).resolve()
    path = run_dir / "conversation.jsonl"
    turn, failed = build_turn(args, run_dir)

    if failed:
        return {
            "schema": "persona_dream.conversation_append_receipt.v1",
            "created_at": utc_now(), "status": "BLOCKED_CONVERSATION_APPEND",
            "mocked": False, "live": False, "run_dir": rel(run_dir),
            "conversation": rel(path), "turn": turn, "failed_gates": failed,
        }

    before = sum(1 for _ in path.open(encoding="utf-8")) if path.is_file() else 0
    after = append_turn(path, turn)

    # Read back. The write is not the evidence; the line being there is.
    last = None
    for raw in path.open(encoding="utf-8"):
        raw = raw.strip()
        if raw:
            last = raw
    read_back = False
    try:
        read_back = json.loads(last) == turn if last else False
    except json.JSONDecodeError:
        read_back = False
    if not read_back:
        failed.append("appended_line_did_not_read_back")

    return {
        "schema": "persona_dream.conversation_append_receipt.v1",
        "created_at": utc_now(),
        "status": "PASS_CONVERSATION_APPENDED" if not failed else "BLOCKED_CONVERSATION_APPEND",
        "mocked": False,
        "live": True,
        "run_dir": rel(run_dir),
        "conversation": rel(path),
        "conversation_sha256": sha_file(path),
        "turns_before": before,
        "turns_after": after,
        "appended": turn,
        "read_back": read_back,
        "append_only": True,
        "claims": {
            "proves": [
                "the turn is durably recorded and survives the browser",
                "the turn is bound by hash to the journal it discusses",
            ] if not failed else [],
            "does_not_prove": [
                "that the conversation reaches memory or influences a later dream; "
                "that return arc is blocked on graph-memory-operator#99",
                "for an embry turn, that the requested tone is audible",
            ],
        },
        "failed_gates": failed,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--role", choices=ROLES, required=True)
    ap.add_argument("--text", required=True)
    ap.add_argument("--tone", help="voiced turns (embry/horus) only: the delivery tone requested")
    ap.add_argument("--audio", help="voiced turns (embry/horus) only: rendered audio for this turn")
    ap.add_argument("--created-at", help="override the timestamp (tests, backfill)")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    r = run(args)
    if args.out:
        Path(args.out).write_text(json.dumps(r, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(r, indent=2, sort_keys=True) if args.json else
          f"{r['status']}  {r.get('conversation')}  turns={r.get('turns_after')}  "
          f"read_back={r.get('read_back')}" + (f"  failed={r['failed_gates']}" if r["failed_gates"] else ""))
    return 0 if r["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
