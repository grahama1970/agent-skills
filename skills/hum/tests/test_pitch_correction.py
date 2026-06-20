import json
from pathlib import Path

import numpy as np
import soundfile as sf

from src.pitch_correction import analyze_pitch, pitch_correct_guide


def _write_detuned_sine(path: Path, *, cents: float, sr: int = 22050) -> None:
    duration = 1.8
    base_hz = 220.0
    hz = base_hz * (2.0 ** (cents / 1200.0))
    t = np.linspace(0.0, duration, int(sr * duration), endpoint=False)
    y = 0.24 * np.sin(2.0 * np.pi * hz * t)
    fade = int(0.035 * sr)
    envelope = np.ones_like(y)
    envelope[:fade] = np.linspace(0.0, 1.0, fade, endpoint=False)
    envelope[-fade:] = np.linspace(1.0, 0.0, fade, endpoint=False)
    sf.write(path, (y * envelope).astype(np.float32), sr)


def test_pitch_correct_guide_writes_pre_sts_variant(tmp_path: Path):
    source = tmp_path / "guide.wav"
    _write_detuned_sine(source, cents=24.0)

    result = pitch_correct_guide(
        source,
        tmp_path / "pitch",
        sample_rate=22050,
        max_correction_cents=35.0,
    )

    assert result.output_wav is not None
    assert result.output_wav.is_file()
    assert result.analysis_json.is_file()
    assert result.manifest_json.is_file()
    assert -35.0 <= result.correction_cents <= 35.0
    assert result.correction_cents < -10.0

    manifest = json.loads(result.manifest_json.read_text())
    assert manifest["schema"] == "hum.pitch_corrected_guide.v1"
    assert manifest["bakeoff_role"] == "pre_elevenlabs_guide_variant"
    assert manifest["release_gate"] == "human_listening_required"

    before = analyze_pitch(source, sample_rate=22050)["median_abs_detune_cents"]
    after = analyze_pitch(result.output_wav, sample_rate=22050)["median_abs_detune_cents"]
    assert after < before


def test_pitch_correct_guide_dry_run_does_not_write_audio(tmp_path: Path):
    source = tmp_path / "guide.wav"
    _write_detuned_sine(source, cents=-18.0)

    result = pitch_correct_guide(source, tmp_path / "pitch", sample_rate=22050, dry_run=True)

    assert result.output_wav is None
    assert result.analysis_json.is_file()
    assert result.manifest_json.is_file()
