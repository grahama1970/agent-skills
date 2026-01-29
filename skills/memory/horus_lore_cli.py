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
import argparse
import json
import sys
from pathlib import Path
from typing import Any

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

def handle_query(args, db, embedder) -> None:
    """Handle query command."""
    results = query_lore(
        db,
        args.query_text,
        embedder,
        top_k=args.top_k,
        entity_filter=args.entity,
        content_type=args.content_type,
        canon_boost=args.canon_boost,
        include_graph=not args.no_graph,
    )

    print(f"\n=== Query Results for: '{args.query_text}' ===\n")
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


def handle_persona(args, db, embedder) -> None:
    """Handle persona command."""
    print(f"\n=== Retrieving Horus's Context for: '{args.query_text}' ===")
    print("(This is what shapes his response - his 'subconscious' recall)")

    context = retrieve_persona_context(
        db,
        args.query_text,
        embedder,
        canon_k=args.canon_k,
        supplementary_k=args.supp_k,
        episodic_k=args.episodic_k,
    )

    if getattr(args, 'json', False):
        # Raw JSON output
        import copy
        output = copy.deepcopy(context)
        # Convert entities set to list for JSON
        output["entities_mentioned"] = list(output.get("entities_mentioned", []))
        print(json.dumps(output, indent=2, default=str))
        return

    if args.format:
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


def handle_enrich(args, db) -> None:
    """Handle enrich command."""
    output_dir = Path("/tmp/horus_lore_enrich")
    output_dir.mkdir(exist_ok=True)

    if args.dry_run:
        # Just count what needs enrichment
        count = list(db.aql.execute("""
            RETURN LENGTH(FOR doc IN horus_lore_docs FILTER doc.abstract == null RETURN 1)
        """))[0]
        print(f"Documents needing enrichment: {count}")
        return

    # Prepare batch file
    batch_file = output_dir / "enrich_batch.jsonl"
    count = prepare_enrichment_batch(db, batch_file, limit=args.limit)

    if count > 0:
        print(f"\nBatch file ready: {batch_file}")
        print(f"\nTo run enrichment with scillm:")
        print(f"  cd {SKILL_DIR.parent / 'scillm'}")
        print(f"  python batch.py submit {batch_file}")
        print(f"\nAfter completion, apply results:")
        print(f"  python {__file__} apply-enrichment --results <results_file>")


# =============================================================================
# Main
# =============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="Horus Lore Ingestion Pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # YouTube subcommand
    yt_parser = subparsers.add_parser("youtube", help="Ingest YouTube transcripts")
    yt_parser.add_argument("--input", "-i", required=True, help="Directory with JSON transcripts")

    # Audiobook subcommand
    ab_parser = subparsers.add_parser("audiobook", help="Ingest audiobook transcripts")
    ab_parser.add_argument("--input", "-i", required=True, help="Directory with audiobook folders")

    # All subcommand
    all_parser = subparsers.add_parser("all", help="Ingest both sources")
    all_parser.add_argument("--youtube-dir", help="YouTube transcripts directory")
    all_parser.add_argument("--audiobook-dir", help="Audiobook directory")

    # Status subcommand
    subparsers.add_parser("status", help="Show ingestion status")

    # Setup subcommand
    subparsers.add_parser("setup", help="Create collections, indexes, views, and graph")

    # Edges subcommand
    subparsers.add_parser("edges", help="Create/update edges between documents")

    # Plot edges subcommand (after enrichment)
    subparsers.add_parser("plot-edges", help="Create plot-point edges (run after enrichment)")

    # Query subcommand
    query_parser = subparsers.add_parser("query", help="Test hybrid search")
    query_parser.add_argument("query_text", help="Query string")
    query_parser.add_argument("--top-k", type=int, default=5, help="Number of results")
    query_parser.add_argument("--entity", action="append", help="Filter by entity (can repeat)")
    query_parser.add_argument("--content-type", choices=["canon", "supplementary"], help="Filter by content type")
    query_parser.add_argument("--canon-boost", type=float, default=1.5, help="Boost factor for canon content")
    query_parser.add_argument("--no-graph", action="store_true", help="Disable graph traversal")

    # Persona subcommand - unified retrieval for Horus's "subconscious"
    persona_parser = subparsers.add_parser("persona", help="Test persona context retrieval (Horus's subconscious)")
    persona_parser.add_argument("query_text", help="User query to Horus")
    persona_parser.add_argument("--canon-k", type=int, default=3, help="Canon results (audiobooks)")
    persona_parser.add_argument("--supp-k", type=int, default=2, help="Supplementary results (YouTube)")
    persona_parser.add_argument("--episodic-k", type=int, default=3, help="Episodic results (past conversations)")
    persona_parser.add_argument("--format", action="store_true", help="Show formatted context for system prompt")
    persona_parser.add_argument("--json", action="store_true", help="Output raw JSON")

    # Enrich subcommand (LLM batch processing)
    enrich_parser = subparsers.add_parser("enrich", help="LLM batch enrichment (abstracts, cleaning)")
    enrich_parser.add_argument("--limit", type=int, default=0, help="Limit docs to process (0=all)")
    enrich_parser.add_argument("--dry-run", action="store_true", help="Show what would be processed")

    # Apply enrichment results
    apply_parser = subparsers.add_parser("apply-enrichment", help="Apply scillm batch results")
    apply_parser.add_argument("--results", "-r", required=True, help="Path to results JSONL file")

    args = parser.parse_args()

    # Connect to DB
    db = get_db()
    print(f"Connected to ArangoDB: {db.name}")

    if args.command == "status":
        show_status(db)
        return

    # Ensure collections exist
    collections = ensure_collections(db)
    ensure_search_views(db)
    ensure_graph(db)

    if args.command == "setup":
        print("Setup complete.")
        return

    if args.command == "edges":
        print("Creating edges...")
        edge_counts = create_edges(db, collections)
        print(f"Edge counts by type: {edge_counts}")
        return

    if args.command == "plot-edges":
        print("Creating plot-point edges (requires enriched chapters)...")
        edge_counts = create_plot_point_edges(db, collections)
        print(f"Plot edge counts by type: {edge_counts}")
        return

    if args.command == "query":
        print("Loading embedder...")
        embedder = get_embedder()
        handle_query(args, db, embedder)
        return

    if args.command == "persona":
        print("Loading embedder...")
        embedder = get_embedder()
        handle_persona(args, db, embedder)
        return

    if args.command == "enrich":
        handle_enrich(args, db)
        return

    if args.command == "apply-enrichment":
        results_path = Path(args.results).expanduser()
        if not results_path.exists():
            print(f"Results file not found: {results_path}")
            sys.exit(1)

        print(f"Applying enrichment results from: {results_path}")
        stats = apply_enrichment_results(db, results_path)
        print(f"\nEnrichment applied:")
        print(f"  Success: {stats['success']}")
        print(f"  Errors: {stats['errors']}")
        return

    # Get embedder for ingestion
    print("Loading embedder...")
    embedder = get_embedder()

    if args.command == "youtube":
        input_dir = Path(args.input).expanduser()
        if not input_dir.exists():
            print(f"Input directory not found: {input_dir}")
            sys.exit(1)
        results = ingest_youtube_directory(input_dir, collections, embedder)
        print(f"\nYouTube ingestion complete:")
        print(f"  Documents: {results['total_docs']}")
        print(f"  Chunks: {results['total_chunks']}")
        print(f"  Skipped: {results['skipped']}")
        if results["errors"]:
            print(f"  Errors: {len(results['errors'])}")
            for err in results["errors"][:5]:
                print(f"    - {err}")

    elif args.command == "audiobook":
        input_dir = Path(args.input).expanduser()
        if not input_dir.exists():
            print(f"Input directory not found: {input_dir}")
            sys.exit(1)
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

    elif args.command == "all":
        ran_any = False
        if args.youtube_dir:
            yt_dir = Path(args.youtube_dir).expanduser()
            print(f"\n--- Ingesting YouTube from {yt_dir} ---")
            if yt_dir.exists():
                yt_results = ingest_youtube_directory(yt_dir, collections, embedder)
                print(f"YouTube: {yt_results['total_docs']} docs, {yt_results['total_chunks']} chunks")
                ran_any = True
            else:
                print(f"Skipping YouTube: directory not found: {yt_dir}")

        if args.audiobook_dir:
            ab_dir = Path(args.audiobook_dir).expanduser()
            print(f"\n--- Ingesting Audiobooks from {ab_dir} ---")
            if ab_dir.exists():
                ab_results = ingest_audiobook_directory(ab_dir, collections, embedder)
                print(f"Audiobooks: {ab_results['total_docs']} docs, {ab_results['total_chunks']} chunks")
                ran_any = True
            else:
                print(f"Skipping Audiobooks: directory not found: {ab_dir}")

        if not ran_any:
            print("No valid input directories found for 'all' command.")
            sys.exit(1)

        # Create edges after ingesting
        print("\n--- Creating edges ---")
        edge_counts = create_edges(db, collections)
        print(f"Edges created: {edge_counts}")

    # Show final status
    print("\n")
    show_status(db)


if __name__ == "__main__":
    main()
