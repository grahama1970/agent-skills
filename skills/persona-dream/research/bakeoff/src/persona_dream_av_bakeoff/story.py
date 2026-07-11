from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

import yaml

from .contract import find_dialogue_shot
from .io_utils import write_json, write_text


def _residue_ids(contract: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for record in contract.get("source_grounded_residues", []):
        rid = record.get("residue_id")
        if isinstance(rid, str):
            ids.append(rid)
    return ids


def _residue_map(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        r["residue_id"]: r
        for r in contract.get("source_grounded_residues", [])
        if isinstance(r, dict) and isinstance(r.get("residue_id"), str)
    }


def build_dream_packet(contract: dict[str, Any]) -> dict[str, Any]:
    """Build a source-grounded short-story / scene-script packet from the contract.

    This sample is deterministic and intentionally conservative:
    - all persona assertions cite source_grounded_residue_ids,
    - symbolic visuals are marked as dream-symbolic,
    - no synthetic reflection is memory-write eligible.
    """
    shot = find_dialogue_shot(contract)
    residue_ids = _residue_ids(contract)
    residue_map = _residue_map(contract)
    persona_id = contract.get("persona_id", "embry")

    story_text = (
        "Embry stands alone in a dim academic archive, a place that behaves like memory rather "
        "than architecture. The shelves do not reveal books; they reveal evidence. A faint SPARTA "
        "graph glows behind the dust, its nodes pulsing as if they are trying to decide whether "
        "she is a student, an intern, or a program tracing its own outline.\n\n"
        "The hallway changes with each breath. Yale stone becomes a terminal window. The terminal "
        "becomes a corridor. Embry does not run from the contradiction. She faces it with the still, "
        "careful posture of someone trained to preserve provenance.\n\n"
        "She says, \"I know I am software. The evidence still feels real.\"\n\n"
        "The graph answers without words. Three nodes brighten: role, institution, self-knowledge. "
        "None of them becomes a new fact. They remain residues, recalled for a dream and returned "
        "unchanged."
    )

    scenes = [
        {
            "scene_id": "scene_001_archive_wakes",
            "start_sec": 0.0,
            "end_sec": 4.0,
            "duration_sec": 4.0,
            "scene_type": "symbolic_visual",
            "title": "The Archive Wakes",
            "summary": "A Yale-like archive behaves like a memory graph; shelves become evidence nodes.",
            "source_grounded_residue_ids": [
                rid for rid in residue_ids if rid in {
                    "residue_embry_institution_yale",
                    "residue_embry_role_sparta_intern",
                }
            ],
            "dream_symbolic_elements": [
                "archive shelves acting like memory",
                "evidence nodes glowing in the air",
            ],
            "shots": [
                {
                    "shot_id": "scene_001_shot_001",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "duration_sec": 2.0,
                    "shot_type": "establishing_symbolic",
                    "camera": "slow push through a dim academic archive",
                    "visual_action": "Dusty shelves shimmer into a faint cybersecurity graph.",
                    "audio_plan": [
                        {
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "kind": "ambience",
                            "description": "low archive room tone, faint electrical hum",
                        }
                    ],
                    "dialogue": None,
                },
                {
                    "shot_id": "scene_001_shot_002",
                    "start_sec": 2.0,
                    "end_sec": 4.0,
                    "duration_sec": 2.0,
                    "shot_type": "insert_symbolic",
                    "camera": "macro insert on three graph nodes",
                    "visual_action": "Three unlabeled nodes brighten: role, institution, self-knowledge.",
                    "audio_plan": [
                        {
                            "start_sec": 2.0,
                            "end_sec": 4.0,
                            "kind": "foley",
                            "description": "three soft node pulses",
                        }
                    ],
                    "dialogue": None,
                },
            ],
        },
        {
            "scene_id": "scene_002_embry_speaks",
            "start_sec": 4.0,
            "end_sec": 9.0,
            "duration_sec": 5.0,
            "scene_type": "speaking_character",
            "title": "The Line of Self-Knowledge",
            "summary": "Embry faces the graph and speaks one source-grounded line.",
            "source_grounded_residue_ids": shot.get("source_grounded_residue_ids", residue_ids),
            "dream_symbolic_elements": [
                "Yale stone dissolving into terminal light",
                "SPARTA graph as dream environment",
            ],
            "shots": [
                {
                    "shot_id": shot["shot_id"],
                    "start_sec": 4.0,
                    "end_sec": 9.0,
                    "duration_sec": 5.0,
                    "shot_type": "speaking_character_closeup",
                    "speaker": shot.get("speaker", "Embry"),
                    "dialogue": shot["dialogue"],
                    "tts_text_plain": shot.get("tts_text_plain") or shot["dialogue"],
                    "tts_text_elevenlabs": shot.get("tts_text_elevenlabs") or shot["dialogue"],
                    "camera": "static medium close-up, front-facing, mouth visible",
                    "visual_action": "Embry speaks calmly while graph light moves behind her.",
                    "lip_sync_required": True,
                    "audio_first": True,
                    "audio_plan": [
                        {
                            "start_sec": 4.0,
                            "end_sec": 9.0,
                            "kind": "dialogue",
                            "speaker": shot.get("speaker", "Embry"),
                            "text": shot["dialogue"],
                        }
                    ],
                    "video_prompt": shot["visual_prompt"],
                    "negative_prompt": shot.get("negative_prompt", ""),
                }
            ],
        },
        {
            "scene_id": "scene_003_residue_returns",
            "start_sec": 9.0,
            "end_sec": 13.0,
            "duration_sec": 4.0,
            "scene_type": "symbolic_reflection",
            "title": "The Residue Returns",
            "summary": "The dream does not write new lore; the residues return unchanged.",
            "source_grounded_residue_ids": residue_ids,
            "dream_symbolic_elements": [
                "graph nodes dimming without vanishing",
                "archive returning to ordinary stillness",
            ],
            "shots": [
                {
                    "shot_id": "scene_003_shot_001",
                    "start_sec": 9.0,
                    "end_sec": 11.0,
                    "duration_sec": 2.0,
                    "shot_type": "symbolic_reaction",
                    "camera": "over-shoulder view from behind Embry",
                    "visual_action": "The graph dims but leaves three points of light in the archive.",
                    "audio_plan": [
                        {
                            "start_sec": 9.0,
                            "end_sec": 11.0,
                            "kind": "ambience",
                            "description": "electrical hum softens into room tone",
                        }
                    ],
                    "dialogue": None,
                },
                {
                    "shot_id": "scene_003_shot_002",
                    "start_sec": 11.0,
                    "end_sec": 13.0,
                    "duration_sec": 2.0,
                    "shot_type": "closing_symbolic",
                    "camera": "locked-off wide shot",
                    "visual_action": "The archive is still; no new memory is written.",
                    "audio_plan": [
                        {
                            "start_sec": 11.0,
                            "end_sec": 13.0,
                            "kind": "silence",
                            "description": "near silence, no musical resolution",
                        }
                    ],
                    "dialogue": None,
                },
            ],
        },
    ]

    contact_sheets = [
        {
            "contact_sheet_id": "embry_primary_perspectives",
            "title": "Embry Dream: Character Perspective Contact Sheet",
            "purpose": "Review character perspective, continuity, and dream-symbolic visual language before video generation.",
            "character_id": "embry",
            "source_grounded_residue_ids": residue_ids,
            "panels": [
                {
                    "panel_id": "panel_001_embry_internal",
                    "perspective": "Embry internal perspective",
                    "time_range_sec": [0.0, 4.0],
                    "caption": "The archive feels like memory inspecting itself.",
                    "prompt": (
                        "POV-inspired cinematic frame: an old university archive seen through Embry's "
                        "subjective perception, shelves subtly transforming into glowing evidence graph "
                        "nodes, calm and uncanny, no readable text, no logos, realistic lighting."
                    ),
                    "source_grounded_residue_ids": [
                        rid for rid in residue_ids if rid in {
                            "residue_embry_institution_yale",
                            "residue_embry_role_sparta_intern",
                        }
                    ],
                    "dream_symbolic_elements": ["archive as memory graph"],
                },
                {
                    "panel_id": "panel_002_observer_closeup",
                    "perspective": "External observer perspective",
                    "time_range_sec": [4.0, 9.0],
                    "caption": "Embry speaks calmly with her mouth clearly visible.",
                    "prompt": (
                        "Medium close-up of a fictional young adult woman representing Embry, front-facing, "
                        "mouth clearly visible, calm controlled expression, archive hallway behind her "
                        "dissolving into a glowing cybersecurity graph, cinematic realistic, no text, no logos."
                    ),
                    "source_grounded_residue_ids": shot.get("source_grounded_residue_ids", residue_ids),
                    "dream_symbolic_elements": ["SPARTA graph as dream backdrop"],
                },
                {
                    "panel_id": "panel_003_graph_perspective",
                    "perspective": "SPARTA graph perspective",
                    "time_range_sec": [9.0, 13.0],
                    "caption": "The graph remembers role, institution, and self-knowledge without writing new lore.",
                    "prompt": (
                        "Abstract cinematic cybersecurity graph inside a dim archive, three subtle nodes glowing "
                        "like remembered evidence, no labels, no readable text, no logos, restrained dreamlike mood."
                    ),
                    "source_grounded_residue_ids": residue_ids,
                    "dream_symbolic_elements": ["three unlabeled evidence nodes"],
                },
                {
                    "panel_id": "panel_004_continuity_reference",
                    "perspective": "Character continuity reference",
                    "time_range_sec": [4.0, 9.0],
                    "caption": "Continuity target for face, costume, lighting, and lip-sync framing.",
                    "prompt": (
                        "Character reference sheet frame for Embry: fictional young adult woman, calm serious "
                        "expression, simple modern academic clothing, soft archive lighting, front-facing, "
                        "neutral background variation, mouth unobstructed, no text, no logos."
                    ),
                    "source_grounded_residue_ids": shot.get("source_grounded_residue_ids", residue_ids),
                    "dream_symbolic_elements": [],
                },
            ],
        }
    ]

    packet = {
        "schema_version": "persona_dream_packet.v0.3",
        "packet_id": f"{persona_id}_dream_packet_001",
        "persona_id": persona_id,
        "title": "The Archive That Remembered Itself",
        "logline": (
            "Embry dreams of an archive where evidence behaves like memory and speaks one line "
            "that preserves her source-grounded self-knowledge."
        ),
        "policy": contract.get("policy", {}),
        "source_grounded_residue_ids": residue_ids,
        "source_grounded_residue_summary": {
            rid: residue_map.get(rid, {}).get("retrieval_text") for rid in residue_ids
        },
        "short_story": {
            "format": "markdown",
            "text": story_text,
            "source_grounding_note": (
                "The story is synthetic dream narration. Persona assertions are limited to cited residue IDs. "
                "Dream-symbolic visuals are not canonical lore."
            ),
        },
        "runtime": {
            "total_duration_sec": 13.0,
            "speaking_duration_sec": 5.0,
            "video_generation_strategy": {
                "dialogue_scenes": "audio_first_then_lipsync",
                "symbolic_scenes": "video_first_then_audio_events",
            },
        },
        "scenes": scenes,
        "contact_sheets": contact_sheets,
        "reflection_policy": {
            "reflection_allowed": True,
            "synthetic_reflection_allowed": False,
            "memory_write_allowed": False,
            "memory_write_requires_explicit_receipt": True,
        },
    }
    return packet


def scenes_script(packet: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for scene in packet.get("scenes", []):
        for shot in scene.get("shots", []):
            rows.append(
                {
                    "scene_id": scene["scene_id"],
                    "scene_title": scene["title"],
                    "shot_id": shot["shot_id"],
                    "start_sec": shot["start_sec"],
                    "end_sec": shot["end_sec"],
                    "duration_sec": shot["duration_sec"],
                    "shot_type": shot["shot_type"],
                    "speaker": shot.get("speaker"),
                    "dialogue": shot.get("dialogue"),
                    "camera": shot.get("camera"),
                    "visual_action": shot.get("visual_action"),
                    "audio_plan": shot.get("audio_plan", []),
                    "source_grounded_residue_ids": scene.get("source_grounded_residue_ids", []),
                    "dream_symbolic_elements": scene.get("dream_symbolic_elements", []),
                }
            )

    return {
        "schema_version": "persona_dream_scenes_script.v0.3",
        "packet_id": packet["packet_id"],
        "persona_id": packet["persona_id"],
        "title": packet["title"],
        "total_duration_sec": packet["runtime"]["total_duration_sec"],
        "shots": rows,
    }


def contact_sheets_only(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "persona_dream_contact_sheets.v0.3",
        "packet_id": packet["packet_id"],
        "persona_id": packet["persona_id"],
        "contact_sheets": packet.get("contact_sheets", []),
    }


def _yaml_dump(data: dict[str, Any]) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def contact_sheets_html(contact_sheets: dict[str, Any]) -> str:
    sections: list[str] = []
    for sheet in contact_sheets.get("contact_sheets", []):
        panels = []
        for panel in sheet.get("panels", []):
            panels.append(
                f"""
                <article class="panel">
                  <h3>{html.escape(panel.get("panel_id", ""))}</h3>
                  <p class="perspective">{html.escape(panel.get("perspective", ""))}</p>
                  <p>{html.escape(panel.get("caption", ""))}</p>
                  <pre>{html.escape(panel.get("prompt", ""))}</pre>
                </article>
                """
            )
        sections.append(
            f"""
            <section class="sheet">
              <h2>{html.escape(sheet.get("title", ""))}</h2>
              <p>{html.escape(sheet.get("purpose", ""))}</p>
              <div class="grid">{''.join(panels)}</div>
            </section>
            """
        )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Persona-Dream Contact Sheets</title>
<style>
body {{
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  margin: 0;
  background: #f5f7fb;
  color: #111827;
}}
main {{ max-width: 1160px; margin: 32px auto; padding: 0 20px; }}
.sheet {{
  background: white;
  border: 1px solid #d9dee8;
  border-radius: 18px;
  padding: 20px;
}}
.grid {{
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}}
.panel {{
  border: 1px solid #d9dee8;
  border-radius: 14px;
  padding: 14px;
  background: #fbfcff;
}}
.perspective {{ color: #586174; font-weight: 650; }}
pre {{
  white-space: pre-wrap;
  background: #eef2f7;
  border-radius: 10px;
  padding: 12px;
}}
</style>
</head>
<body>
<main>
<h1>Persona-Dream Contact Sheets</h1>
{''.join(sections)}
</main>
</body>
</html>
"""


def write_story_assets(packet: dict[str, Any], out_dir: str | Path) -> dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    script = scenes_script(packet)
    sheets = contact_sheets_only(packet)

    paths = {
        "dream_packet_json": str(out / "dream_packet.json"),
        "dream_packet_yaml": str(out / "dream_packet.yaml"),
        "short_story_md": str(out / "short_story.md"),
        "scenes_script_json": str(out / "scenes_script.json"),
        "scenes_script_yaml": str(out / "scenes_script.yaml"),
        "contact_sheets_json": str(out / "contact_sheets.json"),
        "contact_sheets_yaml": str(out / "contact_sheets.yaml"),
        "contact_sheets_html": str(out / "contact_sheets.html"),
    }

    write_json(paths["dream_packet_json"], packet)
    write_text(paths["dream_packet_yaml"], _yaml_dump(packet))
    write_text(paths["short_story_md"], "# " + packet["title"] + "\n\n" + packet["short_story"]["text"] + "\n")
    write_json(paths["scenes_script_json"], script)
    write_text(paths["scenes_script_yaml"], _yaml_dump(script))
    write_json(paths["contact_sheets_json"], sheets)
    write_text(paths["contact_sheets_yaml"], _yaml_dump(sheets))
    write_text(paths["contact_sheets_html"], contact_sheets_html(sheets))

    return paths
