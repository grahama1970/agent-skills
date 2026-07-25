from embry_voice_control.unix_listener import wake_phrase_detected


def test_wake_phrase_detected_supports_observed_kmb_initialism() -> None:
    assert wake_phrase_detected("K.M.B. What is the capital of France?")
    assert wake_phrase_detected("Hey Embry, open review queue.")
    assert not wake_phrase_detected("Embryless background words.")
