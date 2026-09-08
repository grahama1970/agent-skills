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
from pydantic import BaseModel, Field, model_validator

SKILLS = Path(__file__).resolve().parents[2]
INTERVIEW = SKILLS / "interview" / "run.sh"


class ImageRef(BaseModel, extra="forbid"):
    """A character reference image must be a real decodable PNG/JPEG, not just an existing path."""
    name: str
    path: str

    @model_validator(mode="after")
    def _real_image(self) -> "ImageRef":
        p = Path(self.path)
        if not p.exists():
            raise ValueError(f"{self.name}: reference file not found: {self.path}")
        head = p.read_bytes()[:12]
        if not (head.startswith(b"\x89PNG\r\n\x1a\n") or head.startswith(b"\xff\xd8\xff")):
            raise ValueError(f"{self.name}: not a PNG or JPEG (bad magic bytes): {self.path}")
        if p.stat().st_size < 1024:
            raise ValueError(f"{self.name}: image under 1KB is not a usable reference: {self.path}")
        return self


class VoiceWav(BaseModel, extra="forbid"):
    """A voice WAV must be a real RIFF/WAVE file within Kling voice bounds (Rule 8: 5-30s clone, 2-60s lipsync)."""
    name: str
    path: str
    purpose: str = Field(default="lipsync", pattern="^(lipsync|voice_clone)$")
    duration_s: float | None = None

    @model_validator(mode="after")
    def _real_wav(self) -> "VoiceWav":
        import wave
        p = Path(self.path)
        if not p.exists():
            raise ValueError(f"{self.name}: wav file not found: {self.path}")
        try:
            with wave.open(str(p), "rb") as w:
                frames, rate = w.getnframes(), w.getframerate()
        except Exception as exc:
            raise ValueError(f"{self.name}: not a readable RIFF/WAVE file: {exc}")
        self.duration_s = round(frames / float(rate), 2)
        lo, hi = (5.0, 30.0) if self.purpose == "voice_clone" else (2.0, 60.0)
        if not (lo <= self.duration_s <= hi):
            raise ValueError(
                f"{self.name}: wav duration {self.duration_s}s outside Kling {self.purpose} bounds {lo}-{hi}s"
            )
        return self


class PromptSlots(BaseModel, extra="forbid"):
    """Rule 3 slot budget as typed data, validated before any prompt string exists."""
    bindings: str = Field(min_length=5, max_length=160)
    action: str = Field(min_length=10, max_length=260)
    environment: str = Field(min_length=10, max_length=220)
    lighting: str = Field(min_length=5, max_length=140)
    cast_guard: str = Field(min_length=10, max_length=90)
    negative: str = Field(min_length=5, max_length=300)


class KlingInstructions(BaseModel, extra="forbid"):
    """create_kling_scene.instructions.v1: the typed FINAL instructions, validated
    BEFORE conversion to kling_video.request.v1. This is the last human-meaningful
    representation; the converter below it is mechanical."""
    schema_: str = Field(alias="schema", default="create_kling_scene.instructions.v1")
    scene_id: str = Field(min_length=1)
    model_id: str
    characters: list[str] = Field(min_length=1, max_length=4)
    references: list[ImageRef] = Field(min_length=1)
    voices: list[VoiceWav] = Field(default=[])
    slots: PromptSlots

    @model_validator(mode="after")
    def _cross_checks(self) -> "KlingInstructions":
        # POSITIONAL identity binding (webgpt review 2026-09-08): @ElementN is positional in
        # the Kling API, so references[i] MUST belong to characters[i]. Substring/set
        # matching allowed a silent identity swap.
        if len(self.references) != len(self.characters):
            raise ValueError(
                f"reference_set_mismatch: {len(self.characters)} characters vs {len(self.references)} references"
            )
        for i, (c, r) in enumerate(zip(self.characters, self.references), start=1):
            if not (c == r.name or c.endswith(f"_{r.name}") or c.split("_", 1)[-1] == r.name):
                raise ValueError(
                    f"element_binding_order_mismatch: @Element{i} expected {c}, got reference '{r.name}'"
                )
        if len({r.name for r in self.references}) != len(self.references):
            raise ValueError("duplicate_reference_name")
        for i, c in enumerate(self.characters, 1):
            if f"@Element{i}" not in self.slots.bindings:
                raise ValueError(f"@Element{i} missing from bindings for {c}")
        total = sum(len(v) for v in (self.slots.bindings, self.slots.action,
                                     self.slots.environment, self.slots.lighting, self.slots.cast_guard))
        if total > 790:
            raise ValueError(f"combined prompt slots {total} chars exceed ~800 effective budget")
        for v in self.voices:
            if not any(v.name in c or c.endswith(v.name) for c in self.characters):
                raise ValueError(f"voice wav '{v.name}' does not match any character")
        return self

    def audio_plan(self) -> dict:
        """Every validated voice MUST be consumed downstream (webgpt review: a valid WAV
        silently vanishing from the packet is a hard failure, not a quiet success)."""
        return {
            "schema": "create_kling_scene.audio_plan.v1",
            "voices": [{"name": v.name, "path": v.path, "purpose": v.purpose,
                        "duration_s": v.duration_s} for v in self.voices],
            "next_stage": "fal-ai/kling-video/lipsync/audio-to-video" if self.voices else None,
        }


class Stage(BaseModel, extra="forbid"):
    stage: str
    result: dict | None = None
    characters: list[str] | None = None
    refs: dict | None = None
    missing: list | None = None
    prompt_chars: int | None = None
    packet: str | None = None


class Receipt(BaseModel, extra="forbid"):
    """Producer-side typed seam: every receipt write validates first (fail-closed)."""
    schema_: str = Field(alias="schema", default="create_kling_scene.receipt.v1")
    stages: list[Stage]
    status: str = Field(default="IN_PROGRESS", pattern="^(IN_PROGRESS|PASS|BLOCKED)$")
    failed_stage: str | None = None
    errors: list | None = None
    triage: dict | None = None
    needs_attention: list[dict] | None = None
    packet: str | None = None
    next_command: str | None = None
    seam_validation: dict = Field(default={"kind": "create_kling_scene.receipt.v1", "status": "PASS"})


def _write_receipt(receipt: dict, out: Path) -> None:
    receipt = json.loads(json.dumps(receipt, default=str))  # errors() ctx may hold exception objects
    validated = Receipt.model_validate(receipt)  # raises on drift; never warn-and-continue
    out.write_text(validated.model_dump_json(by_alias=True, indent=1))
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
    triage = _triage(signal, layer=STAGE_LAYER.get(stage, "create_kling_scene"))
    receipt["triage"] = triage
    # Escalate to $interview when triage-error cannot fix it: an unrecoverable code,
    # a freshly minted unclassified code, or an unavailable classifier all mean no
    # deterministic next_command exists — a human decision is required.
    unresolvable = (
        triage.get("recoverable") is False
        or "_unclassified_" in str(triage.get("code", ""))
        or triage.get("code") == "triage_unavailable"
    )
    if unresolvable:
        questions = {
            "title": "create-kling-scene blocked: human decision required",
            "context": f"Stage {stage} failed with triage code {triage.get('code')} and no deterministic repair.",
            "questions": [{
                "id": "repair_decision",
                "header": "Repair",
                "text": f"Stage '{stage}' failed: {signal[:300]}. How should this proceed?",
                "options": [
                    {"label": "Fix the input and rerun", "description": "Edit the scene table / refs per the errors and rerun build"},
                    {"label": "Accept as intentional exception", "description": "Record a human-accepted exception for this requirement"},
                    {"label": "Abandon this scene", "description": "Stop; do not generate"},
                ],
                "multi_select": False,
            }],
        }
        qpath = out.parent / "interview_questions.json"
        qpath.write_text(json.dumps(questions, indent=1))
        receipt["needs_attention"] = [{
            "reason": "triage_unresolvable",
            "safe_default": "do_not_generate",
            "resume_hint": f"{INTERVIEW} --file {qpath}",
        }]
    _write_receipt(receipt, out)
    typer.echo(json.dumps(receipt, default=str))
    raise typer.Exit(1)


@app.command()
def build(
    scene: Path = typer.Option(..., help="scene_script.scene_table.v1 JSON"),
    refs: list[str] = typer.Option(..., help="name=/path/to/single_subject_crop.png per character"),
    voice: list[str] = typer.Option([], help="name=/path/to/voice.wav (lipsync bounds 2-60s)"),
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

    # Stage 2: media gate — every ref is a real decodable image, every wav a real bounded WAV
    table = json.loads(scene.read_text())
    characters = [e["element_id"] for e in table["elements"] if e["element_type"] == "character"]
    pairs = [kv.split("=", 1) for kv in refs]
    if len({k for k, _ in pairs}) != len(pairs):
        _fail("reference_check", [{"type": "value_error", "msg": "duplicate_reference_name in --refs"}],
              receipt, receipt_path)
    # Order references by scene-table character order, NOT CLI order (positional @ElementN).
    cli_map = dict(pairs)
    voice_map = dict(kv.split("=", 1) for kv in voice)
    media_errors: list[dict] = []
    images: list[ImageRef] = []
    wavs: list[VoiceWav] = []
    ordered_names = []
    for c in characters:
        match = next((k for k in cli_map if k == c or c.endswith(f"_{k}") or c.split("_", 1)[-1] == k), None)
        if match:
            ordered_names.append(match)
    ref_map = {k: cli_map[k] for k in ordered_names + [k for k in cli_map if k not in ordered_names]}
    for k, v in ref_map.items():
        try:
            images.append(ImageRef(name=k, path=v))
        except Exception as e:
            media_errors.extend(e.errors() if hasattr(e, "errors") else [{"type": "value_error", "msg": str(e)}])
    for k, v in voice_map.items():
        try:
            wavs.append(VoiceWav(name=k, path=v))
        except Exception as e:
            media_errors.extend(e.errors() if hasattr(e, "errors") else [{"type": "value_error", "msg": str(e)}])
    missing = [c for c in characters if not any(k in c or c.endswith(k) for k in ref_map)]
    media_errors.extend({"type": "value_error", "msg": f"missing character reference: {c}"} for c in missing)
    receipt["stages"].append({"stage": "reference_check", "characters": characters, "refs": ref_map,
                              "missing": missing})
    if media_errors:
        _fail("reference_check", media_errors, receipt, receipt_path)

    # Stage 3: compile prompt from the VALIDATED table (rendered prose, slot budget)
    r = subprocess.run(["uv", "run", "--with", "pydantic", "--with", "typer", "python",
                        str(SCENE), "render", str(scene)], capture_output=True, text=True)
    prose = r.stdout.strip()
    env = table["environment"]
    names = {c: i + 1 for i, c in enumerate(characters)}
    try:
        instructions = KlingInstructions(
            scene_id=table["scene_id"],
            model_id=model_id,
            characters=characters,
            references=images,
            voices=wavs,
            slots=PromptSlots(
                bindings=" ".join(f"@Element{i} is {c.split('_', 1)[-1]}." for c, i in names.items()),
                action=prose[:260],
                environment=f"{env['location']}, {env['time_of_day']}. {env['weather']}; {env['wind']}."[:220],
                lighting=f"Lit by {', '.join(env['light_sources'])}: {env['light_behavior']}."[:140],
                cast_guard=f"exactly {len(characters)} people, no one else present.",
                negative="extra person, third person, crowd, text overlays, back of head only, face hidden",
            ),
        )
    except Exception as e:
        errors = e.errors() if hasattr(e, "errors") else [{"type": "value_error", "msg": str(e)}]
        receipt["stages"].append({"stage": "instructions_gate", "result": {"status": "FAIL"}})
        _fail("instructions_gate", errors, receipt, receipt_path)
    instructions_path = out_dir / "kling_instructions.json"
    instructions_path.write_text(instructions.model_dump_json(by_alias=True, indent=1))
    receipt["stages"].append({"stage": "instructions_gate", "result": {"status": "PASS"},
                              "packet": str(instructions_path)})

    # Mechanical conversion: validated instructions -> kling_video.request.v1. No decisions here.
    s = instructions.slots
    prompt = f"{s.bindings} {s.action} {s.environment} {s.lighting} {s.cast_guard}"
    packet = {
        "schema": "kling_video.request.v1",
        "model_id": instructions.model_id,
        "request": {
            "prompt": prompt,
            "negative_prompt": s.negative,
            "elements": [
                {"frontal_image_url": r.path, "reference_image_urls": [r.path]}
                for r in instructions.references
            ],
        },
    }
    packet_path = out_dir / "kling_request.json"
    packet_path.write_text(json.dumps(packet, indent=1))
    if instructions.voices:
        # validated_voice_not_consumed guard: the packet has no audio field, so a durable
        # audio plan MUST exist naming the follow-on lipsync stage for every voice.
        (out_dir / "audio_plan.json").write_text(json.dumps(instructions.audio_plan(), indent=1))
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
    _write_receipt(receipt, receipt_path)
    typer.echo(json.dumps(receipt, default=str))


if __name__ == "__main__":
    app()
