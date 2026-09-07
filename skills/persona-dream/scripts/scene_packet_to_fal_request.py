#!/usr/bin/env python3
"""Collapse a kling.scene_packet.v1 into a fal reference-to-video request.

This is the "narrow" stage: the persona-dream pipeline assembles all scene
information (cast, element packs, storyboard beats, camera, negative prompt)
into a rich scene packet; this adapter condenses that into the small set of
clean reference images + bounded prompt text that Kling actually obeys, then
validates it against the persona-agnostic best-practices-kling-video gate.

Identity travels in elements[] (clean element-pack crops), never prose.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

ROOT = Path(__file__).resolve().parents[1]
SKILL = Path.home() / ".pi/agent/skills/best-practices-kling-video/scripts"
sys.path.insert(0, str(SKILL))
from kling_models import KlingRequestPacket, SINGLE_PROMPT_MAX  # noqa: E402

app = typer.Typer(add_completion=False)

MODEL = "fal-ai/kling-video/o3/standard/reference-to-video"


def _element_pack(character_id: str) -> tuple[str, list[str]]:
    """Return (frontal_path, reference_paths) from the built element pack."""
    pack = ROOT / "reports/assets/element_packs" / character_id
    imgs = sorted(pack.glob("*.png")) if pack.exists() else []
    if not imgs:
        raise FileNotFoundError(f"no element pack for {character_id} at {pack}")
    frontal = next((p for p in imgs if "front" in p.name or "face" in p.name), imgs[0])
    refs = [p for p in imgs if p != frontal] or [frontal]
    return str(frontal), [str(p) for p in refs]


def _condense(scene: dict, env_element: str) -> str:
    """One bounded prompt: element bindings + first beat's provider text.

    Environment is a style ref (@Image1), NOT a character; exclude it from the
    cast bindings and the closed-cast count.
    """
    elements = [e for e in scene.get("element_list", [])
                if e["token"].strip("<>").replace("element_", "") != env_element
                and e.get("type") != "environment"]
    names = [e["token"].strip("<>").replace("element_", "") for e in elements]
    bindings = " ".join(f"@Element{i+1} is {n}." for i, n in enumerate(names))
    closed = f" Exactly {len(names)} people; no one else present." if names else ""
    beats = scene.get("multi_prompt", [])
    beat = beats[0]["prompt"] if beats else ""
    # strip internal tokens; Kling reads @ElementN, not <<<...>>>
    import re
    beat = re.sub(r"<<<[^>]+>>>", "", beat)
    prompt = f"{bindings}{closed} {' '.join(beat.split())}".strip()
    if len(prompt) > SINGLE_PROMPT_MAX:
        prompt = prompt[:SINGLE_PROMPT_MAX].rsplit(".", 1)[0] + "."
    return prompt


@app.command()
def build(
    scene_packet: Path = typer.Argument(...),
    out: Path = typer.Option(...),
    env_element: str = typer.Option("tyranid_environment", help="element pack id used as environment @Image1"),
    duration: str = typer.Option("7"),
):
    scene = json.loads(scene_packet.read_text())
    elements = []
    for e in scene.get("element_list", []):
        cid = e["token"].strip("<>").replace("element_", "")
        if cid == env_element:
            continue
        frontal, refs = _element_pack(cid)
        elements.append({
            "frontal_image_url": f"file://{frontal}",
            "reference_image_urls": [f"file://{p}" for p in refs],
        })
    image_urls = None
    if (ROOT / "reports/assets/element_packs" / env_element).exists():
        env_frontal, _ = _element_pack(env_element)
        image_urls = [f"file://{env_frontal}"]

    prompt = _condense(scene, env_element)
    if image_urls:
        prompt += " Match the environment, furniture, and sky of @Image1 exactly."
    neg = scene.get("negative_prompt")
    if isinstance(neg, list):
        neg = ", ".join(neg)

    packet = {
        "schema": "kling_video.request.v1",
        "model_id": MODEL,
        "request": {
            "prompt": prompt[:SINGLE_PROMPT_MAX],
            "elements": elements or None,
            "image_urls": image_urls,
            "duration": duration,
            "aspect_ratio": "16:9",
            "generate_audio": False,
            "negative_prompt": neg or "extra person, third person, crowd, text, subtitles, watermark",
        },
    }
    packet["request"] = {k: v for k, v in packet["request"].items() if v is not None}
    # validate against the skill gate (file:// tolerated pre-upload)
    check = json.loads(json.dumps(packet).replace("file:///", "https://pending.upload/"))
    KlingRequestPacket.model_validate(check)
    packet["seam_validation"] = {"kind": "kling_video.request.v1", "status": "PASS"}
    out.write_text(json.dumps(packet, indent=2))
    typer.echo(json.dumps({"status": "PASS", "out": str(out), "elements": len(elements),
                           "prompt_chars": len(packet["request"]["prompt"])}))


if __name__ == "__main__":
    app()
