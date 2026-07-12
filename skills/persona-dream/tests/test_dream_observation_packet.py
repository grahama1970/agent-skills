from pathlib import Path
import importlib.util
import json


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


module = load_module("write_dream_observation_packet", ROOT / "scripts/write_dream_observation_packet.py")


def test_fixture_packet_preserves_missing_visual_evidence(tmp_path: Path, monkeypatch):
    watch_root = tmp_path / "watch"
    watch_root.mkdir()
    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"frame")
    video = tmp_path / "fixture.mp4"
    video.write_bytes(b"video")
    (watch_root / "frames_manifest.json").write_text(json.dumps({"frames": [{"path": str(frame)}]}))
    (watch_root / "transcript.json").write_text(json.dumps({"segments": [{"text": "Kai waits.", "start": 0, "duration": 1}]}))
    (watch_root / "report.json").write_text(json.dumps({"visual_descriptions": [], "scene_elements": []}))
    monkeypatch.setattr(module, "video_duration", lambda _path: 10.0)
    packet = module.build_packet(watch_root, video, "dream-1", "rev-1", "fixture_video")
    assert module.validate_packet(packet) == []
    assert packet["status"] == "PASS_DREAM_OBSERVATION_CONTRACT_FIXTURE"
    assert packet["provider_returned"] is False
    assert packet["persona_watched_provider_dream"] is False
    assert packet["visual_facts"] == []
    assert "visual_descriptions_missing" in packet["coverage_gaps"]
    assert packet["psychological_interpretation_performed"] is False
