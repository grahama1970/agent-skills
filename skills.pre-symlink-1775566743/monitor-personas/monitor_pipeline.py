"""
Monitor Personas - Phase 2 pipeline commands.

Contains check-all, ingest-all, extract, classify-streams, archive,
verify-edges, reflect, train, close-loop, and pipeline-status commands.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from monitor_core import (
    console,
    PROJECT_ROOT,
    get_all_personas,
    get_transcript_dir,
    load_state,
    save_state,
    load_learned,
)
from integrations import get_taxonomy, get_memory


def cmd_check_all(
    priority: Optional[str] = None,
    json_output: bool = False,
    persona_ids: Optional[list] = None,
):
    """Check ALL source types across all personas.

    Checks YouTube, RSS, arXiv, Books, Movies, Music, and Code sources.
    """
    from sources import SourceConfig, check_all_sources, HANDLERS
    from state import get_state_manager

    personas = get_all_personas()
    state_mgr = get_state_manager()

    results = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Checking all sources...", total=len(personas))

        for persona in personas:
            if priority and persona.priority != priority:
                continue
            if persona_ids and persona.id not in persona_ids:
                continue

            progress.update(task, description=f"Checking {persona.name}...")

            persona_results = {"persona": persona.id, "name": persona.name, "sources": []}

            for source in persona.sources:
                if isinstance(source, str):
                    continue
                source_config = SourceConfig(
                    type=source.get("type", "youtube"),
                    handle=source.get("handle", source.get("url", "")),
                    priority=persona.priority,
                    search_terms=source.get("search_terms"),
                )

                handler = HANDLERS.get(source_config.type)
                if handler:
                    status = handler.check(source_config, state_mgr.state_dir)
                    persona_results["sources"].append({
                        "type": source_config.type,
                        "handle": source_config.handle,
                        "total": status.total,
                        "ingested": status.ingested,
                        "new": status.new,
                        "error": status.error,
                    })

            results.append(persona_results)
            progress.advance(task)

    if json_output:
        typer.echo(json.dumps(results, indent=2))
    else:
        table = Table(show_header=True, header_style="bold cyan", box=None)
        table.add_column("Persona", style="white", width=20)
        table.add_column("Source", style="dim", width=10)
        table.add_column("Total", justify="right", width=8)
        table.add_column("Ingested", justify="right", width=10)
        table.add_column("New", justify="right", width=6)

        total_new = 0
        for r in results:
            for src in r["sources"]:
                new_count = src.get("new", 0)
                total_new += new_count
                new_str = f"[bold green]{new_count}[/]" if new_count > 0 else "[dim]-[/]"

                table.add_row(
                    r["name"],
                    src["type"],
                    str(src.get("total", 0)),
                    str(src.get("ingested", 0)),
                    new_str,
                )

        panel = Panel(
            table,
            title="[bold]All Sources Status[/]",
            subtitle=f"[dim]{len(results)} personas, {total_new} new items[/]",
            border_style="blue",
        )
        console.print(panel)


def cmd_ingest_all(
    priority: Optional[str] = None,
    max_new: int = 50,
    dry_run: bool = False,
):
    """Ingest new content from ALL source types.

    Triggers appropriate ingest skills for each source type.
    """
    from sources import SourceConfig, HANDLERS
    from state import get_state_manager

    personas = get_all_personas()
    state_mgr = get_state_manager()
    transcript_dir = get_transcript_dir()

    console.print("[bold]Ingesting from all sources...[/]\n")

    for persona in personas:
        if priority and persona.priority != priority:
            continue

        console.print(f"[bold cyan]=== {persona.name} ===[/]")

        for source in persona.sources:
            if isinstance(source, str):
                continue
            source_type = source.get("type", "youtube")
            handle = source.get("handle", source.get("url", ""))

            console.print(f"  [{source_type}] {handle[:50]}...", end="")

            if dry_run:
                console.print(" [yellow][DRY RUN][/]")
                continue

            if source_type == "youtube":
                console.print(" [dim](use 'ingest' command)[/]")
            else:
                console.print(" [dim](not implemented)[/]")

    console.print("\n[bold]Use specific ingest commands for each source type.[/]")


def cmd_extract_qras(
    persona_id: Optional[str] = None,
    max_items: int = 100,
    dry_run: bool = False,
):
    """Extract QRA pairs via /doc2qra.

    Writes transcript full_text to temp markdown, calls doc2qra,
    and stores extraction output alongside the original transcript.
    """
    import tempfile

    from state import get_state_manager, ExtractedContent
    from integrations import get_doc2qra

    personas = get_all_personas()
    transcript_dir = get_transcript_dir()
    state_mgr = get_state_manager()
    doc2qra = get_doc2qra()

    if not doc2qra.is_available():
        console.print("[red]ERROR: /doc2qra skill not available. Cannot extract.[/]")
        console.print("  Install: .pi/skills/doc2qra")
        return

    total_extracted = 0
    total_qras = 0

    for persona in personas:
        if persona_id and persona.id != persona_id:
            continue

        persona_dir = transcript_dir / persona.id
        if not persona_dir.exists():
            continue

        console.print(f"\n[bold cyan]=== {persona.name} ===[/]")

        transcripts = list(persona_dir.glob("*.json"))
        transcripts = [t for t in transcripts
                       if t.name != ".batch_state.json"
                       and not t.name.endswith("_qras.json")]
        pending = [t for t in transcripts if not state_mgr.is_extracted(str(t))]

        console.print(f"  Total: {len(transcripts)}, Pending: {len(pending)}")

        for transcript in pending[:max_items]:
            if dry_run:
                console.print(f"  [yellow][DRY RUN][/] Would extract: {transcript.stem}")
                continue

            console.print(f"  Extracting: {transcript.stem}...", end="")

            try:
                data = json.loads(transcript.read_text())
                full_text = data.get("full_text", "")
                title = data.get("meta", {}).get("title", transcript.stem)

                if len(full_text) < 100:
                    console.print(" [dim](too short)[/]")
                    continue

                # Write transcript text to temp markdown for extractor
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".md", delete=False, prefix="mp_"
                ) as tmp:
                    tmp.write(f"# {title}\n\n{full_text}")
                    tmp_path = Path(tmp.name)

                try:
                    result = doc2qra.convert(
                        file_path=tmp_path,
                        scope=persona.scope,
                        context=f"{persona.name} persona knowledge",
                        persona=persona.name,
                    )
                finally:
                    tmp_path.unlink(missing_ok=True)

                if "error" in result and result.get("qra_count", 0) == 0:
                    console.print(f" [red]ERROR: {result['error'][:80]}[/]")
                    continue

                qra_count = result.get("qra_count", 0)

                # Save QRA output alongside transcript
                qra_output_path = transcript.with_name(f"{transcript.stem}_qras.json")
                qra_data = {
                    "source": str(transcript),
                    "persona_id": persona.id,
                    "scope": persona.scope,
                    "qra_count": qra_count,
                    "extracted_at": datetime.now().isoformat(),
                }
                if "qras" in result:
                    qra_data["qras"] = result["qras"]
                if "summary" in result:
                    qra_data["summary"] = result["summary"]
                if "raw" in result:
                    qra_data["raw_output"] = result["raw"]

                qra_output_path.write_text(json.dumps(qra_data, indent=2))

                state_mgr.mark_extracted(ExtractedContent(
                    source_path=str(transcript),
                    output_path=str(qra_output_path),
                    qra_count=qra_count,
                    extracted_at=datetime.now().isoformat(),
                    persona_id=persona.id,
                    scope=persona.scope,
                ))

                total_extracted += 1
                total_qras += qra_count
                console.print(f" [green]v[/] ({qra_count} QRAs)")

            except Exception as e:
                console.print(f" [red]ERROR: {e}[/]")

    console.print(f"\n[bold]=== Extracted {total_extracted} transcripts -> {total_qras} QRAs ===[/]")


def cmd_extract_shared(
    max_items: int = 50,
    dry_run: bool = False,
):
    """Extract QRAs from shared library documents for each relevant persona.

    Scans the shared library for documents, determines which personas
    should process each document via the relevance matrix, and calls
    doc2qra sequentially for each (document, persona) pair.

    All doc2qra calls are SEQUENTIAL to respect Chutes API concurrency limits.
    """
    import time
    import tempfile

    from state import get_state_manager
    from integrations import get_doc2qra
    from monitor_core import get_shared_library_config, get_all_personas

    shared_config = get_shared_library_config()
    if not shared_config:
        console.print("[yellow]No shared_library config in personas.yaml — skipping[/]")
        return

    library_path = Path(shared_config.path)
    if not library_path.exists():
        console.print(f"[yellow]Shared library path does not exist: {library_path}[/]")
        return

    state_mgr = get_state_manager()
    doc2qra = get_doc2qra()

    if not doc2qra.is_available():
        console.print("[red]ERROR: /doc2qra skill not available[/]")
        return

    # Build persona lookup by ID
    all_personas = {p.id: p for p in get_all_personas()}

    # Scan all documents in shared library subdirectories
    doc_extensions = {".md", ".txt", ".pdf", ".json"}
    documents = []
    for subdir_name, subdir_path in shared_config.subdirs.items():
        full_subdir = library_path / subdir_path
        if not full_subdir.exists():
            continue
        for doc_file in sorted(full_subdir.rglob("*")):
            if doc_file.is_file() and doc_file.suffix in doc_extensions:
                # Skip QRA output files and manifest
                if doc_file.name.endswith("_qras.json") or doc_file.name == ".manifest.json":
                    continue
                doc_type = shared_config.classify_document(
                    doc_file.name, source_type=subdir_name,
                )
                documents.append((doc_file, doc_type, subdir_name))

    if not documents:
        console.print("[dim]No documents found in shared library[/]")
        return

    console.print(f"[bold]Shared Library: {len(documents)} documents found[/]\n")

    total_processed = 0
    total_qras = 0

    for doc_file, doc_type, subdir_name in documents[:max_items]:
        if not doc_type:
            # Try classifying by subdirectory name
            doc_type = shared_config.classify_document("", source_type=subdir_name)
        if not doc_type:
            console.print(f"  [dim]Skipping {doc_file.name} (no relevance match)[/]")
            continue

        relevant_persona_ids = shared_config.get_relevant_personas(doc_type)
        if not relevant_persona_ids:
            continue

        console.print(f"\n[bold cyan]{doc_file.name}[/] [dim]({doc_type})[/]")
        console.print(f"  Relevant personas: {', '.join(relevant_persona_ids)}")

        for persona_id in relevant_persona_ids:
            persona = all_personas.get(persona_id)
            if not persona:
                continue

            # Check if already processed
            if state_mgr.is_shared_processed(str(doc_file), persona_id):
                console.print(f"  [dim]{persona.name}: already processed[/]")
                continue

            if dry_run:
                console.print(f"  [yellow][DRY RUN][/] Would extract for {persona.name}")
                continue

            console.print(f"  Extracting for {persona.name}...", end="")

            try:
                # For JSON transcript files, extract full_text
                if doc_file.suffix == ".json":
                    data = json.loads(doc_file.read_text())
                    text = data.get("full_text", data.get("text", ""))
                    title = data.get("meta", {}).get("title", doc_file.stem)
                    if len(text) < 100:
                        console.print(" [dim](too short)[/]")
                        state_mgr.mark_shared_processed(str(doc_file), persona_id)
                        continue
                    with tempfile.NamedTemporaryFile(
                        mode="w", suffix=".md", delete=False, prefix="sl_"
                    ) as tmp:
                        tmp.write(f"# {title}\n\n{text}")
                        input_path = Path(tmp.name)
                else:
                    input_path = doc_file

                result = doc2qra.convert(
                    file_path=input_path,
                    scope=persona.scope,
                    context=f"{persona.name} perspective on {doc_type}",
                    persona=persona.name,
                )

                # Clean up temp file if created
                if doc_file.suffix == ".json" and input_path != doc_file:
                    input_path.unlink(missing_ok=True)

                qra_count = result.get("qra_count", 0)
                total_qras += qra_count
                total_processed += 1

                state_mgr.mark_shared_processed(str(doc_file), persona_id)
                console.print(f" [green]v[/] ({qra_count} QRAs)")

                # Rate limiting between doc2qra calls
                time.sleep(5)

            except Exception as e:
                console.print(f" [red]ERROR: {e}[/]")

    console.print(f"\n[bold]=== Shared Library: {total_processed} extractions -> {total_qras} QRAs ===[/]")


def cmd_classify_streams(
    persona_id: Optional[str] = None,
    dry_run: bool = False,
):
    """Classify content into Intent or Persona streams.

    Intent stream: Hidden reasoning for query routing
    Persona stream: Visible reasoning for persona fine-tuning
    """
    from state import get_state_manager

    state_mgr = get_state_manager()
    taxonomy = get_taxonomy()

    stats = state_mgr.get_stream_stats()

    console.print("[bold]Stream Classification Status[/]")
    console.print(f"  Intent stream: {stats['intent']} items")
    console.print(f"  Persona stream: {stats['persona']} items")
    console.print(f"  Total classified: {stats['total']} items")

    if dry_run:
        console.print("\n[yellow][DRY RUN] Would classify pending content[/]")
        return

    raise NotImplementedError("classify-streams not yet implemented")


def cmd_archive_sessions(
    hours: int = 24,
    dry_run: bool = False,
):
    """Archive sessions to episodic memory.

    Stores full session context for reflection and training data.
    """
    from integrations import get_episodic_archiver

    archiver = get_episodic_archiver()

    if not archiver.is_available():
        console.print("[yellow]Episodic archiver skill not available[/]")
        console.print("Install: .pi/skills/episodic-archiver")
        return

    if dry_run:
        console.print(f"[yellow][DRY RUN] Would archive sessions from last {hours} hours[/]")
        return

    raise NotImplementedError("archive-sessions not yet implemented")


def cmd_verify_edges(
    collection: str = "operational",
    dry_run: bool = False,
):
    """Verify relationships with existing knowledge.

    Uses /edge-verifier to check verifies/contradicts/related relationships.
    """
    from integrations import get_edge_verifier

    verifier = get_edge_verifier()

    if not verifier.is_available():
        console.print("[yellow]Edge verifier skill not available[/]")
        console.print("Install: .pi/skills/edge-verifier")
        return

    if dry_run:
        console.print(f"[yellow][DRY RUN] Would verify edges in {collection} collection[/]")
        return

    raise NotImplementedError("verify-edges not yet implemented")


def cmd_reflect_on_gaps(
    max_gaps: int = 5,
    dry_run: bool = False,
):
    """Research knowledge gaps via /dogpile.

    Finds unresolved gaps and triggers research to fill them.
    """
    from state import get_state_manager

    state_mgr = get_state_manager()
    pending_gaps = state_mgr.get_pending_gaps()

    console.print(f"[bold]Pending Knowledge Gaps: {len(pending_gaps)}[/]")

    if not pending_gaps:
        console.print("[green]No unresolved gaps![/]")
        return

    table = Table(show_header=True, header_style="bold cyan", box=None)
    table.add_column("Gap ID", style="dim", width=25)
    table.add_column("Description", width=50)
    table.add_column("Persona", width=15)

    for gap in pending_gaps[:max_gaps]:
        table.add_row(gap.gap_id, gap.description[:50], gap.persona_id)

    console.print(table)

    if dry_run:
        console.print(f"\n[yellow][DRY RUN] Would research {min(max_gaps, len(pending_gaps))} gaps[/]")
        return

    raise NotImplementedError("reflect not yet implemented — use /dogpile directly")


def cmd_train_personas(
    persona_id: Optional[str] = None,
    dry_run: bool = False,
):
    """Generate training data and trigger train-persona.

    Exports episodic data and trains LoRA models for personas.
    """
    from state import get_state_manager

    state_mgr = get_state_manager()
    training_state = state_mgr.load_training_state()

    personas = get_all_personas()

    console.print("[bold]Persona Training Status[/]\n")

    table = Table(show_header=True, header_style="bold cyan", box=None)
    table.add_column("Persona", width=20)
    table.add_column("Last Trained", width=20)
    table.add_column("Version", justify="right", width=8)
    table.add_column("Samples", justify="right", width=10)

    for persona in personas:
        if persona_id and persona.id != persona_id:
            continue

        ts = training_state.get(persona.id)
        if ts:
            table.add_row(
                persona.name,
                ts.last_trained or "[dim]Never[/]",
                str(ts.model_version),
                str(ts.training_samples),
            )
        else:
            table.add_row(persona.name, "[dim]Never[/]", "0", "0")

    console.print(table)

    if dry_run:
        console.print("\n[yellow][DRY RUN] Would train persona models[/]")
        return

    raise NotImplementedError("train not yet implemented — use /train-persona directly")


def cmd_close_loop(
    dry_run: bool = False,
    persona_ids: Optional[list] = None,
    priority: Optional[str] = None,
):
    """Run the complete learning pipeline.

    Executes all implemented steps in sequence:
    0. curate - Discover content per persona dynamically
    1. check-all - Check all sources
    2. ingest - Ingest new YouTube content
    3. extract - Extract QRAs via /doc2qra (per-persona, from own transcripts)
    4. extract-shared - Extract QRAs from shared library (per-persona, from shared docs)
    5. learn - Learn to memory with taxonomy
    6. classify-streams - Classify Intent/Persona (pending)
    7. archive - Archive sessions (pending)
    8. verify-edges - Verify relationships (pending)
    9. reflect - Research gaps (pending)
    """
    from monitor_commands import cmd_check, cmd_ingest, cmd_learn
    from curate import cmd_curate
    from state import get_state_manager

    state_mgr = get_state_manager()

    console.print("[bold]Close Loop - Full Pipeline Execution[/]\n")

    # Step 0: Curate new content for personas
    console.print("[bold cyan]Step 0/10:[/] Curating content for personas...")
    try:
        cmd_curate(dry_run=dry_run, persona_ids=persona_ids)
    except Exception as e:
        console.print(f"  [red]Curate failed: {e}[/]")

    # Step 1: Check all sources
    console.print(f"\n[bold cyan]Step 1/10:[/] Checking all sources...")
    try:
        cmd_check_all(priority=priority, json_output=False, persona_ids=persona_ids)
    except Exception as e:
        console.print(f"  [red]Check failed: {e}[/]")

    # Step 2: Ingest new content (YouTube)
    console.print(f"\n[bold cyan]Step 2/10:[/] Ingesting new content...")
    try:
        cmd_ingest(priority=priority, dry_run=dry_run)
    except Exception as e:
        console.print(f"  [red]Ingest failed: {e}[/]")

    # Step 3: Extract QRAs via /doc2qra (per-persona, own transcripts)
    console.print(f"\n[bold cyan]Step 3/10:[/] Extracting QRAs via /doc2qra...")
    try:
        persona_id = persona_ids[0] if persona_ids and len(persona_ids) == 1 else None
        cmd_extract_qras(persona_id=persona_id, dry_run=dry_run)
    except Exception as e:
        console.print(f"  [red]Extract failed: {e}[/]")

    # Step 4: Extract shared library QRAs (per-persona, from shared docs)
    console.print(f"\n[bold cyan]Step 4/10:[/] Extracting shared library QRAs (per-persona fan-out)...")
    try:
        cmd_extract_shared(dry_run=dry_run)
    except Exception as e:
        console.print(f"  [red]Shared library extract failed: {e}[/]")

    # Step 5: Learn to memory
    console.print(f"\n[bold cyan]Step 5/10:[/] Learning to memory with taxonomy...")
    try:
        persona_id = persona_ids[0] if persona_ids and len(persona_ids) == 1 else None
        cmd_learn(persona_id=persona_id, dry_run=dry_run)
    except Exception as e:
        console.print(f"  [red]Learn failed: {e}[/]")

    # Steps 6-9: Not yet implemented — skip with warning
    pending_steps = [
        ("6/10", "Classify streams"),
        ("7/10", "Archive sessions"),
        ("8/10", "Verify edges"),
        ("9/10", "Reflect on gaps"),
    ]
    for step_num, step_desc in pending_steps:
        console.print(f"\n[bold cyan]Step {step_num}:[/] {step_desc} [yellow](skipped — not yet implemented)[/]")

    # Show pipeline status summary
    console.print("\n[bold]Pipeline complete.[/]")

    status = state_mgr.get_pipeline_status()
    curate = status.get("curate_queue", {})
    console.print("\n[bold]Pipeline Status:[/]")
    console.print(f"  Personas monitored: {status['personas_monitored']}")
    if curate.get("total", 0) > 0:
        console.print(f"  Curate queue: {curate.get('unconsumed', 0)} pending / {curate['total']} total")
    console.print(f"  Transcripts learned: {status['transcripts_learned']}")
    console.print(f"  Content extracted: {status['content_extracted']}")
    console.print(f"  Pending gaps: {status['pending_gaps']}")
    console.print(f"  Trained personas: {status['trained_personas']}")


def cmd_pipeline_status():
    """Show overall pipeline status."""
    from state import get_state_manager

    state_mgr = get_state_manager()
    status = state_mgr.get_pipeline_status()

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")

    curate = status.get("curate_queue", {})
    curate_total = curate.get("total", 0)
    curate_pending = curate.get("unconsumed", 0)

    table.add_row("Last Check", status.get("last_check", "[dim]Never[/]"))
    table.add_row("Personas Monitored", str(status.get("personas_monitored", 0)))
    table.add_row("Curate Queue", f"{curate_pending} pending / {curate_total} total")
    if curate.get("by_type"):
        types_str = ", ".join(f"{t}: {c}" for t, c in sorted(curate["by_type"].items()))
        table.add_row("  By Type", f"[dim]{types_str}[/]")
    table.add_row("Transcripts Learned", str(status.get("transcripts_learned", 0)))
    table.add_row("Content Extracted", str(status.get("content_extracted", 0)))
    table.add_row("Intent Stream", str(status.get("stream_classification", {}).get("intent", 0)))
    table.add_row("Persona Stream", str(status.get("stream_classification", {}).get("persona", 0)))
    table.add_row("Pending Gaps", str(status.get("pending_gaps", 0)))
    table.add_row("Total Gaps", str(status.get("total_gaps", 0)))
    table.add_row("Trained Personas", str(status.get("trained_personas", 0)))

    panel = Panel(
        table,
        title="[bold]Pipeline Status[/]",
        border_style="green",
    )
    console.print(panel)
