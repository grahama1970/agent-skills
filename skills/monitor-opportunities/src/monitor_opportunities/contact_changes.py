"""Detect contact changes between nightly runs and turn them into vendor leads.

A contact who just switched roles, joined a hiring company, or whose company
just won a contract is the highest-value CONSULTING signal available: the
window is time-boxed (a leader ~60 days into a new mandate has budget and a
problem list; 18 months in they do not), and the relationship is already warm.

Two independent change sources, per operator direction (2026-08-13):
  LinkedIn  — the role/org we captured for that person tonight vs last night
              (from the actively-hiring and who-viewed captures).
  brave-search — public news about the contact and their org (new role
              announcements, contract/project wins, funding), which catches
              changes LinkedIn never shows us and covers people we only see
              once.

State lives in /memory `contact_snapshots`, read back by EXACT KEY via
/recall/by-keys (the semantic recall view does not index these collections —
graph-memory-operator#120), so detection never depends on search quality.

Fail-soft everywhere: no memory service, no search tool, or a first-ever run
yields zero leads and an honest receipt — never a fabricated change.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

from loguru import logger

SNAPSHOT_COLLECTION = "contact_snapshots"
BRAVE_SEARCH = Path.home() / ".claude" / "skills" / "brave-search" / "brave_search.py"

# Public-signal grammar for a contact-level change. Bounded and fixture-tested;
# the classifier of record is the human reading the digest.
_ROLE_CHANGE = re.compile(
    r"joins?|joined|appointed|named|promoted|"
    r"new (?:role|position|chief|head|vp|director)|"
    r"steps into|takes over as|hired as|starts as",
    re.I,
)
_PROJECT_WIN = re.compile(
    r"awarded|wins?\s+(?:a\s+)?(?:contract|deal|project|bid)|"
    r"won\s+(?:a\s+)?(?:contract|deal|project)|"
    r"secures?\s+(?:a\s+)?(?:contract|deal|\$)|selected (?:to|as|for)|"
    r"lands?\s+(?:a\s+)?(?:contract|deal)|raises?\s+\$|series\s+[a-e]\b",
    re.I,
)


def contact_key(name: str, org: str = "") -> str:
    """Stable id for one person. Org is deliberately EXCLUDED: the whole point
    is to detect the same person appearing at a different org."""
    norm = " ".join(str(name or "").lower().split())
    return "c-" + hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def normalize_contacts(rows: list[dict[str, Any]], source: str) -> list[dict[str, Any]]:
    """Reduce heterogeneous capture rows to the fields change detection needs."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for r in rows:
        name = str(r.get("name") or "").strip()
        if not name or len(name) < 3:
            continue
        key = contact_key(name)
        if key in seen:
            continue
        seen.add(key)
        role = str(r.get("current") or r.get("headline") or r.get("role") or "").strip()
        org = str(r.get("org") or r.get("organization") or "").strip()
        if not org and " at " in role:
            org = role.split(" at ", 1)[1].strip()
        out.append({
            "_key": key,
            "name": name,
            "org": org,
            "role": role[:160],
            "source": source,
            "profile": r.get("profile"),
            "mutuals": r.get("mutuals"),
        })
    return out


def _memory_post(
    memory_url: str, path: str, payload: dict[str, Any], timeout: int = 20
) -> dict[str, Any]:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{memory_url}{path}", data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def load_previous(memory_url: str, keys: list[str]) -> dict[str, dict[str, Any]]:
    """Exact-key read of the last snapshot for these contacts. {} on any failure."""
    if not keys:
        return {}
    try:
        data = _memory_post(
            memory_url, "/recall/by-keys", {"collection": SNAPSHOT_COLLECTION, "keys": keys}
        )
    except Exception as exc:  # noqa: BLE001 - absence of history is not an error
        logger.warning("contact snapshot read skipped: {}", exc)
        return {}
    out: dict[str, dict[str, Any]] = {}
    for doc in data.get("documents", []) or []:
        d = doc.get("document") or doc
        if d.get("_key"):
            out[str(d["_key"])] = d
    return out


def store_snapshot(memory_url: str, contacts: list[dict[str, Any]], observed_at: str) -> int:
    """Upsert tonight's snapshot. Returns how many were stored."""
    stored = 0
    for c in contacts:
        try:
            doc = {**c, "observed_at": observed_at}
            res = _memory_post(
                memory_url, "/store", {"document": doc, "collection": SNAPSHOT_COLLECTION}
            )
            stored += 1 if res.get("stored") else 0
        except Exception as exc:  # noqa: BLE001 - persistence must never fail the run
            logger.warning("contact snapshot store skipped for {}: {}", c.get("name"), exc)
    return stored


def diff_contacts(
    previous: dict[str, dict[str, Any]], current: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """LinkedIn-side changes: same person, different org or role."""
    changes: list[dict[str, Any]] = []
    for c in current:
        prior = previous.get(c["_key"])
        if not prior:
            continue  # first sighting is not a change
        old_org, new_org = str(prior.get("org") or ""), str(c.get("org") or "")
        old_role, new_role = str(prior.get("role") or ""), str(c.get("role") or "")
        if new_org and old_org and new_org.lower() != old_org.lower():
            changes.append({
                "change_type": "org_change", "name": c["name"],
                "from": old_org, "to": new_org, "role": new_role,
                "evidence": "linkedin_capture", "profile": c.get("profile"),
                "mutuals": c.get("mutuals"),
            })
        elif new_role and old_role and new_role.lower() != old_role.lower():
            changes.append({
                "change_type": "role_change", "name": c["name"],
                "from": old_role, "to": new_role, "org": new_org,
                "evidence": "linkedin_capture", "profile": c.get("profile"),
                "mutuals": c.get("mutuals"),
            })
    return changes


def _brave(query: str, timeout: int = 40) -> str:
    """Free key first, paid fallback on quota exhaustion (authorized 2026-08-12)."""
    if not BRAVE_SEARCH.exists():
        return ""
    import os

    argv = ["python3", str(BRAVE_SEARCH), "web", query, "--count", "4", "--no-json",
            "--freshness", "pm"]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout
        paid = os.environ.get("BRAVE_API_KEY_PAID")
        quota = (
            "429" in proc.stderr or "QUOTA" in proc.stderr.upper()
            or "not found in env" in proc.stderr
        )
        if paid and quota:
            proc = subprocess.run(
                argv, capture_output=True, text=True, timeout=timeout,
                env=dict(os.environ, BRAVE_API_KEY=paid),
            )
            if proc.returncode == 0:
                return proc.stdout
    except (subprocess.TimeoutExpired, OSError):
        return ""
    return ""


def public_signal_changes(
    contacts: list[dict[str, Any]], limit: int = 8
) -> list[dict[str, Any]]:
    """brave-search pass for role moves and project/contract wins.

    Catches what LinkedIn does not show us, and works on first sighting (no
    prior snapshot needed) — which matters because most contacts are seen once.
    """
    changes: list[dict[str, Any]] = []
    for c in contacts[:limit]:
        name, org = c.get("name"), c.get("org") or ""
        query = f"{name} {org}".strip()
        if not query:
            continue
        text = _brave(f"{query} new role OR joins OR awarded OR wins contract 2026")
        if not text:
            continue
        role_m = _ROLE_CHANGE.search(text)
        win_m = _PROJECT_WIN.search(text)
        if not (role_m or win_m):
            continue
        changes.append({
            "change_type": "project_win" if win_m else "public_role_change",
            "name": name,
            "org": org,
            "role": c.get("role"),
            "evidence": (win_m or role_m).group(0),
            "evidence_source": "brave-search",
            "profile": c.get("profile"),
            "mutuals": c.get("mutuals"),
        })
    return changes


def vendor_leads(changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Turn contact changes into consulting/vendor leads with an explicit why.

    Graham transmits every message himself; this only prepares the case.
    """
    leads: list[dict[str, Any]] = []
    for ch in changes:
        t = ch["change_type"]
        if t == "org_change":
            why = (
                f"{ch['name']} moved from {ch['from']} to {ch['to']}. A new org means a new "
                "mandate and budget — and your warm path travels with the person."
            )
        elif t in ("role_change", "public_role_change"):
            why = (
                f"{ch['name']} changed role ({ch.get('to') or ch.get('evidence')}). New scope "
                "usually means a problem list and spend authority in the first months."
            )
        else:
            why = (
                f"{ch.get('org') or ch['name']} shows a win signal ('{ch['evidence']}'). "
                "Contract and funding wins are when teams staff up and hire vendors."
            )
        leads.append({
            "name": ch["name"],
            "organization": ch.get("to") if t == "org_change" else ch.get("org"),
            "change_type": t,
            "why_now": why,
            "evidence": ch.get("evidence"),
            "evidence_source": ch.get("evidence_source", "linkedin_capture"),
            "warm_path": ch.get("mutuals"),
            "profile": ch.get("profile"),
            "action": "consulting_outreach_inmail",
            "transmitted_by": "human",
        })
    return leads


def detect(
    captured: list[dict[str, Any]],
    source: str,
    memory_url: str,
    observed_at: str,
    public_signal_limit: int = 8,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Full pass: normalize -> diff vs memory -> public signals -> leads + receipt."""
    contacts = normalize_contacts(captured, source)
    previous = load_previous(memory_url, [c["_key"] for c in contacts])
    linkedin_changes = diff_contacts(previous, contacts)
    public_changes = public_signal_changes(contacts, limit=public_signal_limit)
    stored = store_snapshot(memory_url, contacts, observed_at)
    leads = vendor_leads(linkedin_changes + public_changes)
    receipt = {
        "schema": "monitor_opportunities.contact_changes.v1",
        "contacts_tracked": len(contacts),
        "had_prior_snapshot": len(previous),
        "linkedin_changes": len(linkedin_changes),
        "public_signal_changes": len(public_changes),
        "vendor_leads": len(leads),
        "snapshots_stored": stored,
        "first_run_note": (
            "No prior snapshots: LinkedIn diffs start next run. Public-signal "
            "changes still work on first sighting."
            if not previous else None
        ),
    }
    return leads, receipt
