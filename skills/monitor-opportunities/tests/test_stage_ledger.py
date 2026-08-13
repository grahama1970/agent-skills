"""Stage conservation: no discovered record may vanish without a disposition."""
from __future__ import annotations

from monitor_opportunities.stage_ledger import build_ledger


def _c(cid: str, lane: str = "A") -> dict[str, object]:
    return {"candidate_id": cid, "lane": lane}


def test_full_accounting_passes() -> None:
    discovered = [_c("a"), _c("b"), _c("c")]
    ok, ledger = build_ledger(
        discovered, [_c("a")], [_c("b")], {"c": "a"}
    )
    assert ok, ledger["violations"]
    assert ledger["counts"] == {
        "discovered": 3,
        "accepted": 1,
        "rejected": 1,
        "deduplicated": 1,
        "eligible_not_shortlisted": 0,
        "unaccounted": 0,
    }


def test_eligible_rows_below_shortlist_limit_are_accounted() -> None:
    ok, ledger = build_ledger([_c("a"), _c("b")], [_c("a")], [], {}, admitted_count=2)
    assert ok, ledger["violations"]
    assert ledger["counts"]["eligible_not_shortlisted"] == 1
    assert ledger["counts"]["unaccounted"] == 0


def test_silently_lost_record_is_a_violation() -> None:
    # The defect: a record discovered, then gone, with every receipt still green.
    ok, ledger = build_ledger([_c("a"), _c("ghost")], [_c("a")], [], {})
    assert not ok
    assert any(v["rule"] == "no-silent-loss" for v in ledger["violations"])
    assert ledger["counts"]["unaccounted"] == 1


def test_record_in_two_buckets_is_a_violation() -> None:
    ok, ledger = build_ledger([_c("a")], [_c("a")], [_c("a")], {})
    assert not ok
    assert any(v["rule"] == "single-disposition" for v in ledger["violations"])


def test_dedupe_must_name_a_surviving_canonical() -> None:
    # "deduplicated" is only auditable if the canonical record actually exists.
    ok, ledger = build_ledger([_c("a"), _c("b")], [_c("a")], [], {"b": "nonexistent"})
    assert not ok
    assert any(v["rule"] == "dedupe-names-canonical" for v in ledger["violations"])


def test_lane_claiming_matches_must_emit_records() -> None:
    # DARPA reported MATCHES off a landing page while emitting nothing usable.
    receipts = [{"lane": "B", "result_status": "MATCHES"}]
    ok, ledger = build_ledger([_c("a", lane="A")], [_c("a")], [], {}, source_receipts=receipts)
    assert not ok
    assert any(v["rule"] == "claim-implies-emit" for v in ledger["violations"])
    assert ledger["lane_claims"]["B"]["emitted"] == 0


def test_lane_claiming_matches_and_emitting_passes() -> None:
    receipts = [{"lane": "A", "result_status": "MATCHES"}]
    ok, ledger = build_ledger([_c("a")], [_c("a")], [], {}, source_receipts=receipts)
    assert ok
    assert ledger["lane_claims"]["A"]["emitted"] == 1


def test_lane_reporting_no_matches_need_not_emit() -> None:
    receipts = [{"lane": "C", "result_status": "NO_MATCHES"}]
    ok, _ = build_ledger([_c("a")], [_c("a")], [], {}, source_receipts=receipts)
    assert ok
