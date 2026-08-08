#!/usr/bin/env python3
"""Regenerate site/competence.json — an honest core-competence matrix.

Rows are DISCIPLINES the skill corpus actually declares in its own SKILL.md
frontmatter (`disciplines:`), with the real count of skills per discipline and
the flagship projects that exercise it (via the research-map taxonomy bridge).

This is an exhibit, not a self-assessment: every count is derived from committed
skill frontmatter at HEAD, and every representative project is one whose research
area declares that discipline. There are no proficiency ratings — a discipline
with 3 skills reads honestly as thin. Nothing here is market-demand-weighted;
the matrix says what the corpus does, not what is trendy.

Run after gen_inventory / gen_research_map. Writes site/competence.json, stamped
with the source commit so the coherence gate (gen_build_manifest.py) can prove it
was generated at the deploy commit alongside every other surface.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SITE = REPO / "site"
SKILLS = REPO / "skills"


def _load(name: str):
    return json.loads((SITE / name).read_text())


# project-taxonomy owns the closed discipline vocabulary; the matrix must not
# invent a nineteenth. We read its keys directly (stdlib-only: the values are
# block scalars indented deeper than the 2-space keys, so a minimal line parse
# is exact) so there is ONE authority, never a second copy of the list here.
TAXONOMY_VOCAB = REPO / "skills" / "project-taxonomy" / "references" / "disciplines.yml"


def _closed_vocabulary() -> set[str]:
    text = TAXONOMY_VOCAB.read_text(encoding="utf-8")
    keys: set[str] = set()
    in_vocab = False
    for line in text.splitlines():
        if line.rstrip() == "vocabulary:":
            in_vocab = True
            continue
        if in_vocab:
            if line and not line.startswith((" ", "\t")):
                break  # next top-level key ends the vocabulary block
            m = re.match(r"^  ([a-z][a-z0-9-]+):\s*", line)  # exactly-2-space kebab key
            if m:
                keys.add(m.group(1))
    if not keys:
        raise SystemExit(f"competence: could not read closed vocabulary from {TAXONOMY_VOCAB}")
    return keys


def _frontmatter_disciplines(skill: str) -> list[str]:
    """The `disciplines:` list from a skill's SKILL.md YAML frontmatter, parsed
    with a minimal block-scalar reader (no yaml dependency — site scripts are
    stdlib-only). Returns [] when the skill declares none."""
    p = SKILLS / skill / "SKILL.md"
    if not p.is_file():
        return []
    text = p.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return []
    # frontmatter is between the first two '---' fences
    end = text.find("\n---", 3)
    front = text[3:end] if end != -1 else text[3:]
    lines = front.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip() == "disciplines:" or line.startswith("disciplines:"):
            # inline form: disciplines: [a, b]
            after = line.split(":", 1)[1].strip()
            if after.startswith("["):
                out = [x.strip().strip("'\"") for x in after.strip("[]").split(",") if x.strip()]
                break
            # block form: subsequent '  - value' lines until the next top-level key
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                if nxt.strip().startswith("- "):
                    out.append(nxt.strip()[2:].strip().strip("'\""))
                    j += 1
                elif nxt.strip() == "" or nxt.startswith((" ", "\t")):
                    j += 1  # tolerate blank / deeper-indented lines
                else:
                    break  # next top-level key
            break
        i += 1
    return [d for d in out if d]


def _label(discipline_id: str) -> str:
    """Humanize a kebab id, e.g. 'evaluation-quality' -> 'Evaluation quality',
    'ml-training' -> 'ML training'. Acronyms stay uppercase."""
    special = {"ml": "ML", "ui": "UI", "ux": "UX", "ai": "AI"}
    parts = [special.get(w, w) for w in discipline_id.split("-")]
    label = " ".join(parts)
    return label[:1].upper() + label[1:] if label else discipline_id


def main() -> None:
    inventory = _load("inventory.json")
    rmap = _load("research-map.json")
    content = _load("content.json")

    commit = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], cwd=REPO, text=True
    ).strip()
    as_of = subprocess.check_output(
        ["git", "show", "-s", "--format=%cs", "HEAD"], cwd=REPO, text=True
    ).strip()

    skill_names = [s["n"] for s in inventory["skills"]]

    # discipline id -> set of skills declaring it (real counts from frontmatter)
    counts: dict[str, int] = {}
    seen_by: dict[str, str] = {}
    for name in skill_names:
        for d in _frontmatter_disciplines(name):
            counts[d] = counts.get(d, 0) + 1
            seen_by.setdefault(d, name)

    # Bind the matrix to project-taxonomy as the single authority: any discipline
    # outside its closed vocabulary is drift the matrix must NOT render silently.
    vocab = _closed_vocabulary()
    stray = {d: seen_by[d] for d in counts if d not in vocab}
    if stray:
        detail = ", ".join(f"{d!r} (e.g. skills/{s})" for d, s in sorted(stray.items()))
        raise SystemExit(
            "competence: discipline(s) outside project-taxonomy's closed vocabulary: "
            f"{detail}. Add them to skills/project-taxonomy/references/disciplines.yml "
            "(or fix the skill frontmatter) before the matrix can render."
        )

    # discipline id -> areas (lens/title) and flagship project slugs, via the
    # research-map taxonomy bridge (the site's project<->discipline source).
    # content.json is {stats, projects:[{slug,name,href,...}]}; key the flagships by slug.
    flagship = {p["slug"]: p for p in content["projects"]}
    area_of: dict[str, list[dict]] = {}
    projects_of: dict[str, dict[str, dict]] = {}
    for a in rmap["areas"]:
        systems = [s["slug"] for s in a.get("systems", [])]
        for disc in a.get("disciplines", []):
            area_of.setdefault(disc, []).append({"id": a["id"], "title": a["title"], "lens": a["lens"]})
            for slug in systems:
                if slug in flagship:
                    projects_of.setdefault(disc, {})[slug] = {
                        "slug": slug,
                        "name": flagship[slug].get("name", slug),
                        "href": flagship[slug].get("href", f"#{slug}"),
                    }

    disciplines = []
    for disc, n in counts.items():
        areas = area_of.get(disc, [])
        lenses = sorted({a["lens"] for a in areas})
        disciplines.append({
            "id": disc,
            "label": _label(disc),
            "skillCount": n,
            "lenses": lenses,
            "areas": [{"id": a["id"], "title": a["title"]} for a in areas],
            "projects": sorted(projects_of.get(disc, {}).values(), key=lambda p: p["slug"]),
        })
    # most-exercised competence first; stable tiebreak by id
    disciplines.sort(key=lambda d: (-d["skillCount"], d["id"]))

    if not disciplines:
        raise SystemExit("competence generation failed: no disciplines found in skill frontmatter")

    out = {
        "commit": commit,
        "as_of": as_of,
        "generator": "site/scripts/gen_competence.py",
        "totalSkills": len(skill_names),
        "disciplineCount": len(disciplines),
        "disciplines": disciplines,
    }
    (SITE / "competence.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"competence OK: {len(disciplines)} disciplines from {len(skill_names)} skills @ {commit}")


if __name__ == "__main__":
    main()
