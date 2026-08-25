#!/usr/bin/env python3
"""Focused post-run miss-audit proof."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from live_evidence.miss_audit import build_miss_audit


OUT = Path("/tmp/live-evidence-miss-audit-current")


def row(kind: str, payload: dict) -> str:
    return json.dumps({"kind": kind, "payload": payload}, sort_keys=True) + "\n"


def moment(question_id: str, revision: int) -> dict:
    return {
        "schema": "live_evidence.answer_needed_moment.v1",
        "question_id": question_id,
        "question_revision": revision,
        "query": f"question {question_id} revision {revision}",
        "source_event_ids": [f"event-{question_id}-{revision}"],
        "surface_gate": "accepted",
    }


def decision(question_id: str, revision: int, status: str, reason: str) -> dict:
    return {
        "schema": "live_evidence.card_publication_decision.v1",
        "status": status,
        "reason_codes": [reason],
        "card_id": f"card-{question_id}-{revision}",
        "question_id": question_id,
        "question_revision": revision,
        "answer_revision": revision,
        "transcript_refs": [f"question:{question_id}:revision:{revision}"],
        "source_refs": [f"memory:source-{question_id}:project_memory_versions/{question_id}"],
        "rank_components": {"source_count": 1},
        "visible_card_ids": [f"card-{question_id}-{revision}"] if status == "visible" else [],
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="live-evidence-miss-audit-") as temp:
        journal = Path(temp) / "session.jsonl"
        journal.write_text(
            ""
            + row("answer_needed_moment", moment("question-visible", 1))
            + row("card_publication_decision", decision("question-visible", 1, "visible", "visible_current_question_card"))
            + row("answer_needed_moment", moment("question-held", 1))
            + row(
                "requirement_ledger_opened",
                {
                    "question_id": "question-held",
                    "question_revision": 1,
                    "entries": [{"blocking": True, "status": "unresolved"}],
                },
            )
            + row("answer_needed_moment", moment("question-superseded", 1))
            + row(
                "card_publication_decision",
                decision("question-superseded", 1, "superseded", "stale_revision_blocked_by_newer_visible_card"),
            )
            + row("answer_needed_moment", moment("question-missed", 1)),
            encoding="utf-8",
        )
        report = build_miss_audit(journal)
    out_path = OUT / "report.json"
    out_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    expected = {
        "question-visible": "visible",
        "question-held": "held",
        "question-superseded": "superseded",
        "question-missed": "missed",
    }
    actual = {item.question_id: item.disposition for item in report.questions}
    failures = [
        f"{qid}: expected {want}, got {actual.get(qid)}"
        for qid, want in expected.items()
        if actual.get(qid) != want
    ]
    if failures:
        for failure in failures:
            print(f"post-run miss audit: FAIL: {failure}")
        print(f"post-run miss audit report: {out_path}")
        return 1
    print("post-run miss audit classifies visible/held/superseded/missed: PASS")
    print(f"post-run miss audit: PASS -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
