#!/usr/bin/env python3
"""run_lipsync_canary - scripts.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any


MODELS = {
    "sync-v3": "fal-ai/sync-lipsync/v3",
    "kling": "fal-ai/kling-video/lipsync/audio-to-video",
}

FAL_KEY_ENV_NAMES = ("FAL_KEY", "FAL_API_KEY", "FAL_TOKEN")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run(args: list[str], timeout: float = 60.0) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            args,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        return {
            "args": args,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "status": "ok" if proc.returncode == 0 else "error",
        }
    except Exception as exc:
        return {"args": args, "status": "error", "error": str(exc)}


def ffprobe(path: Path) -> dict[str, Any]:
    result = run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)])
    if result.get("returncode") == 0:
        try:
            return json.loads(result["stdout"])
        except Exception as exc:
            return {"status": "parse_error", "error": str(exc), "raw": result}
    return {"status": "error", "raw": result}


def download(url: str, out: Path) -> dict[str, Any]:
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=300) as response:
            data = response.read()
            out.write_bytes(data)
            return {
                "status": "ok",
                "url": url,
                "output_path": str(out),
                "bytes": len(data),
                "headers": dict(response.headers.items()),
            }
    except Exception as exc:
        return {"status": "error", "url": url, "output_path": str(out), "error": str(exc)}


def detect_fal_key_env() -> tuple[bool, str | None]:
    for name in FAL_KEY_ENV_NAMES:
        value = os.environ.get(name)
        if value:
            if name != "FAL_KEY":
                os.environ["FAL_KEY"] = value
            return True, name
    return False, None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one hosted lip-sync canary with receipt artifacts.")
    parser.add_argument("--provider", choices=sorted(MODELS), required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--sync-mode", default="cut_off")
    parser.add_argument("--dry-run", action="store_true", help="Write receipts without calling the provider.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir: Path = args.out_dir
    receipts = out_dir / "receipts"
    output_video = out_dir / "output" / f"{args.case_id}_{args.provider}_lipsynced.mp4"
    receipts.mkdir(parents=True, exist_ok=True)

    model_id = MODELS[args.provider]
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    prereq_errors: list[str] = []
    if not args.video.exists():
        prereq_errors.append(f"missing video: {args.video}")
    if not args.audio.exists():
        prereq_errors.append(f"missing audio: {args.audio}")
    fal_key_present, fal_key_env_name = detect_fal_key_env()
    if not fal_key_present:
        prereq_errors.append(f"no Fal credential present in any of: {', '.join(FAL_KEY_ENV_NAMES)}")

    try:
        import fal_client  # type: ignore
    except Exception as exc:
        fal_client = None  # type: ignore
        prereq_errors.append(f"fal_client import failed: {exc}")

    request_payload = {
        "schema": "persona_dream.hosted_lipsync_canary_request.v1",
        "created_at": started_at,
        "provider": args.provider,
        "model_id": model_id,
        "case_id": args.case_id,
        "video_path": str(args.video),
        "audio_path": str(args.audio),
        "output_video": str(output_video),
        "sync_mode": args.sync_mode,
        "dry_run": args.dry_run,
        "inputs": {
            "video_sha256": sha256(args.video) if args.video.exists() else None,
            "audio_sha256": sha256(args.audio) if args.audio.exists() else None,
            "video_ffprobe": ffprobe(args.video) if args.video.exists() else None,
            "audio_ffprobe": ffprobe(args.audio) if args.audio.exists() else None,
        },
    }
    write_json(receipts / "provider_request.json", request_payload)

    readiness = {
        "schema": "persona_dream.hosted_lipsync_readiness.v1",
        "created_at": started_at,
        "provider": args.provider,
        "model_id": model_id,
        "fal_key_present": fal_key_present,
        "fal_key_env_name": fal_key_env_name,
        "accepted_fal_key_env_names": list(FAL_KEY_ENV_NAMES),
        "fal_client_importable": fal_client is not None,
        "prereq_errors": prereq_errors,
        "status": "ready" if not prereq_errors and not args.dry_run else "blocked" if prereq_errors else "dry_run",
    }
    write_json(receipts / "hosted_readiness.json", readiness)

    if prereq_errors or args.dry_run:
        verdict = {
            "schema": "persona_dream.hosted_lipsync_canary_verdict.v1",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "case_id": args.case_id,
            "provider": args.provider,
            "status": "blocked" if prereq_errors else "dry_run",
            "reasons": prereq_errors or ["dry_run requested"],
            "output_video": None,
        }
        write_json(receipts / "canary_verdict.json", verdict)
        print(json.dumps(verdict, indent=2))
        return 2 if prereq_errors else 0

    queue_events: list[dict[str, Any]] = []

    def on_queue_update(update: Any) -> None:
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "repr": repr(update),
        }
        status = getattr(update, "status", None)
        if status is not None:
            record["status"] = status
        logs = getattr(update, "logs", None)
        if logs is not None:
            record["logs_repr"] = repr(logs)
        queue_events.append(record)
        with (receipts / "provider_queue_events.jsonl").open("a") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")

    video_url = fal_client.upload_file(str(args.video))  # type: ignore[union-attr]
    audio_url = fal_client.upload_file(str(args.audio))  # type: ignore[union-attr]
    upload_receipt = {
        "schema": "persona_dream.hosted_lipsync_upload_receipt.v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "video_url": video_url,
        "audio_url": audio_url,
    }
    write_json(receipts / "upload_receipt.json", upload_receipt)

    provider_args: dict[str, Any] = {"video_url": video_url, "audio_url": audio_url}
    if args.provider == "sync-v3":
        provider_args["sync_mode"] = args.sync_mode

    response = fal_client.subscribe(  # type: ignore[union-attr]
        model_id,
        arguments=provider_args,
        with_logs=True,
        on_queue_update=on_queue_update,
    )
    write_json(receipts / "provider_response.json", response)

    video = response.get("video") if isinstance(response, dict) else None
    result_url = video.get("url") if isinstance(video, dict) else None
    if not result_url:
        verdict = {
            "schema": "persona_dream.hosted_lipsync_canary_verdict.v1",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "case_id": args.case_id,
            "provider": args.provider,
            "status": "failed",
            "reasons": ["provider response did not include video.url"],
            "output_video": None,
        }
        write_json(receipts / "canary_verdict.json", verdict)
        print(json.dumps(verdict, indent=2))
        return 1

    download_receipt = download(result_url, output_video)
    write_json(receipts / "download_receipt.json", download_receipt)
    if download_receipt.get("status") == "ok":
        write_json(receipts / "output_ffprobe.json", ffprobe(output_video))
        verdict_status = "output_ready"
        reasons: list[str] = []
    else:
        verdict_status = "failed"
        reasons = [download_receipt.get("error", "download failed")]

    verdict = {
        "schema": "persona_dream.hosted_lipsync_canary_verdict.v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "case_id": args.case_id,
        "provider": args.provider,
        "status": verdict_status,
        "reasons": reasons,
        "output_video": str(output_video) if output_video.exists() else None,
        "queue_event_count": len(queue_events),
    }
    write_json(receipts / "canary_verdict.json", verdict)
    print(json.dumps(verdict, indent=2))
    return 0 if verdict_status == "output_ready" else 1


if __name__ == "__main__":
    sys.exit(main())
