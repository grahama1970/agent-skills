#!/usr/bin/env python3
"""PreToolUse hook: block browser-delivery commands until the contracts are Read.

This is the enforcement layer for Rule 2. Skill text is advisory — an agent
under pressure skims it (proven 2026-08-18, five failed submits). A hook runs
in the harness, outside the model, so it cannot be rationalized away.

Wiring (project or user settings.json):

    {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command",
      "command": "python3 <abs-path>/enforce_read_gate.py"}]}]}}

Contract: receives the hook payload on stdin (tool_input.command,
transcript_path). If the command is a browser-delivery command and the session
transcript does NOT contain a full Read of every contract on the reading list,
exit 2 with the missing files named — the harness blocks the call and shows
the agent exactly what to Read. Anything else: exit 0, no interference.

A full Read means: Read tool_use entries for that path whose offset/limit
windows jointly cover the file's current line count (a single no-offset Read
covers min(2000, lines); files longer than 2000 lines need offset reads too).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SKILLS_ROOT = Path(__file__).resolve().parents[2]

# Effect families that constitute a delivery attempt (hardening: browser
# submits were the only governed family; pane sends and pushes are external
# effects with the same false-delivery failure mode).
DELIVERY = re.compile(
    r"(webgpt|kimi|gemini|grok|deepseek|claude)\.submit"
    r"|tau-dag .*--execute"
    r"|run\.sh (webgpt|webkimi|webgemini|webgrok|webclaude) "
    r"|run\.sh compete .*--execute"
    r"|\bherdr (send|pane run)\b"
    r"|\bgit push\b"
)

READ_LIST = [
    SKILLS_ROOT / "best-practices-delivery-proof" / "SKILL.md",
    SKILLS_ROOT / "ask" / "SKILL.md",
    SKILLS_ROOT / "surf" / "SKILL.md",
]
DEFAULT_READ_LIMIT = 2000


def covered(transcript_path: str, target: Path) -> bool:
    """Whether the transcript's Read calls jointly cover the whole file."""
    try:
        total = target.read_text(errors="replace").count("\n") + 1
    except OSError:
        return True  # a missing contract is verify_contract's problem, not a block
    windows: list[tuple[int, int]] = []
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if '"Read"' not in line or target.name not in line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                content = entry.get("message", {}).get("content")
                for block in content if isinstance(content, list) else []:
                    if block.get("type") != "tool_use" or block.get("name") != "Read":
                        continue
                    inp = block.get("input", {})
                    if inp.get("file_path") != str(target):
                        continue
                    start = int(inp.get("offset", 1) or 1)
                    limit = int(inp.get("limit", DEFAULT_READ_LIMIT) or DEFAULT_READ_LIMIT)
                    windows.append((start, start + limit - 1))
    except OSError:
        return False
    if not windows:
        return False
    windows.sort()
    reach = 0
    for start, end in windows:
        if start > reach + 1:
            break
        reach = max(reach, end)
    return reach >= total


ATTEST_PATH = SKILLS_ROOT / "best-practices-delivery-proof" / "fixtures" / ".read-attestation.json"


def attestation_current() -> bool:
    """A digest-bound attestation covers the reading list while digests match.

    Durable across session resume/compaction (Rule 2 amendment); void the
    moment any attested contract's content changes.
    """
    import hashlib

    try:
        data = json.loads(ATTEST_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    attested = {e.get("path"): e.get("sha256") for e in data.get("contracts", [])}
    for target in READ_LIST:
        digest = attested.get(str(target))
        if not digest:
            return False
        try:
            current = hashlib.sha256(target.read_bytes()).hexdigest()
        except OSError:
            return False
        if current != digest:
            return False
    return True


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    command = (payload.get("tool_input") or {}).get("command") or ""
    # A read-only leading program cannot deliver anything; mentioning a submit
    # command inside grep/echo text is a harmless near-match, not an effect.
    first = command.strip().split()[0] if command.strip() else ""
    if first.rsplit("/", 1)[-1] in {"grep", "rg", "cat", "echo", "printf", "head", "tail", "sed", "awk", "less", "man", "wc"}:
        return 0
    if not DELIVERY.search(command):
        return 0
    if attestation_current():
        return 0
    transcript = payload.get("transcript_path") or ""
    missing = [str(p) for p in READ_LIST if not covered(transcript, p)]
    if not missing:
        return 0
    print(
        "delivery-proof read gate: this is a browser delivery command, and the "
        "session has not fully Read the owning contracts. Read each of these "
        "end to end (offset reads for files over 2000 lines), then rerun:\n  "
        + "\n  ".join(missing)
        + "\nList with line counts: python3 skills/best-practices-delivery-proof/"
        "scripts/verify_contract.py read-list\n"
        "After reading, persist the proof: python3 skills/best-practices-delivery-proof/"
        "scripts/verify_contract.py attest",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
