#!/usr/bin/env python3
"""Validate normalized RIRs, including the real SpeechBrain code path."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
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


def speechbrain_probe(
    samples: np.ndarray, *, batch_size: int, waveform_samples: int
) -> dict[str, Any]:
    import torch
    from speechbrain.processing.signal_processing import reverberate

    generator = torch.Generator(device="cpu").manual_seed(20260713)
    waveforms = torch.randn(batch_size, waveform_samples, generator=generator)
    rir = torch.from_numpy(samples.astype(np.float32, copy=False)).unsqueeze(0)
    output = reverberate(waveforms, rir, rescale_amp="avg")
    expected_shape = (batch_size, waveform_samples)
    if tuple(output.shape) != expected_shape:
        raise ValueError(
            f"reverberated shape {tuple(output.shape)} != {expected_shape}"
        )
    if not bool(torch.isfinite(output).all()):
        raise ValueError("reverberated output contains non-finite samples")
    energy = float(torch.sum(torch.square(output)).item())
    if energy <= 0.0:
        raise ValueError("reverberated output has no energy")
    return {"shape": list(output.shape), "finite": True, "energy": energy}


def validate_manifest(
    manifest_path: Path,
    *,
    required_rate: int,
    minimum_duration_ms: float,
    maximum_duration_ms: float,
    minimum_rms_dbfs: float,
    batch_size: int,
    waveform_samples: int,
    run_speechbrain: bool,
) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "embry.rir_normalization_receipt.v1":
        raise ValueError("unsupported normalization receipt schema")
    if manifest.get("status") != "PASS" or manifest.get("failed_gates"):
        raise ValueError("normalization receipt is not passing")

    expected_outputs = manifest.get("counts", {}).get("outputs")
    rows: list[dict[str, Any]] = []
    observed_hashes: set[str] = set()
    for source in manifest.get("sources", []):
        source_frames = int(source["source_frames"])
        source_rate = int(source["source_rate_hz"])
        expected_frames = math.ceil(source_frames * required_rate / source_rate)
        for declared in source.get("outputs", []):
            path = Path(declared["path"])
            if not path.is_file():
                raise ValueError(f"missing derived RIR: {path}")
            actual_hash = sha256_file(path)
            if actual_hash != declared["sha256"]:
                raise ValueError(f"hash mismatch: {path}")
            if actual_hash in observed_hashes:
                raise ValueError(f"duplicate derived RIR hash: {path}")
            observed_hashes.add(actual_hash)
            samples, sample_rate = sf.read(path, dtype="float64", always_2d=True)
            if sample_rate != required_rate:
                raise ValueError(f"unexpected sample rate for {path}: {sample_rate}")
            if samples.shape[1] != 1:
                raise ValueError(f"derived RIR is not mono: {path}")
            if abs(samples.shape[0] - expected_frames) > 1:
                raise ValueError(f"duration ratio mismatch: {path}")
            if samples.size == 0 or not np.isfinite(samples).all():
                raise ValueError(f"invalid sample data: {path}")
            peak = float(np.max(np.abs(samples)))
            rms = float(np.sqrt(np.mean(np.square(samples[:, 0]))))
            rms_dbfs = 20.0 * math.log10(max(rms, np.finfo(np.float64).tiny))
            duration_ms = samples.shape[0] * 1000 / sample_rate
            if not minimum_duration_ms <= duration_ms <= maximum_duration_ms:
                raise ValueError(f"duration outside bounds: {path}")
            if peak <= 0.0 or peak > 1.0:
                raise ValueError(f"invalid peak: {path}")
            if rms_dbfs < minimum_rms_dbfs:
                raise ValueError(f"RIR is effectively silent: {path}")
            probe = (
                speechbrain_probe(
                    samples[:, 0],
                    batch_size=batch_size,
                    waveform_samples=waveform_samples,
                )
                if run_speechbrain
                else {"skipped": True}
            )
            rows.append(
                {
                    "path": str(path.resolve()),
                    "sha256": actual_hash,
                    "sample_rate_hz": sample_rate,
                    "channels": samples.shape[1],
                    "frames": samples.shape[0],
                    "duration_ms": round(duration_ms, 3),
                    "peak": peak,
                    "rms_dbfs": round(rms_dbfs, 6),
                    "speechbrain_probe": probe,
                }
            )

    if not rows or len(rows) != expected_outputs:
        raise ValueError(
            f"manifest declares {expected_outputs} outputs but validated {len(rows)}"
        )
    return {
        "schema": "embry.rir_preflight_receipt.v1",
        "status": "PASS",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "normalization_receipt": {
            "path": str(manifest_path),
            "sha256": sha256_file(manifest_path),
        },
        "speechbrain_exercised": run_speechbrain,
        "counts": {"validated": len(rows), "failed": 0},
        "outputs": rows,
        "failed_gates": [],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--require-rate", type=int, default=16_000)
    parser.add_argument("--minimum-duration-ms", type=float, default=20.0)
    parser.add_argument("--maximum-duration-ms", type=float, default=12_000.0)
    parser.add_argument("--minimum-rms-dbfs", type=float, default=-90.0)
    parser.add_argument("--reverberate-batch-size", type=int, default=16)
    parser.add_argument("--reverberate-samples", type=int, default=48_000)
    parser.add_argument("--skip-speechbrain", action="store_true")
    parser.add_argument(
        "--compat-module-dir",
        type=Path,
        help="Directory containing the trainer's compat.py; applied before SpeechBrain import.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    compat_applied = False
    if args.compat_module_dir:
        sys.path.insert(0, str(args.compat_module_dir.resolve()))
        import compat

        failures = {
            name: status
            for name, status in compat.apply_all().items()
            if "FAIL" in status
        }
        if failures:
            raise RuntimeError(f"trainer compatibility patches failed: {failures}")
        compat_applied = True
    receipt = validate_manifest(
        args.manifest,
        required_rate=args.require_rate,
        minimum_duration_ms=args.minimum_duration_ms,
        maximum_duration_ms=args.maximum_duration_ms,
        minimum_rms_dbfs=args.minimum_rms_dbfs,
        batch_size=args.reverberate_batch_size,
        waveform_samples=args.reverberate_samples,
        run_speechbrain=not args.skip_speechbrain,
    )
    receipt["trainer_compat_applied"] = compat_applied
    atomic_json(args.receipt.resolve(), receipt)
    print(json.dumps(receipt["counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
