"""Keep a LinkedIn skills section in step with the resume's declared competencies.

Screening stacks cross-check a resume against a public profile, so a profile
listing twenty skills against a resume declaring fifty reads as an inconsistency
rather than as modesty. Keeping the two aligned by hand takes roughly thirty
browser operations per run and is exactly the kind of thing that stops happening.

This drives the real, authenticated browser through /surf. It is deliberately
two-phase:

    plan            diff resume competencies against the live profile; writes nothing
    apply --confirm actually add the missing skills, then read the profile back

`plan` is the default because this edits a live professional profile. Nothing is
ever deleted: the only write is adding a skill LinkedIn's own autocomplete
resolved to a real entry in its taxonomy.

Lessons that are encoded here because doing this manually surfaced them:

* LinkedIn's autocomplete will happily return a near-miss. Typing "Observability"
  offers "Observational" first, which is a different word. A suggestion is only
  accepted when the query actually appears in it; otherwise the term is skipped
  and reported, never guessed at.
* The profile view paginates at twenty and renders newest first, so an unchanged
  count after a write does not mean the write failed. Verification reads back by
  name, not by counting rows.
* LinkedIn caps a profile at fifty skills, so the plan reports when the additions
  would exceed the cap instead of silently dropping the tail.
* Neither read proves absence: the details view exposes only its first twenty
  entries, and the add dialog offers skills the profile already holds. So a
  ledger of what this tool has added is kept on disk, and a second run skips
  those rather than duplicating them.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer
from loguru import logger

REPO = Path(__file__).resolve().parents[3]
SURF = REPO / "skills" / "surf" / "run.sh"
DEFAULT_RESUME = REPO / "RESUME.md"
SKILLS_URL = "https://www.linkedin.com/in/grahamanderson/details/skills/"
PROFILE_URL = "https://www.linkedin.com/in/grahamanderson/"
LINKEDIN_SKILL_CAP = 50
# Durable record of what this tool has added. The profile view exposes only its
# first page and LinkedIn's add dialog offers skills the profile already holds,
# so neither read proves absence. This file is the one dependable memory, and it
# is what makes a second run idempotent instead of duplicating work.
LEDGER = REPO / "skills" / "resume" / "local" / "linkedin-synced.json"

SKILLS_HEADINGS = ("CORE COMPETENCIES", "TOP SKILLS", "SKILLS")
# Resume phrasing that LinkedIn has no entry for, mapped to the taxonomy name it
# does index. Verified by probing LinkedIn's own autocomplete, not guessed: it
# has no "AI Observability" or "Regression Gates", but it does have "MLOps" and
# "Regression Testing". Without this the sync silently drops half the resume's
# vocabulary from the profile a recruiter actually searches.
TAXONOMY_ALIASES = {
    "AI Observability": "MLOps",
    "Drift Detection": "Anomaly Detection",
    "Regression Gates": "Regression Testing",
    "Agentic Evaluation Harnesses": "Model Evaluation",
    "Adversarial/Blind Testing": "AI Safety",
    "Guardrails": "Responsible AI",
    "Model Fine-Tuning": "Fine Tuning",
    "Hybrid BM25 + Vector Search": "Semantic Search",
}
WEB_ONLY_HEADINGS = ("DEEPER DETAIL",)

app = typer.Typer(add_completion=False, no_args_is_help=True)


class SyncError(RuntimeError):
    """Stable failure for the LinkedIn sync seam."""


def normalise(term: str) -> str:
    """Comparison key that ignores punctuation and LinkedIn's parenthetical suffixes."""
    return re.sub(r"[^a-z0-9]", "", term.lower())


def resume_competencies(md: str) -> list[str]:
    """Competency terms the resume declares, excluding web-only sections."""
    out: list[str] = []
    section = ""
    for line in md.splitlines():
        if line.startswith("## "):
            section = line[3:].strip().upper()
            continue
        if section.startswith(WEB_ONLY_HEADINGS) or not section.startswith(SKILLS_HEADINGS):
            continue
        if line.startswith("- "):
            body = line[2:]
            body = body.split(":", 1)[1] if ":" in body else body
            out += [t.strip() for t in body.split(",") if t.strip()]
    return out


def surf(*args: str, timeout: int = 180) -> str:
    """One /surf call. Composition point — this script never drives a browser itself."""
    if not SURF.is_file():
        raise SyncError(f"surf skill not found at {SURF}")
    proc = subprocess.run(
        ["bash", str(SURF), *args], capture_output=True, text=True, timeout=timeout
    )
    if proc.returncode != 0:
        raise SyncError(f"surf {args[0]} failed: {proc.stderr.strip()[-200:]}")
    return proc.stdout.strip()


def surf_js(tab: str, expression: str) -> Any:
    """Evaluate one expression in the live tab and decode surf's JSON envelope."""
    raw = surf("js", "--tab-id", tab, expression)
    line = raw.splitlines()[-1] if raw else ""
    try:
        decoded = json.loads(line)
    except json.JSONDecodeError as exc:
        raise SyncError(f"unreadable surf js result: {line[:160]}") from exc
    if isinstance(decoded, str):
        try:
            return json.loads(decoded)
        except json.JSONDecodeError:
            return decoded
    return decoded


@dataclass(frozen=True, slots=True)
class Plan:
    declared: list[str]
    present: list[str]
    missing: list[str]
    over_cap: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "resume.linkedin_sync_plan.v1",
            "declared": len(self.declared),
            "present_on_profile": len(self.present),
            "missing": self.missing,
            "would_exceed_cap_by": self.over_cap,
        }


def _rendered_skills(tab: str) -> list[str]:
    names = surf_js(
        tab,
        "JSON.stringify(Array.from(document.querySelectorAll('a[aria-label^=\"Edit \"]'))"
        ".map(function(a){return a.getAttribute('aria-label').replace('Edit ','')"
        ".replace(' skill','')}))",
    )
    return names if isinstance(names, list) else []


def live_skills(tab: str, max_pages: int = 12) -> list[str]:
    """Every skill on the profile, not just the first rendered page.

    The list paginates at twenty and renders newest first. Reading only what is
    rendered makes long-standing skills look missing and would have this script
    re-add skills the profile already has, so it pages until the set stops
    growing rather than trusting one read.
    """
    surf("go", SKILLS_URL, "--tab-id", tab)
    time.sleep(5)
    seen: list[str] = []
    for _ in range(max_pages):
        for name in _rendered_skills(tab):
            if name not in seen:
                seen.append(name)
        grew = surf_js(
            tab,
            "(function(){var b=Array.from(document.querySelectorAll('button,a')).filter(function(e){"
            "return /show more|show all/i.test((e.textContent||'').trim())})[0];"
            "if(!b)return 'END';b.click();return 'MORE';})()",
        )
        if grew != "MORE":
            surf_js(
                tab,
                "(function(){window.scrollTo(0,document.body.scrollHeight);return 'ok';})()",
            )
            time.sleep(2)
            before = len(seen)
            for name in _rendered_skills(tab):
                if name not in seen:
                    seen.append(name)
            if len(seen) == before:
                break
        time.sleep(3)
    if not seen:
        raise SyncError("could not read the profile's skill list")
    return seen


def profile_text(tab: str) -> str:
    """Raw text of the main profile.

    The details view exposes only its first page, so a skill held for years can
    look absent there. The profile page carries the rest, and membership is
    checked against this text as well before anything is called missing —
    otherwise the sync would re-add skills the profile already has.
    """
    surf("go", PROFILE_URL, "--tab-id", tab)
    time.sleep(6)
    return surf("text", "--tab-id", tab, timeout=180).lower()


def load_ledger() -> list[str]:
    if not LEDGER.is_file():
        return []
    try:
        return list(json.loads(LEDGER.read_text(encoding="utf-8")).get("added", []))
    except (OSError, ValueError):
        logger.warning("ledger unreadable; treating as empty: {}", LEDGER)
        return []


def save_ledger(names: list[str]) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(
        json.dumps({"schema": "resume.linkedin_ledger.v1", "added": sorted(set(names))}, indent=1)
        + "\n",
        encoding="utf-8",
    )


def build_plan(resume: Path, tab: str) -> Plan:
    declared = resume_competencies(resume.read_text(encoding="utf-8"))
    if not declared:
        raise SyncError("resume declares no competencies; nothing to sync")
    present = live_skills(tab)
    have = {normalise(p) for p in present}
    text = profile_text(tab)

    def on_profile(term: str) -> bool:
        key = normalise(term)
        if key in have or any(key in h or h in key for h in have if h):
            return True
        # Second, independent source: the profile's own rendered text.
        return term.lower() in text

    synced = {normalise(x) for x in load_ledger()}

    def already_synced(term: str) -> bool:
        key = normalise(term)
        # LinkedIn stores canonical names ("React.js" for "React"), so exact
        # equality would re-offer a skill the profile already holds.
        return key in synced or any(key in x or x in key for x in synced if x)

    missing = [d for d in declared if not on_profile(d) and not already_synced(d)]
    over = max(0, len(present) + len(missing) - LINKEDIN_SKILL_CAP)
    return Plan(declared, present, missing, over)


def add_skill(tab: str, term: str) -> str | None:
    """Add one skill, accepting only a suggestion that actually matches the query.

    Returns the canonical name LinkedIn stored, or None when nothing matched —
    a near-miss is skipped and reported rather than written to the profile.
    """
    surf_js(
        tab,
        "(function(){var t=Array.from(document.querySelectorAll('a,button')).filter(function(e){"
        "return ((e.getAttribute('aria-label')||e.textContent||'').trim().toLowerCase()==='add a skill')})[0];"
        "if(!t)return 'no-add';t.click();return 'ok';})()",
    )
    time.sleep(2)
    safe = term.replace("'", " ").replace("\\", " ")
    surf_js(
        tab,
        "(function(){var i=document.querySelector('input[placeholder*=\"Project Management\"]');"
        "if(!i)return 'no-input';"
        "var S=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;"
        f"S.call(i,'{safe}');i.dispatchEvent(new Event('input',{{bubbles:true}}));return 'typed';}})()",
    )
    time.sleep(3)
    head = safe.lower().split(" ")[0]
    picked = surf_js(
        tab,
        "(function(){var o=Array.from(document.querySelectorAll('[role=option]'));"
        f"var m=o.filter(function(x){{return x.textContent.toLowerCase().indexOf('{head}')>=0}})[0];"
        "if(!m)return 'NO_MATCH';m.click();return m.textContent.trim();})()",
    )
    time.sleep(2)
    if picked == "NO_MATCH":
        surf("key", "Escape", "--tab-id", tab)
        time.sleep(1)
        return None
    surf_js(
        tab,
        "(function(){var b=Array.from(document.querySelectorAll('button')).filter(function(e){"
        "return e.textContent.trim()==='Save'});if(!b.length)return 'no-save';"
        "b[b.length-1].click();return 'saved';})()",
    )
    time.sleep(4)
    return str(picked)


@app.command()
def plan(
    resume: Path = typer.Option(DEFAULT_RESUME, "--resume"),
    tab: str = typer.Option(..., "--tab-id", help="surf tab already signed in to LinkedIn"),
) -> None:
    """Report which declared competencies are missing from the profile. Writes nothing."""
    try:
        payload = build_plan(resume, tab).as_dict()
    except (OSError, SyncError) as exc:
        logger.error("linkedin sync plan failed: {}", exc)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(payload, indent=2))


@app.command()
def apply(
    resume: Path = typer.Option(DEFAULT_RESUME, "--resume"),
    tab: str = typer.Option(..., "--tab-id", help="surf tab already signed in to LinkedIn"),
    confirm: bool = typer.Option(False, "--confirm", help="Required: this edits a live profile"),
    limit: int = typer.Option(25, "--limit", help="Maximum skills to add in one run"),
) -> None:
    """Add the missing competencies to the profile, then read the profile back."""
    if not confirm:
        logger.error("refusing to edit a live profile without --confirm")
        raise typer.Exit(code=1)
    try:
        current = build_plan(resume, tab)
        added: list[dict[str, str]] = []
        skipped: list[str] = []
        for term in current.missing[:limit]:
            canonical = add_skill(tab, TAXONOMY_ALIASES.get(term, term))
            (added.append({"requested": term, "stored_as": canonical}) if canonical
             else skipped.append(term))
        after = live_skills(tab)
        have = {normalise(x) for x in after}
        # Read back by name: the view paginates, so a row count proves nothing.
        unverified = [
            a["stored_as"] for a in added
            if a["stored_as"] and normalise(a["stored_as"]) not in have
        ]
        save_ledger(load_ledger() + [a["stored_as"] for a in added if a["stored_as"]])
        payload = {
            "schema": "resume.linkedin_sync_receipt.v1",
            "added": added,
            "skipped_no_match": skipped,
            "unverified_after_readback": unverified,
            "verdict": "PASS" if not unverified else "PARTIAL",
        }
    except (OSError, SyncError) as exc:
        logger.error("linkedin sync failed: {}", exc)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(payload, indent=2))
    if payload["verdict"] != "PASS":
        raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
