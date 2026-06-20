from pathlib import Path
import json

import numpy as np
import pretty_midi
import soundfile as sf

from src.techsinger_export import export_techsinger_smoke, validate_techsinger_smoke


def _write_control_item(root: Path, item_id: str) -> dict:
    sr = 22050
    t = np.arange(int(sr * 1.0), dtype=np.float32) / sr
    audio = (0.18 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)
    wav_path = root / f"{item_id}.wav"
    sf.write(wav_path, audio, sr)

    midi = pretty_midi.PrettyMIDI(initial_tempo=120)
    inst = pretty_midi.Instrument(program=53, name="hum melody")
    inst.notes.append(pretty_midi.Note(velocity=90, pitch=57, start=0.0, end=0.45))
    inst.notes.append(pretty_midi.Note(velocity=80, pitch=60, start=0.55, end=0.9))
    inst.pitch_bends.append(pretty_midi.PitchBend(pitch=1024, time=0.2))
    midi.instruments.append(inst)
    midi_path = root / f"{item_id}.mid"
    midi.write(str(midi_path))

    return {
        "id": item_id,
        "split": "train",
        "audio_path": str(wav_path),
        "midi_path": str(midi_path),
        "duration_s": 1.0,
        "speaker_id": "FTEST",
        "source": "unit-test",
        "license": "unit-test",
    }


def test_export_and_validate_techsinger_smoke(tmp_path: Path):
    item = _write_control_item(tmp_path, "FTEST_0001")
    controls = {
        "schema": "hum.train_control_dataset.v1",
        "items": [item],
    }
    manifest = tmp_path / "controls_manifest.json"
    manifest.write_text(json.dumps(controls), encoding="utf-8")

    result = export_techsinger_smoke(manifest, tmp_path / "tech")
    assert result.item_count == 1
    assert result.error_count == 0

    metadata = json.loads(Path(result.metadata_json).read_text())
    row = metadata[0]
    assert row["ph"]
    assert len(row["ph"]) == len(row["ph_durs"])
    assert len(row["ph"]) == len(row["ep_pitches"])
    assert len(row["ph"]) == len(row["glissando_tech"])
    assert any(v == 1 for v in row["glissando_tech"])
    assert Path(row["wav_fn"]).exists()
    assert Path(row["wav_fn"]).with_name("FTEST_0001_f0.npy").exists()

    validation = validate_techsinger_smoke(tmp_path / "tech")
    assert validation.error_count == 0
    assert validation.item_count == 1
    assert validation.has_glissando
