"""
Horus Lore Ingest - Text Chunking Module
Functions for chunking text, YouTube transcripts, and audiobook content.
"""
import json
import re
import subprocess
from pathlib import Path
from typing import Any


# =============================================================================
# Generic Text Chunking
# =============================================================================

def chunk_text(
    text: str,
    chunk_size: int = 500,
    overlap: int = 50,
) -> list[dict[str, Any]]:
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
        chunk_text_str = " ".join(chunk_words)

        # Calculate character positions (approximate)
        start_char = len(" ".join(words[:i])) + (1 if i > 0 else 0)
        end_char = start_char + len(chunk_text_str)

        chunks.append({
            "text": chunk_text_str,
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


# =============================================================================
# YouTube Transcript Chunking
# =============================================================================

def chunk_youtube_transcript(transcript_data: dict, chunk_size: int = 500) -> list[dict[str, Any]]:
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
    current_chunk: list[str] = []
    current_words = 0
    chunk_start_time: float | None = None

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
            chunk_text_str = " ".join(current_chunk)
            chunk_end_time = seg_start  # End at start of next segment

            chunks.append({
                "text": chunk_text_str,
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
        chunk_text_str = " ".join(current_chunk)
        last_seg = segments[-1] if segments else {}
        chunk_end_time = last_seg.get("start", 0) + last_seg.get("duration", 0)

        chunks.append({
            "text": chunk_text_str,
            "start_time": chunk_start_time,
            "end_time": chunk_end_time,
        })

    return chunks


# =============================================================================
# Audiobook Chapter Extraction
# =============================================================================

def extract_chapters_from_m4b(m4b_path: Path) -> list[dict[str, Any]]:
    """
    Extract chapter metadata from M4B audiobook using ffprobe.

    Returns list of {"title": str, "start_sec": float, "end_sec": float}
    """
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


# =============================================================================
# Audiobook Chunking
# =============================================================================

def chunk_audiobook_by_chapters(
    text: str,
    chapters: list[dict[str, Any]],
    total_duration_sec: float,
) -> list[dict[str, Any]]:
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


def chunk_audiobook(text: str, chunk_size: int = 500) -> list[dict[str, Any]]:
    """
    Chunk audiobook transcript by fixed size (fallback when no M4B chapters).
    """
    # Detect chapter/part markers via regex
    lines = text.split('\n')
    chunks = []
    current_section: dict[str, str | None] = {"part": None, "chapter": None}
    current_text: list[str] = []
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
            chunk_text_str = " ".join(current_text)
            chunks.append({
                "text": chunk_text_str,
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
        chunk_text_str = " ".join(current_text)
        chunks.append({
            "text": chunk_text_str,
            "part": current_section.get("part"),
            "chapter": current_section.get("chapter"),
        })

    return chunks
