#!/usr/bin/env python3
"""Build frozen OpenWakeWord features from an accepted Candidate B corpus."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
from typing import Any

import numpy as np
from numpy.lib.format import open_memmap
import soundfile as sf


SPLIT_OUTPUTS = {
    "positive_train": "positive_features_train.npy",
    "positive_validation": "positive_features_test.npy",
    "negative_train": "negative_features_train.npy",
    "negative_validation": "negative_features_test.npy",
}
TARGET_RATE = 16_000
TARGET_SAMPLES = 32_000


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def deterministic_fixed_clip(samples: np.ndarray, record_id: str) -> np.ndarray:
    """Match OpenWakeWord's trailing placement without random acoustic changes."""
    samples = np.asarray(samples, dtype=np.int16).reshape(-1)
    seed = int(hashlib.sha256(record_id.encode("utf-8")).hexdigest()[:16], 16)
    if samples.size > TARGET_SAMPLES:
        # Long RIR tails may put useful speech at either edge. Freeze that choice per record.
        samples = samples[-TARGET_SAMPLES:] if seed & 1 else samples[:TARGET_SAMPLES]
    output = np.zeros(TARGET_SAMPLES, dtype=np.int16)
    end_jitter = seed % 3_201  # OpenWakeWord uses 0-200 ms at 16 kHz.
    start = max(0, TARGET_SAMPLES - samples.size - end_jitter)
    output[start : start + samples.size] = samples
    return output


def record_batches(records: list[dict[str, Any]], batch_size: int) -> Iterable[np.ndarray]:
    for offset in range(0, len(records), batch_size):
        batch = []
        for record in records[offset : offset + batch_size]:
            path = Path(record["path"])
            samples, rate = sf.read(path, dtype="int16", always_2d=False)
            if rate != TARGET_RATE or np.asarray(samples).ndim != 1:
                raise ValueError(f"invalid feature input audio: {path}")
            batch.append(deterministic_fixed_clip(samples, record["variant_id"]))
        yield np.stack(batch)


def extract_split(
    records: list[dict[str, Any]], output: Path, feature_extractor: Any, batch_size: int
) -> dict[str, Any]:
    if not records:
        raise ValueError(f"no records for {output.name}")
    feature_shape = tuple(feature_extractor.get_embedding_shape(TARGET_SAMPLES / TARGET_RATE))
    array = open_memmap(
        output, mode="w+", dtype=np.float32, shape=(len(records), *feature_shape)
    )
    row = 0
    for audio in record_batches(records, batch_size):
        features = feature_extractor.embed_clips(audio, batch_size=len(audio), ncpu=1)
        if features.shape[1:] != feature_shape or not np.isfinite(features).all():
            raise ValueError(f"invalid OpenWakeWord features for {output.name}")
        array[row : row + len(features)] = features
        row += len(features)
        array.flush()
    if row != len(records):
        raise ValueError(f"feature row mismatch for {output.name}: {row} != {len(records)}")
    del array
    saved = np.load(output, mmap_mode="r")
    return {
        "path": str(output),
        "sha256": sha256_file(output),
        "shape": list(saved.shape),
        "dtype": str(saved.dtype),
    }


def concatenate_features(first: Path, second: Path, output: Path) -> dict[str, Any]:
    left = np.load(first, mmap_mode="r")
    right = np.load(second, mmap_mode="r")
    if left.shape[1:] != right.shape[1:] or left.dtype != right.dtype:
        raise ValueError(f"incompatible feature arrays: {first} and {second}")
    combined = open_memmap(
        output,
        mode="w+",
        dtype=left.dtype,
        shape=(left.shape[0] + right.shape[0], *left.shape[1:]),
    )
    combined[: left.shape[0]] = left
    combined[left.shape[0] :] = right
    combined.flush()
    del combined
    saved = np.load(output, mmap_mode="r")
    return {
        "path": str(output),
        "sha256": sha256_file(output),
        "shape": list(saved.shape),
        "dtype": str(saved.dtype),
        "candidate_a_rows": int(left.shape[0]),
        "candidate_b_rows": int(right.shape[0]),
    }


def load_validated_records(validation_receipt: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    validation = json.loads(validation_receipt.read_text())
    if validation.get("status") != "PASS" or validation.get("failed_gates"):
        raise ValueError("Candidate B validation receipt is not PASS")
    producer = validation["producer_receipt"]
    corpus_receipt_path = Path(producer["path"])
    if sha256_file(corpus_receipt_path) != producer["sha256"]:
        raise ValueError("Candidate B source receipt hash mismatch")
    corpus = json.loads(corpus_receipt_path.read_text())
    records_path = Path(corpus["records_manifest"]["path"])
    if sha256_file(records_path) != corpus["records_manifest"]["sha256"]:
        raise ValueError("Candidate B records manifest hash mismatch")
    records = [json.loads(line) for line in records_path.read_text().splitlines() if line]
    return validation, records


def build(args: argparse.Namespace) -> dict[str, Any]:
    from openwakeword.utils import AudioFeatures

    validation, records = load_validated_records(args.validation_receipt)
    by_split = {
        split: sorted(
            (record for record in records if record["split"] == split),
            key=lambda record: record["variant_id"],
        )
        for split in SPLIT_OUTPUTS
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    candidate_b_dir = args.output_dir / "candidate-b"
    combined_dir = args.output_dir / "combined"
    candidate_b_dir.mkdir(exist_ok=True)
    combined_dir.mkdir(exist_ok=True)

    extractor = AudioFeatures(device=args.device)
    candidate_b = {}
    for split, filename in SPLIT_OUTPUTS.items():
        candidate_b[split] = extract_split(
            by_split[split], candidate_b_dir / filename, extractor, args.batch_size
        )

    combined = {}
    for split, filename in SPLIT_OUTPUTS.items():
        combined[split] = concatenate_features(
            args.candidate_a_feature_dir / filename,
            Path(candidate_b[split]["path"]),
            combined_dir / filename,
        )

    melspec_path = Path(extractor.melspec_model._model_path)
    embedding_path = Path(extractor.embedding_model._model_path)
    return {
        "schema": "embry.openwakeword_candidate_b_features.v1",
        "status": "PASS",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "live": True,
        "mocked": False,
        "source_validation_receipt": {
            "path": str(args.validation_receipt),
            "sha256": sha256_file(args.validation_receipt),
            "validated_records": validation["counts"]["records"],
        },
        "framing": {
            "sample_rate_hz": TARGET_RATE,
            "samples": TARGET_SAMPLES,
            "seconds": TARGET_SAMPLES / TARGET_RATE,
            "end_jitter_max_ms": 200,
            "acoustic_augmentation_applied": False,
        },
        "openwakeword_backbone": {
            "melspectrogram": {"path": str(melspec_path), "sha256": sha256_file(melspec_path)},
            "embedding": {"path": str(embedding_path), "sha256": sha256_file(embedding_path)},
            "execution_provider": extractor.onnx_execution_provider,
        },
        "candidate_b": candidate_b,
        "combined_candidate_a_b": combined,
        "runtime": {"python": platform.python_version(), "numpy": np.__version__},
        "failed_gates": [],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validation-receipt", type=Path, required=True)
    parser.add_argument("--candidate-a-feature-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--device", choices=("cpu", "gpu"), default="cpu")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    receipt = build(args)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
