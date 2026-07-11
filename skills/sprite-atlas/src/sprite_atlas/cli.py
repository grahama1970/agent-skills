"""Sprite atlas CLI: inspect, plan, repair, validate, and promote."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Optional

import typer
from PIL import Image

from sprite_atlas.assemble_atlas import assemble_atlas
from sprite_atlas.contracts import load_mapping, load_profile
from sprite_atlas.detect_layout import detect_layout
from sprite_atlas.generate_manifest import write_manifest
from sprite_atlas.frame_repair import (
    apply_frame_patches,
    build_repair_plan,
    extract_named_frames,
    pack_named_frames,
    validate_named_frames,
)
from sprite_atlas.inspect_source import inspect_source
from sprite_atlas.map_frames import detected_counts, mapping_gaps, propose_mapping
from sprite_atlas.normalize_frames import normalize_frames
from sprite_atlas.promote import promote_candidate
from sprite_atlas.receipts import build_receipt, build_regeneration_work_order, sha256_file, write_json
from sprite_atlas.remove_background import crop_metadata_panel, remove_presentation_background
from sprite_atlas.validate_atlas import summarize_checks, validate_atlas_png, validate_manifest

app = typer.Typer(no_args_is_help=True)


def _default_job_dir(job_dir: Path | None, sprite_id: str | None) -> Path:
    if job_dir is not None:
        return job_dir
    root = Path(__file__).resolve().parents[2] / "jobs"
    return root / (sprite_id or "anonymous")


def _missing_cells_report(sprite_id: str, gaps: list[dict[str, object]]) -> list[dict[str, object]]:
    cells: list[dict[str, object]] = []
    for gap in gaps:
        animation = str(gap["animation"])
        row = int(gap["row"])
        for column in gap.get("missing_columns", []):
            cells.append(
                {
                    "animation": animation,
                    "row": row,
                    "column": int(column),
                    "frame_name": f"{sprite_id}_{animation}_{int(column)}",
                }
            )
    return cells


@app.command()
def validate_frames(
    frames_dir: Annotated[Path, typer.Option(help="Named-frame authoring directory.")],
    profile: Annotated[Path, typer.Option(help="Profile JSON path.")],
    job_dir: Annotated[Optional[Path], typer.Option(help="Optional validation output directory.")] = None,
) -> None:
    """Validate a complete <animation>/<frame>.png authoring tree."""
    validation = validate_named_frames(frames_dir=frames_dir, profile=load_profile(profile))
    if job_dir:
        write_json(job_dir / "frame-validation-index.json", validation)
    typer.echo(json.dumps(validation, indent=2))
    if not validation["passed"]:
        raise typer.Exit(code=1)


@app.command()
def pack_frames(
    frames_dir: Annotated[Path, typer.Option(help="Validated named-frame authoring directory.")],
    profile: Annotated[Path, typer.Option(help="Profile JSON path.")],
    sprite_id: Annotated[str, typer.Option(help="Stable sprite id.")],
    job_dir: Annotated[Path, typer.Option(help="Candidate output directory.")],
) -> None:
    """Pack named frame sources into the fixed-grid compatibility atlas."""
    prof = load_profile(profile)
    job_dir.mkdir(parents=True, exist_ok=True)
    atlas = pack_named_frames(frames_dir=frames_dir, profile=prof)
    atlas.save(job_dir / "atlas.candidate.png")
    write_manifest(job_dir / "atlas.candidate.json", sprite_id=sprite_id, image_name=f"{sprite_id}.png", profile=prof)
    typer.echo(json.dumps({"status": "PASS_NAMED_FRAME_PACK", "job_dir": str(job_dir)}, indent=2))


@app.command()
def plan_repair(
    atlas: Annotated[Path, typer.Option(help="Existing runtime atlas PNG.")],
    profile: Annotated[Path, typer.Option(help="Profile JSON path.")],
    sprite_id: Annotated[str, typer.Option(help="Stable sprite id.")],
    job_dir: Annotated[Path, typer.Option(help="Job output directory.")],
) -> None:
    """Emit exact missing/sparse frame IDs without modifying the atlas."""
    prof = load_profile(profile)
    job_dir.mkdir(parents=True, exist_ok=True)
    plan = build_repair_plan(
        image=Image.open(atlas), atlas_path=atlas, profile=prof, profile_path=profile, sprite_id=sprite_id
    )
    write_json(job_dir / "frame-repair-plan.json", plan)
    work_order = {
        "schema": "sprite_atlas.frame_generation_work_order.v1",
        "sprite_id": sprite_id,
        "profile_id": prof.profile_id,
        "source_atlas_sha256": plan["source_atlas_sha256"],
        "required_outputs": [frame["path"] for frame in plan["repair_frames"]],
        "output_contract": {
            "width": prof.atlas.frame_width,
            "height": prof.atlas.frame_height,
            "mode": "RGBA",
            "background": "transparent",
            "duplicates_forbidden": True,
        },
        "status": "GENERATION_REQUIRED" if plan["repair_required"] else "NOT_REQUIRED",
    }
    write_json(job_dir / "frame-generation-work-order.json", work_order)
    typer.echo(json.dumps(plan, indent=2))


@app.command()
def extract_frames(
    atlas: Annotated[Path, typer.Option(help="Existing fixed-grid runtime atlas PNG.")],
    profile: Annotated[Path, typer.Option(help="Profile JSON path.")],
    output_dir: Annotated[Path, typer.Option(help="Named-frame output directory.")],
) -> None:
    """Extract required cells into <animation>/<frame>.png authoring paths."""
    index = extract_named_frames(image=Image.open(atlas), profile=load_profile(profile), output_dir=output_dir)
    typer.echo(json.dumps({"output_dir": str(output_dir), "frame_count": index["frame_count"]}, indent=2))


@app.command()
def apply_frame_patch(
    atlas: Annotated[Path, typer.Option(help="Existing runtime atlas PNG.")],
    profile: Annotated[Path, typer.Option(help="Profile JSON path.")],
    sprite_id: Annotated[str, typer.Option(help="Stable sprite id.")],
    repair_plan: Annotated[Path, typer.Option(help="frame-repair-plan.json path.")],
    patch_dir: Annotated[Path, typer.Option(help="Directory containing named replacement frames.")],
    job_dir: Annotated[Path, typer.Option(help="Candidate output directory.")],
) -> None:
    """Apply exact named-frame patches and revalidate the complete atlas."""
    job_dir.mkdir(parents=True, exist_ok=True)
    plan = json.loads(repair_plan.read_text(encoding="utf-8"))
    write_json(job_dir / "frame-repair-plan.json", plan)
    receipt = apply_frame_patches(
        source_atlas=atlas,
        profile=load_profile(profile),
        profile_path=profile,
        sprite_id=sprite_id,
        repair_plan=plan,
        patch_dir=patch_dir,
        job_dir=job_dir,
    )
    typer.echo(json.dumps(receipt, indent=2))
    if receipt["status"] != "PASS_FRAME_PATCH":
        raise typer.Exit(code=4)


@app.command()
def inspect(
    source: Annotated[Path, typer.Option(help="Source PNG path.")],
    profile: Annotated[Path, typer.Option(help="Profile JSON path.")],
    job_dir: Annotated[Optional[Path], typer.Option(help="Job output directory.")] = None,
    sprite_id: Annotated[Optional[str], typer.Option(help="Sprite id for default job dir.")] = None,
) -> None:
    """Inspect a source sheet and emit analysis artifacts."""
    prof = load_profile(profile)
    out = _default_job_dir(job_dir, sprite_id)
    analysis = inspect_source(source=source, profile=prof, job_dir=out)
    typer.echo(json.dumps({"job_dir": str(out), "frame_gaps": analysis.get("frame_gaps", [])}, indent=2))


@app.command()
def repair(
    source: Annotated[Path, typer.Option(help="Source PNG path.")],
    profile: Annotated[Path, typer.Option(help="Profile JSON path.")],
    sprite_id: Annotated[str, typer.Option(help="Stable sprite id.")],
    job_dir: Annotated[Optional[Path], typer.Option(help="Job output directory.")] = None,
    mapping: Annotated[Optional[Path], typer.Option(help="Approved mapping JSON.")] = None,
) -> None:
    """Repair a source sheet into staged candidate atlas files.

    Places every detected frame into the profile grid. Missing cells stay transparent.
    Emits missing-frames.json listing required cells with no source art.
    """
    prof = load_profile(profile)
    out = _default_job_dir(job_dir, sprite_id)
    out.mkdir(parents=True, exist_ok=True)
    inspect_source(source=source, profile=prof, job_dir=out)
    source_sha = sha256_file(source)

    cleaned = remove_presentation_background(crop_metadata_panel(Image.open(source)))
    detected_rows = detect_layout(cleaned, prof)
    detection_gaps = detected_counts(prof, detected_rows)

    mapping_doc = (
        load_mapping(mapping, source_sha256=source_sha)
        if mapping
        else propose_mapping(prof, detected_rows, source_sha256=source_sha)
    )
    map_gaps = mapping_gaps(prof, mapping_doc)
    missing_cells = _missing_cells_report(sprite_id, map_gaps)
    write_json(
        out / "missing-frames.json",
        {
            "schema": "sprite_atlas.missing_frames.v1",
            "sprite_id": sprite_id,
            "complete": len(missing_cells) == 0,
            "missing_cell_count": len(missing_cells),
            "row_gaps": map_gaps,
            "missing_cells": missing_cells,
        },
    )

    normalized, overflow = normalize_frames(cleaned, prof, mapping_doc)
    if overflow:
        receipt = build_receipt(
            status="BLOCKED_FRAME_OVERFLOW",
            sprite_id=sprite_id,
            profile_id=prof.profile_id,
            source_path=source,
            profile_path=profile,
            checks=[{"name": "normalization", "passed": False, "detail": json.dumps(overflow)}],
        )
        write_json(out / "repair-receipt.json", receipt)
        typer.echo(json.dumps({"status": receipt["status"], "job_dir": str(out), "overflow": overflow}, indent=2))
        raise typer.Exit(code=4)

    atlas = assemble_atlas(prof, normalized)
    candidate_png = out / "atlas.candidate.png"
    candidate_json = out / "atlas.candidate.json"
    atlas.save(candidate_png)
    write_manifest(candidate_json, sprite_id=sprite_id, image_name=f"{sprite_id}.png", profile=prof)

    png_checks = validate_atlas_png(atlas, prof)
    manifest = json.loads(candidate_json.read_text(encoding="utf-8"))
    json_checks = validate_manifest(manifest, prof, sprite_id=sprite_id)
    validation = summarize_checks(png_checks + json_checks)
    write_json(out / "validation.json", validation)

    if missing_cells:
        status = "PARTIAL_REPAIRED"
        write_json(
            out / "regeneration-work-order.json",
            build_regeneration_work_order(
                sprite_id=sprite_id,
                profile_id=prof.profile_id,
                missing_frames=map_gaps,
                prompt_ref=f"skills/battle/assets/sprites/pixijs/{sprite_id}-runtime-prompt-canonical.json",
            ),
        )
        exit_code = 2
    elif validation["passed"]:
        status = "PASS_REPAIRED"
        exit_code = 0
    else:
        status = "FAIL_RUNTIME_VALIDATION"
        exit_code = 5

    receipt = build_receipt(
        status=status,
        sprite_id=sprite_id,
        profile_id=prof.profile_id,
        source_path=source,
        profile_path=profile,
        checks=validation["checks"],
        missing_frames=map_gaps if missing_cells else None,
        atlas_candidate=candidate_png,
        manifest_candidate=candidate_json,
    )
    write_json(out / "repair-receipt.json", receipt)
    typer.echo(
        json.dumps(
            {
                "status": status,
                "job_dir": str(out),
                "passed": validation["passed"],
                "placed_frames": len(normalized),
                "missing_cells": len(missing_cells),
                "missing": missing_cells,
                "detection_gaps": detection_gaps,
            },
            indent=2,
        )
    )
    if exit_code:
        raise typer.Exit(code=exit_code)


@app.command()
def validate(
    atlas: Annotated[Path, typer.Option(help="Runtime atlas PNG.")],
    manifest: Annotated[Path, typer.Option(help="Pixi manifest JSON.")],
    profile: Annotated[Path, typer.Option(help="Profile JSON path.")],
    sprite_id: Annotated[str, typer.Option(help="Sprite id for manifest validation.")],
    job_dir: Annotated[Optional[Path], typer.Option(help="Optional job dir for validation.json output.")] = None,
) -> None:
    """Validate an existing runtime atlas pair."""
    prof = load_profile(profile)
    image = Image.open(atlas)
    png_checks = validate_atlas_png(image, prof)
    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    json_checks = validate_manifest(manifest_data, prof, sprite_id=sprite_id)
    validation = summarize_checks(png_checks + json_checks)
    if job_dir:
        write_json(job_dir / "validation.json", validation)
    typer.echo(json.dumps(validation, indent=2))
    if not validation["passed"]:
        raise typer.Exit(code=1)


@app.command()
def promote(
    job_dir: Annotated[Path, typer.Option(help="Job directory with passing receipt.")],
    out_png: Annotated[Path, typer.Option(help="Production PNG path.")],
    out_json: Annotated[Path, typer.Option(help="Production JSON path.")],
) -> None:
    """Promote staged candidate files after PASS receipt."""
    promote_candidate(job_dir=job_dir, out_png=out_png, out_json=out_json)
    typer.echo(json.dumps({"promoted_png": str(out_png), "promoted_json": str(out_json)}, indent=2))


if __name__ == "__main__":
    app()
