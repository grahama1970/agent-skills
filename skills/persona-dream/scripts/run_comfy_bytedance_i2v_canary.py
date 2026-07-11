#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
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


def image_probe(path: Path) -> dict[str, Any]:
    result = run(["file", str(path)])
    return result


def ffprobe(path: Path) -> dict[str, Any]:
    result = run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)])
    if result.get("returncode") == 0:
        try:
            return json.loads(result["stdout"])
        except Exception as exc:
            return {"status": "parse_error", "error": str(exc), "raw": result}
    return {"status": "error", "raw": result}


def http_json(url: str, data: dict[str, Any] | None = None, timeout: float = 60.0) -> dict[str, Any]:
    req_data = None
    headers = {}
    if data is not None:
        req_data = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=req_data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            parsed = json.loads(body) if body else {}
            return {
                "status": "ok",
                "status_code": response.status,
                "url": url,
                "json": parsed,
            }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed: Any = json.loads(body)
        except Exception:
            parsed = body
        return {
            "status": "http_error",
            "status_code": exc.code,
            "url": url,
            "body": parsed,
        }
    except Exception as exc:
        return {"status": "error", "url": url, "error": str(exc)}


def extract_saved_videos(history: dict[str, Any]) -> list[dict[str, Any]]:
    videos: list[dict[str, Any]] = []
    for prompt_record in history.values():
        outputs = prompt_record.get("outputs", {}) if isinstance(prompt_record, dict) else {}
        for output in outputs.values():
            if not isinstance(output, dict):
                continue
            for key in ("videos", "gifs"):
                for item in output.get(key, []) or []:
                    if isinstance(item, dict):
                        videos.append(item)
    return videos


def extract_execution_errors(history: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for prompt_record in history.values():
        status = prompt_record.get("status", {}) if isinstance(prompt_record, dict) else {}
        for message in status.get("messages", []) if isinstance(status, dict) else []:
            if not isinstance(message, list) or len(message) != 2:
                continue
            kind, payload = message
            if kind == "execution_error" and isinstance(payload, dict):
                errors.append(payload)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a ComfyUI ByteDance/Seedance I2V canary through the local API.")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--comfy-url", default="http://127.0.0.1:8188")
    parser.add_argument("--comfy-root", type=Path, default=Path("/mnt/storage12tb/skills/persona-dream/comfyui"))
    parser.add_argument("--model", default="seedance-1-0-lite-i2v-250428")
    parser.add_argument("--resolution", default="480p")
    parser.add_argument("--aspect-ratio", default="16:9")
    parser.add_argument("--duration", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=1200.0)
    args = parser.parse_args()

    receipts = args.out_dir / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    prereq_errors: list[str] = []
    if not args.image.exists():
        prereq_errors.append(f"missing image: {args.image}")
    if not args.prompt_file.exists():
        prereq_errors.append(f"missing prompt file: {args.prompt_file}")
    input_dir = args.comfy_root / "input"
    output_dir = args.comfy_root / "output"
    if not input_dir.exists():
        prereq_errors.append(f"missing ComfyUI input dir: {input_dir}")
    if not output_dir.exists():
        prereq_errors.append(f"missing ComfyUI output dir: {output_dir}")

    system_stats = http_json(f"{args.comfy_url}/system_stats", timeout=15)
    object_info = http_json(f"{args.comfy_url}/object_info/ByteDanceImageToVideoNode", timeout=15)
    load_image_info = http_json(f"{args.comfy_url}/object_info/LoadImage", timeout=15)
    if system_stats.get("status") != "ok":
        prereq_errors.append("ComfyUI /system_stats unavailable")
    if object_info.get("status") != "ok":
        prereq_errors.append("ComfyUI ByteDanceImageToVideoNode object_info unavailable")
    if load_image_info.get("status") != "ok":
        prereq_errors.append("ComfyUI LoadImage object_info unavailable")

    prompt_text = args.prompt_file.read_text() if args.prompt_file.exists() else ""
    image_name = f"persona_dream_{args.case_id}_bytedance_input{args.image.suffix}"
    if not prereq_errors:
        shutil.copy2(args.image, input_dir / image_name)

    prompt = {
        "1": {
            "class_type": "LoadImage",
            "inputs": {
                "image": image_name,
            },
        },
        "2": {
            "class_type": "ByteDanceImageToVideoNode",
            "inputs": {
                "model": args.model,
                "prompt": prompt_text,
                "image": ["1", 0],
                "resolution": args.resolution,
                "aspect_ratio": args.aspect_ratio,
                "duration": args.duration,
                "seed": 42,
                "camera_fixed": False,
                "watermark": False,
                "generate_audio": False,
            },
        },
        "3": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["2", 0],
                "filename_prefix": f"persona_dream_bytedance/{args.case_id}",
                "format": "mp4",
                "codec": "h264",
            },
        },
    }

    request = {
        "schema": "persona_dream.comfy_bytedance_i2v_canary_request.v1",
        "created_at": started_at,
        "case_id": args.case_id,
        "comfy_url": args.comfy_url,
        "comfy_root": str(args.comfy_root),
        "image_path": str(args.image),
        "prompt_file": str(args.prompt_file),
        "model": args.model,
        "resolution": args.resolution,
        "aspect_ratio": args.aspect_ratio,
        "duration": args.duration,
        "prompt": prompt,
        "inputs": {
            "image_sha256": sha256(args.image) if args.image.exists() else None,
            "prompt_sha256": sha256(args.prompt_file) if args.prompt_file.exists() else None,
            "image_probe": image_probe(args.image) if args.image.exists() else None,
        },
        "system_stats": system_stats,
        "object_info": object_info,
        "load_image_info": load_image_info,
        "prereq_errors": prereq_errors,
    }
    write_json(receipts / "provider_request.json", request)

    if prereq_errors:
        verdict = {
            "schema": "persona_dream.comfy_bytedance_i2v_canary_verdict.v1",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "case_id": args.case_id,
            "status": "blocked",
            "reasons": prereq_errors,
            "output_video": None,
        }
        write_json(receipts / "canary_verdict.json", verdict)
        print(json.dumps(verdict, indent=2))
        return 2

    queue_request = {
        "prompt": prompt,
        "client_id": f"persona-dream-bytedance-{args.case_id}-{int(time.time())}",
    }
    queue_response = http_json(f"{args.comfy_url}/prompt", queue_request, timeout=60)
    write_json(receipts / "queue_response.json", queue_response)
    if queue_response.get("status") != "ok" or "prompt_id" not in queue_response.get("json", {}):
        verdict = {
            "schema": "persona_dream.comfy_bytedance_i2v_canary_verdict.v1",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "case_id": args.case_id,
            "status": "blocked_or_failed_before_queue",
            "reasons": ["ComfyUI /prompt did not return a prompt_id"],
            "queue_response": queue_response,
            "output_video": None,
        }
        write_json(receipts / "canary_verdict.json", verdict)
        print(json.dumps(verdict, indent=2))
        return 1

    prompt_id = queue_response["json"]["prompt_id"]
    deadline = time.time() + args.timeout
    history: dict[str, Any] = {}
    while time.time() < deadline:
        history_response = http_json(f"{args.comfy_url}/history/{prompt_id}", timeout=30)
        write_json(receipts / "latest_history_response.json", history_response)
        if history_response.get("status") == "ok":
            history = history_response.get("json", {})
            if prompt_id in history:
                break
        time.sleep(5)

    write_json(receipts / "history.json", history)
    videos = extract_saved_videos(history)
    execution_errors = extract_execution_errors(history)
    write_json(receipts / "execution_errors.json", execution_errors)

    copied_outputs: list[dict[str, Any]] = []
    for item in videos:
        filename = item.get("filename")
        subfolder = item.get("subfolder", "")
        if not filename:
            continue
        source = output_dir / subfolder / filename
        if source.exists():
            target = args.out_dir / "output" / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied_outputs.append({
                "source": str(source),
                "target": str(target),
                "sha256": sha256(target),
                "ffprobe": ffprobe(target),
            })

    if copied_outputs:
        status = "output_ready"
        reasons: list[str] = []
    elif any("Unauthorized" in str(error.get("exception_message", "")) for error in execution_errors):
        status = "blocked_comfy_org_unauthorized"
        reasons = ["ComfyUI API node returned Unauthorized: Please login first to use this node."]
    else:
        status = "failed_or_timed_out"
        reasons = ["No saved video output found in ComfyUI history before timeout"]

    verdict = {
        "schema": "persona_dream.comfy_bytedance_i2v_canary_verdict.v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "case_id": args.case_id,
        "status": status,
        "reasons": reasons,
        "prompt_id": prompt_id,
        "outputs": copied_outputs,
        "output_video": copied_outputs[0]["target"] if copied_outputs else None,
    }
    write_json(receipts / "canary_verdict.json", verdict)
    print(json.dumps(verdict, indent=2))
    return 0 if status == "output_ready" else 1


if __name__ == "__main__":
    sys.exit(main())
