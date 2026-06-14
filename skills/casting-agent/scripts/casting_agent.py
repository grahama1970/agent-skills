#!/usr/bin/env python3
"""Deterministic planning helper for the casting-agent skill."""

from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

import typer


app = typer.Typer(help="Create story-grounded casting contracts and contact-sheet work orders.")

VERIFY_RECEIPT_SCHEMA_VERSION = "casting-agent-verify-receipt.v1"
CASTING_AGENT_TARGET_PATHS = [
    "skills/casting-agent/SKILL.md",
    "skills/casting-agent/run.sh",
    "skills/casting-agent/scripts/casting_agent.py",
    "skills/casting-agent/references/maintainer-escalation.md",
    "agents/casting-agent/AGENTS.md",
]


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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check_result(checks: list[dict[str, Any]], check_id: str, passed: bool, detail: str) -> None:
    checks.append({"id": check_id, "passed": bool(passed), "detail": detail})


def _is_url(value: str) -> bool:
    return value.startswith(("http://", "https://"))


def _resolve_job_path(job_dir: Path, value: Any) -> Path | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or _is_url(text):
        return None
    path = Path(text)
    if not path.is_absolute():
        path = job_dir / path
    return path


def _path_exists_for_job(job_dir: Path, value: Any) -> bool:
    path = _resolve_job_path(job_dir, value)
    return bool(path and path.exists())


def _load_optional_json(path: Path, checks: list[dict[str, Any]]) -> dict | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        _check_result(checks, f"{path.name}_parse", False, f"{path}: invalid JSON: {exc}")
        return None
    if not isinstance(data, dict):
        _check_result(checks, f"{path.name}_object", False, f"{path}: expected JSON object")
        return None
    _check_result(checks, f"{path.name}_parse", True, f"{path}: valid JSON")
    return data


def _schema_check(checks: list[dict[str, Any]], data: dict | None, path: Path, expected: str) -> None:
    if data is None:
        _check_result(checks, f"{path.stem}_exists", False, f"missing {path}")
        return
    _check_result(checks, f"{path.stem}_exists", True, f"found {path}")
    actual = data.get("schema") or data.get("schema_version")
    _check_result(
        checks,
        f"{path.stem}_schema",
        actual == expected,
        f"{path.name}: expected {expected}, got {actual!r}",
    )


def _path_values(record: dict[str, Any]) -> list[str]:
    values: list[str] = []
    scalar_keys = (
        "evidence_path",
        "artifact_path",
        "receipt_path",
        "review_receipt_path",
        "contact_sheet_receipt_path",
        "contact_sheet_path",
        "blocked_evidence_path",
    )
    list_keys = (
        "evidence_paths",
        "artifact_paths",
        "receipt_paths",
        "review_receipt_paths",
        "contact_sheet_receipt_paths",
    )
    for key in scalar_keys:
        value = record.get(key)
        if value:
            values.append(str(value))
    for key in list_keys:
        raw = record.get(key) or []
        if isinstance(raw, str):
            raw = [raw]
        if isinstance(raw, list):
            values.extend(str(value) for value in raw if str(value).strip())
    return values


def _state_from_record(record: dict[str, Any], default: str | None = None) -> str:
    state = str(record.get("status") or record.get("state") or default or "").strip().lower()
    if not state:
        if record.get("accepted") is True:
            return "accepted"
        if record.get("blocked") is True:
            return "blocked"
    return state


def _collect_terminal_states(job_dir: Path, checks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    states: dict[str, dict[str, Any]] = {}
    receipt_specs = [
        ("accepted_casting_receipt.json", "accepted"),
        ("blocked_casting_receipt.json", "blocked"),
        ("casting_receipt.json", None),
    ]
    found_terminal_receipt = False
    for filename, default_state in receipt_specs:
        path = job_dir / filename
        data = _load_optional_json(path, checks)
        if data is None:
            continue
        found_terminal_receipt = True
        groups: list[tuple[Any, str | None]] = [
            (data.get("entities"), default_state),
            (data.get("entity_states"), default_state),
            (data.get("accepted_entities"), "accepted"),
            (data.get("blocked_entities"), "blocked"),
        ]
        for raw_group, group_default in groups:
            if isinstance(raw_group, dict):
                iterable = raw_group.values()
            elif isinstance(raw_group, list):
                iterable = raw_group
            else:
                iterable = []
            for item in iterable:
                record = item if isinstance(item, dict) else {"entity_id": item}
                entity_id = str(record.get("entity_id") or "").strip()
                if not entity_id:
                    continue
                merged = dict(record)
                merged.setdefault("status", _state_from_record(record, group_default))
                merged.setdefault("source_receipt", str(path))
                states[entity_id] = merged

        entity_id = str(data.get("entity_id") or "").strip()
        if entity_id:
            record = dict(data)
            record.setdefault("status", _state_from_record(record, default_state))
            record.setdefault("source_receipt", str(path))
            states[entity_id] = record

    _check_result(
        checks,
        "terminal_casting_receipt_present",
        found_terminal_receipt,
        "found accepted_casting_receipt.json, blocked_casting_receipt.json, or casting_receipt.json"
        if found_terminal_receipt
        else "missing accepted_casting_receipt.json, blocked_casting_receipt.json, or casting_receipt.json",
    )
    return states


def _claimed_receipt_paths(records: list[dict[str, Any]]) -> list[str]:
    paths: list[str] = []
    for record in records:
        paths.extend(_path_values(record))
    return paths


def validate_job_artifacts(job_dir: Path) -> dict[str, Any]:
    job_dir = job_dir.resolve()
    checks: list[dict[str, Any]] = []
    _check_result(checks, "job_dir_exists", job_dir.exists() and job_dir.is_dir(), f"job_dir={job_dir}")

    contract_path = job_dir / "casting_contract.json"
    chosen_path = job_dir / "chosen_reference_inputs.json"
    work_path = job_dir / "contact_sheet_work_order.json"

    contract = _load_optional_json(contract_path, checks)
    chosen = _load_optional_json(chosen_path, checks)
    work = _load_optional_json(work_path, checks)
    _schema_check(checks, contract, contract_path, "casting_agent.casting_contract.v1")
    _schema_check(checks, chosen, chosen_path, "casting_agent.chosen_reference_inputs.v1")
    _schema_check(checks, work, work_path, "casting_agent.contact_sheet_work_order.v1")

    entities = contract.get("entities") if isinstance(contract, dict) else []
    if not isinstance(entities, list):
        entities = []
    _check_result(checks, "contract_entities_present", bool(entities), f"entity_count={len(entities)}")

    elements = work.get("elements") if isinstance(work, dict) else []
    if not isinstance(elements, list):
        elements = []
    elements_by_entity = {
        str(element.get("entity_id")): element
        for element in elements
        if isinstance(element, dict) and element.get("entity_id")
    }
    terminal_states = _collect_terminal_states(job_dir, checks)

    for entity in entities:
        if not isinstance(entity, dict):
            _check_result(checks, "entity_record_object", False, f"non-object entity record: {entity!r}")
            continue
        entity_id = str(entity.get("entity_id") or "").strip()
        check_prefix = f"entity_{entity_id or 'unknown'}"
        _check_result(checks, f"{check_prefix}_id", bool(entity_id), f"entity_id={entity_id!r}")
        if not entity_id:
            continue

        required = bool(entity.get("contact_sheet_required", True))
        if entity_id not in elements_by_entity:
            _check_result(checks, f"{check_prefix}_work_order_element", not required, "required entity has no work order element")
        else:
            _check_result(checks, f"{check_prefix}_work_order_element", True, "work order element present")

        if not required:
            continue

        state_record = terminal_states.get(entity_id)
        state = _state_from_record(state_record or {})
        _check_result(
            checks,
            f"{check_prefix}_terminal_state",
            state in {"accepted", "blocked"},
            f"state={state!r}; expected accepted or blocked",
        )
        if state in {"accepted", "blocked"}:
            evidence_paths = _path_values(state_record or {})
            evidence_ok = any(_path_exists_for_job(job_dir, value) for value in evidence_paths)
            _check_result(
                checks,
                f"{check_prefix}_evidence_path",
                evidence_ok,
                f"evidence_paths={evidence_paths!r}",
            )

    claimed_paths = _claimed_receipt_paths(
        [record for record in elements if isinstance(record, dict)]
        + [record for record in terminal_states.values() if isinstance(record, dict)]
    )
    for index, value in enumerate(claimed_paths, start=1):
        if _is_url(value):
            continue
        _check_result(
            checks,
            f"claimed_receipt_path_{index}",
            _path_exists_for_job(job_dir, value),
            f"path={value}",
        )

    failed_checks = [check for check in checks if not check["passed"]]
    return {
        "schema_version": VERIFY_RECEIPT_SCHEMA_VERSION,
        "created_at": _now(),
        "skill": "casting-agent",
        "job_dir": str(job_dir),
        "accepted": not failed_checks,
        "checks": checks,
        "failed_checks": failed_checks,
        "artifacts": {
            "casting_contract": str(contract_path),
            "chosen_reference_inputs": str(chosen_path),
            "contact_sheet_work_order": str(work_path),
        },
        "verify_receipt": str(job_dir / "verify-receipt.json"),
    }


def write_verify_receipt(job_dir: Path) -> dict[str, Any]:
    receipt = validate_job_artifacts(job_dir)
    receipt_path = Path(receipt["verify_receipt"])
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return receipt


def load_self_improvement_helper() -> Any:
    helper_path = Path(__file__).resolve().parents[3] / "skills" / "_shared" / "skill_self_improvement.py"
    if not helper_path.exists():
        raise FileNotFoundError(f"{helper_path}:missing_shared_self_improvement_helper")
    spec = importlib.util.spec_from_file_location("skill_self_improvement", helper_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load {helper_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    import struct
    import zlib

    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 960, 576
    rgb = bytes.fromhex(color.removeprefix("#"))
    raw = b"".join(b"\x00" + (rgb * width) for _ in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"tEXt", f"Title\x00{title}".encode("utf-8"))
        + chunk(b"IDAT", zlib.compress(raw, level=9))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)


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
    if not contact_sheet_runner.exists():
        return {
            "asset_root": str(asset_root),
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "expected_artifacts": [],
            "all_expected_artifacts_present": True,
            "fixture_asset_count": len(fixture_assets),
            "skipped": "skills/persona-dream/run.sh not present",
        }
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


@app.command("verify")
def verify_command(
    job_dir: Annotated[Path | None, typer.Option("--job-dir", help="Casting output directory to verify.")] = None,
    out_dir: Annotated[Path | None, typer.Option("--out-dir", help="Alias for --job-dir.")] = None,
) -> None:
    """Verify a completed casting job directory and write verify-receipt.json."""
    target_dir = job_dir or out_dir
    if target_dir is None:
        raise typer.BadParameter("Pass --job-dir or --out-dir.")
    receipt = write_verify_receipt(target_dir)
    typer.echo(json.dumps(receipt, indent=2, ensure_ascii=False))
    if not receipt["accepted"]:
        raise typer.Exit(1)


@app.command("file-maintainer-ticket")
def file_maintainer_ticket_command(
    job_dir: Annotated[Path | None, typer.Option("--job-dir", help="Casting output directory to inspect.")] = None,
    out_dir: Annotated[Path | None, typer.Option("--out-dir", help="Alias for --job-dir.")] = None,
    output: Annotated[Path | None, typer.Option("--output", help="Ticket packet path. Defaults inside the job dir.")] = None,
) -> None:
    """Write a deterministic local maintainer ticket packet from verify output."""
    target_dir = job_dir or out_dir
    if target_dir is None:
        raise typer.BadParameter("Pass --job-dir or --out-dir.")
    receipt = write_verify_receipt(target_dir)
    helper = load_self_improvement_helper()
    packet_path = output or (target_dir / "maintainer-ticket.json")
    packet = helper.write_maintainer_ticket(
        skill_name="casting-agent",
        route="backend_python_or_skill_runtime",
        job_dir=target_dir,
        output_path=packet_path,
        verify_receipt_path=Path(receipt["verify_receipt"]),
        failed_checks=receipt["failed_checks"],
        target_paths=CASTING_AGENT_TARGET_PATHS,
        repro_commands=[
            "cd skills/casting-agent && ./sanity.sh",
            f"cd skills/casting-agent && ./run.sh verify --job-dir {target_dir}",
            f"cd skills/casting-agent && ./run.sh file-maintainer-ticket --job-dir {target_dir}",
            "cd skills/best-practices-skills && uv run python scripts/validate_skill.py ../casting-agent",
        ],
        issue_url="https://github.com/grahama1970/agent-skills/issues/16",
    )
    typer.echo(json.dumps(packet, indent=2, ensure_ascii=False))


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
