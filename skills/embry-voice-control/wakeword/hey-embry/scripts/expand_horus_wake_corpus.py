#!/usr/bin/env python3
"""Materialize deterministic, ASR-admitted Horus wake corpus derivatives."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import scipy
from scipy.signal import butter, fftconvolve, sosfilt
import soundfile as sf


ROOT = Path(__file__).resolve().parent
GENERATOR_SPEC = importlib.util.spec_from_file_location(
    "generate_horus_corpus", ROOT / "generate_horus_corpus.py"
)
assert GENERATOR_SPEC and GENERATOR_SPEC.loader
GENERATOR = importlib.util.module_from_spec(GENERATOR_SPEC)
sys.modules[GENERATOR_SPEC.name] = GENERATOR
GENERATOR_SPEC.loader.exec_module(GENERATOR)

SPLITS = (
    "positive_train",
    "positive_validation",
    "negative_train",
    "negative_validation",
)


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


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


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_assets(path: Path, *, kind: str, split: str) -> list[dict[str, Any]]:
    value = load_json(path)
    if value.get("schema") != "embry.augmentation_asset_manifest.v1":
        raise ValueError(f"unsupported asset manifest: {path}")
    if value.get("kind") != kind or value.get("split") != split:
        raise ValueError(f"asset manifest kind/split mismatch: {path}")
    rows = value.get("assets", [])
    if not rows:
        raise ValueError(f"empty asset manifest: {path}")
    for row in rows:
        if sha256_file(Path(row["path"])) != row["sha256"]:
            raise ValueError(f"asset hash mismatch: {row['path']}")
    return rows


def normalize_base(path: Path, *, rate: int) -> np.ndarray:
    samples, source_rate = sf.read(path, dtype="float64", always_2d=True)
    samples = np.mean(samples, axis=1)
    if source_rate != rate:
        divisor = math.gcd(source_rate, rate)
        samples = scipy.signal.resample_poly(
            samples, rate // divisor, source_rate // divisor
        )
    if samples.size == 0 or not np.isfinite(samples).all():
        raise ValueError(f"invalid base audio: {path}")
    return samples


def pitch_preserving_speed(
    samples: np.ndarray, *, rate: int, speed: float, ffmpeg: str
) -> np.ndarray:
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "source.wav"
        output = Path(directory) / "output.wav"
        sf.write(source, samples, rate, subtype="PCM_16")
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source),
                "-af",
                f"atempo={speed:.6f}",
                "-ar",
                str(rate),
                "-ac",
                "1",
                str(output),
            ],
            check=True,
        )
        result, output_rate = sf.read(output, dtype="float64", always_2d=True)
    if output_rate != rate:
        raise ValueError("ffmpeg speed output rate mismatch")
    return result[:, 0]


def apply_rir(samples: np.ndarray, row: dict[str, Any]) -> np.ndarray:
    rir, rate = sf.read(row["path"], dtype="float64", always_2d=True)
    if rate != 16_000 or rir.shape[1] != 1:
        raise ValueError("RIR must be mono 16 kHz")
    return fftconvolve(samples, rir[:, 0], mode="full")


def apply_noise(
    samples: np.ndarray, row: dict[str, Any], *, snr_db: float, seed: int
) -> tuple[np.ndarray, int]:
    noise, rate = sf.read(row["path"], dtype="float64", always_2d=True)
    noise = np.mean(noise, axis=1)
    if rate != 16_000:
        divisor = math.gcd(rate, 16_000)
        noise = scipy.signal.resample_poly(
            noise, 16_000 // divisor, rate // divisor
        )
    if noise.size == 0 or not np.isfinite(noise).all():
        raise ValueError("invalid noise asset")
    rng = np.random.default_rng(seed)
    offset = int(rng.integers(0, max(1, noise.size)))
    indices = (np.arange(samples.size) + offset) % noise.size
    segment = noise[indices]
    signal_rms = float(np.sqrt(np.mean(np.square(samples))))
    noise_rms = float(np.sqrt(np.mean(np.square(segment))))
    if signal_rms <= 0 or noise_rms <= 0:
        raise ValueError("silent signal or noise")
    scaled = segment * (signal_rms / (10 ** (snr_db / 20)) / noise_rms)
    return samples + scaled, offset


def apply_eq(
    samples: np.ndarray, *, highpass_hz: float, lowpass_hz: float, gain_db: float
) -> np.ndarray:
    high = butter(2, highpass_hz, "highpass", fs=16_000, output="sos")
    low = butter(2, lowpass_hz, "lowpass", fs=16_000, output="sos")
    filtered = sosfilt(low, sosfilt(high, samples))
    return filtered * (10 ** (gain_db / 20))


def deterministic_recipe(
    *, split: str, base_id: str, variant_index: int, attempt_index: int
) -> tuple[int, list[str], dict[str, float]]:
    seed = int(
        hashlib.sha256(
            f"{split}:{base_id}:{variant_index}:{attempt_index}".encode()
        ).hexdigest()[:16],
        16,
    )
    rng = np.random.default_rng(seed)
    families = (
        ("speed", "gain"),
        ("rir", "gain"),
        ("rir", "noise"),
        ("eq", "gain"),
        ("speed", "rir", "noise"),
    )
    chain = list(families[(variant_index + attempt_index - 1) % len(families)])
    values = {
        "speed": float(rng.uniform(0.9, 1.1)),
        "gain_db": float(rng.uniform(-9.0, 3.0)),
        "snr_db": float(rng.uniform(8.0, 30.0)),
        "highpass_hz": float(rng.uniform(40.0, 180.0)),
        "lowpass_hz": float(rng.uniform(5_500.0, 7_500.0)),
        "eq_gain_db": float(rng.uniform(-6.0, 6.0)),
    }
    return seed, chain, values


def apply_recipe(
    samples: np.ndarray,
    *,
    rate: int,
    seed: int,
    chain: list[str],
    values: dict[str, float],
    rirs: list[dict[str, Any]],
    noises: list[dict[str, Any]],
    ffmpeg: str,
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    result = samples.copy()
    details: list[dict[str, Any]] = []
    for position, name in enumerate(chain):
        if name == "speed":
            result = pitch_preserving_speed(
                result, rate=rate, speed=values["speed"], ffmpeg=ffmpeg
            )
            details.append({"name": name, "factor": values["speed"]})
        elif name == "gain":
            result *= 10 ** (values["gain_db"] / 20)
            details.append({"name": name, "db": values["gain_db"]})
        elif name == "rir":
            row = rirs[(seed + position) % len(rirs)]
            result = apply_rir(result, row)
            details.append({"name": name, "sha256": row["sha256"]})
        elif name == "noise":
            row = noises[(seed + position) % len(noises)]
            result, offset = apply_noise(
                result, row, snr_db=values["snr_db"], seed=seed + position
            )
            details.append(
                {
                    "name": name,
                    "sha256": row["sha256"],
                    "snr_db": values["snr_db"],
                    "offset_samples": offset,
                }
            )
        elif name == "eq":
            result = apply_eq(
                result,
                highpass_hz=values["highpass_hz"],
                lowpass_hz=values["lowpass_hz"],
                gain_db=values["eq_gain_db"],
            )
            details.append(
                {
                    "name": name,
                    "highpass_hz": values["highpass_hz"],
                    "lowpass_hz": values["lowpass_hz"],
                    "gain_db": values["eq_gain_db"],
                }
            )
        else:
            raise ValueError(f"unsupported transform: {name}")
    peak = float(np.max(np.abs(result)))
    maximum_peak = 10 ** (-1 / 20)
    if peak > maximum_peak:
        raise ValueError(f"transform clips policy peak: {peak}")
    if result.size == 0 or not np.isfinite(result).all():
        raise ValueError("invalid transformed audio")
    return result, details


def allocation(base_count: int, target_count: int, cap: int) -> list[int]:
    if target_count < base_count or target_count > base_count * cap:
        raise ValueError("target cannot be allocated under per-base cap")
    counts = [target_count // base_count] * base_count
    for index in range(target_count % base_count):
        counts[index] += 1
    if max(counts) > cap or min(counts) < 1 or sum(counts) != target_count:
        raise ValueError("invalid per-base allocation")
    return counts


def transcript_accepted(record: dict[str, Any], transcript: str) -> bool:
    if record["label"] == "positive":
        return GENERATOR.positive_transcript_accepted(transcript)
    return GENERATOR.negative_transcript_accepted(
        transcript, prompt=record["prompt"]
    )


def expand(args: argparse.Namespace) -> dict[str, Any]:
    policy = load_json(args.policy.resolve())
    base_records = [
        row
        for row in load_jsonl(args.base_manifest.resolve())
        if row.get("accepted") and row.get("audio_path")
    ]
    targets = {
        "positive_train": args.positive_train_target,
        "positive_validation": args.positive_validation_target,
        "negative_train": args.negative_train_target,
        "negative_validation": args.negative_validation_target,
    }
    base_targets = {
        "positive_train": 200,
        "positive_validation": 75,
        "negative_train": 260,
        "negative_validation": 90,
    }
    assets = {
        "train": {
            "rirs": load_assets(args.train_rir_manifest, kind="rir", split="train"),
            "noises": load_assets(
                args.train_noise_manifest, kind="noise", split="train"
            ),
        },
        "validation": {
            "rirs": load_assets(
                args.validation_rir_manifest, kind="rir", split="validation"
            ),
            "noises": load_assets(
                args.validation_noise_manifest, kind="noise", split="validation"
            ),
        },
    }
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    records_path = output_dir / "candidate-b-records.jsonl"
    records_path.write_text("", encoding="utf-8")
    output_hashes: set[str] = set()
    final_records: list[dict[str, Any]] = []

    for split in SPLITS:
        selected = sorted(
            (row for row in base_records if row["split"] == split),
            key=lambda row: row["record_id"],
        )
        if len(selected) < base_targets[split]:
            raise ValueError(
                f"{split} has {len(selected)} bases, requires {base_targets[split]}"
            )
        selected = selected[: base_targets[split]]
        cap = policy["maximum_total_clips_per_base"][split]
        per_base = allocation(len(selected), targets[split], cap)
        split_kind = "validation" if split.endswith("validation") else "train"
        for base, clip_count in zip(selected, per_base, strict=True):
            source = Path(base["audio_path"])
            if sha256_file(source).removeprefix("sha256:") != base["audio_sha256"]:
                raise ValueError(f"base hash mismatch: {source}")
            normalized = normalize_base(source, rate=16_000)
            for variant_index in range(clip_count):
                accepted_record = None
                for attempt_index in range(args.max_variant_attempts):
                    if variant_index == 0:
                        seed, chain, values = 0, [], {}
                        transformed, details = normalized, []
                    else:
                        seed, chain, values = deterministic_recipe(
                            split=split,
                            base_id=base["record_id"],
                            variant_index=variant_index,
                            attempt_index=attempt_index,
                        )
                        try:
                            transformed, details = apply_recipe(
                                normalized,
                                rate=16_000,
                                seed=seed,
                                chain=chain,
                                values=values,
                                rirs=assets[split_kind]["rirs"],
                                noises=assets[split_kind]["noises"],
                                ffmpeg=args.ffmpeg,
                            )
                        except ValueError:
                            continue
                    variant_id = hashlib.sha256(
                        canonical_json(
                            {
                                "base_record_id": base["record_id"],
                                "variant_index": variant_index,
                                "seed": seed,
                                "details": details,
                            }
                        )
                    ).hexdigest()[:24]
                    destination = output_dir / "audio" / split / f"{variant_id}.wav"
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    sf.write(destination, transformed, 16_000, subtype="PCM_16")
                    output_hash = sha256_file(destination)
                    if output_hash in output_hashes:
                        destination.unlink()
                        continue
                    if variant_index == 0:
                        transcript = str(base["transcript"])
                        admission_source = "accepted_base_receipt"
                    else:
                        transcript_response = GENERATOR.multipart_transcribe(
                            f"{args.whisper_url.rstrip('/')}/v1/audio/transcriptions",
                            audio=destination.read_bytes(),
                            filename=destination.name,
                            api_key=args.whisper_api_key,
                            timeout=args.timeout,
                        )
                        transcript = str(transcript_response.get("text", ""))
                        admission_source = "post_transform_whisper"
                    if not transcript_accepted(base, transcript):
                        destination.unlink()
                        continue
                    info = sf.info(destination)
                    accepted_record = {
                        "schema": "embry.horus_wake_candidate_b_record.v1",
                        "variant_id": variant_id,
                        "split": split,
                        "label": base["label"],
                        "prompt": base["prompt"],
                        "base_record_id": base["record_id"],
                        "base_audio_sha256": f"sha256:{base['audio_sha256']}",
                        "orpheus_request_id": base["request_id"],
                        "variant_index": variant_index,
                        "identity": variant_index == 0,
                        "transform_seed": seed,
                        "transform_chain": details,
                        "transform_recipe_sha256": sha256_bytes(canonical_json(details)),
                        "path": str(destination),
                        "sha256": output_hash,
                        "bytes": destination.stat().st_size,
                        "pcm_sha256": sha256_bytes(
                            np.asarray(
                                sf.read(destination, dtype="int16")[0], dtype="<i2"
                            ).tobytes()
                        ),
                        "sample_rate_hz": info.samplerate,
                        "channels": info.channels,
                        "subtype": info.subtype,
                        "frames": info.frames,
                        "duration_ms": round(info.frames * 1000 / info.samplerate, 3),
                        "post_transform_asr_transcript": transcript,
                        "post_transform_asr_accepted": True,
                        "asr_admission_source": admission_source,
                    }
                    output_hashes.add(output_hash)
                    break
                if accepted_record is None:
                    raise ValueError(
                        f"no accepted recipe for {base['record_id']} variant {variant_index}"
                    )
                final_records.append(accepted_record)
                with records_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(accepted_record, sort_keys=True) + "\n")

    final_counts = {
        split: sum(row["split"] == split for row in final_records)
        for split in SPLITS
    }
    base_counts = {
        split: len({row["base_record_id"] for row in final_records if row["split"] == split})
        for split in SPLITS
    }
    return {
        "schema": "embry.horus_wake_candidate_b_corpus.v1",
        "status": "PASS",
        "candidate_id": "hey_embry_v1b_horus_augmented",
        "live": True,
        "mocked": False,
        "base_counts": {**base_counts, "total": sum(base_counts.values())},
        "final_counts": {**final_counts, "total": sum(final_counts.values())},
        "derived_counts": {
            **{
                split: final_counts[split] - base_counts[split]
                for split in SPLITS
            },
            "total": sum(final_counts.values()) - sum(base_counts.values()),
        },
        "admission": {
            "positive_alias_rule_id": "whisper_orthographic_embrie_to_embree_v1",
            "negative_phrase_specific_aliases": True,
            "all_base_clips_asr_accepted": True,
            "all_derived_clips_asr_accepted": True,
        },
        "augmentation": {
            "policy_id": policy["policy_id"],
            "identity_clip_per_base": True,
            "pitch_shift_used": False,
            "formant_shift_used": False,
            "lossy_codec_used": False,
            "maximum_non_identity_transforms_per_clip": 3,
            "toolchain": {
                "python": platform.python_version(),
                "numpy": np.__version__,
                "scipy": scipy.__version__,
                "ffmpeg": subprocess.run(
                    [args.ffmpeg, "-version"], capture_output=True, text=True, check=True
                ).stdout.splitlines()[0],
            },
        },
        "physical_sets": {
            "used_in_corpus": False,
            "development_set_modified": False,
            "final_qualification_set_modified": False,
        },
        "records_manifest": {
            "path": str(records_path),
            "sha256": sha256_file(records_path),
        },
        "failed_gates": [],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-manifest", type=Path, required=True)
    parser.add_argument("--positive-train-target", type=int, default=1500)
    parser.add_argument("--positive-validation-target", type=int, default=350)
    parser.add_argument("--negative-train-target", type=int, default=2000)
    parser.add_argument("--negative-validation-target", type=int, default=400)
    parser.add_argument("--train-rir-manifest", type=Path, required=True)
    parser.add_argument("--validation-rir-manifest", type=Path, required=True)
    parser.add_argument("--train-noise-manifest", type=Path, required=True)
    parser.add_argument("--validation-noise-manifest", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--whisper-url", default="http://127.0.0.1:9000")
    parser.add_argument("--whisper-api-key-file", type=Path, required=True)
    parser.add_argument("--ffmpeg", default="/usr/bin/ffmpeg")
    parser.add_argument("--max-variant-attempts", type=int, default=12)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    args.whisper_api_key = args.whisper_api_key_file.read_text().strip()
    if not args.whisper_api_key:
        parser.error("--whisper-api-key-file is empty")
    return args


def main() -> int:
    args = parse_args()
    receipt = expand(args)
    atomic_json(args.receipt.resolve(), receipt)
    print(json.dumps(receipt["final_counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
