#!/usr/bin/env python3
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


MODEL_ID = "bytedance/seedance-2.0/image-to-video"
FAL_KEY_ENV_NAMES = ("FAL_KEY", "FAL_API_KEY", "FAL_TOKEN")
OFFICIAL_API_DOC = "https://fal.ai/models/bytedance/seedance-2.0/image-to-video/api"


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd: list[str], timeout: float = 60.0) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            cmd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        return {
            "cmd": cmd,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "status": "ok" if proc.returncode == 0 else "error",
        }
    except Exception as exc:
        return {"cmd": cmd, "status": "error", "error": str(exc)}


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
        with urllib.request.urlopen(url, timeout=600) as response:
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


def prompt_text(args: argparse.Namespace) -> str:
    if args.prompt_file:
        return args.prompt_file.read_text().strip()
    return args.prompt.strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one hosted Seedance 2.0 regeneration canary with receipts.")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--reference-image", type=Path, required=True)
    parser.add_argument("--prompt", default="")
    parser.add_argument("--prompt-file", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--resolution", choices=["480p", "720p", "1080p"], default="720p")
    parser.add_argument("--duration", choices=["auto", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15"], default="5")
    parser.add_argument("--aspect-ratio", choices=["auto", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"], default="1:1")
    parser.add_argument("--generate-audio", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--dry-run", action="store_true", help="Write receipts without calling the provider.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir: Path = args.out_dir
    receipts = out_dir / "receipts"
    output_video = out_dir / "output" / f"{args.case_id}_seedance_regenerated.mp4"
    receipts.mkdir(parents=True, exist_ok=True)
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    prompt = prompt_text(args)
    prereq_errors: list[str] = []
    if not args.reference_image.exists():
        prereq_errors.append(f"missing reference image: {args.reference_image}")
    if not prompt:
        prereq_errors.append("missing prompt text")
    fal_key_present, fal_key_env_name = detect_fal_key_env()
    if not fal_key_present:
        prereq_errors.append(f"no Fal credential present in any of: {', '.join(FAL_KEY_ENV_NAMES)}")

    try:
        import fal_client  # type: ignore
    except Exception as exc:
        fal_client = None  # type: ignore
        prereq_errors.append(f"fal_client import failed: {exc}")

    provider_args: dict[str, Any] = {
        "prompt": prompt,
        "image_url": "<uploaded by runner>",
        "resolution": args.resolution,
        "duration": args.duration,
        "aspect_ratio": args.aspect_ratio,
        "generate_audio": args.generate_audio,
    }
    if args.seed is not None:
        provider_args["seed"] = args.seed

    request_payload = {
        "schema": "persona_dream.seedance_canary_request.v1",
        "created_at": started_at,
        "model_id": MODEL_ID,
        "official_api_doc": OFFICIAL_API_DOC,
        "case_id": args.case_id,
        "reference_image_path": str(args.reference_image),
        "output_video": str(output_video),
        "dry_run": args.dry_run,
        "provider_args_template": provider_args,
        "identity_boundary": "fictional persona-dream regeneration canary; generated character imagery is synthetic and not factual identity evidence",
        "inputs": {
            "reference_image_sha256": sha256(args.reference_image) if args.reference_image.exists() else None,
            "reference_image_size_bytes": args.reference_image.stat().st_size if args.reference_image.exists() else None,
            "prompt_source": str(args.prompt_file) if args.prompt_file else "inline",
            "prompt": prompt,
        },
    }
    write_json(receipts / "provider_request.json", request_payload)

    readiness = {
        "schema": "persona_dream.seedance_readiness.v1",
        "created_at": started_at,
        "model_id": MODEL_ID,
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
            "schema": "persona_dream.seedance_canary_verdict.v1",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "case_id": args.case_id,
            "model_id": MODEL_ID,
            "status": "blocked" if prereq_errors else "dry_run",
            "reasons": prereq_errors or ["dry_run requested"],
            "output_video": None,
            "route_role": "regeneration_canary_not_existing_clip_lipsync_repair",
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

    image_url = fal_client.upload_file(str(args.reference_image))  # type: ignore[union-attr]
    upload_receipt = {
        "schema": "persona_dream.seedance_upload_receipt.v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "image_url": image_url,
    }
    write_json(receipts / "upload_receipt.json", upload_receipt)

    live_args = dict(provider_args)
    live_args["image_url"] = image_url
    response = fal_client.subscribe(  # type: ignore[union-attr]
        MODEL_ID,
        arguments=live_args,
        with_logs=True,
        on_queue_update=on_queue_update,
    )
    write_json(receipts / "provider_response.json", response)

    video = response.get("video") if isinstance(response, dict) else None
    result_url = video.get("url") if isinstance(video, dict) else None
    if not result_url:
        verdict = {
            "schema": "persona_dream.seedance_canary_verdict.v1",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "case_id": args.case_id,
            "model_id": MODEL_ID,
            "status": "failed",
            "reasons": ["provider response did not include video.url"],
            "output_video": None,
            "queue_event_count": len(queue_events),
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
        "schema": "persona_dream.seedance_canary_verdict.v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "case_id": args.case_id,
        "model_id": MODEL_ID,
        "status": verdict_status,
        "reasons": reasons,
        "output_video": str(output_video) if output_video.exists() else None,
        "queue_event_count": len(queue_events),
        "route_role": "regeneration_canary_not_existing_clip_lipsync_repair",
    }
    write_json(receipts / "canary_verdict.json", verdict)
    print(json.dumps(verdict, indent=2))
    return 0 if verdict_status == "output_ready" else 1


if __name__ == "__main__":
    sys.exit(main())
