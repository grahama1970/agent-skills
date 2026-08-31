#!/usr/bin/env python3
"""Validate that grahama.co DESIGN.md is an implementation contract, not vibes."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SITE = REPO / "site"

REQUIRED_HEADINGS = [
    "## 1. Design goal",
    "## 2. CSS source of truth",
    "## 3. Design tokens",
    "## 4. Typography",
    "## 5. Spacing and layout",
    "## 6. Components and interaction styles",
    "## 7. Motion",
    "## 8. Accessibility",
    "## 9. Project-specific visual worlds",
    "## 10. Anti-patterns",
    "## 11. Implementation touchpoints",
    "## 12. Validation commands",
]

REQUIRED_DESIGN_LITERALS = [
    "site/app/globals.css",
    "/fonts/fraunces-site-subset.woff2",
    "/fonts/fraunces-var.woff2",
    "--ink: #0c0908",
    "--text: #ece2d3",
    "--paper: #f2eadc",
    "--brass: #e2ac62",
    "--ember: #d1703c",
    "--sage: #93a289",
    "--gut: clamp(18px, 3.2vw, 44px)",
    "--wrap: min(1260px, 92vw)",
    "font-size: 17px",
    "line-height: 1.62",
    "letter-spacing: 0.005em",
    "font-size: clamp(2rem, 4.4vw, 3.5rem)",
    "padding-block: clamp(64px, 9vw, 140px)",
    ".hero-grid",
    ".hero-main",
    ".hero-side",
    ".shot-link",
    ".shot-img",
    ".project-actions",
    ".github-repo-link",
    ":focus-visible",
    "prefers-reduced-motion",
    "data-qid",
    "data-qs-action",
    "skills/monitor-website/run.sh design-contract-check --json",
    "skills/surf/run.sh snap",
    "site/project-visibility.json",
    "site/visual-assets.yml",
    "site/components/cases/tau-case.tsx",
    "site/app/explore/page.tsx",
    "site/app/page.tsx",
]

REQUIRED_BRAND_LITERALS = [
    "discovered",
    "entertaining",
    "honest",
    "unmistakably Graham",
    "Palantir",
    "Straive",
    "R&D-tech",
    "curiosity",
    "Dream",
    "DARPA",
    "proof boundary",
    "creative and technical work",
]

REQUIRED_BRAND_HEADINGS = [
    "## 1. Brand position",
    "## 2. Brand truth",
    "## 3. Audience and anti-audience",
    "## 4. Curiosity filter",
    "## 5. Tone",
    "## 6. Visual identity",
    "## 7. Proof and honesty",
    "## 8. Competitor/category anti-models",
    "## 9. Portfolio model",
    "## 10. Maintenance rules",
    "## 11. Brand acceptance test",
]

LOCAL_BRAND_LITERALS = [
    "Canonical brand source: `site/BRAND.md`",
    "unmistakably Graham",
    "R&D-tech",
    "Straive",
    "Palantir",
    "Surf",
    "Dream",
    "creative and technical work",
]

LOCAL_DESIGN_LITERALS = [
    "Canonical design source: `site/DESIGN.md`",
    "Executable CSS source: `site/app/globals.css`",
    "--ink: #0c0908",
    "--text: #ece2d3",
    "--brass: #e2ac62",
    "--gut: clamp(18px, 3.2vw, 44px)",
    ".hero-grid",
    ".shot-img",
    ".github-repo-link",
    "prefers-reduced-motion",
    "skills/surf/run.sh snap",
    "site/project-visibility.json",
    "site/visual-assets.yml",
    "site/components/cases/tau-case.tsx",
    "site/app/explore/page.tsx",
    "site/app/page.tsx",
    "skills/monitor-website/run.sh design-contract-check --json",
]

CSS_LITERALS_THAT_MUST_MATCH_DOC = [
    "--ink: #0c0908",
    "--text: #ece2d3",
    "--paper: #f2eadc",
    "--brass: #e2ac62",
    "--ember: #d1703c",
    "--sage: #93a289",
    "--gut: clamp(18px, 3.2vw, 44px)",
    "--wrap: min(1260px, 92vw)",
    "font-size: 17px",
    "line-height: 1.62",
    "letter-spacing: 0.005em",
    "padding-block: clamp(64px, 9vw, 140px)",
]

MIN_DESIGN_WORDS = 1200
MIN_BRAND_WORDS = 1100
MIN_LOCAL_BRAND_WORDS = 500
MIN_LOCAL_DESIGN_WORDS = 500


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def word_count(text: str) -> int:
    return len([part for part in re.split(r"\s+", text.strip()) if part])


def missing_literals(text: str, literals: list[str]) -> list[str]:
    return [literal for literal in literals if literal not in text]


def validate(design_doc: Path, brand_doc: Path, globals_css: Path) -> dict:
    local_brand = REPO / "skills/monitor-website/local/docs/BRAND.md"
    local_design = REPO / "skills/monitor-website/local/docs/DESIGN.md"
    result = {
        "schema": "monitor_website.design_contract_check.v1",
        "design_doc": str(design_doc),
        "brand_doc": str(brand_doc),
        "local_brand_doc": str(local_brand),
        "local_design_doc": str(local_design),
        "globals_css": str(globals_css),
        "status": "PASS",
        "errors": [],
        "metrics": {},
    }
    errors: list[str] = []
    for label, path in (
        ("design_doc", design_doc),
        ("brand_doc", brand_doc),
        ("local_brand_doc", local_brand),
        ("local_design_doc", local_design),
        ("globals_css", globals_css),
    ):
        if not path.is_file():
            errors.append(f"{label} missing: {path}")
    if errors:
        result["status"] = "FAIL"
        result["errors"] = errors
        return result

    design = read(design_doc)
    brand = read(brand_doc)
    local_brand_text = read(local_brand)
    local_design_text = read(local_design)
    css = read(globals_css)
    result["metrics"] = {
        "design_words": word_count(design),
        "brand_words": word_count(brand),
        "local_brand_words": word_count(local_brand_text),
        "local_design_words": word_count(local_design_text),
        "required_headings": len(REQUIRED_HEADINGS),
        "required_brand_headings": len(REQUIRED_BRAND_HEADINGS),
        "required_design_literals": len(REQUIRED_DESIGN_LITERALS),
        "required_brand_literals": len(REQUIRED_BRAND_LITERALS),
    }

    if word_count(design) < MIN_DESIGN_WORDS:
        errors.append(f"DESIGN.md too thin: {word_count(design)} words < {MIN_DESIGN_WORDS}")
    if word_count(brand) < MIN_BRAND_WORDS:
        errors.append(f"BRAND.md too thin: {word_count(brand)} words < {MIN_BRAND_WORDS}")
    if word_count(local_brand_text) < MIN_LOCAL_BRAND_WORDS:
        errors.append(f"local BRAND.md too thin: {word_count(local_brand_text)} words < {MIN_LOCAL_BRAND_WORDS}")
    if word_count(local_design_text) < MIN_LOCAL_DESIGN_WORDS:
        errors.append(f"local DESIGN.md too thin: {word_count(local_design_text)} words < {MIN_LOCAL_DESIGN_WORDS}")
    for heading in REQUIRED_HEADINGS:
        if heading not in design:
            errors.append(f"DESIGN.md missing heading: {heading}")
    for heading in REQUIRED_BRAND_HEADINGS:
        if heading not in brand:
            errors.append(f"BRAND.md missing heading: {heading}")
    for literal in missing_literals(design, REQUIRED_DESIGN_LITERALS):
        errors.append(f"DESIGN.md missing implementation literal: {literal}")
    for literal in missing_literals(brand, REQUIRED_BRAND_LITERALS):
        errors.append(f"BRAND.md missing brand literal: {literal}")
    for literal in missing_literals(local_brand_text, LOCAL_BRAND_LITERALS):
        errors.append(f"local BRAND.md missing literal: {literal}")
    for literal in missing_literals(local_design_text, LOCAL_DESIGN_LITERALS):
        errors.append(f"local DESIGN.md missing literal: {literal}")
    for literal in CSS_LITERALS_THAT_MUST_MATCH_DOC:
        if literal not in css:
            errors.append(f"globals.css no longer contains documented literal: {literal}")
        if literal not in design:
            errors.append(f"DESIGN.md does not document CSS literal: {literal}")
    if "monospace" not in design.lower() or "machine output" not in design.lower():
        errors.append("DESIGN.md must document the monospace/machine-output boundary")
    if "accessibility" not in design.lower() or "alt" not in design.lower():
        errors.append("DESIGN.md must document accessibility and alt-text requirements")
    if "not a Palantir clone" not in design:
        errors.append("DESIGN.md must explicitly reject Palantir-style category mimicry")
    if "not a Straive-style AI operations funnel" not in design:
        errors.append("DESIGN.md must explicitly reject Straive-style category mimicry")
    if "curiosity" not in brand.lower() or "proof boundary" not in brand.lower():
        errors.append("BRAND.md must document curiosity filtering and proof boundaries")

    result["status"] = "FAIL" if errors else "PASS"
    result["errors"] = errors
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--design-doc", default=str(SITE / "DESIGN.md"))
    parser.add_argument("--brand-doc", default=str(SITE / "BRAND.md"))
    parser.add_argument("--globals-css", default=str(SITE / "app/globals.css"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = validate(Path(args.design_doc), Path(args.brand_doc), Path(args.globals_css))
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"design-contract-check: {result['status']}")
        for error in result["errors"]:
            print(f"- {error}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
