#!/usr/bin/env python3
"""gen_catalog.py — deterministic public search corpus (#1291).

Builds site/catalog.json: one searchable document per project, research area,
and skill, assembled from repo state (content.json, research-map.json,
project-visibility.json, inventory.json). Each doc carries the fields the
in-browser BM25 search (#1292) needs — name, aliases, area, disciplines,
summary, href, evidence access — so a client can type a problem ("RAG", "red
team", "which tab acted", "voice agent") and land on the matching work.

Project search text follows the human-facing project documentation: README.md
is preferred, with SKILL.md as an explicit fallback. Public-only and honest: a
project's href/evidence come from the visibility layer (private work links to
its public overview, never the private repo); nothing here is fabricated or
LLM-inferred.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SITE = REPO / "site"
SKILLS = REPO / "skills"
OUT = SITE / "catalog.json"

# Project slug -> the PUBLIC skill dir whose documentation is safe to publish.
# (sparta-explorer indexes the public sparta-review methodology, never the
# private sparta application.)
SLUG_TO_SKILL = {"sparta-explorer": "sparta-review"}


def _plain_markdown(raw: str, cap: int) -> str:
    """Convert authored Markdown to compact searchable text without inventing
    copy. Keep the words, remove presentation syntax, and cap index size."""
    body = re.sub(r"```.*?```", " ", raw, flags=re.S)
    body = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r" \1 ", body)
    body = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", body)
    body = re.sub(r"<[^>]+>", " ", body)
    body = re.sub(r"(?m)^#{1,6}\s*", "", body)
    body = re.sub(r"[`*_>|]", " ", body)
    body = re.sub(r"(?m)^\s*[-+]\s+", " ", body)
    body = re.sub(r"\s+", " ", body).strip()
    return body[:cap]


def _frontmatter_description(raw: str) -> tuple[str, str]:
    """Return (description, prose) for a SKILL.md-like document."""
    fm = re.match(r"(?s)^---\n(.*?)\n---\n(.*)", raw)
    front, prose = (fm.group(1), fm.group(2)) if fm else ("", raw)
    dm = re.search(
        r"(?ms)^description:\s*>?\s*\n?((?:.|\n)*?)(?=^\w[\w-]*:|\Z)",
        front,
    )
    desc = re.sub(r"\s+", " ", (dm.group(1) if dm else "")).strip()
    return desc, prose


def _source_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _skill_text(skill: str, body_cap: int = 2400) -> tuple[str, str, str, str]:
    """Return (description, body, repo-relative path, sha256) from public
    SKILL.md. Missing public documentation produces empty values rather than a
    fabricated summary; downstream validation can decide whether that is
    publishable."""
    p = SKILLS / skill / "SKILL.md"
    if not p.exists():
        return "", "", "", ""
    raw = p.read_text(encoding="utf-8", errors="replace")
    desc, prose = _frontmatter_description(raw)
    body = _plain_markdown(prose, body_cap)
    return desc, body, p.relative_to(REPO).as_posix(), _source_digest(p)


def _project_text(slug: str) -> tuple[str, str, str, str]:
    """Return (body, source path, source kind, sha256) for a public project.

    README.md is the human/operator source and therefore drives client-facing
    search. SKILL.md remains a deterministic fallback for projects without a
    README. The explicit slug mapping keeps private implementations out of the
    public corpus.
    """
    skill = SLUG_TO_SKILL.get(slug, slug)
    readme = SKILLS / skill / "README.md"
    if readme.exists():
        raw = readme.read_text(encoding="utf-8", errors="replace")
        return (
            _plain_markdown(raw, 4800),
            readme.relative_to(REPO).as_posix(),
            "README.md",
            _source_digest(readme),
        )

    desc, body, path, digest = _skill_text(skill, body_cap=4800)
    return " ".join(part for part in (desc, body) if part).strip(), path, "SKILL.md", digest


def _load(name: str) -> dict:
    return json.loads((SITE / name).read_text(encoding="utf-8"))


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def main() -> None:
    content = _load("content.json")
    rmap = _load("research-map.json")
    vis = {v["slug"]: v for v in _load("project-visibility.json")["projects"]}
    inventory = _load("inventory.json")

    # slug -> area (title, id, aliases, lens) from the taxonomy bridge
    project_area: dict[str, dict] = {}
    area_docs = []
    for a in rmap["areas"]:
        for s in a["systems"]:
            project_area[s["slug"]] = a
        area_docs.append(
            {
                "id": f"area:{a['id']}",
                "type": "area",
                "name": a["title"],
                "lens": a["lens"],
                "aliases": a["aliases"],
                "disciplines": a["disciplines"],
                "summary": a["blurb"],
                "skillCount": a["skillCount"],
            }
        )

    docs = list(area_docs)

    for p in content["projects"]:
        v = vis.get(p["slug"], {})
        a = project_area.get(p["slug"], {})
        body, source_path, source_kind, source_digest = _project_text(p["slug"])
        docs.append(
            {
                "id": f"project:{p['slug']}",
                "type": "project",
                "slug": p["slug"],
                "name": p["name"],
                "area": a.get("title", ""),
                "areaId": a.get("id", ""),
                "lens": a.get("lens", ""),
                "aliases": a.get("aliases", []),
                "disciplines": a.get("disciplines", []),
                "question": p.get("question", ""),
                "summary": p.get("blurb", ""),
                "body": body,
                "href": v.get("href") or p.get("href"),
                "visibility": v.get("visibility", "public"),
                "evidenceAccess": v.get("evidence_access", "source"),
                "sourcePath": source_path,
                "sourceKind": source_kind,
                "sourceDigest": source_digest,
            }
        )

    # Skills: lighter docs, findable by name + their area's aliases so a
    # capability query surfaces the contracts behind it.
    for s in inventory.get("skills", []):
        desc, body, source_path, source_digest = _skill_text(s["n"], body_cap=1000)
        docs.append(
            {
                "id": f"skill:{s['n']}",
                "type": "skill",
                "name": s["n"],
                "category": s.get("c", ""),
                "sanity": bool(s.get("s")),
                "summary": desc,
                "body": body,
                "href": f"https://github.com/grahama1970/agent-skills/blob/main/skills/{s['n']}/SKILL.md",
                "sourcePath": source_path,
                "sourceKind": "SKILL.md",
                "sourceDigest": source_digest,
            }
        )

    out = {
        "schema": "grahama.catalog.v1",
        "sourceCommit": _git_commit(),
        "sourcePolicy": {
            "projects": "public README.md preferred; public SKILL.md fallback",
            "skills": "public SKILL.md",
            "copy": "authored source text only; no LLM inference",
        },
        "counts": {
            "areas": sum(1 for d in docs if d["type"] == "area"),
            "projects": sum(1 for d in docs if d["type"] == "project"),
            "skills": sum(1 for d in docs if d["type"] == "skill"),
        },
        "documents": docs,
    }
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)} — {len(docs)} documents ({out['counts']})")


if __name__ == "__main__":
    main()
