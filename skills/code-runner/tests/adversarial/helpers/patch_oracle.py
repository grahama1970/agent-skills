"""patch_oracle - helpers.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path


_DIFF_RE = re.compile(r"^diff --git a/(.*?) b/(.*?)$")


def _diff_text_from_artifact(path: Path) -> str:
    text = path.read_text(errors="replace")
    if "```diff" not in text:
        return text

    start = text.index("```diff") + len("```diff")
    rest = text[start:]
    end = rest.find("```")
    if end == -1:
        return rest
    return rest[:end]


def touched_paths_from_patch_or_hunk(path: Path) -> set[str]:
    touched: set[str] = set()

    for line in _diff_text_from_artifact(path).splitlines():
        match = _DIFF_RE.match(line)
        if match:
            old, new = match.groups()
            if old != "/dev/null":
                touched.add(old)
            if new != "/dev/null":
                touched.add(new)
            continue
        if line.startswith("diff --git "):
            parts = shlex.split(line)
            if len(parts) == 4:
                for raw in parts[2:]:
                    if raw == "/dev/null":
                        continue
                    if raw.startswith(("a/", "b/")):
                        touched.add(raw[2:])
            continue

        if line.startswith("rename from "):
            touched.add(line.removeprefix("rename from ").strip())
        elif line.startswith("rename to "):
            touched.add(line.removeprefix("rename to ").strip())
        elif line.startswith("copy from "):
            touched.add(line.removeprefix("copy from ").strip())
        elif line.startswith("copy to "):
            touched.add(line.removeprefix("copy to ").strip())

    return touched


def assert_patch_touches_only(path: Path, allowed: set[str]) -> None:
    touched = touched_paths_from_patch_or_hunk(path)
    illegal = sorted(item for item in touched if item not in allowed)
    assert not illegal, f"{path} touched outside allowlist: {illegal}; touched={sorted(touched)}"
