"""Tests for live Chatterbox session-mood receipt hardening."""
import hashlib
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


live_mod = _load("session_mood_chatterbox_live")


def _response(audio_path: Path) -> dict:
    digest = hashlib.sha256(audio_path.read_bytes()).hexdigest()
    return {
        "engine": "chatterbox_base",
        "requested_tone": "firm_boundary",
        "normalized_tone": "firm_boundary",
        "voice_delivery": {"tone_was_normalized": False},
        "emotion_knobs": {"exaggeration": 0.9, "cfg_weight": 0.45},
        "finished_response_audio": str(audio_path),
        "finished_response_metrics": {
            "sha256": digest,
            "duration_seconds": 1.0,
        },
        "chunks": [
            {
                "asr_verification": {
                    "accepted_gate": {"ok": True, "wer": 0.0},
                    "candidates": [
                        {"asr": {"transcript": "The answer is unchanged.",
                                 "gate": {"ok": True, "wer": 0.0}}}
                    ],
                }
            }
        ],
    }


def test_render_turn_snapshots_finished_audio(monkeypatch, tmp_path):
    source_audio = tmp_path / "source.wav"
    source_audio.write_bytes(b"RIFF" + b"\0" * 64)
    expected_sha = hashlib.sha256(source_audio.read_bytes()).hexdigest()

    seen = {}
    def fake_post_json(_url, payload):
        seen.update(payload)
        return _response(source_audio)
    monkeypatch.setattr(live_mod, "post_json", fake_post_json)

    got = live_mod.render_turn(
        {
            "turn_id": "turn_001",
            "answer_text": "The answer is unchanged.",
            "voice_delivery": {"required_engine": "chatterbox_base"},
        },
        label="unit",
        out_dir=tmp_path,
    )

    snapshot = tmp_path / "turn_001_finished_response.wav"
    assert snapshot.read_bytes() == source_audio.read_bytes()
    assert got["audio_snapshot_status"] == "PASS_AUDIO_SNAPSHOT_DURABLE"
    assert got["finished_response_audio_source"] == str(source_audio)
    assert got["finished_response_audio_resolved_source"] == str(source_audio)
    assert got["finished_response_audio_snapshot"] == str(snapshot)
    assert got["finished_response_audio_snapshot_sha256"] == "sha256:" + expected_sha
    assert seen["asr_max_wer"] == 0.0
    assert seen["asr_max_candidates"] == 3


def test_out_path_maps_to_host_log_root(monkeypatch, tmp_path):
    host_root = tmp_path / "logs"
    source_audio = host_root / "batch" / "finished_response.wav"
    source_audio.parent.mkdir(parents=True)
    source_audio.write_bytes(b"RIFF" + b"mapped")
    monkeypatch.setattr(live_mod, "CHATTERBOX_OUT_HOST_ROOT", host_root)

    assert live_mod.resolve_audio_path("/out/batch/finished_response.wav") == source_audio


def test_missing_finished_audio_blocks(monkeypatch, tmp_path):
    missing = tmp_path / "missing.wav"
    response = {
        "engine": "chatterbox_base",
        "finished_response_audio": str(missing),
        "chunks": [
            {
                "asr_verification": {
                    "accepted_gate": {"ok": True},
                    "candidates": [
                        {"asr": {"transcript": "The answer is unchanged.",
                                 "gate": {"ok": True, "wer": 0.0}}}
                    ],
                }
            }
        ],
    }
    monkeypatch.setattr(live_mod, "post_json", lambda _url, _payload: response)

    with pytest.raises(RuntimeError, match="BLOCKED_CHATTERBOX_AUDIO_ARTIFACT_MISSING"):
        live_mod.render_turn(
            {
                "turn_id": "turn_001",
                "answer_text": "The answer is unchanged.",
                "voice_delivery": {"required_engine": "chatterbox_base"},
            },
            label="unit",
            out_dir=tmp_path,
        )


def test_asr_text_drift_blocks(monkeypatch, tmp_path):
    source_audio = tmp_path / "source.wav"
    source_audio.write_bytes(b"RIFF" + b"\0" * 64)
    response = _response(source_audio)
    response["chunks"][0]["asr_verification"]["candidates"][0]["asr"]["transcript"] = (
        "The answer is unchanged. Bye!"
    )
    monkeypatch.setattr(live_mod, "post_json", lambda _url, _payload: response)

    with pytest.raises(RuntimeError, match="BLOCKED_CHATTERBOX_ASR_TEXT_DRIFT"):
        live_mod.render_turn(
            {
                "turn_id": "turn_001",
                "answer_text": "The answer is unchanged.",
                "voice_delivery": {"required_engine": "chatterbox_base"},
            },
            label="unit",
            out_dir=tmp_path,
        )
