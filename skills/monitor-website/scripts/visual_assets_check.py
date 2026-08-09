#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
SITE = REPO / "site"
PUBLIC_VISUAL_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".mp4"}
GENERATED_METHODS = {
    "synthetic_illustration",
    "generated_image",
    "ai_generated",
    "synthetic_as_product_output",
}
REQUIRED_FIELDS = {
    "id",
    "path",
    "kind",
    "source",
    "creation_method",
    "sha256",
    "project_ids",
    "public_approval",
    "role",
    "caption",
    "alt_text",
    "crop",
    "does_not_establish",
}


def load_yaml(path: Path) -> dict:
    import yaml

    return yaml.safe_load(path.read_text())


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO / path


def public_visuals() -> set[str]:
    paths: set[str] = set()
    for path in (SITE / "public").rglob("*"):
        if path.is_file() and path.suffix.lower() in PUBLIC_VISUAL_EXTENSIONS:
            paths.add(path.relative_to(REPO).as_posix())
    app_icon = SITE / "app" / "icon.svg"
    if app_icon.is_file():
        paths.add(app_icon.relative_to(REPO).as_posix())
    return paths


def validate_entry(entry: dict, seen_ids: set[str], seen_paths: set[str]) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED_FIELDS - set(entry))
    asset_id = str(entry.get("id", "<missing-id>"))
    if missing:
        errors.append(f"{asset_id}: missing fields: {', '.join(missing)}")
    if asset_id in seen_ids:
        errors.append(f"{asset_id}: duplicate id")
    seen_ids.add(asset_id)

    rel = str(entry.get("path", ""))
    if rel in seen_paths:
        errors.append(f"{asset_id}: duplicate path {rel}")
    seen_paths.add(rel)
    path = repo_path(rel)
    if not path.is_file():
        errors.append(f"{asset_id}: file missing: {rel}")
    else:
        expected = str(entry.get("sha256", ""))
        actual = sha256(path)
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            errors.append(f"{asset_id}: sha256 must be a 64-character lowercase digest")
        elif expected != actual:
            errors.append(f"{asset_id}: digest mismatch for {rel}")

    if entry.get("role") not in {"evidence", "explanation", "decoration"}:
        errors.append(f"{asset_id}: role must be evidence, explanation, or decoration")
    if entry.get("public_approval") is not True:
        errors.append(f"{asset_id}: public_approval must be true")
    if not entry.get("caption"):
        errors.append(f"{asset_id}: caption missing")
    if not entry.get("alt_text"):
        errors.append(f"{asset_id}: alt_text missing")
    if not entry.get("does_not_establish"):
        errors.append(f"{asset_id}: does_not_establish missing")
    if not entry.get("source"):
        errors.append(f"{asset_id}: source missing")
    if not isinstance(entry.get("project_ids"), list):
        errors.append(f"{asset_id}: project_ids must be a list")

    method = str(entry.get("creation_method", ""))
    if method in GENERATED_METHODS and entry.get("role") == "evidence":
        errors.append(f"{asset_id}: generated asset cannot be marked evidence")
    if entry.get("simulated_craft") is True:
        errors.append(f"{asset_id}: simulated handcrafted material is forbidden")
    if entry.get("altered_or_distressed_machine_evidence") is True:
        errors.append(f"{asset_id}: altered or distressed machine evidence is forbidden")
    return errors


def validate(registry_path: Path) -> dict:
    result = {
        "schema": "monitor_website.visual_assets_check.v1",
        "registry": str(registry_path),
        "status": "PASS",
        "errors": [],
        "counts": {},
    }
    if not registry_path.is_file():
        result["status"] = "FAIL"
        result["errors"].append(f"registry missing: {registry_path}")
        return result

    registry = load_yaml(registry_path) or {}
    if registry.get("schema") != "grahama.visual_assets.v1":
        result["errors"].append("schema must be grahama.visual_assets.v1")
    assets = registry.get("assets") or []
    if not isinstance(assets, list):
        result["errors"].append("assets must be a list")
        assets = []

    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for entry in assets:
        if not isinstance(entry, dict):
            result["errors"].append("asset entry must be a map")
            continue
        result["errors"].extend(validate_entry(entry, seen_ids, seen_paths))

    registered_public = {str(asset.get("path", "")) for asset in assets if isinstance(asset, dict)}
    unregistered = sorted(public_visuals() - registered_public)
    for rel in unregistered:
        result["errors"].append(f"unregistered public visual: {rel}")

    required_project_evidence = {
        "tau": False,
        "sparta-explorer": False,
        "persona-dream": False,
        "grahama-co": False,
    }
    for asset in assets:
        if not isinstance(asset, dict) or asset.get("role") != "evidence":
            continue
        projects = set(asset.get("project_ids") or [])
        for project_id in required_project_evidence:
            if project_id in projects:
                required_project_evidence[project_id] = True
    for project_id, present in required_project_evidence.items():
        if not present:
            result["errors"].append(f"missing evidence asset for {project_id}")

    result["counts"] = {
        "registered_assets": len(assets),
        "public_visuals": len(public_visuals()),
        "evidence_assets": sum(1 for a in assets if isinstance(a, dict) and a.get("role") == "evidence"),
    }
    if result["errors"]:
        result["status"] = "FAIL"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", default=str(SITE / "visual-assets.yml"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = validate(Path(args.registry))
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"visual-assets-check: {result['status']}")
        for error in result["errors"]:
            print(error, file=sys.stderr)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
