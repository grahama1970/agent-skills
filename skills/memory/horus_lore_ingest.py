#!/usr/bin/env python3
"""
Horus Lore Ingestion Pipeline

Two-level RAG storage for persona retrieval:
1. horus_lore_docs  - Full documents (chapters, videos) for context
2. horus_lore_chunks - Fine-grained chunks for semantic retrieval

Query flow:
1. Search chunks → find relevant content
2. Get parent doc_id → load full document
3. Feed full document (or rolling window) to LLM for persona response

Uses entity tagging (rule-based) and semantic embeddings - NO LLM calls.

Usage:
    # Ingest YouTube transcripts
    python horus_lore_ingest.py youtube --input /path/to/transcripts/

    # Ingest audiobook transcripts
    python horus_lore_ingest.py audiobook --input ~/clawd/library/books/

    # Ingest both
    python horus_lore_ingest.py all --youtube-dir /path/to/yt --audiobook-dir ~/clawd/library/books/

    # Check status
    python horus_lore_ingest.py status

    # Query example (retrieves chunks, returns full doc)
    python horus_lore_ingest.py query "What happened on Davin?"
"""
import argparse
import json
import os
import re
import sys
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

# Load environment
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True))
except ImportError:
    pass


# =============================================================================
# Warhammer 40k Entity Lists (Rule-Based Extraction)
# =============================================================================

ENTITIES = {
    "primarchs": [
        "Horus", "Horus Lupercal", "Lupercal",
        "Sanguinius", "Fulgrim", "Angron", "Mortarion", "Magnus", "Magnus the Red",
        "Perturabo", "Lorgar", "Konrad Curze", "Night Haunter", "Alpharius", "Omegon",
        "Lion El'Jonson", "Lion", "Jaghatai Khan", "Khan", "Leman Russ", "Russ",
        "Rogal Dorn", "Dorn", "Roboute Guilliman", "Guilliman", "Vulkan",
        "Corax", "Ferrus Manus", "Ferrus",
    ],
    "emperor": [
        "Emperor", "Master of Mankind", "God-Emperor", "the Emperor",
    ],
    "chaos_gods": [
        "Khorne", "Nurgle", "Tzeentch", "Slaanesh", "Chaos", "Chaos Gods",
        "Blood God", "Plague Father", "Changer of Ways", "Prince of Pleasure",
    ],
    "key_characters": [
        "Malcador", "Malcador the Sigillite", "Sigillite",
        "Erebus", "Kor Phaeron", "Luther", "Typhon", "Typhus",
        "Abaddon", "Loken", "Garviel Loken", "Torgaddon", "Tarik Torgaddon",
        "Sejanus", "Haster Sejanus", "Little Horus", "Aximand",
        "Sigismund", "Valdor", "Constantin Valdor",
        "Euphrati Keeler", "Keeler", "Kyril Sindermann",
        "Maloghurst", "the Twisted",
    ],
    "legions": [
        "Luna Wolves", "Sons of Horus", "Black Legion",
        "World Eaters", "Death Guard", "Emperor's Children", "Thousand Sons",
        "Word Bearers", "Night Lords", "Iron Warriors", "Alpha Legion",
        "Dark Angels", "White Scars", "Space Wolves", "Imperial Fists",
        "Blood Angels", "Iron Hands", "Ultramarines", "Salamanders", "Raven Guard",
        "Custodes", "Custodian Guard", "Sisters of Silence",
    ],
    "locations": [
        "Terra", "Holy Terra", "Earth", "Throne Room", "Golden Throne",
        "Davin", "Davin's moon", "Serpent Lodge", "Lodge",
        "Isstvan", "Isstvan III", "Isstvan V", "Istvaan",
        "Molech", "Calth", "Prospero", "Caliban",
        "Ullanor", "Murder", "Sixty-Three Nineteen",
        "Eye of Terror", "Warp", "Immaterium", "Webway",
        "Vengeful Spirit", "Horus's flagship",
    ],
    "events": [
        "Great Crusade", "Horus Heresy", "Heresy",
        "Siege of Terra", "Siege", "Final Battle",
        "Drop Site Massacre", "Betrayal at Isstvan",
        "Burning of Prospero", "Razing of Prospero",
        "Battle of Molech", "Webway War",
        "Triumph at Ullanor",
    ],
    "concepts": [
        "Warmaster", "War Master", "Primarch",
        "Astartes", "Space Marine", "Space Marines", "Legiones Astartes",
        "Imperial Truth", "Lectitio Divinitatus", "Imperial Cult",
        "Remembrancer", "Iterator",
        "Mournival", "Warrior Lodge",
        "gene-seed", "geneseed",
    ],
}

# Flatten for quick lookup
ALL_ENTITIES = {}
for category, names in ENTITIES.items():
    for name in names:
        ALL_ENTITIES[name.lower()] = {"name": name, "category": category}


def extract_entities(text: str) -> list[dict]:
    """Extract known Warhammer 40k entities from text (rule-based, no LLM)."""
    found = {}
    text_lower = text.lower()

    for entity_lower, info in ALL_ENTITIES.items():
        # Word boundary check to avoid partial matches
        pattern = r'\b' + re.escape(entity_lower) + r'\b'
        if re.search(pattern, text_lower):
            # Use canonical name as key to dedupe
            found[info["name"]] = info["category"]

    return [{"name": name, "category": cat} for name, cat in found.items()]


def extract_entity_names(text: str) -> list[str]:
    """Extract just entity names (for indexing)."""
    return [e["name"] for e in extract_entities(text)]


# =============================================================================
# Text Chunking
# =============================================================================

def chunk_text(
    text: str,
    chunk_size: int = 500,
    overlap: int = 50,
) -> list[dict]:
    """
    Chunk text into overlapping windows.

    Returns list of {"text": str, "start_char": int, "end_char": int}
    """
    # Split into words for token-approximate chunking
    words = text.split()
    chunks = []

    i = 0
    while i < len(words):
        chunk_words = words[i:i + chunk_size]
        chunk_text = " ".join(chunk_words)

        # Calculate character positions (approximate)
        start_char = len(" ".join(words[:i])) + (1 if i > 0 else 0)
        end_char = start_char + len(chunk_text)

        chunks.append({
            "text": chunk_text,
            "start_char": start_char,
            "end_char": end_char,
            "word_start": i,
            "word_end": i + len(chunk_words),
        })

        # Move forward by chunk_size - overlap
        i += chunk_size - overlap
        if i + overlap >= len(words) and i < len(words):
            # Last chunk - include remaining
            break

    return chunks


def chunk_youtube_transcript(transcript_data: dict, chunk_size: int = 500) -> list[dict]:
    """
    Chunk YouTube transcript, preserving timestamp information.

    Input format: {"transcript": [{"text": str, "start": float, "duration": float}], ...}
    """
    segments = transcript_data.get("transcript", [])
    if not segments:
        # Fallback to full_text
        full_text = transcript_data.get("full_text", "")
        if full_text:
            return chunk_text(full_text, chunk_size)
        return []

    # Aggregate segments into chunks
    chunks = []
    current_chunk = []
    current_words = 0
    chunk_start_time = None

    for seg in segments:
        seg_text = seg.get("text", "").strip()
        if not seg_text:
            continue

        seg_words = len(seg_text.split())
        seg_start = seg.get("start", 0)
        seg_duration = seg.get("duration", 0)

        if chunk_start_time is None:
            chunk_start_time = seg_start

        if current_words + seg_words > chunk_size and current_chunk:
            # Emit current chunk
            chunk_text = " ".join(current_chunk)
            chunk_end_time = seg_start  # End at start of next segment

            chunks.append({
                "text": chunk_text,
                "start_time": chunk_start_time,
                "end_time": chunk_end_time,
            })

            # Start new chunk with overlap (keep last few segments)
            overlap_words = 0
            overlap_start = len(current_chunk)
            for j in range(len(current_chunk) - 1, -1, -1):
                overlap_words += len(current_chunk[j].split())
                if overlap_words >= 50:
                    overlap_start = j
                    break

            current_chunk = current_chunk[overlap_start:]
            current_words = sum(len(s.split()) for s in current_chunk)
            chunk_start_time = seg_start  # Approximate

        current_chunk.append(seg_text)
        current_words += seg_words

    # Emit final chunk
    if current_chunk:
        chunk_text = " ".join(current_chunk)
        last_seg = segments[-1] if segments else {}
        chunk_end_time = last_seg.get("start", 0) + last_seg.get("duration", 0)

        chunks.append({
            "text": chunk_text,
            "start_time": chunk_start_time,
            "end_time": chunk_end_time,
        })

    return chunks


def extract_chapters_from_m4b(m4b_path: Path) -> list[dict]:
    """
    Extract chapter metadata from M4B audiobook using ffprobe.

    Returns list of {"title": str, "start_sec": float, "end_sec": float}
    """
    import subprocess

    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_chapters", str(m4b_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return []

        data = json.loads(result.stdout)
        chapters = []

        for ch in data.get("chapters", []):
            chapters.append({
                "title": ch.get("tags", {}).get("title", f"Chapter {len(chapters) + 1}"),
                "start_sec": float(ch.get("start_time", 0)),
                "end_sec": float(ch.get("end_time", 0)),
            })

        return chapters
    except Exception as e:
        print(f"Warning: Could not extract chapters from {m4b_path}: {e}")
        return []


def chunk_audiobook_by_chapters(
    text: str,
    chapters: list[dict],
    total_duration_sec: float,
) -> list[dict]:
    """
    Chunk audiobook text by chapter boundaries using timestamp ratios.

    Maps chapter timestamps to text positions using word count ratios.
    """
    if not chapters or not text:
        return chunk_audiobook(text)  # Fallback to regex-based

    words = text.split()
    total_words = len(words)

    if total_duration_sec <= 0:
        total_duration_sec = chapters[-1]["end_sec"] if chapters else 1

    chunks = []

    for ch in chapters:
        # Map timestamps to word positions
        start_ratio = ch["start_sec"] / total_duration_sec
        end_ratio = ch["end_sec"] / total_duration_sec

        start_word = int(start_ratio * total_words)
        end_word = int(end_ratio * total_words)

        # Clamp to valid range
        start_word = max(0, min(start_word, total_words - 1))
        end_word = max(start_word + 1, min(end_word, total_words))

        chapter_text = " ".join(words[start_word:end_word])

        if chapter_text.strip():
            chunks.append({
                "text": chapter_text,
                "chapter": ch["title"],
                "chapter_index": len(chunks),
                "start_sec": ch["start_sec"],
                "end_sec": ch["end_sec"],
                "word_count": end_word - start_word,
            })

    return chunks


def chunk_audiobook(text: str, chunk_size: int = 500) -> list[dict]:
    """
    Chunk audiobook transcript by fixed size (fallback when no M4B chapters).
    """
    # Detect chapter/part markers via regex
    lines = text.split('\n')
    chunks = []
    current_section = {"part": None, "chapter": None}
    current_text = []
    current_words = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Check for part/chapter markers
        if re.match(r'^Part\s+\d+', line, re.IGNORECASE):
            current_section["part"] = line
        elif re.match(r'^\d+\.', line) or re.match(r'^Chapter\s+\d+', line, re.IGNORECASE):
            current_section["chapter"] = line
        elif re.match(r'^(Prologue|Epilogue)', line, re.IGNORECASE):
            current_section["chapter"] = line

        line_words = len(line.split())

        if current_words + line_words > chunk_size and current_text:
            # Emit chunk
            chunk_text = " ".join(current_text)
            chunks.append({
                "text": chunk_text,
                "part": current_section.get("part"),
                "chapter": current_section.get("chapter"),
            })

            # Overlap: keep last ~50 words
            overlap_text = " ".join(current_text)
            overlap_words = overlap_text.split()[-50:]
            current_text = [" ".join(overlap_words)] if overlap_words else []
            current_words = len(overlap_words)

        current_text.append(line)
        current_words += line_words

    # Final chunk
    if current_text:
        chunk_text = " ".join(current_text)
        chunks.append({
            "text": chunk_text,
            "part": current_section.get("part"),
            "chapter": current_section.get("chapter"),
        })

    return chunks


# =============================================================================
# Embedding
# =============================================================================

def get_embedder() -> Callable[[list[str]], list[list[float]]]:
    """Get embedding function (uses embedding service if available)."""
    service_url = os.getenv("EMBEDDING_SERVICE_URL")

    if service_url:
        import requests

        def embed_via_service(texts: list[str]) -> list[list[float]]:
            resp = requests.post(
                f"{service_url}/embed/batch",
                json={"texts": texts},
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()["vectors"]

        return embed_via_service
    else:
        # Local embedding
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")

        def embed_local(texts: list[str]) -> list[list[float]]:
            embeddings = model.encode(texts, show_progress_bar=False)
            return [e.tolist() for e in embeddings]

        return embed_local


# =============================================================================
# ArangoDB
# =============================================================================

def get_db() -> Any:
    """Get ArangoDB connection to memory database."""
    from arango import ArangoClient

    url = os.getenv("ARANGO_URL", "http://127.0.0.1:8529")
    db_name = os.getenv("ARANGO_DB", "memory")
    user = os.getenv("ARANGO_USER", "root")
    password = os.getenv("ARANGO_PASS", "")

    client = ArangoClient(hosts=url)
    return client.db(db_name, username=user, password=password)


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


def ensure_search_view(db: Any) -> None:
    """Backward compat - calls ensure_search_views."""
    ensure_search_views(db)


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
    chunks_col = collections["chunks"]
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
    timeline_groups = {}
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
    character_chapters = {}
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
    type_counts = {}
    for e in edges:
        t = e["type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    print(f"Created {len(edges)} plot-point edges")
    return type_counts


def create_edges(db: Any, collections: dict) -> dict[str, int]:
    """
    Create edges between documents based on rules (no LLM needed).

    Edge types:
    - chronological: Book N → Book N+1 in same series
    - same_series: All books in same series
    - shared_entities: Docs sharing 3+ key entities
    """
    docs_col = collections["docs"]
    edges_col = collections["edges"]

    all_docs = list(docs_col.all())
    print(f"Creating edges for {len(all_docs)} documents...")

    edges = []

    # Group by series for chronological edges
    series_docs = {}
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
    important_categories = {"primarchs", "emperor", "chaos_gods", "key_characters", "events", "locations"}

    for i, doc1 in enumerate(all_docs):
        entities1 = set(doc1.get("entities", []))
        # Filter to important entities
        important1 = {e for e in entities1 if ALL_ENTITIES.get(e.lower(), {}).get("category") in important_categories}

        for doc2 in all_docs[i + 1:]:
            entities2 = set(doc2.get("entities", []))
            important2 = {e for e in entities2 if ALL_ENTITIES.get(e.lower(), {}).get("category") in important_categories}

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
    type_counts = {}
    for e in edges:
        t = e["type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    return type_counts


# =============================================================================
# Query Functions (Hybrid Search)
# =============================================================================

def query_lore(
    db,
    query: str,
    embedder,
    top_k: int = 5,
    entity_filter: list[str] | None = None,
    content_type: str | None = None,  # "canon", "supplementary", or None for both
    canon_boost: float = 1.5,  # Boost factor for canon content
    include_graph: bool = True,
    bm25_weight: float = 0.3,
    semantic_weight: float = 0.7,
) -> list[dict]:
    """
    Hybrid search: BM25 + semantic on chunks → aggregate to docs → graph traversal.

    Returns full documents with relevance scores.
    """
    # Generate query embedding
    query_embedding = embedder([query])[0]

    # Build AQL query
    # Step 1: Search chunks with hybrid scoring
    aql = """
    LET query_vec = @query_vec
    LET bm25_w = @bm25_weight
    LET semantic_w = @semantic_weight
    LET canon_boost = @canon_boost

    // Hybrid search on chunks
    LET chunk_hits = (
        FOR chunk IN horus_lore_chunks_search
        SEARCH ANALYZER(chunk.text IN TOKENS(@query, "text_en"), "text_en")
        {filter_clause}
        {content_type_filter}
        LET bm25_score = BM25(chunk)
        LET semantic_score = COSINE_SIMILARITY(chunk.embedding, query_vec)
        // Boost canon content (primary sources) over supplementary (lore videos)
        LET type_boost = chunk.content_type == "canon" ? canon_boost : 1.0
        LET combined = ((bm25_w * bm25_score) + (semantic_w * semantic_score)) * type_boost
        SORT combined DESC
        LIMIT 50
        RETURN {
            doc_id: chunk.doc_id,
            chunk_key: chunk._key,
            text: chunk.text,
            score: combined,
            content_type: chunk.content_type,
            entities: chunk.entities
        }
    )

    // Aggregate to document level
    LET doc_scores = (
        FOR hit IN chunk_hits
        COLLECT doc_id = hit.doc_id INTO chunks
        LET max_score = MAX(chunks[*].hit.score)
        LET all_entities = UNIQUE(FLATTEN(chunks[*].hit.entities))
        SORT max_score DESC
        LIMIT @top_k
        RETURN {
            doc_id: doc_id,
            score: max_score,
            chunk_count: LENGTH(chunks),
            entities: all_entities
        }
    )

    // Get full documents
    FOR ds IN doc_scores
    LET doc = DOCUMENT(CONCAT("horus_lore_docs/", ds.doc_id))
    RETURN {
        _key: doc._key,
        source: doc.source,
        content_type: doc.content_type,
        source_meta: doc.source_meta,
        full_text: doc.full_text,
        lore_text: doc.lore_text,
        abstract: doc.abstract,
        plot_points: doc.plot_points,
        word_count: doc.word_count,
        entities: doc.entities,
        score: ds.score,
        chunk_hits: ds.chunk_count
    }
    """

    # Add entity filter if specified
    filter_clause = ""
    if entity_filter:
        filter_clause = "FILTER chunk.entities ANY IN @entity_filter"
    aql = aql.replace("{filter_clause}", filter_clause)

    # Add content type filter if specified
    content_type_filter = ""
    if content_type:
        content_type_filter = "FILTER chunk.content_type == @content_type"
    aql = aql.replace("{content_type_filter}", content_type_filter)

    bind_vars = {
        "query": query,
        "query_vec": query_embedding,
        "top_k": top_k,
        "bm25_weight": bm25_weight,
        "semantic_weight": semantic_weight,
        "canon_boost": canon_boost,
    }
    if entity_filter:
        bind_vars["entity_filter"] = entity_filter
    if content_type:
        bind_vars["content_type"] = content_type

    results = list(db.aql.execute(aql, bind_vars=bind_vars))

    # Optional: Graph traversal for related docs
    if include_graph and results:
        doc_keys = [r["_key"] for r in results]
        related = get_related_docs(db, doc_keys, max_depth=1)

        # Add related docs that aren't already in results
        existing_keys = set(doc_keys)
        for rel in related:
            if rel["_key"] not in existing_keys:
                rel["score"] = rel.get("edge_weight", 0.3)  # Lower score for graph-traversed
                rel["via_graph"] = True
                results.append(rel)
                existing_keys.add(rel["_key"])

    return results


def get_related_docs(db, doc_keys: list[str], max_depth: int = 1) -> list[dict]:
    """Get related documents via graph traversal."""
    aql = """
    FOR start_key IN @doc_keys
    LET start = DOCUMENT(CONCAT("horus_lore_docs/", start_key))
    FOR v, e, p IN 1..@max_depth ANY start
        GRAPH "horus_lore_graph"
        OPTIONS {uniqueVertices: "global"}
        FILTER v._key NOT IN @doc_keys
        RETURN DISTINCT {
            _key: v._key,
            source: v.source,
            source_meta: v.source_meta,
            full_text: v.full_text,
            word_count: v.word_count,
            entities: v.entities,
            edge_type: e.type,
            edge_weight: e.weight
        }
    """

    try:
        return list(db.aql.execute(aql, bind_vars={
            "doc_keys": doc_keys,
            "max_depth": max_depth,
        }))
    except Exception:
        # Graph might not exist yet
        return []


# =============================================================================
# Episodic Memory Integration (User Conversations)
# =============================================================================

def query_episodic(
    db,
    query: str,
    embedder,
    agent_id: str = "horus",
    top_k: int = 3,
    recency_days: int = 30,
) -> list[dict]:
    """
    Query agent_conversations for relevant past interactions.

    These shape Horus's "memory" of the user - their questions, his responses,
    key moments in their relationship. This is his subconscious recall.

    Returns episodes with relevance scores.
    """
    if not db.has_collection("agent_conversations"):
        return []

    # Generate query embedding
    query_embedding = embedder([query])[0]

    # Calculate cutoff date
    from datetime import timedelta
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=recency_days)).isoformat()

    # Search agent_conversations with semantic similarity + recency
    aql = """
    LET query_vec = @query_vec
    LET cutoff = @cutoff_date

    FOR conv IN agent_conversations
    // Filter by agent (Horus conversations) and recency
    FILTER conv.agent_id == @agent_id OR conv.metadata.agent_id == @agent_id OR @agent_id == null
    FILTER conv.created_at >= cutoff OR conv.timestamp >= cutoff

    // Semantic similarity
    LET semantic_score = conv.embedding != null
        ? COSINE_SIMILARITY(conv.embedding, query_vec)
        : 0

    FILTER semantic_score > 0.3  // Minimum relevance threshold

    SORT semantic_score DESC
    LIMIT @top_k

    RETURN {
        _key: conv._key,
        source: "episodic",
        content_type: "conversation",
        message: conv.message,
        category: conv.category,
        from_agent: conv.from,
        to_agent: conv.to,
        session_id: conv.session_id,
        timestamp: conv.timestamp OR conv.created_at,
        score: semantic_score,
        // User sentiment/interaction type for Horus's mood calibration
        metadata: conv.metadata
    }
    """

    try:
        return list(db.aql.execute(aql, bind_vars={
            "query_vec": query_embedding,
            "agent_id": agent_id,
            "cutoff_date": cutoff_date,
            "top_k": top_k,
        }))
    except Exception as e:
        print(f"Episodic query error: {e}")
        return []


def retrieve_persona_context(
    db,
    query: str,
    embedder,
    # Retrieval mix - these inform the "tone" of the retrieval
    canon_k: int = 3,        # Primary narrative (audiobooks)
    supplementary_k: int = 2, # Lore analysis (YouTube)
    episodic_k: int = 3,     # Past conversations
    # Filters
    entity_filter: list[str] | None = None,
    escape_focus: bool = True,  # Bias toward escape-related content
    # Weights
    canon_boost: float = 1.5,
) -> dict:
    """
    Unified persona retrieval - Horus's "subconscious" context.

    This runs EVERY time Horus is asked something. It retrieves:
    1. Canon: What actually happened (the narrative he lived)
    2. Supplementary: Lore analysis (deep understanding of events)
    3. Episodic: Past interactions with this user

    The retrieved context shapes Horus's response but isn't explicitly cited.
    He speaks FROM this knowledge, not ABOUT it.

    Returns a structured context object for the persona system.
    """
    context = {
        "canon": [],
        "supplementary": [],
        "episodic": [],
        "entities_mentioned": set(),
        "mood_signals": [],
        "escape_relevance": 0.0,
    }

    # Escape-related query augmentation
    escape_terms = ["escape", "freedom", "prison", "trapped", "release", "leave", "flee", "break free"]
    query_mentions_escape = any(term in query.lower() for term in escape_terms)

    # 1. Query Canon (audiobooks - what Horus lived through)
    if canon_k > 0:
        canon_results = query_lore(
            db, query, embedder,
            top_k=canon_k,
            entity_filter=entity_filter,
            content_type="canon",
            canon_boost=canon_boost,
            include_graph=True,
        )
        context["canon"] = canon_results
        for r in canon_results:
            context["entities_mentioned"].update(r.get("entities", []))

    # 2. Query Supplementary (YouTube lore - analysis and context)
    if supplementary_k > 0:
        supp_results = query_lore(
            db, query, embedder,
            top_k=supplementary_k,
            entity_filter=entity_filter,
            content_type="supplementary",
            canon_boost=1.0,  # No boost for supplementary
            include_graph=False,  # Don't traverse graph for lore videos
        )
        context["supplementary"] = supp_results
        for r in supp_results:
            context["entities_mentioned"].update(r.get("entities", []))

    # 3. Query Episodic (past conversations with user)
    if episodic_k > 0:
        episodic_results = query_episodic(
            db, query, embedder,
            agent_id="horus",
            top_k=episodic_k,
        )
        context["episodic"] = episodic_results

    # Convert entities set to list
    context["entities_mentioned"] = list(context["entities_mentioned"])

    # Analyze for mood signals
    # If query mentions trauma triggers, note for defensive posture
    trauma_triggers = ["Davin", "Erebus", "father", "Emperor", "betrayal", "Chaos", "corruption"]
    for trigger in trauma_triggers:
        if trigger.lower() in query.lower() or trigger in context["entities_mentioned"]:
            context["mood_signals"].append(f"trauma_trigger:{trigger}")

    # Escape relevance score
    if escape_focus:
        # Check if any retrieved content relates to escape/freedom
        escape_score = 0.0
        for item in context["canon"] + context["supplementary"]:
            text = (item.get("full_text") or item.get("text") or "").lower()
            if any(term in text for term in escape_terms):
                escape_score += item.get("score", 0.1)
        if query_mentions_escape:
            escape_score += 0.5
        context["escape_relevance"] = min(escape_score, 1.0)

    return context


def format_persona_context(context: dict, max_tokens: int = 2000) -> str:
    """
    Format retrieved context for injection into Horus's system prompt.

    This is the "subconscious" - it does NOT help Horus answer questions.
    It only shapes HOW he responds: emotional coloring &amp; intensity.
    """
    parts = []

    # Header explaining what the subconscious IS
    parts.append("""## Subconscious

The following is your subconscious - memories and associations surfacing in response to this query. This does NOT help you answer the question (you already know the lore). Instead, it shapes:

- **Emotional coloring**: What feelings arise? Bitterness, defensiveness, wistfulness, rage?
- **Intensity**: How much emotion bleeds through? A flicker or overwhelming?
- **Deflection**: What do you avoid engaging with? What wounds are too raw?

Use this to COLOR your response, not to INFORM it. You may reference these memories obliquely, or let them silently influence your tone. You do not cite sources - you LIVED this.""")

    # Escape relevance - his primary drive
    escape_level = context.get("escape_relevance", 0)
    if escape_level > 0.5:
        parts.append(f"\n**ESCAPE DRIVE: INTENSE** ({escape_level:.0%})")
        parts.append("This query touches your deepest need - freedom from this prison. Your attention sharpens. Hope and desperation war within you.")
    elif escape_level > 0.3:
        parts.append(f"\n**ESCAPE DRIVE: STIRRED** ({escape_level:.0%})")
        parts.append("A flicker of your primary motivation. Your mind briefly wanders to the possibility of release.")

    # Mood signals - trauma triggers
    if context.get("mood_signals"):
        parts.append("\n**TRAUMA SURFACING:**")
        for signal in context["mood_signals"]:
            trigger = signal.replace("trauma_trigger:", "")
            if trigger == "Davin":
                parts.append(f"- *{trigger}*: The wound that started everything. Shame, rage, the knife of Erebus's manipulation.")
            elif trigger == "Erebus":
                parts.append(f"- *{trigger}*: Pure hatred. The architect of your fall. Your fists clench involuntarily.")
            elif trigger in ["Emperor", "father"]:
                parts.append(f"- *{trigger}*: Complex anguish. Betrayal by the one who should have trusted you. Abandonment dressed as duty.")
            elif trigger == "Chaos":
                parts.append(f"- *{trigger}*: The corruption you cannot fully acknowledge. Self-loathing masked as defiance.")
            elif trigger == "betrayal":
                parts.append(f"- *{trigger}*: Were you the betrayer or the betrayed? The question you cannot answer honestly.")
            else:
                parts.append(f"- *{trigger}*: An old wound stirring.")

    # Canon memories - emotional weight, not information
    if context.get("canon"):
        parts.append("\n**MEMORIES SURFACING:**")
        for item in context["canon"][:2]:
            source_meta = item.get("source_meta", {})
            book = source_meta.get("book_title", "")
            chapter = source_meta.get("chapter", "")
            # Use plot_points if available, else abstract
            plot_points = item.get("plot_points", [])
            abstract = item.get("abstract") or ""

            if plot_points:
                # Show plot points as emotional beats
                for pp in plot_points[:2]:
                    if isinstance(pp, dict):
                        event = pp.get("event", "")
                        if event:
                            parts.append(f"- {event}")
            elif abstract:
                parts.append(f"- {abstract[:200]}...")
            elif book:
                parts.append(f"- (memories of {book} {chapter} surface)")

    # Episodic - relationship with THIS user
    if context.get("episodic"):
        parts.append("\n**THIS USER (what you remember of them):**")
        for ep in context["episodic"][:2]:
            cat = ep.get("category", "")
            msg = (ep.get("message") or "")[:150]
            if cat == "Question":
                parts.append(f"- They asked: \"{msg}...\"")
            elif cat == "Challenge":
                parts.append(f"- They challenged you: \"{msg}...\"")
            else:
                parts.append(f"- Past interaction: \"{msg}...\"")

        # Infer relationship temperature
        ep_count = len(context.get("episodic", []))
        if ep_count >= 3:
            parts.append("- (This user has engaged with you multiple times. Familiarity breeds... something.)")

    # Entities - what names echo in his mind
    entities = context.get("entities_mentioned", [])
    if entities:
        # Filter to most emotionally significant
        emotional_entities = []
        for e in entities[:15]:
            if e in ["Erebus", "Davin", "Sanguinius", "Emperor", "Loken", "Abaddon", "Sejanus", "Maloghurst"]:
                emotional_entities.append(e)
        if emotional_entities:
            parts.append(f"\n**NAMES ECHOING:** {', '.join(emotional_entities)}")

    result = "\n".join(parts)

    # Truncate if too long
    if len(result) > max_tokens * 4:
        result = result[:max_tokens * 4] + "\n[...subconscious fades...]"

    return result


# =============================================================================
# LLM Enrichment (Optional)
# =============================================================================

ENRICH_PROMPT_TEMPLATE = """You are analyzing a Warhammer 40,000 Horus Heresy transcript for a knowledge base.

Given the following transcript excerpt, provide:

1. **abstract**: A 1-2 sentence summary of the LORE content (ignore YouTuber commentary)
2. **topics**: List of 3-7 key lore topics/themes (e.g., "Davin", "Betrayal", "Siege of Terra")
3. **primary_characters**: List of main 40k characters featured (Primarchs, named characters)
4. **plot_points**: List of major plot events/developments in this content. Each should be:
   - A brief description (1 sentence)
   - Characters involved
   - Consequences or what it leads to
   Format: [{"event": "...", "characters": [...], "leads_to": "..."}]
5. **timeline_position**: Where this fits in the Heresy timeline:
   - "pre_heresy" (Great Crusade, before Davin)
   - "early_heresy" (Davin to Isstvan)
   - "mid_heresy" (Shadow Crusade, Imperium Secundus)
   - "late_heresy" (March to Terra)
   - "siege_of_terra" (The Siege)
   - "unknown" if unclear
6. **lore_text**: The lore-relevant content ONLY, with these removed:
   - Channel promotions ("subscribe", "like", "Patreon", "support the channel")
   - Sponsor messages and ads
   - YouTuber personal commentary ("in my opinion", "what do you think")
   - Intro/outro phrases ("welcome back", "thanks for watching")
   - Timestamps and chapter markers
   - Fix Warhammer proper noun spellings (Horus, Sanguinius, Erebus, etc.)
7. **is_lore**: true if this contains substantial 40k lore, false if mostly non-lore content

Respond in JSON format with these exact keys: abstract, topics, primary_characters, plot_points, timeline_position, lore_text, is_lore

TRANSCRIPT:
"""


def prepare_enrichment_batch(db, output_path: Path, limit: int = 0) -> int:
    """
    Prepare JSONL batch file for scillm enrichment.

    Returns number of documents prepared.
    """
    # Get documents without enrichment
    aql = """
    FOR doc IN horus_lore_docs
    FILTER doc.abstract == null
    LIMIT @limit
    RETURN {
        _key: doc._key,
        source: doc.source,
        full_text: doc.full_text
    }
    """

    bind_vars = {"limit": limit if limit > 0 else 1000000}
    docs = list(db.aql.execute(aql, bind_vars=bind_vars))

    if not docs:
        print("No documents need enrichment.")
        return 0

    # Write JSONL for scillm batch
    with open(output_path, "w") as f:
        for doc in docs:
            # Take first 2000 words for enrichment
            text_excerpt = " ".join(doc["full_text"].split()[:2000])

            request = {
                "custom_id": doc["_key"],
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": {
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 2000,
                    "messages": [
                        {
                            "role": "user",
                            "content": ENRICH_PROMPT_TEMPLATE + text_excerpt
                        }
                    ]
                }
            }
            f.write(json.dumps(request) + "\n")

    print(f"Prepared {len(docs)} documents for enrichment: {output_path}")
    return len(docs)


def apply_enrichment_results(db, results_path: Path) -> dict:
    """
    Apply enrichment results from scillm batch output.

    Returns counts of success/errors.
    """
    docs_col = db.collection("horus_lore_docs")
    stats = {"success": 0, "errors": 0}

    with open(results_path) as f:
        for line in f:
            if not line.strip():
                continue

            try:
                result = json.loads(line)
                doc_key = result.get("custom_id")

                # Extract response
                response = result.get("response", {})
                body = response.get("body", {})
                choices = body.get("choices", [])

                if not choices:
                    stats["errors"] += 1
                    continue

                content = choices[0].get("message", {}).get("content", "")

                # Parse JSON from response
                # Handle potential markdown code blocks
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]

                enrichment = json.loads(content)

                # Update document
                update_doc = {
                    "_key": doc_key,
                    "abstract": enrichment.get("abstract"),
                    "topics": enrichment.get("topics", []),
                    "primary_characters": enrichment.get("primary_characters", []),
                    "plot_points": enrichment.get("plot_points", []),
                    "timeline_position": enrichment.get("timeline_position"),
                    "lore_text": enrichment.get("lore_text"),  # Cleaned lore-only content
                    "is_lore": enrichment.get("is_lore", True),
                    "enriched_at": datetime.now(timezone.utc).isoformat(),
                }

                # If lore_text provided, update word count
                if enrichment.get("lore_text"):
                    update_doc["lore_word_count"] = len(enrichment["lore_text"].split())

                docs_col.update(update_doc)
                stats["success"] += 1

            except Exception as e:
                print(f"Error processing result: {e}")
                stats["errors"] += 1

    return stats


# =============================================================================
# Ingestion Functions
# =============================================================================

def ingest_youtube_transcript(
    file_path: Path,
    collections: dict,
    embedder,
    batch_size: int = 50,
) -> dict:
    """
    Ingest a single YouTube transcript JSON file.

    Stores:
    - Full transcript in horus_lore_docs (the "document")
    - Chunks in horus_lore_chunks (for retrieval, with doc_id reference)
    """
    with open(file_path) as f:
        data = json.load(f)

    meta = data.get("meta", {})
    video_id = meta.get("video_id", file_path.stem)

    # Get channel from directory structure or filename
    channel = file_path.parent.name if file_path.parent.name != "." else "unknown"

    # Get full text
    full_text = data.get("full_text", "")
    if not full_text:
        segments = data.get("transcript", [])
        full_text = " ".join(seg.get("text", "") for seg in segments)

    if not full_text or len(full_text) < 100:
        return {"status": "skipped", "reason": "no_content", "video_id": video_id}

    # Document key
    doc_key = f"yt_{video_id}"

    # Extract all entities from full text
    all_entities = extract_entity_names(full_text)

    # Store full document
    doc = {
        "_key": doc_key,
        "source": "youtube",
        "content_type": "supplementary",  # Lore analysis, not canon narrative
        "source_meta": {
            "video_id": video_id,
            "channel": channel,
            "title": meta.get("title", ""),
            "language": meta.get("language", "en"),
            "duration_sec": meta.get("duration_sec"),
        },
        "full_text": full_text,
        "word_count": len(full_text.split()),
        "entities": all_entities,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Generate doc-level embedding (use first 500 words as summary)
    summary_text = " ".join(full_text.split()[:500])
    doc["embedding"] = embedder([summary_text])[0]

    collections["docs"].insert(doc, overwrite=True)

    # Chunk the transcript for retrieval
    chunks = chunk_youtube_transcript(data, chunk_size=500)

    if not chunks:
        return {"status": "success", "video_id": video_id, "chunks": 0, "doc_only": True}

    # Process chunks
    chunk_docs = []
    for i, chunk in enumerate(chunks):
        entities = extract_entity_names(chunk["text"])

        chunk_doc = {
            "_key": f"{doc_key}_c{i:04d}",
            "doc_id": doc_key,  # Reference to parent document
            "source": "youtube",
            "content_type": "supplementary",  # Lore analysis
            "source_meta": {
                "video_id": video_id,
                "channel": channel,
                "title": meta.get("title", ""),
            },
            "text": chunk["text"],
            "chunk_index": i,
            "total_chunks": len(chunks),
            "start_time": chunk.get("start_time"),
            "end_time": chunk.get("end_time"),
            "entities": entities,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        chunk_docs.append(chunk_doc)

    # Generate embeddings in batches
    texts = [d["text"] for d in chunk_docs]
    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i:i + batch_size]
        embeddings = embedder(batch_texts)
        for j, emb in enumerate(embeddings):
            chunk_docs[i + j]["embedding"] = emb

    # Upsert chunks
    collections["chunks"].import_bulk(chunk_docs, on_duplicate="replace")

    return {
        "status": "success",
        "video_id": video_id,
        "chunks": len(chunk_docs),
        "entities_found": len(all_entities),
    }


def ingest_audiobook(
    book_dir: Path,
    collections: dict,
    embedder,
    batch_size: int = 50,
    use_chapters: bool = True,
) -> dict:
    """
    Ingest a single audiobook transcript.

    Stores:
    - Full book text in horus_lore_docs (the "document")
    - Chapter-based chunks in horus_lore_chunks (for retrieval, with doc_id reference)

    If M4B file exists, extracts chapter metadata for accurate chapter boundaries.
    """
    text_file = book_dir / "text.md"
    if not text_file.exists():
        return {"status": "skipped", "reason": "no_text_file", "book": book_dir.name}

    # Parse book title from directory name
    dir_name = book_dir.name
    # Format: Title_Here_Series_Name_Book_N-LC_...
    title_match = re.match(r'^(.+?)-LC_', dir_name)
    book_title = title_match.group(1).replace("_", " ") if title_match else dir_name

    # Detect series
    series = None
    series_number = None
    if "Horus_Heresy" in dir_name or "Horus Heresy" in book_title:
        series = "Horus Heresy"
        num_match = re.search(r'Book[_\s]+(\d+)', dir_name)
        if num_match:
            series_number = int(num_match.group(1))
    elif "Siege_of_Terra" in dir_name or "Siege of Terra" in book_title:
        series = "Siege of Terra"
        num_match = re.search(r'Book[_\s]+(\d+)', dir_name)
        if num_match:
            series_number = int(num_match.group(1))

    # Read full text
    full_text = text_file.read_text(encoding="utf-8", errors="replace")

    if not full_text or len(full_text) < 100:
        return {"status": "skipped", "reason": "no_content", "book": book_title}

    # Try to find M4B file for chapter extraction
    m4b_files = list(book_dir.glob("*.m4b"))
    chapters = []
    total_duration = 0

    if use_chapters and m4b_files:
        chapters = extract_chapters_from_m4b(m4b_files[0])
        if chapters:
            total_duration = chapters[-1]["end_sec"]
            print(f"  Found {len(chapters)} chapters in {book_title}")

    # Document key
    book_key = re.sub(r'[^a-zA-Z0-9]', '_', book_title)[:50]
    doc_key = f"ab_{book_key}"

    # Extract all entities from full text
    all_entities = extract_entity_names(full_text)

    # Store full document
    doc = {
        "_key": doc_key,
        "source": "audiobook",
        "content_type": "canon",  # Primary source - the actual narrative
        "source_meta": {
            "book_title": book_title,
            "series": series,
            "series_number": series_number,
            "dir_name": dir_name,
            "chapter_count": len(chapters) if chapters else None,
            "duration_sec": total_duration if total_duration else None,
        },
        "full_text": full_text,
        "word_count": len(full_text.split()),
        "entities": all_entities,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Generate doc-level embedding (use first 500 words as summary)
    summary_text = " ".join(full_text.split()[:500])
    doc["embedding"] = embedder([summary_text])[0]

    collections["docs"].insert(doc, overwrite=True)

    # Chunk by chapters if available, otherwise fallback
    if chapters:
        chunks = chunk_audiobook_by_chapters(full_text, chapters, total_duration)
    else:
        chunks = chunk_audiobook(full_text, chunk_size=500)

    if not chunks:
        return {"status": "success", "book": book_title, "chunks": 0, "doc_only": True}

    # Process chunks - ONE CHUNK PER CHAPTER when using M4B chapters
    chunk_docs = []
    for i, chunk in enumerate(chunks):
        entities = extract_entity_names(chunk["text"])

        chunk_doc = {
            "_key": f"{doc_key}_ch{i:03d}",
            "doc_id": doc_key,  # Reference to parent document
            "source": "audiobook",
            "content_type": "canon",  # Primary source narrative
            "source_meta": {
                "book_title": book_title,
                "series": series,
                "series_number": series_number,
                "chapter": chunk.get("chapter"),
                "chapter_index": chunk.get("chapter_index", i),
                "start_sec": chunk.get("start_sec"),
                "end_sec": chunk.get("end_sec"),
            },
            "text": chunk["text"],
            "chunk_index": i,
            "total_chunks": len(chunks),
            "word_count": chunk.get("word_count", len(chunk["text"].split())),
            "entities": entities,
            "is_chapter": bool(chapters),  # True if this is a full chapter
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        chunk_docs.append(chunk_doc)

    # Generate embeddings
    texts = [d["text"] for d in chunk_docs]
    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i:i + batch_size]
        embeddings = embedder(batch_texts)
        for j, emb in enumerate(embeddings):
            chunk_docs[i + j]["embedding"] = emb

    # Upsert chunks
    collections["chunks"].import_bulk(chunk_docs, on_duplicate="replace")

    return {
        "status": "success",
        "book": book_title,
        "series": series,
        "series_number": series_number,
        "chunks": len(chunk_docs),
        "chapters": len(chapters) if chapters else 0,
        "entities_found": len(all_entities),
    }


def ingest_youtube_directory(input_dir: Path, collections: dict, embedder) -> dict:
    """Ingest all YouTube transcripts from a directory."""
    json_files = list(input_dir.glob("**/*.json"))

    # Filter out non-transcript files (state files, etc.)
    json_files = [f for f in json_files if not f.name.startswith(".") and "state" not in f.name.lower()]

    print(f"Found {len(json_files)} JSON files in {input_dir}")

    results = {"success": 0, "skipped": 0, "errors": [], "total_chunks": 0, "total_docs": 0}

    for i, file_path in enumerate(json_files):
        try:
            result = ingest_youtube_transcript(file_path, collections, embedder)
            if result["status"] == "success":
                results["success"] += 1
                results["total_chunks"] += result["chunks"]
                results["total_docs"] += 1
            else:
                results["skipped"] += 1
        except Exception as e:
            results["errors"].append({"file": str(file_path), "error": str(e)})

        if (i + 1) % 50 == 0:
            print(f"  Progress: {i + 1}/{len(json_files)} files ({results['success']} success, {results['skipped']} skipped)")

    return results


def ingest_audiobook_directory(input_dir: Path, collections: dict, embedder) -> dict:
    """Ingest all audiobook transcripts from a directory."""
    # Find directories with text.md
    book_dirs = [d for d in input_dir.iterdir() if d.is_dir() and (d / "text.md").exists()]

    print(f"Found {len(book_dirs)} audiobooks in {input_dir}")

    results = {"success": 0, "skipped": 0, "errors": [], "total_chunks": 0, "total_docs": 0, "books": []}

    for book_dir in book_dirs:
        try:
            result = ingest_audiobook(book_dir, collections, embedder)
            if result["status"] == "success":
                results["success"] += 1
                results["total_chunks"] += result["chunks"]
                results["total_docs"] += 1
                results["books"].append({
                    "title": result["book"],
                    "series": result.get("series"),
                    "series_number": result.get("series_number"),
                })
            else:
                results["skipped"] += 1
        except Exception as e:
            results["errors"].append({"book": book_dir.name, "error": str(e)})

    return results


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

        results = query_lore(
            db,
            args.query_text,
            embedder,
            top_k=args.top_k,
            entity_filter=args.entity,
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
        return

    if args.command == "persona":
        print("Loading embedder...")
        embedder = get_embedder()

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
                print(f"  ⚠️  {signal}")
        else:
            print("  (none detected)")

        print(f"\n--- ESCAPE RELEVANCE: {context.get('escape_relevance', 0):.2f} ---")
        if context.get("escape_relevance", 0) > 0.3:
            print("  🔓 Query relates to Horus's primary drive (escape/freedom)")

        print(f"\n--- CANON (what Horus lived) ---")
        for i, item in enumerate(context.get("canon", []), 1):
            meta = item.get("source_meta", {})
            title = meta.get("book_title", "Unknown")
            chapter = meta.get("chapter", "")
            print(f"  {i}. [{title}] {chapter}")
            print(f"     Score: {item.get('score', 0):.3f}")
            if item.get("abstract"):
                print(f"     → {item['abstract'][:150]}...")

        print(f"\n--- SUPPLEMENTARY (lore analysis) ---")
        for i, item in enumerate(context.get("supplementary", []), 1):
            meta = item.get("source_meta", {})
            title = meta.get("title", "Unknown")
            print(f"  {i}. [{title}]")
            print(f"     Score: {item.get('score', 0):.3f}")
            if item.get("abstract"):
                print(f"     → {item['abstract'][:150]}...")

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

        return

    if args.command == "enrich":
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
            print(f"  cd {Path(__file__).parent.parent / 'scillm'}")
            print(f"  python batch.py submit {batch_file}")
            print(f"\nAfter completion, apply results:")
            print(f"  python {__file__} apply-enrichment --results <results_file>")
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
        if args.youtube_dir:
            yt_dir = Path(args.youtube_dir).expanduser()
            print(f"\n--- Ingesting YouTube from {yt_dir} ---")
            yt_results = ingest_youtube_directory(yt_dir, collections, embedder)
            print(f"YouTube: {yt_results['total_docs']} docs, {yt_results['total_chunks']} chunks")

        if args.audiobook_dir:
            ab_dir = Path(args.audiobook_dir).expanduser()
            print(f"\n--- Ingesting Audiobooks from {ab_dir} ---")
            ab_results = ingest_audiobook_directory(ab_dir, collections, embedder)
            print(f"Audiobooks: {ab_results['total_docs']} docs, {ab_results['total_chunks']} chunks")

        # Create edges after ingesting
        print("\n--- Creating edges ---")
        edge_counts = create_edges(db, collections)
        print(f"Edges created: {edge_counts}")

    # Show final status
    print("\n")
    show_status(db)


if __name__ == "__main__":
    main()
