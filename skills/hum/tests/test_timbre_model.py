from pathlib import Path
import json

import numpy as np
import soundfile as sf

from src.decompose import decompose_audio_dataset
from src.timbre_model import render_trained_hum, train_hum_timbre_model


def test_train_and_render_hum_timbre_model(tmp_path: Path):
    sr = 22050
    t = np.arange(int(sr * 1.2), dtype=np.float32) / sr
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    for index, hz in enumerate([220.0, 246.94], start=1):
        audio = (
            0.25 * np.sin(2.0 * np.pi * hz * t)
            + 0.08 * np.sin(2.0 * np.pi * hz * 2.0 * t)
            + 0.03 * np.sin(2.0 * np.pi * hz * 3.0 * t)
        ).astype(np.float32)
        sf.write(source_dir / f"hum_{index}.wav", audio, sr)

    decomposition = decompose_audio_dataset(source_dir, tmp_path / "decomp", sr=sr)
    train = train_hum_timbre_model(Path(decomposition["index_json"]), tmp_path / "model", sr=sr, n_harmonics=8)
    model = json.loads(Path(train.model_json).read_text())
    assert model["schema"] == "hum.timbre_model.v1"
    assert model["clip_count"] == 2
    assert model["frame_count"] > 0
    assert len(model["harmonic_weights"]) == 8

    melody = {
        "schema": "hum.render_melody.v1",
        "notes": [
            {"start": 0.0, "midi": 57, "duration": 0.45},
            {"start": 0.5, "midi": 59, "duration": 0.45},
        ],
    }
    melody_path = tmp_path / "melody.json"
    melody_path.write_text(json.dumps(melody))
    result = render_trained_hum(Path(train.model_json), tmp_path / "render", melody_json=melody_path)

    wav_path = Path(result.output_wav)
    manifest_path = Path(result.render_manifest)
    assert wav_path.exists()
    assert manifest_path.exists()
    assert result.note_count == 2
    assert result.peak > 0.1
    rendered, rendered_sr = sf.read(wav_path)
    assert rendered_sr == sr
    assert float(np.max(np.abs(rendered))) > 0.1


def test_render_trained_hum_consumes_midi_pitch_bend(tmp_path: Path):
    import pretty_midi

    sr = 22050
    t = np.arange(int(sr * 1.2), dtype=np.float32) / sr
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    audio = (
        0.25 * np.sin(2.0 * np.pi * 220.0 * t)
        + 0.08 * np.sin(2.0 * np.pi * 440.0 * t)
    ).astype(np.float32)
    sf.write(source_dir / "hum.wav", audio, sr)
    decomposition = decompose_audio_dataset(source_dir, tmp_path / "decomp", sr=sr)
    train = train_hum_timbre_model(Path(decomposition["index_json"]), tmp_path / "model", sr=sr, n_harmonics=6)

    midi = pretty_midi.PrettyMIDI(initial_tempo=120)
    instrument = pretty_midi.Instrument(program=53, name="MELODY")
    instrument.notes.append(pretty_midi.Note(velocity=90, pitch=57, start=0.0, end=0.9))
    instrument.pitch_bends.append(pretty_midi.PitchBend(pitch=0, time=0.0))
    instrument.pitch_bends.append(pretty_midi.PitchBend(pitch=8191, time=0.9))
    midi.instruments.append(instrument)
    midi_path = tmp_path / "gliss.mid"
    midi.write(str(midi_path))

    result = render_trained_hum(
        Path(train.model_json),
        tmp_path / "render_bend",
        midi_path=midi_path,
        midi_track_name="MELODY",
        midi_min_note_duration_s=0.0,
    )
    manifest = json.loads(Path(result.render_manifest).read_text())

    assert manifest["pitch_bend_note_count"] == 1
    assert manifest["pitch_bend_control"] == "pitch_bend_points_interpolated_to_f0_curve"
    assert Path(result.output_wav).exists()
