#!/usr/bin/env python3
"""Track and report how long browser tabs have been open.

Purpose
    Chrome's extension API exposes no tab creation time -- ``tab.list`` returns
    only id, title, url, active, and windowId -- so tab age cannot be read from
    the browser and has to be observed and remembered. This keeps a first-seen
    ledger and annotates tabs with their age.

    Age matters because a stale tab is the usual cause of a broken browser
    lane: a reviewer tab that has been open for days has accumulated
    conversation state, may hold a rate-limit banner, and is the first thing to
    suspect when a provider handler starts failing.

    The ledger is honest about what it knows. A tab first seen on the very
    first scan could have been opened seconds or weeks earlier, so its age is
    reported as a LOWER BOUND (``at_least``). Only tabs that appear in a later
    scan than the one that created the ledger have an age accurate to the gap
    between scans (``observed``). Reporting a lower bound as though it were
    exact is how "the tab is fresh" gets asserted about a week-old tab.

Inputs
    ``tab.list --json`` output on stdin.

Outputs
    ``annotate-tabs``: the same tabs, each with ``age_seconds``, ``age_human``,
    ``first_seen``, and ``age_source``.
    ``report``: a sorted, human-readable oldest-first listing.

Failure modes
    An unreadable or corrupt ledger is rebuilt from the current scan; ages then
    restart as lower bounds rather than failing the caller. A ledger that
    cannot be written is reported but never fatal -- age is diagnostic, not a
    proof boundary.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

LEDGER = Path(os.environ.get("SURF_TAB_AGE_LEDGER", Path.home() / ".surf" / "tab-first-seen.json"))
SCHEMA = "surf.tab_age_ledger.v1"


def _load() -> tuple[dict[str, dict[str, Any]], bool]:
    """Return (entries, ledger_existed)."""
    try:
        payload = json.loads(LEDGER.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, False
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        return {}, False
    entries = payload.get("tabs")
    if not isinstance(entries, dict):
        return {}, False
    return {str(k): v for k, v in entries.items() if isinstance(v, dict)}, True


def _save(entries: dict[str, dict[str, Any]]) -> str | None:
    """Persist atomically; return an error string rather than raising."""
    try:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=str(LEDGER.parent), delete=False, suffix=".tmp"
        )
        with handle as fh:
            json.dump({"schema": SCHEMA, "tabs": entries}, fh, sort_keys=True)
        os.replace(handle.name, LEDGER)
    except OSError as exc:
        return str(exc)
    return None


def human(seconds: float) -> str:
    seconds = int(max(0, seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"
    return f"{seconds // 86400}d{(seconds % 86400) // 3600:02d}h"


def _tabs_from(payload: Any) -> list[dict[str, Any]]:
    """Accept either a bare list or the --with-kde {"tabs": [...]} shape."""
    if isinstance(payload, list):
        return [t for t in payload if isinstance(t, dict)]
    if isinstance(payload, dict):
        inner = payload.get("tabs")
        if isinstance(inner, list):
            return [t for t in inner if isinstance(t, dict)]
    return []


def annotate(payload: Any) -> Any:
    now = time.time()
    entries, ledger_existed = _load()
    tabs = _tabs_from(payload)
    seen_now: set[str] = set()

    for tab in tabs:
        tab_id = str(tab.get("id") or "")
        if not tab_id:
            continue
        seen_now.add(tab_id)
        entry = entries.get(tab_id)
        if entry is None:
            # A tab present on the first ever scan predates the ledger by an
            # unknown amount; one appearing later was genuinely created since
            # the previous scan.
            entries[tab_id] = {"first_seen": now, "precise": bool(ledger_existed)}
            entry = entries[tab_id]
        first_seen = float(entry.get("first_seen") or now)
        precise = bool(entry.get("precise"))
        tab["first_seen"] = first_seen
        tab["age_seconds"] = round(now - first_seen, 1)
        tab["age_human"] = ("" if precise else ">=") + human(now - first_seen)
        tab["age_source"] = "observed" if precise else "at_least"

    # Forget tabs that are gone so the ledger tracks the browser rather than
    # growing without bound.
    for stale in [k for k in entries if k not in seen_now]:
        del entries[stale]
    error = _save(entries)
    if error and isinstance(payload, dict):
        payload["tab_age_ledger_error"] = error
    return payload


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "annotate-tabs"
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError) as exc:
        print(f"tab_age: unreadable tab list on stdin: {exc}", file=sys.stderr)
        return 1
    annotated = annotate(payload)
    if mode == "report":
        tabs = sorted(
            _tabs_from(annotated), key=lambda t: t.get("age_seconds", 0), reverse=True
        )
        for tab in tabs:
            print(
                f"{tab.get('age_human', '?'):>8}  {str(tab.get('id', '')):<12}"
                f"{(tab.get('title') or '')[:44]:<46}{(tab.get('url') or '')[:60]}"
            )
        return 0
    json.dump(annotated, sys.stdout, indent=2, sort_keys=True)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
