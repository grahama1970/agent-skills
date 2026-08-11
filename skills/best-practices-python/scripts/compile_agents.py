"""Compile Python rule references into the skill-level AGENTS.md file.

Inputs: ``rules/_sections.md`` plus matching rule markdown files.
Outputs: ``AGENTS.md`` in the skill root.
Failure modes: raises normal file IO errors when required rule files are missing.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES_DIR = ROOT / "rules"
OUT = ROOT / "AGENTS.md"


def read_section_prefixes() -> list[str]:
    txt = (RULES_DIR / "_sections.md").read_text(encoding="utf-8")
    prefixes: list[str] = []
    for line in txt.splitlines():
        line = line.strip()
        if not line or not line[0].isdigit():
            continue
        if "(" in line and ")" in line:
            prefixes.append(line.split("(", 1)[1].split(")", 1)[0].strip())
    return prefixes


def compile_agents() -> None:
    prefixes = read_section_prefixes()

    parts: list[str] = []
    parts.append("# Python Best Practices (AGENTS)\n")
    parts.append(
        "This document is compiled from `rules/`. Apply categories in order: "
        + " → ".join(prefixes)
        + ".\n"
    )
    parts.append(
        "\nTip: The most important house rules are in `conventions-` and `style-` "
        "(Loguru, Typer, httpx, uv/pyproject, module docstrings, max 800 LOC, sanity tests).\n"
    )

    for prefix in prefixes:
        rule_files = sorted(p for p in RULES_DIR.glob(f"{prefix}-*.md") if p.is_file())
        if not rule_files:
            continue
        parts.append(f"\n## {prefix}\n")
        for path in rule_files:
            # Keep it simple: include the whole rule file; consumers can later trim if desired.
            parts.append(f"\n---\n\n### {path.stem}\n")
            parts.append(path.read_text(encoding="utf-8").strip() + "\n")

    OUT.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    compile_agents()
