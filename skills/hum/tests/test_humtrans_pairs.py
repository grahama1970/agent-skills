from pathlib import Path
import json
import zipfile

from src.female_humming_dataset import build_humtrans_pair_manifest


def _write_zip(path: Path, members: dict[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)


def test_build_humtrans_pair_manifest_filters_female_pairs(tmp_path: Path):
    downloads = tmp_path / "downloads"
    splits = {
        "TRAIN": ["F01_0001_0001_1_D", "M01_0001_0001_1"],
        "VALID": ["F02_0002_0001_1"],
        "TEST": ["F03_0003_0001_1"],
    }
    (downloads / "train_valid_test_keys.json").parent.mkdir(parents=True)
    (downloads / "train_valid_test_keys.json").write_text(json.dumps(splits), encoding="utf-8")
    _write_zip(
        downloads / "all_midi.zip",
        {
            "midi_data/F01_0001_0001_1_D.mid": b"midi-1",
            "midi_data/M01_0001_0001_1.mid": b"midi-2",
            "midi_data/F02_0002_0001_1.mid": b"midi-3",
            "midi_data/F03_0003_0001_1.mid": b"midi-4",
        },
    )
    _write_zip(
        downloads / "all_wav.zip",
        {
            "wav_data/F01_0001_0001_1_D.wav": b"wav-1",
            "wav_data/M01_0001_0001_1.wav": b"wav-2",
            "wav_data/F02_0002_0001_1.wav": b"wav-3",
            "wav_data/F03_0003_0001_1.wav": b"wav-4",
        },
    )

    result = build_humtrans_pair_manifest(tmp_path)

    assert result["count"] == 3
    assert result["split_counts"] == {"train": 1, "valid": 1, "test": 1}
    rows = [json.loads(line) for line in Path(result["pairs_jsonl"]).read_text().splitlines()]
    assert [row["id"] for row in rows] == [
        "F01_0001_0001_1_D",
        "F02_0002_0001_1",
        "F03_0003_0001_1",
    ]
    assert all(row["gender_prefix"] == "F" for row in rows)
