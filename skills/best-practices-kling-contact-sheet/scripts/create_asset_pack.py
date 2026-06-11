#!/usr/bin/env python3
"""Create a Kling-style asset pack scaffold."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import typer

app = typer.Typer(add_completion=False, help="Create a Kling-style asset pack scaffold.")

ASSET_PREFIX = {
    "character": "CHAR",
    "animal": "ANIMAL",
    "prop-item": "PROP",
    "costume-accessory": "COSTUME",
    "scene": "SCENE",
    "effect": "EFFECT",
    "other": "ASSET",
}

DEFAULT_REFERENCE_NAMES = {
    "character": [
        "01_main_front_full_body.png",
        "02_three_quarter_full_body.png",
        "03_side_or_back_view.png",
        "04_face_or_detail_closeup.png",
    ],
    "animal": [
        "01_main_front_or_hero.png",
        "02_three_quarter_or_alt_angle.png",
        "03_side_or_back_view.png",
        "04_face_or_detail_closeup.png",
    ],
    "prop-item": [
        "01_main_hero_angle.png",
        "02_side_top_or_back.png",
        "03_scale_or_in_hand.png",
        "04_material_or_marking_detail.png",
    ],
    "costume-accessory": [
        "01_front_worn_view.png",
        "02_back_or_side_worn_view.png",
        "03_isolated_flat_lay_or_detail.png",
        "04_trim_closure_material_closeup.png",
    ],
    "scene": [
        "01_wide_establishing_view.png",
        "02_alternate_camera_angle.png",
        "03_key_landmark_detail.png",
        "04_lighting_mood_reference.png",
    ],
    "effect": [
        "01_main_effect_shape.png",
        "02_particle_or_texture_closeup.png",
        "03_scale_or_interaction.png",
        "04_motion_phase_or_lighting.png",
    ],
    "other": [
        "01_main_reference.png",
        "02_supplementary_angle.png",
        "03_supplementary_detail.png",
        "04_closeup_or_scale.png",
    ],
}

def slugify(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")
    if not slug:
        raise ValueError("Asset name must contain at least one letter or number.")
    return slug

@app.command()
def main(
    root: Path = typer.Option(Path("."), "--root", help="Destination root folder."),
    asset_type: str = typer.Option(..., "--type", help="Asset type."),
    name: str = typer.Option(..., "--name", help="Asset name, e.g. Maya Ren."),
    version_number: int = typer.Option(1, "--version", min=1, help="Version number, e.g. 1 -> v01."),
    make_placeholders: bool = typer.Option(
        False,
        "--make-placeholders",
        help="Create empty placeholder image files. Off by default.",
    ),
) -> None:
    if asset_type not in ASSET_PREFIX:
        allowed = ", ".join(sorted(ASSET_PREFIX))
        raise typer.BadParameter(f"unsupported asset type '{asset_type}'. Expected one of: {allowed}")
    slug = slugify(name)
    version = f"v{version_number:02d}"
    folder_name = f"{ASSET_PREFIX[asset_type]}_{slug}_{version}"
    pack = root.expanduser().resolve() / folder_name
    refs = pack / "references"
    refs.mkdir(parents=True, exist_ok=True)

    reference_files = DEFAULT_REFERENCE_NAMES[asset_type]
    for filename in reference_files:
        target = refs / filename
        if make_placeholders:
            target.touch(exist_ok=True)

    (pack / "description.txt").write_text(
        "Asset name: {name}\n"
        "Asset type: {atype}\n"
        "Version: {version}\n\n"
        "Core identity:\n\n"
        "Visual details:\n\n"
        "Scale:\n\n"
        "Style:\n\n"
        "Lighting / mood:\n\n"
        "Do not change:\n- \n\n"
        "Allowed variation:\n- \n\n"
        "Ignore:\n- \n".format(name=slug, atype=asset_type, version=version),
        encoding="utf-8",
    )
    (pack / "do_not_change.txt").write_text("- \n", encoding="utf-8")
    (pack / "ignore.txt").write_text("- Plain reference background\n- Temporary pose\n- Labels outside subject\n", encoding="utf-8")
    (pack / "prompt_template.txt").write_text(
        "[@{name}_{version}] performs [specific visible action].\n"
        "Camera: [shot size], [angle], [movement].\n"
        "Background: [environment movement].\n"
        "Keep consistent: [identity locks].\n"
        "Avoid: [failure modes].\n".format(name=slug, version=version),
        encoding="utf-8",
    )

    manifest = {
        "asset_name": slug,
        "asset_type": asset_type,
        "version": version,
        "last_updated": date.today().isoformat(),
        "references": [
            {
                "file": f"references/{filename}",
                "role": "main" if idx == 0 else ("detail" if idx == 3 else "supplementary"),
                "purpose": "Fill in the purpose for this reference.",
                "must_show": [],
            }
            for idx, filename in enumerate(reference_files)
        ],
        "description": {
            "core_identity": "",
            "visual_details": "",
            "scale": "",
            "style": "",
            "lighting_mood": "",
            "do_not_change": [],
            "allowed_variation": [],
            "ignore": ["plain reference background", "temporary pose", "labels outside subject"],
        },
        "kling_constraints": {
            "element_reference_count": "2-4",
            "allowed_extensions": [".jpg", ".jpeg", ".png"],
            "minimum_dimensions_px": 300,
            "maximum_file_size_mb": 10,
        },
    }
    (pack / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    typer.echo(f"Created: {pack}")
    typer.echo("Next: add 2-4 real reference images to the references/ folder and complete description.txt.")

if __name__ == "__main__":
    app()
