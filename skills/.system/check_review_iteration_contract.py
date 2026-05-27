#!/usr/bin/env python3
"""Check that review-* skill docs declare the shared iteration contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "--max-rounds",
    "--output-dir",
    "--ask-gate",
    "--ask-model",
    "--ask-reasoning",
    "--ask-timeout",
    "--ask-focus",
    "review_result.json",
    "PASS",
    "NEEDS_CHANGES",
    "BLOCKED",
    "INSUFFICIENT_EVIDENCE",
]


def _frontmatter(text: str) -> tuple[str | None, str | None]:
    if not text.startswith("---\n"):
        return None, "missing_opening_frontmatter_delimiter"
    end = text.find("\n---\n", len("---\n"))
    if end == -1:
        return None, "missing_closing_frontmatter_delimiter"
    return text[len("---\n") : end], None


def _check_frontmatter(skill_md: Path, text: str) -> list[dict[str, object]]:
    failures: list[dict[str, object]] = []
    raw, error = _frontmatter(text)
    if error:
        return [{"path": str(skill_md), "frontmatter": error}]
    assert raw is not None
    if "## " in raw or "```" in raw:
        failures.append({"path": str(skill_md), "frontmatter": "markdown_inside_frontmatter"})
    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        failures.append({"path": str(skill_md), "frontmatter": "invalid_yaml", "error": str(exc)})
        return failures
    if not isinstance(parsed, dict):
        failures.append({"path": str(skill_md), "frontmatter": "frontmatter_not_mapping"})
        return failures
    expected_name = skill_md.parent.name
    if parsed.get("name") != expected_name:
        failures.append(
            {
                "path": str(skill_md),
                "frontmatter": "name_mismatch",
                "expected": expected_name,
                "actual": parsed.get("name"),
            }
        )
    description = parsed.get("description")
    if not isinstance(description, str) or not description.strip():
        failures.append({"path": str(skill_md), "frontmatter": "missing_description"})
    for field in ("triggers", "provides", "composes"):
        if field not in parsed:
            failures.append({"path": str(skill_md), "frontmatter": f"missing_{field}"})
        elif not isinstance(parsed[field], list):
            failures.append({"path": str(skill_md), "frontmatter": f"{field}_not_list"})
    return failures


def main() -> int:
    failures: list[dict[str, object]] = []
    review_skill_paths = sorted(ROOT.glob("review-*/SKILL.md"))
    for skill_md in review_skill_paths:
        text = skill_md.read_text()
        failures.extend(_check_frontmatter(skill_md, text))
        missing = [token for token in REQUIRED if token not in text]
        if missing:
            failures.append({"path": str(skill_md), "missing": missing})
    if failures:
        print(json.dumps({"ok": False, "failures": failures}, indent=2))
        return 1
    print(json.dumps({"ok": True, "checked": len(review_skill_paths)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
