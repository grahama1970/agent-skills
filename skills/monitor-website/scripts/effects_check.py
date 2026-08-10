#!/usr/bin/env python3
"""Check that public-site CSS animations are registered in site/effects.yml."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]
SITE = REPO / "site"


def strip_comments(text: str) -> str:
    return re.sub(r"/\*.*?\*/", " ", text, flags=re.S)


def load_allowed_keyframes(effects_path: Path) -> set[str]:
    data = yaml.safe_load(effects_path.read_text()) or {}
    allowed: set[str] = set()
    for effect in data.get("registered_effects") or []:
        for name in effect.get("allowed_keyframes") or []:
            allowed.add(str(name))
    return allowed


def iter_css_files(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if not p.is_absolute():
            p = REPO / p
        if p.is_dir():
            files.extend(sorted(p.rglob("*.css")))
        elif p.is_file():
            files.append(p)
    return files


def declared_keyframes(css: str) -> set[str]:
    return set(re.findall(r"@keyframes\s+([_a-zA-Z][-_a-zA-Z0-9]*)", css))


def split_animation_values(value: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    for idx, char in enumerate(value):
        if char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(value[start:idx].strip())
            start = idx + 1
    parts.append(value[start:].strip())
    return [part for part in parts if part]


def animation_uses(css: str) -> list[dict]:
    uses: list[dict] = []
    rule_re = re.compile(r"([^{}@][^{}]*)\{([^{}]*)\}", re.S)
    for match in rule_re.finditer(css):
        selector = " ".join(match.group(1).split())
        body = match.group(2)
        for decl in re.finditer(r"animation(?:-name)?\s*:\s*([^;]+);", body):
            prop = decl.group(0).split(":", 1)[0].strip()
            value = decl.group(1).strip()
            if value == "none" or value.startswith("none "):
                continue
            names = []
            if prop == "animation-name":
                names = [part.strip() for part in value.split(",")]
            else:
                for part in split_animation_values(value):
                    token = part.strip().split()[0] if part.strip() else ""
                    if token and token not in {"none", "linear", "ease", "ease-in", "ease-out", "ease-in-out"}:
                        names.append(token)
            for name in names:
                uses.append({"selector": selector[:140], "keyframe": name, "value": value})
    return uses


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--effects", default=str(SITE / "effects.yml"))
    ap.add_argument("--css", action="append", default=["site/app", "site/components"])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    effects_path = Path(args.effects)
    if not effects_path.is_absolute():
        effects_path = REPO / effects_path
    allowed = load_allowed_keyframes(effects_path)
    files = iter_css_files(args.css)
    findings = []
    all_declared: set[str] = set()
    all_uses: list[dict] = []
    for path in files:
        css = strip_comments(path.read_text())
        declared = declared_keyframes(css)
        uses = animation_uses(css)
        all_declared.update(declared)
        for use in uses:
            use["file"] = str(path.relative_to(REPO))
        all_uses.extend(uses)

    used_names = {use["keyframe"] for use in all_uses}
    for name in sorted(used_names - allowed):
        findings.append({"type": "unregistered_animation_use", "keyframe": name})
    for name in sorted(all_declared - allowed):
        findings.append({"type": "unregistered_keyframes", "keyframe": name})
    for use in all_uses:
        if use["keyframe"] not in allowed:
            findings.append({"type": "unregistered_animation_selector", **use})

    result = {
        "schema": "monitor_website.effects_check.v1",
        "status": "PASS" if not findings else "FAIL",
        "effects": str(effects_path.relative_to(REPO)),
        "css_files_scanned": [str(p.relative_to(REPO)) for p in files],
        "counts": {
            "registered_keyframes": len(allowed),
            "declared_keyframes": len(all_declared),
            "animation_uses": len(all_uses),
            "findings": len(findings),
        },
        "allowed_keyframes": sorted(allowed),
        "findings": findings,
    }
    print(json.dumps(result, indent=2) if args.json else result["status"])
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
