"""Audio-to-MIDI melody extraction via Basic Pitch."""

from __future__ import annotations

import glob
from pathlib import Path

from basic_pitch import ICASSP_2022_MODEL_PATH
from basic_pitch.inference import predict_and_save


def transcribe_to_midi(audio_path: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    predict_and_save(
        [str(audio_path)],
        str(out_dir),
        True,
        False,
        False,
        True,
        ICASSP_2022_MODEL_PATH,
    )

    candidates = sorted(glob.glob(str(out_dir / "*.mid"))) + sorted(glob.glob(str(out_dir / "*.midi")))
    if not candidates:
        raise FileNotFoundError(f"Basic Pitch did not produce MIDI for {audio_path}")
    return Path(candidates[0])
