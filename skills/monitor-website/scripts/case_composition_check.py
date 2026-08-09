#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
SITE = REPO / "site"


def load_yaml(path: Path) -> dict:
    import yaml

    return yaml.safe_load(path.read_text())


def repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO / path


def visual_assets() -> dict[str, dict]:
    registry = load_yaml(SITE / "visual-assets.yml") or {}
    return {
        str(asset.get("id")): asset
        for asset in registry.get("assets", [])
        if isinstance(asset, dict) and asset.get("id")
    }


def validate(config_path: Path) -> dict:
    result = {
        "schema": "monitor_website.case_composition_check.v1",
        "config": str(config_path),
        "status": "PASS",
        "errors": [],
        "counts": {},
    }
    if not config_path.is_file():
        result["status"] = "FAIL"
        result["errors"].append(f"config missing: {config_path}")
        return result

    config = load_yaml(config_path) or {}
    if config.get("schema") != "grahama.flagship_compositions.v1":
        result["errors"].append("schema must be grahama.flagship_compositions.v1")
    cases = config.get("cases") or []
    if len(cases) != 3:
        result["errors"].append(f"expected exactly 3 flagship cases, found {len(cases)}")

    assets = visual_assets()
    composition_ids: list[str] = []
    project_ids: list[str] = []
    for case in cases:
        if not isinstance(case, dict):
            result["errors"].append("case entry must be a map")
            continue
        project_id = str(case.get("project_id", ""))
        project_ids.append(project_id)
        composition_id = str(case.get("composition_id", ""))
        composition_ids.append(composition_id)
        component = repo_path(str(case.get("component", "")))
        if not component.is_file():
            result["errors"].append(f"{project_id}: component missing: {case.get('component')}")
            source = ""
        else:
            source = component.read_text()
            marker = f'data-case-composition="{composition_id}"'
            if marker not in source:
                result["errors"].append(f"{project_id}: component missing marker {marker}")
        artifact = assets.get(str(case.get("artifact_id", "")))
        if not artifact:
            result["errors"].append(f"{project_id}: artifact_id not registered: {case.get('artifact_id')}")
        else:
            if artifact.get("role") != "evidence" or case.get("artifact_role") != "evidence":
                result["errors"].append(f"{project_id}: flagship artifact must be registered as evidence")
            if str(artifact.get("creation_method", "")).startswith("synthetic") and case.get("artifact_role") == "evidence":
                result["errors"].append(f"{project_id}: generated media used as evidence")
            if project_id not in set(artifact.get("project_ids") or []):
                result["errors"].append(f"{project_id}: artifact project_ids do not include project")
        if case.get("generated_media_used_as_evidence") is not False:
            result["errors"].append(f"{project_id}: generated_media_used_as_evidence must be false")
        if not str(case.get("proof_boundary", "")).strip():
            result["errors"].append(f"{project_id}: proof_boundary missing")
        if not str(case.get("mobile_transformation", "")).strip():
            result["errors"].append(f"{project_id}: mobile_transformation missing")

    if len(set(composition_ids)) != len(composition_ids):
        result["errors"].append("two flagships use the same composition_id")
    if set(project_ids) != {"tau", "sparta-explorer", "persona-dream"}:
        result["errors"].append("flagship projects must be tau, sparta-explorer, and persona-dream")

    page = (SITE / "app" / "page.tsx").read_text()
    forbidden = ["CARD_META", "className=\"card ", "<ProjectCard", "project-card renderer"]
    for token in forbidden:
        if token in page:
            result["errors"].append(f"common project-card renderer residue remains in homepage: {token}")
    for component in ("TauCase", "SpartaCase", "PersonaDreamCase"):
        if component not in page:
            result["errors"].append(f"homepage missing {component}")

    result["counts"] = {
        "cases": len(cases),
        "composition_ids": len(set(composition_ids)),
        "registered_visual_assets": len(assets),
    }
    if result["errors"]:
        result["status"] = "FAIL"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(SITE / "flagship-compositions.yml"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = validate(Path(args.config))
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"case-composition-check: {result['status']}")
        for error in result["errors"]:
            print(error, file=sys.stderr)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
