"""Contact freshness: what changed, and is what we know still true?

The value proposition (Graham 2026-08-13): "a contact switches roles/jobs or
wins a project ... where we might be a good vendor for". A contact who just
moved, or whose company just won work, is a time-boxed consulting opening into
an already-warm relationship.

Change detection uses two independent sources so neither can silently go quiet:
  stored-vs-observed  the role/org we hold vs what was observed this cycle
  public signal       brave-search for role moves and contract/funding wins,
                      which also works on FIRST sighting (most contacts are
                      seen once, so a stored-vs-observed diff would never fire)

Staleness is reported, never guessed: a contact with no observation newer than
`stale_days` is flagged for re-research rather than assumed unchanged.
"""

from __future__ import annotations

import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger

BRAVE_SEARCH = Path.home() / ".claude" / "skills" / "brave-search" / "brave_search.py"

ROLE_CHANGE = re.compile(
    r"joins?|joined|appointed|named|promoted|"
    r"new (?:role|position|chief|head|vp|director)|"
    r"steps into|takes over as|hired as|starts as",
    re.I,
)
PROJECT_WIN = re.compile(
    r"awarded|wins?\s+(?:a\s+)?(?:contract|deal|project|bid)|"
    r"won\s+(?:a\s+)?(?:contract|deal|project)|"
    r"secures?\s+(?:a\s+)?(?:contract|deal|\$)|selected (?:to|as)|"
    r"lands?\s+(?:a\s+)?(?:contract|deal)|raises?\s+\$|series\s+[a-e]\b",
    re.I,
)


def _parse_dt(value: Any) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def stale_contacts(
    contacts: list[dict[str, Any]], stale_days: int = 30, now: datetime | None = None
) -> list[dict[str, Any]]:
    """Contacts whose last observation is older than the freshness window."""
    now = now or datetime.now(UTC)
    out = []
    for c in contacts:
        seen = _parse_dt(c.get("observed_at"))
        if seen is None or (now - seen).days > stale_days:
            out.append({
                "name": c.get("name"), "org": c.get("org"),
                "last_seen": c.get("observed_at"),
                "age_days": None if seen is None else (now - seen).days,
            })
    return out


def brave(query: str, timeout: int = 40) -> str:
    """Free key first, paid fallback on quota exhaustion."""
    if not BRAVE_SEARCH.exists():
        return ""
    argv = ["python3", str(BRAVE_SEARCH), "web", query, "--count", "4",
            "--no-json", "--freshness", "pm"]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout
        paid = os.environ.get("BRAVE_API_KEY_PAID")
        quota = ("429" in proc.stderr or "QUOTA" in proc.stderr.upper()
                 or "not found in env" in proc.stderr)
        if paid and quota:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                                  env=dict(os.environ, BRAVE_API_KEY=paid))
            if proc.returncode == 0:
                return proc.stdout
    except (subprocess.TimeoutExpired, OSError):
        return ""
    return ""


def detect_changes(
    stored: dict[str, dict[str, Any]],
    observed: list[dict[str, Any]],
    research_limit: int = 5,
) -> list[dict[str, Any]]:
    """Stored-vs-observed diffs plus a bounded public-signal pass."""
    changes: list[dict[str, Any]] = []
    for c in observed:
        prior = stored.get(str(c.get("_key")))
        if not prior:
            continue
        old_org, new_org = str(prior.get("org") or ""), str(c.get("org") or "")
        old_role, new_role = str(prior.get("role") or ""), str(c.get("role") or "")
        if new_org and old_org and new_org.lower() != old_org.lower():
            changes.append({"change_type": "org_change", "name": c.get("name"),
                            "from": old_org, "to": new_org,
                            "evidence_source": "stored_vs_observed"})
        elif new_role and old_role and new_role.lower() != old_role.lower():
            changes.append({"change_type": "role_change", "name": c.get("name"),
                            "from": old_role, "to": new_role, "org": new_org,
                            "evidence_source": "stored_vs_observed"})
    for c in observed[:research_limit]:
        name, org = c.get("name"), c.get("org") or ""
        if not name:
            continue
        text = brave(f"{name} {org} new role OR joins OR awarded OR wins contract 2026")
        if not text:
            continue
        win, role = PROJECT_WIN.search(text), ROLE_CHANGE.search(text)
        if not (win or role):
            continue
        changes.append({
            "change_type": "project_win" if win else "public_role_change",
            "name": name, "org": org,
            "evidence": (win or role).group(0),
            "evidence_source": "brave-search",
        })
    if not changes:
        logger.info("no contact changes detected this cycle")
    return changes
