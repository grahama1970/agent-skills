# Best Practices: Kling Contact Sheet Skill

> **Disciplines:** engineering-standards · content-creation

This bundle is a reusable skill for designing, auditing, and packaging AI-video-ready reference images for Kling-style workflows.

It is optimized for:

- Characters and recurring actors
- Props, items, products, and accessories
- Costumes and worn objects
- Scenery, sets, and environments
- Animals, creatures, and effects

## What this skill does

It turns a loose idea like “make a character contact sheet Kling can understand” into a structured reference pack:

```text
AssetName_v01/
  references/
    01_main_front_or_hero.png
    02_three_quarter_or_alt_angle.png
    03_side_back_top_or_scale.png
    04_detail_closeup.png
  description.txt
  do_not_change.txt
  ignore.txt
  prompt_template.txt
  manifest.json
```

## Most important principle

Use a contact sheet for human review, but upload the important panels as separate reference images whenever possible. A dense grid can be interpreted as one scene with multiple copies or layout artifacts.

## Current Kling-specific assumptions

Verified against official Kling documentation on 2026-06-11:

- One multi-image Element uses 2–4 reference images.
- The main image should usually be front-facing for consistency.
- Supplementary images should show different angles or additional details.
- Element descriptions should include core characteristics, key details, and ignored features.
- VIDEO 3.0 Omni image inputs support `.jpg`, `.jpeg`, and `.png`, with at least 300 px width/height and file size up to 10 MB.
- VIDEO 3.0 Omni can use up to 7 images/elements without video input, or up to 4 images/elements when a video is also provided.

See `source_notes/kling_official_reference_notes.md` for source URLs.

## How to use

1. Read `SKILL.md` for the operating instructions.
2. Pick a template from `templates/`.
3. Fill in the asset description and reference image plan.
4. Use `checklists/pre_upload_quality_gate.md` before uploading to Kling.
5. Optional: use `scripts/create_asset_pack.py` to scaffold folders and blank files.
6. Optional: use `scripts/validate_asset_pack.py` to check image counts, file types, file sizes, and dimensions.

## Example commands

Create a blank character pack:

```bash
python scripts/create_asset_pack.py --root ./packs --type character --name Maya_Ren --version 1
```

Validate a pack after adding reference images:

```bash
python scripts/validate_asset_pack.py ./packs/CHAR_Maya_Ren_v01
```

## Recommended workflow

```text
1. Design one asset.
2. Produce 2–4 clean reference images.
3. Write identity locks and ignore notes.
4. Upload as one Element.
5. Prompt with explicit subject movement and background movement.
6. Iterate by fixing the reference pack, not by adding random prompt adjectives.
```
