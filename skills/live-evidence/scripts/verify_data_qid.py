#!/usr/bin/env python3
"""Verify write-time instrumentation on application-level React controls.

The scanner parses the bounded TSX opening-tag grammar without treating handler
bodies or arrow syntax as tag terminators. Reusable shadcn primitives are
excluded because their callers own stable action identity.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


INTERACTIVE_TAGS = {"Button", "Input", "button", "input", "select", "a"}
REQUIRED_ATTRIBUTES = {"data-qid", "data-qs-action", "title"}


@dataclass(frozen=True, slots=True)
class OpeningTag:
    """One parsed JSX opening tag."""

    name: str
    text: str
    line: int


def opening_tags(text: str):
    """Yield opening tags while respecting quotes and JSX brace depth."""

    index = 0
    line = 1
    while index < len(text):
        if text[index] != "<" or index + 1 >= len(text) or text[index + 1] in {"/", ">", "!"}:
            if text[index] == "\n":
                line += 1
            index += 1
            continue
        start = index
        start_line = line
        index += 1
        name_chars: list[str] = []
        while index < len(text) and (text[index].isalnum() or text[index] in {"_", "."}):
            name_chars.append(text[index])
            index += 1
        name = "".join(name_chars)
        if not name:
            continue
        quote: str | None = None
        brace_depth = 0
        while index < len(text):
            char = text[index]
            if char == "\n":
                line += 1
            if quote:
                if char == quote and text[index - 1] != "\\":
                    quote = None
            elif char in {"\"", "'", "`"}:
                quote = char
            elif char == "{":
                brace_depth += 1
            elif char == "}" and brace_depth > 0:
                brace_depth -= 1
            elif char == ">" and brace_depth == 0:
                index += 1
                yield OpeningTag(name=name, text=text[start:index], line=start_line)
                break
            index += 1
        else:
            return


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "ui/src").resolve()
    violations: list[str] = []
    for path in sorted(root.rglob("*.tsx")):
        if path.parts[-3:-1] == ("components", "ui"):
            continue
        text = path.read_text(encoding="utf-8")
        controls = [tag for tag in opening_tags(text) if tag.name in INTERACTIVE_TAGS]
        if controls and "useRegisterAction(" not in text:
            violations.append(f"{path.relative_to(root)}: controls exist without useRegisterAction")
        for tag in controls:
            missing = sorted(attribute for attribute in REQUIRED_ATTRIBUTES if attribute not in tag.text)
            if missing:
                violations.append(
                    f"{path.relative_to(root)}:{tag.line} <{tag.name}> missing {', '.join(missing)}"
                )
    if violations:
        print("React action instrumentation violations:", file=sys.stderr)
        for violation in violations:
            print(f"  {violation}", file=sys.stderr)
        return 1
    print("data-qid / QuerySpec instrumentation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
