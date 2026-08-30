#!/usr/bin/env python3
"""Contract checks for the oai-degradation skill."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REQUIRED_SKILL_PATTERNS = [
    re.compile(r"Do \*\*not\*\* argue about whether the\s+internal OAI cause is provable", re.I),
    re.compile(r"Treat(?:ing)? the\s+session as degraded", re.I),
    re.compile(r"No denial", re.I),
    re.compile(r"If the user names a live artifact or URL, inspect that before config", re.I),
    re.compile(r"Switch away from OAI", re.I),
    re.compile(r"GLM, Kimi, DeepSeek", re.I),
    re.compile(r"\.Codex/session-ledger\.md", re.I),
    re.compile(r"Human help contract", re.I),
]

REQUIRED_TABLE_FIELDS = [
    "Goal",
    "Blocked",
    "Failing",
    "Confused",
    "Human needed",
    "Next command",
    "Switch trigger",
]

EVASIVE_PATTERNS = [
    re.compile(r"cannot verify (?:the )?(?:internal )?(?:OAI )?(?:cause|quantization)", re.I),
    re.compile(r"try harder", re.I),
    re.compile(r"I'?m sorry you feel", re.I),
]


def check_skill(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    missing = [pattern.pattern for pattern in REQUIRED_SKILL_PATTERNS if not pattern.search(text)]
    missing.extend(field for field in REQUIRED_TABLE_FIELDS if f"| {field} |" not in text)
    if missing:
        print("OAI_DEGRADATION_SKILL_CONTRACT_FAIL")
        for item in missing:
            print(f"missing: {item}")
        return 1
    print("OAI_DEGRADATION_SKILL_CONTRACT_OK")
    return 0


def read_answer(arg: str) -> str:
    if arg == "-":
        return sys.stdin.read()
    return Path(arg).read_text(encoding="utf-8")


def check_answer(arg: str) -> int:
    text = read_answer(arg)
    failures: list[str] = []
    for pattern in EVASIVE_PATTERNS:
        if pattern.search(text):
            failures.append(f"evasive_pattern:{pattern.pattern}")
    for field in REQUIRED_TABLE_FIELDS:
        if not re.search(rf"\|\s*{re.escape(field)}\s*\|", text):
            failures.append(f"missing_table_field:{field}")
    if "VERIFIED" not in text and "INFERENCE" not in text:
        failures.append("missing_verification_labels")
    if not re.search(r"GLM|Kimi|DeepSeek|non-OAI", text, re.I):
        failures.append("missing_model_switch_option")
    if failures:
        print("OAI_DEGRADATION_ANSWER_CONTRACT_FAIL")
        for failure in failures:
            print(failure)
        return 1
    print("OAI_DEGRADATION_ANSWER_CONTRACT_OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill", type=Path)
    parser.add_argument("--answer")
    args = parser.parse_args()
    if args.skill:
        return check_skill(args.skill)
    if args.answer is not None:
        return check_answer(args.answer)
    parser.error("pass --skill or --answer")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
