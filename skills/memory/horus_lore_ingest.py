"""
Horus Lore Ingest - Ingestion Module
Functions for ingesting YouTube transcripts and audiobook content.
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import sys
SKILL_DIR = Path(__file__).parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from horus_lore_config import extract_entity_names
from horus_lore_chunking import (
    chunk_youtube_transcript,
    chunk_audiobook,
    chunk_audiobook_by_chapters,
    extract_chapters_from_m4b,
)


# =============================================================================
# YouTube Transcript Ingestion
# =============================================================================

def ingest_youtube_transcript(
    file_path: Path,
    collections: dict[str, Any],
    embedder: Callable[[list[str]], list[list[float]]],
    batch_size: int = 50,
) -> dict[str, Any]:
    """
    Ingest a single YouTube transcript JSON file.

    Stores:
    - Full transcript in horus_lore_docs (the "document")
    - Chunks in horus_lore_chunks (for retrieval, with doc_id reference)
    """
    with open(file_path, encoding="utf-8", errors="replace") as f:
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
    try:
        doc_embedding = embedder([summary_text])[0]
        if doc_embedding is not None:
            doc["embedding"] = doc_embedding
    except Exception as e:
        print(f"Warning: embedding failed for video {video_id}: {e}", file=sys.stderr)

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
        try:
            embeddings = embedder(batch_texts)
        except Exception as e:
            print(f"Warning: chunk embedding batch failed for video {video_id}: {e}", file=sys.stderr)
            embeddings = []
        for j, emb in enumerate(embeddings):
            if emb is not None:
                chunk_docs[i + j]["embedding"] = emb

    # Upsert chunks
    collections["chunks"].import_bulk(chunk_docs, on_duplicate="replace")

    return {
        "status": "success",
        "video_id": video_id,
        "chunks": len(chunk_docs),
        "entities_found": len(all_entities),
    }


# =============================================================================
# Audiobook Ingestion
# =============================================================================

def ingest_audiobook(
    book_dir: Path,
    collections: dict[str, Any],
    embedder: Callable[[list[str]], list[list[float]]],
    batch_size: int = 50,
    use_chapters: bool = True,
) -> dict[str, Any]:
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
    elif "Primarchs" in dir_name or "Primarchs" in book_title:
        series = "The Primarchs"
        num_match = re.search(r'Book[_\s]+(\d+)', dir_name)
        if num_match:
            series_number = int(num_match.group(1))

    # Read full text
    full_text = text_file.read_text(encoding="utf-8", errors="replace")

    if not full_text or len(full_text) < 100:
        return {"status": "skipped", "reason": "no_content", "book": book_title}

    # Try to find M4B file for chapter extraction
    m4b_files = list(book_dir.glob("*.m4b"))
    chapters: list[dict] = []
    total_duration = 0.0

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
    try:
        doc_embedding = embedder([summary_text])[0]
        if doc_embedding is not None:
            doc["embedding"] = doc_embedding
    except Exception as e:
        print(f"Warning: embedding failed for book {book_title}: {e}", file=sys.stderr)

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
        try:
            embeddings = embedder(batch_texts)
        except Exception as e:
            print(f"Warning: chunk embedding batch failed for book {book_title}: {e}", file=sys.stderr)
            embeddings = []
        for j, emb in enumerate(embeddings):
            if emb is not None:
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


# =============================================================================
# Directory Ingestion
# =============================================================================

def ingest_youtube_directory(
    input_dir: Path,
    collections: dict[str, Any],
    embedder: Callable[[list[str]], list[list[float]]],
) -> dict[str, Any]:
    """Ingest all YouTube transcripts from a directory."""
    json_files = list(input_dir.glob("**/*.json"))

    # Filter out non-transcript files (state files, etc.)
    json_files = [f for f in json_files if not f.name.startswith(".") and "state" not in f.name.lower()]

    print(f"Found {len(json_files)} JSON files in {input_dir}")

    results: dict[str, Any] = {"success": 0, "skipped": 0, "errors": [], "total_chunks": 0, "total_docs": 0}

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


def ingest_audiobook_directory(
    input_dir: Path,
    collections: dict[str, Any],
    embedder: Callable[[list[str]], list[list[float]]],
) -> dict[str, Any]:
    """Ingest all audiobook transcripts from a directory."""
    # Find directories with text.md
    book_dirs = [d for d in input_dir.iterdir() if d.is_dir() and (d / "text.md").exists()]

    print(f"Found {len(book_dirs)} audiobooks in {input_dir}")

    results: dict[str, Any] = {"success": 0, "skipped": 0, "errors": [], "total_chunks": 0, "total_docs": 0, "books": []}

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
