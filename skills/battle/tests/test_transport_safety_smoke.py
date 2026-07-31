from battle_skill.transport_safety_smoke import _parse_vitest_summary, _receipt_errors


def test_parse_vitest_summary_counts_passed_files_and_tests() -> None:
    summary = _parse_vitest_summary(
        """
 Test Files  3 passed (3)
      Tests  14 passed (14)
"""
    )

    assert summary == {
        "test_files_passed": 3,
        "test_files_total": 3,
        "tests_passed": 14,
        "tests_total": 14,
    }


def test_transport_safety_receipt_gate_requires_closed_bad_resume_statuses() -> None:
    frontend = {
        "returncode": 0,
        "tests_passed": 14,
        "tests_total": 14,
    }
    errors = _receipt_errors(
        health={"status": "PASS"},
        event_count=4,
        resume_events=[{"seq": 3}, {"seq": 4}],
        bad_resume_statuses={
            "future_last_event_id": 400,
            "non_integer_last_event_id": 400,
            "negative_last_event_id": 400,
        },
        frontend=frontend,
    )
    assert errors == []

    errors = _receipt_errors(
        health={"status": "PASS"},
        event_count=4,
        resume_events=[{"seq": 2}, {"seq": 3}, {"seq": 4}],
        bad_resume_statuses={
            "future_last_event_id": 400,
            "non_integer_last_event_id": 200,
            "negative_last_event_id": 400,
        },
        frontend=frontend,
    )
    assert errors == [
        "resume-after-2 returned unexpected event count",
        "resume-after-2 replayed already acknowledged events",
        "non_integer_last_event_id did not fail closed with HTTP 400",
    ]
