#!/usr/bin/env python3
"""Hash and describe an existing OpenWakeWord generated WAV corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import soundfile as sf


SPLITS = {
    "positive_train": ("positive", "train"),
    "positive_test": ("positive", "validation"),
    "negative_train": ("negative", "train"),
    "negative_test": ("negative", "validation"),
}


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


def freeze(root: Path, candidate_id: str) -> dict[str, Any]:
    root = root.resolve()
    files: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    total_bytes = 0
    seen_hashes: dict[str, str] = {}
    cross_split_duplicates: list[dict[str, str]] = []
    for directory, (audio_class, split) in SPLITS.items():
        paths = sorted((root / directory).glob("*.wav"))
        if not paths:
            raise ValueError(f"no WAV files found in {root / directory}")
        counts[directory] = len(paths)
        for path in paths:
            info = sf.info(path)
            digest = sha256_file(path)
            prior = seen_hashes.get(digest)
            if prior:
                cross_split_duplicates.append(
                    {"sha256": digest, "first_path": prior, "duplicate_path": str(path)}
                )
            else:
                seen_hashes[digest] = str(path)
            size = path.stat().st_size
            total_bytes += size
            files.append(
                {
                    "path": str(path),
                    "relative_path": str(path.relative_to(root)),
                    "class": audio_class,
                    "split": split,
                    "sha256": digest,
                    "bytes": size,
                    "duration_ms": round(info.frames * 1000 / info.samplerate, 3),
                    "sample_rate_hz": info.samplerate,
                    "channels": info.channels,
                    "frames": info.frames,
                    "generation_seed": None,
                    "source_voice": None,
                }
            )
    return {
        "schema": "embry.openwakeword_source_corpus.v1",
        "candidate_id": candidate_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "counts": counts,
        "total_files": len(files),
        "total_bytes": total_bytes,
        "files": files,
        "cross_split_duplicates": cross_split_duplicates,
        "provenance_limitations": [
            "existing filenames do not encode generation seeds",
            "existing filenames do not encode source voice identifiers",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-total", type=int)
    args = parser.parse_args()
    manifest = freeze(args.root, args.candidate_id)
    if args.expected_total is not None and manifest["total_files"] != args.expected_total:
        raise ValueError(
            f"expected {args.expected_total} files, found {manifest['total_files']}"
        )
    atomic_json(args.output.resolve(), manifest)
    print(
        json.dumps(
            {
                "total_files": manifest["total_files"],
                "total_bytes": manifest["total_bytes"],
                "cross_split_duplicates": len(manifest["cross_split_duplicates"]),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

