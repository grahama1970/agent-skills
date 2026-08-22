from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/session_mood_voice_recognition.py"


def load_module():
    spec = importlib.util.spec_from_file_location("session_mood_voice_recognition", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def run_with_scores(monkeypatch, tmp_path: Path, *, floor_disputed_score: float):
    module = load_module()
    reference = SCRIPT
    conditioning = SCRIPT
    renders = [tmp_path / "turn_floor_disputed.wav", tmp_path / "turn_clear.wav"]
    adversarial = [tmp_path / "kai.wav", tmp_path / "horus.wav"]
    for path in renders + adversarial:
        path.write_bytes(path.name.encode("utf-8"))

    monkeypatch.setattr(module, "render_paths", lambda _receipt: (renders, []))
    monkeypatch.setattr(module, "load_encoder", lambda: object())
    monkeypatch.setattr(module, "embed", lambda _encoder, path: Path(path).name)
    monkeypatch.setattr(module, "audio_seconds", lambda path: 5.483 if "floor" in Path(path).name else 5.259)
    monkeypatch.setattr(module, "within_speaker_baseline", lambda *_args: {"method": "stubbed"})
    monkeypatch.setattr(
        module,
        "duration_matched_baseline",
        lambda *_args: {"slice_seconds": 5.483, "mean": 0.934093},
    )

    def cosine(left, right):
        pair = (str(left), str(right))
        if pair == (SCRIPT.name, SCRIPT.name):
            return 0.9
        if pair[1] == "turn_floor_disputed.wav":
            return floor_disputed_score
        if pair[1] == "turn_clear.wav":
            return 0.858506
        if pair[1] == "kai.wav":
            return 0.633146
        if pair[1] == "horus.wav":
            return 0.478377
        return 0.9

    monkeypatch.setattr(module, "cosine", cosine)
    return module.run(
        SimpleNamespace(
            live_receipt=Path("stub-live-receipt.json"),
            reference_audio=reference,
            conditioning_reference=conditioning,
            adversarial_audio=adversarial,
            out=None,
        )
    )


def test_duration_floor_is_report_only_when_fixed_threshold_passes(monkeypatch, tmp_path):
    receipt = run_with_scores(monkeypatch, tmp_path, floor_disputed_score=0.765845)

    assert receipt["status"] == "PASS_SESSION_MOOD_VOICE_RECOGNITION"
    assert "all_renders_recognized_as_embry" not in receipt["failed_gates"]
    disputed = receipt["genuine_renders"][0]
    assert disputed["passes_threshold"] is True
    assert disputed["passes_identity_gate"] is True
    assert disputed["passes_duration_aware_floor"] is False
    assert disputed["identity_gate"] == "fixed_min_embry_similarity"
    assert receipt["preregistered_thresholds"]["duration_aware_floor"] == "report_only"


def test_fixed_threshold_still_blocks_low_similarity_render(monkeypatch, tmp_path):
    receipt = run_with_scores(monkeypatch, tmp_path, floor_disputed_score=0.749)

    assert receipt["status"] == "BLOCKED_SESSION_MOOD_VOICE_RECOGNITION"
    assert "all_renders_recognized_as_embry" in receipt["failed_gates"]
    disputed = receipt["genuine_renders"][0]
    assert disputed["passes_threshold"] is False
    assert disputed["passes_identity_gate"] is False
