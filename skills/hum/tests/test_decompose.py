from pathlib import Path
import json

import numpy as np
import soundfile as sf

from src.decompose import decompose_audio_dataset, decompose_audio_to_hum


def test_decompose_audio_to_hum_writes_pitch_cadence_and_audio(tmp_path: Path):
    sr = 22050
    duration_s = 1.25
    t = np.arange(int(sr * duration_s), dtype=np.float32) / sr
    carrier = np.sin(2.0 * np.pi * 220.0 * t)
    pulses = 0.45 + 0.55 * (np.sin(2.0 * np.pi * 4.0 * t) > 0).astype(np.float32)
    audio = (0.35 * carrier * pulses).astype(np.float32)

    source = tmp_path / "source.wav"
    sf.write(source, audio, sr)

    result = decompose_audio_to_hum(source, tmp_path / "out", sr=sr)

    melody_path = Path(result.melody_json)
    cadence_path = Path(result.cadence_json)
    sound_path = Path(result.sound_json)
    text_path = Path(result.text_json)
    hum_path = Path(result.neutral_hum_wav)
    assert melody_path.exists()
    assert cadence_path.exists()
    assert sound_path.exists()
    assert text_path.exists()
    assert hum_path.exists()
    assert result.duration_s > 1.0
    assert result.voiced_ratio > 0.5

    melody = json.loads(melody_path.read_text())
    cadence = json.loads(cadence_path.read_text())
    sound = json.loads(sound_path.read_text())
    text = json.loads(text_path.read_text())
    assert melody["schema"] == "hum.melody.v1"
    assert cadence["schema"] == "hum.cadence.v1"
    assert sound["schema"] == "hum.sound.v1"
    assert text["schema"] == "hum.text_alignment.v1"
    assert text["mode"] == "skipped"
    assert "hum_articulation is not literal speech phoneme recognition" in sound["note"]
    assert sound["summary"]["label_counts"]
    assert "hum_articulation" in sound["frames"][0]
    assert any(frame["f0_hz"] > 100.0 for frame in melody["frames"])
    assert melody["pitch_control"]["representation"] == "frame_level_f0_plus_midi_bend"
    assert "bend_cents" in melody["frames"][0]

    hum, hum_sr = sf.read(hum_path)
    assert hum_sr == sr
    assert len(hum) == len(audio)
    assert float(np.max(np.abs(hum))) > 0.1


def test_decompose_audio_dataset_writes_index(tmp_path: Path):
    sr = 22050
    t = np.arange(sr, dtype=np.float32) / sr
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()
    for index, freq in enumerate([220.0, 330.0], start=1):
        source = dataset_dir / f"clip_{index}.wav"
        sf.write(source, (0.25 * np.sin(2.0 * np.pi * freq * t)).astype(np.float32), sr)

    result = decompose_audio_dataset(dataset_dir, tmp_path / "out", sr=sr)

    index_path = Path(result["index_json"])
    assert index_path.exists()
    index_payload = json.loads(index_path.read_text())
    assert index_payload["schema"] == "hum.dataset_decomposition.v1"
    assert index_payload["count"] == 2
    assert index_payload["error_count"] == 0
    for item in index_payload["items"]:
        assert Path(item["melody_json"]).exists()
        assert Path(item["cadence_json"]).exists()
        assert Path(item["sound_json"]).exists()
        assert Path(item["text_json"]).exists()
        assert Path(item["neutral_hum_wav"]).exists()


def test_decompose_audio_to_hum_marks_glissando_events(tmp_path: Path):
    sr = 22050
    duration_s = 1.4
    t = np.arange(int(sr * duration_s), dtype=np.float32) / sr
    start_hz = 220.0
    end_hz = 440.0
    f0 = start_hz * ((end_hz / start_hz) ** (t / duration_s))
    phase = np.cumsum(2.0 * np.pi * f0 / sr).astype(np.float32)
    audio = (0.35 * np.sin(phase)).astype(np.float32)

    source = tmp_path / "glide.wav"
    sf.write(source, audio, sr)

    result = decompose_audio_to_hum(source, tmp_path / "out", sr=sr)
    melody = json.loads(Path(result.melody_json).read_text())

    events = melody["pitch_control"]["glissando_events"]
    assert events
    assert any(event["articulation"] == "glissando" for event in events)
    assert any(event["direction"] == "slide_up" for event in events)
    assert max(abs(event["delta_cents"]) for event in events) > 500.0
