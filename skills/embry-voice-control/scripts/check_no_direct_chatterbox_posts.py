#!/usr/bin/env python3
"""NO_DIRECT_CHATTERBOX_POSTS: retained static gate.

Deterministic AST/lexical scan of ``src/embry_voice_control`` proving no file
reaches the Chatterbox service outside the gate/core seam. Flags:

- string literals naming the service endpoints (``/synthesize``,
  ``/synthesize-batch``);
- ``httpx.post`` / ``requests.post`` / ``post_json(...)`` call sites whose
  target expression mentions a Chatterbox URL constant (``:8018``,
  ``chatterbox``) — except in the allowlisted seam module.

Allowlist: ``chatterbox_gate.py`` (the seam; the POST itself lives in
speak_core, loaded and verified there).

Exits nonzero on any violation. Run after any change to the package.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "embry_voice_control"
ALLOWLIST = {"chatterbox_gate.py"}

ENDPOINT_LITERALS = {"/synthesize", "/synthesize-batch"}
URL_HINTS = (":8018", "chatterbox")
POST_CALLEES = {"post", "post_json"}


def _flagged_literals(tree: ast.AST) -> list[str]:
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in ENDPOINT_LITERALS:
                hits.append(f"endpoint literal {node.value!r} @ line {node.lineno}")
    return hits


def _flagged_posts(tree: ast.AST) -> list[str]:
    hits: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "attr", None) or getattr(func, "id", None)
        if name not in POST_CALLEES:
            continue
        rendered = ast.unparse(node)
        if any(hint in rendered for hint in URL_HINTS):
            hits.append(f"chatterbox POST call @ line {node.lineno}: {rendered[:120]}")
    return hits


def main() -> int:
    violations: list[str] = []
    files = sorted(SRC.glob("*.py"))
    for path in files:
        if path.name in ALLOWLIST:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for hit in _flagged_literals(tree) + _flagged_posts(tree):
            violations.append(f"{path.name}: {hit}")
    if violations:
        print("FAIL_NO_DIRECT_CHATTERBOX_POSTS")
        for v in violations:
            print("  ", v)
        return 1
    scanned = ", ".join(p.name for p in files)
    print("PASS_NO_DIRECT_CHATTERBOX_POSTS")
    print("  scanned:", scanned)
    print("  allowlist:", sorted(ALLOWLIST))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
