#!/usr/bin/env python3
"""Write the day's events into memory so tomorrow's dream differs from today's (#1212).

The five-cycle reliability pilot produced five byte-identical journals
(sha `f812641f9dbbc7e2` across cycles 001-005). The pipeline was not broken:
recall returned the same residue every cycle because nothing new had ever been
written. A dream can only be about what is in memory, and nothing about any
particular day was.

So this writes the day in. Three kinds of thing reach Embry:

``code``           what was actually built, read from git
``project_state``  an opinion about where the work stands
``affect``         what the human seemed to be feeling

Each is stored as a first-person stance, not a log line -- "I spent the day on
the tone measurement and it came back negative" rather than
``3 commits to skills/persona-dream``. A log line recalled into a dream produces
a dream about a log line.

Volume is capped at 8 events. A forty-commit day must compress, because forty
events would drown the persona memories the dream is supposed to blend with,
and the blend is the entire point.

Every write is read back before it counts. ``/store`` has previously returned a
success body for a document it did not write, so the store response is not
evidence; a subsequent ``/recall`` that finds the key is.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
MEMORY_SOCKET = "/run/user/1000/embry/memory.sock"
COLLECTION = "lessons"

#: One day's events live under their own scope so recall can ask for "today"
#: specifically, rather than hoping today outranks everything else in a
#: top-k sweep. This is the first colon-namespaced scope in the skill; existing
#: persona scopes use ``<persona>-<suffix>``.
def day_scope(date: str) -> str:
    return f"episodic:day={date}"


#: Target 3-7 events, hard cap 8. Below 3 a day is not worth dreaming on; above
#: 8 the day crowds out identity.
MIN_EVENTS = 3
MAX_EVENTS = 8

#: How long an event stays worth recalling. Code churn is forgettable within a
#: week; how someone felt is not.
DECAY_CLASS = {"code": "fast", "project_state": "medium", "affect": "slow"}


def utc_now() -> str:
    return datetime.now().astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def rel(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path)


def _key_for(persona: str, date: str, text: str) -> str:
    src = f"{persona}:{date}:{text}"
    return "pd_day_" + hashlib.sha256(src.encode()).hexdigest()[:24]


def git_commits(repo: Path, date: str) -> list[dict[str, str]]:
    """Commits authored on ``date``, newest first."""
    try:
        out = subprocess.run(
            ["git", "log", f"--since={date} 00:00", f"--until={date} 23:59",
             "--pretty=format:%H%x1f%s", "--name-only", "-z"],
            cwd=str(repo), capture_output=True, text=True, timeout=60, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if out.returncode != 0:
        return []
    commits: list[dict[str, str]] = []
    for block in out.stdout.split("\x00\x00"):
        block = block.strip("\x00\n ")
        if not block or "\x1f" not in block:
            continue
        head, _, rest = block.partition("\x1f")
        subject, _, files = rest.partition("\n")
        commits.append({
            "sha": head[:9],
            "subject": subject.strip(),
            "files": "\n".join(f for f in files.split("\x00") if f.strip()),
        })
    return commits


def _area_of(path: str) -> str:
    """The area a changed file belongs to -- a skill name where possible."""
    parts = Path(path).parts
    if len(parts) >= 2 and parts[0] == "skills":
        return f"skills/{parts[1]}"
    return parts[0] if parts else "repo root"


def compress_commits(commits: list[dict[str, str]], budget: int) -> list[dict[str, Any]]:
    """Group a day's commits by area and speak about each group in first person.

    Forty commits is not forty things that happened; it is usually two or three
    things that happened, committed forty times. Grouping by area recovers that,
    and keeps a busy day inside the event budget without dropping a whole area
    on the floor.
    """
    by_area: dict[str, list[dict[str, str]]] = {}
    for c in commits:
        areas = {_area_of(f) for f in c["files"].splitlines() if f.strip()} or {"repo root"}
        # Attribute a commit to its dominant area so one commit is one thing.
        area = sorted(areas)[0] if len(areas) == 1 else Counter(
            _area_of(f) for f in c["files"].splitlines() if f.strip()
        ).most_common(1)[0][0]
        by_area.setdefault(area, []).append(c)

    ranked = sorted(by_area.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    events: list[dict[str, Any]] = []
    for area, group in ranked[:budget]:
        subjects = [g["subject"] for g in group]
        headline = subjects[0]
        # Strip a conventional-commit prefix; she would not say "feat:" aloud.
        headline = re.sub(r"^\w[\w./-]*:\s*", "", headline).strip()
        if len(group) == 1:
            stance = f"I worked on {area} today. The thing I did was: {headline}"
        else:
            stance = (
                f"I spent {len(group)} commits on {area} today. It started with "
                f"{headline!r} and kept going; that is where my attention was."
            )
        events.append({
            "kind": "code",
            "text": stance,
            "salience": round(min(1.0, 0.35 + 0.1 * len(group)), 3),
            "provenance": {
                "source": "git",
                "area": area,
                "commit_count": len(group),
                "commits": [g["sha"] for g in group[:12]],
                "subjects": subjects[:6],
            },
        })
    dropped = ranked[budget:]
    if dropped:
        # Never silently truncate: a day that lost areas must say so, or the
        # artifact reads as complete coverage when it is not.
        events.append({
            "kind": "code",
            "text": (
                f"I also touched {len(dropped)} other areas today "
                f"({', '.join(a for a, _ in dropped[:6])}) but nothing there held me."
            ),
            "salience": 0.2,
            "provenance": {"source": "git", "areas_folded": [a for a, _ in dropped],
                           "reason": "event budget"},
        })
    return events


def build_events(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[str]]:
    """Assemble the day's events, newest signal first. Returns (events, notes)."""
    notes: list[str] = []
    events: list[dict[str, Any]] = []

    # Affect and project_state are scarce and slow-decaying, so they get first
    # claim on the budget; code is abundant and compresses.
    for signal in args.affect or []:
        events.append({
            "kind": "affect", "text": signal.strip(),
            "salience": 0.9,
            "provenance": {"source": "operator", "channel": "--affect"},
        })
    for opinion in args.project_state or []:
        events.append({
            "kind": "project_state", "text": opinion.strip(),
            "salience": 0.7,
            "provenance": {"source": "operator", "channel": "--project-state"},
        })
    for raw in args.event or []:
        events.append({
            "kind": "code", "text": raw.strip(), "salience": 0.5,
            "provenance": {"source": "operator", "channel": "--event"},
        })

    if args.from_commits:
        budget = max(0, MAX_EVENTS - len(events))
        commits = git_commits(Path(args.repo), args.date)
        if not commits:
            notes.append(f"no commits found in {args.repo} on {args.date}")
        elif budget <= 0:
            notes.append("code events skipped: budget already spent on affect/project_state")
        else:
            code_events = compress_commits(commits, budget)
            events.extend(code_events)
            notes.append(f"{len(commits)} commits compressed to {len(code_events)} events")

    if len(events) > MAX_EVENTS:
        notes.append(f"trimmed {len(events) - MAX_EVENTS} events to the cap of {MAX_EVENTS}")
        events = events[:MAX_EVENTS]

    for idx, ev in enumerate(events):
        ev["decay_class"] = DECAY_CLASS.get(ev["kind"], "medium")
        ev["ordinal"] = idx
    return events, notes


def _client():
    import httpx
    return httpx.Client(
        transport=httpx.HTTPTransport(uds=MEMORY_SOCKET),
        base_url="http://localhost", timeout=15.0,
    )


def store_and_read_back(events: list[dict[str, Any]], persona: str, date: str) -> list[dict[str, Any]]:
    """Write each event, then prove it is there by recalling the scope.

    The store response is deliberately not the evidence. A single ``/recall``
    over the day scope after all writes is cheaper than one per event and is a
    stronger check: it proves the events are retrievable the same way the dream
    will retrieve them, not merely that rows exist.
    """
    scope = day_scope(date)
    results: list[dict[str, Any]] = []
    with _client() as client:
        for ev in events:
            document = {
                "_key": _key_for(persona, date, ev["text"]),
                "problem": f"What happened for {persona} on {date} ({ev['kind']})",
                "solution": ev["text"],
                "scope": scope,
                "tags": ["persona-dream", "day-event", f"kind:{ev['kind']}",
                         f"persona:{persona}", f"day:{date}"],
                "persona_id": persona,
                "kind": ev["kind"],
                "salience": ev["salience"],
                "decay_class": ev["decay_class"],
                "provenance": ev["provenance"],
                "day": date,
            }
            try:
                resp = client.post("/store", json={"document": document, "collection": COLLECTION})
                http_status, err = resp.status_code, None
            except Exception as exc:  # noqa: BLE001 - reported, not raised
                http_status, err = 0, str(exc)
            results.append({**ev, "document_key": document["_key"],
                            "store_http_status": http_status, "store_error": err,
                            "read_back": False})

        # The read-back. This is the part that counts.
        stored_keys = {r["document_key"] for r in results}
        seen: set[str] = set()
        try:
            resp = client.post("/recall", json={
                "q": f"{persona} {date} what happened today",
                "scope": scope, "k": 64, "threshold": 0.0,
            })
            for raw in (resp.json() or {}).get("items", []) or []:
                key = str(raw.get("_key") or raw.get("source_id") or "")
                if key in stored_keys:
                    seen.add(key)
            recall_error = None
        except Exception as exc:  # noqa: BLE001
            recall_error = str(exc)
        for r in results:
            r["read_back"] = r["document_key"] in seen
    for r in results:
        r["recall_error"] = recall_error
    return results


def run(args: argparse.Namespace) -> dict[str, Any]:
    events, notes = build_events(args)
    failed: list[str] = []

    if len(events) < MIN_EVENTS:
        return {
            "schema": "persona_dream.day_ingest_receipt.v1", "created_at": utc_now(),
            "status": "BLOCKED_TOO_FEW_EVENTS", "mocked": False, "live": False,
            "date": args.date, "scope": day_scope(args.date),
            "event_count": len(events), "minimum": MIN_EVENTS, "notes": notes,
            "failed_gates": [f"only {len(events)} events; a day needs at least {MIN_EVENTS}"],
        }

    stored = store_and_read_back(events, args.persona, args.date) if not args.dry_run else [
        {**e, "document_key": _key_for(args.persona, args.date, e["text"]),
         "store_http_status": None, "store_error": None, "read_back": None,
         "recall_error": None} for e in events
    ]

    if not args.dry_run:
        not_read_back = [s["document_key"] for s in stored if not s["read_back"]]
        if not_read_back:
            failed.append(f"stored_but_not_recallable:{len(not_read_back)}")
        errs = [s["store_error"] for s in stored if s["store_error"]]
        if errs:
            failed.append(f"store_errors:{len(errs)}")

    by_kind = Counter(s["kind"] for s in stored)
    receipt = {
        "schema": "persona_dream.day_ingest_receipt.v1",
        "created_at": utc_now(),
        "status": ("PASS_DAY_INGESTED" if not failed else "BLOCKED_DAY_INGEST")
        if not args.dry_run else "DRY_RUN_NOT_WRITTEN",
        "mocked": False,
        "live": not args.dry_run,
        "date": args.date,
        "persona": args.persona,
        "scope": day_scope(args.date),
        "collection": COLLECTION,
        "event_count": len(stored),
        "event_cap": MAX_EVENTS,
        "events_by_kind": dict(sorted(by_kind.items())),
        "events": stored,
        "read_back_count": sum(1 for s in stored if s["read_back"]),
        "read_back_rule": (
            "a /store success body is not evidence; an event counts only when a "
            "subsequent /recall over the day scope returns its key"
        ),
        "notes": notes,
        "failed_gates": failed,
        "claims": {
            "proves": ([
                "the day's events are stored under a day-specific scope and are "
                "retrievable by the same recall path the dream uses",
            ] if not failed and not args.dry_run else []),
            "does_not_prove": [
                "that the resulting dream is better, only that it can differ",
                "that the first-person stances are accurate about the day",
            ],
        },
    }
    out = Path(args.out) if args.out else Path(args.out_dir) / f"DAY_INGEST_{args.date}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    receipt["receipt_path"] = rel(out)
    return receipt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--persona", default="embry")
    ap.add_argument("--repo", default=str(REPO_ROOT))
    ap.add_argument("--from-commits", action="store_true")
    ap.add_argument("--project-state", action="append", default=[])
    ap.add_argument("--affect", action="append", default=[])
    ap.add_argument("--event", action="append", default=[])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out-dir", default="/tmp/pd-days")
    ap.add_argument("--out")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    r = run(args)
    print(json.dumps(r, indent=2, sort_keys=True) if args.json else
          f"{r['status']}  date={r['date']}  events={r.get('event_count')}  "
          f"read_back={r.get('read_back_count')}  scope={r['scope']}")
    return 0 if r["status"].startswith(("PASS_", "DRY_RUN")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
