from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import soundfile as sf


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


normalize = load_script("normalize_rirs")
validate = load_script("validate_rirs")
freeze = load_script("freeze_corpus")


def write_stereo(path: Path, *, rate: int = 44_100) -> None:
    frames = rate // 4
    samples = np.zeros((frames, 2), dtype=np.float64)
    samples[100, 0] = 0.8
    samples[250, 1] = -0.6
    samples[101:1000, 0] += np.linspace(0.2, 0.0, 899)
    samples[251:1200, 1] += np.linspace(-0.15, 0.0, 949)
    sf.write(path, samples, rate, subtype="PCM_16")


def test_normalize_splits_stereo_and_validates_without_speechbrain(tmp_path: Path):
    source = tmp_path / "source"
    output = tmp_path / "derived"
    source.mkdir()
    write_stereo(source / "Room A.wav")

    receipt = normalize.normalize_directory(
        source,
        output,
        target_rate=16_000,
        peak_target=0.95,
        kaiser_beta=8.6,
        expected_source_count=1,
    )
    manifest = tmp_path / "normalization.json"
    normalize.atomic_json(manifest, receipt)

    assert receipt["counts"] == {"sources": 1, "outputs": 2}
    assert receipt["policy"]["channel_policy"] == "split"
    hashes = {row["sha256"] for row in receipt["sources"][0]["outputs"]}
    assert len(hashes) == 2
    for row in receipt["sources"][0]["outputs"]:
        audio, rate = sf.read(row["path"], always_2d=True)
        assert rate == 16_000
        assert audio.shape[1] == 1

    preflight = validate.validate_manifest(
        manifest,
        required_rate=16_000,
        minimum_duration_ms=20,
        maximum_duration_ms=12_000,
        minimum_rms_dbfs=-90,
        batch_size=2,
        waveform_samples=4_000,
        run_speechbrain=False,
    )
    assert preflight["status"] == "PASS"
    assert preflight["counts"] == {"validated": 2, "failed": 0}


def test_validator_rejects_modified_output(tmp_path: Path):
    source = tmp_path / "source"
    output = tmp_path / "derived"
    source.mkdir()
    write_stereo(source / "Room.wav")
    receipt = normalize.normalize_directory(
        source,
        output,
        target_rate=16_000,
        peak_target=0.95,
        kaiser_beta=8.6,
        expected_source_count=1,
    )
    manifest = tmp_path / "normalization.json"
    normalize.atomic_json(manifest, receipt)
    first = Path(receipt["sources"][0]["outputs"][0]["path"])
    first.write_bytes(first.read_bytes() + b"tamper")

    try:
        validate.validate_manifest(
            manifest,
            required_rate=16_000,
            minimum_duration_ms=20,
            maximum_duration_ms=12_000,
            minimum_rms_dbfs=-90,
            batch_size=2,
            waveform_samples=4_000,
            run_speechbrain=False,
        )
    except ValueError as error:
        assert "hash mismatch" in str(error)
    else:
        raise AssertionError("tampered RIR was accepted")


def test_receipt_is_json_serializable(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    write_stereo(source / "Room.wav")
    receipt = normalize.normalize_directory(
        source,
        tmp_path / "derived",
        target_rate=16_000,
        peak_target=0.95,
        kaiser_beta=8.6,
        expected_source_count=1,
    )
    assert json.loads(json.dumps(receipt))["schema"] == normalize.SCHEMA


def test_freeze_corpus_records_missing_legacy_provenance(tmp_path: Path):
    for directory in freeze.SPLITS:
        target = tmp_path / directory
        target.mkdir()
        write_stereo(target / f"{directory}.wav", rate=16_000)
    manifest = freeze.freeze(tmp_path, "hey_embry_v1a_general")
    assert manifest["total_files"] == 4
    assert manifest["counts"] == {name: 1 for name in freeze.SPLITS}
    assert manifest["files"][0]["generation_seed"] is None
    assert manifest["provenance_limitations"]
