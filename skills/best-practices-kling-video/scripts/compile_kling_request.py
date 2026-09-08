"""Compile large pipeline artifacts into a bounded, validated Kling request.

Slot-budget condenser: identity travels in elements[], never prose.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

TRIAGE = Path(__file__).resolve().parents[2] / "triage-error" / "run.sh"


def _triage(signal: str) -> dict:
    """Route raw validation failure through triage-error; self-heal on ambiguous (mint + persist code)."""
    try:
        r = subprocess.run(
            [str(TRIAGE), "classify", "--text", signal[:2000], "--layer", "kling_video"],
            capture_output=True, text=True, timeout=30,
        )
        result = json.loads(r.stdout)
        if result.get("ambiguous"):
            r2 = subprocess.run(
                [str(TRIAGE), "triage", "--text", signal[:2000], "--layer", "kling_video"],
                capture_output=True, text=True, timeout=60,
            )
            try:
                result = json.loads(r2.stdout)
            except Exception:
                pass
        return result
    except Exception as exc:  # ponytail: triage unavailable degrades to a note; validation still fails closed
        return {"code": "triage_unavailable", "cause": str(exc)}

import typer

sys.path.insert(0, str(Path(__file__).parent))
from kling_models import KlingRequestPacket, SINGLE_PROMPT_MAX  # noqa: E402

app = typer.Typer(add_completion=False)

SLOTS = ("action", "environment", "camera", "mood")
BUDGETS = {"action": 200, "environment": 150, "camera": 100, "mood": 100}


def _truncate_words(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(",;")


def _first_str(obj, *keys) -> str:
    """Walk dicts/lists collecting the first non-empty string under any of keys."""
    if isinstance(obj, dict):
        for k in keys:
            v = obj.get(k)
            if isinstance(v, str) and v.strip():
                return v
        for v in obj.values():
            r = _first_str(v, *keys)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _first_str(v, *keys)
            if r:
                return r
    return ""


@app.command()
def compile(
    out: Path = typer.Option(...),
    storyboard: Path = typer.Option(None),
    bible: Path = typer.Option(None),
    look_lock: Path = typer.Option(None),
    refs: list[str] = typer.Option([], help="name=url_or_path per character, order = @ElementN order"),
    action: str = typer.Option("", help="override action slot"),
    environment: str = typer.Option("", help="override environment slot"),
    camera: str = typer.Option("", help="override camera slot"),
    mood: str = typer.Option("cinematic, intimate, no text overlays"),
    duration: str = typer.Option("5"),
    model_id: str = typer.Option("fal-ai/kling-video/o3/standard/reference-to-video"),
    negative_prompt: str = typer.Option("text, subtitles, watermark, gore"),
):
    """Condense pipeline artifacts into slot-budgeted prompt + elements."""
    sb = json.loads(storyboard.read_text()) if storyboard else {}
    ll = json.loads(look_lock.read_text()) if look_lock else {}

    slots = {
        "action": action or _first_str(sb, "action", "motion", "blocking", "description"),
        "environment": environment or _first_str(sb, "environment", "setting", "location"),
        "camera": camera or _first_str(ll, "camera", "shot_type", "movement"),
        "mood": mood,
    }
    names = [r.split("=", 1)[0] for r in refs]
    binding = " ".join(f"@Element{i+1} is {n}." for i, n in enumerate(names))
    body = ". ".join(_truncate_words(slots[s], BUDGETS[s]) for s in SLOTS if slots[s])
    prompt = f"{binding} {body}".strip()
    if len(prompt) > SINGLE_PROMPT_MAX:
        prompt = prompt[:SINGLE_PROMPT_MAX].rsplit(".", 1)[0] + "."

    elements = []
    for r in refs:
        _, src = r.split("=", 1)
        # local paths stay as-is; submit step uploads and rewrites to public URLs
        url = src if src.startswith("https://") else f"file://{Path(src).resolve()}"
        elements.append({"frontal_image_url": url, "reference_image_urls": [url]})

    packet = {
        "schema": "kling_video.request.v1",
        "model_id": model_id,
        "request": {
            "prompt": prompt,
            "elements": elements or None,
            "duration": duration,
            "aspect_ratio": "16:9",
            "generate_audio": False,
            "negative_prompt": negative_prompt,
        },
    }
    packet["request"] = {k: v for k, v in packet["request"].items() if v is not None}
    # validate with file:// tolerated pre-upload by swapping scheme for the check
    check = json.loads(json.dumps(packet).replace("file:///", "https://pending.upload/"))
    KlingRequestPacket.model_validate(check)
    packet["seam_validation"] = {"kind": "kling_video.request.v1", "status": "PASS"}
    out.write_text(json.dumps(packet, indent=2))
    typer.echo(json.dumps({"status": "PASS", "out": str(out), "prompt_chars": len(prompt)}))


@app.command()
def validate(packet_path: Path):
    """Validate a packet; exit 1 with pydantic errors() JSON on failure."""
    try:
        KlingRequestPacket.model_validate(json.loads(packet_path.read_text()))
        typer.echo(json.dumps({"status": "PASS"}))
    except Exception as e:  # pydantic ValidationError has .errors()
        errors = e.errors() if hasattr(e, "errors") else [{"msg": str(e)}]
        triage = _triage("; ".join(f"{err.get('type', '')}: {err.get('msg', err)}" for err in errors))
        typer.echo(json.dumps({"status": "FAIL", "errors": errors, "triage": triage}, default=str))
        raise typer.Exit(1)


@app.command()
def submit(packet_path: Path, out_dir: Path = typer.Option(...)):
    """Upload local refs, validate, submit (PAID), poll, download video."""
    import fal_client

    packet = json.loads(packet_path.read_text())
    req = packet["request"]

    def _up(u: str) -> str:
        return fal_client.upload_file(u[len("file://"):]) if u.startswith("file://") else u

    for el in req.get("elements", []):
        if el.get("frontal_image_url", "").startswith("file://"):
            el["frontal_image_url"] = _up(el["frontal_image_url"])
        if el.get("reference_image_urls"):
            el["reference_image_urls"] = [_up(u) for u in el["reference_image_urls"]]
    for key in ("image_urls",):
        if req.get(key):
            req[key] = [_up(u) for u in req[key]]
    for key in ("start_image_url", "end_image_url"):
        if req.get(key):
            req[key] = _up(req[key])
    KlingRequestPacket.model_validate(packet)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "kling_request.json").write_text(json.dumps(packet, indent=2))
    result = fal_client.subscribe(packet["model_id"], arguments=req, with_logs=True)
    (out_dir / "kling_response.json").write_text(json.dumps(result, indent=2))
    video_url = result["video"]["url"]
    import urllib.request

    urllib.request.urlretrieve(video_url, out_dir / "kling_dream.mp4")
    typer.echo(json.dumps({"status": "PASS", "video": str(out_dir / "kling_dream.mp4"),
                           "bytes": (out_dir / "kling_dream.mp4").stat().st_size}))


if __name__ == "__main__":
    app()
