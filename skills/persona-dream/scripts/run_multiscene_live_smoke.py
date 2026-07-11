#!/usr/bin/env python3
"""Run a real multi-scene Persona Dream image smoke.

This intentionally uses live Scillm image generation. It does not submit to
Kling and it does not accept fake provider outputs as proof.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import struct
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCILLM_GENERATE = Path(
    os.environ.get("SCILLM_GENERATE_IMAGE", "/home/graham/workspace/experiments/scillm/scripts/generate_image.py")
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_hex(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def png_dimensions(path: Path) -> tuple[int | None, int | None]:
    data = path.read_bytes()[:24]
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None, None
    width, height = struct.unpack(">II", data[16:24])
    return int(width), int(height)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def scene_prompt(scene_id: str, kind: str) -> str:
    ordinal = int(scene_id.rsplit("_", 1)[-1])
    base = (
        "Persona Dream live multi-scene smoke. Create a photo-realistic cinematic image, "
        "not illustration, not cartoon, not anime, not a placeholder. Use natural lensing, "
        "credible human-scale materials, real-world lighting, and no visible text labels."
    )
    if kind == "contact_sheet":
        return (
            f"{base}\n\n"
            f"Scene {ordinal}: produce a 4:3 production contact sheet/reference board for a surreal "
            "near-future tea terrace inside a memory archive. Include four coherent quadrants: "
            "main character wardrobe reference, location reference, prop reference, and lighting palette. "
            "All quadrants should look like real production stills from the same film world."
        )
    return (
        f"{base}\n\n"
        f"Scene {ordinal}: produce one final Kling-ready storyboard panel. A producer has selected a "
        "director and script writer; this is the panel after that selection. Show a grounded cinematic "
        "moment on the tea terrace memory archive: one protagonist studies a glowing evidence shard while "
        "another figure waits in the background. Maintain continuity with a realistic contact sheet look, "
        "clean composition, no captions, no watermarks."
    )


def run_image(
    *,
    generate_script: Path,
    prompt_file: Path,
    out_path: Path,
    receipt_path: Path,
    events_path: Path,
    auth: str,
    model: str,
    quality: str,
    timeout_s: float,
) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(generate_script),
        "--prompt-file",
        str(prompt_file),
        "--out",
        str(out_path),
        "--receipt",
        str(receipt_path),
        "--auth",
        auth,
        "--model",
        model,
        "--quality",
        quality,
        "--events-out",
        str(events_path),
        "--timeout-s",
        str(timeout_s),
        "--json",
    ]
    started = time.monotonic()
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout_s + 30,
        check=False,
    )
    elapsed_s = round(time.monotonic() - started, 3)
    receipt = load_json(receipt_path)
    width, height = png_dimensions(out_path) if out_path.is_file() else (None, None)
    actual_sha = sha256_hex(out_path) if out_path.is_file() else None
    return {
        "cmd": cmd,
        "returncode": proc.returncode,
        "elapsed_s": elapsed_s,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
        "ok": proc.returncode == 0
        and out_path.is_file()
        and out_path.stat().st_size > 0
        and receipt.get("ok") is True
        and str(receipt.get("sha256") or "") == str(actual_sha),
        "image_path": str(out_path),
        "receipt_path": str(receipt_path),
        "events_path": str(events_path),
        "bytes": out_path.stat().st_size if out_path.is_file() else 0,
        "width": width,
        "height": height,
        "sha256": actual_sha,
        "receipt_sha256": receipt.get("sha256"),
        "auth": receipt.get("auth") or auth,
        "model": receipt.get("model") or model,
    }


def run_scene(scene_index: int, args: argparse.Namespace) -> dict[str, Any]:
    scene_id = f"scene_{scene_index:03d}"
    scene_root = args.run_root / "scenes" / scene_id
    prompts_dir = scene_root / "prompts"
    artifacts_dir = scene_root / "artifacts"
    receipts_dir = scene_root / "receipts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    receipts_dir.mkdir(parents=True, exist_ok=True)

    contact_prompt = prompts_dir / "contact_sheet.prompt.md"
    panel_prompt = prompts_dir / "panel_001.prompt.md"
    contact_prompt.write_text(scene_prompt(scene_id, "contact_sheet") + "\n", encoding="utf-8")
    panel_prompt.write_text(scene_prompt(scene_id, "panel") + "\n", encoding="utf-8")

    contact = run_image(
        generate_script=args.scillm_generate,
        prompt_file=contact_prompt,
        out_path=artifacts_dir / "contact_sheet.png",
        receipt_path=receipts_dir / "contact_sheet_receipt.json",
        events_path=receipts_dir / "contact_sheet_events.jsonl",
        auth=args.auth,
        model=args.model,
        quality=args.quality,
        timeout_s=args.image_timeout_s,
    )
    panel = run_image(
        generate_script=args.scillm_generate,
        prompt_file=panel_prompt,
        out_path=artifacts_dir / "panel_001.png",
        receipt_path=receipts_dir / "panel_generation_receipt.json",
        events_path=receipts_dir / "panel_generation_events.jsonl",
        auth=args.auth,
        model=args.model,
        quality=args.quality,
        timeout_s=args.image_timeout_s,
    )

    manifest = {
        "schema": "persona_dream.multiscene_live_scene_manifest.v1",
        "scene_id": scene_id,
        "created_at": utc_now(),
        "mocked": False,
        "live": True,
        "kling_called": False,
        "paid_call_authorized": False,
        "contact_sheet": contact,
        "panel": panel,
        "ok": contact.get("ok") is True and panel.get("ok") is True,
    }
    write_json(receipts_dir / "scene_manifest.json", manifest)
    return manifest


def find_singleton_receipts(run_root: Path) -> list[str]:
    forbidden = [
        run_root / "receipts" / "contact_sheet_receipt.json",
        run_root / "receipts" / "panel_generation_receipt.json",
        run_root / "receipts" / "panel_source_receipt.json",
        run_root / "panel_repair_gate_receipt.json",
    ]
    return [str(path) for path in forbidden if path.exists()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--scene-count", type=int, default=2)
    parser.add_argument("--max-workers", type=int, default=2)
    parser.add_argument("--auth", choices=["codex-oauth", "openai-api-key"], default="codex-oauth")
    parser.add_argument("--model", default="gpt-image-2")
    parser.add_argument("--quality", default="high")
    parser.add_argument("--image-timeout-s", type=float, default=900.0)
    parser.add_argument("--scillm-generate", type=Path, default=DEFAULT_SCILLM_GENERATE)
    parser.add_argument("--json", action="store_true", dest="json_out")
    args = parser.parse_args(argv)

    if args.scene_count < 1:
        raise SystemExit("--scene-count must be >= 1")
    if args.max_workers < 1:
        raise SystemExit("--max-workers must be >= 1")
    if not args.scillm_generate.is_file():
        raise SystemExit(f"missing Scillm image generator: {args.scillm_generate}")

    args.run_root.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = [executor.submit(run_scene, index, args) for index in range(1, args.scene_count + 1)]
        scenes = [future.result() for future in concurrent.futures.as_completed(futures)]
    scenes.sort(key=lambda item: str(item.get("scene_id") or ""))
    forbidden_singletons = find_singleton_receipts(args.run_root)
    ok = all(scene.get("ok") is True for scene in scenes) and not forbidden_singletons
    receipt = {
        "schema": "persona_dream.multiscene_live_smoke_receipt.v1",
        "created_at": utc_now(),
        "status": "PASS" if ok else "FAIL",
        "reason": "ok" if ok else "one_or_more_live_scene_generations_failed",
        "mocked": False,
        "live": True,
        "auth": args.auth,
        "model": args.model,
        "quality": args.quality,
        "run_root": str(args.run_root),
        "scene_count": args.scene_count,
        "max_workers": args.max_workers,
        "elapsed_s": round(time.monotonic() - started, 3),
        "kling_called": False,
        "paid_call_authorized": False,
        "forbidden_singleton_receipts": forbidden_singletons,
        "scenes": scenes,
        "claims": {
            "proves": [
                "real Scillm image generation can produce scene-scoped contact sheet and panel artifacts",
                "per-scene receipts and image hashes agree for generated artifacts",
                "multi-scene worker execution does not need Kling submission",
            ],
            "does_not_prove": [
                "Kling accepts the final request",
                "all upstream producer/director/script semantic gates are correct",
                "final panel creative quality is human accepted",
            ],
        },
    }
    receipt_path = args.run_root / "receipts" / "multiscene_live_smoke_receipt.json"
    write_json(receipt_path, receipt)
    out = {"status": receipt["status"], "reason": receipt["reason"], "receipt": str(receipt_path)}
    print(json.dumps(out, indent=2) if args.json_out else out)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
