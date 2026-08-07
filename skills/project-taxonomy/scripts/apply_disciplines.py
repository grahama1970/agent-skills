"""Apply the canonical research-discipline vocabulary to every skill.

Purpose: read ``references/disciplines.yml`` (closed vocabulary + explicit
per-skill mapping), then (a) write a ``disciplines:`` list into each skill's
SKILL.md frontmatter, (b) maintain a ``> **Disciplines:**`` banner line in each
skill README.md that has one, and (c) optionally delegate to the
``/memory run.sh ingest-skills`` subcommand so ``skill_descriptions`` (the single recall
surface — no parallel discipline collection) carries the labels for
``/memory recall``.

Inputs: disciplines.yml, skills/*/SKILL.md, skills/*/README.md, and for sync
the sibling /memory skill entrypoint.
Outputs: edited frontmatter/README lines (idempotent) and a JSON report on
stdout.

Failure modes (fail closed): a skill with SKILL.md but no mapping entry, a
mapping entry whose directory is missing, a discipline outside the
vocabulary, or unparseable frontmatter each abort with exit 2 and a named
error; a failed memory ingest exits 1. This module never touches ArangoDB or
Qdrant directly — persistence goes through the /memory skill surface.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import typer
import yaml
from loguru import logger

app = typer.Typer(add_completion=False, no_args_is_help=True)

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
SKILLS_ROOT = SKILL_DIR.parent
DISCIPLINES_YML = SKILL_DIR / "references" / "disciplines.yml"
BANNER_PREFIX = "> **Disciplines:**"


def load_config() -> tuple[dict[str, str], dict[str, list[str]]]:
    config = yaml.safe_load(DISCIPLINES_YML.read_text(encoding="utf-8"))
    vocabulary = {k: " ".join(str(v).split()) for k, v in config["vocabulary"].items()}
    mapping = {k: list(v) for k, v in config["skills"].items()}
    return vocabulary, mapping


def validate(
    vocabulary: dict[str, str],
    mapping: dict[str, list[str]],
    skills_root: Path = SKILLS_ROOT,
) -> list[str]:
    """Fail-closed consistency check between vocabulary, mapping, and disk."""
    errors: list[str] = []
    on_disk = {
        d.name
        for d in skills_root.iterdir()
        if d.is_dir() and (d / "SKILL.md").is_file() and not d.name.startswith((".", "_"))
    }
    for name in sorted(on_disk - set(mapping)):
        errors.append(f"unmapped skill (add to disciplines.yml): {name}")
    for name in sorted(set(mapping) - on_disk):
        errors.append(f"mapped skill has no SKILL.md on disk: {name}")
    for name, discs in mapping.items():
        if not 1 <= len(discs) <= 3:
            errors.append(f"{name}: needs 1-3 disciplines, has {len(discs)}")
        for disc in discs:
            if disc not in vocabulary:
                errors.append(f"{name}: '{disc}' not in vocabulary")
    return errors


def frontmatter_bounds(lines: list[str]) -> tuple[int, int]:
    """Return (open_idx, close_idx) of the --- delimiters or raise ValueError."""
    if not lines or lines[0].strip() != "---":
        raise ValueError("no frontmatter")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return 0, i
    raise ValueError("unterminated frontmatter")


def strip_existing_block(lines: list[str], close: int) -> list[str]:
    """Remove any existing top-level disciplines: block inside the frontmatter."""
    out: list[str] = []
    i = 0
    while i < close:
        if lines[i].startswith("disciplines:"):
            i += 1
            while i < close and (lines[i].startswith((" ", "\t")) or not lines[i].strip()):
                if not lines[i].strip() and i + 1 < close and not lines[i + 1].startswith((" ", "\t")):
                    break
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return out


def set_skill_md(path: Path, disciplines: list[str], write: bool) -> str:
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    _, close = frontmatter_bounds(lines)
    head = strip_existing_block(lines[:close], close)
    block = ["disciplines:"] + [f"  - {d}" for d in disciplines]
    new_lines = head + block + lines[close:]
    new_text = "\n".join(new_lines)
    if new_text == text:
        return "unchanged"
    if write:
        path.write_text(new_text, encoding="utf-8")
    return "updated"


def set_readme(path: Path, disciplines: list[str], write: bool) -> str:
    if not path.is_file():
        return "no_readme"
    lines = path.read_text(encoding="utf-8").split("\n")
    banner = f"{BANNER_PREFIX} {' · '.join(disciplines)}"
    kept = [ln for ln in lines if not ln.startswith(BANNER_PREFIX)]
    insert_at = next((i + 1 for i, ln in enumerate(kept) if ln.startswith("# ")), 0)
    if insert_at < len(kept) and not kept[insert_at].strip():
        new_lines = kept[: insert_at + 1] + [banner] + kept[insert_at + 1 :]
    else:
        new_lines = kept[:insert_at] + ["", banner] + kept[insert_at:]
    new_text = "\n".join(new_lines)
    if new_text == "\n".join(lines):
        return "unchanged"
    if write:
        path.write_text(new_text, encoding="utf-8")
    return "updated"


def sync_memory(vocabulary: dict[str, str], mapping: dict[str, list[str]]) -> dict:
    """Delegate to the canonical /memory skill surface for catalog ingest.

    skill_descriptions is the single recall surface for skill metadata
    (anti-silo rule: no parallel discipline collection). /memory's
    ingest-skills subcommand reads SKILL.md frontmatter — including the
    disciplines: field this script maintains — and the skill_descriptions
    ArangoSearch view indexes it for recall. This module never touches
    ArangoDB or Qdrant directly.
    """
    result = subprocess.run(
        [str(SKILLS_ROOT / "memory" / "run.sh"), "ingest-skills", str(SKILLS_ROOT)],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if result.returncode != 0:
        logger.error("memory ingest-skills failed: {}", result.stderr.strip()[-500:])
        raise typer.Exit(code=1)
    try:
        ingest = json.loads(result.stdout[result.stdout.index("{"):])
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("memory ingest-skills returned non-JSON output: {}", exc)
        raise typer.Exit(code=1) from exc
    if not ingest.get("ok"):
        logger.error("memory ingest-skills reported failure: {}", ingest)
        raise typer.Exit(code=1)
    return {"ingest": ingest, "collection": "skill_descriptions"}


@app.command()
def run(
    write: bool = typer.Option(False, "--write", help="Apply edits (default: check only)"),
    memory_sync: bool = typer.Option(False, "--memory-sync", help="Upsert registry into /memory"),
) -> None:
    vocabulary, mapping = load_config()
    errors = validate(vocabulary, mapping)
    if errors:
        typer.echo(json.dumps({"status": "FAIL", "errors": errors}, indent=2))
        raise typer.Exit(code=2)

    results = {"skill_md": {"updated": 0, "unchanged": 0}, "readme": {"updated": 0, "unchanged": 0, "no_readme": 0}}
    failures: list[str] = []
    for name, discs in sorted(mapping.items()):
        try:
            results["skill_md"][set_skill_md(SKILLS_ROOT / name / "SKILL.md", discs, write)] += 1
            results["readme"][set_readme(SKILLS_ROOT / name / "README.md", discs, write)] += 1
        except ValueError as exc:
            failures.append(f"{name}: {exc}")

    report: dict = {
        "status": "FAIL" if failures else ("APPLIED" if write else "CHECK_ONLY"),
        "skills": len(mapping),
        "disciplines": len(vocabulary),
        "results": results,
        "failures": failures,
    }
    if failures:
        typer.echo(json.dumps(report, indent=2))
        raise typer.Exit(code=2)
    if memory_sync:
        report["memory"] = sync_memory(vocabulary, mapping)
    typer.echo(json.dumps(report, indent=2))


if __name__ == "__main__":
    app()
