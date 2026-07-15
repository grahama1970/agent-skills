from embry_voice_control.embry_chat import (
    build_tau_response_plan,
    chunk_tone_arc,
    normalize_tts_text,
    split_speakable_text,
    split_speakable_with_emotion_close,
)


def test_grounded_compliance_memory_answer_is_used() -> None:
    plan = build_tau_response_plan(
        turn_text="What evidence should a SPARTA QRA include?",
        intent_result={"action": "COMPLIANCE"},
        answer_result={"can_answer": True, "final_response": "Use source-grounded, verified evidence."},
    )

    assert plan["route_taken"] == "memory_answer"
    assert plan["route_reason"] == "compliance_grounded_memory_answer"
    assert plan["tts_render_text"] == (
        "Use source-grounded, verified evidence. "
        "[happy]"
    )


def test_compliance_memory_miss_remains_fail_closed() -> None:
    plan = build_tau_response_plan(
        turn_text="What evidence should a SPARTA QRA include?",
        intent_result={"action": "COMPLIANCE"},
        answer_result={"can_answer": False, "answer_type": "insufficient_memory_evidence"},
    )

    assert plan["route_taken"] == "fail_closed"
    assert plan["route_reason"] == "memory_intent_action_compliance"


def test_speakable_text_is_split_without_losing_words() -> None:
    text = " ".join(["grounded"] * 60)
    chunks = split_speakable_text(text, max_chars=80)

    assert " ".join(chunks) == text
    assert len(chunks) > 1
    assert all(len(chunk) <= 80 for chunk in chunks)


def test_long_answer_uses_concerned_confident_happy_arc() -> None:
    chunks = split_speakable_text(" ".join(["grounded"] * 60), max_chars=180)
    tones = chunk_tone_arc(len(chunks))

    assert len(chunks) >= 3
    assert tones[0] == "careful_concerned"
    assert set(tones[1:-1]) == {"memory_confident"}
    assert tones[-1] == "playful_light"


def test_tts_expands_domain_acronyms_without_changing_display_answer() -> None:
    answer = "A SPARTA QRA must pass rapidfuzz token_set_ratio >= 0.6."
    spoken = normalize_tts_text(answer)

    assert "SPARTA" not in spoken
    assert "QRA" not in spoken
    assert "Space Attack Research and Tactic Analysis" in spoken
    assert "question, reasoning, and answer" in spoken
    assert "at least zero point six" in spoken


def test_emotion_close_remains_in_final_chunk() -> None:
    text = ("grounded evidence " * 30).strip() + " [happy]"
    chunks = split_speakable_with_emotion_close(text, max_chars=180)

    assert chunks[-1] == "[happy]"
    assert all(len(chunk) <= 180 for chunk in chunks)
