#!/usr/bin/env python3
"""Generate site/research-map.json from the DECLARED discipline taxonomy.

This is the #1289 taxonomy bridge: it replaces keyword/filename-prefix
classification with a versioned map from the canonical 18 disciplines
(owned by /project-taxonomy, declared in every SKILL.md `disciplines:`
frontmatter) to a small set of client-facing research areas. Projects land in
an area via their own declared discipline (plus a declared `taxonomy:` signal
where a discipline serves two areas — e.g. battle's `competition` tag routes it
to adaptive-lineage rather than compliance). Areas carry client-language
aliases so downstream BM25 search (#1292) matches the words clients type.

Nothing here is LLM-inferred; the bridge is data, maintained in source.
Run by monitor-website refresh alongside the other generated surfaces.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILLS = REPO / "skills"
CONTENT = REPO / "site" / "content.json"
OUT = REPO / "site" / "research-map.json"

# --- Versioned bridge: canonical discipline -> client-facing area ------------
# `taxonomy_route` overrides the discipline when a project also declares a
# matching `taxonomy:` tag (keeps adaptive-lineage distinct from compliance
# though both are `compliance-security`).
AREAS = [
    {
        "id": "pipelines",
        "title": "Agentic pipelines & orchestration",
        "blurb": "Reliable agent execution and orchestration — contracts, transport, and runtime truth.",
        "disciplines": ["agentic-orchestration", "browser-automation", "developer-tooling", "model-ops"],
        "aliases": ["agent orchestration", "agent harness", "tool use", "browser agents", "dag", "workflow", "orchestration"],
    },
    {
        "id": "memory",
        "title": "Agentic memory & persona",
        "blurb": "Durable memory, persona, and voice an agent keeps and re-queries as its own history.",
        "disciplines": ["memory-knowledge", "persona-simulation", "voice-audio"],
        "aliases": ["memory", "rag memory", "persona", "voice", "continuity", "long-lived agent"],
    },
    {
        "id": "extraction",
        "title": "Extraction & evidence",
        "blurb": "Documents, research, and video into one truthful, cited result — no knobs to mislead.",
        "disciplines": ["extraction", "research-retrieval", "data-engineering"],
        "aliases": ["document extraction", "pdf", "ocr", "rag", "retrieval", "research", "citations", "ingestion"],
    },
    {
        "id": "compliance",
        "title": "Compliance, security & governance",
        "blurb": "Evidence-grounded reasoning where a human, not the model, holds authority.",
        "disciplines": ["compliance-security", "engineering-standards"],
        "aliases": ["compliance", "security", "governance", "audit", "policy", "oscal", "assurance", "gate"],
    },
    {
        "id": "adaptive-lineage",
        "title": "Adaptive-lineage hacking",
        "blurb": "Adversarial evolution and security testing scored by deterministic proof gates.",
        "disciplines": [],  # reached only via taxonomy_route below
        "taxonomy_route": {"compliance-security": "competition"},
        "aliases": ["red team", "adversarial", "exploit", "security testing", "fuzzing", "evolution", "arena"],
    },
    {
        "id": "applied-ml",
        "title": "Applied ML & formal methods",
        "blurb": "Trained models and machine-checked proofs where a result has to be verifiable.",
        "disciplines": ["ml-training"],
        "aliases": ["machine learning", "training", "classifier", "lean4", "formal verification", "proof"],
    },
    {
        "id": "design-interface",
        "title": "Design & interface",
        "blurb": "Interfaces and design systems built to be operated, not just admired.",
        "disciplines": ["ui-design-engineering"],
        "aliases": ["ux", "ui", "frontend", "react", "design system", "interface"],
    },
    {
        "id": "creative-media",
        "title": "Creative & media research",
        "blurb": "Image, video, voice, and music generation — the creative-production half of the practice.",
        "disciplines": ["content-creation"],
        "aliases": ["video generation", "image generation", "music", "film", "creative ai", "media", "score"],
    },
]

# Disciplines intentionally not surfaced as client research areas.
SUPPORTING = {"observability-operations", "human-collaboration"}


def _frontmatter(path: Path) -> str:
    m = re.match(r"(?s)^---\n(.*?)\n---", path.read_text(errors="replace"))
    return m.group(1) if m else ""


def _list_field(front: str, field: str) -> list[str]:
    m = re.search(rf"(?ms)^{field}:\s*\n((?:[ \t]+-[ \t]*[a-z0-9-]+\s*\n?)+)", front)
    return re.findall(r"-[ \t]*([a-z0-9-]+)", m.group(1)) if m else []


def _skill_disciplines(name: str) -> tuple[list[str], list[str]]:
    p = SKILLS / name / "SKILL.md"
    if not p.exists():
        return [], []
    front = _frontmatter(p)
    return _list_field(front, "disciplines"), _list_field(front, "taxonomy")


def _area_for(disciplines: list[str], taxonomy: list[str]) -> str | None:
    """Map a skill's declared disciplines (+ taxonomy signal) to one area id."""
    # taxonomy overrides first (e.g. compliance-security + competition -> adaptive)
    for area in AREAS:
        route = area.get("taxonomy_route", {})
        for disc, tag in route.items():
            if disc in disciplines and tag in taxonomy:
                return area["id"]
    for area in AREAS:
        if any(d in area["disciplines"] for d in disciplines):
            return area["id"]
    return None


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def main() -> None:
    content = json.loads(CONTENT.read_text(encoding="utf-8"))
    projects = content["projects"]

    # Assign each site project to an area via its declared discipline. The
    # project slug is usually the skill dir; sparta-explorer maps to sparta-review.
    slug_to_skill = {"sparta-explorer": "sparta-review"}
    by_area: dict[str, list[dict]] = {a["id"]: [] for a in AREAS}
    unrouted = []
    for p in projects:
        skill = slug_to_skill.get(p["slug"], p["slug"])
        disc, tax = _skill_disciplines(skill)
        area_id = _area_for(disc, tax)
        if area_id is None:
            unrouted.append((p["slug"], disc, tax))
            continue
        by_area[area_id].append(
            {"slug": p["slug"], "name": p["name"], "href": p["href"]}
        )
    if unrouted:
        raise SystemExit(f"projects could not be routed to an area: {unrouted}")

    # Count skills per area from declared disciplines (not directory prefixes).
    skill_counts: dict[str, int] = {a["id"]: 0 for a in AREAS}
    for skill_dir in sorted(SKILLS.glob("*/SKILL.md")):
        disc, tax = _list_field(_frontmatter(skill_dir), "disciplines"), _list_field(
            _frontmatter(skill_dir), "taxonomy"
        )
        area_id = _area_for(disc, tax)
        if area_id:
            skill_counts[area_id] += 1

    areas_out = [
        {
            "id": a["id"],
            "title": a["title"],
            "blurb": a["blurb"],
            "aliases": a["aliases"],
            "disciplines": a["disciplines"] + list(a.get("taxonomy_route", {}).keys()),
            "systems": by_area[a["id"]],
            "skillCount": skill_counts[a["id"]],
        }
        for a in AREAS
    ]

    out = {
        "schema": "grahama.research_map.v2",
        "areas": areas_out,
        "supportingDisciplines": sorted(SUPPORTING),
        "projectCount": len(projects),
        "sourceCommit": _git_commit(),
    }
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with_projects = sum(1 for a in areas_out if a["systems"])
    print(
        f"wrote {OUT.relative_to(REPO)} — {len(areas_out)} areas "
        f"({with_projects} with flagship projects), from declared disciplines"
    )


if __name__ == "__main__":
    main()
