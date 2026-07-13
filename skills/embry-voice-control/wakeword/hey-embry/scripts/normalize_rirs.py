#!/usr/bin/env python3
"""Create immutable mono 16 kHz room-impulse-response derivatives."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import scipy
from scipy.signal import resample_poly
import soundfile as sf


SCHEMA = "embry.rir_normalization_receipt.v1"
SUPPORTED_SUFFIXES = {".wav", ".flac"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def safe_stem(path: Path) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", path.stem).strip("._")
    if not value:
        raise ValueError(f"invalid source filename: {path.name}")
    return value


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def rms_dbfs(samples: np.ndarray) -> float:
    rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))
    return 20.0 * math.log10(max(rms, np.finfo(np.float64).tiny))


def normalize_channel(
    samples: np.ndarray,
    *,
    source_rate: int,
    target_rate: int,
    kaiser_beta: float,
    peak_target: float,
) -> tuple[np.ndarray, float]:
    if samples.ndim != 1 or samples.size == 0:
        raise ValueError("source channel must be a nonempty one-dimensional array")
    if not np.isfinite(samples).all():
        raise ValueError("source channel contains non-finite samples")

    divisor = math.gcd(source_rate, target_rate)
    resampled = resample_poly(
        samples.astype(np.float64, copy=False),
        target_rate // divisor,
        source_rate // divisor,
        window=("kaiser", kaiser_beta),
    )
    if not np.isfinite(resampled).all():
        raise ValueError("resampled channel contains non-finite samples")
    peak = float(np.max(np.abs(resampled)))
    if peak <= 0.0:
        raise ValueError("source channel is silent")
    gain = peak_target / peak
    normalized = np.clip(resampled * gain, -1.0, 1.0)
    return normalized, gain


def normalize_directory(
    input_dir: Path,
    output_dir: Path,
    *,
    target_rate: int,
    peak_target: float,
    kaiser_beta: float,
    expected_source_count: int | None,
) -> dict[str, Any]:
    input_dir = input_dir.resolve()
    output_dir = output_dir.resolve()
    sources = sorted(
        path
        for path in input_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )
    if not sources:
        raise ValueError(f"no supported RIR files found in {input_dir}")
    if expected_source_count is not None and len(sources) != expected_source_count:
        raise ValueError(
            f"expected {expected_source_count} source RIRs, found {len(sources)}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    source_rows: list[dict[str, Any]] = []
    output_hashes: set[str] = set()
    for source in sources:
        source_info = sf.info(source)
        audio, source_rate = sf.read(source, dtype="float64", always_2d=True)
        if source_rate <= 0 or source_info.frames <= 0:
            raise ValueError(f"invalid audio metadata: {source}")
        outputs: list[dict[str, Any]] = []
        for channel_index in range(audio.shape[1]):
            normalized, gain = normalize_channel(
                audio[:, channel_index],
                source_rate=source_rate,
                target_rate=target_rate,
                kaiser_beta=kaiser_beta,
                peak_target=peak_target,
            )
            destination = output_dir / (
                f"{safe_stem(source)}.ch{channel_index}.16k.mono.wav"
            )
            sf.write(destination, normalized, target_rate, subtype="PCM_16")
            written, written_rate = sf.read(
                destination, dtype="float64", always_2d=True
            )
            output_hash = sha256_file(destination)
            if output_hash in output_hashes:
                raise ValueError(f"duplicate derived RIR content: {destination}")
            output_hashes.add(output_hash)
            outputs.append(
                {
                    "source_channel": channel_index,
                    "path": str(destination),
                    "sha256": output_hash,
                    "bytes": destination.stat().st_size,
                    "sample_rate_hz": written_rate,
                    "channels": written.shape[1],
                    "frames": written.shape[0],
                    "duration_ms": round(written.shape[0] * 1000 / written_rate, 3),
                    "peak": float(np.max(np.abs(written))),
                    "rms_dbfs": round(rms_dbfs(written[:, 0]), 6),
                    "applied_gain": gain,
                }
            )
        source_rows.append(
            {
                "source_path": str(source),
                "source_sha256": sha256_file(source),
                "source_bytes": source.stat().st_size,
                "source_rate_hz": source_rate,
                "source_channels": audio.shape[1],
                "source_frames": audio.shape[0],
                "outputs": outputs,
            }
        )

    return {
        "schema": SCHEMA,
        "status": "PASS",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "toolchain": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "soundfile": sf.__version__,
        },
        "policy": {
            "target_rate_hz": target_rate,
            "channel_policy": "split",
            "resampler": "scipy.signal.resample_poly",
            "window": ["kaiser", kaiser_beta],
            "peak_target": peak_target,
            "output_subtype": "PCM_16",
            "trimmed": False,
        },
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "counts": {
            "sources": len(source_rows),
            "outputs": sum(len(row["outputs"]) for row in source_rows),
        },
        "sources": source_rows,
        "failed_gates": [],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--target-rate", type=int, default=16_000)
    parser.add_argument("--peak-target", type=float, default=0.95)
    parser.add_argument("--kaiser-beta", type=float, default=8.6)
    parser.add_argument("--expected-source-count", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.target_rate <= 0:
        raise ValueError("target rate must be positive")
    if not 0.0 < args.peak_target <= 1.0:
        raise ValueError("peak target must be in (0, 1]")
    receipt = normalize_directory(
        args.input_dir,
        args.output_dir,
        target_rate=args.target_rate,
        peak_target=args.peak_target,
        kaiser_beta=args.kaiser_beta,
        expected_source_count=args.expected_source_count,
    )
    atomic_json(args.receipt.resolve(), receipt)
    print(json.dumps(receipt["counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

