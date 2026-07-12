from embry_voice_control.audio_e2e.event_waiter import managed_fields_match


def test_managed_fields_match_accepts_final_transcript_nested_contract() -> None:
    expected = {
        "campaign_id": "campaign-1", "case_id": "case-1", "attempt_id": "attempt-1",
        "session_id": "session-1", "turn_id": "turn-1", "source_authority_id": "source-1",
    }
    event = {"payload": {"managed_turn": expected}}
    assert managed_fields_match(event, expected)


def test_managed_fields_match_rejects_wrong_turn() -> None:
    expected = {"turn_id": "turn-1"}
    assert not managed_fields_match({"payload": {"managed_turn": {"turn_id": "turn-2"}}}, expected)


def test_managed_fields_match_reads_session_and_turn_from_event_envelope() -> None:
    expected = {
        "campaign_id": "campaign-1", "case_id": "case-1", "attempt_id": "attempt-1",
        "session_id": "session-1", "turn_id": "turn-1", "source_authority_id": "source-1",
    }
    event = {
        "session_id": "session-1",
        "turn_id": "turn-1",
        "payload": {
            "campaign_id": "campaign-1", "case_id": "case-1", "attempt_id": "attempt-1",
            "source_authority_id": "source-1",
        },
    }
    assert managed_fields_match(event, expected)
