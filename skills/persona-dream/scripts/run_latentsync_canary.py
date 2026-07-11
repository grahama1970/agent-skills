#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run(args: list[str], cwd: Path | None = None, timeout: float = 60.0) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        return {
            "args": args,
            "cwd": str(cwd) if cwd else None,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "status": "ok" if proc.returncode == 0 else "error",
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "args": args,
            "cwd": str(cwd) if cwd else None,
            "status": "timeout",
            "timeout": timeout,
            "stdout": exc.stdout,
            "stderr": exc.stderr,
        }
    except Exception as exc:
        return {"args": args, "cwd": str(cwd) if cwd else None, "status": "error", "error": str(exc)}


def ffprobe(path: Path) -> dict[str, Any]:
    result = run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)])
    if result.get("returncode") == 0:
        try:
            return json.loads(result["stdout"])
        except Exception as exc:
            return {"status": "parse_error", "error": str(exc), "raw": result}
    return {"status": "error", "raw": result}


def gpu_memory() -> dict[str, Any]:
    result = run([
        "nvidia-smi",
        "--query-gpu=memory.total,memory.used,memory.free",
        "--format=csv,noheader,nounits",
    ])
    if result.get("returncode") != 0:
        return {"status": "error", "raw": result}
    line = (result.get("stdout") or "").strip().splitlines()[0]
    try:
        total, used, free = [int(part.strip()) for part in line.split(",")]
        return {"status": "ok", "total_mib": total, "used_mib": used, "free_mib": free}
    except Exception as exc:
        return {"status": "parse_error", "error": str(exc), "raw": result}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one LatentSync local lip-sync canary with receipts.")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--latentsync-root", type=Path, default=Path("/home/graham/workspace/experiments/LatentSync"))
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--guidance-scale", type=float, default=1.5)
    parser.add_argument("--min-free-vram-mib", type=int, default=18000)
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    receipts = args.out_dir / "receipts"
    output_video = args.out_dir / "output" / f"{args.case_id}_latentsync.mp4"
    output_video.parent.mkdir(parents=True, exist_ok=True)
    receipts.mkdir(parents=True, exist_ok=True)
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    config = args.latentsync_root / "configs/unet/stage2_512.yaml"
    ckpt = args.latentsync_root / "checkpoints/latentsync_unet.pt"
    whisper = args.latentsync_root / "checkpoints/whisper/tiny.pt"
    prereq_errors: list[str] = []
    for label, path in {
        "video": args.video,
        "audio": args.audio,
        "python": args.python,
        "latentsync_root": args.latentsync_root,
        "unet_config": config,
        "checkpoint": ckpt,
        "whisper": whisper,
    }.items():
        if not path.exists():
            prereq_errors.append(f"missing {label}: {path}")
    gpu = gpu_memory()
    if gpu.get("status") == "ok" and gpu.get("free_mib", 0) < args.min_free_vram_mib:
        prereq_errors.append(
            f"insufficient free GPU memory: {gpu.get('free_mib')} MiB free, "
            f"requires at least {args.min_free_vram_mib} MiB"
        )

    command = [
        str(args.python),
        "-m",
        "scripts.inference",
        "--unet_config_path",
        str(config),
        "--inference_ckpt_path",
        str(ckpt),
        "--inference_steps",
        str(args.steps),
        "--guidance_scale",
        str(args.guidance_scale),
        "--enable_deepcache",
        "--video_path",
        str(args.video),
        "--audio_path",
        str(args.audio),
        "--video_out_path",
        str(output_video),
    ]
    request = {
        "schema": "persona_dream.latentsync_canary_request.v1",
        "created_at": started_at,
        "case_id": args.case_id,
        "video_path": str(args.video),
        "audio_path": str(args.audio),
        "output_video": str(output_video),
        "latentsync_root": str(args.latentsync_root),
        "python": str(args.python),
        "command": command,
        "dry_run": args.dry_run,
        "gpu_memory": gpu,
        "min_free_vram_mib": args.min_free_vram_mib,
        "inputs": {
            "video_sha256": sha256(args.video) if args.video.exists() else None,
            "audio_sha256": sha256(args.audio) if args.audio.exists() else None,
            "video_ffprobe": ffprobe(args.video) if args.video.exists() else None,
            "audio_ffprobe": ffprobe(args.audio) if args.audio.exists() else None,
        },
    }
    write_json(receipts / "latentsync_request.json", request)

    if prereq_errors or args.dry_run:
        verdict = {
            "schema": "persona_dream.latentsync_canary_verdict.v1",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "case_id": args.case_id,
            "status": "blocked" if prereq_errors else "dry_run",
            "reasons": prereq_errors or ["dry_run requested"],
            "output_video": None,
        }
        write_json(receipts / "canary_verdict.json", verdict)
        print(json.dumps(verdict, indent=2))
        return 2 if prereq_errors else 0

    result = run(command, cwd=args.latentsync_root, timeout=args.timeout)
    write_json(receipts / "latentsync_command.json", result)
    (receipts / "latentsync_stdout.log").write_text(result.get("stdout") or "")
    (receipts / "latentsync_stderr.log").write_text(result.get("stderr") or "")
    if output_video.exists():
        write_json(receipts / "output_ffprobe.json", ffprobe(output_video))
        verdict = {
            "schema": "persona_dream.latentsync_canary_verdict.v1",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "case_id": args.case_id,
            "status": "output_ready" if result.get("returncode") == 0 else "output_created_with_command_error",
            "returncode": result.get("returncode"),
            "output_video": str(output_video),
            "output_sha256": sha256(output_video),
        }
    else:
        verdict = {
            "schema": "persona_dream.latentsync_canary_verdict.v1",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "case_id": args.case_id,
            "status": "failed",
            "returncode": result.get("returncode"),
            "reasons": ["output video was not created"],
            "output_video": None,
        }
    write_json(receipts / "canary_verdict.json", verdict)
    print(json.dumps(verdict, indent=2))
    return 0 if verdict.get("status") == "output_ready" else 1


if __name__ == "__main__":
    sys.exit(main())
