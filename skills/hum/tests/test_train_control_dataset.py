from pathlib import Path
import json
import zipfile

import numpy as np
import pretty_midi
import soundfile as sf

from src.train_control_dataset import build_train_control_dataset


def _write_pair(root: Path, key: str, split: str) -> Path:
    sr = 22050
    t = np.arange(int(sr * 0.8), dtype=np.float32) / sr
    audio = (0.2 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)
    wav_path = root / f"{key}.wav"
    sf.write(wav_path, audio, sr)

    midi = pretty_midi.PrettyMIDI(initial_tempo=120)
    inst = pretty_midi.Instrument(program=53, name="MELODY")
    inst.notes.append(pretty_midi.Note(velocity=90, pitch=57, start=0.0, end=0.7))
    midi.instruments.append(inst)
    midi_path = root / f"{key}.mid"
    midi.write(str(midi_path))

    wav_zip = root / "all_wav.zip"
    midi_zip = root / "all_midi.zip"
    with zipfile.ZipFile(wav_zip, "a") as zf:
        zf.write(wav_path, f"wav_data_sync_with_midi/{key}.wav")
    with zipfile.ZipFile(midi_zip, "a") as zf:
        zf.write(midi_path, f"midi_data/{key}.mid")

    row = {
        "id": key,
        "split": split,
        "speaker_id": key.split("_", 1)[0],
        "midi_zip": str(midi_zip),
        "midi_member": f"midi_data/{key}.mid",
        "wav_zip": str(wav_zip),
        "wav_member": f"wav_data_sync_with_midi/{key}.wav",
        "source": "test",
        "license": "test",
    }
    return row


def test_build_train_control_dataset_from_zip_pairs(tmp_path: Path):
    rows = [
        _write_pair(tmp_path, "F01_001", "train"),
        _write_pair(tmp_path, "F01_002", "valid"),
        _write_pair(tmp_path, "F01_003", "test"),
    ]
    pairs = tmp_path / "pairs.jsonl"
    pairs.write_text("\n".join(json.dumps(row) for row in rows) + "\n")

    result = build_train_control_dataset(
        pairs,
        tmp_path / "controls",
        train_limit=1,
        valid_limit=1,
        test_limit=1,
    )
    manifest = json.loads(Path(result.manifest_json).read_text())
    assert manifest["schema"] == "hum.train_control_dataset.v1"
    assert manifest["split_counts"] == {"train": 1, "valid": 1, "test": 1}
    assert manifest["items"][0]["note_count"] == 1
    assert Path(manifest["items"][0]["audio_path"]).exists()
    assert Path(manifest["items"][0]["midi_path"]).exists()
