from pathlib import Path
import json

import numpy as np
import soundfile as sf

from src.decompose import decompose_audio_dataset
from src.sample_renderer import _load_midi_melody, render_female_hum


def test_render_female_hum_writes_wav_and_manifest(tmp_path: Path):
    sr = 22050
    t = np.arange(int(sr * 1.4), dtype=np.float32) / sr
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    for index, hz in enumerate([220.0, 330.0], start=1):
        env = np.ones_like(t)
        env[: int(0.04 * sr)] = np.linspace(0.0, 1.0, int(0.04 * sr), dtype=np.float32)
        env[-int(0.04 * sr) :] = np.linspace(1.0, 0.0, int(0.04 * sr), dtype=np.float32)
        audio = (0.35 * np.sin(2.0 * np.pi * hz * t) * env).astype(np.float32)
        sf.write(source_dir / f"carrier_{index}.wav", audio, sr)

    decomposition = decompose_audio_dataset(source_dir, tmp_path / "decomp", sr=sr)
    result = render_female_hum(Path(decomposition["index_json"]), tmp_path / "render", sr=sr)

    wav_path = Path(result.output_wav)
    manifest_path = Path(result.render_manifest)
    assert wav_path.exists()
    assert manifest_path.exists()
    assert result.sample_count >= 2
    assert result.note_count == 5
    assert result.duration_s > 3.0
    assert result.peak > 0.1

    audio, audio_sr = sf.read(wav_path)
    assert audio_sr == sr
    assert len(audio) > sr * 3
    assert float(np.max(np.abs(audio))) > 0.1

    manifest = json.loads(manifest_path.read_text())
    assert manifest["schema"] == "hum.sample_render.v1"
    assert manifest["renderer"] == "sample_based_mvp"
    assert manifest["carrier"] == "original"
    assert len(manifest["notes"]) == 5
    assert all(note["carrier"] == "original" for note in manifest["notes"])
    assert manifest["limitations"]


def test_render_female_hum_accepts_midi_melody(tmp_path: Path):
    import pretty_midi

    sr = 22050
    t = np.arange(int(sr * 1.2), dtype=np.float32) / sr
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    sf.write(source_dir / "carrier.wav", (0.35 * np.sin(2.0 * np.pi * 220.0 * t)).astype(np.float32), sr)
    decomposition = decompose_audio_dataset(source_dir, tmp_path / "decomp", sr=sr)

    midi = pretty_midi.PrettyMIDI()
    decoy = pretty_midi.Instrument(program=1, name="busy piano")
    for i in range(12):
        decoy.notes.append(pretty_midi.Note(velocity=60, pitch=48, start=i * 0.1, end=i * 0.1 + 0.05))
    midi.instruments.append(decoy)

    instrument = pretty_midi.Instrument(program=53, name="MELODY")
    for start, pitch in [(0.0, 57), (0.42, 59), (0.84, 60)]:
        instrument.notes.append(pretty_midi.Note(velocity=90, pitch=pitch, start=start, end=start + 0.32))
    midi.instruments.append(instrument)
    midi_path = tmp_path / "phrase.mid"
    midi.write(str(midi_path))

    result = render_female_hum(
        Path(decomposition["index_json"]),
        tmp_path / "render_midi",
        midi_path=midi_path,
        midi_track_name="MELODY",
        sr=sr,
        tone="low_breathy",
    )

    manifest = json.loads(Path(result.render_manifest).read_text())
    assert manifest["midi_path"] == str(midi_path)
    assert manifest["melody_source"] == str(midi_path)
    assert manifest["selected_midi_instrument"] == "MELODY"
    assert manifest["tone"] == "low_breathy"
    assert len(manifest["notes"]) == 3
    assert Path(result.output_wav).exists()


def test_load_midi_melody_preserves_pitch_bend_points(tmp_path: Path):
    import pretty_midi

    midi = pretty_midi.PrettyMIDI(initial_tempo=120)
    instrument = pretty_midi.Instrument(program=53, name="MELODY")
    instrument.notes.append(pretty_midi.Note(velocity=90, pitch=60, start=0.0, end=1.0))
    instrument.pitch_bends.append(pretty_midi.PitchBend(pitch=0, time=0.0))
    instrument.pitch_bends.append(pretty_midi.PitchBend(pitch=4096, time=0.5))
    instrument.pitch_bends.append(pretty_midi.PitchBend(pitch=8191, time=1.0))
    midi.instruments.append(instrument)
    midi_path = tmp_path / "pitch_bend.mid"
    midi.write(str(midi_path))

    melody = _load_midi_melody(
        midi_path,
        preferred_track_name="MELODY",
        legato=False,
        min_note_duration_s=0.0,
        pitch_bend_range_semitones=2.0,
    )

    points = melody["notes"][0]["pitch_bend_points"]
    assert len(points) == 3
    assert points[0]["bend_cents"] == 0.0
    assert 99.0 < points[1]["bend_cents"] < 101.0
    assert 199.0 < points[2]["bend_cents"] <= 200.0
