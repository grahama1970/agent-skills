"""Thin orchestrator: validated scene table + reference images -> Kling request packet.

No bespoke logic. Each stage delegates to the owning skill and fails closed:
  1. scene table  -> best-practices-scene-script-writing scene_table.py validate/render
  2. references   -> local existence + one-file-per-character check
  3. compile      -> deterministic slot-budget prompt from the VALIDATED table
  4. packet gate  -> best-practices-kling-video kling_models validate (+ triage)
Failures at any stage are routed through triage-error (self-heal: ambiguous
signals mint a provisional catalog code).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import typer

SKILLS = Path(__file__).resolve().parents[2]
SCENE = SKILLS / "best-practices-scene-script-writing" / "scripts" / "scene_table.py"
KLING = SKILLS / "best-practices-kling-video" / "run.sh"
TRIAGE = SKILLS / "triage-error" / "run.sh"

app = typer.Typer(add_completion=False)


def _triage(signal: str, layer: str = "create_kling_scene") -> dict:
    try:
        r = subprocess.run([str(TRIAGE), "classify", "--text", signal[:2000], "--layer", layer],
                           capture_output=True, text=True, timeout=30)
        result = json.loads(r.stdout)
        if result.get("ambiguous"):
            r2 = subprocess.run([str(TRIAGE), "triage", "--text", signal[:2000], "--layer", layer],
                                capture_output=True, text=True, timeout=60)
            try:
                result = json.loads(r2.stdout)
            except Exception:
                pass
        return result
    except Exception as exc:
        return {"code": "triage_unavailable", "cause": str(exc)}


# Each stage's failures belong to the OWNING skill's triage layer.
STAGE_LAYER = {
    "scene_table_gate": "scene_script",
    "kling_packet_gate": "kling_video",
    "reference_check": "create_kling_scene",
}


def _fail(stage: str, errors: list, receipt: dict, out: Path) -> None:
    receipt["status"] = "BLOCKED"
    receipt["failed_stage"] = stage
    receipt["errors"] = errors
    signal = "; ".join(
        f"{e.get('type', '')}: {e.get('msg', e)}" if isinstance(e, dict) else str(e)
        for e in errors
    )
    receipt["triage"] = _triage(signal, layer=STAGE_LAYER.get(stage, "create_kling_scene"))
    out.write_text(json.dumps(receipt, indent=1, default=str))
    typer.echo(json.dumps(receipt, default=str))
    raise typer.Exit(1)


@app.command()
def build(
    scene: Path = typer.Option(..., help="scene_script.scene_table.v1 JSON"),
    refs: list[str] = typer.Option(..., help="name=/path/to/single_subject_crop.png per character"),
    model_id: str = typer.Option("fal-ai/kling-video/o3/standard/reference-to-video"),
    out_dir: Path = typer.Option(...),
):
    """Compose a validated scene table + refs into a validated Kling request packet."""
    out_dir.mkdir(parents=True, exist_ok=True)
    receipt: dict = {"schema": "create_kling_scene.receipt.v1", "stages": []}
    receipt_path = out_dir / "receipt.json"

    # Stage 1: scene table gate (owning skill's pydantic validator)
    r = subprocess.run(["uv", "run", "--with", "pydantic", "--with", "typer", "python",
                        str(SCENE), "validate", str(scene)], capture_output=True, text=True)
    gate = json.loads(r.stdout) if r.stdout.strip() else {"status": "FAIL", "errors": [r.stderr[-500:]]}
    receipt["stages"].append({"stage": "scene_table_gate", "result": gate})
    if gate.get("status") != "PASS":
        _fail("scene_table_gate", gate.get("errors", []), receipt, receipt_path)

    # Stage 2: reference check — every character row needs exactly one existing ref file
    table = json.loads(scene.read_text())
    characters = [e["element_id"] for e in table["elements"] if e["element_type"] == "character"]
    ref_map = dict(kv.split("=", 1) for kv in refs)
    missing = [c for c in characters
               if not any(k in c or c.endswith(k) for k in ref_map)] \
        + [f"{k}: file not found {v}" for k, v in ref_map.items() if not Path(v).exists()]
    receipt["stages"].append({"stage": "reference_check", "characters": characters, "refs": ref_map,
                              "missing": missing})
    if missing:
        _fail("reference_check", [f"missing character reference: {m}" for m in missing],
              receipt, receipt_path)

    # Stage 3: compile prompt from the VALIDATED table (rendered prose, slot budget)
    r = subprocess.run(["uv", "run", "--with", "pydantic", "--with", "typer", "python",
                        str(SCENE), "render", str(scene)], capture_output=True, text=True)
    prose = r.stdout.strip()
    names = {c: i + 1 for i, c in enumerate(characters)}
    bindings = " ".join(f"@Element{i} is {c.split('_', 1)[-1]}." for c, i in names.items())
    cast_guard = f"exactly {len(characters)} people, no one else present."
    prompt = f"{bindings} {prose} {cast_guard}"[:790]
    packet = {
        "schema": "kling_video.request.v1",
        "model_id": model_id,
        "request": {
            "prompt": prompt,
            "negative_prompt": "extra person, third person, crowd, text overlays, back of head only, face hidden",
            "elements": [
                {"frontal_image_url": ref_map[k], "reference_image_urls": [ref_map[k]]}
                for k in ref_map
            ],
        },
    }
    packet_path = out_dir / "kling_request.json"
    packet_path.write_text(json.dumps(packet, indent=1))
    receipt["stages"].append({"stage": "compile", "prompt_chars": len(prompt),
                              "packet": str(packet_path)})

    # Stage 4: Kling packet gate (owning skill's pydantic validator + its triage)
    # Local ref paths are placeholders until submit uploads them; validate shape with
    # fal-style URLs substituted so the gate checks everything else.
    shape = json.loads(packet_path.read_text())
    for el in shape["request"]["elements"]:
        el["frontal_image_url"] = "https://v3b.fal.media/placeholder.png"
        el["reference_image_urls"] = ["https://v3b.fal.media/placeholder.png"]
    shape_path = out_dir / "kling_request.shapecheck.json"
    shape_path.write_text(json.dumps(shape))
    r = subprocess.run([str(KLING), "validate", str(shape_path)], capture_output=True, text=True)
    gate = json.loads(r.stdout) if r.stdout.strip() else {"status": "FAIL", "errors": [r.stderr[-500:]]}
    receipt["stages"].append({"stage": "kling_packet_gate", "result": gate})
    if gate.get("status") != "PASS":
        _fail("kling_packet_gate", gate.get("errors", []), receipt, receipt_path)

    receipt["status"] = "PASS"
    receipt["packet"] = str(packet_path)
    receipt["next_command"] = (
        f"{KLING} submit {packet_path} --out-dir {out_dir}  # PAID; uploads local refs first"
    )
    receipt_path.write_text(json.dumps(receipt, indent=1, default=str))
    typer.echo(json.dumps(receipt, default=str))


if __name__ == "__main__":
    app()
