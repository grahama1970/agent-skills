"""The morning interview: turn a digest into recorded human decisions.

The nightly delivered a digest for weeks and never learned anything back: no
record of why an opportunity was skipped, no confirmation of an identity match,
no way to tell a reviewed digest from an ignored one. The external review named
this the single largest broken capability - ranking cannot improve without
outcomes, and RUN_DELIVERED_UNREVIEWED cannot be detected without dispositions.

This composes the /interview skill over the latest run's digest:

1. Build a questions.json from the digest: one disposition question per top
   opportunity, one per strong-or-ambiguous LinkedIn identity candidate, and one
   per Meetup event worth attending.
2. Run /interview (HTML or TUI - the human's choice of surface).
3. Write every answer through the EXISTING append-only decision ledger
   (decisions.append_decision), so replay, idempotency, and the report
   projection all keep working unchanged.
4. Confirmed LinkedIn identities are stored to /memory contact_snapshots via
   the same daemon monitor-contacts uses, so a confirmed match becomes a
   durable contact instead of a one-morning answer.

Skipping the interview is always allowed; unanswered items simply stay
undispositioned, and the receipt says so rather than pretending review happened.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from loguru import logger

from .decisions import append_decision
from .util import read_json, utc_now, write_json

INTERVIEW_RUN = Path(__file__).resolve().parents[3] / "interview" / "run.sh"
MEMORY_URL_DEFAULT = "http://127.0.0.1:8601"

DISPOSITION_OPTIONS = [
    {"label": "Pursue", "description": "Prepare the application/outreach package for this one."},
    {"label": "Skip - not interested", "description": "Wrong role, company, or direction."},
    {"label": "Skip - not qualified enough", "description": "Requirements outweigh the claim corpus today."},
    {"label": "Defer", "description": "Keep it visible; not this week."},
]
DISPOSITION_ACTION = {
    "Pursue": "KEEP",
    "Skip - not interested": "REJECT",
    "Skip - not qualified enough": "REJECT",
    "Defer": "DEFER",
}


def build_questions(run_dir: Path, *, max_opportunities: int = 8, max_identities: int = 5) -> dict[str, Any]:
    """A questions.json for /interview, generated from one run's artifacts."""

    digest = read_json(run_dir / "morning-digest.json")
    questions: list[dict[str, Any]] = []

    for row in (digest.get("top") or [])[:max_opportunities]:
        opp_id = str(row.get("opportunity_id") or row.get("candidate_id") or "")
        if not opp_id:
            continue
        questions.append(
            {
                "id": f"disposition::{opp_id}",
                "header": str(row.get("organization") or "?")[:12],
                "text": f"{row.get('title')} — {row.get('organization')}. Disposition?",
                "options": DISPOSITION_OPTIONS,
                "multi_select": False,
            }
        )

    identity_count = 0
    prospect_queue = {}
    pq_path = run_dir / "prospect-queue.json"
    if pq_path.exists():
        prospect_queue = read_json(pq_path)
    for prospect in prospect_queue.get("prospects") or []:
        if identity_count >= max_identities:
            break
        candidates = prospect.get("linkedin_candidates") or []
        subject = str(prospect.get("subject") or "")
        if not candidates or not subject:
            continue
        identity_count += 1
        options = [
            {
                "label": str(c.get("profile_url") or "")[:80],
                "description": f"{c.get('confidence')}: {str(c.get('headline') or '')[:90]}",
            }
            for c in candidates[:3]
        ]
        options.append({"label": "None of these", "description": "No listed profile is this person."})
        questions.append(
            {
                "id": f"identity::{prospect.get('relationship_signal_id')}::{subject}",
                "header": subject.split(" ")[0][:12],
                "text": (
                    f"Is one of these {subject}? Met via {prospect.get('organization')}"
                    f" ({str(prospect.get('event_title') or '')[:60]})."
                ),
                "options": options,
                "multi_select": False,
            }
        )

    return {
        "title": "Morning opportunities",
        "context": f"Run {run_dir.name}: dispositions feed ranking; confirmed identities become durable contacts.",
        "questions": questions,
    }


def _store_confirmed_identity(subject: str, profile_url: str, signal_id: str, memory_url: str) -> bool:
    """Write a human-confirmed identity into contact_snapshots, read-back proven."""

    import hashlib
    import urllib.request

    key = "c-" + hashlib.sha256(" ".join(subject.lower().split()).encode()).hexdigest()[:16]
    doc = {
        "_key": key,
        "name": subject,
        "profile": profile_url,
        "source": "meetup_identity_confirmed_by_human",
        "relationship_signal_id": signal_id,
        "confirmed_at": utc_now(),
    }
    body = json.dumps({"collection": "contact_snapshots", "document": doc}).encode()
    try:
        req = urllib.request.Request(f"{memory_url}/store", data=body, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=15)
        check = json.dumps({"collection": "contact_snapshots", "keys": [key]}).encode()
        req = urllib.request.Request(f"{memory_url}/recall/by-keys", data=check, headers={"Content-Type": "application/json"})
        back = json.loads(urllib.request.urlopen(req, timeout=15).read().decode())
        return bool(back.get("documents"))
    except Exception as exc:  # noqa: BLE001 - a memory outage must not lose the ledger write
        logger.warning("contact store failed for {}: {}", subject, exc)
        return False


def apply_answers(run_dir: Path, answers: dict[str, str], *, memory_url: str = MEMORY_URL_DEFAULT) -> dict[str, Any]:
    """Write interview answers through the existing decision ledger."""

    dispositions = 0
    identities_confirmed = 0
    identities_rejected = 0
    errors: list[str] = []
    for qid, answer in answers.items():
        try:
            if qid.startswith("disposition::"):
                item_id = qid.split("::", 1)[1]
                action = DISPOSITION_ACTION.get(answer.split(" (")[0], None)
                if action is None:
                    continue
                append_decision(
                    run_dir=run_dir, item_id=item_id, action=action, actor="human",
                    idempotency_key=f"morning-interview:{run_dir.name}:{qid}",
                    reason=f"morning interview: {answer}",
                )
                dispositions += 1
            elif qid.startswith("identity::"):
                _, signal_id, subject = qid.split("::", 2)
                if answer.startswith("None of these"):
                    identities_rejected += 1
                    continue
                if _store_confirmed_identity(subject, answer, signal_id, memory_url):
                    identities_confirmed += 1
                else:
                    errors.append(f"contact store unproven for {subject}")
        except Exception as exc:  # noqa: BLE001 - one bad answer must not lose the rest
            errors.append(f"{qid}: {exc}")
    receipt = {
        "schema": "monitor_opportunities.morning_interview_receipt.v1",
        "run": run_dir.name,
        "answered": len(answers),
        "dispositions_recorded": dispositions,
        "identities_confirmed": identities_confirmed,
        "identities_rejected": identities_rejected,
        "errors": errors,
        "reviewed_at": utc_now(),
        "external_effects": False,
    }
    write_json(run_dir / "morning-interview-receipt.json", receipt)
    return receipt


def run_interview(run_dir: Path, *, mode: str = "auto", timeout: int = 900) -> dict[str, Any]:
    """Build questions, run /interview, apply answers. The full loop."""

    questions = build_questions(run_dir)
    if not questions["questions"]:
        return {"schema": "monitor_opportunities.morning_interview_receipt.v1", "run": run_dir.name,
                "answered": 0, "note": "digest had nothing to ask about"}
    qpath = run_dir / "morning-interview-questions.json"
    write_json(qpath, questions)
    proc = subprocess.run(
        ["bash", str(INTERVIEW_RUN), "--file", str(qpath), "--mode", mode, "--timeout", str(timeout), "--json"],
        capture_output=True, text=True, timeout=timeout + 60,
    )
    start = proc.stdout.find("{")
    if proc.returncode != 0 or start < 0:
        raise RuntimeError(f"interview did not complete: {proc.stderr[:300] or proc.stdout[:300]}")
    payload = json.loads(proc.stdout[start:])
    answers = payload.get("answers") or payload.get("responses") or {}
    if isinstance(answers, list):
        answers = {a.get("id"): a.get("answer") for a in answers if isinstance(a, dict)}
    return apply_answers(run_dir, {str(k): str(v) for k, v in answers.items() if v})
