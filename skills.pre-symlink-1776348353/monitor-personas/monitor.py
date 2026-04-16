#!/usr/bin/env python3
"""
Monitor Personas - Nightly persona monitoring system.

Thin assembler: imports from monitor_core, monitor_commands, monitor_pipeline.
Provides the typer app with all commands wired up.

Reads ALL personas from personas.yaml and monitors their sources
for new content. Integrates with:
- /scheduler for nightly automation
- /task-monitor for progress tracking
- /taxonomy for classification
- /memory for knowledge storage

Usage:
    uv run python monitor.py check      # Check all personas for new content
    uv run python monitor.py ingest     # Ingest new content
    uv run python monitor.py learn      # Learn to memory with taxonomy
    uv run python monitor.py status     # Show monitoring status
"""

from typing import Optional

import typer

# Re-export everything from sub-modules for backward compatibility
from monitor_core import (
    console,
    SKILL_DIR,
    CONFIG_FILE,
    PROJECT_ROOT,
    STATE_DIR,
    STATE_FILE,
    LEARNED_FILE,
    PersonaConfig,
    load_config,
    get_all_personas,
    get_settings,
    get_transcript_dir,
    get_youtube_video_count,
    get_ingested_count,
    load_state,
    save_state,
    load_learned,
    save_learned,
)

from monitor_commands import (
    cmd_check,
    cmd_ingest,
    cmd_learn,
    cmd_status,
    cmd_list_personas,
)

from monitor_pipeline import (
    cmd_check_all,
    cmd_ingest_all,
    cmd_extract_qras,
    cmd_classify_streams,
    cmd_archive_sessions,
    cmd_verify_edges,
    cmd_reflect_on_gaps,
    cmd_train_personas,
    cmd_close_loop,
    cmd_pipeline_status,
)

from curate import cmd_curate
from monitor_readiness import cmd_readiness
from backfill_taxonomy import cmd_backfill_taxonomy


app = typer.Typer(help="Nightly persona monitoring system")


# ─── Phase 1 Commands ──────────────────────────────────────────────────────


@app.command()
def check(
    priority: Optional[str] = typer.Option(None, "--priority", "-p", help="Filter by priority"),
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Filter by category"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Check ALL personas for new content."""
    cmd_check(app, priority=priority, category=category, json_output=json_output)


@app.command()
def ingest(
    priority: Optional[str] = typer.Option(None, "--priority", "-p", help="Only ingest priority level"),
    max_new: int = typer.Option(100, "--max-new", "-n", help="Max new videos per persona"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be ingested"),
):
    """Ingest new content for ALL personas."""
    cmd_ingest(priority=priority, max_new=max_new, dry_run=dry_run)


@app.command()
def learn(
    persona_id: Optional[str] = typer.Option(None, "--persona", "-p", help="Specific persona"),
    max_items: int = typer.Option(100, "--max", "-n", help="Max items to learn"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be learned"),
    batch: bool = typer.Option(True, "--batch/--no-batch", help="Use batch ingestion (recommended)"),
):
    """Learn pending transcripts to memory with taxonomy classification."""
    cmd_learn(persona_id=persona_id, max_items=max_items, dry_run=dry_run, batch=batch)


@app.command()
def status():
    """Show monitoring status for ALL personas."""
    cmd_status()


@app.command()
def list_personas(
    include_fictional: bool = typer.Option(True, "--fictional/--no-fictional", help="Include fictional personas"),
):
    """List all configured personas."""
    cmd_list_personas(include_fictional=include_fictional)


# ─── Curate Command ─────────────────────────────────────────────────────────


@app.command("curate")
def curate(
    persona: Optional[str] = typer.Option(None, "--persona", "-p", help="Persona ID(s), comma-separated"),
    content_type: Optional[str] = typer.Option(None, "--type", "-t", help="Content types: movies,books,music,arxiv,security,feeds,dogpile,youtube"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be discovered"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Discover new content aligned to persona tastes."""
    types = content_type.split(",") if content_type else None
    persona_ids = [p.strip() for p in persona.split(",")] if persona else None
    cmd_curate(persona_ids=persona_ids, content_types=types,
               dry_run=dry_run, json_output=json_output)


# ─── Phase 2 Pipeline Commands ──────────────────────────────────────────────


@app.command("check-all")
def check_all(
    priority: Optional[str] = typer.Option(None, "--priority", "-p", help="Filter by priority"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Check ALL source types across all personas."""
    cmd_check_all(priority=priority, json_output=json_output)


@app.command("ingest-all")
def ingest_all(
    priority: Optional[str] = typer.Option(None, "--priority", "-p", help="Filter by priority"),
    max_new: int = typer.Option(50, "--max-new", "-n", help="Max new items per source"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be ingested"),
):
    """Ingest new content from ALL source types."""
    cmd_ingest_all(priority=priority, max_new=max_new, dry_run=dry_run)


@app.command("extract")
def extract_qras(
    persona_id: Optional[str] = typer.Option(None, "--persona", "-p", help="Specific persona"),
    max_items: int = typer.Option(100, "--max", "-n", help="Max items to extract"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be extracted"),
):
    """Extract content to QRAs via /extractor."""
    cmd_extract_qras(persona_id=persona_id, max_items=max_items, dry_run=dry_run)


@app.command("classify-streams")
def classify_streams(
    persona_id: Optional[str] = typer.Option(None, "--persona", "-p", help="Specific persona"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be classified"),
):
    """Classify content into Intent or Persona streams."""
    cmd_classify_streams(persona_id=persona_id, dry_run=dry_run)


@app.command("archive")
def archive_sessions(
    hours: int = typer.Option(24, "--hours", "-h", help="Archive sessions from last N hours"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be archived"),
):
    """Archive sessions to episodic memory."""
    cmd_archive_sessions(hours=hours, dry_run=dry_run)


@app.command("verify-edges")
def verify_edges(
    collection: str = typer.Option("operational", "--collection", "-c", help="Knowledge graph collection"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be verified"),
):
    """Verify relationships with existing knowledge."""
    cmd_verify_edges(collection=collection, dry_run=dry_run)


@app.command("reflect")
def reflect_on_gaps(
    max_gaps: int = typer.Option(5, "--max-gaps", "-n", help="Max gaps to research"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be researched"),
):
    """Research knowledge gaps via /dogpile."""
    cmd_reflect_on_gaps(max_gaps=max_gaps, dry_run=dry_run)


@app.command("train")
def train_personas(
    persona_id: Optional[str] = typer.Option(None, "--persona", "-p", help="Specific persona"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be trained"),
):
    """Generate training data and trigger train-persona."""
    cmd_train_personas(persona_id=persona_id, dry_run=dry_run)


@app.command("close-loop")
def close_loop(
    persona: Optional[str] = typer.Option(None, "--persona", "-p", help="Specific persona ID(s), comma-separated"),
    priority: Optional[str] = typer.Option(None, "--priority", help="Filter by priority (HIGH/MEDIUM/LOW)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen"),
):
    """Run the complete learning pipeline."""
    persona_ids = [p.strip() for p in persona.split(",")] if persona else None
    cmd_close_loop(dry_run=dry_run, persona_ids=persona_ids, priority=priority)


@app.command("readiness")
def readiness(
    persona_id: Optional[str] = typer.Option(None, "--persona", "-p", help="Persona ID(s), comma-separated"),
    priority: Optional[str] = typer.Option(None, "--priority", help="Filter by priority (HIGH/MEDIUM/LOW)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show per-bridge breakdown"),
):
    """Assess if personas have sufficient QRAs for their core competency."""
    cmd_readiness(persona_id=persona_id, priority=priority, json_output=json_output, verbose=verbose)


@app.command("backfill-taxonomy")
def backfill_taxonomy(
    scope: Optional[str] = typer.Option(None, "--scope", "-s", help="Scope(s), comma-separated"),
    collection: Optional[str] = typer.Option(None, "--collection", "-c", help="ArangoDB collection"),
    sample_size: int = typer.Option(100, "--sample-size", "-n", help="Teacher sample size per scope"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without LLM calls or writes"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Shadow-LEGO backfill: stamp taxonomy_tags on existing QRAs."""
    cmd_backfill_taxonomy(
        scope=scope, collection=collection,
        sample_size=sample_size, dry_run=dry_run, json_output=json_output,
    )


@app.command("pipeline-status")
def pipeline_status():
    """Show overall pipeline status."""
    cmd_pipeline_status()


if __name__ == "__main__":
    app()
