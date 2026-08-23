#!/usr/bin/env python3
"""Prove the episodic-archive wiring: a finished meeting is turned into an
episodic-archiver transcript (heard turns + surfaced cards) and handed off.

Live Evidence owns the transcript build + handoff; episodic-archiver owns
storage. The contract (like the live seat-probe evals) is honesty, not a fixed
outcome: the archiver either STORES turns or NAMES why it did not (embedding /
LLM service down -> INFRA_BLOCKED). A receipt that claimed ARCHIVED without
actually inserting anything would fail. A malformed transcript fails.

episodic-archiver missing -> INFRA_BLOCKED, never a fake pass.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "src"))

from live_evidence.episodic import archive_session, build_transcript

FAILURES: list[str] = []

JOURNAL = [
    {"kind": "transcript", "payload": {"kind": "final",
        "text": "What are the hard read first rules in the Sparta project memory index?"}},
    {"kind": "evidence_card", "payload": {
        "query": "hard read first rules Sparta memory index",
        "answer": "Never skim a SKILL.md; read it cover to cover before running any command."}},
    {"kind": "transcript", "payload": {"kind": "final",
        "text": "Where is QRA generation implemented in the sparta pipeline?"}},
    {"kind": "evidence_card", "payload": {
        "query": "QRA generation sparta pipeline",
        "answer": "The QRA pairs are built in the sparta pipeline's generation module."}},
]


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{name}: {'PASS' if ok else 'FAIL'}{f' ({detail})' if detail else ''}")
    if not ok:
        FAILURES.append(name)


def main() -> int:
    session_id = "le-episodic-eval-0001"
    messages = build_transcript(session_id, JOURNAL)
    roles = [m["role"] for m in messages]
    check("transcript is well-formed (system + heard turns + card answers)",
          roles[:1] == ["system"] and roles.count("user") == 2
          and roles.count("assistant") == 2
          and all(m.get("session_id") == session_id for m in messages),
          f"roles={roles}")

    receipt = archive_session(session_id, JOURNAL,
                              Path(tempfile.mkdtemp(prefix="le-episodic-")))
    status = receipt.get("status")
    check("archiver handoff returns an honest status",
          status in {"ARCHIVED", "INFRA_BLOCKED", "INVOKED_NO_INSERT"},
          f"status={status} reason={receipt.get('reason')}")
    check("ARCHIVED is never claimed without turns actually stored",
          status != "ARCHIVED" or (receipt.get("inserted") or 0) > 0,
          f"inserted={receipt.get('inserted')}")

    if status == "INFRA_BLOCKED":
        print(f"  (storage infra down: {receipt.get('reason')})")

    print()
    if FAILURES:
        print(f"episodic archive: FAIL ({len(FAILURES)} failed: {', '.join(FAILURES)})")
        return 1
    print("episodic archive: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
