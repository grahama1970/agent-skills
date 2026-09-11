"""Per-use loudness fitting for filler clips (thinking hums, song hums).

Rule (human-set): fillers VARY in volume per use but are NEVER louder than the
speech around them. Target band per use: speech_ref - 5.0 .. speech_ref - 1.5 dB
mean RMS, drawn per use so repetition doesn't sound like a looped sample.

Measured 2026-09-11: Turbo Embry speech ~ -27.2 dB mean RMS; an SFX 'ponder'
render came out at -17.8 dB (9.4 dB OVER speech) — the exact robotic-loud
failure the human ear caught. This module fixes it at assembly time.

Run `python3 filler_gain.py` for the self-check.
"""
from __future__ import annotations

import random
import re
import subprocess
import tempfile
from pathlib import Path


def measure_db(wav: str | Path) -> float:
    """Mean volume (RMS dB) via ffmpeg volumedetect."""
    r = subprocess.run(["ffmpeg", "-i", str(wav), "-af", "volumedetect",
                        "-f", "null", "-"], capture_output=True, text=True, timeout=60)
    m = re.search(r"mean_volume:\s*(-?[\d.]+)\s*dB", r.stderr)
    if not m:
        raise ValueError(f"volumedetect_failed: {wav}")
    return float(m.group(1))


def draw_target_db(ref_db: float, floor: float = 1.5, ceil: float = 5.0,
                   rng: random.Random | None = None) -> float:
    """Per-use target inside [ref-ceil, ref-floor]; vary, never above ref-floor."""
    rng = rng or random.Random()
    return rng.uniform(ref_db - ceil, ref_db - floor)


def apply_gain(wav: str | Path, out: str | Path, gain_db: float) -> Path:
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(wav),
                    "-af", f"volume={gain_db:+.2f}dB", "-ar", "24000", "-ac", "1",
                    "-c:a", "pcm_s16le", str(out)], check=True)
    return Path(out)


def fit_filler(wav: str | Path, ref_db: float, out: str | Path | None = None,
               rng: random.Random | None = None) -> Path:
    """Gain-fit one filler into the under-speech band for this use."""
    cur = measure_db(wav)
    target = draw_target_db(ref_db, rng=rng)
    out = Path(out) if out else Path(tempfile.mkstemp(suffix=".wav")[1])
    return apply_gain(wav, out, target - cur)


def demo() -> None:
    ref = -27.2
    rng = random.Random(7)
    # a clip measured over speech gets pulled down into the band; one under gets lifted
    for start in (-17.8, -32.0):
        target = draw_target_db(ref, rng=rng)
        assert ref - 5.01 <= target <= ref - 1.49, target  # in band, under speech
        assert target < ref, "never louder than speech"
    # round-trip on a generated tone (no external files needed)
    import math, struct, wave
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tone = f.name
    with wave.open(tone, "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
        w.writeframes(b"".join(struct.pack("<h", int(0.2 * 32767 * math.sin(2 * math.pi * 220 * t / 24000)))
                               for t in range(24000)))
    fitted = fit_filler(tone, ref, rng=random.Random(1))
    got = measure_db(fitted)
    assert ref - 5.5 <= got <= ref - 1.0, f"fitted {got} outside band vs ref {ref}"
    # variation: two draws differ
    t1, t2 = draw_target_db(ref, rng=random.Random(1)), draw_target_db(ref, rng=random.Random(2))
    assert t1 != t2 or draw_target_db(ref, rng=random.Random(3)) != t1, "no volume variation"
    print("filler_gain.py self-check: PASS")


if __name__ == "__main__":
    demo()
