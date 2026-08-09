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
PORTFOLIO_DIR = SKILL_DIR / "references" / "portfolio"
REPO_ROOT = SKILLS_ROOT.parent
PORTFOLIO_REGISTRY_JSON = REPO_ROOT / "portfolio" / "research-taxonomy.json"
PORTFOLIO_REGISTRY_YAML = REPO_ROOT / "portfolio" / "research-taxonomy.yaml"
DISAGREEMENTS_CSV = PORTFOLIO_DIR / "discipline-area-disagreements.csv"
PORTFOLIO_MAX_AGE_DAYS = 90  # governance: quarterly review
WORKSPACE_ROOT = Path.home() / "workspace" / "experiments"
ACTIVITY_WINDOW_DAYS = 30
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
    errors.extend(validate_domains(skills_root, on_disk))
    return errors


def inbound_edges(skills_root: Path = SKILLS_ROOT) -> dict[str, int]:
    """Count how many skills declare each skill in their `composes:` list."""
    counts: dict[str, int] = {}
    for skill_md in sorted(skills_root.glob("*/SKILL.md")):
        try:
            meta = yaml.safe_load(skill_md.read_text(encoding="utf-8").split("---", 2)[1]) or {}
        except (yaml.YAMLError, IndexError):
            continue
        deps = meta.get("composes")
        deps = [deps] if isinstance(deps, str) else (deps or [])
        for dep in deps:
            counts[str(dep)] = counts.get(str(dep), 0) + 1
    return counts


def validate_domains(skills_root: Path, on_disk: set[str]) -> list[str]:
    """Fail-closed gates for the optional domain axis.

    A domain is product context, not method: membership means the domain is
    why the skill exists. The infrastructure guard enforces that in code —
    a skill composed by more than `infrastructure_max_inbound` others is
    shared infrastructure and cannot be claimed by any domain.
    """
    config = yaml.safe_load(DISCIPLINES_YML.read_text(encoding="utf-8"))
    vocab = config.get("domain_vocabulary") or {}
    members = config.get("domains") or {}
    cap = int((config.get("domain_rules") or {}).get("infrastructure_max_inbound", 7))
    counts = inbound_edges(skills_root)
    errors: list[str] = []
    for name, doms in members.items():
        if name not in on_disk:
            errors.append(f"domain member has no SKILL.md on disk: {name}")
        for dom in doms:
            if dom not in vocab:
                errors.append(f"{name}: domain '{dom}' not in domain_vocabulary")
        ib = counts.get(name, 0)
        if ib > cap:
            errors.append(
                f"{name}: {ib} inbound composes edges (> {cap}) — shared "
                f"infrastructure cannot belong to a domain; it is USED BY "
                f"{doms}, it does not exist FOR it"
            )
    return errors


def frontmatter_bounds(lines: list[str]) -> tuple[int, int]:
    """Return (open_idx, close_idx) of the --- delimiters or raise ValueError."""
    if not lines or lines[0].strip() != "---":
        raise ValueError("no frontmatter")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return 0, i
    raise ValueError("unterminated frontmatter")


def strip_existing_block(lines: list[str], close: int, key: str = "disciplines:") -> list[str]:
    """Remove an existing top-level block (disciplines:/domains:) from frontmatter."""
    out: list[str] = []
    i = 0
    while i < close:
        if lines[i].startswith(key):
            i += 1
            while i < close and (lines[i].startswith((" ", "\t")) or not lines[i].strip()):
                if not lines[i].strip() and i + 1 < close and not lines[i + 1].startswith((" ", "\t")):
                    break
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return out


def set_skill_md(
    path: Path, disciplines: list[str], write: bool, domains: list[str] | None = None
) -> str:
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    _, close = frontmatter_bounds(lines)
    head = strip_existing_block(lines[:close], close, key="disciplines:")
    head = strip_existing_block(head, len(head), key="domains:")
    block = ["disciplines:"] + [f"  - {d}" for d in disciplines]
    if domains:
        block += ["domains:"] + [f"  - {d}" for d in domains]
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

    domain_members = yaml.safe_load(DISCIPLINES_YML.read_text(encoding="utf-8")).get("domains") or {}
    results = {"skill_md": {"updated": 0, "unchanged": 0}, "readme": {"updated": 0, "unchanged": 0, "no_readme": 0}}
    failures: list[str] = []
    for name, discs in sorted(mapping.items()):
        try:
            results["skill_md"][set_skill_md(
                SKILLS_ROOT / name / "SKILL.md", discs, write, domain_members.get(name)
            )] += 1
            results["readme"][set_readme(SKILLS_ROOT / name / "README.md", discs, write)] += 1
        except ValueError as exc:
            failures.append(f"{name}: {exc}")

    report: dict = {
        "status": "FAIL" if failures else ("APPLIED" if write else "CHECK_ONLY"),
        "skills": len(mapping),
        "disciplines": len(vocabulary),
        "results": results,
        "domain_members": len(domain_members),
        "failures": failures,
    }
    if failures:
        typer.echo(json.dumps(report, indent=2))
        raise typer.Exit(code=2)
    if memory_sync:
        report["memory"] = sync_memory(vocabulary, mapping)
    typer.echo(json.dumps(report, indent=2))


@app.command()
def crosswalk(
    write: bool = typer.Option(False, "--write", help="Regenerate the disagreements CSV"),
) -> None:
    """Deterministically diff portfolio per-skill areas against local disciplines.

    Uses area_crosswalk from disciplines.yml and the committed
    references/portfolio/skill-classification.csv. Fail closed: an area in the
    classification missing from the crosswalk, or a crosswalk discipline
    outside the vocabulary, is an error. Without --write, verifies the
    committed CSV matches the regenerated one (drift gate for sanity/CI).
    """
    import csv
    import io

    config = yaml.safe_load(DISCIPLINES_YML.read_text(encoding="utf-8"))
    vocabulary = set(config["vocabulary"])
    mapping = {k: list(v) for k, v in config["skills"].items()}
    xw = config.get("area_crosswalk") or {}
    errors = [
        f"crosswalk area '{area}' maps to unknown discipline '{d}'"
        for area, discs in xw.items()
        for d in discs
        if d not in vocabulary
    ]
    rows = list(csv.DictReader((PORTFOLIO_DIR / "skill-classification.csv").open(encoding="utf-8")))
    for area in sorted({r["research_area"] for r in rows if r["research_area"]}):
        if area not in xw:
            errors.append(f"classification area '{area}' missing from area_crosswalk")
    if errors:
        typer.echo(json.dumps({"status": "FAIL", "errors": errors}, indent=2))
        raise typer.Exit(code=2)

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["skill", "webgpt_area", "webgpt_confidence", "local_disciplines", "resolution"])
    count = 0
    for row in rows:
        area, name = row["research_area"], row["skill"]
        if area and name in mapping and not (set(mapping[name]) & set(xw[area])):
            writer.writerow([name, area, row["confidence"], "|".join(mapping[name]), "PENDING_HUMAN_REVIEW"])
            count += 1
    generated = buf.getvalue()
    if write:
        DISAGREEMENTS_CSV.write_text(generated, encoding="utf-8")
        status = "WRITTEN"
    elif not DISAGREEMENTS_CSV.is_file():
        typer.echo(json.dumps({"status": "FAIL", "errors": ["disagreements CSV missing; run crosswalk --write"]}))
        raise typer.Exit(code=2)
    elif DISAGREEMENTS_CSV.read_text(encoding="utf-8") != generated:
        typer.echo(json.dumps({"status": "FAIL", "errors": ["disagreements CSV is stale; run crosswalk --write"]}))
        raise typer.Exit(code=2)
    else:
        status = "IN_SYNC"
    typer.echo(json.dumps({"status": status, "disagreements": count, "csv": str(DISAGREEMENTS_CSV)}))


def _active_local_repos(window_days: int) -> set[str]:
    """Canonical names of active primary checkouts under ~/workspace/experiments.

    Worktrees and lane clones must not inflate the portfolio: directories
    whose .git is a file (linked worktrees) are skipped, and each remaining
    clone is canonicalized to its origin URL basename, so N clones of one
    repo count once under the repo's real name.
    """
    active: set[str] = set()
    for repo in sorted(WORKSPACE_ROOT.iterdir()):
        git_meta = repo / ".git"
        if not git_meta.is_dir():  # absent, or a file -> linked worktree
            continue
        recent = subprocess.run(
            ["git", "-C", str(repo), "log", "-1", f"--since={window_days} days ago", "--pretty=%h"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if recent.returncode != 0 or not recent.stdout.strip():
            continue
        origin = subprocess.run(
            ["git", "-C", str(repo), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        url = origin.stdout.strip()
        if origin.returncode != 0 or not url:
            continue  # origin-less local clones are fixtures/scratch, not portfolio lines
        active.add(url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git").lower())
    return active


def checkout_staleness() -> dict:
    """How far behind origin/<branch> this checkout is.

    A coverage gate is only as truthful as the tree it runs in: a stale
    checkout cannot see skills added since it last fetched, so it would
    report green while blind. Observed 2026-08-09: a local run reported
    "345 skills, all mapped" while origin/main already had 346.
    """
    subprocess.run(["git", "fetch", "-q", "origin"], capture_output=True, timeout=120, check=False)
    branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, check=False
    ).stdout.strip()
    counts = subprocess.run(
        ["git", "rev-list", "--left-right", "--count", f"origin/{branch}...HEAD"],
        capture_output=True, text=True, check=False,
    ).stdout.split()
    behind = int(counts[0]) if len(counts) == 2 else -1
    return {"branch": branch, "behind_origin": behind, "current": behind == 0}


@app.command("portfolio-check")
def portfolio_check() -> None:
    """Validate the repo-level portfolio registry and its freshness (fail closed).

    Gates: bundled validator passes on portfolio/research-taxonomy.json; the
    YAML twin exists; the registry is younger than the quarterly-review cap;
    and every locally active repo (commits in the last 30 days under
    ~/workspace/experiments) appears in the registry — unclassified active
    repos are named so the project classification stays up to date.
    """
    from datetime import UTC, date, datetime

    validator = PORTFOLIO_DIR / "validate-research-taxonomy.py"
    errors = [
        f"missing: {f}"
        for f in (validator, PORTFOLIO_REGISTRY_JSON, PORTFOLIO_REGISTRY_YAML)
        if not f.is_file()
    ]
    if errors:
        typer.echo(json.dumps({"status": "FAIL", "errors": errors}, indent=2))
        raise typer.Exit(code=2)

    result = subprocess.run(
        ["python3", str(validator), str(PORTFOLIO_REGISTRY_JSON)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        logger.error("portfolio validator failed: {}", (result.stdout + result.stderr).strip()[-500:])
        typer.echo(json.dumps({"status": "FAIL", "errors": [(result.stdout + result.stderr).strip()[-300:]]}))
        raise typer.Exit(code=2)

    registry = json.loads(PORTFOLIO_REGISTRY_JSON.read_text(encoding="utf-8"))
    generated_on = date.fromisoformat(str(registry.get("generated_on")))
    age_days = (datetime.now(UTC).date() - generated_on).days
    known_repos = {
        str(p.get("repository", "")).split("/")[-1].lower() for p in registry.get("projects", [])
    }
    config = yaml.safe_load(DISCIPLINES_YML.read_text(encoding="utf-8"))
    overrides = config.get("portfolio_repo_overrides") or {}
    aliases = {str(k).lower(): str(v).lower() for k, v in (overrides.get("aliases") or {}).items()}
    ignored = {str(v).lower() for v in overrides.get("ignore") or []}
    active = {aliases.get(name, name) for name in _active_local_repos(ACTIVITY_WINDOW_DAYS)}
    unclassified = sorted(active - known_repos - ignored)

    stale = checkout_staleness()
    report = {
        "status": "PASS",
        "checkout": stale,
        "validator": result.stdout.strip(),
        "registry_generated_on": str(generated_on),
        "registry_age_days": age_days,
        "unclassified_active_repos": unclassified,
    }
    if age_days > PORTFOLIO_MAX_AGE_DAYS:
        report["status"] = "FAIL"
        report["errors"] = [
            f"registry is {age_days} days old (> {PORTFOLIO_MAX_AGE_DAYS}); quarterly review due"
        ]
    if not stale["current"]:
        report["status"] = "FAIL"
        report.setdefault("errors", []).append(
            f"checkout is {stale['behind_origin']} commits behind origin/{stale['branch']}; "
            "coverage measured here is not trustworthy — fetch/rebase before trusting this gate"
        )
    if unclassified:
        report["status"] = "FAIL"
        report.setdefault("errors", []).append(
            "active repos missing from portfolio registry: " + ", ".join(unclassified)
        )
    typer.echo(json.dumps(report, indent=2))
    if report["status"] != "PASS":
        raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
