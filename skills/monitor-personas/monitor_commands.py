"""
Monitor Personas - Core commands: check, ingest, learn, status, list-personas.

Contains the primary typer commands for persona monitoring.
"""

import json
import os
import subprocess

from loguru import logger
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

# Import canonical ingest-youtube channel listing
_SKILLS_DIR = Path(__file__).resolve().parent.parent
_IY_DIR = str(_SKILLS_DIR / "ingest-youtube")
if _IY_DIR not in sys.path:
    sys.path.insert(0, _IY_DIR)
_MEMORY_DIR = str(_SKILLS_DIR / "memory")
if _MEMORY_DIR not in sys.path:
    sys.path.insert(0, _MEMORY_DIR)
from youtube_transcripts.downloader import list_channel_video_ids

from integrations import (
    TaxonomyIntegration,
    MemoryIntegration,
    get_taxonomy,
    get_memory,
)
from monitor_core import (
    console,
    SKILL_DIR,
    CONFIG_FILE,
    PROJECT_ROOT,
    STATE_DIR,
    STATE_FILE,
    LEARNED_FILE,
    PersonaConfig,
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


def cmd_check(
    app: typer.Typer,
    priority: Optional[str] = None,
    category: Optional[str] = None,
    json_output: bool = False,
):
    """Check ALL personas for new content."""
    personas = get_all_personas()
    state = load_state()
    results = []

    filtered_personas = []
    for persona in personas:
        if priority and persona.priority != priority:
            continue
        if category and persona.category != category:
            continue
        youtube_source = None
        for source in persona.sources:
            if isinstance(source, str):
                continue
            if source.get("type") == "youtube":
                youtube_source = source.get("handle")
                break
        if youtube_source:
            filtered_personas.append((persona, youtube_source))

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task(f"Checking {len(filtered_personas)} personas...", total=len(filtered_personas))

        for persona, youtube_source in filtered_personas:
            progress.update(task, description=f"Checking {persona.name}...")

            youtube_count = get_youtube_video_count(youtube_source)
            ingested_count = get_ingested_count(persona.id)
            new_count = max(0, youtube_count - ingested_count) if youtube_count >= 0 else 0

            state["personas"][persona.id] = {
                "name": persona.name,
                "priority": persona.priority,
                "category": persona.category,
                "scope": persona.scope,
                "youtube_count": youtube_count,
                "ingested_count": ingested_count,
                "new_count": new_count,
                "last_checked": datetime.now().isoformat(),
            }

            results.append({
                "id": persona.id,
                "name": persona.name,
                "priority": persona.priority,
                "category": persona.category,
                "youtube": youtube_count,
                "ingested": ingested_count,
                "new": new_count,
            })

            progress.advance(task)

    state["last_check"] = datetime.now().isoformat()
    save_state(state)

    if json_output:
        typer.echo(json.dumps(results, indent=2))
    else:
        table = Table(show_header=True, header_style="bold cyan", box=None)
        table.add_column("Persona", style="white", width=25)
        table.add_column("Priority", style="yellow", width=8)
        table.add_column("YouTube", justify="right", width=8)
        table.add_column("Ingested", justify="right", width=10)
        table.add_column("New", justify="right", width=6)

        total_new = 0
        for r in sorted(results, key=lambda x: (-x["new"], x["priority"])):
            new_str = f"[bold green]{r['new']}[/]" if r["new"] > 0 else "[dim]-[/]"
            total_new += r["new"]

            priority_style = {
                "HIGH": "[bold red]HIGH[/]",
                "MEDIUM": "[yellow]MEDIUM[/]",
                "LOW": "[dim]LOW[/]",
            }.get(r["priority"], r["priority"])

            table.add_row(
                r["name"],
                priority_style,
                str(r["youtube"]),
                str(r["ingested"]),
                new_str,
            )

        panel = Panel(
            table,
            title="[bold]Persona Monitor Status[/]",
            subtitle=f"[dim]{len(results)} personas, {total_new} new videos[/]",
            border_style="blue",
        )
        console.print(panel)


def _sync_to_shared_library(persona_dir: Path, persona_id: str):
    """Copy new transcripts to shared library for cross-persona consumption.

    Symlinks persona transcript files to the shared library transcripts
    directory so cmd_extract_shared can fan out QRAs to relevant personas.
    """
    from monitor_core import get_shared_library_config

    shared_config = get_shared_library_config()
    if not shared_config:
        return

    library_path = Path(shared_config.path)
    transcripts_subdir = shared_config.subdirs.get("transcripts", "transcripts")
    shared_persona_dir = library_path / transcripts_subdir / persona_id
    shared_persona_dir.mkdir(parents=True, exist_ok=True)

    # Symlink new transcript files
    for json_file in persona_dir.glob("*.json"):
        if json_file.name == ".batch_state.json" or json_file.name.endswith("_qras.json"):
            continue
        target = shared_persona_dir / json_file.name
        if not target.exists():
            try:
                target.symlink_to(json_file)
            except OSError:
                # Fallback: copy if symlink fails (cross-filesystem)
                import shutil
                shutil.copy2(json_file, target)


def cmd_ingest(
    priority: Optional[str] = None,
    max_new: int = 100,
    dry_run: bool = False,
):
    """Ingest new content for ALL personas."""
    personas = get_all_personas()
    transcript_dir = get_transcript_dir()
    settings = get_settings()
    batch_settings = settings.get("batch", {})

    typer.echo(f"Processing {len(personas)} personas...\n")

    for persona in personas:
        if priority and persona.priority != priority:
            continue

        youtube_source = None
        for source in persona.sources:
            if isinstance(source, str):
                continue
            if source.get("type") == "youtube":
                youtube_source = source.get("handle")
                break

        if not youtube_source:
            continue

        typer.echo(f"=== {persona.name} ({persona.priority}) ===")

        youtube_count = get_youtube_video_count(youtube_source)
        ingested_count = get_ingested_count(persona.id)
        new_count = max(0, youtube_count - ingested_count) if youtube_count >= 0 else 0

        if new_count == 0:
            typer.echo(f"  No new videos (YouTube: {youtube_count}, Ingested: {ingested_count})")
            continue

        typer.echo(f"  Found {new_count} new videos")

        if dry_run:
            typer.echo(f"  [DRY RUN] Would ingest up to {min(new_count, max_new)} videos")
            continue

        video_list = transcript_dir / f"{persona.id}_videos.txt"
        persona_dir = transcript_dir / persona.id
        persona_dir.mkdir(exist_ok=True)

        typer.echo(f"  Updating video list...")
        video_ids = list_channel_video_ids(youtube_source, max_results=0)

        if not video_ids:
            typer.echo(f"  ERROR: Failed to fetch video list", err=True)
            continue

        video_list.write_text("\n".join(video_ids) + "\n")

        typer.echo(f"  Starting batch ingestion...")

        ingest_youtube_dir = PROJECT_ROOT / ".pi/skills/ingest-youtube"
        cmd = [
            "uv", "run", "python", "supervisor.py", "run",
            "--input", str(video_list),
            "--output", str(persona_dir),
            "--delay-min", str(batch_settings.get("delay_min", 3)),
            "--delay-max", str(batch_settings.get("delay_max", 10)),
        ]

        log_file = transcript_dir / f"{persona.id}.log"
        with open(log_file, "a") as log:
            subprocess.Popen(
                cmd,
                cwd=ingest_youtube_dir,
                stdout=log,
                stderr=log,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )

        typer.echo(f"  Batch started (log: {log_file.name})")

        # Sync existing transcripts to shared library for cross-persona fan-out
        _sync_to_shared_library(persona_dir, persona.id)

    typer.echo("\n=== Ingestion jobs started ===")


def cmd_learn(
    persona_id: Optional[str] = None,
    max_items: int = 100,
    dry_run: bool = False,
    batch: bool = True,
):
    """Learn pending transcripts to memory with taxonomy classification."""
    personas = get_all_personas()
    transcript_dir = get_transcript_dir()
    learned = load_learned()

    taxonomy = get_taxonomy()
    memory = get_memory()

    if not memory.is_available():
        console.print("[red]ERROR: Memory skill not available[/]")
        raise typer.Exit(1)

    total_learned = 0

    for persona in personas:
        if persona_id and persona.id != persona_id:
            continue

        persona_dir = transcript_dir / persona.id
        if not persona_dir.exists():
            continue

        collection = taxonomy.collection_for_persona(
            category=persona.category, scope=persona.scope,
        )
        console.print(f"\n[bold cyan]=== {persona.name} -> scope: {persona.scope}, collection: {collection} ===[/]")

        transcripts = list(persona_dir.glob("*.json"))
        transcripts = [t for t in transcripts if t.name != ".batch_state.json"]
        pending = [t for t in transcripts if str(t) not in learned]

        console.print(f"  Total: {len(transcripts)}, Pending: {len(pending)}")

        if not pending:
            continue

        if batch:
            if dry_run:
                console.print(f"  [yellow][DRY RUN][/] Would batch ingest {len(pending)} transcripts from {persona_dir}")
                continue

            console.print(f"  Batch ingesting {len(pending)} transcripts...", end="")

            result = memory.ingest_youtube_directory(
                persona_dir, scope=persona.scope, tags=persona.taxonomy_hints,
            )

            if result.success:
                for t in pending[:max_items]:
                    learned.add(str(t))
                total_learned += len(pending[:max_items])
                console.print(f" [green]v[/] ({result.documents_ingested} docs, {result.chunks_created} chunks)")

                # ── Post-batch Quality Scan ──
                try:
                    from memory_quality_scorer import score_memory as _score_memory
                    quality_scores = []
                    low_quality = []
                    for t in pending[:max_items]:
                        try:
                            data = json.loads(Path(t).read_text())
                            text = data.get("full_text", "")
                            if len(text) < 100:
                                continue
                            qr = _score_memory(
                                text=text,
                                scope=persona.scope,
                                bridges_stored=data.get("taxonomy_tags", []),
                                check_contradiction=False,  # Skip graph traversal in batch (performance)
                            )
                            quality_scores.append(qr.overall_score)
                            if qr.content_quality == "ambiguous":
                                low_quality.append(Path(t).stem)
                        except Exception:
                            continue
                    if quality_scores:
                        avg = sum(quality_scores) / len(quality_scores)
                        console.print(f"  [dim]Quality: avg={avg:.2f}, ambiguous={len(low_quality)}/{len(quality_scores)}[/]")
                        if low_quality:
                            console.print(f"  [dim yellow]Low quality: {', '.join(low_quality[:5])}{'...' if len(low_quality) > 5 else ''}[/]")
                except Exception as e:
                    console.print(f"  [dim](quality scan skipped: {e})[/]")
            else:
                console.print(f" [red]x[/] {result.message[:100]}")
        else:
            for transcript in pending[:max_items]:
                if dry_run:
                    console.print(f"  [yellow][DRY RUN][/] Would learn: {transcript.stem}")
                    continue

                console.print(f"  Learning: {transcript.stem}...", end="")

                try:
                    data = json.loads(transcript.read_text())
                    full_text = data.get("full_text", "")
                    video_id = data.get("meta", {}).get("video_id", transcript.stem)

                    if len(full_text) < 100:
                        console.print(" [dim](too short, skipped)[/]")
                        continue

                    tags = list(persona.taxonomy_hints)

                    if taxonomy.is_available():
                        taxonomy_result = taxonomy.extract(
                            text=full_text[:3000],
                            collection=collection,
                            bridges_only=True,
                            fast=True,
                        )
                        tags.extend(taxonomy_result.bridge_tags)

                    if tags:
                        data["taxonomy_tags"] = list(set(tags))
                        transcript.write_text(json.dumps(data, indent=2))

                    # ── Quality Scoring ──
                    quality_meta = {}
                    try:
                        from memory_quality_scorer import score_memory as _score_memory
                        qr = _score_memory(
                            text=full_text,
                            scope=persona.scope,
                            bridges_stored=tags,
                            check_contradiction=True,
                        )
                        quality_meta = qr.to_metadata()
                        data["_quality_score"] = quality_meta.get("_quality_score", 0.0)
                        data["_conflict_ref"] = quality_meta.get("_conflict_ref")
                        data["_conflict_bridge"] = quality_meta.get("_conflict_bridge")
                        data["_conflict_text"] = quality_meta.get("_conflict_text")
                        data["_content_quality"] = qr.content_quality
                        data["_deficits"] = qr.deficits
                        transcript.write_text(json.dumps(data, indent=2))

                        # Enqueue low-quality memories for re-creation
                        if qr.content_quality == "ambiguous" or qr.overall_score < 0.2:
                            try:
                                from recreation_queue import enqueue as _enqueue
                                reason = "ambiguous" if qr.content_quality == "ambiguous" else "low_score"
                                _enqueue(
                                    key=video_id,
                                    scope=persona.scope,
                                    reason=reason,
                                    deficits=qr.deficits,
                                    quality_score=qr.overall_score,
                                    original_text=full_text[:200],
                                )
                            except Exception as e:
                                logger.debug("persona quality scoring failed: {}", e)
                    except Exception as e:
                        console.print(f" [dim](quality scoring skipped: {e})[/]")

                    learned.add(str(transcript))
                    total_learned += 1
                    tag_str = f" tags: {','.join(tags)}" if tags else ""
                    q_str = f" quality={quality_meta.get('_quality_score', '?')}" if quality_meta else ""
                    console.print(f" [green]v[/]{tag_str}{q_str}")

                except Exception as e:
                    console.print(f" [red]ERROR: {e}[/]")

        save_learned(learned)

    console.print(f"\n[bold]=== Learned {total_learned} transcripts to memory ===[/]")


def cmd_status():
    """Show monitoring status for ALL personas."""
    state = load_state()
    learned = load_learned()

    info_table = Table(show_header=False, box=None, padding=(0, 1))
    info_table.add_column("Key", style="cyan")
    info_table.add_column("Value", style="white")
    info_table.add_row("Config", str(CONFIG_FILE))
    info_table.add_row("State", str(STATE_FILE))
    info_table.add_row("Last check", state.get("last_check", "[dim]Never[/]"))
    info_table.add_row("Learned", f"{len(learned)} transcripts")

    console.print(Panel(info_table, title="[bold]Persona Monitor[/]", border_style="blue"))

    personas = state.get("personas", {})
    if not personas:
        console.print("[yellow]No personas checked yet. Run: ./run.sh check[/]")
        return

    table = Table(show_header=True, header_style="bold cyan", box=None)
    table.add_column("Persona", style="white", width=25)
    table.add_column("Priority", style="yellow", width=8)
    table.add_column("YouTube", justify="right", width=8)
    table.add_column("Ingested", justify="right", width=10)
    table.add_column("New", justify="right", width=6)

    total_new = 0
    for pid, data in sorted(personas.items(), key=lambda x: -x[1].get("new_count", 0)):
        new_count = data.get("new_count", 0)
        total_new += new_count
        new_str = f"[bold green]{new_count}[/]" if new_count > 0 else "[dim]-[/]"

        p = data.get("priority", "?")
        priority_style = {
            "HIGH": "[bold red]HIGH[/]",
            "MEDIUM": "[yellow]MEDIUM[/]",
            "LOW": "[dim]LOW[/]",
        }.get(p, p)

        table.add_row(
            data.get("name", pid),
            priority_style,
            str(data.get("youtube_count", "?")),
            str(data.get("ingested_count", "?")),
            new_str,
        )

    panel = Panel(
        table,
        title="[bold]Persona Status[/]",
        subtitle=f"[dim]{len(personas)} personas, {total_new} new videos[/]",
        border_style="green",
    )
    console.print(panel)


def cmd_list_personas(include_fictional: bool = True):
    """List all configured personas."""
    personas = get_all_personas()

    fictional_personas = [p for p in personas if p.fictional]
    real_personas = [p for p in personas if not p.fictional]

    if real_personas:
        table = Table(show_header=True, header_style="bold cyan", box=None)
        table.add_column("ID", style="dim", width=20)
        table.add_column("Name", style="white", width=25)
        table.add_column("Priority", width=8)
        table.add_column("Scope", style="dim", width=15)
        table.add_column("Category", style="dim", width=15)

        for p in real_personas:
            priority_style = {
                "HIGH": "[bold red]HIGH[/]",
                "MEDIUM": "[yellow]MEDIUM[/]",
                "LOW": "[dim]LOW[/]",
            }.get(p.priority, p.priority)

            table.add_row(p.id, p.name, priority_style, p.scope, p.category)

        panel = Panel(
            table,
            title="[bold]Real Personas (Source Monitoring)[/]",
            subtitle=f"[dim]{len(real_personas)} personas with content sources[/]",
            border_style="blue",
        )
        console.print(panel)

    if include_fictional and fictional_personas:
        table = Table(show_header=True, header_style="bold magenta", box=None)
        table.add_column("ID", style="dim", width=20)
        table.add_column("Name", style="white", width=25)
        table.add_column("Priority", width=8)
        table.add_column("Lore Sources", style="dim", width=25)

        for p in fictional_personas:
            priority_style = {
                "HIGH": "[bold red]HIGH[/]",
                "MEDIUM": "[yellow]MEDIUM[/]",
                "LOW": "[dim]LOW[/]",
            }.get(p.priority, p.priority)

            lore_sources = ", ".join(p.lore_sources) if p.lore_sources else "[dim]-[/]"

            table.add_row(p.id, p.name, priority_style, lore_sources)

        panel = Panel(
            table,
            title="[bold]Fictional Personas (Character Definitions)[/]",
            subtitle=f"[dim]{len(fictional_personas)} character personas[/]",
            border_style="magenta",
        )
        console.print(panel)

    console.print(f"\nTotal: {len(real_personas)} real + {len(fictional_personas)} fictional = {len(personas)} personas")
