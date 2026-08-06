"""Imagegen variation fan-out for slide visuals (#1230).

compile_brief turns a slide's visual need + theme tokens into a generation
brief (so variations match the deck palette instead of generic AI-art drift).
emit_variation_plan writes N prompt variants plus a tau-DAG-shaped spec; when
OPENAI_API_KEY is present, run_variations executes them live through the
system imagegen CLI and writes a contact sheet. Selected images enter through
the NORMAL asset intake (magic bytes, alt text) as ILLUSTRATION assets whose
generation_brief marks them for the GENERATED_ASSET_CLAIM_SURFACE gate.
Failure modes: missing key or missing imagegen CLI reports NEEDS_ATTENTION —
never a fabricated image, never a silent skip.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from loguru import logger

from .models import DeckManifest

_AXES = [
    "clean minimal geometric composition, generous negative space",
    "abstract technical illustration, subtle grid texture",
    "dramatic single focal object, soft depth of field",
    "flat vector style, bold shapes, no text",
]

IMAGEGEN_CLI = (
    Path(__file__).resolve().parents[3] / ".system" / "imagegen" / "scripts" / "image_gen.py"
)


def compile_brief(deck: DeckManifest, slide_id: str) -> str:
    slide = next((s for s in deck.slides if s.id == slide_id), None)
    if slide is None:
        raise ValueError(f"no slide '{slide_id}'")
    tokens = deck.deck.theme_tokens
    return (
        f"Illustration for a pitch-deck slide titled '{slide.title}'. "
        f"Theme: dark background, accent color {tokens.accent}. "
        f"Concept: {slide.message} "
        "Decorative and abstract — MUST NOT contain any text, numbers, charts, or diagrams."
    )


def emit_variation_plan(deck: DeckManifest, slide_id: str, output_dir: Path, count: int = 4) -> Path:
    brief = compile_brief(deck, slide_id)
    variants = [f"{brief} Style: {_AXES[i % len(_AXES)]}" for i in range(count)]
    plan = {
        "schema": "pitchdeck.image_variation_plan.v1",
        "slide_id": slide_id,
        "brief": brief,
        "variants": variants,
        "tau_dag": {
            "topology": "concurrent",
            "nodes": [
                {"id": f"imagegen-{i + 1}", "handler": "imagegen", "prompt": v}
                for i, v in enumerate(variants)
            ],
            "join": {"id": "contact-sheet", "type": "human-select"},
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    plan_path = output_dir / "variation_plan.json"
    plan_path.write_text(json.dumps(plan, indent=1), encoding="utf-8")
    return plan_path


def run_variations(plan_path: Path, output_dir: Path) -> dict:
    """Execute the plan live via the system imagegen CLI; contact-sheet the results."""
    if not os.getenv("OPENAI_API_KEY"):
        return {"status": "NEEDS_ATTENTION", "reason": "OPENAI_API_KEY is not set; live generation blocked"}
    if not IMAGEGEN_CLI.exists():
        return {"status": "NEEDS_ATTENTION", "reason": f"imagegen CLI not found at {IMAGEGEN_CLI}"}
    plan = json.loads(plan_path.read_text())
    produced: list[str] = []
    for index, prompt in enumerate(plan["variants"], start=1):
        out = output_dir / f"variant-{index}.png"
        result = subprocess.run(
            ["python3", str(IMAGEGEN_CLI), "--prompt", prompt, "--output", str(out)],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0 and out.exists():
            produced.append(str(out))
        else:
            logger.error("variant {} failed: {}", index, result.stderr[-200:])
    status = "PASS" if len(produced) == len(plan["variants"]) else "USABLE_WITH_GAPS" if produced else "NEEDS_ATTENTION"
    if produced:
        from PIL import Image

        images = [Image.open(p).convert("RGB") for p in produced]
        width = min(i.width for i in images)
        resized = [i.resize((width, round(i.height * width / i.width))) for i in images]
        sheet = Image.new("RGB", (width, sum(i.height for i in resized)), "black")
        y = 0
        for i in resized:
            sheet.paste(i, (0, y))
            y += i.height
        sheet.save(output_dir / "contact_sheet.png")
    return {"status": status, "produced": produced}
