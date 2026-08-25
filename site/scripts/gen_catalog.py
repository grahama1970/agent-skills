#!/usr/bin/env python3
"""gen_catalog.py — deterministic public search corpus (#1291).

Builds site/catalog.json: one searchable document per project, research area,
and skill, assembled from repo state (content.json, research-map.json,
project-visibility.json, inventory.json). Each doc carries the fields the
in-browser BM25 search (#1292) needs — name, aliases, area, disciplines,
summary, href, evidence access — so a client can type a problem ("RAG", "red
team", "which tab acted", "voice agent") and land on the matching work.

Public-only and honest: a project's href/evidence come from the visibility
layer (private work links to its public overview, never the private repo);
nothing here is fabricated or LLM-inferred.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SITE = REPO / "site"
SKILLS = REPO / "skills"
OUT = SITE / "catalog.json"

# Project slug -> the PUBLIC skill dir whose SKILL.md gives searchable body text.
# (sparta-explorer indexes the public sparta-review methodology, never the
# private sparta application.)
SLUG_TO_SKILL = {"sparta-explorer": "sparta-review"}
NO_PROJECT_SKILL_BODY = {"memory"}


def _skill_text(skill: str) -> tuple[str, str]:
    """(description, body) from a public SKILL.md — frontmatter description plus
    prose with markdown/frontmatter stripped, capped so the index stays small."""
    p = SKILLS / skill / "SKILL.md"
    if not p.exists():
        return "", ""
    raw = p.read_text(errors="replace")
    fm = re.match(r"(?s)^---\n(.*?)\n---\n(.*)", raw)
    front, prose = (fm.group(1), fm.group(2)) if fm else ("", raw)
    dm = re.search(r"(?ms)^description:\s*>?\s*\n?((?:.|\n)*?)(?=^\w[\w-]*:|\Z)", front)
    desc = re.sub(r"\s+", " ", (dm.group(1) if dm else "")).strip()
    # strip code fences, headings markup, links -> plain words; cap length
    body = re.sub(r"```.*?```", " ", prose, flags=re.S)
    body = re.sub(r"[#>*`|_\-]{1,}", " ", body)
    body = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", body)
    body = re.sub(r"\s+", " ", body).strip()[:2400]
    return desc, body


def _load(name: str) -> dict:
    return json.loads((SITE / name).read_text(encoding="utf-8"))


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO, capture_output=True, text=True, check=True,
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

    # Per-project scout keywords: natural-language PROBLEM phrasings each project
    # genuinely solves, so a visitor's problem lands on the right project (the
    # scout-conversion promise, webgpt Criterion 4). Merged into aliases (which
    # BM25 boosts). Must stay TRUE to what the project does — this maps real
    # problems to real work, it is not SEO stuffing. Gated by search_fixture G5.
    SCOUT = {
        "tau": ["orchestrate agents", "agent workers", "multi-agent orchestration",
                "workflow reports success without evidence", "prove what an agent did"],
        "battle": ["adversarial testing", "adversarially test an agent", "red teaming",
                   "test an agent adversarially", "exploit evolution"],
        "surf": ["which browser tab acted", "authenticated browser control",
                 "agent browser provenance"],
        "persona-dream": ["agent forgets previous decisions",
                          "remembers previous conversations",
                          "durable memory across sessions", "memory and persona"],
        "extractor": ["extract from pdfs", "document extraction", "tables and figures"],
        "dogpile": ["research across github arxiv and the web", "multi-source research sweep"],
        "watch": ["what was on screen at an exact moment", "video at exact timestamps",
                  "screen observation"],
        "scillm": ["multiple model providers", "provider glue", "model gateway"],
        "debugger": ["runtime truth before patching", "inspect program state",
                     "live breakpoint state"],
        "memory": ["graph memory", "memory first recall", "ArangoDB memory",
                   "Qdrant semantic recall", "BM25 graph recall",
                   "agent lessons learned"],
        "sparta-explorer": ["trace compliance claims to evidence", "compliance evidence",
                            "governed evidence"],
    }

    # Honest scout-card metadata: what a visitor needs before starting, and the
    # boundary of what the project proves (webgpt Scout Card). Both stay truthful
    # to the real system — "before you start" sets expectations, "known boundary"
    # states what it does NOT establish, matching the evidence culture.
    SCOUT_META = {
        "tau": ("Python env; a model gateway and, for browser handlers, browser bindings.",
                "Proves each agent turn was bounded and receipted — not that the task itself was solved correctly."),
        "battle": ("Docker and isolated target images.",
                   "Scores what actually worked in a sandbox — not production safety."),
        "surf": ("Chrome with the surf extension or a supported CDP setup, and an authenticated browser session.",
                 "Proves tab / element / screenshot provenance — not whether the broader agent workflow is correct."),
        "persona-dream": ("A memory service, Chatterbox TTS, and the insightface identity gate.",
                          "Tests whether a dream changes persona state under sealed conditions — a null result is valid, and it makes no claim that dreaming helps."),
        "extractor": ("Python env and a vision/model provider for extraction.",
                      "Extracts what is present without knobs to flatter the result — not that the source is complete."),
        "dogpile": ("Search API keys and network access.",
                    "Reports what the sweep reached across sources — not exhaustive coverage."),
        "watch": ("A screen-capture pipeline and frame storage.",
                  "Records what was on screen at a moment — not intent."),
        "scillm": ("A container runtime and provider credentials (OAuth).",
                   "Normalizes provider access behind one contract — it does not itself reason or plan."),
        "debugger": ("Python env with the target process reachable for breakpoints.",
                     "Shows real runtime state at a paused frame — it does not fix the bug for you."),
        "memory": ("Public abstract only — the graph-memory operator and memory data are private.",
                   "Describes the architecture boundary: ArangoDB documents and graph edges, Qdrant vectors, and memory-first routing. It does not expose private repository contents or records."),
        "sparta-explorer": ("Public overview only — the system and its evidence are private.",
                            "A public methodology overview; the implementation and evidence are under NDA."),
    }

    for p in content["projects"]:
        v = vis.get(p["slug"], {})
        a = project_area.get(p["slug"], {})
        _req, _bound = SCOUT_META.get(p["slug"], ("", ""))
        skill = SLUG_TO_SKILL.get(p["slug"], p["slug"])
        desc, body = ("", "") if p["slug"] in NO_PROJECT_SKILL_BODY else _skill_text(skill)
        project_body = " ".join(
            part for part in (p.get("question", ""), p.get("why", ""), _bound) if part
        )
        docs.append(
            {
                "id": f"project:{p['slug']}",
                "type": "project",
                "slug": p["slug"],
                "name": p["name"],
                "area": a.get("title", ""),
                "areaId": a.get("id", ""),
                "lens": a.get("lens", ""),
                "aliases": a.get("aliases", []) + SCOUT.get(p["slug"], []),
                "disciplines": a.get("disciplines", []),
                "question": p.get("question", ""),
                "summary": v.get("abstract") or p.get("blurb", ""),
                "body": (project_body if p["slug"] in NO_PROJECT_SKILL_BODY else f"{desc} {body}").strip(),
                "href": v.get("href") or p.get("href"),
                "visibility": v.get("visibility", "public"),
                "evidenceAccess": v.get("evidence_access", "source"),
                # Honest scout-readiness (webgpt Criterion 4). NONE claims
                # "run-now": that requires a passing fresh-clone quickstart
                # receipt, which no project has yet. Public working code needs
                # named infra/credentials -> setup-required; private -> abstract.
                "scoutState": (
                    "abstract-only" if v.get("visibility", "public") != "public"
                    else "setup-required"
                ),
                "requirements": _req,
                "boundary": _bound,
            }
        )

    # Skills: lighter docs, findable by name + their area's aliases so a
    # capability query surfaces the contracts behind it.
    area_by_discipline: dict[str, dict] = {}
    for a in rmap["areas"]:
        for d in a["disciplines"]:
            area_by_discipline[d] = a
    for s in inventory.get("skills", []):
        desc, body = _skill_text(s["n"])  # public SKILL.md content
        docs.append(
            {
                "id": f"skill:{s['n']}",
                "type": "skill",
                "name": s["n"],
                "category": s.get("c", ""),
                "sanity": bool(s.get("s")),
                "summary": desc,
                "body": body[:1000],  # shorter cap so 338 skills don't bloat
                "href": f"https://github.com/grahama1970/agent-skills/blob/main/skills/{s['n']}/SKILL.md",
            }
        )

    out = {
        "schema": "grahama.catalog.v1",
        "sourceCommit": _git_commit(),
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
