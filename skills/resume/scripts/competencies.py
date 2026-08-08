"""Competency evidence for resume tailoring, derived from the real repo.

A resume is customised per employer, so the question "which competencies do I
lead with for THIS posting?" gets asked repeatedly. Answering it from memory
invites drift and invented claims. This command answers it from evidence that
already exists and is already governed:

    skills/project-taxonomy/references/disciplines.yml

That file is the canonical closed vocabulary (18 disciplines) plus an explicit,
fail-closed per-skill mapping, maintained by /project-taxonomy. This script
never re-derives or guesses a discipline; it aggregates what that registry
already asserts, so a competency claim is always backed by a countable set of
named skills.

Two modes:

    report            rank every discipline by demonstrated skill count
    match POSTING     rank disciplines by overlap with a job posting, so the
                      tailored resume leads with what the employer asked for

Both emit JSON. `match` is deterministic term overlap over the posting text —
it reports what the posting actually says, and makes no claim about any
employer's proprietary ranking model.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer
import yaml
from loguru import logger

REPO = Path(__file__).resolve().parents[3]
REGISTRY = REPO / "skills" / "project-taxonomy" / "references" / "disciplines.yml"

app = typer.Typer(add_completion=False, no_args_is_help=True)

# Terms that carry no discriminating signal in a job posting.
_STOP = frozenset(
    """the a an and or of for in to with on at by is are be as from that this we you your our
    will their its it they have has can may must should would could about across into over
    per via than then when what which who whom whose how why all any both each more most other
    some such only own same so too very just also if but not no nor own s t don now""".split()
)


@dataclass(frozen=True, slots=True)
class Registry:
    """The canonical discipline vocabulary and its per-skill mapping."""

    vocabulary: dict[str, str]
    skills: dict[str, list[str]]

    @classmethod
    def load(cls, path: Path) -> "Registry":
        if not path.is_file():
            raise FileNotFoundError(f"discipline registry not found: {path}")
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        vocab = data.get("vocabulary") or {}
        skills = data.get("skills") or {}
        if not vocab or not skills:
            raise ValueError(f"discipline registry is missing vocabulary/skills: {path}")
        unknown = {d for ds in skills.values() for d in ds} - set(vocab)
        if unknown:
            raise ValueError(f"registry maps skills to unknown disciplines: {sorted(unknown)}")
        return cls(vocab, skills)

    def counts(self) -> Counter:
        """Skills per discipline, primary or secondary."""
        return Counter(d for ds in self.skills.values() for d in ds)

    def primary_counts(self) -> Counter:
        """Skills per discipline where it is the primary (first) label."""
        return Counter(ds[0] for ds in self.skills.values() if ds)

    def members(self, discipline: str) -> list[str]:
        return sorted(name for name, ds in self.skills.items() if discipline in ds)


def terms(text: str) -> set[str]:
    """Lowercased word set with stop words and very short tokens removed."""
    return {w for w in re.findall(r"[a-z0-9+#.-]{3,}", text.lower())} - _STOP


def discipline_terms(reg: Registry, discipline: str) -> set[str]:
    """Signal for one discipline: its prose description plus its skill names."""
    words = terms(reg.vocabulary.get(discipline, ""))
    words |= {w for name in reg.members(discipline) for w in terms(name.replace("-", " "))}
    words |= terms(discipline.replace("-", " "))
    return words


def build_report(reg: Registry) -> dict[str, Any]:
    counts, primary = reg.counts(), reg.primary_counts()
    rows = []
    for name in reg.vocabulary:
        members = reg.members(name)
        rows.append(
            {
                "discipline": name,
                "skills": counts.get(name, 0),
                "primary_skills": primary.get(name, 0),
                "share_pct": round(100 * counts.get(name, 0) / max(len(reg.skills), 1), 1),
                "examples": members[:6],
            }
        )
    rows.sort(key=lambda r: (-r["skills"], r["discipline"]))
    return {
        "schema": "resume.competency_evidence.v1",
        "source": str(REGISTRY.relative_to(REPO)),
        "skills_mapped": len(reg.skills),
        "disciplines": rows,
    }


def build_match(reg: Registry, posting: str) -> dict[str, Any]:
    """Rank disciplines by how much of the posting's language they cover."""
    post = terms(posting)
    if not post:
        raise ValueError("posting text produced no searchable terms")
    counts = reg.counts()
    rows = []
    for name in reg.vocabulary:
        overlap = sorted(discipline_terms(reg, name) & post)
        rows.append(
            {
                "discipline": name,
                "matched_terms": overlap,
                "match_count": len(overlap),
                "skills": counts.get(name, 0),
                # Evidence-weighted: what the posting asks for, scaled by how
                # much of it this resume can actually back with real skills.
                "score": round(len(overlap) * (1 + counts.get(name, 0) / 25), 2),
            }
        )
    rows.sort(key=lambda r: (-r["score"], -r["match_count"], r["discipline"]))
    leading = [r["discipline"] for r in rows[:4] if r["match_count"]]
    return {
        "schema": "resume.competency_match.v1",
        "source": str(REGISTRY.relative_to(REPO)),
        "posting_terms": len(post),
        "lead_with": leading,
        "disciplines": rows,
    }


@app.command()
def report(registry: Path = typer.Option(REGISTRY, "--registry")) -> None:
    """Rank demonstrated competencies by evidence in the skills catalog."""
    try:
        payload = build_report(Registry.load(registry))
    except (OSError, ValueError) as exc:
        logger.error("competency report failed: {}", exc)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(payload, indent=2))


@app.command()
def match(
    posting: Path = typer.Argument(..., help="Job posting text or Markdown"),
    registry: Path = typer.Option(REGISTRY, "--registry"),
) -> None:
    """Rank competencies against one posting, to tailor which lead the resume."""
    try:
        if not posting.is_file():
            raise FileNotFoundError(f"posting file does not exist: {posting}")
        payload = build_match(Registry.load(registry), posting.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.error("competency match failed: {}", exc)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(payload, indent=2))


if __name__ == "__main__":
    app()
