#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: Path) -> dict:
    import yaml

    return yaml.safe_load(path.read_text())


def route_exists(route: str) -> bool:
    route = route.strip("/")
    if route.endswith(".html"):
        route = route[:-5]
    if not route:
        return (ROOT / "app" / "page.tsx").is_file()
    return (ROOT / "app" / route / "page.tsx").is_file()


def validate(config_path: Path) -> list[str]:
    errors: list[str] = []
    config = load_yaml(config_path)
    page_path = ROOT / "app" / "page.tsx"
    page = page_path.read_text()

    if config.get("schema") != "grahama.homepage_beats.v1":
        errors.append("schema must be grahama.homepage_beats.v1")

    beats = config.get("beats") or []
    if len(beats) != 5:
        errors.append(f"homepage-beats.yml must declare exactly 5 beats, found {len(beats)}")
    declared_ids = [beat.get("id") for beat in beats]
    rendered_ids = re.findall(r'data-home-beat="([^"]+)"', page)
    if rendered_ids != declared_ids:
        errors.append(f"rendered beat order {rendered_ids} does not match config {declared_ids}")

    for beat in beats:
        section_id = beat.get("section_id")
        if not section_id or f'id="{section_id}"' not in page:
            errors.append(f"section id missing for beat {beat.get('id')}: {section_id}")

    for route in config.get("required_depth_routes") or []:
        if not route_exists(str(route)):
            errors.append(f"required depth route missing: {route}")

    for token in config.get("banned_homepage_imports") or []:
        if token in page:
            errors.append(f"banned homepage import remains: {token}")
    for token in config.get("banned_homepage_tokens") or []:
        if token in page:
            errors.append(f"banned homepage full-surface token remains: {token}")

    if "data-supporting-projects={supporting.join(',')}" not in page:
        errors.append("supporting investigations must expose the compact supporting project set")
    if "const supporting = ['sparta-explorer', 'persona-dream', 'battle']" not in page:
        errors.append("supporting investigations must stay at exactly three named projects")
    for component in ("TauCase", "SpartaCase", "PersonaDreamCase"):
        if component not in page:
            errors.append(f"homepage missing {component}")
    if "HeroContradictionPlate" not in page:
        errors.append("proposition beat must retain HeroContradictionPlate")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(ROOT / "homepage-beats.yml"))
    parser.add_argument("--expect-fail", action="store_true")
    args = parser.parse_args()

    errors = validate(Path(args.config))
    if args.expect_fail:
        if errors:
            print("OK: invalid homepage beats fixture failed validation")
            return 0
        print("expected homepage beats fixture to fail, but it passed", file=sys.stderr)
        return 1

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("OK: homepage has exactly five configured beats and no full explorer modules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
