#!/usr/bin/env python3
"""Independently validate a materialized Candidate B Horus wake corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf


EXPECTED_BASE = {
    "positive_train": 200,
    "positive_validation": 75,
    "negative_train": 260,
    "negative_validation": 90,
}
EXPECTED_FINAL = {
    "positive_train": 1500,
    "positive_validation": 350,
    "negative_train": 2000,
    "negative_validation": 400,
}
CAPS = {
    "positive_train": 8,
    "positive_validation": 5,
    "negative_train": 8,
    "negative_validation": 5,
}
ALLOWED_TRANSFORMS = {"speed", "gain", "rir", "noise", "eq"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def load_records(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def referenced_hashes(
    records: list[dict[str, Any]], *, split_suffix: str, transform: str
) -> set[str]:
    return {
        step["sha256"]
        for row in records
        if row["split"].endswith(split_suffix)
        for step in row["transform_chain"]
        if step["name"] == transform
    }


def validate(receipt_path: Path, *, require_exact_counts: bool) -> dict[str, Any]:
    receipt_path = receipt_path.resolve()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("schema") != "embry.horus_wake_candidate_b_corpus.v1":
        raise ValueError("unsupported Candidate B receipt schema")
    if receipt.get("status") != "PASS" or receipt.get("failed_gates"):
        raise ValueError("Candidate B producer receipt is not passing")
    records_path = Path(receipt["records_manifest"]["path"])
    if sha256_file(records_path) != receipt["records_manifest"]["sha256"]:
        raise ValueError("records manifest hash mismatch")
    records = load_records(records_path)

    output_hashes: set[str] = set()
    base_hashes: dict[str, set[str]] = defaultdict(set)
    request_ids: dict[str, set[str]] = defaultdict(set)
    transform_seeds: dict[str, set[int]] = defaultdict(set)
    recipe_hashes: dict[str, set[str]] = defaultdict(set)
    base_counts: dict[str, Counter[str]] = defaultdict(Counter)
    phrase_counts: dict[str, Counter[str]] = defaultdict(Counter)
    errors: list[str] = []

    for row in records:
        split = row.get("split")
        if split not in EXPECTED_FINAL:
            errors.append("unknown_split")
            continue
        path = Path(row["path"])
        if not path.is_file() or sha256_file(path) != row["sha256"]:
            errors.append("output_hash_mismatch")
            continue
        if row["sha256"] in output_hashes:
            errors.append("duplicate_output_hash")
        output_hashes.add(row["sha256"])
        info = sf.info(path)
        samples, rate = sf.read(path, dtype="float64", always_2d=True)
        if rate != 16_000 or info.channels != 1 or info.subtype != "PCM_16":
            errors.append("invalid_audio_format")
        if samples.size == 0 or not np.isfinite(samples).all():
            errors.append("invalid_audio_samples")
        peak = float(np.max(np.abs(samples))) if samples.size else 0.0
        if peak <= 0 or peak > 10 ** (-1 / 20) + 1 / 32768:
            errors.append("audio_peak_policy_failed")
        if not row.get("post_transform_asr_accepted"):
            errors.append("asr_admission_missing")
        chain = row.get("transform_chain", [])
        names = [step.get("name") for step in chain]
        if len(names) > 3 or not set(names).issubset(ALLOWED_TRANSFORMS):
            errors.append("forbidden_transform")
        if row.get("identity") != (row.get("variant_index") == 0 and not chain):
            errors.append("identity_contract_mismatch")
        base_counts[split][row["base_record_id"]] += 1
        phrase_counts[split][row["prompt"]] += int(row["variant_index"] == 0)
        base_hashes[split].add(row["base_audio_sha256"])
        request_ids[split].add(row["orpheus_request_id"])
        if not row["identity"]:
            transform_seeds[split].add(row["transform_seed"])
            recipe_hashes[split].add(row["transform_recipe_sha256"])

    observed_final = Counter(row.get("split") for row in records)
    observed_base = {
        split: len(base_counts[split]) for split in EXPECTED_BASE
    }
    if require_exact_counts:
        if dict(observed_final) != EXPECTED_FINAL:
            errors.append("final_count_mismatch")
        if observed_base != EXPECTED_BASE:
            errors.append("base_count_mismatch")
    for split, counts in base_counts.items():
        if counts and (max(counts.values()) > CAPS[split] or min(counts.values()) < 1):
            errors.append("per_base_expansion_cap_violation")
        if any(count != 1 for count in Counter(
            row["base_record_id"]
            for row in records
            if row["split"] == split and row["identity"]
        ).values()):
            errors.append("identity_count_mismatch")

    for train_split, validation_split in (
        ("positive_train", "positive_validation"),
        ("negative_train", "negative_validation"),
    ):
        if base_hashes[train_split] & base_hashes[validation_split]:
            errors.append("base_hash_split_overlap")
        if request_ids[train_split] & request_ids[validation_split]:
            errors.append("request_id_split_overlap")
        if transform_seeds[train_split] & transform_seeds[validation_split]:
            errors.append("transform_seed_split_overlap")
        if recipe_hashes[train_split] & recipe_hashes[validation_split]:
            errors.append("transform_recipe_split_overlap")

    train_rirs = referenced_hashes(records, split_suffix="train", transform="rir")
    validation_rirs = referenced_hashes(
        records, split_suffix="validation", transform="rir"
    )
    train_noise = referenced_hashes(records, split_suffix="train", transform="noise")
    validation_noise = referenced_hashes(
        records, split_suffix="validation", transform="noise"
    )
    if train_rirs & validation_rirs:
        errors.append("rir_hash_split_overlap")
    if train_noise & validation_noise:
        errors.append("noise_hash_split_overlap")

    for split in ("negative_train", "negative_validation"):
        counts = phrase_counts[split]
        minimum = 20 if split == "negative_train" else 6
        if counts and min(counts.values()) < minimum:
            errors.append("negative_phrase_coverage_below_minimum")
        if counts and max(counts.values()) / sum(counts.values()) > 0.15:
            errors.append("negative_phrase_coverage_imbalanced")

    failed_gates = sorted(set(errors))
    return {
        "schema": "embry.horus_wake_candidate_b_validation.v1",
        "status": "PASS" if not failed_gates else "FAIL",
        "live": True,
        "mocked": False,
        "producer_receipt": {
            "path": str(receipt_path),
            "sha256": sha256_file(receipt_path),
        },
        "counts": {
            "records": len(records),
            "unique_output_hashes": len(output_hashes),
            "base_by_split": observed_base,
            "final_by_split": dict(observed_final),
        },
        "disjointness": {
            "rir_hash_overlap_count": len(train_rirs & validation_rirs),
            "noise_hash_overlap_count": len(train_noise & validation_noise),
        },
        "negative_phrase_counts": {
            split: dict(counts) for split, counts in phrase_counts.items()
            if split.startswith("negative")
        },
        "failed_gates": failed_gates,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--require-exact-counts", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = validate(
        args.receipt, require_exact_counts=args.require_exact_counts
    )
    atomic_json(args.output.resolve(), result)
    print(json.dumps({"status": result["status"], "counts": result["counts"]}))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
