#!/usr/bin/env python3
"""Guard the Ask/Tau/watchdog JSON-stream monitoring contract."""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]

REQUIRED = {
    "skills/ask/SKILL.md": [
        "Monitor Tau JSON Streams",
        "events.jsonl",
        "dag-progress.json",
        "terminal `PASS`, `FAIL`, `BLOCKED`, or `NEEDS_ATTENTION`",
        "`--no-poll` is a compatibility flag only",
    ],
    "skills/ask/src/ask/tau_dag_cli.py": [
        "ask.tau_stream_monitoring_policy.v1",
        "effective_poll = requested_poll or execute",
        "--no-poll is ignored with --execute",
    ],
    "skills/tau/SKILL.md": [
        "JSON streaming is part of the runtime contract",
        "events.jsonl",
        "dag-progress.json",
        "Project agents supervising Tau must treat the JSON stream as the source of truth",
    ],
    "skills/project-watchdog/SKILL.md": [
        "The watchdog must still monitor the Tau run continuously",
        "events.jsonl",
        "dag-progress.json",
        "tau-stream-monitor.json",
    ],
}


def _contents(root: Path) -> dict[str, str]:
    return {rel: (root / rel).read_text(encoding="utf-8") for rel in REQUIRED}


def check(contents: dict[str, str]) -> list[str]:
    problems: list[str] = []
    for rel, needles in REQUIRED.items():
        text = contents.get(rel, "")
        normalized = " ".join(text.split())
        for needle in needles:
            if needle not in text and " ".join(needle.split()) not in normalized:
                problems.append(f"{rel}: missing {needle!r}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--adversarial",
        choices=["missing-ask-monitoring"],
        default="",
        help="Prove the checker catches a known missing contract phrase.",
    )
    args = parser.parse_args()

    contents = _contents(ROOT)
    if args.adversarial == "missing-ask-monitoring":
        contents["skills/ask/SKILL.md"] = contents["skills/ask/SKILL.md"].replace(
            "Monitor Tau JSON Streams", "Monitor Tau Output"
        )
        problems = check(contents)
        if any("skills/ask/SKILL.md" in p and "Monitor Tau JSON Streams" in p for p in problems):
            print("ADVERSARIAL_CAUGHT missing-ask-monitoring")
            return 0
        print("ADVERSARIAL_NOT_CAUGHT", problems)
        return 1

    problems = check(contents)
    if problems:
        print("JSON_STREAM_CONTRACT_FAILED")
        for problem in problems:
            print(problem)
        return 1
    print("JSON_STREAM_CONTRACT_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
