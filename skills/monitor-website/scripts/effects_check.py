#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
SITE = REPO / "site"
PROHIBITED_HOMEPAGE_TOKENS = {
    "glow": "fixed ambient glow layer",
    "grain": "fixed grain layer",
    "ruledbg": "decorative ruled background",
    "rise": "load-time hero choreography",
    "UnusualPath": "decorative animated path",
}
PROHIBITED_CSS_TOKENS = {
    ".glow": "fixed ambient glow selector",
    ".grain": "fixed grain selector",
    "@keyframes rise": "load-time rise animation",
    ".ruledbg": "decorative ruled background selector",
    "@keyframes c-breathe": "breathing brandmark animation",
    "@keyframes c-glow": "glowing brandmark animation",
    ".unusual-path-svg": "decorative path drawing selector",
}


def load_yaml(path: Path) -> dict:
    import yaml

    return yaml.safe_load(path.read_text())


def validate(config_path: Path) -> dict:
    result = {
        "schema": "monitor_website.effects_check.v1",
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
    if config.get("schema") != "grahama.effects.v1":
        result["errors"].append("schema must be grahama.effects.v1")
    policy = config.get("policy") or {}
    for key in (
        "ambient_loops_allowed_on_homepage",
        "decorative_fixed_layers_allowed_on_homepage",
        "simulated_material_allowed",
        "captured_values_may_animate",
    ):
        if policy.get(key) is not False:
            result["errors"].append(f"policy.{key} must be false")
    effects = config.get("registered_effects") or []
    if not effects:
        result["errors"].append("registered_effects must not be empty")
    for effect in effects:
        if not isinstance(effect, dict):
            result["errors"].append("registered effect must be a map")
            continue
        for key in ("id", "trigger", "semantic_purpose", "allowed_selectors", "reduced_motion_equivalent"):
            if not effect.get(key):
                result["errors"].append(f"effect {effect.get('id', '<missing-id>')}: {key} missing")

    page = (SITE / "app" / "page.tsx").read_text()
    for token, reason in PROHIBITED_HOMEPAGE_TOKENS.items():
        if token in page:
            result["errors"].append(f"homepage still references {reason}: {token}")

    css = (SITE / "app" / "globals.css").read_text()
    for token, reason in PROHIBITED_CSS_TOKENS.items():
        if token in css:
            result["errors"].append(f"CSS still defines {reason}: {token}")
    machine_animation = re.findall(r"\\.(machine|hero-plate|ticket)[^{]*\\{[^}]*animation\\s*:", css, re.S)
    if machine_animation:
        result["errors"].append("captured values or receipt surfaces must not animate")

    component_path = SITE / "components" / "unusual-path.tsx"
    if component_path.exists():
        result["errors"].append("decorative UnusualPath component still exists")
    constellation = SITE / "components" / "capability-constellation.tsx"
    if constellation.is_file():
        source = constellation.read_text()
        if "<title>{n.title || n.label}</title>" in source:
            result["errors"].append("constellation still uses native SVG title tooltip")
        if "getInspectorData" not in source or "graph-inspector-card" not in source:
            result["errors"].append("constellation missing normalized HTML graph inspector")

    result["counts"] = {
        "registered_effects": len(effects),
        "removed_homepage_effects": len(config.get("removed_homepage_effects") or []),
    }
    if result["errors"]:
        result["status"] = "FAIL"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(SITE / "effects.yml"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = validate(Path(args.config))
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"effects-check: {result['status']}")
        for error in result["errors"]:
            print(error, file=sys.stderr)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
