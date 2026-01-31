"""
Horus Lore Ingest - Storage Module
ArangoDB connection, collections, indexes, views, graph, and edge creation.
"""
import hashlib
import os
from typing import Any

# Import config for entity lookups in edge creation
import sys
from pathlib import Path
SKILL_DIR = Path(__file__).parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from horus_lore_config import ALL_ENTITIES, IMPORTANT_ENTITY_CATEGORIES


# =============================================================================
# ArangoDB Connection
# =============================================================================

from db import get_db


# =============================================================================
# Collections and Indexes
# =============================================================================

def ensure_collections(db: Any) -> dict[str, Any]:
    """Ensure all horus_lore collections exist with proper indexes."""
    collections = {}

    # Documents collection (full chapters/videos)
    if not db.has_collection("horus_lore_docs"):
        db.create_collection("horus_lore_docs")
        print("Created collection: horus_lore_docs")
    collections["docs"] = db.collection("horus_lore_docs")

    # Chunks collection (for retrieval)
    if not db.has_collection("horus_lore_chunks"):
        db.create_collection("horus_lore_chunks")
        print("Created collection: horus_lore_chunks")
    collections["chunks"] = db.collection("horus_lore_chunks")

    # Edges collection (for multi-hop traversal)
    if not db.has_collection("horus_lore_edges"):
        db.create_collection("horus_lore_edges", edge=True)
        print("Created collection: horus_lore_edges (edge)")
    collections["edges"] = db.collection("horus_lore_edges")

    # Create indexes on docs
    docs_indexes = {idx["name"] for idx in collections["docs"].indexes()}
    if "idx_source" not in docs_indexes:
        collections["docs"].add_persistent_index(fields=["source"], name="idx_source")
    if "idx_series" not in docs_indexes:
        collections["docs"].add_persistent_index(fields=["source_meta.series"], name="idx_series", sparse=True)

    # Create indexes on chunks
    chunks_indexes = {idx["name"] for idx in collections["chunks"].indexes()}
    if "idx_doc_id" not in chunks_indexes:
        collections["chunks"].add_persistent_index(fields=["doc_id"], name="idx_doc_id")
    if "idx_entities" not in chunks_indexes:
        collections["chunks"].add_persistent_index(fields=["entities[*]"], name="idx_entities")
    if "idx_source" not in chunks_indexes:
        collections["chunks"].add_persistent_index(fields=["source"], name="idx_source")

    return collections


def ensure_collection(db: Any) -> Any:
    """Backward compat - returns chunks collection."""
    collections = ensure_collections(db)
    return collections["chunks"]


# =============================================================================
# Search Views
# =============================================================================

def ensure_search_views(db: Any) -> None:
    """Create ArangoSearch views for hybrid search on both collections."""
    existing_views = [v["name"] for v in db.views()]

    # View for chunks (primary retrieval)
    if "horus_lore_chunks_search" not in existing_views:
        db.create_arangosearch_view(
            name="horus_lore_chunks_search",
            properties={
                "links": {
                    "horus_lore_chunks": {
                        "analyzers": ["text_en", "identity"],
                        "fields": {
                            "text": {"analyzers": ["text_en"]},
                            "entities": {"analyzers": ["identity"]},
                            "source": {"analyzers": ["identity"]},
                            "doc_id": {"analyzers": ["identity"]},
                            "source_meta": {
                                "fields": {
                                    "channel": {"analyzers": ["identity"]},
                                    "book_title": {"analyzers": ["identity"]},
                                    "series": {"analyzers": ["identity"]},
                                }
                            },
                        },
                        "includeAllFields": False,
                        "storeValues": "id",
                    }
                },
            }
        )
        print("Created ArangoSearch view: horus_lore_chunks_search")
    else:
        print("View horus_lore_chunks_search already exists")

    # View for docs (for direct doc search if needed)
    if "horus_lore_docs_search" not in existing_views:
        db.create_arangosearch_view(
            name="horus_lore_docs_search",
            properties={
                "links": {
                    "horus_lore_docs": {
                        "analyzers": ["text_en", "identity"],
                        "fields": {
                            "full_text": {"analyzers": ["text_en"]},
                            "entities": {"analyzers": ["identity"]},
                            "source": {"analyzers": ["identity"]},
                            "source_meta": {
                                "fields": {
                                    "channel": {"analyzers": ["identity"]},
                                    "book_title": {"analyzers": ["identity"]},
                                    "series": {"analyzers": ["identity"]},
                                    "title": {"analyzers": ["text_en"]},
                                }
                            },
                        },
                        "includeAllFields": False,
                        "storeValues": "id",
                    }
                },
            }
        )
        print("Created ArangoSearch view: horus_lore_docs_search")
    else:
        print("View horus_lore_docs_search already exists")


def ensure_search_view(db: Any) -> None:
    """Backward compat - calls ensure_search_views."""
    ensure_search_views(db)


# =============================================================================
# Graph
# =============================================================================

def ensure_graph(db: Any) -> Any:
    """Create named graph for traversal."""
    graph_name = "horus_lore_graph"

    if db.has_graph(graph_name):
        print(f"Graph {graph_name} already exists")
        return db.graph(graph_name)

    graph = db.create_graph(
        graph_name,
        edge_definitions=[
            {
                "edge_collection": "horus_lore_edges",
                "from_vertex_collections": ["horus_lore_docs"],
                "to_vertex_collections": ["horus_lore_docs"],
            }
        ],
    )
    print(f"Created graph: {graph_name}")
    return graph


# =============================================================================
# Document Key Generation
# =============================================================================

def create_doc_key(source: str, identifier: str, chunk_idx: int) -> str:
    """Create deterministic document key."""
    raw = f"{source}:{identifier}:chunk{chunk_idx}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


# =============================================================================
# Edge Creation (Rule-Based, No LLM)
# =============================================================================

def create_plot_point_edges(db: Any, collections: dict) -> dict[str, int]:
    """
    Create edges between chapters based on plot points (after LLM enrichment).

    Edge types:
    - leads_to: Plot point A leads to plot point B (from LLM extraction)
    - same_timeline: Chapters in same timeline period
    - character_arc: Same character appears in multiple chapters
    """
    edges_col = collections["edges"]

    # Get enriched chapters with plot points
    enriched = list(db.aql.execute("""
        FOR c IN horus_lore_chunks
        FILTER c.is_chapter == true
        FILTER c.plot_points != null AND LENGTH(c.plot_points) > 0
        RETURN {
            _key: c._key,
            doc_id: c.doc_id,
            chapter: c.source_meta.chapter,
            plot_points: c.plot_points,
            timeline: c.timeline_position,
            characters: c.primary_characters
        }
    """))

    if not enriched:
        print("No enriched chapters with plot points found.")
        return {}

    print(f"Creating plot-point edges for {len(enriched)} chapters...")

    edges = []

    # Timeline edges - connect chapters in same timeline period
    timeline_groups: dict[str, list] = {}
    for ch in enriched:
        tl = ch.get("timeline")
        if tl and tl != "unknown":
            if tl not in timeline_groups:
                timeline_groups[tl] = []
            timeline_groups[tl].append(ch)

    for timeline, chapters in timeline_groups.items():
        if len(chapters) < 2:
            continue
        for i, ch1 in enumerate(chapters):
            for ch2 in chapters[i + 1:]:
                edge_key = f"timeline_{ch1['_key']}_{ch2['_key']}"
                edges.append({
                    "_key": edge_key[:250],
                    "_from": f"horus_lore_chunks/{ch1['_key']}",
                    "_to": f"horus_lore_chunks/{ch2['_key']}",
                    "type": "same_timeline",
                    "timeline": timeline,
                    "weight": 0.4,
                })

    # Character arc edges - connect chapters featuring same character prominently
    character_chapters: dict[str, list] = {}
    for ch in enriched:
        for char in ch.get("characters", []):
            char_lower = char.lower()
            if char_lower not in character_chapters:
                character_chapters[char_lower] = []
            character_chapters[char_lower].append(ch)

    # Only create edges for major characters (appearing in 3+ chapters)
    for char, chapters in character_chapters.items():
        if len(chapters) >= 3:
            # Sort by series_number if available
            for i, ch1 in enumerate(chapters):
                for ch2 in chapters[i + 1:]:
                    if ch1["doc_id"] != ch2["doc_id"]:  # Different books
                        edge_key = f"arc_{char[:20]}_{ch1['_key']}_{ch2['_key']}"
                        edges.append({
                            "_key": edge_key[:250],
                            "_from": f"horus_lore_chunks/{ch1['_key']}",
                            "_to": f"horus_lore_chunks/{ch2['_key']}",
                            "type": "character_arc",
                            "character": char,
                            "weight": 0.6,
                        })

    if edges:
        edges_col.import_bulk(edges, on_duplicate="replace")

    # Count by type
    type_counts: dict[str, int] = {}
    for e in edges:
        t = e["type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    print(f"Created {len(edges)} plot-point edges")
    return type_counts


def create_edges(db: Any, collections: dict) -> dict[str, int]:
    """
    Create edges between documents based on rules (no LLM needed).

    Edge types:
    - chronological: Book N -> Book N+1 in same series
    - same_series: All books in same series
    - shared_entities: Docs sharing 3+ key entities
    """
    docs_col = collections["docs"]
    edges_col = collections["edges"]

    all_docs = list(docs_col.all())
    print(f"Creating edges for {len(all_docs)} documents...")

    edges = []

    # Group by series for chronological edges
    series_docs: dict[str, list] = {}
    for doc in all_docs:
        series = doc.get("source_meta", {}).get("series")
        if series:
            if series not in series_docs:
                series_docs[series] = []
            series_docs[series].append(doc)

    # Chronological edges within series
    for series, docs in series_docs.items():
        # Sort by series_number
        sorted_docs = sorted(
            [d for d in docs if d.get("source_meta", {}).get("series_number")],
            key=lambda d: d["source_meta"]["series_number"]
        )

        for i in range(len(sorted_docs) - 1):
            from_doc = sorted_docs[i]
            to_doc = sorted_docs[i + 1]

            edge_key = f"chron_{from_doc['_key']}_{to_doc['_key']}"
            edges.append({
                "_key": edge_key[:250],
                "_from": f"horus_lore_docs/{from_doc['_key']}",
                "_to": f"horus_lore_docs/{to_doc['_key']}",
                "type": "chronological",
                "series": series,
                "weight": 1.0,
            })

    # Same-series edges (bidirectional)
    for series, docs in series_docs.items():
        if len(docs) < 2:
            continue
        for i, doc1 in enumerate(docs):
            for doc2 in docs[i + 1:]:
                edge_key = f"series_{doc1['_key']}_{doc2['_key']}"
                edges.append({
                    "_key": edge_key[:250],
                    "_from": f"horus_lore_docs/{doc1['_key']}",
                    "_to": f"horus_lore_docs/{doc2['_key']}",
                    "type": "same_series",
                    "series": series,
                    "weight": 0.5,
                })

    # Shared entities edges (docs sharing 3+ important entities)
    for i, doc1 in enumerate(all_docs):
        entities1 = set(doc1.get("entities", []))
        # Filter to important entities
        important1 = {
            e for e in entities1
            if ALL_ENTITIES.get(e.lower(), {}).get("category") in IMPORTANT_ENTITY_CATEGORIES
        }

        for doc2 in all_docs[i + 1:]:
            entities2 = set(doc2.get("entities", []))
            important2 = {
                e for e in entities2
                if ALL_ENTITIES.get(e.lower(), {}).get("category") in IMPORTANT_ENTITY_CATEGORIES
            }

            shared = important1 & important2
            if len(shared) >= 3:
                edge_key = f"shared_{doc1['_key']}_{doc2['_key']}"
                edges.append({
                    "_key": edge_key[:250],
                    "_from": f"horus_lore_docs/{doc1['_key']}",
                    "_to": f"horus_lore_docs/{doc2['_key']}",
                    "type": "shared_entities",
                    "entities": list(shared),
                    "weight": min(len(shared) / 10.0, 1.0),  # More shared = stronger
                })

    # Import edges
    if edges:
        edges_col.import_bulk(edges, on_duplicate="replace")
        print(f"Created {len(edges)} edges")

    # Count by type
    type_counts: dict[str, int] = {}
    for e in edges:
        t = e["type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    return type_counts
