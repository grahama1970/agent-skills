"""Stage conservation: no discovered record may vanish without a disposition."""
from __future__ import annotations

from monitor_opportunities.ranking import dedupe_postings
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


def test_dedupe_rewrites_all_aliases_to_final_canonical_survivor() -> None:
    base = {
        "lane": "A",
        "title": "Principal AI Architect",
        "workplace_type": "REMOTE",
        "fit_score": 0.9,
    }
    rows = [
        {**base, "candidate_id": "old", "organization": "Galois Inc."},
        {**base, "candidate_id": "middle", "organization": "Galois LLC", "posting_url": "https://jobs.example/galois"},
        {
            **base,
            "candidate_id": "final",
            "organization": "Galois",
            "posting_url": "https://boards.example/jobs/view/123",
            "apply_url": "https://boards.example/jobs/view/123/apply",
        },
    ]

    deduped, dropped, merged_into = dedupe_postings(rows)

    assert dropped == 2
    assert [row["candidate_id"] for row in deduped] == ["final"]
    assert merged_into == {"old": "final", "middle": "final"}

    ok, ledger = build_ledger(rows, deduped, [], merged_into, admitted_count=1)
    assert ok, ledger["violations"]
    assert ledger["counts"]["deduplicated"] == 2


def test_dedupe_uses_explicit_organization_canonical_key() -> None:
    base = {
        "lane": "A",
        "title": "AI Assurance Architect",
        "workplace_type": "REMOTE",
        "fit_score": 0.9,
    }
    rows = [
        {**base, "candidate_id": "ge-old", "organization": "General Electric Aerospace"},
        {
            **base,
            "candidate_id": "ge-final",
            "organization": "GE Aerospace",
            "organization_canonical": "GE Aerospace",
            "posting_url": "https://boards.example/jobs/view/ge",
        },
    ]

    deduped, dropped, merged_into = dedupe_postings(rows)

    assert dropped == 1
    assert [row["candidate_id"] for row in deduped] == ["ge-final"]
    assert merged_into == {"ge-old": "ge-final"}
