"""Seed-VC singing voice conversion wrapper."""

from __future__ import annotations

import glob
import os
import subprocess
from pathlib import Path

DEFAULT_SEEDVC_DIR = Path(
    os.environ.get("SEEDVC_DIR", "/mnt/storage12tb/tools/seed-vc")
)


def seedvc_dir(path: str | Path | None = None) -> Path:
    return Path(path or DEFAULT_SEEDVC_DIR)


def inference_script(path: str | Path | None = None) -> Path:
    script = seedvc_dir(path) / "inference.py"
    if not script.is_file():
        raise FileNotFoundError(
            f"Seed-VC inference.py not found at {script}. "
            "Clone https://github.com/Plachtaa/seed-vc and set SEEDVC_DIR."
        )
    return script


def convert_hum(
    source_hum: Path,
    target_ref: Path,
    out_dir: Path,
    *,
    seedvc_root: str | Path | None = None,
    diffusion_steps: int = 45,
    length_adjust: float = 1.0,
    inference_cfg_rate: float = 0.7,
    semi_tone_shift: int = 0,
    fp16: bool | None = None,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    script = inference_script(seedvc_root)

    python_bin = os.environ.get("SEEDVC_PYTHON")
    if not python_bin:
        venv_py = seedvc_dir(seedvc_root) / ".venv" / "bin" / "python"
        python_bin = str(venv_py) if venv_py.is_file() else "python"

    if fp16 is None:
        fp16 = os.environ.get("SEEDVC_FP16", "0") == "1"
    cmd = [
        python_bin,
        str(script),
        "--source",
        str(source_hum),
        "--target",
        str(target_ref),
        "--output",
        str(out_dir),
        "--diffusion-steps",
        str(diffusion_steps),
        "--length-adjust",
        str(length_adjust),
        "--inference-cfg-rate",
        str(inference_cfg_rate),
        "--f0-condition",
        "True",
        "--auto-f0-adjust",
        "False",
        "--semi-tone-shift",
        str(semi_tone_shift),
        "--fp16",
        "True" if fp16 else "False",
    ]

    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    env["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(seedvc_dir(seedvc_root)), env=env)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip()[-500:]
        raise RuntimeError(f"Seed-VC conversion failed: {tail}")

    wavs = sorted(glob.glob(str(out_dir / "*.wav")))
    if not wavs:
        raise FileNotFoundError(f"Seed-VC produced no WAV files in {out_dir}")
    return Path(wavs[-1])
