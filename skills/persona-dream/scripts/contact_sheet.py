#!/usr/bin/env python3
"""Build, amend, retrieve, and index persona-dream contact sheets."""

from __future__ import annotations

from pydantic_step_gate import validate_http_json

import base64
import hashlib
import html
import json
import math
import os
import uuid
from datetime import datetime, timezone
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Annotated, Any

import httpx
import typer
from PIL import Image, ImageDraw, ImageFont, ImageOps


app = typer.Typer(help="Persona-dream contact sheet builder.")

QDRANT_URL = "http://127.0.0.1:6333"
EMBED_URL = "http://127.0.0.1:8603/embed"
MEMORY_URL = "http://127.0.0.1:8601"
QDRANT_COLLECTION = "persona_dream_visual_assets_v1"
MEMORY_COLLECTION = "persona_dream_visual_assets"
VECTOR_SIZE = 1024
POINT_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "persona-dream.visual-assets")

PROVIDER_MODELS = {
    "kling_3_0_o3_omni": {
        "provider": "fal",
        "model_id": "fal-ai/kling-video/o3/standard/reference-to-video",
        "route_role": "default_joint_audio_video",
    },
    "seedance_2_0": {
        "provider": "fal",
        "model_id": "bytedance/seedance-2.0",
        "route_role": "second_native_audio_video_challenger",
    },
    "elevenlabs_kling_lipsync_control": {
        "provider": "fal",
        "model_id": "elevenlabs_tts_plus_kling_lipsync_control",
        "route_role": "voice_control_lipsync_baseline",
    },
}


def _ensure_fal_key() -> None:
    fal_key = os.getenv("FAL_KEY") or os.getenv("FAL_API_KEY") or os.getenv("FAL_TOKEN")
    if not fal_key:
        raise RuntimeError("FAL_KEY, FAL_API_KEY, or FAL_TOKEN is required for --live provider submission.")
    os.environ.setdefault("FAL_KEY", fal_key)


def _extract_video_url(result: dict[str, Any]) -> str:
    for key in ("video", "output", "file"):
        value = result.get(key)
        if isinstance(value, dict) and isinstance(value.get("url"), str):
            return value["url"]
        if isinstance(value, str) and value.startswith("http"):
            return value
    if isinstance(result.get("videos"), list):
        for item in result["videos"]:
            if isinstance(item, dict) and isinstance(item.get("url"), str):
                return item["url"]
    raise KeyError(f"Could not find video URL in provider response keys={list(result.keys())}")


def _download_url(url: str, output_path: Path) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=900) as response:
        data = response.read()
        output_path.write_bytes(data)
        return {
            "url": url,
            "output_path": str(output_path),
            "bytes": len(data),
            "headers": dict(response.headers.items()),
        }


def _run_json_command(cmd: list[str]) -> dict[str, Any]:
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    payload: dict[str, Any] = {
        "cmd": cmd,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    if completed.returncode == 0 and completed.stdout.strip():
        try:
            payload["json"] = json.loads(completed.stdout)
        except json.JSONDecodeError:
            pass
    return payload


def _ffprobe(path: Path) -> dict[str, Any]:
    if shutil.which("ffprobe") is None:
        return {"status": "skipped", "reason": "ffprobe_not_found"}
    result = _run_json_command([
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration,size:stream=index,codec_type,codec_name,width,height,duration,nb_frames",
        "-of",
        "json",
        str(path),
    ])
    return {"status": "ok" if result.get("returncode") == 0 else "error", **result}


def _frame_sheet(video_path: Path, output_path: Path) -> dict[str, Any]:
    if shutil.which("ffmpeg") is None:
        return {"status": "skipped", "reason": "ffmpeg_not_found"}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vf",
        "select='not(mod(n,24))',scale=320:-1,tile=5x2",
        "-frames:v",
        "1",
        str(output_path),
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return {
        "status": "ok" if completed.returncode == 0 and output_path.exists() else "error",
        "cmd": cmd,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "output_path": str(output_path) if output_path.exists() else None,
    }


ASSET_HINTS: dict[str, dict[str, Any]] = {
    "embry_character_reference_sheet": ("character", "embry", "Embry Character Reference Sheet"),
    "horus_character_reference_sheet": ("character", "horus", "Horus Character Reference Sheet"),
    "location_void_tea_terrace_reference_sheet": ("environment", "void_tea_terrace", "Void Tea Terrace Location Sheet"),
    "location_sparta_archive_reference_sheet": ("environment", "sparta_archive", "SPARTA Archive Location Sheet"),
    "location_graph_room_reference_sheet": ("environment", "sparta_graph_room", "SPARTA Graph Room Location Sheet"),
    "location_memory_terminal_reference_sheet": ("environment", "memory_terminal", "Memory Terminal Location Sheet"),
    "environment_void_world_reference_sheet": ("environment", "void_world_background", "Void World Background Sheet"),
    "prop_patio_table_umbrella_tea_reference_sheet": ("object", "patio_table_umbrella_tea_kit", "Patio Table, Umbrella, and Tea Prop Kit"),
    "prop_sparta_hologram_receipt_reference_sheet": ("object", "sparta_hologram_receipt_kit", "SPARTA Hologram Receipt Prop Kit"),
    "creature_tyranid_background_reference_sheet": ("creature", "tyranid_background_wildlife", "Background Alien Creature Sheet"),
    "contact_sheet_embry_surfboard": ("object", "contact_sheet_embry_surfboard", "Embry Surfboard Contact Sheet"),
    "contact_sheet_kai_surfboard": ("object", "contact_sheet_kai_surfboard", "Kai Surfboard Contact Sheet"),
    "contact_sheet_june_swell": ("environment", "contact_sheet_june_swell", "June Swell Contact Sheet"),
    "contact_sheet_lava_reef": ("environment", "contact_sheet_lava_reef", "Lava Reef Contact Sheet"),
    "contact_sheet_kona_coast": ("environment", "contact_sheet_kona_coast", "Kona Coast Contact Sheet"),
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_key(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:32]


def font(size: int) -> ImageFont.ImageFont:
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def classify(stem: str) -> dict[str, Any]:
    if stem in ASSET_HINTS:
        entity_type, entity_id, title = ASSET_HINTS[stem]
    else:
        entity_type = {"character": "character", "location": "environment", "environment": "environment", "prop": "object", "creature": "creature"}.get(stem.split("_", 1)[0], "object")
        entity_id = stem
        title = stem.replace("_", " ").title()
    desc = title.replace(" Sheet", "").replace(" Kit", "")
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "title": title,
        "description": f"{desc} for persona-dream provider prompts and continuity references.",
        "tags": ["persona-dream", entity_type, entity_id],
    }


def image_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_thumb(path: Path, size: tuple[int, int]) -> Image.Image:
    return ImageOps.contain(Image.open(path).convert("RGB"), size, Image.Resampling.LANCZOS)


def draw_wrapped(draw: ImageDraw.ImageDraw, text: str, xy: tuple[int, int], max_width: int, fnt: ImageFont.ImageFont, fill: str) -> int:
    x, y = xy
    line = ""
    line_h = 20
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=fnt)[2] <= max_width or not line:
            line = candidate
            continue
        draw.text((x, y), line, font=fnt, fill=fill)
        y += line_h
        line = word
    if line:
        draw.text((x, y), line, font=fnt, fill=fill)
        y += line_h
    return y


def build_assets(asset_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    image_paths = sorted((asset_root / "images").glob("*.png"))
    if not image_paths:
        raise typer.BadParameter(f"No PNG assets found under {asset_root / 'images'}")
    assets = []
    for path in image_paths:
        meta = classify(path.stem)
        sha = image_sha(path)
        point_id = str(uuid.uuid5(POINT_NAMESPACE, sha))
        meta.update(
            {
                "schema": "persona_dream.visual_asset.v1",
                "_key": stable_key(f"persona-dream:{sha}"),
                "kind": "persona_dream_visual_asset",
                "asset_id": path.stem,
                "image_path": str(path),
                "prompt_path": str(asset_root / "prompts" / f"{path.stem}.prompt.md"),
                "response_path": str(asset_root / "receipts" / f"{path.stem}.response.json"),
                "sha256": sha,
                "bytes": path.stat().st_size,
                "visual_qdrant_collection": QDRANT_COLLECTION,
                "visual_qdrant_point_id": point_id,
                "semantic_sync_state": "pending",
                "created_at_utc": now_iso(),
            }
        )
        assets.append(meta)
    blocked = []
    receipts_dir = asset_root / "receipts"
    if receipts_dir.exists():
        for response_path in sorted(receipts_dir.glob("*.response.json")):
            try:
                data = json.loads(response_path.read_text())
            except json.JSONDecodeError:
                continue
            if data.get("error"):
                blocked.append(
                    {
                        "asset_id": response_path.name.removesuffix(".response.json"),
                        "reason": data["error"].get("message", "provider_error"),
                        "response_path": str(response_path),
                    }
                )
    return assets, blocked


def create_contact_sheet(assets: list[dict[str, Any]], out_path: Path) -> None:
    cols, card_w, card_h, margin, gap = 2, 760, 500, 32, 24
    preview_w, preview_h = 320, 320
    rows = math.ceil(len(assets) / cols)
    canvas = Image.new("RGB", (margin * 2 + cols * card_w + gap, margin * 2 + rows * card_h + (rows - 1) * gap + 82), "#f4f1eb")
    draw = ImageDraw.Draw(canvas)
    draw.text((margin, 24), "Persona-Dream Contact Sheet Index", font=font(34), fill="#171717")
    for idx, asset in enumerate(assets):
        x = margin + (idx % cols) * (card_w + gap)
        y = margin + 72 + (idx // cols) * (card_h + gap)
        draw.rounded_rectangle((x, y, x + card_w, y + card_h), radius=8, fill="#ffffff", outline="#c8c0b2", width=2)
        preview_x = x + 18
        preview_y = y + 18
        draw.rectangle((preview_x, preview_y, preview_x + preview_w, preview_y + preview_h), fill="#f0ede6", outline="#e3ddd1")
        thumb = make_thumb(Path(asset["image_path"]), (preview_w, preview_h))
        canvas.paste(thumb, (preview_x + (preview_w - thumb.width) // 2, preview_y + (preview_h - thumb.height) // 2))
        text_x = preview_x + preview_w + 22
        text_w = card_w - preview_w - 62
        draw_wrapped(draw, asset["title"], (text_x, y + 26), text_w, font(22), "#171717")
        draw.text((text_x, y + 92), f"{asset['entity_type']} / {asset['entity_id']}", font=font(15), fill="#4d4d4d")
        draw_wrapped(draw, asset["description"], (text_x, y + 122), text_w, font(15), "#333333")
    canvas.save(out_path)


def create_provider_matrix(assets: list[dict[str, Any]], out_path: Path) -> None:
    groups = {
        "Characters": [a for a in assets if a["entity_type"] == "character"],
        "Environments": [a for a in assets if a["entity_type"] == "environment"],
        "Objects / Props": [a for a in assets if a["entity_type"] == "object"],
        "Creatures": [a for a in assets if a["entity_type"] == "creature"],
    }
    canvas = Image.new("RGB", (1800, 1300), "#101010")
    draw = ImageDraw.Draw(canvas)
    draw.text((52, 40), "Provider Reference Matrix", font=font(42), fill="#f3f0e8")
    draw.text((52, 95), "character sheet + location sheet + object/creature sheet + scene prompt", font=font(22), fill="#c7c0b5")
    y = 160
    for heading, group in groups.items():
        draw.text((52, y), heading, font=font(24), fill="#f3f0e8")
        y += 42
        x = 52
        for asset in group:
            draw.rounded_rectangle((x, y, x + 310, y + 218), radius=6, fill="#f7f4ee", outline="#333333")
            draw.rectangle((x + 42, y + 12, x + 42 + 226, y + 148), fill="#eee9df")
            thumb = make_thumb(Path(asset["image_path"]), (226, 136))
            canvas.paste(thumb, (x + 42 + (226 - thumb.width) // 2, y + 18 + (136 - thumb.height) // 2))
            draw_wrapped(draw, asset["title"], (x + 14, y + 170), 282, font(15), "#171717")
            x += 330
            if x + 310 > 1748:
                x = 52
                y += 238
        y += 244
    canvas.save(out_path)


def write_html(asset_root: Path, assets: list[dict[str, Any]], blocked: list[dict[str, Any]]) -> None:
    cards = "\n".join(
        f"<article><img src='images/{html.escape(Path(a['image_path']).name)}'><h3>{html.escape(a['title'])}</h3><p>{html.escape(a['entity_type'])} / {html.escape(a['entity_id'])}</p><p>{html.escape(a['description'])}</p></article>"
        for a in assets
    )
    blocked_html = "".join(f"<li>{html.escape(b['asset_id'])}: {html.escape(b['reason'])}</li>" for b in blocked) or "<li>None</li>"
    (asset_root / "index.html").write_text(
        f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>Persona-Dream Contact Sheet</title><style>
body{{margin:0;font-family:system-ui,sans-serif;background:#f4f1eb;color:#181716}}header{{padding:32px 44px;background:#111;color:#f7f3ea}}main{{padding:28px 44px 60px}}.hero{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px;margin-bottom:30px}}.hero img{{width:100%;height:auto;border:1px solid #c7beb0;background:white}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:18px;align-items:start}}article{{background:white;border:1px solid #c8c0b2;border-radius:8px;padding:14px}}article img{{display:block;width:100%;height:auto;max-height:520px;object-fit:contain;background:#eee9df}}code{{background:#ebe5da;padding:2px 5px;border-radius:4px}}</style></head><body><header><h1>Persona-Dream Contact Sheet</h1><p>Memory-backed and Qdrant-indexed visual references on the 12TB drive.</p></header><main><section class='hero'><div><h2>Contact Sheet Index</h2><img src='contact_sheet_index.png'></div><div><h2>Provider Matrix</h2><img src='provider_matrix.png'></div></section><section><h2>Assets</h2><div class='grid'>{cards}</div></section><section><h2>Blocked Assets</h2><ul>{blocked_html}</ul></section></main></body></html>"""
    )


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def qdrant_index(assets: list[dict[str, Any]]) -> dict[str, Any]:
    points = []
    with httpx.Client(timeout=120) as client:
        existing = client.get(f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}", timeout=10)
        created = existing.status_code != 200
        if created:
            response = client.put(
                f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}",
                json={"vectors": {"text_mm": {"size": VECTOR_SIZE, "distance": "Cosine"}, "image_mm": {"size": VECTOR_SIZE, "distance": "Cosine"}}},
                timeout=30,
            )
            response.raise_for_status()
        for asset in assets:
            doc = f"{asset['title']}\n{asset['description']}\n{asset['entity_type']} {asset['entity_id']} {' '.join(asset['tags'])}"
            text_resp = client.post(EMBED_URL, json={"text": doc}, timeout=120)
            text_resp.raise_for_status()
            image_b64 = base64.b64encode(Path(asset["image_path"]).read_bytes()).decode("ascii")
            image_resp = client.post(EMBED_URL, json={"text": doc, "image_b64": image_b64}, timeout=120)
            image_resp.raise_for_status()
            text_vec = validate_http_json("embedding", text_resp.json())["embedding"]
            image_vec = validate_http_json("embedding", image_resp.json())["embedding"]
            if len(text_vec) != VECTOR_SIZE or len(image_vec) != VECTOR_SIZE:
                raise RuntimeError("Embedding dimension mismatch")
            asset.update(
                {
                    "embedding_model": text_resp.json().get("model"),
                    "embedding_model_version": text_resp.json().get("model_version"),
                    "embedding_dimensions": VECTOR_SIZE,
                    "embedding_schema": "text_mm=text_only, image_mm=text_plus_image_b64",
                    "semantic_sync_state": "synced",
                }
            )
            points.append({"id": asset["visual_qdrant_point_id"], "vector": {"text_mm": text_vec, "image_mm": image_vec}, "payload": asset})
        upsert = client.put(f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points?wait=true", json={"points": points}, timeout=120)
        upsert.raise_for_status()
        return {"collection_created": created, "collection": QDRANT_COLLECTION, "upserted": len(points), "upsert_response": validate_http_json("memory_generic", upsert.json())}


def memory_upsert(assets: list[dict[str, Any]]) -> dict[str, Any]:
    docs = []
    for asset in assets:
        doc = dict(asset)
        doc["problem"] = f"Persona-dream contact sheet visual asset: {asset['title']}"
        doc["solution"] = f"{asset['title']} is stored at {asset['image_path']} and indexed in visual Qdrant point {asset['visual_qdrant_point_id']}."
        doc["tags"] = sorted(set(asset["tags"] + ["contact-sheet", "persona-dream", "visual-asset", asset["entity_type"]]))
        docs.append(doc)
    with httpx.Client(base_url=MEMORY_URL, timeout=30) as client:
        response = client.post("/upsert", json={"collection": MEMORY_COLLECTION, "documents": docs})
        response.raise_for_status()
        return validate_http_json("memory_store", response.json())


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_scene_bindings(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ids = {asset["entity_id"] for asset in assets}

    def keep(items: list[str]) -> list[str]:
        return [item for item in items if item in ids]

    return [
        {"scene_id": "void_tea_dialogue", "characters": keep(["horus", "embry"]), "environments": keep(["void_tea_terrace", "void_world_background"]), "objects": keep(["patio_table_umbrella_tea_kit", "sparta_hologram_receipt_kit"]), "creatures": keep(["tyranid_background_wildlife"])},
        {"scene_id": "sparta_archive_dialogue", "characters": keep(["horus", "embry"]), "environments": keep(["sparta_archive"]), "objects": keep(["sparta_hologram_receipt_kit"]), "creatures": []},
        {"scene_id": "sparta_graph_room_dialogue", "characters": keep(["horus", "embry"]), "environments": keep(["sparta_graph_room"]), "objects": keep(["sparta_hologram_receipt_kit"]), "creatures": []},
        {"scene_id": "memory_terminal_reflection", "characters": keep(["horus", "embry"]), "environments": keep(["memory_terminal"]), "objects": keep(["sparta_hologram_receipt_kit"]), "creatures": []},
    ]


def discover_timed_script(asset_root: Path) -> Path | None:
    candidates = [
        asset_root / "timed_transcript.json",
        asset_root / "storyboard.json",
        asset_root / "story_assets" / "scenes_script.json",
    ]
    for parent in asset_root.parents:
        candidates.extend(
            [
                parent / "timed_transcript.json",
                parent / "storyboard.json",
                parent / "story_assets" / "scenes_script.json",
                parent / "site" / "artifacts" / "timed_transcript.json",
                parent / "site" / "artifacts" / "storyboard.json",
            ]
        )
    seen: set[Path] = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        if path.exists():
            return path
    return None


def load_timed_shots(path: Path | None) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    if path is None:
        return [], None
    data = json.loads(path.read_text())
    shots = data.get("shots") if isinstance(data, dict) else data
    if not isinstance(shots, list):
        raise typer.BadParameter(f"Timed script does not contain shots[]: {path}")
    normalized = []
    for idx, shot in enumerate(shots, start=1):
        if not isinstance(shot, dict):
            continue
        start = shot.get("start_sec")
        end = shot.get("end_sec")
        duration = shot.get("duration_sec")
        if duration is None and isinstance(start, (int, float)) and isinstance(end, (int, float)):
            duration = round(float(end) - float(start), 4)
        normalized.append(
            {
                "shot_id": shot.get("shot_id") or f"shot_{idx:02d}",
                "scene_id": shot.get("scene_id"),
                "scene_title": shot.get("scene_title"),
                "start_sec": start,
                "end_sec": end,
                "duration_sec": duration,
                "speaker": shot.get("speaker"),
                "dialogue": shot.get("dialogue"),
                "visual": shot.get("visual") or shot.get("visual_action") or "",
                "camera": shot.get("camera"),
                "source_grounded_residue_ids": shot.get("source_grounded_residue_ids", []),
                "dream_symbolic_elements": shot.get("dream_symbolic_elements", []),
            }
        )
    return normalized, {
        "path": str(path),
        "schema": data.get("schema") or data.get("schema_version") if isinstance(data, dict) else None,
        "shot_count": len(normalized),
    }


def classify_shot_scene(shot: dict[str, Any]) -> str | None:
    scene_id = str(shot.get("scene_id") or "").lower()
    text = " ".join(
        str(shot.get(field) or "")
        for field in ("scene_id", "scene_title", "visual", "camera", "dialogue")
    ).lower()
    if any(token in text for token in ("tea", "patio", "umbrella", "void-world", "void world", "tyranid")):
        return "void_tea_dialogue"
    if "archive" in text:
        return "sparta_archive_dialogue"
    if "graph" in text or scene_id == "scene_002_embry_speaks":
        return "sparta_graph_room_dialogue"
    if "memory" in text or "terminal" in text:
        return "memory_terminal_reflection"
    if not scene_id and (shot.get("speaker") or shot.get("dialogue")):
        return "void_tea_dialogue"
    return scene_id or None


def attach_shots_to_scenes(scenes: list[dict[str, Any]], shots: list[dict[str, Any]]) -> None:
    shots_by_scene: dict[str, list[dict[str, Any]]] = {}
    for shot in shots:
        scene_id = classify_shot_scene(shot)
        if scene_id:
            shots_by_scene.setdefault(scene_id, []).append(shot)
    for scene in scenes:
        scene_shots = shots_by_scene.get(scene["scene_id"], [])
        speaking = [shot for shot in scene_shots if shot.get("dialogue")]
        selected = speaking[0] if speaking else scene_shots[0] if scene_shots else None
        scene["timed_shots"] = scene_shots
        scene["selected_timed_shot"] = selected
        if selected:
            scene["duration_target_sec"] = selected.get("duration_sec")
            scene["dialogue_contract"]["exact_dialogue"] = selected.get("dialogue")
            scene["dialogue_contract"]["speaker"] = selected.get("speaker")
            scene["dialogue_contract"]["timed_shot_id"] = selected.get("shot_id")
            scene["dialogue_contract"]["start_sec"] = selected.get("start_sec")
            scene["dialogue_contract"]["end_sec"] = selected.get("end_sec")
            for lane in scene["provider_inputs"].values():
                lane["duration_target_sec"] = selected.get("duration_sec")
                if selected.get("dialogue"):
                    lane["exact_dialogue"] = selected.get("dialogue")
                    lane["speaker"] = selected.get("speaker")


SCENE_PROMPT_BLUEPRINTS: dict[str, dict[str, str]] = {
    "void_tea_dialogue": {
        "title": "Void Tea Dialogue",
        "prompt": (
            "Horus and Embry sit at a patio table under a simple umbrella in a surreal void-world tea setting. "
            "Use the character reference sheets for identity continuity, the void tea terrace and void world sheets "
            "for place continuity, and keep the Tyranid-like creatures as distant background motion only. The scene "
            "is quiet, intimate, and source-grounded; no new lore, no subtitles, no readable text."
        ),
    },
    "sparta_archive_dialogue": {
        "title": "SPARTA Archive Dialogue",
        "prompt": (
            "Horus and Embry speak in the SPARTA archive evidence room. Use the archive location sheet, character "
            "sheets, and SPARTA hologram/receipt prop kit. The tone is restrained and work-focused, with visible "
            "faces for dialogue and no invented dashboard claims, logos, subtitles, or readable text."
        ),
    },
    "sparta_graph_room_dialogue": {
        "title": "SPARTA Graph Room Dialogue",
        "prompt": (
            "Horus and Embry discuss source-grounded evidence in the SPARTA graph room. Use the graph room sheet "
            "for spatial continuity and the character sheets for identity. Abstract graph shapes may appear, but "
            "there must be no readable text, no fake operational status, and no unsupported persona lore."
        ),
    },
    "memory_terminal_reflection": {
        "title": "Memory Terminal Reflection",
        "prompt": (
            "Horus and Embry stand near a memory terminal in a quiet reflective scene. Use the memory terminal "
            "environment sheet and SPARTA receipt prop sheet as continuity anchors. The scene should feel like "
            "persona memory residue being inspected, not written back; no memory upserts are depicted."
        ),
    },
}


def _assets_by_entity_id(assets: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {asset["entity_id"]: asset for asset in assets}


def _asset_refs(entity_ids: list[str], assets_by_entity: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    refs = []
    for entity_id in entity_ids:
        asset = assets_by_entity.get(entity_id)
        if not asset:
            continue
        refs.append(
            {
                "entity_type": asset["entity_type"],
                "entity_id": asset["entity_id"],
                "asset_id": asset["asset_id"],
                "title": asset["title"],
                "image_path": asset["image_path"],
                "prompt_path": asset["prompt_path"],
                "sha256": asset["sha256"],
                "visual_qdrant_collection": asset["visual_qdrant_collection"],
                "visual_qdrant_point_id": asset["visual_qdrant_point_id"],
            }
        )
    return refs


def build_provider_inputs(
    assets: list[dict[str, Any]],
    scene_bindings: list[dict[str, Any]],
    timed_shots: list[dict[str, Any]],
    timing_source: dict[str, Any] | None,
) -> dict[str, Any]:
    assets_by_entity = _assets_by_entity_id(assets)
    scenes = []
    for binding in scene_bindings:
        scene_id = binding["scene_id"]
        blueprint = SCENE_PROMPT_BLUEPRINTS.get(scene_id, {"title": scene_id, "prompt": scene_id.replace("_", " ")})
        reference_entity_ids = (
            binding.get("characters", [])
            + binding.get("environments", [])
            + binding.get("objects", [])
            + binding.get("creatures", [])
        )
        references = _asset_refs(reference_entity_ids, assets_by_entity)
        reference_paths = [ref["image_path"] for ref in references]
        shared = {
            "scene_id": scene_id,
            "scene_title": blueprint["title"],
            "base_scene_prompt": blueprint["prompt"],
            "reference_images": reference_paths,
            "reference_assets": references,
            "dialogue_contract": {
                "source": "timed_transcript_or_scene_script",
                "exact_dialogue_required": True,
                "exact_dialogue": None,
                "note": "Provider runners must fill exact_dialogue from the accepted timed script before calling paid media APIs.",
            },
            "negative_constraints": [
                "no unsupported persona lore",
                "no readable text, subtitles, logos, or watermarks",
                "no extra speaking characters",
                "do not treat dream symbolism as factual memory writes",
                "keep character identity anchored to the supplied reference sheets",
            ],
        }
        scenes.append(
            {
                **shared,
                "provider_inputs": {
                    "kling_3_0_o3_omni": {
                        "lane_role": "default_joint_audio_video",
                        "input_mode": "native_av_with_reference_images",
                        "prompt": (
                            f"{blueprint['prompt']} Use the supplied reference images as continuity anchors. "
                            "Generate synchronized speech and video only after exact_dialogue is supplied."
                        ),
                        "reference_images": reference_paths,
                        "requires_exact_dialogue": True,
                        "requires_duration_target": True,
                    },
                    "seedance_2_0": {
                        "lane_role": "second_native_audio_video_challenger",
                        "input_mode": "native_av_with_reference_images_when_available",
                        "prompt": (
                            f"{blueprint['prompt']} Preserve the same reference-image identity and scene contract "
                            "used by the Kling lane so provider differences, not prompt drift, are being compared."
                        ),
                        "reference_images": reference_paths,
                        "requires_exact_dialogue": True,
                        "requires_duration_target": True,
                    },
                    "elevenlabs_kling_lipsync_control": {
                        "lane_role": "voice_control_lipsync_baseline",
                        "input_mode": "tts_audio_plus_shared_base_video",
                        "base_video_prompt": blueprint["prompt"],
                        "reference_images": reference_paths,
                        "requires_shared_base_video": True,
                        "requires_exact_dialogue": True,
                        "note": "ElevenLabs and any WavTTS comparison must use the same accepted base video.",
                    },
                },
            }
        )
    attach_shots_to_scenes(scenes, timed_shots)
    return {
        "schema": "persona_dream.provider_inputs.v1",
        "created_at_utc": now_iso(),
        "timing_source": timing_source,
        "provider_lanes": [
            "kling_3_0_o3_omni",
            "seedance_2_0",
            "elevenlabs_kling_lipsync_control",
        ],
        "assembly_rule": "scene binding -> reference assets -> base scene prompt -> provider-specific input contract",
        "timed_shots": timed_shots,
        "scenes": scenes,
    }


def do_build(asset_root: Path, index_qdrant: bool, write_memory: bool, timed_script: Path | None) -> dict[str, Any]:
    assets, blocked = build_assets(asset_root)
    timed_script = timed_script or discover_timed_script(asset_root)
    timed_shots, timing_source = load_timed_shots(timed_script)
    qdrant_receipt = qdrant_index(assets) if index_qdrant else None
    memory_receipt = memory_upsert(assets) if write_memory else None
    create_contact_sheet(assets, asset_root / "contact_sheet_index.png")
    create_provider_matrix(assets, asset_root / "provider_matrix.png")
    write_html(asset_root, assets, blocked)
    scene_bindings = build_scene_bindings(assets)
    provider_inputs = build_provider_inputs(assets, scene_bindings, timed_shots, timing_source)
    manifest = {"schema": "persona_dream.reference_asset_manifest.v1", "created_at_utc": now_iso(), "root": str(asset_root), "qdrant_collection": QDRANT_COLLECTION if index_qdrant else None, "memory_collection": MEMORY_COLLECTION if write_memory else None, "assets": assets, "blocked_assets": blocked}
    visual_context = {"schema": "persona_dream.visual_entity_context.v1", "created_at_utc": now_iso(), "characters": [a for a in assets if a["entity_type"] == "character"], "environments": [a for a in assets if a["entity_type"] == "environment"], "objects": [a for a in assets if a["entity_type"] == "object"], "creatures": [a for a in assets if a["entity_type"] == "creature"], "scene_bindings": scene_bindings, "provider_lanes": ["kling_3_0_o3_omni", "seedance_2_0", "elevenlabs_kling_lipsync_control"], "provider_inputs_path": str(asset_root / "provider_inputs.json"), "timing_source": timing_source, "qdrant": qdrant_receipt, "memory": memory_receipt}
    (asset_root / "reference_asset_manifest.json").write_text(json.dumps(manifest, indent=2))
    (asset_root / "visual_entity_context.json").write_text(json.dumps(visual_context, indent=2))
    (asset_root / "provider_inputs.json").write_text(json.dumps(provider_inputs, indent=2))
    if qdrant_receipt:
        (asset_root / "qdrant_upsert_receipt.json").write_text(json.dumps(qdrant_receipt, indent=2))
    if memory_receipt:
        (asset_root / "memory_upsert_receipt.json").write_text(json.dumps(memory_receipt, indent=2))
    return {"asset_root": str(asset_root), "assets": len(assets), "blocked_assets": len(blocked), "timed_shots": len(timed_shots), "timing_source": timing_source, "qdrant": qdrant_receipt, "memory": memory_receipt, "provider_inputs": str(asset_root / "provider_inputs.json"), "index_html": str(asset_root / "index.html")}


def scene_lane_ready(scene: dict[str, Any], lane_id: str) -> tuple[str, list[str]]:
    reasons = []
    lane = scene["provider_inputs"][lane_id]
    reference_images = lane.get("reference_images") or scene.get("reference_images") or []
    if not reference_images:
        reasons.append("missing_reference_images")
    missing_refs = [path for path in reference_images if not Path(path).exists()]
    if missing_refs:
        reasons.append("missing_reference_image_files")
    if lane.get("requires_duration_target") and not lane.get("duration_target_sec"):
        reasons.append("missing_duration_target_sec")
    if lane.get("requires_exact_dialogue") and not lane.get("exact_dialogue"):
        reasons.append("missing_exact_dialogue")
    if lane.get("requires_shared_base_video"):
        reasons.append("shared_base_video_not_rendered")
    return ("ready_for_provider_request" if not reasons else "needs_inputs"), reasons


def build_provider_request(scene: dict[str, Any], lane_id: str) -> dict[str, Any]:
    lane = scene["provider_inputs"][lane_id]
    model = PROVIDER_MODELS.get(lane_id, {"provider": "unknown", "model_id": lane_id, "route_role": lane.get("lane_role")})
    reference_images = lane.get("reference_images") or scene.get("reference_images") or []
    image_receipts = [
        {
            "path": path,
            "sha256": sha256_file(Path(path)) if Path(path).exists() else None,
            "exists": Path(path).exists(),
        }
        for path in reference_images
    ]
    status, reasons = scene_lane_ready(scene, lane_id)
    return {
        "schema": "persona_dream.provider_request_dry_run.v1",
        "created_at_utc": now_iso(),
        "status": status,
        "reasons": reasons,
        "dry_run": True,
        "scene_id": scene["scene_id"],
        "scene_title": scene.get("scene_title"),
        "lane_id": lane_id,
        "provider": model["provider"],
        "model_id": model["model_id"],
        "route_role": model["route_role"],
        "prompt": lane.get("prompt") or lane.get("base_video_prompt") or scene.get("base_scene_prompt"),
        "negative_constraints": scene.get("negative_constraints", []),
        "reference_images": reference_images,
        "reference_image_receipts": image_receipts,
        "exact_dialogue": lane.get("exact_dialogue"),
        "speaker": lane.get("speaker"),
        "duration_target_sec": lane.get("duration_target_sec"),
        "timed_shot": scene.get("selected_timed_shot"),
        "provider_args_template": {
            "prompt": lane.get("prompt") or lane.get("base_video_prompt") or scene.get("base_scene_prompt"),
            "reference_images": "<upload reference_images before live call>",
            "dialogue": lane.get("exact_dialogue"),
            "duration": lane.get("duration_target_sec"),
            "generate_audio": lane_id in {"kling_3_0_o3_omni", "seedance_2_0"},
        },
        "identity_boundary": "fictional persona-dream references; generated character imagery is synthetic and not factual identity evidence",
        "paid_call_performed": False,
    }


def do_provider_dry_run(provider_inputs: Path, out_dir: Path, scene_filter: str | None, lane_filter: str | None) -> dict[str, Any]:
    data = json.loads(provider_inputs.read_text())
    if data.get("schema") != "persona_dream.provider_inputs.v1":
        raise typer.BadParameter(f"Unexpected provider input schema: {data.get('schema')}")
    out_dir.mkdir(parents=True, exist_ok=True)
    receipts = []
    scenes = data.get("scenes", [])
    for scene in scenes:
        if scene_filter and scene.get("scene_id") != scene_filter:
            continue
        for lane_id in sorted(scene.get("provider_inputs", {})):
            if lane_filter and lane_id != lane_filter:
                continue
            receipt = build_provider_request(scene, lane_id)
            receipt_path = out_dir / scene["scene_id"] / lane_id / "provider_request_dry_run.json"
            write_json(receipt_path, receipt)
            receipts.append(
                {
                    "scene_id": scene["scene_id"],
                    "lane_id": lane_id,
                    "status": receipt["status"],
                    "reasons": receipt["reasons"],
                    "receipt_path": str(receipt_path),
                }
            )
    ready = sum(1 for receipt in receipts if receipt["status"] == "ready_for_provider_request")
    manifest = {
        "schema": "persona_dream.provider_dry_run_manifest.v1",
        "created_at_utc": now_iso(),
        "provider_inputs": str(provider_inputs),
        "out_dir": str(out_dir),
        "scene_filter": scene_filter,
        "lane_filter": lane_filter,
        "receipt_count": len(receipts),
        "ready_count": ready,
        "needs_inputs_count": len(receipts) - ready,
        "receipts": receipts,
        "paid_call_performed": False,
    }
    write_json(out_dir / "provider_dry_run_manifest.json", manifest)
    return manifest


def build_submit_arguments(receipt: dict[str, Any]) -> dict[str, Any]:
    lane_id = receipt["lane_id"]
    prompt = receipt["prompt"]
    dialogue = receipt.get("exact_dialogue")
    if dialogue and dialogue not in prompt:
        prompt = f'{prompt} Horus says exactly: "{dialogue}"'
    duration = receipt.get("duration_target_sec") or 5
    duration_int = max(3, min(15, round(float(duration))))
    reference_images = [
        item["path"]
        for item in receipt.get("reference_image_receipts", [])
        if item.get("exists") and item.get("path")
    ]
    if lane_id == "kling_3_0_o3_omni":
        return {
            "prompt": prompt,
            "image_urls": "<uploaded by submit-provider --live>",
            "duration": str(duration_int),
            "aspect_ratio": "16:9",
            "generate_audio": True,
            "reference_image_paths": reference_images,
        }
    if lane_id == "seedance_2_0":
        return {
            "prompt": prompt,
            "image_url": "<first uploaded reference image by submit-provider --live>",
            "duration": str(duration_int),
            "aspect_ratio": "16:9",
            "generate_audio": True,
            "reference_image_paths": reference_images,
        }
    raise ValueError(f"Unsupported live provider lane: {lane_id}")


def do_submit_provider(receipt_path: Path, out_dir: Path | None, live: bool, no_logs: bool) -> dict[str, Any]:
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("schema") != "persona_dream.provider_request_dry_run.v1":
        raise ValueError(f"Not a provider_request_dry_run receipt: {receipt_path}")
    if receipt.get("status") != "ready_for_provider_request":
        raise ValueError(f"Receipt is not ready_for_provider_request: {receipt.get('reasons')}")

    lane_id = receipt["lane_id"]
    model = PROVIDER_MODELS.get(lane_id)
    if not model:
        raise ValueError(f"Unsupported provider lane: {lane_id}")
    if model["provider"] != "fal":
        raise ValueError(f"Unsupported provider: {model['provider']}")

    out_dir = out_dir or receipt_path.parent / ("live_submission" if live else "submit_dry_run")
    out_dir.mkdir(parents=True, exist_ok=True)
    provider_args_template = build_submit_arguments(receipt)
    image_paths = provider_args_template.pop("reference_image_paths")
    request = {
        "schema": "persona_dream.provider_submit_request.v1",
        "created_at_utc": now_iso(),
        "source_receipt": str(receipt_path),
        "scene_id": receipt["scene_id"],
        "lane_id": lane_id,
        "provider": model["provider"],
        "model_id": model["model_id"],
        "live": live,
        "paid_call_performed": False,
        "provider_args_template": {**provider_args_template, "reference_image_paths": image_paths},
        "expected_outputs": [
            "provider_response.json",
            "output.mp4",
            "ffprobe.json",
            "frame_sheet.jpg",
            "provider_submit_receipt.json",
        ],
    }
    write_json(out_dir / "provider_submit_request.json", request)

    if not live:
        result = {
            "schema": "persona_dream.provider_submit_receipt.v1",
            "created_at_utc": now_iso(),
            "source_receipt": str(receipt_path),
            "out_dir": str(out_dir),
            "status": "dry_run",
            "paid_call_performed": False,
            "model_id": model["model_id"],
            "provider_args_template": request["provider_args_template"],
            "next_command": (
                f"./run.sh contact-sheet submit-provider --receipt {receipt_path} "
                f"--out-dir {out_dir} --live"
            ),
        }
        write_json(out_dir / "provider_submit_receipt.json", result)
        return result

    _ensure_fal_key()
    import fal_client  # type: ignore

    upload_receipts = []
    uploaded_urls = []
    for path in image_paths:
        url = fal_client.upload_file(path)
        uploaded_urls.append(url)
        upload_receipts.append({"path": path, "url": url, "sha256": sha256_file(Path(path))})
    write_json(out_dir / "upload_receipts.json", {"schema": "persona_dream.provider_uploads.v1", "uploads": upload_receipts})

    live_args = dict(provider_args_template)
    if lane_id == "kling_3_0_o3_omni":
        live_args["image_urls"] = uploaded_urls
    elif lane_id == "seedance_2_0":
        live_args["image_url"] = uploaded_urls[0]

    queue_events_path = out_dir / "provider_queue_events.jsonl"

    def on_queue_update(update: Any) -> None:
        record = {"ts": now_iso(), "repr": repr(update)}
        status = getattr(update, "status", None)
        if status is not None:
            record["status"] = status
        logs = getattr(update, "logs", None)
        if logs is not None:
            record["logs_repr"] = repr(logs)
        with queue_events_path.open("a") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")

    response = fal_client.subscribe(
        model["model_id"],
        arguments=live_args,
        with_logs=not no_logs,
        on_queue_update=None if no_logs else on_queue_update,
    )
    write_json(out_dir / "provider_response.json", response)
    video_url = _extract_video_url(response)
    output_video = out_dir / "output.mp4"
    download_receipt = _download_url(video_url, output_video)
    write_json(out_dir / "download_receipt.json", download_receipt)
    ffprobe_receipt = _ffprobe(output_video)
    write_json(out_dir / "ffprobe.json", ffprobe_receipt)
    frame_sheet_receipt = _frame_sheet(output_video, out_dir / "frame_sheet.jpg")
    write_json(out_dir / "frame_sheet_receipt.json", frame_sheet_receipt)
    final = {
        "schema": "persona_dream.provider_submit_receipt.v1",
        "created_at_utc": now_iso(),
        "source_receipt": str(receipt_path),
        "out_dir": str(out_dir),
        "status": "output_ready" if output_video.exists() else "failed",
        "paid_call_performed": True,
        "model_id": model["model_id"],
        "provider_response": str(out_dir / "provider_response.json"),
        "output_video": str(output_video) if output_video.exists() else None,
        "ffprobe": str(out_dir / "ffprobe.json"),
        "frame_sheet": str(out_dir / "frame_sheet.jpg") if (out_dir / "frame_sheet.jpg").exists() else None,
        "manual_review_required": True,
    }
    write_json(out_dir / "provider_submit_receipt.json", final)
    return final


@app.command()
def build(
    asset_root: Annotated[Path, typer.Option(help="Directory containing images/, prompts/, receipts/.")],
    index_qdrant: Annotated[bool, typer.Option("--index-qdrant", help="Embed and upsert assets to Qdrant.")] = False,
    write_memory: Annotated[bool, typer.Option("--write-memory", help="Upsert asset pointer records to memory.")] = False,
    timed_script: Annotated[Path | None, typer.Option("--timed-script", help="Optional timed_transcript.json, storyboard.json, or scenes_script.json. Auto-discovered when omitted.")] = None,
) -> None:
    typer.echo(json.dumps(do_build(asset_root, index_qdrant, write_memory, timed_script), indent=2))


@app.command()
def amend(
    asset_root: Annotated[Path, typer.Option(help="Existing contact-sheet asset root to rescan/update.")],
    index_qdrant: Annotated[bool, typer.Option("--index-qdrant")] = False,
    write_memory: Annotated[bool, typer.Option("--write-memory")] = False,
    timed_script: Annotated[Path | None, typer.Option("--timed-script")] = None,
) -> None:
    typer.echo(json.dumps(do_build(asset_root, index_qdrant, write_memory, timed_script), indent=2))


@app.command("provider-dry-run")
def provider_dry_run(
    provider_inputs: Annotated[Path, typer.Option("--provider-inputs", help="provider_inputs.json generated by contact-sheet build.")],
    out_dir: Annotated[Path, typer.Option("--out-dir", help="Directory for dry-run provider request receipts.")],
    scene_id: Annotated[str | None, typer.Option("--scene-id", help="Optional scene_id filter.")] = None,
    lane_id: Annotated[str | None, typer.Option("--lane-id", help="Optional lane_id filter.")] = None,
) -> None:
    typer.echo(json.dumps(do_provider_dry_run(provider_inputs, out_dir, scene_id, lane_id), indent=2))


@app.command("submit-provider")
def submit_provider(
    receipt: Annotated[Path, typer.Option("--receipt", help="provider_request_dry_run.json to submit.")],
    out_dir: Annotated[Path | None, typer.Option("--out-dir", help="Output directory for submit receipts.")] = None,
    live: Annotated[bool, typer.Option("--live", help="Actually call the paid provider. Default is dry-run.")] = False,
    no_logs: Annotated[bool, typer.Option("--no-logs", help="Disable provider queue logs for live calls.")] = False,
) -> None:
    typer.echo(json.dumps(do_submit_provider(receipt, out_dir, live, no_logs), indent=2))


@app.command()
def retrieve(
    query: Annotated[str, typer.Option("--query", "-q", help="Recall query for contact-sheet assets.")],
    limit: Annotated[int, typer.Option("--limit", "-k")] = 5,
) -> None:
    with httpx.Client(base_url=MEMORY_URL, timeout=10) as client:
        response = client.post("/recall", json={"q": query, "k": limit, "collections": [MEMORY_COLLECTION]})
        response.raise_for_status()
        data = validate_http_json("memory_recall", response.json())
        if not data.get("found") or not data.get("items"):
            listed = client.post("/list", json={"collection": MEMORY_COLLECTION, "limit": 500})
            listed.raise_for_status()
            terms = [term.lower() for term in query.split() if len(term) > 2]
            docs = validate_http_json("memory_list", listed.json()).get("documents", [])
            scored = []
            for doc in docs:
                haystack = " ".join(
                    str(doc.get(field, ""))
                    for field in ("title", "description", "entity_type", "entity_id", "asset_id", "image_path")
                ).lower()
                score = sum(1 for term in terms if term in haystack)
                if score:
                    scored.append((score, doc))
            scored.sort(key=lambda item: item[0], reverse=True)
            data = {
                "found": bool(scored),
                "confidence": float(scored[0][0]) if scored else 0.0,
                "items": [doc for _, doc in scored[:limit]],
                "meta": {"fallback": "/list_local_filter", "collection": MEMORY_COLLECTION},
            }
    typer.echo(json.dumps(data, indent=2))


if __name__ == "__main__":
    app()
