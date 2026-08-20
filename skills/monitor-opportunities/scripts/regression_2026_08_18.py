"""Regression guards for the failure signatures of 2026-08-17/18/20.

Each check reproduces a failure that actually happened and exercises the REAL
production code path that fixed it — the same discipline as
regression_2026_08_13.py. Unit tests written alongside the fixes proved too
weak: every one of these defects shipped while 400+ tests were green.

Signatures covered:
1. EDGE_EVIDENCE   - a relationship edge cited a URL its receipts never recorded
                     and killed the 02:00 nightly (RELATIONSHIP_EDGE_EVIDENCE_REF_UNRESOLVED).
2. FIXTURE_AGING   - the committed discovery fixture aged past the recency gate,
                     fixture runs shortlisted zero, 17 tests failed for the wrong reason.
3. RETENTION       - every run overwrote local/nightly/latest, destroying history.
4. MEETUP_BUDGET   - attendee capture blew a flat 120s budget and zeroed the lane
                     (meetup_isolated_capture_timeout) while the run reported PASS.
5. NAME_GUARD      - an attendee listed as "R" burned a live search and resolved
                     to strangers wearing a confidence label.
6. QUEUE_PROJECTION- the prospect queue dropped every linkedin_* field, so the
                     receipt counted 3 strong candidates the queue never carried.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str) -> None:
    print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}")
    if not ok:
        FAILURES.append(name)


def edge_evidence() -> None:
    from monitor_opportunities.contact_changes import relationship_signals_from_meetup_attendees

    evidence = {
        "groups": [
            {
                "url": "https://www.meetup.com/example-group/",
                "name": "Example Group",
                "location": "Buffalo, NY",
                "attendees": [
                    {
                        "name": "Ada Example",
                        "role": "Host",
                        "profile_url": "https://www.meetup.com/example-group/members/1/",
                        "event_url": "https://www.meetup.com/example-group/events/123/",
                        "event_title": "Example Event",
                    }
                ],
            }
        ]
    }
    signals = relationship_signals_from_meetup_attendees(evidence)
    edges = [edge for signal in signals for edge in signal["contact_path"]]
    signal_refs = {ref for signal in signals for ref in signal["evidence_refs"]}
    leaked = [
        ref
        for edge in edges
        for ref in edge.get("evidence_refs", [])
        if ref not in signal_refs
    ]
    check(
        "EDGE_EVIDENCE",
        bool(signals) and not leaked,
        f"{len(signals)} signal(s); every edge ref is signal-backed"
        if not leaked
        else f"edges cite refs outside the signal: {leaked}",
    )


def fixture_aging() -> None:
    import json

    from monitor_opportunities.discovery import shift_fixture_dates
    from monitor_opportunities.ranking import rank

    skill = Path(__file__).resolve().parents[1]
    fixture = json.loads((skill / "tests" / "fixtures" / "discovery" / "discovery-run.json").read_text())
    rows = fixture["candidates"]
    shift_fixture_dates(rows)
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "discovery"
        run_dir.mkdir()
        fixture["candidates"] = rows
        (run_dir / "discovery-run.json").write_text(json.dumps(fixture))
        (run_dir / "candidates.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
        out = Path(tmp) / "rank"
        rank(run_dir, 8, out)
        shortlisted = json.loads((out / "shortlist.json").read_text())
    check(
        "FIXTURE_AGING",
        len(shortlisted) > 0,
        f"re-dated fixture shortlists {len(shortlisted)} (zero means the fixture aged out again)",
    )


def retention() -> None:
    import monitor_opportunities.cli as cli

    with tempfile.TemporaryDirectory() as tmp:
        skill_dir = Path(tmp) / "skills" / "monitor-opportunities"
        first = cli._new_nightly_run_dir(skill_dir)
        second = cli._new_nightly_run_dir(skill_dir)
        link = skill_dir / "local" / "nightly" / "latest"
        ok = first.exists() and second.exists() and link.is_symlink()
        check(
            "RETENTION",
            ok,
            "two runs -> two dated dirs plus a latest symlink"
            if ok
            else f"first={first.exists()} second={second.exists()} symlink={link.is_symlink()}",
        )


def meetup_budget() -> None:
    import inspect

    from monitor_opportunities import browser_capture

    source = inspect.getsource(browser_capture.capture_meetup_buffalo_isolated)
    scales = "events_per_group" in source and "max_group_pages * 12" in source
    env = os.environ.pop("MONITOR_MEETUP_CAPTURE_TIMEOUT_SECONDS", None)
    try:
        # 8 groups x 2 events must default well above the flat 120s that zeroed the lane.
        estimated = max(180, 60 + 8 * 12 * (1 + 2))
        check(
            "MEETUP_BUDGET",
            scales and estimated >= 300,
            f"default budget for 8 groups x 2 events is {estimated}s (was a flat 120s)",
        )
    finally:
        if env is not None:
            os.environ["MONITOR_MEETUP_CAPTURE_TIMEOUT_SECONDS"] = env


def name_guard() -> None:
    from monitor_opportunities.linkedin_leads import _is_resolvable_name

    junk = ["R", "Kathy", "J.", "x y" ]
    real = ["Matthew Gracie", "Cathy Stearns"]
    wrong = [n for n in junk if _is_resolvable_name(n)] + [n for n in real if not _is_resolvable_name(n)]
    check(
        "NAME_GUARD",
        not wrong,
        "junk names skipped, full names resolvable" if not wrong else f"misclassified: {wrong}",
    )


def queue_projection() -> None:
    from monitor_opportunities.prospect_queue import relationship_prospects

    signal = {
        "signal_id": "rel-test",
        "subject": "Ada Example",
        "organization": "Example Group",
        "signal_type": "event_copresence",
        "relationship_path": ["Graham Anderson", "Example Group", "Ada Example"],
        "evidence_refs": ["https://www.meetup.com/example-group/events/123/"],
        "linkedin_top_candidate": "https://www.linkedin.com/in/ada-example/",
        "linkedin_candidates": [{"profile_url": "https://www.linkedin.com/in/ada-example/", "confidence": "strong"}],
        "linkedin_confirmation_required": True,
    }
    rows = relationship_prospects([signal])
    row = rows[0] if rows else {}
    ok = row.get("linkedin_top_candidate") == signal["linkedin_top_candidate"] and row.get("subject") == "Ada Example"
    check(
        "QUEUE_PROJECTION",
        ok,
        "queue rows carry the resolved LinkedIn candidate" if ok else f"projection dropped fields: {sorted(row)}",
    )


def location_blackhole() -> None:
    """172 candidates/night died in HUMAN_REVIEW_LOCATION_AMBIGUOUS unseen (2026-08-20)."""

    from monitor_opportunities.discovery import _workplace_type
    from monitor_opportunities.ranking import _eligibility

    cases = [
        ("United States", "we are a fully remote company", "REMOTE"),
        ("New York Office", "In-Person 5 days a week in our NYC office", "ONSITE_ELSEWHERE"),
        ("United States", "join our mission", "AMBIGUOUS"),
    ]
    wrong = [(l, _workplace_type(l, b)) for l, b, want in cases if _workplace_type(l, b) != want]
    state, _ = _eligibility({"lane": "A", "title": "AI Engineer", "workplace_type": "ONSITE_ELSEWHERE"})
    reject_named = state == "REJECT_RELOCATION_REQUIRED"
    # The remaining ambiguous rows must be surfaced, not buried.
    from monitor_opportunities import morning_interview
    import inspect
    surfaced = "HUMAN_REVIEW_LOCATION_AMBIGUOUS" in inspect.getsource(morning_interview.build_questions)
    check(
        "LOCATION_BLACKHOLE",
        not wrong and reject_named and surfaced,
        "body-aware inference, named on-site rejection, ambiguous rows surfaced in the interview"
        if not wrong and reject_named and surfaced
        else f"wrong={wrong} reject_named={reject_named} surfaced={surfaced}",
    )


def identity_floor() -> None:
    """Context similarity assigned the WRONG PERSON's profile as strong (2026-08-20).

    Deterministic half of the guard: candidates whose title/slug lack the
    subject's name must be discarded no matter how well context terms match.
    Exercises the real filter with a synthetic search result set.
    """

    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ops-linkedin" / "src"))
    from unittest.mock import patch
    import ops_linkedin.lead_resolver as lr

    fake = [
        {"url": "https://www.linkedin.com/in/arlette-verploegh-1/", "title": "Arlette Verploegh - Founder Institute",
         "description": "works with Jonathan Greechan on startup founder programs"},
        {"url": "https://www.linkedin.com/in/jonathangreechan/", "title": "Jonathan Greechan - Co-Founder, Founder Institute",
         "description": "startup founder programs"},
    ]
    with patch.object(lr, "search_profiles", return_value=(fake, "q")):
        r = lr.resolve_candidates("Jonathan Greechan", context="startup founder institute", location="")
    urls = [c["profile_url"] for c in r["candidates"]]
    ok = urls == ["https://www.linkedin.com/in/jonathangreechan/"]
    check(
        "IDENTITY_FLOOR",
        ok,
        "wrong-person profile discarded despite matching context terms" if ok else f"candidates={urls}",
    )


def queue_dedupe() -> None:
    """Duplicate relationship signals doubled queue rows (2026-08-20)."""

    from monitor_opportunities.prospect_queue import relationship_prospects

    signal = {"signal_id": "rel-dup", "subject": "Ada Example", "organization": "G",
              "signal_type": "event_copresence", "relationship_path": ["Graham Anderson", "G", "Ada Example"],
              "evidence_refs": ["https://example.com/e"]}
    rows = relationship_prospects([signal, dict(signal)])
    check("QUEUE_DEDUPE", len(rows) == 1, f"{len(rows)} row(s) from a duplicated signal (want 1)")


def requirement_extraction() -> None:
    """Real postings extracted ZERO requirements (2026-08-20): every top opportunity
    showed requirements=0, so 'pursue' tailored a resume against nothing.

    Two causes: (1) <strong> inside <li> was treated as a heading and stopped item
    capture - Ashby/Greenhouse/Lever all bold the bullet lead-in; (2) posting_text
    truncated at 4000 chars cut requirement lists off the end of long postings.
    """

    from monitor_opportunities.qualification_match import extract_requirements

    nested = ('<h2>What We\'re Looking For</h2><ul style="min-height:1.5em">'
              '<li><p style="x"><strong>Systems-First:</strong> reliable distributed systems in Python.</p></li>'
              '<li><p>Deep experience with OCR and document extraction at scale.</p></li></ul>')
    reqs = extract_requirements(nested)
    check(
        "REQUIREMENT_EXTRACTION",
        len(reqs) == 2,
        f"nested <li><p><strong> bullets extract {len(reqs)} requirement(s) (want 2)",
    )


def posting_text_cap() -> None:
    import inspect

    from monitor_opportunities import discovery

    src = inspect.getsource(discovery)
    check(
        "POSTING_TEXT_CAP",
        "[:4000]" not in src and "[:14000]" in src,
        "posting_text captured at 14000 chars so requirement lists survive"
        if "[:4000]" not in src
        else "posting_text still truncated at 4000; requirements at the end of long postings are lost",
    )


def main() -> int:
    for fn in (edge_evidence, fixture_aging, retention, meetup_budget, name_guard, queue_projection, location_blackhole, identity_floor, queue_dedupe, requirement_extraction, posting_text_cap):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - a crashed check is a failed check
            check(fn.__name__.upper(), False, f"raised {type(exc).__name__}: {exc}")
    if FAILURES:
        print(f"REGRESSION_2026_08_18 FAIL: {FAILURES}")
        return 1
    print("REGRESSION_2026_08_18 OK: all 11 failure signatures guarded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
