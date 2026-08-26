#!/usr/bin/env python3
"""Verify best-practices-react write-time attributes in the eval console.

Every interactive element in ui/src must be resolvable by an agent/CDP: raw
<a>/<button>/<select>/<input>/<textarea> tags carry data-qid, data-qs-action,
and title; the ActionButton wrapper (which applies those attributes + calls
useRegisterAction from required props, like the site's ButtonLink) must be
called with qid, qsAction, and title. Exit 1 = not shippable.

Skips: the shadcn library primitives under components/ui/ (generic components;
the call sites carry the attributes) and any tag that spreads {...props} (it
receives the attributes from a props type that requires them).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "src"
RAW_TAG_RE = re.compile(r"<(a|button|select|input|textarea)\b[^>]*?/?>", re.DOTALL)
WRAPPER_RE = re.compile(r"<(ActionButton)\b[^>]*?/?>", re.DOTALL)
RAW_REQUIRED = ("data-qid", "data-qs-action", "title")
WRAPPER_REQUIRED = ("qid", "qsAction", "title")

failures: list[str] = []
checked = 0

for path in sorted(ROOT.glob("**/*.tsx")):
    # shadcn primitives are generic library components; call sites carry attrs.
    if "components" in path.parts and "ui" in path.parts:
        continue
    text = path.read_text(encoding="utf-8")

    def _check(match: re.Match[str], required: tuple[str, ...], kind: str) -> None:
        global checked
        tag = match.group(0)
        checked += 1
        if "...props" in tag:
            return
        missing = [a for a in required if not re.search(rf"\b{re.escape(a)}\b", tag)]
        if missing:
            line = text[: match.start()].count("\n") + 1
            failures.append(f"{path.relative_to(ROOT.parent)}:{line} <{kind}> missing {', '.join(missing)}")

    for m in RAW_TAG_RE.finditer(text):
        _check(m, RAW_REQUIRED, m.group(1))
    for m in WRAPPER_RE.finditer(text):
        _check(m, WRAPPER_REQUIRED, "ActionButton")

if failures:
    print(f"FAIL: {len(failures)}/{checked} interactive elements missing attributes")
    for f in failures:
        print(f"  {f}")
    sys.exit(1)

print(f"OK: {checked} interactive elements carry required best-practices-react attributes")
