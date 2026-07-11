from __future__ import annotations

from pathlib import Path
from typing import Any

from .io_utils import write_json, write_text


def _speaking_shots(packet: dict[str, Any]) -> list[dict[str, Any]]:
    shots: list[dict[str, Any]] = []
    for scene in packet.get("scenes", []):
        for shot in scene.get("shots", []):
            if shot.get("dialogue"):
                copy = dict(shot)
                copy["_scene_id"] = scene.get("scene_id")
                copy["_scene_title"] = scene.get("title")
                copy["_scene_summary"] = scene.get("summary")
                copy["_scene_residue_ids"] = scene.get("source_grounded_residue_ids", [])
                copy["_dream_symbolic_elements"] = scene.get("dream_symbolic_elements", [])
                shots.append(copy)
    return shots


def build_nava_prompt(
    *,
    packet: dict[str, Any],
    shot: dict[str, Any],
    speaker_wav: str | None,
    first_frame_image: str | None,
) -> dict[str, Any]:
    dialogue = shot["dialogue"]
    source_residues = packet.get("source_grounded_residue_summary", {})
    residue_ids = shot.get("_scene_residue_ids") or packet.get("source_grounded_residue_ids", [])

    # Keep factual content short and provenance-aware; let NAVA render, not invent.
    residue_lines = []
    for rid in residue_ids:
        text = source_residues.get(rid)
        if text:
            residue_lines.append(f"{rid}: {text}")

    residue_block = " ".join(residue_lines)

    prompt = (
        "A restrained cinematic dream scene grounded only in the following persona residues: "
        f"{residue_block}. "
        "A fictional young adult woman representing Embry stands in a dim academic archive that "
        "subtly transforms into a glowing cybersecurity evidence graph. Front-facing medium close-up, "
        "mouth clearly visible, no occlusion, calm controlled expression, no cuts during speech, "
        "no readable text, no logos. Background ambience is quiet archive room tone with a soft "
        "electrical graph hum. She speaks exactly: "
        f"<S>{dialogue}<E> "
        "The scene may use symbolic visual metaphors, but it must not add new lore, names, events, "
        "claims, labels, or on-screen text."
    )

    record: dict[str, Any] = {
        "prompt": prompt,
        "metadata": {
            "packet_id": packet.get("packet_id"),
            "persona_id": packet.get("persona_id"),
            "scene_id": shot.get("_scene_id"),
            "shot_id": shot.get("shot_id"),
            "source_grounded_residue_ids": residue_ids,
            "dialogue": dialogue,
            "dream_symbolic_elements": shot.get("_dream_symbolic_elements", []),
            "expected_duration_sec": shot.get("duration_sec"),
            "lane": "nava_joint_av",
        },
    }

    if first_frame_image:
        record["image_path"] = str(Path(first_frame_image).expanduser().resolve())
    if speaker_wav:
        record["spk_wavs"] = [str(Path(speaker_wav).expanduser().resolve())]

    return record


def write_nava_inputs(
    *,
    packet: dict[str, Any],
    out_dir: str | Path,
    speaker_wav: str | None = None,
    first_frame_image: str | None = None,
) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    shots = _speaking_shots(packet)
    if not shots:
        raise ValueError("No dialogue shots found in dream packet.")

    records = [
        build_nava_prompt(
            packet=packet,
            shot=shot,
            speaker_wav=speaker_wav,
            first_frame_image=first_frame_image,
        )
        for shot in shots
    ]

    jsonl_path = out / "nava_prompts.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for record in records:
            # Do not include metadata in the NAVA line unless the runner tolerates unknown keys.
            nava_record = {k: v for k, v in record.items() if k in {"prompt", "image_path", "spk_wavs"}}
            import json

            f.write(json.dumps(nava_record, ensure_ascii=False) + "\n")

    manifest = {
        "schema_version": "persona_dream_nava_prompt_manifest.v0.1",
        "jsonl_path": str(jsonl_path),
        "records": records,
        "notes": [
            "The NAVA JSONL is derived from the source-grounded dream packet.",
            "NAVA may use prompt rewriting, but rewriting must preserve <S>...</E> dialogue spans.",
            "NAVA should render the scene, not decide lore/story.",
        ],
    }
    write_json(out / "nava_prompt_manifest.json", manifest)

    preview_lines = ["# NAVA Prompt Preview", ""]
    for i, record in enumerate(records, start=1):
        preview_lines.append(f"## Record {i}")
        preview_lines.append("")
        preview_lines.append("```json")
        import json

        preview_lines.append(json.dumps(record, indent=2, ensure_ascii=False))
        preview_lines.append("```")
        preview_lines.append("")
    write_text(out / "nava_prompt_preview.md", "\n".join(preview_lines))

    return manifest
