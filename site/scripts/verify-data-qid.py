#!/usr/bin/env python3
"""Verify best-practices-react write-time attributes in site source.

Every interactive element (<a>, <button>) in site TSX must carry
data-qid, data-qs-action, and title. Exit 1 = not shippable.

Static source check only: this site is fully statically rendered with no
conditional interactive chrome, so source coverage equals DOM coverage.
If conditionally-rendered interactive components are added, switch to the
live-DOM manifest flow (/test-interactions generate) per the skill.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ("data-qid", "data-qs-action", "title")
# Opening tags for interactive elements, including ButtonLink (renders <a>).
TAG_RE = re.compile(r"<(a|button|ButtonLink)\b[^>]*?/?>", re.DOTALL)

failures: list[str] = []
checked = 0

for path in sorted(ROOT.glob("**/*.tsx")):
    if "node_modules" in path.parts or ".next" in path.parts:
        continue
    text = path.read_text(encoding="utf-8")
    for m in TAG_RE.finditer(text):
        tag = m.group(0)
        checked += 1
        # A spread pass-through ({...props}) receives the attributes from a
        # props type that requires them (see ButtonLinkProps); call sites are
        # still checked individually.
        if "...props" in tag:
            continue
        missing = [attr for attr in REQUIRED if attr not in tag]
        # ButtonLink enforces the attrs via its required prop types; the
        # call sites still must pass them, so the same check applies.
        if missing:
            line = text[: m.start()].count("\n") + 1
            failures.append(
                f"{path.relative_to(ROOT)}:{line} <{m.group(1)}> missing {', '.join(missing)}"
            )

if failures:
    print(f"FAIL: {len(failures)}/{checked} interactive elements missing attributes")
    for f in failures:
        print(f"  {f}")
    sys.exit(1)

print(f"OK: {checked} interactive elements carry data-qid, data-qs-action, title")
