"""Typed scene table: the structured source of truth for a scene.

Prose prompts are RENDERED from this table, never authored directly.
Schema: scene_script.scene_table.v1
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

TRIAGE = Path(__file__).resolve().parents[2] / "triage-error" / "run.sh"

import typer
from pydantic import BaseModel, Field, model_validator

app = typer.Typer(add_completion=False)


class EnvironmentHeader(BaseModel, extra="forbid"):
    """The actual environment as structured facts, not prose."""
    location: str = Field(min_length=3, description="Specific place, e.g. 'gothic void-world terrace, flagstones, iron rail'")
    time_of_day: str = Field(min_length=2, description="e.g. 'perpetual storm dusk'")
    weather: str = Field(min_length=2, description="Named condition, e.g. 'dry electrical storm, no rain'")
    temperature: str = Field(min_length=2, description="e.g. 'cold; breath faintly visible'")
    humidity: str = Field(min_length=2, description="e.g. 'arid; no condensation'")
    wind: str = Field(min_length=2, description="Force + direction, e.g. 'steady wind left-to-right across frame'")
    light_sources: list[str] = Field(min_length=1, description="In-world sources, e.g. ['laptop glow', 'storm sky', 'lightning']")
    light_behavior: str = Field(min_length=3, description="e.g. 'glow flickers; lightning overexposes for single beats'")
    ambient_sound: str | None = Field(default=None, description="When audio-bearing, e.g. 'wind + distant creature calls'")


class ElementRow(BaseModel, extra="forbid"):
    """One row per relevant character/prop/creature in the scene."""
    element_id: str = Field(min_length=1, description="e.g. 'character_embry', 'prop_umbrella'")
    element_type: str = Field(pattern="^(character|prop|creature|surface|effect)$")
    description: str = Field(min_length=5, description="Physical/material state, e.g. 'porcelain teapot, glaze reflecting lightning'")
    environment_interaction: str = Field(
        min_length=5,
        description="How the environment touches it or it touches the environment; "
                    "explicit stillness needs a reason, e.g. 'hangs dead still in the airless calm'",
    )
    action: str | None = Field(default=None, description="Primary beat action (characters), physics-bearing verb")

    @model_validator(mode="after")
    def _interaction_has_substance(self) -> "ElementRow":
        # Deterministic ambiguity gate. Semantic depth is the review gate's job;
        # this rejects structurally vague text fail-closed.
        text = self.environment_interaction.strip().lower()
        filler = {"is there", "in the scene", "present", "visible", "exists", "n/a", "none", "-"}
        if text in filler:
            raise ValueError(f"{self.element_id}: environment_interaction is filler, not an interaction")
        if len(text.split()) < 3:
            raise ValueError(f"{self.element_id}: environment_interaction too thin (<3 words); state force+effect or stillness+reason")
        VAGUE_WORDS = {"nice", "beautiful", "cinematic", "atmospheric", "epic", "interesting", "cool", "amazing", "stunning", "dramatic"}
        for field_name, value in (("description", self.description), ("environment_interaction", self.environment_interaction)):
            hits = VAGUE_WORDS & set(value.lower().replace(",", " ").split())
            if hits:
                raise ValueError(
                    f"{self.element_id}.{field_name}: vague adjective {sorted(hits)} does the work a "
                    "physical fact should do; replace with a state/force/effect"
                )
        return self


class SceneTable(BaseModel, extra="forbid"):
    schema_: str = Field(alias="schema", default="scene_script.scene_table.v1")
    scene_id: str = Field(min_length=1)
    environment: EnvironmentHeader
    elements: list[ElementRow] = Field(min_length=1)

    @model_validator(mode="after")
    def _characters_act(self) -> "SceneTable":
        for e in self.elements:
            if e.element_type == "character" and not e.action:
                raise ValueError(f"{e.element_id}: characters require an action beat")
        return self


def render_prose(table: SceneTable) -> str:
    """Deterministic prose rendering for prompt slots (behaviors/environment/lighting)."""
    env = table.environment
    parts = [f"{env.location}, {env.time_of_day}. {env.weather}; {env.wind}."]
    for e in table.elements:
        bits = [e.description, e.environment_interaction]
        if e.action:
            bits.insert(0, e.action)
        parts.append(f"{e.element_id.split('_', 1)[-1].replace('_', ' ')}: " + "; ".join(bits) + ".")
    parts.append(f"Lit by {', '.join(env.light_sources)}: {env.light_behavior}.")
    return " ".join(parts)


@app.command()
def validate(path: Path):
    """Validate a scene table; pydantic errors() JSON on failure."""
    try:
        t = SceneTable.model_validate(json.loads(path.read_text()))
        typer.echo(json.dumps({"status": "PASS", "elements": len(t.elements)}))
    except Exception as e:
        errors = e.errors() if hasattr(e, "errors") else [{"msg": str(e)}]
        out = {"status": "FAIL", "errors": errors}
        out["triage"] = _triage("; ".join(str(err.get("msg", err)) for err in errors))
        typer.echo(json.dumps(out, default=str))
        raise typer.Exit(1)


def _triage(signal: str) -> dict:
    """Route the raw failure signal through triage-error (never emit a bare generic code)."""
    try:
        r = subprocess.run(
            [str(TRIAGE), "classify", "--text", signal[:2000], "--layer", "scene_script"],
            capture_output=True, text=True, timeout=30,
        )
        return json.loads(r.stdout)
    except Exception as exc:  # ponytail: triage unavailable degrades to a note, validation still fails closed
        return {"code": "triage_unavailable", "cause": str(exc)}


@app.command()
def render(path: Path):
    """Render validated table to prompt prose (stdout)."""
    t = SceneTable.model_validate(json.loads(path.read_text()))
    typer.echo(render_prose(t))


if __name__ == "__main__":
    app()
