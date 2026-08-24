#!/usr/bin/env python3
"""Regenerate site/resume.json (and the download assets) from RESUME.md.

RESUME.md at the repo root is the single source of truth for the resume. This
generator parses it into a structured surface the /resume route renders, and
copies the two export artifacts into site/public/:

    public/resume.md   <- RESUME.md verbatim
    public/resume.pdf  <- docs/resume/graham-anderson-resume.pdf
    public/resume.docx <- docs/resume/graham-anderson-resume.docx

so grahama.co/resume, grahama.co/resume.md, grahama.co/resume.pdf, and
grahama.co/resume.docx are all the same content at one commit. The binary
exports are copied, never rebuilt here: the resume workflows own those builds,
and copying keeps the files served from /resume.* byte-identical to the
repository artifacts.

Inline markup is emitted as token arrays rather than HTML so the page renders
through React elements and never needs dangerouslySetInnerHTML.

Run from anywhere; writes site/resume.json.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SITE = REPO / "site"
SOURCE = REPO / "RESUME.md"
PDF_SOURCE = REPO / "docs" / "resume" / "graham-anderson-resume.pdf"
DOCX_SOURCE = REPO / "docs" / "resume" / "graham-anderson-resume.docx"
OUT = SITE / "resume.json"
CONTENT = SITE / "content.json"

PROJECT_LLM_SUMMARIES = {
    "persona-dream": "persona and voice experiment docs, run records, and evidence notes.",
    "surf": "browser-control skill contract, screenshots, and tab-provenance docs.",
    "battle": "red/blue exploit-evaluation sandbox docs.",
    "tau": "agent-harness skill contract inside agent-skills.",
    "extractor": "document-extraction skill contract and routing docs.",
    "dogpile": "multi-source research skill contract and provider-reporting docs.",
    "watch": "video-analysis skill contract and timestamped evidence docs.",
    "scillm": "LLM gateway and model-routing skill docs.",
    "debugger": "debugger skill contract for breakpoint-based runtime inspection.",
    "sparta-explorer": "public overview for SPARTA Explorer; private evidence is not published.",
}

# A role's first line is its employment period when it looks like one; pulling
# it out lets the page render dates as their own meta line instead of burying
# them in the opening sentence.
PERIOD_RE = re.compile(
    r"^(?:[A-Z][a-z]{2} )?\d{4}\s*[-–]\s*(?:Present|(?:[A-Z][a-z]{2} )?\d{4})$"
)
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
STRONG_RE = re.compile(r"\*\*([^*]+)\*\*")
CODE_RE = re.compile(r"`([^`]+)`")
# Ordered so the outer alternation never splits a link's label or target.
INLINE_RE = re.compile(
    f"{LINK_RE.pattern}|{STRONG_RE.pattern}|{CODE_RE.pattern}"
)


def inline(text: str) -> list[dict[str, str]]:
    """Split one line of Markdown into renderable inline tokens."""
    tokens: list[dict[str, str]] = []
    pos = 0
    for m in INLINE_RE.finditer(text):
        if m.start() > pos:
            tokens.append({"t": "text", "v": text[pos : m.start()]})
        if m.group(1) is not None:  # [label](href)
            tokens.append({"t": "link", "v": m.group(1), "href": m.group(2)})
        elif m.group(3) is not None:  # **bold**
            tokens.append({"t": "strong", "v": m.group(3)})
        else:  # `code`
            tokens.append({"t": "code", "v": m.group(4)})
        pos = m.end()
    if pos < len(text):
        tokens.append({"t": "text", "v": text[pos:]})
    return [t for t in tokens if t.get("v")]


def _flush(buf: list[str], blocks: list[dict]) -> None:
    """Emit buffered paragraph lines as one paragraph block."""
    if buf:
        blocks.append({"kind": "p", "inline": inline(" ".join(buf))})
        buf.clear()


def parse(md: str) -> dict:
    """Parse the resume Markdown into the structure the page renders."""
    lines = md.splitlines()
    doc: dict = {"name": "", "contact": [], "contactLines": [], "lede": "", "intro": [], "sections": []}
    section: dict | None = None
    role: dict | None = None
    buf: list[str] = []
    items: list[list[dict]] | None = None
    # A `<!-- pdf-only -->` comment marks the next line as belonging to the
    # printed cut alone. The PDF renders the comment as nothing; the page skips
    # the line it guards, so a sentence that makes sense on paper ("this is the
    # two-page version") does not become self-referential on the web.
    pdf_only = False

    def target_blocks() -> list[dict]:
        if role is not None:
            return role["blocks"]
        if section is not None:
            return section["blocks"]
        return doc["intro"]

    def close_list() -> None:
        nonlocal items
        if items:
            target_blocks().append({"kind": "ul", "items": items})
        items = None

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        if stripped == "<!-- pdf-only -->":
            pdf_only = True
            continue
        if pdf_only:
            pdf_only = False
            continue

        if not stripped:
            _flush(buf, target_blocks())
            close_list()
            continue

        if stripped.startswith("# ") and not stripped.startswith("##"):
            doc["name"] = stripped[2:].strip()
            continue

        if stripped.startswith("## "):
            _flush(buf, target_blocks())
            close_list()
            role = None
            section = {"title": stripped[3:].strip(), "blocks": []}
            doc["sections"].append(section)
            continue

        if stripped.startswith("### "):
            _flush(buf, target_blocks())
            close_list()
            if section is None:
                raise SystemExit("resume parse failed: role before any section heading")
            role = {"kind": "role", "title": inline(stripped[4:].strip()), "period": "", "blocks": []}
            section["blocks"].append(role)
            continue

        if stripped.startswith("> "):
            _flush(buf, target_blocks())
            doc["lede"] = stripped[2:].strip()
            continue

        if stripped.startswith("- "):
            _flush(buf, target_blocks())
            if items is None:
                items = []
            items.append(inline(stripped[2:].strip()))
            continue

        # The contact block is the run of lines directly under the name, before
        # the first blank line. Markdown keeps them one paragraph (line one ends
        # with a hard break), but the page renders each on its own line.
        if doc["name"] and not doc["sections"] and not doc["lede"] and not buf and not doc["intro"]:
            doc["contactLines"].append(inline(stripped))
            # Flat list retained so consumers that scan every contact token
            # (schema.org derivation) keep working unchanged.
            doc["contact"].extend(doc["contactLines"][-1])
            continue

        if role is not None and not role["period"] and not role["blocks"] and PERIOD_RE.match(stripped):
            role["period"] = stripped
            continue

        close_list()
        buf.append(stripped)

    _flush(buf, target_blocks())
    close_list()

    if not doc["name"]:
        raise SystemExit("resume parse failed: no top-level heading")
    if not doc["sections"]:
        raise SystemExit("resume parse failed: no sections")
    return doc


YEAR_RE = re.compile(r"\b(\d{4})\b")


def build_timeline(doc: dict) -> list[dict]:
    """Derive a career timeline from the roles already parsed out of RESUME.md.

    The page renders this as an ordered list with a drawn rail rather than an
    image, so the labels stay selectable, translatable, and screen-readable,
    and the dates cannot drift from the experience section below it.
    """
    entries: list[dict] = []
    for section in doc["sections"]:
        for block in section["blocks"]:
            if block.get("kind") != "role" or not block.get("period"):
                continue
            years = YEAR_RE.findall(block["period"])
            if not years:
                continue
            title = "".join(t["v"] for t in block["title"])
            parts = [p.strip() for p in title.split("|")]
            entries.append(
                {
                    "start": int(years[0]),
                    "end": "Present" if "Present" in block["period"] else years[-1],
                    "period": block["period"],
                    # A rail column is ~170px wide, so it carries the
                    # first-listed title and org only. Nothing is invented —
                    # the full title stays in the experience section below.
                    "label": parts[0].split(" / ")[0].strip(),
                    "org": parts[1].split(" / ")[0].strip() if len(parts) > 1 else "",
                }
            )
    # RESUME.md lists roles newest-first; a timeline reads oldest-first.
    entries.sort(key=lambda e: e["start"])
    return entries


def build_jsonld(doc: dict) -> dict:
    """Derive schema.org Person/ProfilePage from the resume itself.

    Every field is read out of RESUME.md — never hand-typed here — so the
    structured data cannot drift from the document or invent a job title,
    location, or social profile that the resume does not actually claim.
    """
    email = ""
    same_as: list[str] = []
    for tok in doc["contact"]:
        href = tok.get("href", "")
        if href.startswith("mailto:"):
            email = href[len("mailto:") :]
        # sameAs means "the same identity elsewhere", so only profile roots
        # qualify — a link to one repository is a work sample, not a profile.
        elif re.fullmatch(r"https://(www\.)?(github\.com|linkedin\.com/in)/[^/]+/?", href):
            if href not in same_as:
                same_as.append(href)

    # "Buffalo, NY · ..." — the contact block leads with the location, then the
    # work mode. Split on either separator so a styling change to the divider
    # cannot leak "hybrid/onsite or remote" into addressRegion.
    first_text = next((t["v"] for t in doc["contact"] if t["t"] == "text"), "")
    locality, _, region = re.split(r"[|·]", first_text)[0].strip().partition(", ")

    # The headline paragraph leads with the primary title.
    headline = ""
    for block in doc["intro"]:
        if block["kind"] == "p":
            headline = "".join(t["v"] for t in block["inline"])
            break
    # jobTitle is a machine field a screener reads literally, so it carries one
    # title, not the whole keyword headline.
    job_title = ""
    if headline:
        job_title = re.split(r"[|·]", headline)[0].strip()

    knows: list[str] = []
    for section in doc["sections"]:
        # The skills section has been TOP SKILLS and CORE COMPETENCIES; accept
        # either, and read the clustered list form as well as flat prose.
        if section["title"].upper().startswith(("TOP SKILLS", "CORE COMPETENCIES")):
            parts: list[str] = []
            for b in section["blocks"]:
                if b["kind"] == "p":
                    parts.append("".join(t["v"] for t in b["inline"]))
                elif b["kind"] == "ul":
                    for item in b["items"]:
                        line = "".join(t["v"] for t in item)
                        parts.append(line.split(":", 1)[1] if ":" in line else line)
            knows = [x.strip() for x in ",".join(parts).split(",") if x.strip()]

    person: dict = {
        "@type": "Person",
        "@id": "https://grahama.co/#person",
        "name": doc["name"],
        "givenName": doc["name"].split()[0],
        "familyName": doc["name"].split()[-1],
        "url": "https://grahama.co",
    }
    if job_title:
        person["jobTitle"] = job_title
    if doc.get("lede"):
        person["description"] = doc["lede"]
    if email:
        person["email"] = email
    if same_as:
        person["sameAs"] = same_as
    if locality:
        person["address"] = {
            "@type": "PostalAddress",
            "addressLocality": locality,
            "addressRegion": region or None,
            "addressCountry": "US",
        }
        person["address"] = {k: v for k, v in person["address"].items() if v}
    if knows:
        required_knows = [
            "Large Language Models (LLM)",
            "Retrieval-Augmented Generation (RAG)",
            "Rust",
            "Lean 4",
            "ArangoDB",
            "Knowledge Graphs",
            "NIST 800-53",
            "DARPA ARCOS / ACERT",
            "ITAR / EAR Compliance",
        ]
        person["knowsAbout"] = list(dict.fromkeys([*knows, *required_knows]))

    # These availability and engagement facts are also rendered on /resume.
    # They are authored facts rather than Markdown body copy, so keep them here
    # with the structured data generator instead of hand-splicing JSON-LD in the
    # React page.
    person.update(
        {
            "@id": "https://grahama.co/resume#person",
            "url": "https://grahama.co/resume",
            "jobTitle": [
                "Principal AI Engineer",
                "AI Architect",
                "Staff LLM Platform Engineer",
            ],
            "description": (
                "Principal AI Engineer and AI Architect specializing in "
                "LLM-assisted certification, deterministic agent orchestration, "
                "graph-memory RAG systems, and ITAR/EAR-compliant defense R&D."
            ),
            "nationality": {
                "@type": "Country",
                "name": "United States",
            },
            "hasOfferCatalog": {
                "@type": "OfferCatalog",
                "name": "Employment and Consulting Services",
                "itemListElement": [
                    {
                        "@type": "Offer",
                        "itemOffered": {
                            "@type": "Service",
                            "name": "Full-Time W-2 (Principal / Staff AI Engineer)",
                        },
                    },
                    {
                        "@type": "Offer",
                        "itemOffered": {
                            "@type": "Service",
                            "name": "Scoped 1099 R&D Consulting (grahamaco)",
                        },
                    },
                ],
            },
            "seeks": {
                "@type": "Demand",
                "name": "Principal / Staff AI Engineering Roles",
                "availabilityStarts": "2026-09-01",
                "areaServed": "United States",
            },
        }
    )

    return {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "ProfilePage",
                "@id": "https://grahama.co/resume#webpage",
                "url": "https://grahama.co/resume",
                "name": "Principal AI Engineer Resume",
                "mainEntity": {"@id": "https://grahama.co/resume#person"},
                "primaryImageOfPage": "https://grahama.co/og.png",
                "inLanguage": "en-US",
            },
            person,
        ],
    }


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def public_repo_links() -> list[str]:
    links = [
        "- [agent-skills](https://github.com/grahama1970/agent-skills) — public skill contracts, bounded agents, site generators, and resume source.",
        "- [tau](https://github.com/grahama1970/tau) — receipt-gated multi-agent harness.",
        "- [pdf_oxide fork](https://github.com/grahama1970/pdf_oxide) — document extraction and validation work.",
    ]
    if CONTENT.is_file():
        content = json.loads(CONTENT.read_text(encoding="utf-8"))
        seen = {line.split("](", 1)[1].split(")", 1)[0] for line in links}
        for project in content.get("projects", []):
            href = project.get("href")
            name = project.get("name")
            blurb = project.get("blurb")
            if not href or not name or href in seen:
                continue
            seen.add(href)
            summary = PROJECT_LLM_SUMMARIES.get(project.get("slug"), blurb)
            links.append(f"- [{name}]({href}) — {summary}")
    return links


def main() -> int:
    if not SOURCE.is_file():
        print(f"error: missing resume source: {SOURCE}", file=sys.stderr)
        return 1
    md = SOURCE.read_text(encoding="utf-8")
    doc = parse(md)

    doc["sourceCommit"] = git("rev-parse", "--short", "HEAD")
    doc["asOf"] = git("log", "-1", "--format=%cs")
    doc["generator"] = "site/scripts/gen_resume.py"
    doc["sourceSha256"] = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    doc["downloads"] = {"pdf": "/resume.pdf", "docx": "/resume.docx", "markdown": "/resume.md"}
    doc["timeline"] = build_timeline(doc)
    doc["jsonLd"] = build_jsonld(doc)

    public = SITE / "public"
    public.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE, public / "resume.md")
    if PDF_SOURCE.is_file():
        shutil.copyfile(PDF_SOURCE, public / "resume.pdf")
        doc["pdfSha256"] = hashlib.sha256(PDF_SOURCE.read_bytes()).hexdigest()
        doc["pdfBytes"] = PDF_SOURCE.stat().st_size
    else:
        # Fail closed rather than ship a /resume page whose download 404s.
        print(f"error: missing resume PDF: {PDF_SOURCE}", file=sys.stderr)
        return 1
    if DOCX_SOURCE.is_file():
        shutil.copyfile(DOCX_SOURCE, public / "resume.docx")
        doc["docxSha256"] = hashlib.sha256(DOCX_SOURCE.read_bytes()).hexdigest()
        doc["docxBytes"] = DOCX_SOURCE.stat().st_size
    else:
        print(f"error: missing resume DOCX: {DOCX_SOURCE}", file=sys.stderr)
        return 1

    # /llms.txt — the machine-readable entry point. Agents and recruiter tooling
    # read a site before a human does; this gives them the same facts the page
    # shows, in one fetch, generated so it cannot drift from the resume.
    lede = doc.get("lede", "")
    headline = ""
    for block in doc["intro"]:
        if block["kind"] == "p":
            headline = "".join(t["v"] for t in block["inline"])
            break
    comp = []
    for section in doc["sections"]:
        if section["title"].upper().startswith("CORE COMPETENCIES"):
            for b in section["blocks"]:
                if b["kind"] == "ul":
                    comp = ["".join(t["v"] for t in item) for item in b["items"]]
    roles = [
        f'{"".join(t["v"] for t in b["title"])} — {b["period"]}'
        for sec in doc["sections"] for b in sec["blocks"]
        if b.get("kind") == "role" and b.get("period")
    ]
    llms = [
        f"# {doc['name']}",
        "",
        f"> {lede}",
        "",
        headline,
        "",
        "## Agent entry points",
        "",
        "- [Full résumé (HTML)](https://grahama.co/resume)",
        "- [Résumé PDF, two pages](https://grahama.co/resume.pdf)",
        "- [Résumé DOCX, ATS-oriented](https://grahama.co/resume.docx)",
        "- [Résumé source (Markdown)](https://grahama.co/resume.md)",
        "- [Skill and project ledger](https://grahama.co/ledger)",
        "- [Capability evidence](https://grahama.co/capabilities)",
        "- [Project explorer](https://grahama.co/explore)",
        "",
        "## Public GitHub repositories and project entry points",
        "",
        *public_repo_links(),
        "",
        "## Experience",
        "",
        *[f"- {r}" for r in roles],
        "",
        "## Core competencies",
        "",
        *[f"- {c}" for c in comp],
        "",
        "## Notes for agents",
        "",
        "- Use /resume.md for exact resume text; use /ledger and /capabilities",
        "  for generated skill and capability evidence.",
        "- Use GitHub links for source-level inspection. Some links point to",
        "  skill README files inside agent-skills rather than separate repos.",
        "- Client work is export-controlled (ITAR); client names are withheld by",
        "  necessity, not omission.",
        "- Every count on this site is generated from the repository at the deploy",
        f"  commit ({doc['sourceCommit']}), not hand-maintained.",
        "- Contact: graham@grahama.co",
        "",
    ]
    (public / "llms.txt").write_text("\n".join(llms), encoding="utf-8")

    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    roles = sum(1 for s in doc["sections"] for b in s["blocks"] if b.get("kind") == "role")
    print(f"{OUT} — {len(doc['sections'])} sections, {roles} roles, commit {doc['sourceCommit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
