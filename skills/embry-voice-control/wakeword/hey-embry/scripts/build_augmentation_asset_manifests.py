#!/usr/bin/env python3
"""Freeze split-disjoint RIR and background-noise augmentation pools."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import soundfile as sf


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


def audio_row(path: Path) -> dict[str, Any]:
    info = sf.info(path)
    if info.frames <= 0 or info.channels <= 0 or info.samplerate <= 0:
        raise ValueError(f"invalid audio asset: {path}")
    return {
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "sample_rate_hz": info.samplerate,
        "channels": info.channels,
        "frames": info.frames,
        "duration_ms": round(info.frames * 1000 / info.samplerate, 3),
    }


def load_rirs(preflight_path: Path) -> list[dict[str, Any]]:
    receipt = json.loads(preflight_path.read_text(encoding="utf-8"))
    if receipt.get("schema") != "embry.rir_preflight_receipt.v1":
        raise ValueError("unsupported RIR preflight schema")
    if receipt.get("status") != "PASS" or receipt.get("failed_gates"):
        raise ValueError("RIR preflight did not pass")
    rows = sorted(receipt["outputs"], key=lambda row: row["sha256"])
    for row in rows:
        path = Path(row["path"])
        if sha256_file(path) != row["sha256"]:
            raise ValueError(f"RIR hash mismatch: {path}")
        if row["sample_rate_hz"] != 16_000 or row["channels"] != 1:
            raise ValueError(f"RIR is not mono 16 kHz: {path}")
    return rows


def load_noise(noise_dir: Path) -> list[dict[str, Any]]:
    paths = sorted(
        path
        for path in noise_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in {".wav", ".flac"}
    )
    if len(paths) < 2:
        raise ValueError("at least two independent noise files are required")
    rows = sorted((audio_row(path) for path in paths), key=lambda row: row["sha256"])
    hashes = [row["sha256"] for row in rows]
    if len(hashes) != len(set(hashes)):
        raise ValueError("duplicate background-noise file hashes")
    return rows


def split_assets(
    rows: list[dict[str, Any]], *, train_count: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not 0 < train_count < len(rows):
        raise ValueError("train count must leave nonempty train and validation pools")
    return rows[:train_count], rows[train_count:]


def manifest(kind: str, split: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": "embry.augmentation_asset_manifest.v1",
        "kind": kind,
        "split": split,
        "count": len(rows),
        "assets": rows,
        "failed_gates": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rir-preflight", type=Path, required=True)
    parser.add_argument("--noise-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--rir-train-count", type=int, default=12)
    parser.add_argument("--noise-train-count", type=int, required=True)
    args = parser.parse_args()

    rirs = load_rirs(args.rir_preflight.resolve())
    noises = load_noise(args.noise_dir.resolve())
    train_rirs, validation_rirs = split_assets(rirs, train_count=args.rir_train_count)
    train_noise, validation_noise = split_assets(
        noises, train_count=args.noise_train_count
    )
    outputs = {
        "train-rirs.json": manifest("rir", "train", train_rirs),
        "validation-rirs.json": manifest("rir", "validation", validation_rirs),
        "train-noise.json": manifest("noise", "train", train_noise),
        "validation-noise.json": manifest("noise", "validation", validation_noise),
    }
    for name, value in outputs.items():
        atomic_json(args.output_dir.resolve() / name, value)
    print(json.dumps({name: value["count"] for name, value in outputs.items()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
