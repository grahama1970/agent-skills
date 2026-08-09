"""Audit a resume and its public surfaces the way an automated screener reads them.

A resume is read by software before a person sees it, and 2026 screening stacks
reject on two patterns that have nothing to do with whether the work was real:

1. A skills list naming capabilities the experience bullets never demonstrate.
   Workday's AI layer flags this hardest; it reads as padding.
2. Public surfaces telling different stories — a LinkedIn profile, a resume, and
   a personal site that disagree read as a verification risk.

Both are mechanical, so they are checked mechanically instead of by eye:

    support           every declared competency appears in a bullet or the prose
    surfaces URL      the machine-readable surfaces a crawler or agent will fetch

Both exit non-zero on failure so they can gate a send. Neither judges whether the
resume is good; they check only that it cannot be dismissed for a reason that is
purely structural.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer
from loguru import logger

REPO = Path(__file__).resolve().parents[3]
DEFAULT_RESUME = REPO / "RESUME.md"

app = typer.Typer(add_completion=False, no_args_is_help=True)

# Section that declares capabilities; the name has changed over time.
SKILLS_HEADINGS = ("CORE COMPETENCIES", "TOP SKILLS", "SKILLS")
# Rendered-only material must not count as evidence for a claim.
WEB_ONLY_HEADINGS = ("DEEPER DETAIL",)


@dataclass(frozen=True, slots=True)
class Split:
    """A resume divided into what it claims and what it demonstrates."""

    claims: list[str]
    evidence: str

    @classmethod
    def from_markdown(cls, md: str) -> "Split":
        claims: list[str] = []
        evidence: list[str] = []
        section = ""
        for line in md.splitlines():
            if line.startswith("## "):
                section = line[3:].strip().upper()
                continue
            if section.startswith(WEB_ONLY_HEADINGS):
                continue
            if section.startswith(SKILLS_HEADINGS):
                if line.startswith("- "):
                    body = line[2:]
                    # "Cluster: term, term" — the cluster label is presentation.
                    body = body.split(":", 1)[1] if ":" in body else body
                    claims += [t.strip() for t in body.split(",") if t.strip()]
                continue
            evidence.append(line)
        return cls(claims, "\n".join(evidence).lower())


def supported(term: str, evidence: str) -> bool:
    """A term counts as demonstrated only if the evidence text actually says it.

    Whole-phrase match first, then every significant word: "Regression Gates" is
    satisfied by prose containing both words, but not by silence.
    """
    low = term.lower()
    if low in evidence:
        return True
    words = [w for w in re.findall(r"[a-z0-9+#]+", low) if len(w) > 3]
    return bool(words) and all(w in evidence for w in words)


def audit_support(md: str) -> dict[str, Any]:
    split = Split.from_markdown(md)
    if not split.claims:
        raise ValueError("no competency section found; nothing to audit")
    unsupported = [t for t in split.claims if not supported(t, split.evidence)]
    return {
        "schema": "resume.screening_support.v1",
        "claims": len(split.claims),
        "unsupported": unsupported,
        "verdict": "PASS" if not unsupported else "FAIL",
        "why": (
            "Every declared competency appears in the experience text."
            if not unsupported
            else "These competencies are claimed but never demonstrated; screeners read that as padding."
        ),
    }


def _fetch(url: str, timeout: int = 20) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "resume-screening-audit"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except Exception as exc:  # noqa: BLE001 — a probe failure is a finding, not a crash
        logger.warning("fetch failed for {}: {}", url, exc)
        return 0, ""


def audit_surfaces(base: str) -> dict[str, Any]:
    """Check what a crawler or agent gets when it reads the site cold."""
    base = base.rstrip("/")
    checks: list[dict[str, Any]] = []

    for path, needle, why in (
        ("/robots.txt", "Sitemap:", "crawlers need the sitemap pointer"),
        ("/sitemap.xml", "<urlset", "the resume URL must be discoverable"),
        ("/llms.txt", "#", "agents fetch this before parsing HTML"),
        ("/resume", "resume:link:pdf", "the resume page itself"),
        ("/resume.pdf", "", "the attachable artifact"),
        ("/resume.md", "#", "the machine-diffable source"),
    ):
        status, body = _fetch(base + path)
        ok = status == 200 and (needle in body if needle else True)
        checks.append({"path": path, "status": status, "ok": ok, "why": why})

    status, home = _fetch(base + "/")
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', home, re.S)
    person = None
    for raw in blocks:
        try:
            graph = json.loads(raw).get("@graph", [])
        except json.JSONDecodeError:
            continue
        person = next((n for n in graph if n.get("@type") == "Person"), None) or person
    checks.append(
        {
            "path": "/ (schema.org Person)",
            "status": status,
            "ok": bool(person and person.get("jobTitle") and person.get("knowsAbout")),
            "why": "recruiter tooling reads structured data before prose",
            "detail": {
                "jobTitle": (person or {}).get("jobTitle"),
                "knowsAbout": len((person or {}).get("knowsAbout", [])),
            },
        }
    )
    failed = [c for c in checks if not c["ok"]]
    return {
        "schema": "resume.screening_surfaces.v1",
        "base_url": base,
        "checks": checks,
        "failed": len(failed),
        "verdict": "PASS" if not failed else "FAIL",
    }


@app.command()
def support(resume: Path = typer.Option(DEFAULT_RESUME, "--resume")) -> None:
    """Fail if any declared competency is never demonstrated in the experience."""
    try:
        if not resume.is_file():
            raise FileNotFoundError(f"resume does not exist: {resume}")
        payload = audit_support(resume.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.error("support audit failed: {}", exc)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(payload, indent=2))
    if payload["verdict"] != "PASS":
        raise typer.Exit(code=2)


@app.command()
def surfaces(base_url: str = typer.Argument("https://grahama.co")) -> None:
    """Fail if a machine reader would not find the resume surfaces it expects."""
    try:
        payload = audit_surfaces(base_url)
    except ValueError as exc:
        logger.error("surface audit failed: {}", exc)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(payload, indent=2))
    if payload["verdict"] != "PASS":
        raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
