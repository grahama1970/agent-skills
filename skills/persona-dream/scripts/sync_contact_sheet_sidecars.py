#!/usr/bin/env python3
"""Write probed-dimension sidecars and prompt links for contact-sheet PNGs.

Does not duplicate PNG bytes. Each canonical sheet gets:
  - {name}.png                         (single canonical image)
  - {name}.prompt.md                   (symlink to prompt source when possible)
  - {name}.contact_sheet.meta.json     (probed size + full prompt + inline refs)

Sidecar embeds the creation prompt and any inline local/URL/brave-search image
references parsed from that prompt, plus casting/grounding/generation receipts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from PIL import Image

from validate_phase_05_contact_sheet_gate import (
    DEFAULT_REQUIREMENTS,
    probe_png,
)

SIDECAR_SCHEMA = "persona_dream.contact_sheet_sidecar.v2"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
URL_RE = re.compile(r"https?://[^\s)\"\'<>]+", re.IGNORECASE)
MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
ABS_IMAGE_PATH_RE = re.compile(
    r"(?:/[A-Za-z0-9_@.+-]+)+\.(?:png|jpe?g|webp|gif|bmp)",
    re.IGNORECASE,
)
BRAVE_ARTIFACT_RE = re.compile(r"(?:grounding/)?brave_search_[A-Za-z0-9_.-]+\.json")

REQUIREMENT_TO_CASTING_ENTITY: dict[str, str] = {
    "character_horus_lupercal": "character_horus_lupercal_warmaster",
    "character_embry_lawson": "character_embry",
    "creature_adult_tyranids": "creature_warhammer_40k_tyranids_background",
    "creature_baby_tyranid_railing": "creature_baby_tyranid_railing",
    "effect_tzeentch_sky_eye": "effect_tzeentch_warp_eye_void_sky",
    "prop_umbrella": "prop_umbrella",
    "prop_tea_service": "prop_tea_service",
    "prop_sparta_laptop_notes": "prop_sparta_laptop_notes",
    "surface_stone_railing_patio": "surface_stone_railing_patio",
    "environment_void_world_patio": "environment_void_world_patio_tea_terrace",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def requirement_id_for_file(file_name: str) -> str | None:
    for req in DEFAULT_REQUIREMENTS:
        if req.get("file") == file_name:
            return str(req["id"])
    return None


def prompt_candidates(run_root: Path, png_name: str) -> list[Path]:
    refs_dir = run_root / "reference_sheets"
    stem = png_name.removesuffix(".png")
    candidates: list[Path] = [
        refs_dir / f"{stem}.prompt.md",
        run_root / "prompts" / "reference_sheets" / f"{stem}.prompt.md",
    ]
    for suffix in ("_reference_sheet", "_contact_sheet", "_motion_contact_sheet"):
        if stem.endswith(suffix):
            short = stem[: -len(suffix)]
            candidates.append(run_root / "prompts" / "reference_sheets" / f"{short}.prompt.md")
            candidates.append(refs_dir / f"{short}.prompt.md")
    return candidates


def resolve_prompt_path(run_root: Path, png_name: str) -> Path | None:
    for candidate in prompt_candidates(run_root, png_name):
        if candidate.is_file():
            return candidate.resolve()
    return None


def ensure_prompt_link(run_root: Path, png_path: Path, prompt_path: Path, *, write: bool) -> Path:
    link_path = png_path.parent / f"{png_path.stem}.prompt.md"
    if link_path.exists():
        if link_path.is_symlink() and link_path.resolve() == prompt_path:
            return link_path
        if link_path.is_file() and not link_path.is_symlink():
            if link_path.read_text(encoding="utf-8") == prompt_path.read_text(encoding="utf-8"):
                return link_path
    if not write:
        return link_path
    if link_path.is_symlink() or link_path.exists():
        link_path.unlink()
    link_path.symlink_to(prompt_path)
    return link_path


def classify_url(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if "brave" in host or "search.brave" in host:
        return "brave_search"
    return "remote_url"


def probe_reference_file(path: Path) -> dict[str, Any]:
    record: dict[str, Any] = {"path": str(path.resolve()), "exists": path.is_file()}
    if not path.is_file():
        return record
    record["bytes"] = path.stat().st_size
    if path.suffix.lower() not in IMAGE_SUFFIXES:
        record["kind"] = "non_image_file"
        return record
    try:
        with Image.open(path) as image:
            record.update(
                {
                    "kind": "image",
                    "width": image.size[0],
                    "height": image.size[1],
                    "mode": image.mode,
                }
            )
    except OSError as exc:
        record["kind"] = "image_unreadable"
        record["error"] = str(exc)
    return record


def resolve_reference_target(target: str, *, run_root: Path, prompt_path: Path) -> Path | None:
    raw = target.strip().strip("\"'")
    if raw.startswith(("http://", "https://")):
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = (prompt_path.parent / path).resolve()
    return path


def extract_inline_references(prompt_text: str, *, run_root: Path, prompt_path: Path) -> dict[str, Any]:
    markdown_images: list[dict[str, Any]] = []
    local_image_files: list[dict[str, Any]] = []
    remote_urls: list[dict[str, Any]] = []
    brave_search_artifacts: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    seen_urls: set[str] = set()

    for match in MARKDOWN_IMAGE_RE.finditer(prompt_text):
        alt, target = match.group(1), match.group(2).strip()
        entry = {"alt": alt, "target": target, "source": "markdown_image"}
        if target.startswith(("http://", "https://")):
            if target not in seen_urls:
                seen_urls.add(target)
                remote_urls.append({"url": target, "kind": classify_url(target), **entry})
        else:
            path = resolve_reference_target(target, run_root=run_root, prompt_path=prompt_path)
            if path is not None:
                key = str(path)
                if key not in seen_paths:
                    seen_paths.add(key)
                    probed = probe_reference_file(path)
                    probed["source"] = "markdown_image"
                    probed["alt"] = alt
                    local_image_files.append(probed)
        markdown_images.append(entry)

    for match in ABS_IMAGE_PATH_RE.finditer(prompt_text):
        path = Path(match.group(0))
        key = str(path)
        if key in seen_paths:
            continue
        seen_paths.add(key)
        probed = probe_reference_file(path)
        probed["source"] = "absolute_path"
        local_image_files.append(probed)

    for match in URL_RE.finditer(prompt_text):
        url = match.group(0).rstrip(".,;)")
        if url in seen_urls:
            continue
        seen_urls.add(url)
        remote_urls.append({"url": url, "kind": classify_url(url), "source": "prompt_url"})

    for match in BRAVE_ARTIFACT_RE.finditer(prompt_text):
        rel = match.group(0)
        if rel.startswith("grounding/"):
            artifact = run_root / rel
        else:
            artifact = run_root / "grounding" / Path(rel).name
        if artifact.is_file():
            brave_search_artifacts.append(load_brave_artifact_summary(artifact))

    return {
        "markdown_images": markdown_images,
        "local_image_files": local_image_files,
        "remote_urls": remote_urls,
        "brave_search_artifacts": brave_search_artifacts,
    }


def load_brave_artifact_summary(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    facts = []
    for fact in payload.get("facts", []):
        if not isinstance(fact, dict):
            continue
        facts.append(
            {
                "entity_id": fact.get("entity_id"),
                "source_title": fact.get("source_title"),
                "source_url": fact.get("source_url"),
                "summary": fact.get("summary"),
                "thumbnail_url": fact.get("thumbnail_url") or fact.get("image_url"),
            }
        )
    return {
        "artifact_path": str(path.resolve()),
        "schema": payload.get("schema"),
        "artifact_id": payload.get("artifact_id"),
        "query": payload.get("query"),
        "status": payload.get("status"),
        "facts": facts,
    }


def load_casting_context(run_root: Path, requirement_id: str | None) -> dict[str, Any] | None:
    if not requirement_id:
        return None
    casting_path = run_root / "casting" / "casting_contract.json"
    if not casting_path.is_file():
        return None
    casting = json.loads(casting_path.read_text(encoding="utf-8"))
    entity_id = REQUIREMENT_TO_CASTING_ENTITY.get(requirement_id, requirement_id)
    for entity in casting.get("entities", []):
        if str(entity.get("entity_id")) != entity_id:
            continue
        refs = []
        for ref in entity.get("provided_references", []) or []:
            refs.append(probe_reference_file(Path(ref)))
        return {
            "entity_id": entity_id,
            "display_name": entity.get("display_name"),
            "reference_strategy": entity.get("reference_strategy"),
            "provided_references": refs,
            "source_urls": list(entity.get("source_urls") or []),
            "brave_search_queries": list(entity.get("brave_search_queries") or []),
            "memory_reference_queries": list(entity.get("memory_reference_queries") or []),
        }
    return {"entity_id": entity_id, "status": "not_found_in_casting_contract"}


def load_brave_grounding_for_entity(run_root: Path, requirement_id: str | None) -> list[dict[str, Any]]:
    if not requirement_id:
        return []
    entity_id = REQUIREMENT_TO_CASTING_ENTITY.get(requirement_id, requirement_id)
    grounding_dir = run_root / "grounding"
    if not grounding_dir.is_dir():
        return []
    matches: list[dict[str, Any]] = []
    for artifact in sorted(grounding_dir.glob("brave_search_*.json")):
        try:
            payload = json.loads(artifact.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        facts = payload.get("facts") or []
        if any(str(fact.get("entity_id")) == entity_id for fact in facts if isinstance(fact, dict)):
            summary = load_brave_artifact_summary(artifact)
            matches.append(summary)
    return matches


def load_generation_attempt(run_root: Path, png_path: Path) -> dict[str, Any] | None:
    attempts_path = run_root / "generated_image_attempts.json"
    if not attempts_path.is_file():
        return None
    payload = json.loads(attempts_path.read_text(encoding="utf-8"))
    png_resolved = str(png_path.resolve())
    for attempt in payload.get("attempts", []):
        if str(attempt.get("output_path")) == png_resolved:
            return {
                "attempt_id": attempt.get("attempt_id"),
                "backend": attempt.get("backend"),
                "model": attempt.get("model"),
                "size_requested": attempt.get("size"),
                "status": attempt.get("status"),
                "reused_existing": attempt.get("reused_existing"),
                "prompt_path": attempt.get("prompt_path"),
                "receipt_path": attempt.get("receipt_path"),
                "created_at": attempt.get("created_at"),
            }
    return None


def build_sidecar(
    *,
    run_root: Path,
    png_path: Path,
    prompt_path: Path,
    requirement_id: str | None,
) -> dict[str, Any]:
    metrics = probe_png(png_path)
    prompt_text = prompt_path.read_text(encoding="utf-8")
    inline_refs = extract_inline_references(prompt_text, run_root=run_root, prompt_path=prompt_path)
    brave_grounding = load_brave_grounding_for_entity(run_root, requirement_id)
    for item in brave_grounding:
        if item not in inline_refs["brave_search_artifacts"]:
            inline_refs["brave_search_artifacts"].append(item)

    return {
        "schema": SIDECAR_SCHEMA,
        "updated_at": now_iso(),
        "png_file": png_path.name,
        "requirement_id": requirement_id,
        "prompt_path": str(prompt_path),
        "prompt_link_path": str(png_path.with_suffix(".prompt.md")),
        "prompt_sha256": sha256_text(prompt_text),
        "prompt_line_count": len(prompt_text.splitlines()),
        "creation_prompt": prompt_text,
        "creation_prompt_inline_references": inline_refs,
        "casting_context": load_casting_context(run_root, requirement_id),
        "brave_search_grounding": brave_grounding,
        "generation_attempt": load_generation_attempt(run_root, png_path),
        "probed_width": metrics["width"],
        "probed_height": metrics["height"],
        "probed_size_label": metrics["size_label"],
        "probed_size_tier": metrics["size_tier"],
        "png_sha256": metrics["sha256"],
        "png_bytes": metrics["bytes"],
        "layout_ok": metrics["layout_ok"],
        "header_contract": {
            "required_on_image": [
                "requirement_id",
                "probed_width_x_height",
                "prompt_sha256_prefix",
            ],
            "note": (
                "On-image dimension text is not proof. This sidecar records probed bytes "
                "after export/install and preserves the full creation prompt plus inline refs."
            ),
        },
    }


def sync_run(run_root: Path, *, write: bool, only: list[str] | None = None) -> dict[str, Any]:
    refs_dir = run_root / "reference_sheets"
    if not refs_dir.is_dir():
        raise FileNotFoundError(f"missing reference_sheets: {refs_dir}")

    required_files = {str(req["file"]) for req in DEFAULT_REQUIREMENTS if req.get("file")}
    pngs = sorted(refs_dir.glob("*.png"))
    results: list[dict[str, Any]] = []
    missing_prompt: list[str] = []

    for png_path in pngs:
        if only and png_path.name not in only:
            continue
        if png_path.name not in required_files:
            continue
        prompt_path = resolve_prompt_path(run_root, png_path.name)
        if prompt_path is None:
            missing_prompt.append(png_path.name)
            results.append({"png": png_path.name, "status": "MISSING_PROMPT"})
            continue
        prompt_link = ensure_prompt_link(run_root, png_path, prompt_path, write=write)
        sidecar = build_sidecar(
            run_root=run_root,
            png_path=png_path,
            prompt_path=prompt_path,
            requirement_id=requirement_id_for_file(png_path.name),
        )
        sidecar_path = png_path.with_name(f"{png_path.stem}.contact_sheet.meta.json")
        if write:
            sidecar_path.write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
        inline = sidecar["creation_prompt_inline_references"]
        results.append(
            {
                "png": png_path.name,
                "status": "OK",
                "sidecar": str(sidecar_path),
                "prompt_link": str(prompt_link),
                "probed_size": f"{sidecar['probed_width']}x{sidecar['probed_height']}",
                "prompt_sha256": sidecar["prompt_sha256"][:12],
                "inline_local_images": len(inline.get("local_image_files") or []),
                "inline_remote_urls": len(inline.get("remote_urls") or []),
                "brave_artifacts": len(sidecar.get("brave_search_grounding") or []),
            }
        )

    return {
        "run_root": str(run_root),
        "write": write,
        "synced": sum(1 for item in results if item["status"] == "OK"),
        "missing_prompt": missing_prompt,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--write", action="store_true", help="Write sidecars and prompt symlinks")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--only", action="append", help="Limit to one PNG file name")
    args = parser.parse_args()

    payload = sync_run(args.run_root.expanduser().resolve(), write=args.write, only=args.only)
    print(json.dumps(payload, indent=2))
    return 1 if payload["missing_prompt"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
