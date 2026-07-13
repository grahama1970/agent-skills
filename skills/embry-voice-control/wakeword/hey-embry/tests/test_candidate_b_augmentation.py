from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import soundfile as sf


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


assets = load_script("build_augmentation_asset_manifests")
expand = load_script("expand_horus_wake_corpus")
validate = load_script("validate_candidate_b_corpus")


def write_audio(path: Path, *, frequency: float, rate: int = 16_000) -> None:
    time = np.arange(rate, dtype=np.float64) / rate
    samples = 0.1 * np.sin(2 * np.pi * frequency * time)
    sf.write(path, samples, rate, subtype="PCM_16")


def test_exact_webgpt_allocations_obey_caps() -> None:
    assert sorted(expand.allocation(200, 1500, 8)) == [7] * 100 + [8] * 100
    assert sorted(expand.allocation(75, 350, 5)) == [4] * 25 + [5] * 50
    assert sorted(expand.allocation(260, 2000, 8)) == [7] * 80 + [8] * 180
    assert sorted(expand.allocation(90, 400, 5)) == [4] * 50 + [5] * 40


def test_recipe_is_deterministic_and_bounded() -> None:
    first = expand.deterministic_recipe(
        split="positive_train", base_id="base-1", variant_index=3, attempt_index=2
    )
    second = expand.deterministic_recipe(
        split="positive_train", base_id="base-1", variant_index=3, attempt_index=2
    )
    assert first == second
    seed, chain, values = first
    assert seed > 0
    assert 1 <= len(chain) <= 3
    assert set(chain) <= {"speed", "gain", "rir", "noise", "eq"}
    assert 0.9 <= values["speed"] <= 1.1
    assert -9 <= values["gain_db"] <= 3
    assert 8 <= values["snr_db"] <= 30
    assert values["highpass_hz"] <= 180
    assert values["lowpass_hz"] >= 5500


def test_asset_builder_creates_hash_disjoint_pools(tmp_path: Path) -> None:
    rir_rows = []
    for index in range(16):
        path = tmp_path / f"rir-{index}.wav"
        write_audio(path, frequency=100 + index)
        row = assets.audio_row(path)
        row["speechbrain_probe"] = {"finite": True}
        rir_rows.append(row)
    preflight = tmp_path / "preflight.json"
    preflight.write_text(
        json.dumps(
            {
                "schema": "embry.rir_preflight_receipt.v1",
                "status": "PASS",
                "outputs": rir_rows,
                "failed_gates": [],
            }
        )
    )
    loaded = assets.load_rirs(preflight)
    train, validation = assets.split_assets(loaded, train_count=12)
    assert len(train) == 12
    assert len(validation) == 4
    assert {row["sha256"] for row in train}.isdisjoint(
        row["sha256"] for row in validation
    )


def test_pitch_preserving_speed_uses_ffmpeg_and_preserves_rate() -> None:
    samples = np.sin(2 * np.pi * 220 * np.arange(16_000) / 16_000) * 0.1
    output = expand.pitch_preserving_speed(
        samples, rate=16_000, speed=1.05, ffmpeg="/usr/bin/ffmpeg"
    )
    assert output.size < samples.size
    assert np.isfinite(output).all()


def test_negative_derivative_admission_remains_prompt_specific() -> None:
    record = {"label": "negative", "prompt": "Hey Henry."}
    assert expand.transcript_accepted(record, "Hey Henry.")
    assert not expand.transcript_accepted(record, "Henry.")
    assert not expand.transcript_accepted(record, "Hey Embry.")


def test_identity_base_transcript_remains_valid_admission_authority() -> None:
    positive = {"label": "positive", "prompt": "Hey Em-bree!"}
    negative = {"label": "negative", "prompt": "Emery!"}
    assert expand.transcript_accepted(positive, "Hey, Embrie.")
    assert expand.transcript_accepted(negative, "Emory.")


def test_independent_validator_checks_materialized_audio(tmp_path: Path) -> None:
    records = []
    for index, split in enumerate(("positive_train", "positive_validation")):
        path = tmp_path / f"{split}.wav"
        write_audio(path, frequency=220 + index)
        records.append(
            {
                "split": split,
                "path": str(path),
                "sha256": validate.sha256_file(path),
                "post_transform_asr_accepted": True,
                "transform_chain": [],
                "identity": True,
                "variant_index": 0,
                "base_record_id": f"base-{index}",
                "base_audio_sha256": f"sha256:base-{index}",
                "orpheus_request_id": f"request-{index}",
                "transform_seed": 0,
                "transform_recipe_sha256": "sha256:identity",
                "prompt": "Hey Em-bree!",
            }
        )
    records_path = tmp_path / "records.jsonl"
    records_path.write_text(
        "".join(json.dumps(record) + "\n" for record in records)
    )
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(
        json.dumps(
            {
                "schema": "embry.horus_wake_candidate_b_corpus.v1",
                "status": "PASS",
                "failed_gates": [],
                "records_manifest": {
                    "path": str(records_path),
                    "sha256": validate.sha256_file(records_path),
                },
            }
        )
    )
    result = validate.validate(receipt_path, require_exact_counts=False)
    assert result["status"] == "PASS"
    assert result["counts"]["records"] == 2
