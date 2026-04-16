"""
Persona Lore Ingest — Store persona backstory documents into /memory with /taxonomy bridges.

Generic for any persona (200+). No hardcoded registry — scope is derived from persona ID.
Convention: {persona_id}-memories

Usage:
    uv run persona_lore_ingest.py ingest --persona embry --docs-dir /mnt/storage12tb/media/personas/embry/docs
    uv run persona_lore_ingest.py ingest --persona embry --yaml /mnt/storage12tb/media/personas/embry/embry_persona.yaml
    uv run persona_lore_ingest.py ingest --persona horus --docs-dir /path/to/horus/docs
    uv run persona_lore_ingest.py ingest --persona anyname --docs-dir /path/to/docs
    uv run persona_lore_ingest.py list --persona embry
    uv run persona_lore_ingest.py list --persona horus --scope horus_lore  # query legacy scope
"""

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(help="Persona memory ingestion into /memory with /taxonomy bridges.")

SKILL_DIR = Path(__file__).parent
PI_SKILLS_DIR = SKILL_DIR.parent

# Ensure common.taxonomy is reachable
if str(PI_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(PI_SKILLS_DIR))


def _persona_scope(persona_id: str) -> str:
    """Derive memory scope from persona ID. Convention: {id}-memories."""
    return f"{persona_id}-memories"


def _get_bridge_attributes(text: str) -> list[str]:
    """Extract bridge attributes from text via taxonomy keyword matching."""
    try:
        from common.taxonomy_core import get_bridge_attributes
        return get_bridge_attributes(text)
    except ImportError:
        return []


def _run_memory(args: list[str], capture: bool = True) -> dict:
    """Run memory skill."""
    run_sh = SKILL_DIR / "run.sh"
    if not run_sh.exists():
        typer.echo(f"ERROR: {run_sh} not found", err=True)
        return {"returncode": 1, "error": "run.sh not found"}

    env = {k: v for k, v in __import__("os").environ.items() if k != "VIRTUAL_ENV"}
    try:
        result = subprocess.run(
            ["bash", str(run_sh)] + args,
            capture_output=capture, text=True, timeout=60,
            cwd=str(SKILL_DIR), env=env,
        )
        return {"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}
    except Exception as e:
        return {"returncode": 1, "error": str(e)}


def _split_markdown_sections(text: str) -> list[dict]:
    """Split markdown into sections by ## headers. Returns list of {title, body, level}."""
    sections = []
    current_title = "Preamble"
    current_level = 0
    current_lines: list[str] = []

    for line in text.split("\n"):
        header_match = re.match(r'^(#{1,4})\s+(.+)', line)
        if header_match:
            # Save previous section
            body = "\n".join(current_lines).strip()
            if body and len(body) > 30:
                sections.append({"title": current_title, "body": body, "level": current_level})
            current_level = len(header_match.group(1))
            current_title = header_match.group(2).strip()
            current_lines = []
        else:
            current_lines.append(line)

    # Final section
    body = "\n".join(current_lines).strip()
    if body and len(body) > 30:
        sections.append({"title": current_title, "body": body, "level": current_level})

    return sections


def _split_yaml_sections(text: str) -> list[dict]:
    """Split YAML persona file into logical sections for memory storage."""
    sections = []
    current_key = ""
    current_lines: list[str] = []

    # Top-level YAML keys become sections
    for line in text.split("\n"):
        top_key_match = re.match(r'^([a-z_]+):', line)
        if top_key_match and not line.startswith(" ") and not line.startswith("#"):
            # Save previous
            body = "\n".join(current_lines).strip()
            if body and len(body) > 50:
                sections.append({"title": current_key or "metadata", "body": body, "level": 1})
            current_key = top_key_match.group(1)
            current_lines = [line]
        else:
            current_lines.append(line)

    body = "\n".join(current_lines).strip()
    if body and len(body) > 50:
        sections.append({"title": current_key or "metadata", "body": body, "level": 1})

    return sections


def ingest_document(
    persona_id: str,
    scope: str,
    doc_path: Path,
    dry_run: bool = False,
    skip_files: Optional[set] = None,
) -> dict:
    """Ingest a single document into memory, split by sections."""
    if skip_files and doc_path.name in skip_files:
        typer.echo(f"  SKIP {doc_path.name} (in skip list)")
        return {"doc": doc_path.stem, "stored": 0, "skipped": 0}

    text = doc_path.read_text(errors="ignore")
    doc_name = doc_path.stem

    if doc_path.suffix in (".yaml", ".yml"):
        sections = _split_yaml_sections(text)
    else:
        sections = _split_markdown_sections(text)

    if not sections:
        typer.echo(f"  SKIP {doc_name}: no sections found")
        return {"doc": doc_name, "stored": 0, "skipped": 0}

    stored = 0
    skipped = 0

    for section in sections:
        title = section["title"]
        body = section["body"]

        # Truncate body for memory storage (keep it reasonable)
        if len(body) > 2000:
            body = body[:2000] + "\n...[truncated]"

        # Extract bridges
        bridges = _get_bridge_attributes(f"{title} {body}")
        if not bridges:
            bridges = ["persona", "lore"]

        problem = f"{persona_id} memory: {doc_name} — {title}"
        solution = body

        if dry_run:
            typer.echo(f"  DRY RUN: {problem[:80]} [{','.join(bridges)}]")
            stored += 1
            continue

        # Build tag args: --tag X --tag Y (not --tags CSV)
        tag_args = []
        for b in bridges:
            tag_args.extend(["--tag", b])

        result = _run_memory([
            "learn",
            "--problem", problem,
            "--solution", solution,
            "--scope", scope,
        ] + tag_args)

        if result.get("returncode") == 0:
            stored += 1
            typer.echo(f"  OK {title[:60]} [{','.join(bridges)}]")
        else:
            skipped += 1
            err = result.get("stderr", result.get("error", ""))[:100]
            typer.echo(f"  FAIL {title[:60]}: {err}")

    return {"doc": doc_name, "stored": stored, "skipped": skipped}


@app.command()
def ingest(
    persona: str = typer.Option(..., help="Persona ID (any string: embry, horus, maya, etc.)"),
    docs_dir: Optional[Path] = typer.Option(None, help="Directory containing .md/.yaml docs"),
    yaml: Optional[Path] = typer.Option(None, help="Persona YAML file to ingest"),
    scope: Optional[str] = typer.Option(None, help="Override memory scope (default: {persona}-memories)"),
    skip: Optional[str] = typer.Option(None, help="Comma-separated filenames to skip"),
    dry_run: bool = typer.Option(False, help="Print what would be stored without storing"),
):
    """Ingest persona backstory documents into /memory with /taxonomy bridges.

    Works for any persona — no registry needed. Scope defaults to {persona}-memories.
    """
    effective_scope = scope or _persona_scope(persona)
    skip_files = set(skip.split(",")) if skip else set()

    typer.echo(f"Ingesting {persona} into scope: {effective_scope}")

    if not docs_dir and not yaml:
        typer.echo("ERROR: provide --docs-dir, --yaml, or both", err=True)
        raise typer.Exit(1)

    total_stored = 0
    total_skipped = 0

    # Ingest markdown/text docs from directory
    if docs_dir:
        if not docs_dir.exists():
            typer.echo(f"ERROR: docs directory not found: {docs_dir}", err=True)
            raise typer.Exit(1)

        doc_files = sorted(
            [f for f in docs_dir.iterdir()
             if f.suffix in (".md", ".txt", ".yaml", ".yml") and f.is_file()]
        )
        typer.echo(f"\nFound {len(doc_files)} docs in {docs_dir}")

        for doc_file in doc_files:
            typer.echo(f"\n[{doc_file.name}]")
            result = ingest_document(persona, effective_scope, doc_file,
                                     dry_run=dry_run, skip_files=skip_files)
            total_stored += result["stored"]
            total_skipped += result["skipped"]

    # Ingest standalone YAML
    if yaml:
        if not yaml.exists():
            typer.echo(f"ERROR: YAML file not found: {yaml}", err=True)
            raise typer.Exit(1)

        typer.echo(f"\n[{yaml.name}]")
        result = ingest_document(persona, effective_scope, yaml, dry_run=dry_run)
        total_stored += result["stored"]
        total_skipped += result["skipped"]

    typer.echo(f"\n{'DRY RUN ' if dry_run else ''}Done: {total_stored} stored, {total_skipped} skipped")


@app.command(name="list")
def list_memories(
    persona: str = typer.Option(..., help="Persona ID"),
    scope: Optional[str] = typer.Option(None, help="Override scope (default: {persona}-memories)"),
    query: str = typer.Option("persona backstory formative memory identity", help="Search query"),
    k: int = typer.Option(20, help="Number of results"),
):
    """List stored memories for a persona by recalling from memory."""
    effective_scope = scope or _persona_scope(persona)
    typer.echo(f"Recalling {persona} memories from scope: {effective_scope}")

    result = _run_memory([
        "recall", "--q", query,
        "--scope", effective_scope, "--k", str(k),
    ])

    if result.get("returncode") == 0:
        try:
            data = json.loads(result.get("stdout", "{}"))
            items = data.get("items", [])
            typer.echo(f"Found {len(items)} items:\n")
            for item in items:
                title = item.get("problem", item.get("title", "?"))[:80]
                bridges = item.get("bridge_attributes", item.get("tags", []))
                typer.echo(f"  - {title} [{', '.join(bridges) if isinstance(bridges, list) else bridges}]")
        except json.JSONDecodeError:
            typer.echo(result.get("stdout", "")[:500])
    else:
        typer.echo(f"Recall failed: {result.get('stderr', result.get('error', ''))[:200]}")


if __name__ == "__main__":
    app()
