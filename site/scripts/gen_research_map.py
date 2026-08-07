#!/usr/bin/env python3
"""Generate site/research-map.json — the research-area mini-map.

The homepage groups the flagship projects into a small, declared taxonomy so a
visitor can see the shape of the research program before decoding ten codenames.
The AREAS below are the *declared* taxonomy (maintained here in source, not
inferred by an LLM at render time). Each project is assigned to areas by an
explicit slug list; skills are counted into an area by keyword so the map also
reflects how much of the 300+ skill ledger sits under each theme.

Run by monitor-website refresh alongside the other generated surfaces.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONTENT = REPO / "site" / "content.json"
INVENTORY = REPO / "site" / "inventory.json"
OUT = REPO / "site" / "research-map.json"

# Declared taxonomy. `systems` are project slugs (a project may sit in two
# areas when that is genuinely true — e.g. tau is both pipeline and compliance).
# `skill_keywords` count matching skills from the inventory into the area.
AREAS = [
    {
        "id": "pipelines",
        "title": "Agentic pipelines",
        "blurb": "Reliable agent execution and orchestration — contracts, transport, and runtime truth.",
        "systems": ["tau", "surf", "scillm", "debugger"],
        "skill_keywords": ["ask", "tau", "surf", "scillm", "debug", "orchestr", "agent", "dag", "pipeline", "webgpt", "browser"],
    },
    {
        "id": "memory",
        "title": "Agentic memory",
        "blurb": "Durable memory and persona an agent keeps, dreams on, and re-queries as its own history.",
        "systems": ["persona-dream", "watch"],
        "skill_keywords": ["memory", "persona", "dream", "watch", "recall", "arango", "qdrant", "voice", "embry", "chatterbox"],
    },
    {
        "id": "extraction",
        "title": "Extraction & evidence",
        "blurb": "Turning documents, research, and video into one truthful, cited result — no knobs to mislead.",
        "systems": ["extractor", "dogpile"],
        "skill_keywords": ["extract", "ingest", "dogpile", "qras", "pdf", "ocr", "parse", "discover", "citation", "consume"],
    },
    {
        "id": "compliance",
        "title": "Compliance & governance",
        "blurb": "Evidence-grounded reasoning where a human, not the model, holds authority.",
        "systems": ["sparta-explorer", "tau"],
        "skill_keywords": ["sparta", "compliance", "governance", "policy", "audit", "review", "oscal"],
    },
    {
        "id": "adaptive-lineage",
        "title": "Adaptive lineage hacking",
        "blurb": "Adversarial evolution and security testing scored by deterministic proof gates.",
        "systems": ["battle"],
        "skill_keywords": ["battle", "hack", "exploit", "red", "blue", "adversar", "security", "cve", "eval"],
    },
]


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:  # noqa: BLE001 - provenance is best-effort
        return "unknown"


def main() -> None:
    content = json.loads(CONTENT.read_text(encoding="utf-8"))
    projects = {p["slug"]: p for p in content["projects"]}
    skills = json.loads(INVENTORY.read_text(encoding="utf-8")).get("skills", [])

    declared = {s for a in AREAS for s in a["systems"]}
    missing = declared - projects.keys()
    if missing:
        raise SystemExit(
            f"research map references unknown project slug(s): {sorted(missing)} "
            f"({CONTENT.relative_to(REPO)})"
        )

    areas_out = []
    for area in AREAS:
        kws = area["skill_keywords"]
        skill_count = sum(
            1
            for s in skills
            if any(k in s.get("n", "").lower() or k in s.get("c", "").lower() for k in kws)
        )
        areas_out.append(
            {
                "id": area["id"],
                "title": area["title"],
                "blurb": area["blurb"],
                "systems": [
                    {"slug": slug, "name": projects[slug]["name"], "href": projects[slug]["href"]}
                    for slug in area["systems"]
                ],
                "skillCount": skill_count,
            }
        )

    out = {
        "areas": areas_out,
        "projectCount": len(projects),
        "sourceCommit": _git_commit(),
    }
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)} ({len(areas_out)} areas, {len(projects)} projects)")


if __name__ == "__main__":
    main()
