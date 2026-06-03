#!/usr/bin/env python3
"""Return 0 if Chrome focus changed between two focus.state JSON blobs."""

from __future__ import annotations

import json
import sys


def _parse(blob: str) -> dict:
    if not blob or not blob.strip():
        return {}
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        return {}


def focus_changed(before_json: str, after_json: str) -> bool:
    before = _parse(before_json)
    after = _parse(after_json)
    return before.get("focusedWindowId") != after.get("focusedWindowId") or before.get(
        "activeTabId"
    ) != after.get("activeTabId")


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: focus_changed.py BEFORE_JSON AFTER_JSON", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(0 if focus_changed(sys.argv[1], sys.argv[2]) else 1)


if __name__ == "__main__":
    main()
