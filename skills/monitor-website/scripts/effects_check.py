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
}
PROHIBITED_CSS_TOKENS = {
    ".glow": "fixed ambient glow selector",
    ".grain": "fixed grain selector",
    "@keyframes rise": "load-time rise animation",
    "@keyframes pop": "ledger cell pop animation",
    ".ruledbg": "decorative ruled background selector",
    "@keyframes c-breathe": "breathing brandmark animation",
    "@keyframes c-glow": "glowing brandmark animation",
    ".cell::after": "ledger pseudo-tooltip that expands document width",
    ".mosaic:hover .cell:not(:hover)": "ledger neighbor recoil effect",
    "transform: scale(1.28)": "ledger hover scale effect",
}


def css_block(source: str, selector: str) -> str:
    for match in re.finditer(r"(?P<selectors>[^{}]+)\{(?P<body>[^{}]*)\}", source, re.S):
        selectors = [part.strip() for part in match.group("selectors").split(",")]
        if selector in selectors:
            return match.group("body")
    return ""


def reduced_motion_blocks(source: str) -> str:
    blocks: list[str] = []
    start = 0
    marker = "@media (prefers-reduced-motion: reduce)"
    while True:
        idx = source.find(marker, start)
        if idx == -1:
            break
        brace = source.find("{", idx)
        if brace == -1:
            break
        depth = 0
        end = brace
        for pos in range(brace, len(source)):
            if source[pos] == "{":
                depth += 1
            elif source[pos] == "}":
                depth -= 1
                if depth == 0:
                    end = pos + 1
                    break
        blocks.append(source[idx:end])
        start = end
    return "\n".join(blocks)


def validate_registered_animation_contract(result: dict, effects: list[dict], css: str) -> None:
    allowed_keyframes = {
        keyframe
        for effect in effects
        if isinstance(effect, dict)
        for keyframe in effect.get("allowed_keyframes", []) or []
    }
    defined_keyframes = set(re.findall(r"@keyframes\s+([a-zA-Z0-9_-]+)", css))
    used_animation_keyframes: set[str] = set()
    for declaration in re.findall(r"animation\s*:\s*([^;]+);", css):
        if declaration.strip() == "none" or declaration.strip().startswith("none "):
            continue
        used_animation_keyframes.update(
            name for name in allowed_keyframes if re.search(rf"\b{re.escape(name)}\b", declaration)
        )
        if not any(re.search(rf"\b{re.escape(name)}\b", declaration) for name in allowed_keyframes):
            result["errors"].append(f"CSS animation declaration is not backed by a registered keyframe: {declaration.strip()}")

    unregistered_defined = sorted(defined_keyframes - allowed_keyframes)
    if unregistered_defined:
        result["errors"].append(f"CSS defines unregistered keyframes: {', '.join(unregistered_defined)}")

    missing_defined = sorted(allowed_keyframes - defined_keyframes)
    if missing_defined:
        result["errors"].append(f"effects.yml registers keyframes not defined in CSS: {', '.join(missing_defined)}")

    unused_registered = sorted(allowed_keyframes - used_animation_keyframes)
    if unused_registered:
        result["errors"].append(f"effects.yml registers keyframes not used by CSS animation declarations: {', '.join(unused_registered)}")

    result.setdefault("counts", {})["defined_keyframes"] = len(defined_keyframes)
    result["counts"]["allowed_keyframes"] = len(allowed_keyframes)
    result["counts"]["used_registered_keyframes"] = len(used_animation_keyframes)


def validate_unusual_path_contract(result: dict, effects_by_id: dict[str, dict], css: str, component: str) -> None:
    effect = effects_by_id.get("unusual-career-path")
    if not effect:
        return

    for selector in effect.get("allowed_selectors", []) or []:
        if selector not in css and selector not in component:
            result["errors"].append(f"unusual-career-path selector not present in CSS/component source: {selector}")

    for keyframe in effect.get("allowed_keyframes", []) or []:
        if f"@keyframes {keyframe}" not in css:
            result["errors"].append(f"unusual-career-path keyframe not defined in CSS: {keyframe}")
        if not re.search(rf"\banimation\s*:[^;]*\b{re.escape(keyframe)}\b", css):
            result["errors"].append(f"unusual-career-path keyframe not used by an animation declaration: {keyframe}")

    reduce = reduced_motion_blocks(css)
    required_reduced_motion = {
        ".path-line": ("stroke-dashoffset: 0", "animation: none"),
        ".is-visible .path-line": ("stroke-dashoffset: 0", "animation: none"),
        ".path-node": ("opacity: 1", "transition: none"),
        ".is-visible .path-node": ("opacity: 1", "transition: none"),
        ".is-visible .path-node.is-final": ("animation: none",),
        ".final-clip": ("transform: scaleX(1)", "animation: none"),
        ".is-visible .final-clip": ("transform: scaleX(1)", "animation: none"),
        ".goal-ring": ("animation: none", "opacity: 0"),
        ".is-visible .goal-ring": ("animation: none", "opacity: 0"),
    }
    for selector, declarations in required_reduced_motion.items():
        block = css_block(reduce, selector)
        if not block:
            result["errors"].append(f"unusual-career-path reduced-motion rule missing: {selector}")
            continue
        normalized = re.sub(r"\s+", " ", block)
        for declaration in declarations:
            if declaration not in normalized:
                result["errors"].append(
                    f"unusual-career-path reduced-motion rule {selector} missing declaration: {declaration}"
                )


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
    effects_by_id = {effect.get("id"): effect for effect in effects if isinstance(effect, dict) and effect.get("id")}
    registered_ids = set(effects_by_id)

    page = (SITE / "app" / "page.tsx").read_text()
    for token, reason in PROHIBITED_HOMEPAGE_TOKENS.items():
        if token in page:
            result["errors"].append(f"homepage still references {reason}: {token}")

    css = (SITE / "app" / "globals.css").read_text()
    for token, reason in PROHIBITED_CSS_TOKENS.items():
        if token in css:
            result["errors"].append(f"CSS still defines {reason}: {token}")
    validate_registered_animation_contract(result, effects, css)
    machine_animation = re.findall(r"\.(machine|hero-plate|ticket)[^{]*\{[^}]*animation\s*:", css, re.S)
    if machine_animation:
        result["errors"].append("captured values or receipt surfaces must not animate")

    component_path = SITE / "components" / "unusual-path.tsx"
    if component_path.exists() and "unusual-career-path" not in registered_ids:
        result["errors"].append("UnusualPath component exists without registered unusual-career-path effect")
    if "unusual-career-path" in registered_ids and not component_path.exists():
        result["errors"].append("unusual-career-path registered but component is missing")
    if "unusual-career-path" in registered_ids and "<UnusualPath" not in page:
        result["errors"].append("unusual-career-path registered but homepage does not render <UnusualPath />")
    if component_path.exists():
        validate_unusual_path_contract(result, effects_by_id, css, component_path.read_text())
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
        "removed_public_effects": len(config.get("removed_public_effects") or []),
        **result["counts"],
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
