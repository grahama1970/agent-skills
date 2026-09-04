#!/usr/bin/env python3
"""Deterministic contract checks for the Threader agent (no model calls).

Asserts the invariants that make bad grouping unrepresentable:
- activation rule: empty ledger -> new_topic with no call;
- hallucinated parent_id rejected;
- non-null parent_id on new_topic rejected;
- topic_title over 6 words rejected;
- valid follow_up with exact ledger id accepted.
Exit 0 with 'threader contract checks PASS' only when all hold.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from live_evidence.threader import QuestionThreader, _validate  # noqa: E402


def main() -> int:
    outcome = QuestionThreader().classify("Implement removeExtraParens in JavaScript", [])
    assert outcome.error is None and outcome.verdict is not None
    assert outcome.verdict.relation == "new_topic", "empty ledger must be new_topic"

    ids = {"q1"}
    verdict, _ = _validate(
        '{"relation":"follow_up","parent_id":"q1","topic_title":"Array Mutation"}', ids
    )
    assert verdict is not None and verdict.parent_id == "q1"

    verdict, detail = _validate(
        '{"relation":"follow_up","parent_id":"hallucinated","topic_title":"X"}', ids
    )
    assert verdict is None and "exact id" in (detail or ""), "hallucinated parent must be rejected"

    verdict, _ = _validate('{"relation":"new_topic","parent_id":"q1","topic_title":"X"}', ids)
    assert verdict is None, "parent_id must be null for new_topic"

    verdict, detail = _validate(
        '{"relation":"new_topic","parent_id":null,'
        '"topic_title":"one two three four five six seven"}',
        ids,
    )
    assert verdict is None and "6 words" in (detail or "")

    print("threader contract checks PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
