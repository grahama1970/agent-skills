"""Tests for session-mood voice-recognition preflight."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


preflight = _load("session_mood_voice_recognition_preflight")


def _write_receipt(tmp_path: Path, *, snapshot_sha: str | None = None) -> Path:
    snapshot = tmp_path / "turn_001_finished_response.wav"
    snapshot.write_bytes(b"RIFF" + b"\0" * 64)
    actual_sha = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    receipt = {
        "render_results": [
            {
                "turn_id": "turn_001",
                "finished_response_audio_snapshot": str(snapshot),
                "finished_response_audio_snapshot_sha256": "sha256:" + (snapshot_sha or actual_sha),
                "asr_gate": {"wer": 0.0},
            }
        ]
    }
    path = tmp_path / "RECEIPT.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    return path


def test_audio_snapshot_validation_passes_for_matching_sha(tmp_path):
    receipt = _write_receipt(tmp_path)

    snapshots, failures = preflight.validate_audio_snapshots(receipt)

    assert failures == []
    assert snapshots[0]["snapshot"]["exists"] is True


def test_audio_snapshot_sha_mismatch_blocks(tmp_path):
    receipt = _write_receipt(tmp_path, snapshot_sha="0" * 64)

    _snapshots, failures = preflight.validate_audio_snapshots(receipt)

    assert "turn_001_audio_snapshot_sha256_matches" in failures


def test_missing_backend_blocks_even_with_valid_audio(monkeypatch, tmp_path):
    live_receipt = _write_receipt(tmp_path)
    reference = tmp_path / "embry_ref.wav"
    reference.write_bytes(b"RIFF" + b"ref")
    monkeypatch.setattr(preflight.importlib.util, "find_spec", lambda _name: None)
    out = tmp_path / "preflight.json"

    args = type("Args", (), {
        "live_receipt": live_receipt,
        "reference_audio": reference,
        "engine": ["resemblyzer", "speechbrain_ecapa"],
        "out": out,
    })()
    got = preflight.run(args)

    assert got["status"] == "BLOCKED_SPEAKER_RECOGNITION_PREFLIGHT"
    assert "speaker_recognition_backend_available" in got["failed_gates"]
    assert out.exists()


def test_available_backend_passes_with_valid_audio(monkeypatch, tmp_path):
    live_receipt = _write_receipt(tmp_path)
    reference = tmp_path / "embry_ref.wav"
    reference.write_bytes(b"RIFF" + b"ref")
    monkeypatch.setattr(preflight.importlib.util, "find_spec", lambda _name: object())
    out = tmp_path / "preflight.json"

    args = type("Args", (), {
        "live_receipt": live_receipt,
        "reference_audio": reference,
        "engine": ["resemblyzer"],
        "out": out,
    })()
    got = preflight.run(args)

    assert got["status"] == "PASS_SPEAKER_RECOGNITION_PREFLIGHT"
    assert got["failed_gates"] == []
