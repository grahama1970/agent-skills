"""tts_wavtts - persona_dream_av_bakeoff.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from .fal_utils import upload_file
from .io_utils import write_json
from .media import convert_audio_for_fal_if_needed, newest_wav_after, sha256_file


def generate_wavtts_tts(
    *,
    contract: dict[str, Any],
    shot: dict[str, Any],
    out_dir: str | Path,
    ref_audio: str | Path | None,
    ref_text: str | None,
    confirm_voice_consent: bool,
    wavtts_cwd: str | Path | None = None,
    wavtts_audio_path: str | Path | None = None,
    upload_to_fal: bool = True,
) -> dict[str, Any]:
    if not confirm_voice_consent:
        raise ValueError(
            "WavTTS voice cloning requires --confirm-voice-consent. Use only owned/licensed/consented voices."
        )

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    gen_text = shot.get("tts_text_plain") or shot["dialogue"]

    # Option A: user already generated WavTTS audio.
    if wavtts_audio_path:
        audio_path = Path(wavtts_audio_path).expanduser().resolve()
        if not audio_path.exists():
            raise FileNotFoundError(audio_path)
        cmd = None
        stdout = ""
        stderr = ""
    else:
        if not ref_audio:
            raise ValueError("--ref-audio is required for WavTTS generation.")
        if not ref_text:
            raise ValueError("--ref-text is required for WavTTS generation.")

        exe = shutil.which("wavtts_infer-cli")
        if exe is None:
            raise RuntimeError(
                "wavtts_infer-cli not found. Activate the WavTTS environment and run `pip install -e .`."
            )

        ref_audio_path = Path(ref_audio).expanduser().resolve()
        if not ref_audio_path.exists():
            raise FileNotFoundError(ref_audio_path)

        started_at = time.time()
        cwd = Path(wavtts_cwd).expanduser().resolve() if wavtts_cwd else Path.cwd()
        cmd = [
            exe,
            "--model",
            "WavTTS",
            "--ref_audio",
            str(ref_audio_path),
            "--ref_text",
            ref_text,
            "--gen_text",
            gen_text,
        ]

        completed = subprocess.run(
            cmd,
            cwd=str(cwd),
            check=False,
            capture_output=True,
            text=True,
        )
        stdout = completed.stdout
        stderr = completed.stderr

        if completed.returncode != 0:
            raise RuntimeError(
                "WavTTS failed.\n\nCOMMAND:\n"
                + " ".join(cmd)
                + "\n\nSTDOUT:\n"
                + stdout
                + "\n\nSTDERR:\n"
                + stderr
            )

        search_roots = [out_dir, cwd]
        audio_path = newest_wav_after(search_roots, started_at)
        if audio_path is None:
            raise FileNotFoundError(
                "WavTTS completed but no new .wav file was found. "
                "Run WavTTS manually and pass --wavtts-audio-path /path/to/output.wav."
            )

        # Copy to a stable location under the run.
        stable_audio = out_dir / "wavtts_audio.wav"
        if audio_path.resolve() != stable_audio.resolve():
            shutil.copy2(audio_path, stable_audio)
            audio_path = stable_audio

    fal_audio_path = convert_audio_for_fal_if_needed(audio_path, out_dir)
    audio_url = upload_file(fal_audio_path) if upload_to_fal else None

    payload = {
        "schema_version": "persona_dream_tts_result.v0.2",
        "backend": "wavtts_local",
        "contract_experiment_id": contract.get("experiment_id"),
        "shot_id": shot["shot_id"],
        "model_id": "WavTTS local CLI",
        "request": {
            "ref_audio": str(ref_audio) if ref_audio else None,
            "ref_text": ref_text,
            "gen_text": gen_text,
            "confirm_voice_consent": confirm_voice_consent,
            "wavtts_audio_path": str(wavtts_audio_path) if wavtts_audio_path else None,
        },
        "command": cmd,
        "result": {
            "stdout": stdout,
            "stderr": stderr,
        },
        "audio_path": str(audio_path),
        "audio_sha256": sha256_file(audio_path),
        "fal_audio_path": str(fal_audio_path),
        "audio_url": audio_url,
        "timestamps": None,
        "notes": [
            "WavTTS does not provide native word timestamps in this wrapper.",
            "Whisper derives transcript/timing during verification.",
            "Use only owned, licensed, or explicitly consented reference voices.",
        ],
    }
    write_json(out_dir / "tts.json", payload)
    return payload
