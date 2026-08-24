#!/usr/bin/env python3
"""Generate public Calendly metadata from the Calendly API.

The PAT is a build-time/server-side credential. This script writes only public
booking links and display metadata that can safely ship in the static bundle.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


SITE = Path(__file__).resolve().parents[1]
OUT = SITE / "calendly.json"
API = "https://api.calendly.com"


def get_json(path: str, token: str, query: dict[str, str] | None = None) -> dict:
    url = f"{API}{path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "grahama.co site build",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def public_event_type(raw: dict) -> dict:
    return {
        "name": raw.get("name"),
        "slug": raw.get("slug"),
        "active": bool(raw.get("active")),
        "duration": raw.get("duration"),
        "kind": raw.get("kind"),
        "schedulingUrl": raw.get("scheduling_url"),
    }


def main() -> int:
    token = os.environ.get("CALENDLY_PAT", "").strip()
    if not token:
        if OUT.exists():
            print(f"calendly: CALENDLY_PAT missing; preserving {OUT}")
            return 0
        print("error: CALENDLY_PAT missing and no calendly.json exists", file=sys.stderr)
        return 1

    try:
        me = get_json("/users/me", token).get("resource") or {}
        user_uri = me["uri"]
        event_types = get_json("/event_types", token, {"user": user_uri}).get("collection") or []
    except (KeyError, urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        print(f"error: calendly API refresh failed: {exc}", file=sys.stderr)
        return 1

    public_events = [public_event_type(item) for item in event_types]
    active_events = [item for item in public_events if item["active"] and item["schedulingUrl"]]
    primary_url = active_events[0]["schedulingUrl"] if active_events else me.get("scheduling_url")

    payload = {
        "generator": "site/scripts/gen_calendly.py",
        "source": "calendly_api_v2",
        "generatedFromApi": True,
        "asOf": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "user": {
            "name": me.get("name"),
            "slug": me.get("slug"),
            "timezone": me.get("timezone"),
            "schedulingUrl": me.get("scheduling_url"),
        },
        "primarySchedulingUrl": primary_url,
        "eventTypes": public_events,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"calendly: wrote {OUT} with {len(public_events)} event type(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
