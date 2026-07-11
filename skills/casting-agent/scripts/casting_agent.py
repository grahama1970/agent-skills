#!/usr/bin/env python3
"""Deterministic planning helper for the casting-agent skill."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Annotated

import typer


app = typer.Typer(help="Create story-grounded casting contracts and contact-sheet work orders.")


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise typer.BadParameter(f"file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"invalid JSON: {path}: {exc}") from exc


def _parse_references(items: list[str]) -> dict[str, list[str]]:
    refs: dict[str, list[str]] = {}
    for item in items:
        if "=" not in item:
            raise typer.BadParameter("--reference must be <entity_id>=<path-or-url>")
        entity_id, value = item.split("=", 1)
        entity_id = entity_id.strip()
        value = value.strip()
        if not entity_id or not value:
            raise typer.BadParameter("--reference must include non-empty entity_id and path/url")
        refs.setdefault(entity_id, []).append(value)
    return refs


def _flatten_keyed_entities(package: dict) -> list[dict]:
    out: list[dict] = []
    group_map = {
        "characters": "character",
        "creatures": "creature",
        "scenery": "environment",
        "environments": "environment",
        "props": "object",
        "objects": "object",
        "effects": "effect",
    }
    keyed = package.get("keyed_entities", package)
    for group_name, category in group_map.items():
        group = keyed.get(group_name, {}) or {}
        if isinstance(group, list):
            iterable = enumerate(group)
        elif isinstance(group, dict):
            iterable = group.items()
        else:
            continue
        for key, entity in iterable:
            if not isinstance(entity, dict):
                continue
            merged = dict(entity)
            merged.setdefault("entity_key", str(key))
            merged.setdefault("category", category)
            merged.setdefault("entity_id", f"{category}_{key}")
            out.append(merged)
    return out


def _entity_reference_paths(entity: dict) -> list[str]:
    refs: list[str] = []
    for field in ("image_file_paths", "reference_image_paths", "document_paths"):
        values = entity.get(field) or []
        if isinstance(values, str):
            values = [values]
        refs.extend(str(value) for value in values if str(value).strip())
    return refs


def _entity_groups(visual_entities: dict) -> list[dict]:
    if visual_entities.get("schema") == "persona_dream.story_visual_package.v1":
        return _flatten_keyed_entities(visual_entities)
    if "keyed_entities" in visual_entities:
        flattened = _flatten_keyed_entities(visual_entities)
        if flattened:
            return flattened
    entities = visual_entities.get("entities", visual_entities)
    out: list[dict] = []
    for group_name in ("characters", "creatures", "environments", "objects", "effects"):
        for entity in entities.get(group_name, []) or []:
            merged = dict(entity)
            merged.setdefault("category", group_name[:-1] if group_name.endswith("s") else group_name)
            out.append(merged)
    return out


def _package_context(package: dict) -> str:
    story = package.get("story") or {}
    if isinstance(story, str):
        return story
    parts = []
    for key in ("context", "tone", "visual_state", "notes"):
        value = story.get(key)
        if value:
            parts.append(str(value))
    return "\n".join(parts)


def _write_package_inputs(package_path: Path, package: dict, out_dir: Path) -> tuple[Path, Path, list[str]]:
    package_inputs = out_dir / "package_inputs"
    package_inputs.mkdir(parents=True, exist_ok=True)
    story = package.get("story") or {}
    if isinstance(story, str):
        story_text = story
    else:
        story_text = story.get("text") or ""
        story_path = story.get("path") or story.get("story_path")
        if story_path and Path(story_path).exists():
            story_text = Path(story_path).read_text()
    if not story_text.strip():
        raise typer.BadParameter(f"story package has no story.text or existing story.path: {package_path}")

    entities = _entity_groups(package)
    if not entities:
        raise typer.BadParameter(f"story package has no keyed entities: {package_path}")

    story_out = package_inputs / "story_contract.md"
    story_out.write_text(story_text.rstrip() + "\n")
    visual_out = package_inputs / "visual_entities.json"
    visual_out.write_text(json.dumps({
        "schema": "persona_dream.visual_entities.v1",
        "source_story_package": str(package_path),
        "story_id": package.get("story_id"),
        "keyed_entities": package.get("keyed_entities", {}),
        "entities": {
            "characters": [e for e in entities if e.get("category") == "character"],
            "creatures": [e for e in entities if e.get("category") == "creature"],
            "environments": [e for e in entities if e.get("category") == "environment"],
            "objects": [e for e in entities if e.get("category") == "object"],
            "effects": [e for e in entities if e.get("category") == "effect"],
        },
    }, indent=2) + "\n")

    references = []
    for entity in entities:
        entity_id = entity.get("entity_id")
        for ref in _entity_reference_paths(entity):
            references.append(f"{entity_id}={ref}")
    return story_out, visual_out, references


def _load_receipt_urls(path: Path) -> list[str]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return []
    urls = []
    for result in data.get("results", []) or []:
        for key in ("page_url", "url", "image_url", "thumbnail_url"):
            value = result.get(key)
            if value:
                urls.append(str(value))
    return urls


def _receipt_path_for_entity(receipt_dir: Path, entity_id: str) -> Path | None:
    candidates = [path for path in sorted(receipt_dir.glob(f"{entity_id}*.json")) if path.stat().st_size > 0]
    return candidates[0] if candidates else None


def _default_panels(entity_type: str) -> list[str]:
    if entity_type in {"character"}:
        return [
            "01_main_front_full_body.png",
            "02_three_quarter_full_body.png",
            "03_side_or_back_view.png",
            "04_face_or_detail_closeup.png",
        ]
    if entity_type in {"creature", "animal"}:
        return [
            "01_main_full_silhouette.png",
            "02_motion_or_side_pose.png",
            "03_detail_closeup.png",
            "04_group_or_scale_reference.png",
        ]
    if entity_type in {"environment", "scene"}:
        return [
            "01_wide_establishing_view.png",
            "02_alternate_camera_angle.png",
            "03_key_landmark_detail.png",
            "04_lighting_mood_reference.png",
        ]
    return [
        "01_main_hero_angle.png",
        "02_side_top_or_back.png",
        "03_scale_or_context.png",
        "04_material_or_detail.png",
    ]


def _search_queries(entity: dict, context: str) -> list[str]:
    name = entity.get("display_name") or entity.get("canonical_name") or entity.get("entity_id")
    anchors = entity.get("visual_anchors") or entity.get("required_visual_anchors") or []
    terms = [str(name)] + [str(a) for a in anchors[:4]]
    if context:
        terms.append(context)
    base = " ".join(t for t in terms if t)
    queries = [base]
    lowered = base.lower()
    if "horus" in lowered and "pre-heresy" not in lowered:
        queries.insert(0, "pre-Heresy Horus Lupercal smiling charismatic white gold armor")
    return queries[:3]


def _run_case(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), *args],
        capture_output=True,
        text=True,
    )


def _write_fixture_png(path: Path) -> None:
    # 1x1 transparent PNG. This is only a reference-path fixture; no image
    # generation or provider call is implied.
    path.write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
            "1f15c4890000000d49444154789c6360000002000100ffff030000060005"
            "57bfab0000000049454e44ae426082"
        )
    )


def _write_labeled_fixture_png(path: Path, title: str, color: str) -> None:
    from PIL import Image, ImageDraw, ImageFont

    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (960, 576), color)
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 44)
    draw.rectangle((24, 24, 936, 552), outline="#f7f2e8", width=6)
    draw.text((58, 58), title, fill="#f7f2e8", font=font)
    draw.text((58, 132), "deterministic casting-agent E2E fixture", fill="#f7f2e8", font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24))
    image.save(path)


def _build_contact_sheet_fixture(root: Path) -> dict:
    asset_root = root / "contact_sheet_fixture"
    for dirname in ("images", "prompts", "receipts"):
        (asset_root / dirname).mkdir(parents=True, exist_ok=True)

    fixture_assets = {
        "horus_character_reference_sheet": ("Horus Lupercal Reference Sheet", "#5b3b22"),
        "embry_character_reference_sheet": ("Embry Reference Sheet", "#355c60"),
        "creature_tyranid_background_reference_sheet": ("Tyranid Background Creature Sheet", "#49305d"),
        "location_void_tea_terrace_reference_sheet": ("Void Tea Terrace Location Sheet", "#263b5e"),
        "prop_patio_table_umbrella_tea_reference_sheet": ("Patio Table Umbrella Tea Prop Kit", "#61522d"),
    }
    for stem, (title, color) in fixture_assets.items():
        _write_labeled_fixture_png(asset_root / "images" / f"{stem}.png", title, color)
        (asset_root / "prompts" / f"{stem}.prompt.md").write_text(
            f"# {title}\n\nDeterministic E2E fixture prompt for casting-agent contact-sheet generation.\n"
        )
        (asset_root / "receipts" / f"{stem}.response.json").write_text(
            json.dumps({"schema": "casting_agent.fixture_receipt.v1", "status": "fixture"}, indent=2) + "\n"
        )

    repo_root = Path(__file__).resolve().parents[3]
    contact_sheet_runner = repo_root / "skills" / "persona-dream" / "run.sh"
    result = subprocess.run(
        [
            str(contact_sheet_runner),
            "contact-sheet",
            "build",
            "--asset-root",
            str(asset_root),
        ],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )
    expected = [
        asset_root / "contact_sheet_index.png",
        asset_root / "provider_matrix.png",
        asset_root / "index.html",
        asset_root / "reference_asset_manifest.json",
        asset_root / "visual_entity_context.json",
        asset_root / "provider_inputs.json",
    ]
    return {
        "asset_root": str(asset_root),
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "expected_artifacts": [str(path) for path in expected],
        "all_expected_artifacts_present": result.returncode == 0 and all(path.exists() for path in expected),
        "fixture_asset_count": len(fixture_assets),
    }


@app.command()
def plan(
    story: Annotated[Path, typer.Option("--story", help="Story contract or screenplay path.")],
    visual_entities: Annotated[Path, typer.Option("--visual-entities", help="visual_entities.json path.")],
    out_dir: Annotated[Path, typer.Option("--out-dir", help="Output directory for casting artifacts.")],
    context: Annotated[list[str], typer.Option("--context", help="Additional story/casting context.")] = None,
    reference: Annotated[list[str], typer.Option("--reference", help="<entity_id>=<path-or-url>. Repeatable.")] = None,
    max_search_rounds: Annotated[int, typer.Option("--max-search-rounds", min=0, max=10)] = 3,
    max_generation_rounds: Annotated[int, typer.Option("--max-generation-rounds", min=0, max=10)] = 2,
) -> None:
    """Write casting_contract.json and contact_sheet_work_order.json without live calls."""
    result = _plan_artifacts(
        story=story,
        visual_entities=visual_entities,
        out_dir=out_dir,
        context=context or [],
        reference=reference or [],
        max_search_rounds=max_search_rounds,
        max_generation_rounds=max_generation_rounds,
        source_package=None,
    )
    typer.echo(json.dumps(result, indent=2))


def _plan_artifacts(
    story: Path,
    visual_entities: Path,
    out_dir: Path,
    context: list[str],
    reference: list[str],
    max_search_rounds: int,
    max_generation_rounds: int,
    source_package: Path | None,
) -> dict:
    if not story.exists():
        raise typer.BadParameter(f"story not found: {story}")
    entities_doc = _load_json(visual_entities)
    entities = _entity_groups(entities_doc)
    if not entities:
        raise typer.BadParameter(f"no entities found in {visual_entities}")

    context_text = "\n".join(context or [])
    refs = _parse_references(reference or [])
    for entity in entities:
        entity_id = entity.get("entity_id")
        embedded_refs = _entity_reference_paths(entity)
        if embedded_refs:
            refs.setdefault(entity_id, []).extend(embedded_refs)
    out_dir.mkdir(parents=True, exist_ok=True)

    casting_entities = []
    chosen_refs = []
    work_elements = []

    for entity in entities:
        entity_id = entity.get("entity_id")
        entity_type = entity.get("category") or entity.get("entity_type") or "object"
        provided = refs.get(entity_id, [])
        strategy = "provided_reference" if provided else "brave_search_needed"
        must_include = entity.get("visual_anchors") or entity.get("required_visual_anchors") or []
        must_avoid = entity.get("must_not_include") or entity.get("forbidden_genericizations") or []
        queries = [] if provided else _search_queries(entity, context_text)
        panels = _default_panels(str(entity_type))

        casting_entities.append({
            "entity_id": entity_id,
            "entity_type": entity_type,
            "entity_key": entity.get("entity_key"),
            "display_name": entity.get("display_name") or entity.get("canonical_name") or entity_id,
            "description": entity.get("description", ""),
            "story_role": entity.get("story_role", ""),
            "visual_state": context_text,
            "reference_strategy": strategy,
            "provided_references": provided,
            "source_urls": entity.get("source_urls", []),
            "memory_reference_queries": [entity.get("display_name") or entity_id],
            "brave_search_queries": queries,
            "must_include": must_include,
            "must_avoid": must_avoid,
            "contact_sheet_required": bool(entity.get("contact_sheet_required", True)),
            "contact_sheet_kind": entity.get("contact_sheet_kind", f"{entity_type}_reference_pack"),
            "retry_budget": {
                "max_search_rounds": max_search_rounds,
                "max_generation_rounds_per_entity": max_generation_rounds,
                "max_review_rounds": 2,
            },
        })

        for ref in provided:
            chosen_refs.append({
                "entity_id": entity_id,
                "reference_source": "provided",
                "path_or_url": ref,
                "status": "unverified",
                "reason": "Provided by caller; casting-agent must verify before contact-sheet generation.",
            })

        work_elements.append({
            "entity_id": entity_id,
            "element_name": entity.get("display_name") or entity_id,
            "entity_type": entity_type,
            "description": entity.get("description", ""),
            "planned_panels": panels,
            "provider_rule": "2-4 separate images per Kling Element; human contact sheet is review-only.",
            "ready_for_contact_sheet": bool(provided) or bool(queries),
        })

    contract = {
        "schema": "casting_agent.casting_contract.v1",
        "status": "planned",
        "story_path": str(story),
        "visual_entities_path": str(visual_entities),
        "source_story_package": str(source_package) if source_package else None,
        "context": context_text,
        "live_calls_performed": False,
        "paid_provider_call_performed": False,
        "entities": casting_entities,
    }
    chosen = {
        "schema": "casting_agent.chosen_reference_inputs.v1",
        "status": "planned",
        "references": chosen_refs,
    }
    work = {
        "schema": "casting_agent.contact_sheet_work_order.v1",
        "status": "planned",
        "downstream_skill": "contact-sheet",
        "elements": work_elements,
    }

    (out_dir / "casting_contract.json").write_text(json.dumps(contract, indent=2) + "\n")
    (out_dir / "chosen_reference_inputs.json").write_text(json.dumps(chosen, indent=2) + "\n")
    (out_dir / "contact_sheet_work_order.json").write_text(json.dumps(work, indent=2) + "\n")
    (out_dir / "casting_plan.md").write_text(
        "# Casting Plan\n\n"
        f"- Story: `{story}`\n"
        f"- Visual entities: `{visual_entities}`\n"
        f"- Entities: {len(casting_entities)}\n"
        f"- Provided references: {len(chosen_refs)}\n"
        "- Live calls performed: false\n"
        "- Next: verify references or run Brave search, then delegate to `contact-sheet`.\n"
    )
    return {
        "status": "planned",
        "out_dir": str(out_dir),
        "entity_count": len(casting_entities),
        "provided_reference_count": len(chosen_refs),
        "artifacts": [
            str(out_dir / "casting_contract.json"),
            str(out_dir / "chosen_reference_inputs.json"),
            str(out_dir / "contact_sheet_work_order.json"),
            str(out_dir / "casting_plan.md"),
        ],
    }


@app.command("plan-package")
def plan_package(
    story_package: Annotated[Path, typer.Option("--story-package", help="Keyed story visual package JSON.")],
    out_dir: Annotated[Path, typer.Option("--out-dir", help="Output directory for casting artifacts.")],
    context: Annotated[list[str], typer.Option("--context", help="Additional story/casting context.")] = None,
    reference: Annotated[list[str], typer.Option("--reference", help="<entity_id>=<path-or-url>. Repeatable.")] = None,
    max_search_rounds: Annotated[int, typer.Option("--max-search-rounds", min=0, max=10)] = 3,
    max_generation_rounds: Annotated[int, typer.Option("--max-generation-rounds", min=0, max=10)] = 2,
) -> None:
    """Plan casting from a required keyed story visual package JSON."""
    package = _load_json(story_package)
    package_context = _package_context(package)
    context_values = []
    if package_context:
        context_values.append(package_context)
    context_values.extend(context or [])
    story, visual_entities, package_refs = _write_package_inputs(story_package, package, out_dir)
    result = _plan_artifacts(
        story=story,
        visual_entities=visual_entities,
        out_dir=out_dir,
        context=context_values,
        reference=reference or [],
        max_search_rounds=max_search_rounds,
        max_generation_rounds=max_generation_rounds,
        source_package=story_package,
    )
    result["story_package"] = str(story_package)
    result["embedded_reference_count"] = len(package_refs)
    typer.echo(json.dumps(result, indent=2))


@app.command("identity-contracts")
def identity_contracts(
    casting_contract: Annotated[Path, typer.Option("--casting-contract", help="casting_contract.json path.")],
    receipt_dir: Annotated[Path, typer.Option("--receipt-dir", help="Directory containing Brave search receipt JSON files.")],
    out_dir: Annotated[Path, typer.Option("--out-dir", help="Output directory for identity_contracts/*.json.")],
) -> None:
    """Write identity contracts from casting contract plus raw Brave receipts."""
    contract = _load_json(casting_contract)
    entities = contract.get("entities") or []
    if not entities:
        raise typer.BadParameter(f"no entities found in {casting_contract}")
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    missing_receipts = []
    for entity in entities:
        entity_id = entity.get("entity_id")
        receipt_path = _receipt_path_for_entity(receipt_dir, entity_id)
        receipt_paths = [str(receipt_path)] if receipt_path else []
        source_urls = list(entity.get("source_urls") or [])
        if receipt_path:
            source_urls.extend(_load_receipt_urls(receipt_path)[:12])
        elif entity.get("reference_strategy") == "brave_search_needed":
            missing_receipts.append(entity_id)
        identity = {
            "schema": "casting_agent.identity_contract.v1",
            "entity_id": entity_id,
            "entity_key": entity.get("entity_key"),
            "entity_type": entity.get("entity_type"),
            "canonical_name": entity.get("display_name") or entity_id,
            "description": entity.get("description", ""),
            "required_identity_terms": entity.get("brave_search_queries") or [entity.get("display_name") or entity_id],
            "required_visual_anchors": entity.get("must_include") or [],
            "forbidden_genericizations": entity.get("must_avoid") or [],
            "provided_references": entity.get("provided_references") or [],
            "search_queries": entity.get("brave_search_queries") or [],
            "search_receipt_paths": receipt_paths,
            "source_urls": source_urls,
            "contract_notes": [
                "Generated by casting-agent from story visual package and Brave receipts.",
                "Use this contract before prompt/image generation; fail closed on contradictions.",
            ],
        }
        path = out_dir / f"{entity_id}.json"
        path.write_text(json.dumps(identity, indent=2) + "\n")
        written.append(str(path))
    result = {
        "status": "planned",
        "identity_contract_count": len(written),
        "missing_receipts": missing_receipts,
        "artifacts": written,
    }
    typer.echo(json.dumps(result, indent=2))


@app.command()
def sanity() -> None:
    """Run a tiny fixture through the planner."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        story = root / "story_contract.md"
        story.write_text("Horus and Embry discuss SPARTA Explorer under a patio umbrella.\n")
        visual = root / "visual_entities.json"
        visual.write_text(json.dumps({
            "entities": {
                "characters": [{
                    "entity_id": "character_horus_lupercal_warmaster",
                    "display_name": "Horus Lupercal / The Warmaster",
                    "story_role": "Warm pre-Heresy collaborator",
                    "visual_anchors": ["bald", "pale", "white gold armor"],
                    "must_not_include": ["corrupted chaos monster"],
                    "contact_sheet_required": True,
                }]
            }
        }))
        out = root / "out"
        # Reuse the planner function through Typer would be awkward; run command body by shelling to self.
        import subprocess, sys
        result = subprocess.run([
            sys.executable,
            str(Path(__file__).resolve()),
            "plan",
            "--story", str(story),
            "--visual-entities", str(visual),
            "--out-dir", str(out),
            "--context", "pre-Heresy smiling Horus",
            "--reference", "character_horus_lupercal_warmaster=/tmp/horus.png",
        ], check=True, capture_output=True, text=True)
        for name in ("casting_contract.json", "chosen_reference_inputs.json", "contact_sheet_work_order.json"):
            if not (out / name).exists():
                raise RuntimeError(f"missing {name}")
        data = json.loads((out / "casting_contract.json").read_text())
        assert data["entities"][0]["reference_strategy"] == "provided_reference"
        package = root / "story_visual_package.json"
        package.write_text(json.dumps({
            "schema": "persona_dream.story_visual_package.v1",
            "story_id": "sanity_horus_embry",
            "story": {
                "text": "Horus and Embry discuss SPARTA Explorer under a patio umbrella.",
                "context": "pre-Heresy smiling Horus",
            },
            "keyed_entities": {
                "characters": {
                    "horus": {
                        "entity_id": "character_horus_lupercal_warmaster",
                        "display_name": "Horus Lupercal / The Warmaster",
                        "description": "Warm pre-Heresy collaborator.",
                        "image_file_paths": ["/tmp/horus.png"],
                        "visual_anchors": ["bald", "pale", "white gold armor"],
                        "must_not_include": ["corrupted chaos monster"],
                        "contact_sheet_required": True,
                    }
                }
            },
        }))
        package_out = root / "package_out"
        package_result = subprocess.run([
            sys.executable,
            str(Path(__file__).resolve()),
            "plan-package",
            "--story-package", str(package),
            "--out-dir", str(package_out),
        ], check=True, capture_output=True, text=True)
        package_data = json.loads((package_out / "casting_contract.json").read_text())
        assert package_data["source_story_package"] == str(package)
        assert package_data["entities"][0]["entity_key"] == "horus"
        assert package_data["entities"][0]["provided_references"] == ["/tmp/horus.png"]
        typer.echo(result.stdout.strip())
        typer.echo(package_result.stdout.strip())
        typer.echo("sanity_ok")


@app.command("sanity-e2e")
def sanity_e2e(
    artifact_root: Annotated[
        Path | None,
        typer.Option("--artifact-root", help="Optional output root. Defaults to a temporary directory."),
    ] = None,
) -> None:
    """Run positive and negative casting-agent E2E sanity gates."""
    temp_ctx = None
    if artifact_root is None:
        temp_ctx = tempfile.TemporaryDirectory()
        root = Path(temp_ctx.name)
    else:
        root = artifact_root
        root.mkdir(parents=True, exist_ok=True)

    try:
        story = root / "story_contract.md"
        visual = root / "visual_entities.json"
        ref_dir = root / "references"
        ref_dir.mkdir(exist_ok=True)
        horus_ref = ref_dir / "horus_pre_heresy_ref.png"
        embry_ref = ref_dir / "embry_ref.png"
        _write_fixture_png(horus_ref)
        _write_fixture_png(embry_ref)

        story.write_text(
            "Horus Lupercal and Embry sit at a patio tea table under an "
            "umbrella on a 40K void world while Tyranids move in the far "
            "background. They discuss SPARTA Explorer as a humane evidence "
            "workspace.\n"
        )
        visual.write_text(json.dumps({
            "schema": "persona_dream.visual_entities.v1",
            "entities": {
                "characters": [
                    {
                        "entity_id": "character_horus_lupercal_warmaster",
                        "category": "character",
                        "display_name": "Horus Lupercal / The Warmaster",
                        "story_role": "Pre-Heresy charismatic collaborator",
                        "visual_anchors": [
                            "bald",
                            "pale",
                            "primarch-scale",
                            "white and gold armor",
                            "red cloak",
                        ],
                        "must_not_include": [
                            "corrupted chaos monster",
                            "generic dark-haired man",
                        ],
                        "contact_sheet_required": True,
                    },
                    {
                        "entity_id": "character_embry",
                        "category": "character",
                        "display_name": "Embry",
                        "story_role": "Warm humane SPARTA product collaborator",
                        "visual_anchors": ["calm", "practical", "fictional persona"],
                        "must_not_include": ["celebrity likeness"],
                        "contact_sheet_required": True,
                    },
                ],
                "environments": [
                    {
                        "entity_id": "environment_void_tea_terrace",
                        "category": "environment",
                        "display_name": "Void-world patio tea terrace",
                        "story_role": "Primary conversation setting",
                        "visual_anchors": [
                            "patio table",
                            "umbrella",
                            "void world",
                            "distant Warhammer 40,000 background scale",
                        ],
                        "must_not_include": ["generic modern cafe"],
                        "contact_sheet_required": True,
                    }
                ],
                "objects": [
                    {
                        "entity_id": "object_patio_table_umbrella_tea",
                        "category": "object",
                        "display_name": "Patio table, umbrella, and tea service",
                        "story_role": "Foreground prop kit",
                        "visual_anchors": ["round table", "umbrella", "tea cups", "SPARTA Explorer notes"],
                        "must_not_include": ["weapon-focused tableau"],
                        "contact_sheet_required": True,
                    }
                ],
                "creatures": [
                    {
                        "entity_id": "creature_tyranids_background",
                        "category": "creature",
                        "display_name": "Tyranids from Warhammer 40,000",
                        "story_role": "Distant background motion",
                        "visual_anchors": [
                            "chitin carapace",
                            "scything talons",
                            "hive-organism silhouettes",
                        ],
                        "must_not_include": ["cute alien wildlife"],
                        "contact_sheet_required": True,
                    }
                ],
            },
        }, indent=2))

        positive_out = root / "positive"
        positive = _run_case([
            "plan",
            "--story", str(story),
            "--visual-entities", str(visual),
            "--out-dir", str(positive_out),
            "--context", "pre-Heresy smiling Horus; calm tea-table product design meeting",
            "--reference", f"character_horus_lupercal_warmaster={horus_ref}",
            "--reference", f"character_embry={embry_ref}",
        ])
        if positive.returncode != 0:
            raise RuntimeError(f"positive case failed: {positive.stderr}")

        required_outputs = [
            positive_out / "casting_contract.json",
            positive_out / "chosen_reference_inputs.json",
            positive_out / "contact_sheet_work_order.json",
            positive_out / "casting_plan.md",
        ]
        for path in required_outputs:
            if not path.exists():
                raise RuntimeError(f"positive case missing artifact: {path}")

        contract = json.loads((positive_out / "casting_contract.json").read_text())
        chosen = json.loads((positive_out / "chosen_reference_inputs.json").read_text())
        work = json.loads((positive_out / "contact_sheet_work_order.json").read_text())
        assert contract["schema"] == "casting_agent.casting_contract.v1"
        assert contract["live_calls_performed"] is False
        assert contract["paid_provider_call_performed"] is False
        assert len(contract["entities"]) == 5
        strategies = {e["entity_id"]: e["reference_strategy"] for e in contract["entities"]}
        assert strategies["character_horus_lupercal_warmaster"] == "provided_reference"
        assert strategies["character_embry"] == "provided_reference"
        assert strategies["creature_tyranids_background"] == "brave_search_needed"
        assert strategies["environment_void_tea_terrace"] == "brave_search_needed"
        assert strategies["object_patio_table_umbrella_tea"] == "brave_search_needed"
        assert len(chosen["references"]) == 2
        assert len(work["elements"]) == 5
        assert all(2 <= len(e["planned_panels"]) <= 4 for e in work["elements"])

        contact_sheet_case = _build_contact_sheet_fixture(root)
        if not contact_sheet_case["all_expected_artifacts_present"]:
            raise RuntimeError(f"contact-sheet fixture failed: {contact_sheet_case}")

        negative_cases = []

        missing_story = _run_case([
            "plan",
            "--story", str(root / "missing_story.md"),
            "--visual-entities", str(visual),
            "--out-dir", str(root / "negative_missing_story"),
        ])
        negative_cases.append({
            "id": "missing_story",
            "returncode": missing_story.returncode,
            "stderr": missing_story.stderr,
            "passed": missing_story.returncode != 0 and "story not found" in missing_story.stderr,
        })

        missing_visual_entities = _run_case([
            "plan",
            "--story", str(story),
            "--visual-entities", str(root / "missing_visual_entities.json"),
            "--out-dir", str(root / "negative_missing_visual_entities"),
        ])
        negative_cases.append({
            "id": "missing_visual_entities",
            "returncode": missing_visual_entities.returncode,
            "stderr": missing_visual_entities.stderr,
            "passed": missing_visual_entities.returncode != 0 and "file not found" in missing_visual_entities.stderr,
        })

        bad_reference = _run_case([
            "plan",
            "--story", str(story),
            "--visual-entities", str(visual),
            "--out-dir", str(root / "negative_bad_reference"),
            "--reference", "not-a-valid-reference",
        ])
        negative_cases.append({
            "id": "bad_reference_format",
            "returncode": bad_reference.returncode,
            "stderr": bad_reference.stderr,
            "passed": bad_reference.returncode != 0 and "--reference must be <entity_id>=<path-or-url>" in bad_reference.stderr,
        })

        empty_visual = root / "empty_visual_entities.json"
        empty_visual.write_text(json.dumps({"entities": {"characters": []}}))
        empty_entities = _run_case([
            "plan",
            "--story", str(story),
            "--visual-entities", str(empty_visual),
            "--out-dir", str(root / "negative_empty_entities"),
        ])
        negative_cases.append({
            "id": "empty_entity_list",
            "returncode": empty_entities.returncode,
            "stderr": empty_entities.stderr,
            "passed": empty_entities.returncode != 0 and "no entities found" in empty_entities.stderr,
        })

        if not all(case["passed"] for case in negative_cases):
            raise RuntimeError(f"negative case failure: {negative_cases}")

        report = {
            "schema": "casting_agent.e2e_sanity_report.v1",
            "status": "pass",
            "artifact_root": str(root),
            "positive_case": {
                "status": "pass",
                "entity_count": len(contract["entities"]),
                "provided_reference_count": len(chosen["references"]),
                "contact_sheet_work_order_element_count": len(work["elements"]),
                "artifacts": [str(path) for path in required_outputs],
                "live_calls_performed": False,
                "paid_provider_call_performed": False,
            },
            "contact_sheet_case": {
                "status": "pass",
                "fixture_asset_count": contact_sheet_case["fixture_asset_count"],
                "asset_root": contact_sheet_case["asset_root"],
                "artifacts": contact_sheet_case["expected_artifacts"],
                "live_calls_performed": False,
                "paid_provider_call_performed": False,
            },
            "negative_cases": negative_cases,
        }
        (root / "e2e_sanity_report.json").write_text(json.dumps(report, indent=2) + "\n")
        typer.echo(json.dumps(report, indent=2))
        typer.echo("sanity_e2e_ok")
    finally:
        if temp_ctx is not None:
            temp_ctx.cleanup()


if __name__ == "__main__":
    app()
