#!/usr/bin/env python3
"""probe_lipsync_local - scripts.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any


ROOTS = [
    Path("/home/graham/workspace/experiments"),
    Path("/mnt/storage12tb/models"),
    Path("/mnt/storage12tb/comfyui"),
    Path("/mnt/storage12tb/skills/persona-dream"),
]

CANDIDATE_DIR_NAMES = {
    "LatentSync": ["LatentSync", "latentsync"],
    "Wav2Lip": ["Wav2Lip", "wav2lip"],
    "MuseTalk": ["MuseTalk", "musetalk"],
    "ComfyUI_wav2lip": ["ComfyUI_wav2lip", "ComfyUI-Wav2Lip"],
}


def run(args: list[str], timeout: float = 20.0) -> dict[str, Any]:
    try:
        proc = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
        return {
            "args": args,
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
            "status": "ok" if proc.returncode == 0 else "error",
        }
    except Exception as exc:
        return {"args": args, "status": "error", "error": str(exc)}


def find_dirs() -> dict[str, list[str]]:
    found = {name: [] for name in CANDIDATE_DIR_NAMES}
    for root in ROOTS:
        if not root.exists():
            continue
        for dirpath, dirnames, _filenames in os.walk(root, onerror=lambda _err: None):
            path = Path(dirpath)
            depth = len(path.relative_to(root).parts) if path != root else 0
            if depth > 5:
                dirnames[:] = []
                continue
            lower = path.name.lower()
            for candidate, names in CANDIDATE_DIR_NAMES.items():
                if lower in {n.lower() for n in names}:
                    found[candidate].append(str(path))
            dirnames[:] = [name for name in dirnames if not name.startswith(".git")]
    return found


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Probe local open-source lip-sync route readiness.")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    modules = ["torch", "cv2", "numpy", "insightface", "ffmpeg", "librosa", "whisper"]
    receipt = {
        "schema": "persona_dream.local_lipsync_readiness.v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "candidate_dirs": find_dirs(),
        "python_modules": {name: bool(importlib.util.find_spec(name)) for name in modules},
        "executables": {name: shutil.which(name) for name in ["ffmpeg", "ffprobe", "docker", "nvidia-smi", "git"]},
        "docker_images": run(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}\t{{.ID}}\t{{.Size}}"], timeout=20),
        "nvidia_smi": run(["nvidia-smi", "--query-gpu=name,memory.total,memory.used,driver_version", "--format=csv,noheader"], timeout=12),
        "route_assessment": {
            "LatentSync": "preferred local/open-source repair candidate; not runnable until repo/checkpoints/env are present",
            "Wav2Lip": "baseline local repair candidate; not runnable until repo/checkpoint/env are present",
            "MuseTalk": "higher-quality comparison candidate; not runnable until repo/checkpoint/env are present",
        },
    }
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
