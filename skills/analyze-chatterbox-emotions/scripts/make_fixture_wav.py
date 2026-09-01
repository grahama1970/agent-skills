#!/usr/bin/env python3
"""Generate deterministic PCM WAV fixtures for voice-quality evaluation."""
from __future__ import annotations

import argparse
import math
import wave
from pathlib import Path


def write_fixture(path: Path, *, sample_rate: int = 16_000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    samples: list[int] = []

    def tone(seconds: float, hz: float, amp: float) -> None:
        count = int(seconds * sample_rate)
        for i in range(count):
            env = 0.65 + 0.35 * math.sin(2 * math.pi * 3.0 * (i / sample_rate))
            samples.append(int(32767 * amp * env * math.sin(2 * math.pi * hz * (i / sample_rate))))

    def silence(seconds: float) -> None:
        samples.extend([0] * int(seconds * sample_rate))

    tone(0.55, 220.0, 0.22)
    silence(0.42)
    tone(0.45, 246.94, 0.18)
    silence(0.18)
    tone(0.55, 196.0, 0.20)

    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(sample_rate)
        fh.writeframes(b"".join(int(x).to_bytes(2, "little", signed=True) for x in samples))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    write_fixture(args.out)
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
