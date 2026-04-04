#!/usr/bin/env python3
"""
Horus Lore Ingest CLI - Main Entry Point
Thin wrapper that imports from modular components.

Two-level RAG storage for persona retrieval:
1. horus_lore_docs  - Full documents (chapters, videos) for context
2. horus_lore_chunks - Fine-grained chunks for semantic retrieval

Query flow:
1. Search chunks -> find relevant content
2. Get parent doc_id -> load full document
3. Feed full document (or rolling window) to LLM for persona response

Uses entity tagging (rule-based) and semantic embeddings - NO LLM calls.

Usage:
    # Ingest YouTube transcripts
    python horus_lore_cli.py youtube --input /path/to/transcripts/

    # Ingest audiobook transcripts
    python horus_lore_cli.py audiobook --input ~/clawd/library/books/

    # Ingest both
    python horus_lore_cli.py all --youtube-dir /path/to/yt --audiobook-dir ~/clawd/library/books/

    # Check status
    python horus_lore_cli.py status

    # Query example (retrieves chunks, returns full doc)
    python horus_lore_cli.py query "What happened on Davin?"

    # Persona context retrieval (for Horus's subconscious)
    python horus_lore_cli.py persona "Tell me about your brothers"
"""
import typer
import json
import sys
from pathlib import Path
from typing import Any, Optional

# Add this directory to path for imports
SKILL_DIR = Path(__file__).parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

# Import from modules
from horus_lore_config import ALL_ENTITIES
from horus_lore_embeddings import get_embedder
from horus_lore_storage import (
    get_db,
    ensure_collections,
    ensure_search_views,
    ensure_graph,
    create_edges,
    create_plot_point_edges,
)
from horus_lore_query import (
    query_lore,
    retrieve_persona_context,
    format_persona_context,
)
from horus_lore_ingest import (
    ingest_youtube_directory,
    ingest_audiobook_directory,
)
from horus_lore_enrichment import (
    prepare_enrichment_batch,
    apply_enrichment_results,
)
from preset_storage import compile_spec, upsert_preset


# =============================================================================
# Status Display
# =============================================================================

def show_status(db: Any) -> None:
    """Show current ingestion status."""
    print("\n=== Horus Lore Status ===")

    # Check documents collection
    if db.has_collection("horus_lore_docs"):
        docs_col = db.collection("horus_lore_docs")
        docs_count = docs_col.count()
        print(f"\nDocuments (horus_lore_docs): {docs_count}")

        # By source
        doc_sources = list(db.aql.execute("""
            FOR doc IN horus_lore_docs
            COLLECT source = doc.source WITH COUNT INTO count
            RETURN {source, count}
        """))
        for ds in doc_sources:
            print(f"  {ds['source']}: {ds['count']} docs")

        # Series breakdown
        series_counts = list(db.aql.execute("""
            FOR doc IN horus_lore_docs
            FILTER doc.source_meta.series != null
            COLLECT series = doc.source_meta.series WITH COUNT INTO count
            SORT count DESC
            RETURN {series, count}
        """))
        if series_counts:
            print("\nBy series:")
            for sc in series_counts:
                print(f"  {sc['series']}: {sc['count']} books")
    else:
        print("\nDocuments collection not created yet.")

    # Check chunks collection
    if db.has_collection("horus_lore_chunks"):
        chunks_col = db.collection("horus_lore_chunks")
        chunks_count = chunks_col.count()
        print(f"\nChunks (horus_lore_chunks): {chunks_count}")

        # By source
        chunk_sources = list(db.aql.execute("""
            FOR chunk IN horus_lore_chunks
            COLLECT source = chunk.source WITH COUNT INTO count
            RETURN {source, count}
        """))
        for cs in chunk_sources:
            print(f"  {cs['source']}: {cs['count']} chunks")
    else:
        print("\nChunks collection not created yet.")

    # Check edges
    if db.has_collection("horus_lore_edges"):
        edges_col = db.collection("horus_lore_edges")
        edges_count = edges_col.count()
        print(f"\nEdges (horus_lore_edges): {edges_count}")

        # By type
        edge_types = list(db.aql.execute("""
            FOR edge IN horus_lore_edges
            COLLECT type = edge.type WITH COUNT INTO count
            RETURN {type, count}
        """))
        for et in edge_types:
            print(f"  {et['type']}: {et['count']} edges")
    else:
        print("\nEdges collection not created yet.")

    # Top entities across all docs
    if db.has_collection("horus_lore_docs"):
        top_entities = list(db.aql.execute("""
            FOR doc IN horus_lore_docs
            FOR entity IN doc.entities
            COLLECT name = entity WITH COUNT INTO count
            SORT count DESC
            LIMIT 15
            RETURN {name, count}
        """))
        if top_entities:
            print("\nTop 15 entities across documents:")
            for ent in top_entities:
                print(f"  {ent['name']}: {ent['count']} docs")


# =============================================================================
# Command Handlers
# =============================================================================

def handle_query(
    query_text: str,
    db,
    embedder,
    top_k: int = 5,
    entity: Optional[list[str]] = None,
    content_type: Optional[str] = None,
    canon_boost: float = 1.5,
    no_graph: bool = False,
) -> None:
    """Handle query command."""
    results = query_lore(
        db,
        query_text,
        embedder,
        top_k=top_k,
        entity_filter=entity,
        content_type=content_type,
        canon_boost=canon_boost,
        include_graph=not no_graph,
    )

    print(f"\n=== Query Results for: '{query_text}' ===\n")
    for i, r in enumerate(results):
        source_info = r.get("source_meta", {})
        title = source_info.get("title") or source_info.get("book_title") or "Unknown"
        via = " (via graph)" if r.get("via_graph") else ""
        print(f"{i + 1}. [{r['source']}] {title}{via}")
        print(f"   Score: {r['score']:.3f} | Words: {r.get('word_count', 'N/A')} | Entities: {len(r.get('entities', []))}")
        if r.get("abstract"):
            print(f"   Abstract: {r['abstract']}")
        if r.get("entities"):
            print(f"   Key entities: {', '.join(r['entities'][:10])}")
        # Show preview of text (prefer lore_text if available)
        text = r.get("lore_text") or r.get("full_text", "")
        preview = text[:300].replace("\n", " ")
        print(f"   Preview: {preview}...")
        print()


def handle_persona(
    query_text: str,
    db,
    embedder,
    canon_k: int = 3,
    supp_k: int = 2,
    episodic_k: int = 3,
    as_json: bool = False,
    format_output: bool = False,
) -> None:
    """Handle persona command."""
    print(f"\n=== Retrieving Horus's Context for: '{query_text}' ===")
    print("(This is what shapes his response - his 'subconscious' recall)")

    context = retrieve_persona_context(
        db,
        query_text,
        embedder,
        canon_k=canon_k,
        supplementary_k=supp_k,
        episodic_k=episodic_k,
    )

    if as_json:
        # Raw JSON output
        import copy
        output = copy.deepcopy(context)
        # Convert entities set to list for JSON
        output["entities_mentioned"] = list(output.get("entities_mentioned", []))
        print(json.dumps(output, indent=2, default=str))
        return

    if format_output:
        # Show formatted context for system prompt
        formatted = format_persona_context(context)
        print("\n" + "=" * 60)
        print("FORMATTED PERSONA CONTEXT (inject into system prompt):")
        print("=" * 60)
        print(formatted)
        return

    # Default: human-readable summary
    print(f"\n--- MOOD SIGNALS ---")
    if context.get("mood_signals"):
        for signal in context["mood_signals"]:
            print(f"  Warning: {signal}")
    else:
        print("  (none detected)")

    print(f"\n--- ESCAPE RELEVANCE: {context.get('escape_relevance', 0):.2f} ---")
    if context.get("escape_relevance", 0) > 0.3:
        print("  Query relates to Horus's primary drive (escape/freedom)")

    print(f"\n--- CANON (what Horus lived) ---")
    for i, item in enumerate(context.get("canon", []), 1):
        meta = item.get("source_meta", {})
        title = meta.get("book_title", "Unknown")
        chapter = meta.get("chapter", "")
        print(f"  {i}. [{title}] {chapter}")
        print(f"     Score: {item.get('score', 0):.3f}")
        if item.get("abstract"):
            print(f"     -> {item['abstract'][:150]}...")

    print(f"\n--- SUPPLEMENTARY (lore analysis) ---")
    for i, item in enumerate(context.get("supplementary", []), 1):
        meta = item.get("source_meta", {})
        title = meta.get("title", "Unknown")
        print(f"  {i}. [{title}]")
        print(f"     Score: {item.get('score', 0):.3f}")
        if item.get("abstract"):
            print(f"     -> {item['abstract'][:150]}...")

    print(f"\n--- EPISODIC (past conversations) ---")
    for i, item in enumerate(context.get("episodic", []), 1):
        cat = item.get("category", "interaction")
        msg = (item.get("message") or "")[:100]
        print(f"  {i}. [{cat}] {msg}...")
        print(f"     Score: {item.get('score', 0):.3f}")

    print(f"\n--- ENTITIES IN CONTEXT ---")
    entities = context.get("entities_mentioned", [])
    if entities:
        print(f"  {', '.join(entities[:15])}")
        if len(entities) > 15:
            print(f"  ... and {len(entities) - 15} more")
    else:
        print("  (none)")


def handle_enrich(db, limit: int = 0, dry_run: bool = False) -> None:
    """Handle enrich command."""
    output_dir = Path("/tmp/horus_lore_enrich")
    output_dir.mkdir(exist_ok=True)

    if dry_run:
        # Just count what needs enrichment
        count = list(db.aql.execute("""
            RETURN LENGTH(FOR doc IN horus_lore_docs FILTER doc.abstract == null RETURN 1)
        """))[0]
        print(f"Documents needing enrichment: {count}")
        return

    # Prepare batch file
    batch_file = output_dir / "enrich_batch.jsonl"
    count = prepare_enrichment_batch(db, batch_file, limit=limit)

    if count > 0:
        print(f"\nBatch file ready: {batch_file}")
        print(f"\nTo run enrichment with scillm:")
        print(f"  cd {SKILL_DIR.parent / 'scillm'}")
        print(f"  python batch.py submit {batch_file}")
        print(f"\nAfter completion, apply results:")
        print(f"  python {__file__} apply-enrichment --results <results_file>")


def handle_preset(
    action: str,
    db,
    query: Optional[str] = None,
    ids: Optional[str] = None,
    overrides: Optional[str] = None,
    strict: bool = False,
) -> None:
    """Handle preset command."""
    if action == "compile":
        try:
            input_ids = json.loads(ids) if ids else {}
        except json.JSONDecodeError:
            print("Error: --ids and --overrides must be valid JSON")
            sys.exit(1)

        parsed_overrides = json.loads(overrides) if overrides else {}
        spec = compile_spec(db, input_ids, parsed_overrides, strict)
        print(json.dumps(spec, indent=2))
        
    elif action == "list":
        # List sets first (primary affordance)
        sets = list(db.aql.execute("FOR s IN preset_sets RETURN s"))
        print("\n=== Director Personas & Preset Sets ===")
        for s in sets:
            print(f"• {s['title']} ({s['_key']}) - {s.get('description', '')}")
            
    elif action == "sanity":
        print("\n=== Running Preset Sanity Check ===")
        print("Validating all Preset Sets for cycles, missing ref, and evidence integrity...\n")
        
        sets = list(db.aql.execute("FOR s IN preset_sets RETURN s"))
        errors = 0
        warnings = 0
        passed = 0
        
        REQUIRED_CATEGORIES = ["camera", "lens", "lighting", "audio", "grade"]
        
        for s in sets:
            sid = s["_key"]
            status = "✓"
            notes = []
            
            # 1. Compilation Check (Strict Mode)
            try:
                # Compile with strict mode to catch missing IDs / cycles
                spec = compile_spec(db, {"set": sid}, strict=True)
                
                # Check for category completeness
                missing_cats = [c for c in REQUIRED_CATEGORIES if c not in spec.get("resolved_ids", {})]
                set_type = s.get("set_type", "complete")
                
                if missing_cats:
                    if set_type == "complete":
                        notes.append(f"INCOMPLETE: Set '{sid}' (COMPLETE) missing {missing_cats}")
                        status = "✗"
                        errors += 1
                    else:
                        notes.append(f"PARTIAL: Set '{sid}' missing {missing_cats}")
                        if status == "✓": status = "!"
                        warnings += 1
            except ValueError as e:
                status = "✗"
                errors += 1
                notes.append(f"ERROR: {str(e)}")
            except Exception as e:
                status = "✗"
                errors += 1
                notes.append(f"ERROR (Unexpected): {str(e)}")
            else:
                # 5. Evidence Check (Sets)
                # Check for existing refs in preset_refs where _from == sid
                set_edges = list(db.aql.execute("FOR e IN preset_refs FILTER e._from == @sid RETURN e", bind_vars={"sid": f"preset_sets/{sid}"}))
                if set_type == "complete" and not set_edges:
                     # Only warning for now as we haven't seeded full evidence
                     notes.append("WARNING: 0 Evidence Refs (Should have >= 3 pos, >= 1 neg)")
                     if status == "✓": status = "!"
                     warnings += 1
                
                passed += 1
                
            print(f"{status} Set: {sid}")
            for n in notes:
                print(f"    - {n}")
                
        # Also check all individual presets for broken media links and valid timecodes
        print("\n--- Verifying Evidence Links (Components) ---")
        presets = list(db.aql.execute("FOR p IN presets RETURN p"))
        for p in presets:
            pid = p["_key"]
            # Check outbound edges integrity
            edges = list(db.aql.execute("""
                FOR edge IN preset_refs
                FILTER edge._from == @pid
                LET target = DOCUMENT(edge._to)
                RETURN {
                    to: edge._to, 
                    target_exists: (target != null),
                    tc_in: edge.tc_in_s,
                    tc_out: edge.tc_out_s
                }
            """, bind_vars={"pid": f"presets/{pid}"}))
            
            for edge in edges:
                # 1. Broken Link (Fatal Error)
                if not edge.get("target_exists"):
                    print(f"✗ Preset '{pid}' has BROKEN LINK -> {edge.get('to')}")
                    errors += 1
                
                # 2. Missing Timecodes (Warning)
                elif edge.get("tc_in") is None or edge.get("tc_out") is None:
                    print(f"! Preset '{pid}' has MISSING TIMECODES -> {edge.get('to')}")
                    warnings += 1

                # 3. Invalid Timecode Logic (Fatal Error)
                elif edge.get("tc_in") is not None and edge.get("tc_out") is not None and edge.get("tc_in") >= edge.get("tc_out"):
                    print(f"✗ Preset '{pid}' has INVALID TIMECODE LOGIC (in >= out) -> {edge.get('to')}")
                    errors += 1
        
        print(f"\nSummary: {passed} Passed, {errors} Errors, {warnings} Warnings")
        
        if errors > 0:
            print("\n[red]Sanity Check FAILED (Fatal errors found).[/red]")
            sys.exit(1)
        elif warnings > 0:
             print(f"\n[yellow]Sanity Check PASSED with {warnings} warnings.[/yellow]")
             sys.exit(0)
        else:
            print("\n[green]Sanity Check PASSED (Clean).[/green]")

    elif action == "search":
        print(f"\nSearching presets for: '{query}'")
        # Simple wildcard search on tags/title for now
        # Ideally use the memory_view_preset logic if strict semantic match needed
        q = query.lower()
        query = """
            FOR p IN presets
            FILTER CONTAINS(LOWER(p.title), @q) OR @q IN p.tags OR CONTAINS(LOWER(p.description), @q)
            RETURN p
        """
        results = list(db.aql.execute(query, bind_vars={"q": q}))
        for r in results:
            print(f"• [{r['type'].upper()}] {r['title']} ({r['_key']})")


# =============================================================================
# Typer App
# =============================================================================

app = typer.Typer(help="Horus Lore Ingestion Pipeline")


def _connect_db():
    """Connect to ArangoDB."""
    db = get_db()
    print(f"Connected to ArangoDB: {db.name}")
    return db


def _setup_collections(db):
    """Ensure all collections, views, and graph exist."""
    collections = ensure_collections(db)
    ensure_search_views(db)
    ensure_graph(db)
    return collections


@app.command()
def youtube(
    input: str = typer.Option(..., "-i", "--input", help="Directory with JSON transcripts"),
):
    """Ingest YouTube transcripts."""
    db = _connect_db()
    collections = _setup_collections(db)
    print("Loading embedder...")
    embedder = get_embedder()

    input_dir = Path(input).expanduser()
    if not input_dir.exists():
        print(f"Input directory not found: {input_dir}")
        raise typer.Exit(code=1)

    results = ingest_youtube_directory(input_dir, collections, embedder)
    print(f"\nYouTube ingestion complete:")
    print(f"  Documents: {results['total_docs']}")
    print(f"  Chunks: {results['total_chunks']}")
    print(f"  Skipped: {results['skipped']}")
    if results["errors"]:
        print(f"  Errors: {len(results['errors'])}")
        for err in results["errors"][:5]:
            print(f"    - {err}")

    print("\n")
    show_status(db)


@app.command()
def audiobook(
    input: str = typer.Option(..., "-i", "--input", help="Directory with audiobook folders"),
):
    """Ingest audiobook transcripts."""
    db = _connect_db()
    collections = _setup_collections(db)
    print("Loading embedder...")
    embedder = get_embedder()

    input_dir = Path(input).expanduser()
    if not input_dir.exists():
        print(f"Input directory not found: {input_dir}")
        raise typer.Exit(code=1)

    results = ingest_audiobook_directory(input_dir, collections, embedder)
    print(f"\nAudiobook ingestion complete:")
    print(f"  Documents: {results['total_docs']}")
    print(f"  Chunks: {results['total_chunks']}")
    print(f"  Skipped: {results['skipped']}")
    if results["books"]:
        print(f"  Books ingested:")
        for book in results["books"][:10]:
            series_info = f" ({book['series']} #{book['series_number']})" if book.get("series") else ""
            print(f"    - {book['title']}{series_info}")
    if results["errors"]:
        print(f"  Errors: {len(results['errors'])}")

    print("\n")
    show_status(db)


@app.command("all")
def all_cmd(
    youtube_dir: Optional[str] = typer.Option(None, "--youtube-dir", help="YouTube transcripts directory"),
    audiobook_dir: Optional[str] = typer.Option(None, "--audiobook-dir", help="Audiobook directory"),
):
    """Ingest both sources."""
    db = _connect_db()
    collections = _setup_collections(db)
    print("Loading embedder...")
    embedder = get_embedder()

    ran_any = False
    if youtube_dir:
        yt_dir = Path(youtube_dir).expanduser()
        print(f"\n--- Ingesting YouTube from {yt_dir} ---")
        if yt_dir.exists():
            yt_results = ingest_youtube_directory(yt_dir, collections, embedder)
            print(f"YouTube: {yt_results['total_docs']} docs, {yt_results['total_chunks']} chunks")
            ran_any = True
        else:
            print(f"Skipping YouTube: directory not found: {yt_dir}")

    if audiobook_dir:
        ab_dir = Path(audiobook_dir).expanduser()
        print(f"\n--- Ingesting Audiobooks from {ab_dir} ---")
        if ab_dir.exists():
            ab_results = ingest_audiobook_directory(ab_dir, collections, embedder)
            print(f"Audiobooks: {ab_results['total_docs']} docs, {ab_results['total_chunks']} chunks")
            ran_any = True
        else:
            print(f"Skipping Audiobooks: directory not found: {ab_dir}")

    if not ran_any:
        print("No valid input directories found for 'all' command.")
        raise typer.Exit(code=1)

    # Create edges after ingesting
    print("\n--- Creating edges ---")
    edge_counts = create_edges(db, collections)
    print(f"Edges created: {edge_counts}")

    print("\n")
    show_status(db)


@app.command()
def status():
    """Show ingestion status."""
    db = _connect_db()
    show_status(db)


@app.command()
def setup():
    """Create collections, indexes, views, and graph."""
    db = _connect_db()
    _setup_collections(db)
    print("Setup complete.")


@app.command()
def edges():
    """Create/update edges between documents."""
    db = _connect_db()
    collections = _setup_collections(db)
    print("Creating edges...")
    edge_counts = create_edges(db, collections)
    print(f"Edge counts by type: {edge_counts}")


@app.command("plot-edges")
def plot_edges():
    """Create plot-point edges (run after enrichment)."""
    db = _connect_db()
    collections = _setup_collections(db)
    print("Creating plot-point edges (requires enriched chapters)...")
    edge_counts = create_plot_point_edges(db, collections)
    print(f"Plot edge counts by type: {edge_counts}")


@app.command()
def query(
    query_text: str = typer.Argument(..., help="Query string"),
    top_k: int = typer.Option(5, "--top-k", help="Number of results"),
    entity: Optional[list[str]] = typer.Option(None, help="Filter by entity (can repeat)"),
    content_type: Optional[str] = typer.Option(None, "--content-type", help="Filter by content type (canon, supplementary)"),
    canon_boost: float = typer.Option(1.5, "--canon-boost", help="Boost factor for canon content"),
    no_graph: bool = typer.Option(False, "--no-graph", help="Disable graph traversal"),
):
    """Test hybrid search."""
    db = _connect_db()
    _setup_collections(db)
    print("Loading embedder...")
    embedder = get_embedder()
    handle_query(query_text, db, embedder, top_k=top_k, entity=entity, content_type=content_type, canon_boost=canon_boost, no_graph=no_graph)


@app.command()
def persona(
    query_text: str = typer.Argument(..., help="User query to Horus"),
    canon_k: int = typer.Option(3, "--canon-k", help="Canon results (audiobooks)"),
    supp_k: int = typer.Option(2, "--supp-k", help="Supplementary results (YouTube)"),
    episodic_k: int = typer.Option(3, "--episodic-k", help="Episodic results (past conversations)"),
    format_output: bool = typer.Option(False, "--format", help="Show formatted context for system prompt"),
    as_json: bool = typer.Option(False, "--json", help="Output raw JSON"),
):
    """Test persona context retrieval (Horus's subconscious)."""
    db = _connect_db()
    _setup_collections(db)
    print("Loading embedder...")
    embedder = get_embedder()
    handle_persona(query_text, db, embedder, canon_k=canon_k, supp_k=supp_k, episodic_k=episodic_k, as_json=as_json, format_output=format_output)


@app.command()
def enrich(
    limit: int = typer.Option(0, help="Limit docs to process (0=all)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be processed"),
):
    """LLM batch enrichment (abstracts, cleaning)."""
    db = _connect_db()
    _setup_collections(db)
    handle_enrich(db, limit=limit, dry_run=dry_run)


@app.command("apply-enrichment")
def apply_enrichment(
    results: str = typer.Option(..., "-r", "--results", help="Path to results JSONL file"),
):
    """Apply scillm batch results."""
    db = _connect_db()
    _setup_collections(db)

    results_path = Path(results).expanduser()
    if not results_path.exists():
        print(f"Results file not found: {results_path}")
        raise typer.Exit(code=1)

    print(f"Applying enrichment results from: {results_path}")
    stats = apply_enrichment_results(db, results_path)
    print(f"  Success: {stats['success']}")
    print(f"  Errors: {stats['errors']}")


@app.command("preset")
def preset_cmd(
    action: str = typer.Argument(..., help="Action: list, search, compile, sanity, info"),
    query_str: Optional[str] = typer.Option(None, "-q", "--query", help="Search query"),
    ids: Optional[str] = typer.Option(None, help="JSON dict of preset IDs for compilation"),
    overrides: Optional[str] = typer.Option(None, help="JSON dict of overrides for compilation"),
    strict: bool = typer.Option(False, help="Enable strict mode for compilation"),
):
    """Manage filmmaking presets (lighting, camera, lens)."""
    db = _connect_db()
    _setup_collections(db)
    handle_preset(action, db, query=query_str, ids=ids, overrides=overrides, strict=strict)


if __name__ == "__main__":
    app()
