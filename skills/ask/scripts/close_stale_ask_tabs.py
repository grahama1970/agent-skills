#!/usr/bin/env python3
"""Close stale browser tabs that /ask opened for its own runs.

Each /ask browser run records a project binding under
``~/.pi/<backend>-projects/ask-*.json`` with the ``tab_id`` it opened/bound and
a ``last_used_at`` timestamp. Roundtable/single-handler runs never closed those
tabs, so provider windows accumulate dozens of stale ChatGPT/Kimi/Grok/etc tabs.

This reaper closes ONLY tabs that /ask itself created, identified by three
independent guards so a user's own tabs are never touched:

  1. tab_id must be referenced by an ``ask-*`` binding file (not any other tab);
  2. the live tab's host must match that binding's provider host (defence in
     depth against a browser recycling a tab_id onto an unrelated page);
  3. the binding's last_used_at must be older than --max-age-hours, so an
     in-flight run's tab is never closed.

Dry-run by default. Pass --apply to actually close. Emits a JSON receipt.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# skills/ask/scripts/close_stale_ask_tabs.py -> skills/
SKILLS_DIR = Path(__file__).resolve().parents[2]
SURF_RUN = SKILLS_DIR / "surf" / "run.sh"
PI_HOME = Path.home() / ".pi"

# Provider host suffixes per /ask browser backend. A live tab is only eligible
# for closing when its host ends with one of the backend's suffixes.
BACKEND_HOST_SUFFIXES = {
    "webgpt": ("chatgpt.com", "chat.openai.com"),
    "webclaude": ("claude.ai",),
    "webkimi": ("kimi.com",),
    "webgemini": ("gemini.google.com",),
    "webgrok": ("grok.com",),
    "webdeepseek": ("deepseek.com",),
}


def _host_of(url: str) -> str:
    from urllib.parse import urlparse

    try:
        return (urlparse(url).netloc or "").lower()
    except Exception:
        return ""


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        text = value.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _surf(args: list[str], *, timeout: float = 60.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(SURF_RUN), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _live_tabs() -> dict[int, str]:
    """Return {tab_id: url} for all currently open tabs, or raise on failure."""
    proc = _surf(["tab.list", "--json"])
    if proc.returncode != 0:
        raise RuntimeError(f"surf tab.list failed (rc={proc.returncode}): {proc.stderr[:300]}")
    data = json.loads(proc.stdout)
    tabs = data if isinstance(data, list) else data.get("tabs", data.get("result", []))
    out: dict[int, str] = {}
    for t in tabs:
        try:
            out[int(t["id"])] = str(t.get("url", ""))
        except (KeyError, ValueError, TypeError):
            continue
    return out


def _iter_ask_bindings():
    """Yield (backend, binding_path, binding_dict) for every ask-* binding."""
    for backend in BACKEND_HOST_SUFFIXES:
        proj_dir = PI_HOME / f"{backend}-projects"
        if not proj_dir.is_dir():
            continue
        for path in sorted(proj_dir.glob("ask-*.json")):
            try:
                data = json.loads(path.read_text())
            except Exception:
                data = {}
            yield backend, path, data


def reap(
    *,
    max_age_hours: float,
    trust_window_hours: float,
    keep_recent_per_backend: int,
    apply: bool,
    prune_orphans: bool,
    now: datetime,
) -> dict:
    live = _live_tabs()
    live_ids = set(live)

    # Many ask-* bindings reuse the SAME tab_id, so the unit of work is a live
    # tab, not a binding file. Build a tab-centric view keyed by (backend,
    # tab_id): the newest last_used_at across all its bindings decides
    # staleness, and every binding path that points at it is pruned together.
    tabs: dict[tuple[str, int], dict] = {}
    orphan_paths: list[Path] = []

    def _ts_of(data: dict) -> datetime | None:
        return _parse_ts(data.get("last_used_at")) or _parse_ts(data.get("created_at"))

    for backend, path, data in _iter_ask_bindings():
        tab_raw = data.get("tab_id")
        try:
            tab_id = int(tab_raw) if tab_raw not in (None, "") else None
        except (ValueError, TypeError):
            tab_id = None

        if tab_id is None or tab_id not in live_ids:
            orphan_paths.append(path)  # binding whose tab is already gone
            continue

        key = (backend, tab_id)
        ts = _ts_of(data)
        entry = tabs.setdefault(key, {
            "backend": backend,
            "tab_id": tab_id,
            "host": _host_of(live[tab_id]),
            "newest_ts": None,
            "paths": [],
        })
        entry["paths"].append(path)
        if ts is not None and (entry["newest_ts"] is None or ts > entry["newest_ts"]):
            entry["newest_ts"] = ts

    # Protect the N most-recently-used distinct tabs per backend (in-flight runs).
    protected: set[tuple[str, int]] = set()
    by_backend: dict[str, list] = {}
    for key, entry in tabs.items():
        by_backend.setdefault(entry["backend"], []).append((key, entry))
    for backend, items in by_backend.items():
        items.sort(
            key=lambda ke: ke[1]["newest_ts"] or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        for key, _ in items[:max(0, keep_recent_per_backend)]:
            protected.add(key)

    closed: list[dict] = []
    skipped: list[dict] = []
    pruned_orphans: list[str] = []
    errors: list[dict] = []

    for key, entry in tabs.items():
        backend, tab_id = key
        host = entry["host"]
        suffixes = BACKEND_HOST_SUFFIXES[backend]
        record = {
            "backend": backend,
            "tab_id": tab_id,
            "host": host,
            "bindings": len(entry["paths"]),
            "newest_used_at": entry["newest_ts"].strftime("%Y-%m-%dT%H:%M:%SZ") if entry["newest_ts"] else None,
        }

        reason_skip = None
        if key in protected:
            reason_skip = "protected_recent"
        elif not any(host == s or host.endswith("." + s) for s in suffixes):
            reason_skip = f"host_mismatch:{host}"
        elif entry["newest_ts"] is None:
            reason_skip = "no_timestamp"
        else:
            age_h = (now - entry["newest_ts"]).total_seconds() / 3600.0
            if age_h < max_age_hours:
                reason_skip = f"too_recent:{age_h:.1f}h"
            elif age_h > trust_window_hours:
                # Browser tab ids are recycled over time, so a binding older than
                # the trust window may now point at an unrelated (possibly the
                # user's own) tab. Refuse to close by an untrustworthy id — the
                # stale binding file is pruned as an orphan instead.
                reason_skip = f"tab_id_untrusted:{age_h:.1f}h"

        if reason_skip:
            skipped.append({**record, "skip_reason": reason_skip})
            continue

        if apply:
            proc = _surf(["tab.close", str(tab_id)])
            if proc.returncode != 0:
                errors.append({**record, "error": proc.stderr[:200] or f"rc={proc.returncode}"})
                continue
            if prune_orphans:
                for p in entry["paths"]:
                    try:
                        p.unlink()
                    except Exception:
                        pass
        closed.append(record)

    # Orphan binding files (tab already gone) — optionally prune.
    if prune_orphans:
        for p in orphan_paths:
            if apply:
                try:
                    p.unlink()
                except Exception as exc:
                    errors.append({"binding": str(p), "error": str(exc)})
                    continue
            pruned_orphans.append(str(p))

    return {
        "schema": "ask.close_stale_tabs_receipt.v1",
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "applied": apply,
        "max_age_hours": max_age_hours,
        "keep_recent_per_backend": keep_recent_per_backend,
        "prune_orphans": prune_orphans,
        "live_tab_count": len(live),
        "closed_count": len(closed),
        "skipped_count": len(skipped),
        "pruned_orphan_bindings": len(pruned_orphans),
        "closed": closed,
        "skipped": skipped,
        "orphans": pruned_orphans,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="actually close tabs (default: dry-run)")
    ap.add_argument("--max-age-hours", type=float, default=6.0,
                    help="only close ask tabs whose binding is older than this (default 6h)")
    ap.add_argument("--trust-window-hours", type=float, default=24.0,
                    help="never close by a tab_id whose binding is older than this; "
                         "browser tab ids get recycled, so an older id is untrusted (default 24h)")
    ap.add_argument("--keep-recent-per-backend", type=int, default=1,
                    help="always keep the N most-recently-used ask tabs per backend (default 1)")
    ap.add_argument("--prune-orphans", action="store_true",
                    help="also delete ask-* binding files whose tab is gone / after closing")
    ap.add_argument("--json", action="store_true", help="emit the JSON receipt only")
    args = ap.parse_args(argv)

    if not SURF_RUN.exists():
        print(f"surf run.sh not found at {SURF_RUN}", file=sys.stderr)
        return 2

    now = datetime.now(timezone.utc)
    try:
        receipt = reap(
            max_age_hours=args.max_age_hours,
            trust_window_hours=args.trust_window_hours,
            keep_recent_per_backend=args.keep_recent_per_backend,
            apply=args.apply,
            prune_orphans=args.prune_orphans,
            now=now,
        )
    except Exception as exc:
        print(json.dumps({"schema": "ask.close_stale_tabs_receipt.v1", "error": str(exc)}))
        return 1

    if args.json:
        print(json.dumps(receipt, indent=2))
    else:
        mode = "APPLIED" if receipt["applied"] else "DRY-RUN"
        print(f"[{mode}] {receipt['closed_count']} stale /ask tab(s) "
              f"{'closed' if receipt['applied'] else 'would close'}; "
              f"{receipt['skipped_count']} skipped; "
              f"{receipt['pruned_orphan_bindings']} orphan binding(s) pruned; "
              f"{len(receipt['errors'])} error(s).")
        for c in receipt["closed"]:
            print(f"  close  {c['backend']:11s} tab {c['tab_id']}  {c['host']}")
        if receipt["errors"]:
            for e in receipt["errors"]:
                print(f"  ERROR  {e.get('backend','?')} tab {e.get('tab_id','?')}: {e.get('error')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
