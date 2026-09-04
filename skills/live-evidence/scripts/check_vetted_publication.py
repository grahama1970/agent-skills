#!/usr/bin/env python3
"""Fail when a session journal shows visible cards without answer vetting.

Guard for the 2026-09-03 incident: fast solver timed out, fallback-to-ask was
skipped (fast_solver_fallback_ask_skipped), reviewer marked every answer weak,
and unvetted Memory-echo answers were still published as visible/supported.

A visible card publication decision is VETTED only if, for its question_id:
  - a fast_solver_receipt was journaled (solver actually answered), or
  - an ask receipt/dispatch was journaled ($ask tau-dag run directory lane), or
  - the decision itself is explicitly marked degraded/unvetted.

Exit 1 with stable code `unvetted_card_published` when any visible decision
lacks all three. Exit 0 when the journal is clean.
"""
from __future__ import annotations

import json
import sys


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_vetted_publication.py <session.jsonl>", file=sys.stderr)
        return 2
    rows = [json.loads(line) for line in open(sys.argv[1]) if line.strip()]
    solver_ok: set[str] = set()
    ask_ok: set[str] = set()
    for row in rows:
        kind = row.get("kind")
        payload = row.get("payload") or {}
        qid = str(payload.get("question_id") or "")
        if kind == "fast_solver_receipt" and qid:
            solver_ok.add(qid)
        if kind in ("ask_dispatch", "ask_receipt", "ask_solution") and qid:
            ask_ok.add(qid)

    violations = []
    for row in rows:
        if row.get("kind") != "card_publication_decision":
            continue
        payload = row.get("payload") or {}
        if payload.get("status") not in (None, "visible"):
            continue
        if payload.get("degraded") or payload.get("unvetted"):
            continue
        qid = str(payload.get("question_id") or "")
        if qid in solver_ok or qid in ask_ok:
            continue
        violations.append({"question_id": qid, "card_id": payload.get("card_id")})

    if violations:
        print(json.dumps({
            "code": "unvetted_card_published",
            "violations": len(violations),
            "detail": violations[:5],
        }))
        return 1
    print(json.dumps({"code": "ok", "visible_decisions_vetted": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
