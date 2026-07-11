from embry_voice_control.pipewire_playback import authority_identity


def test_authority_is_deterministic_and_sink_bound():
    args = dict(session_id="s", turn_id="t", render_event_id="r", artifact_id="a", audio_sha256="h")
    first = authority_identity(**args, sink_node_name="jabra")
    assert first == authority_identity(**args, sink_node_name="jabra")
    assert first != authority_identity(**args, sink_node_name="other")
    assert first["stream_node_name"].startswith("embry.playback.")


def test_run_normalizes_prefixed_audio_hash(monkeypatch, tmp_path):
    import embry_voice_control.pipewire_playback as playback

    captured = {}
    response = type("Response", (), {"json": lambda self: {"db_path": str(tmp_path / "journal.db")}})()
    monkeypatch.setattr(playback.httpx, "get", lambda *args, **kwargs: response)

    def stop_after_capture(*args, **kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop")

    monkeypatch.setattr(playback, "resolve_audio_artifact", stop_after_capture)
    try:
        playback.run_playback(
            journal_db=tmp_path / "journal.db", journal_url="http://journal",
            session_id="s", turn_id="t", source_event_id="source", source_sequence=1,
            tau_plan_event_id="plan", render_event_id="render", tau_plan_sha256="sha256:plan",
            tts_text_sha256="sha256:text", audio_sha256="sha256:abc", audio_bytes=100,
            sink_node_name="sink", expected_current_node_id=1, expected_sink_description="sink",
            expected_sink_volume=0.7, sink_volume_tolerance=0.02, output_dir=tmp_path / "out",
        )
    except RuntimeError as error:
        assert str(error) == "stop"
    assert captured["audio_sha256"] == "abc"
    assert captured["artifact_id"] == "audio:abc"
