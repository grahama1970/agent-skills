from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

import aiohttp
import typer


app = typer.Typer(no_args_is_help=True)

DEFAULT_URL = "http://localhost:4001/v1/chat/completions"
DEFAULT_MODEL = "chutes-deepseek"
DEFAULT_TOKEN = "sk-dev-proxy-123"
REQUIRED_KEYS = {"question", "answer", "claim", "evidence_quote", "factuality", "tom"}
FACTUALITY = {
    "narration_assertion",
    "character_speech",
    "character_thought",
    "reported_story",
    "uncertain_narration",
}
TOM_KEYS = {"holder", "mental_state", "target"}
TOM_STATES = {
    "belief",
    "intention",
    "emotion",
    "perception",
    "preference",
    "uncertainty",
    "evaluation",
}
ACCEPTED_RECORD_METADATA_KEYS = {
    "_key",
    "schema_version",
    "record_id",
    "type",
    "record_type",
    "memory_collection",
    "question_text",
    "answer_text",
    "claim_text",
    "evidence_text",
    "text",
    "retrieval_text",
    "validation_status",
    "canon_status",
    "upsert_eligible",
    "tags",
    "book",
    "chapter",
    "chapter_id",
    "chunk_id",
    "document_id",
    "source_path",
    "source_sha256",
    "primary_start_char",
    "primary_end_char",
    "context_start_char",
    "context_end_char",
    "evidence_start_char",
    "evidence_end_char",
    "evidence_quote_sha256",
}
CHAPTER_HEADING_RE = re.compile(
    r"(?im)^[ \t]*(?:chapter[ \t]+)(?P<label>\d+|[ivxlcdm]+|[a-z][a-z -]*)[ \t]*$"
)
WORD_NUMBERS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
}


@dataclass(frozen=True)
class SentenceSpan:
    sentence_index: int
    paragraph_index: int
    text: str
    start_char: int
    end_char: int


@dataclass(frozen=True)
class ParagraphSpan:
    paragraph_index: int
    text: str
    start_char: int
    end_char: int


@dataclass(frozen=True)
class TextChunk:
    chunk_id: str
    document_id: str
    source_path: str | None
    source_sha256: str
    primary_start_char: int
    primary_end_char: int
    context_start_char: int
    context_end_char: int
    primary_start_sentence: int
    primary_end_sentence: int
    context_start_sentence: int
    context_end_sentence: int
    overlap_before_sentences: int
    overlap_after_sentences: int
    target_chars: int
    max_chars: int
    chunk_text: str
    record_id_prefix: str


@dataclass(frozen=True)
class ChunkResult:
    chunk_id: str
    accepted: bool
    record_count: int
    elapsed_s: float
    http_status: int | None
    defects: list[str]
    chunk_dir: str
    accepted_attempt: int | None
    attempts: int


@dataclass(frozen=True)
class BatchConfig:
    chunks_path: Path
    out_dir: Path
    book: str
    chapter: str
    chapter_id: str
    persona_id: str
    url: str
    model: str
    concurrency: int
    timeout: int
    response_start_timeout: int
    stream_idle_timeout: int
    retry_delay: int
    min_records: int
    max_records: int
    max_tokens: int
    json_object: bool
    limit: int
    force: bool


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "document"


def chapter_number(label: str, fallback: int) -> int:
    raw = label.strip().lower()
    if raw.isdigit():
        return int(raw)
    if raw in WORD_NUMBERS:
        return WORD_NUMBERS[raw]
    roman_values = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
    if raw and all(char in roman_values for char in raw):
        total = 0
        prev = 0
        for char in reversed(raw):
            val = roman_values[char]
            total += -val if val < prev else val
            prev = max(prev, val)
        return total or fallback
    return fallback


def find_paragraphs(text: str) -> list[ParagraphSpan]:
    paragraphs: list[ParagraphSpan] = []
    start: int | None = None
    index = 0
    for match in re.finditer(r"\n[ \t]*\n", text):
        block_start = 0 if start is None else start
        block_end = match.start()
        raw = text[block_start:block_end]
        if raw.strip():
            leading = len(raw) - len(raw.lstrip())
            trailing = len(raw.rstrip())
            abs_start = block_start + leading
            abs_end = block_start + trailing
            paragraphs.append(ParagraphSpan(index, text[abs_start:abs_end], abs_start, abs_end))
            index += 1
        start = match.end()

    block_start = 0 if start is None else start
    raw = text[block_start:]
    if raw.strip():
        leading = len(raw) - len(raw.lstrip())
        trailing = len(raw.rstrip())
        abs_start = block_start + leading
        abs_end = block_start + trailing
        paragraphs.append(ParagraphSpan(index, text[abs_start:abs_end], abs_start, abs_end))
    return paragraphs


def split_sentences_regex(paragraph: ParagraphSpan) -> list[tuple[str, int, int]]:
    boundary = re.compile(
        r"""(?<=[.!?])(?:["'”’)\]]*)\s+(?=["'“‘(\[]*[A-Z0-9])""",
        re.VERBOSE,
    )
    spans: list[tuple[int, int]] = []
    start = 0
    for match in boundary.finditer(paragraph.text):
        end = match.start()
        if paragraph.text[start:end].strip():
            spans.append((start, end))
        start = match.end()
    if start < len(paragraph.text):
        spans.append((start, len(paragraph.text)))

    out: list[tuple[str, int, int]] = []
    for local_start, local_end in spans:
        raw = paragraph.text[local_start:local_end]
        leading = len(raw) - len(raw.lstrip())
        trailing = len(raw.rstrip())
        abs_start = paragraph.start_char + local_start + leading
        abs_end = paragraph.start_char + local_start + trailing
        clean = paragraph.text[abs_start - paragraph.start_char : abs_end - paragraph.start_char]
        if clean.strip():
            out.append((clean, abs_start, abs_end))
    return out


def sentence_spans(text: str) -> list[SentenceSpan]:
    sentences: list[SentenceSpan] = []
    for paragraph in find_paragraphs(text):
        for sent_text, start, end in split_sentences_regex(paragraph):
            sentences.append(
                SentenceSpan(
                    sentence_index=len(sentences),
                    paragraph_index=paragraph.paragraph_index,
                    text=sent_text,
                    start_char=start,
                    end_char=end,
                )
            )
    return sentences


def build_primary_sentence_groups(
    sentences: list[SentenceSpan],
    target_chars: int,
    max_chars: int,
) -> list[tuple[int, int]]:
    groups: list[tuple[int, int]] = []
    start = 0
    while start < len(sentences):
        end = start
        last_paragraph_boundary: int | None = None
        while end < len(sentences):
            sent = sentences[end]
            next_len = sent.end_char - sentences[start].start_char
            next_is_new_para = (
                end + 1 >= len(sentences)
                or sentences[end + 1].paragraph_index != sent.paragraph_index
            )
            if next_is_new_para:
                last_paragraph_boundary = end + 1
            if end > start and next_len > max_chars:
                break
            end += 1
            if next_len >= target_chars:
                if next_is_new_para:
                    break
                if last_paragraph_boundary and last_paragraph_boundary > start:
                    boundary_len = (
                        sentences[last_paragraph_boundary - 1].end_char
                        - sentences[start].start_char
                    )
                    if boundary_len >= int(target_chars * 0.65):
                        end = last_paragraph_boundary
                        break
        groups.append((start, max(end, start + 1)))
        start = max(end, start + 1)
    return groups


def make_chunks(
    text: str,
    document_id: str,
    source_path: str | None,
    target_chars: int,
    max_chars: int,
    overlap_before_sentences: int,
    overlap_after_sentences: int,
) -> list[TextChunk]:
    if target_chars <= 0:
        raise ValueError("target_chars must be positive")
    if max_chars < target_chars:
        raise ValueError("max_chars must be >= target_chars")
    if overlap_before_sentences < 0 or overlap_after_sentences < 0:
        raise ValueError("overlap sentence counts must be non-negative")

    normalized = normalize_newlines(text)
    sents = sentence_spans(normalized)
    if not sents:
        return []

    source_hash = sha256_text(normalized)
    groups = build_primary_sentence_groups(sents, target_chars, max_chars)
    chunks: list[TextChunk] = []
    for index, (primary_start_sent, primary_end_sent) in enumerate(groups, start=1):
        context_start_sent = max(0, primary_start_sent - overlap_before_sentences)
        context_end_sent = min(len(sents), primary_end_sent + overlap_after_sentences)
        primary_start_char = sents[primary_start_sent].start_char
        primary_end_char = sents[primary_end_sent - 1].end_char
        context_start_char = sents[context_start_sent].start_char
        context_end_char = sents[context_end_sent - 1].end_char
        chunk_id = f"c{index:02d}"
        chunks.append(
            TextChunk(
                chunk_id=chunk_id,
                document_id=document_id,
                source_path=source_path,
                source_sha256=source_hash,
                primary_start_char=primary_start_char,
                primary_end_char=primary_end_char,
                context_start_char=context_start_char,
                context_end_char=context_end_char,
                primary_start_sentence=primary_start_sent,
                primary_end_sentence=primary_end_sent,
                context_start_sentence=context_start_sent,
                context_end_sentence=context_end_sent,
                overlap_before_sentences=primary_start_sent - context_start_sent,
                overlap_after_sentences=context_end_sent - primary_end_sent,
                target_chars=target_chars,
                max_chars=max_chars,
                chunk_text=normalized[context_start_char:context_end_char],
                record_id_prefix=f"{document_id}-{chunk_id}-r",
            )
        )
    return chunks


def write_chunks_jsonl(chunks: list[TextChunk], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as out:
        for chunk in chunks:
            out.write(json.dumps(asdict(chunk), ensure_ascii=False))
            out.write("\n")


def write_chunk_dicts_jsonl(chunks: list[dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as out:
        for chunk in chunks:
            out.write(json.dumps(chunk, ensure_ascii=False))
            out.write("\n")


def load_chunks(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except Exception as exc:
                raise ValueError(f"{path}:line_{line_no}:invalid_json:{exc}") from exc
            if not isinstance(obj, dict):
                raise ValueError(f"{path}:line_{line_no}:not_object")
            rows.append(obj)
    return rows


def load_book_source(source: Path) -> tuple[str, Path, str]:
    if source.is_file():
        return normalize_newlines(source.read_text(encoding="utf-8")), source, "text_file"

    text_md = source / "text.md"
    if text_md.exists():
        return normalize_newlines(text_md.read_text(encoding="utf-8")), text_md, "directory_text_md"

    clean_dir = source / "clean"
    json_paths = sorted(clean_dir.glob("*.json")) if clean_dir.exists() else sorted(source.glob("*.json"))
    if not json_paths:
        raise FileNotFoundError(f"No text.md or JSON source files found in {source}")

    parts: list[str] = []
    for path in json_paths:
        obj = json.loads(path.read_text(encoding="utf-8"))
        text = obj.get("full_text") or obj.get("text") or obj.get("clean_text") or obj.get("content")
        if isinstance(text, str) and text.strip():
            parts.append(text.strip())
    if not parts:
        raise ValueError(f"JSON source files in {source} did not contain usable text fields")
    return normalize_newlines("\n\n".join(parts)), clean_dir if clean_dir.exists() else source, "json_concat"


def find_chapter_bounds(text: str) -> list[dict[str, Any]]:
    matches = list(CHAPTER_HEADING_RE.finditer(text))
    if not matches:
        return [
            {
                "chapter_index": 1,
                "chapter_number": 1,
                "chapter": "Document",
                "heading": "Document",
                "start_char": 0,
                "end_char": len(text),
            }
        ]

    bounds: list[dict[str, Any]] = []
    for index, match in enumerate(matches, start=1):
        label = match.group("label")
        number = chapter_number(label, index)
        end = matches[index].start() if index < len(matches) else len(text)
        heading = f"Chapter {number:02d}" if str(label).strip().isdigit() else match.group(0).strip()
        bounds.append(
            {
                "chapter_index": index,
                "chapter_number": number,
                "chapter": heading,
                "heading": match.group(0).strip(),
                "start_char": match.start(),
                "end_char": end,
            }
        )
    return bounds


def stage_book_source(source: Path, out: Path, book: str, book_id: str, force: bool) -> dict[str, Any]:
    text, source_text_path, source_kind = load_book_source(source)
    cleaned_dir = out / "cleaned_chapters"
    if force and out.exists():
        shutil.rmtree(out)
    cleaned_dir.mkdir(parents=True, exist_ok=True)

    chapters: list[dict[str, Any]] = []
    for bound in find_chapter_bounds(text):
        number = int(bound["chapter_number"])
        chapter_id = f"{book_id}_ch{number:02d}"
        body = text[bound["start_char"] : bound["end_char"]].strip()
        if body:
            body += "\n"
        output_path = cleaned_dir / f"chapter_{number:02d}.txt"
        if output_path.exists() and not force:
            raise FileExistsError(f"{output_path} already exists; pass --force to overwrite")
        output_path.write_text(body, encoding="utf-8")
        chapters.append(
            {
                **bound,
                "book": book,
                "book_id": book_id,
                "chapter_id": chapter_id,
                "output_path": str(output_path),
                "chars": len(body),
                "sha256": sha256_text(body),
            }
        )

    manifest = {
        "schema_version": "fact-extractor-stage-book.v1",
        "created_at": now(),
        "book": book,
        "book_id": book_id,
        "source": str(source),
        "source_text_path": str(source_text_path),
        "source_kind": source_kind,
        "source_sha256": sha256_text(text),
        "source_chars": len(text),
        "chapter_count": len(chapters),
        "chapter_detection": "standalone_chapter_heading",
        "chapters": chapters,
        "warnings": [],
    }
    if source_kind == "json_concat":
        manifest["warnings"].append("json_concat_source_can_contain_overlaps; prefer text.md when available")
    if len(chapters) <= 3:
        manifest["warnings"].append("low_chapter_marker_count; source may not expose all print chapter boundaries")
    out.mkdir(parents=True, exist_ok=True)
    (out / "stage_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def load_chapter_manifest(chapters_path: Path) -> list[dict[str, Any]]:
    chapters = load_jsonl(chapters_path)
    if not chapters:
        raise ValueError(f"{chapters_path}:no_chapters")

    required = {"chapter_id", "title", "text_path"}
    for idx, chapter in enumerate(chapters, start=1):
        missing = sorted(required - set(chapter))
        if missing:
            raise ValueError(f"{chapters_path}:line_{idx}:missing:{','.join(missing)}")
    return chapters


def make_book_chunks(
    chapters_path: Path,
    book: str,
    book_id: str,
    target_chars: int,
    max_chars: int,
    overlap_before_sentences: int,
    overlap_after_sentences: int,
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for chapter in load_chapter_manifest(chapters_path):
        text_path = Path(str(chapter["text_path"]))
        if not text_path.exists():
            raise FileNotFoundError(f"{text_path}:missing_text_path_for:{chapter['chapter_id']}")

        chapter_chunks = make_chunks(
            text_path.read_text(encoding="utf-8"),
            document_id=str(chapter["chapter_id"]),
            source_path=str(text_path),
            target_chars=target_chars,
            max_chars=max_chars,
            overlap_before_sentences=overlap_before_sentences,
            overlap_after_sentences=overlap_after_sentences,
        )
        for chunk in chapter_chunks:
            row = asdict(chunk)
            source_chunk_id = row["chunk_id"]
            chunk_key = f"{chapter['chapter_id']}-{source_chunk_id}"
            row["source_chunk_id"] = source_chunk_id
            row["chunk_id"] = chunk_key
            row["record_id_prefix"] = f"{chunk_key}-r"
            row.update(
                {
                    "_key": chunk_key,
                    "type": "book_chunk_record",
                    "record_id": chunk_key,
                    "record_type": "book_chunk",
                    "memory_collection": "book_chunks",
                    "book": book,
                    "book_id": book_id,
                    "chapter": chapter["title"],
                    "chapter_id": chapter["chapter_id"],
                    "chapter_index": chapter.get("index"),
                    "title": f"{book} {chapter['title']} {source_chunk_id}",
                    "text": row["chunk_text"],
                    "retrieval_text": row["chunk_text"],
                    "validation_status": "accepted",
                    "canon_status": "source_grounded",
                    "upsert_eligible": True,
                    "tags": [
                        "book_chunk",
                        f"book:{book_id}",
                        f"chapter:{chapter['chapter_id']}",
                    ],
                    "audio_start_time": chapter.get("start_time"),
                    "audio_end_time": chapter.get("end_time"),
                    "transcript_jsonl_path": chapter.get("transcript_jsonl_path"),
                }
            )
            chunks.append(row)
    return chunks


def merge_accepted_records(fact_root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    defects: list[str] = []
    records: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    paths = sorted(fact_root.glob("*/accepted_records.jsonl"))
    if (fact_root / "accepted_records.jsonl").exists():
        paths.append(fact_root / "accepted_records.jsonl")
    if not paths:
        defects.append(f"{fact_root}:no_accepted_records_jsonl")
        return records, defects

    for path in paths:
        try:
            rows = load_jsonl(path)
        except Exception as exc:
            defects.append(f"{path}:load_failed:{exc}")
            continue
        for line_no, row in enumerate(rows, start=1):
            key = str(row.get("record_id") or row.get("_key") or "")
            if not key:
                defects.append(f"{path}:line_{line_no}:missing_record_id")
                continue
            if key in seen_keys:
                defects.append(f"{path}:line_{line_no}:duplicate_record_id:{key}")
                continue
            seen_keys.add(key)
            records.append(row)
    return records, defects


def split_chunk_sections(chunk: dict[str, Any]) -> tuple[str, str, str]:
    context_start = chunk["context_start_char"]
    primary_start = chunk["primary_start_char"]
    primary_end = chunk["primary_end_char"]
    context_end = chunk["context_end_char"]
    chunk_text = chunk["chunk_text"]
    before = chunk_text[: primary_start - context_start]
    primary = chunk_text[primary_start - context_start : primary_end - context_start]
    after = chunk_text[primary_end - context_start : context_end - context_start]
    return before, primary, after


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalized_span_matches(haystack: str, needle: str) -> list[tuple[int, int]]:
    normalized_chars: list[str] = []
    raw_index_for_normalized: list[int] = []
    in_space = False
    for raw_index, char in enumerate(haystack):
        if char.isspace():
            if normalized_chars and not in_space:
                normalized_chars.append(" ")
                raw_index_for_normalized.append(raw_index)
                in_space = True
            continue
        normalized_chars.append(char)
        raw_index_for_normalized.append(raw_index)
        in_space = False

    normalized_haystack = "".join(normalized_chars).strip()
    leading_trim = 0
    while leading_trim < len(normalized_chars) and normalized_chars[leading_trim] == " ":
        leading_trim += 1
    raw_index_for_trimmed = raw_index_for_normalized[leading_trim : leading_trim + len(normalized_haystack)]
    normalized_needle = normalize_space(needle)
    if not normalized_needle:
        return []

    matches: list[tuple[int, int]] = []
    search_from = 0
    while True:
        pos = normalized_haystack.find(normalized_needle, search_from)
        if pos < 0:
            break
        end_pos = pos + len(normalized_needle) - 1
        if end_pos < len(raw_index_for_trimmed):
            matches.append((raw_index_for_trimmed[pos], raw_index_for_trimmed[end_pos] + 1))
        search_from = pos + 1
    return matches


def exactify_quote(record: dict[str, Any], primary: str) -> tuple[dict[str, Any], str | None]:
    quote = record.get("evidence_quote")
    if not isinstance(quote, str) or not quote:
        return record, None
    if primary.find(quote) >= 0:
        return record, None
    matches = normalized_span_matches(primary, quote)
    if len(matches) != 1:
        return record, None
    start, end = matches[0]
    repaired = dict(record)
    repaired["evidence_quote"] = primary[start:end]
    return repaired, "evidence_quote_whitespace_exactified"


def evidence_span(record: dict[str, Any], chunk: dict[str, Any]) -> tuple[int, int]:
    quote = record.get("evidence_quote")
    if not isinstance(quote, str) or not quote:
        raise ValueError("record evidence_quote must be a non-empty string")
    before, primary, _after = split_chunk_sections(chunk)
    local = primary.find(quote)
    if local < 0:
        raise ValueError("evidence_quote is not in primary_text")
    local_in_chunk = len(before) + local
    start = int(chunk["context_start_char"]) + local_in_chunk
    return start, start + len(quote)


def enrich_records(
    records: list[dict[str, Any]],
    chunk: dict[str, Any],
    meta: dict[str, str],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    persona_id = str(meta.get("persona_id") or "").strip()
    for index, record in enumerate(records, start=1):
        evidence_start, evidence_end = evidence_span(record, chunk)
        record_id = f"{chunk['record_id_prefix']}{index:03d}"
        question = str(record["question"]).strip()
        answer = str(record["answer"]).strip()
        claim = str(record["claim"]).strip()
        evidence = str(record["evidence_quote"]).strip()
        text = f"{question}\n\n{answer}\n\nClaim: {claim}\n\nEvidence: {evidence}"
        tags = [
            "persona_memory",
            "record_type:persona_qra_fact",
            "source-grounded",
            f"book:{slugify(meta['book'])}",
            f"chapter:{slugify(meta['chapter_id'])}",
        ]
        if persona_id:
            tags.append(f"persona:{persona_id}")
        enriched.append(
            {
                **record,
                "schema_version": "fact-extractor-accepted-record.v1",
                "_key": record_id,
                "record_id": record_id,
                "type": "persona_memory_record",
                "record_type": "persona_qra_fact",
                "memory_collection": "persona_memory",
                "persona_id": persona_id or None,
                "persona_ids": [persona_id] if persona_id else [],
                "question_text": question,
                "answer_text": answer,
                "claim_text": claim,
                "evidence_text": evidence,
                "title": question,
                "text": text,
                "retrieval_text": text,
                "validation_status": "accepted",
                "canon_status": "source_grounded",
                "upsert_eligible": bool(persona_id),
                "dream_safe": True,
                "scope": "persona-dream" if persona_id else "fact-extraction",
                "tags": tags,
                "book": meta["book"],
                "chapter": meta["chapter"],
                "chapter_id": meta["chapter_id"],
                "chunk_id": chunk["chunk_id"],
                "document_id": chunk.get("document_id"),
                "source_path": chunk.get("source_path"),
                "source_sha256": chunk.get("source_sha256"),
                "source_doc_key": meta["chapter_id"],
                "source_section_key": chunk["chunk_id"],
                "source_ref": {
                    "book": meta["book"],
                    "chapter": meta["chapter"],
                    "chapter_id": meta["chapter_id"],
                    "chunk_id": chunk["chunk_id"],
                    "source_path": chunk.get("source_path"),
                    "primary_start_char": chunk.get("primary_start_char"),
                    "primary_end_char": chunk.get("primary_end_char"),
                    "evidence_start_char": evidence_start,
                    "evidence_end_char": evidence_end,
                },
                "primary_start_char": chunk.get("primary_start_char"),
                "primary_end_char": chunk.get("primary_end_char"),
                "context_start_char": chunk.get("context_start_char"),
                "context_end_char": chunk.get("context_end_char"),
                "evidence_start_char": evidence_start,
                "evidence_end_char": evidence_end,
                "evidence_quote_sha256": sha256_text(record["evidence_quote"]),
            }
        )
    return enriched


def accepted_metadata_defects(record: dict[str, Any], path: Path, line_no: int) -> list[str]:
    defects: list[str] = []
    missing = sorted(key for key in ACCEPTED_RECORD_METADATA_KEYS if key not in record)
    if missing:
        defects.append(f"{path}:line_{line_no}:missing_metadata:{missing}")
    if record.get("schema_version") != "fact-extractor-accepted-record.v1":
        defects.append(f"{path}:line_{line_no}:bad_schema_version:{record.get('schema_version')}")
    if not record.get("chapter_id") or not record.get("chapter"):
        defects.append(f"{path}:line_{line_no}:missing_chapter_identity")
    if record.get("_key") != record.get("record_id"):
        defects.append(f"{path}:line_{line_no}:key_record_id_mismatch")
    if record.get("memory_collection") != "persona_memory":
        defects.append(f"{path}:line_{line_no}:bad_memory_collection:{record.get('memory_collection')}")
    if record.get("upsert_eligible") and not record.get("persona_id"):
        defects.append(f"{path}:line_{line_no}:upsert_eligible_without_persona_id")
    for forbidden in ("embedding", "embedding_visual", "vector"):
        if forbidden in record:
            defects.append(f"{path}:line_{line_no}:forbidden_inline_vector_field:{forbidden}")
    tags = record.get("tags")
    if not isinstance(tags, list) or "persona_memory" not in tags or "record_type:persona_qra_fact" not in tags:
        defects.append(f"{path}:line_{line_no}:bad_tags")
    if not isinstance(record.get("evidence_start_char"), int) or not isinstance(record.get("evidence_end_char"), int):
        defects.append(f"{path}:line_{line_no}:bad_evidence_span")
    elif record["evidence_end_char"] <= record["evidence_start_char"]:
        defects.append(f"{path}:line_{line_no}:empty_evidence_span")
    return defects


def render_prompt(chunk: dict[str, Any], min_records: int, max_records: int, meta: dict[str, str]) -> str:
    before, primary, after = split_chunk_sections(chunk)
    return f"""Return JSONL only. The first character of your response must be {{. Each output line must be one complete JSON object. Do not use markdown fences. Do not return a wrapper object, array, bullet list, explanation, or trailing commentary.

Task:
Extract dense, source-grounded QRA/fact candidates from the supplied text. Use only the supplied text. Do not use outside lore, later chapters, summaries, adaptations, or prior model knowledge.

You are given three sections:
- context_before: context only
- primary_text: the only section from which evidence_quote may be copied
- context_after: context only

Density:
Extract {min_records}-{max_records} minimal records from primary_text if supported. Return fewer only if fewer are directly supported. Prefer recall-useful atomic records: one event, state, relationship, claim, perception, belief, intention, emotion, or change per record.
You must return at most {max_records} JSONL lines. A response with more than {max_records} records is invalid and will be rejected. If there are many possible facts, choose the {max_records} most recall-useful records and stop.

Each JSONL line must have exactly these fields:
{{"question":"string","answer":"string","claim":"string","evidence_quote":"exact contiguous substring from primary_text","factuality":"narration_assertion|character_speech|character_thought|reported_story|uncertain_narration","tom":null}}

For non-null tom, use exactly:
{{"holder":"string","mental_state":"belief|intention|emotion|perception|preference|uncertainty|evaluation","target":"string"}}

Rules:
- Never output more than {max_records} records.
- factuality must be exactly one of: narration_assertion, character_speech, character_thought, reported_story, uncertain_narration.
- Do not invent factuality values. Never output character_perception, dialogue_claim, character_belief, rumor, or inferred_from_action.
- For perceived events narrated as happening in the scene, use factuality = narration_assertion and put the perception signal in tom when needed.
- evidence_quote must be copied exactly from primary_text.
- evidence_quote must be one uninterrupted contiguous span from primary_text.
- evidence_quote must be short: prefer 4-18 words, and use at most one sentence unless the source sentence itself is shorter than the needed proof.
- Do not quote an entire paragraph to prove one fact.
- If a fact needs two distant pieces of evidence, create a narrower record supported by one short exact quote instead of stitching a long quote.
- Do not stitch separate phrases or sentences together; if intervening source text exists, include it exactly or choose a shorter single quote.
- Do not omit words, sentences, punctuation, or speaker turns from inside evidence_quote.
- Bad evidence_quote: "The first sentence. The third sentence." when primary_text contains a second sentence between them.
- Good evidence_quote: the smallest exact phrase or single source sentence that proves the record.
- Do not use evidence_quote from context_before or context_after.
- Treat primary_text as authoritative even if names, titles, spelling, grammar, or OCR look wrong.
- Do not correct, normalize, canonicalize, modernize, or lore-fix any source spelling in evidence_quote, question, answer, claim, entities, or tom fields.
- If primary_text says "Vipers", "Torgadden", "Ekadon", or any other apparently unusual spelling, use exactly that source spelling.
- Every question must be useful for later retrieval.
- Every answer must be concise but complete.
- claim must be one atomic fact or mental-state claim supported by evidence_quote.
- Do not produce chapter summaries, literary analysis, symbolism, or generic observations.
- Do not combine multiple unrelated facts into one record.
- Do not duplicate records unless evidence, state, time, or ToM holder/target differs.
- If the answer depends on a character belief, thought, speech, uncertainty, or report, make that explicit.
- Use tom only when the quote directly supports a mental state, belief, intention, emotion, perception, preference, uncertainty, or evaluation. Otherwise tom must be null.

Input metadata:
BOOK: {meta["book"]}
CHAPTER: {meta["chapter"]}
CHAPTER_ID: {meta["chapter_id"]}
CHUNK_ID: {chunk["chunk_id"]}

<context_before>
{before}
</context_before>

<primary_text>
{primary}
</primary_text>

<context_after>
{after}
</context_after>
"""


def make_payload(
    chunk: dict[str, Any],
    min_records: int,
    max_records: int,
    meta: dict[str, str],
    model: str,
    max_tokens: int,
    json_object: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": render_prompt(chunk, min_records, max_records, meta)}],
        "temperature": 0,
        "stream": True,
    }
    if max_tokens > 0:
        payload["max_tokens"] = max_tokens
    if json_object:
        payload["response_format"] = {"type": "json_object"}
    return payload


def parse_sse_content(raw_sse: str) -> tuple[str, dict[str, Any]]:
    content_parts: list[str] = []
    events = 0
    done = False
    errors: list[str] = []
    finish_reasons: list[str] = []
    for line in raw_sse.splitlines():
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data:
            continue
        events += 1
        if data == "[DONE]":
            done = True
            continue
        try:
            obj = json.loads(data)
        except Exception as exc:
            errors.append(f"sse_json_parse:{exc}:{data[:120]}")
            continue
        if "error" in obj:
            errors.append(f"sse_error:{obj['error']}")
        choice = (obj.get("choices") or [{}])[0]
        if choice.get("finish_reason"):
            finish_reasons.append(str(choice["finish_reason"]))
        delta = choice.get("delta") or {}
        if "content" in delta:
            content_parts.append(delta.get("content") or "")
        elif ((choice.get("message") or {}).get("content")):
            content_parts.append((choice.get("message") or {}).get("content") or "")
    return "".join(content_parts), {
        "sse_data_events": events,
        "sse_done_seen": done,
        "sse_parse_errors": errors,
        "finish_reasons": finish_reasons,
        "stream_complete_ok": done or any(reason in {"stop", "length"} for reason in finish_reasons),
    }


def validate_content(content: str, chunk: dict[str, Any], min_records: int, max_records: int) -> dict[str, Any]:
    _before, primary, _after = split_chunk_sections(chunk)
    report: dict[str, Any] = {
        "accepted": False,
        "parse_ok": False,
        "raw_jsonl_only_ok": False,
        "raw_record_count": 0,
        "record_count": 0,
        "record_count_target_ok": False,
        "record_count_hard_ok": False,
        "schema_ok": True,
        "quotes_exact_ok": True,
        "quotes_primary_span_ok": True,
        "closed_vocab_ok": True,
        "tom_shape_ok": True,
        "nonempty_fields_ok": True,
        "duplicates_ok": True,
        "defects": [],
        "warnings": [],
        "dropped_records": [],
        "records": [],
    }
    if "```" in content or content.lstrip().startswith("["):
        report["defects"].append("not_strict_jsonl_shape")

    lines = [line for line in content.splitlines() if line.strip()]
    records = []
    for idx, line in enumerate(lines, start=1):
        try:
            records.append(json.loads(line))
        except Exception as exc:
            report["defects"].append(f"line_{idx}_json_parse_failed:{exc}:{line[:160]}")

    report["parse_ok"] = len(records) == len(lines) and bool(records)
    report["raw_jsonl_only_ok"] = report["parse_ok"] and "not_strict_jsonl_shape" not in report["defects"]
    report["raw_record_count"] = len(records)
    seen: set[tuple[str, str, str, str]] = set()
    valid_records: list[dict[str, Any]] = []
    for idx, rec in enumerate(records, start=1):
        rid = f"{chunk['chunk_id']}:line_{idx}"
        record_defects: list[str] = []
        if not isinstance(rec, dict):
            record_defects.append(f"{rid}:not_object")
            report["dropped_records"].append({"line": idx, "defects": record_defects, "record": rec})
            continue
        rec, repair_warning = exactify_quote(rec, primary)
        if repair_warning:
            report["warnings"].append(f"{rid}:{repair_warning}")
        if set(rec) != REQUIRED_KEYS:
            record_defects.append(f"{rid}:key_mismatch:{sorted(set(rec) ^ REQUIRED_KEYS)}")
        for key in ("question", "answer", "claim", "evidence_quote", "factuality"):
            if not isinstance(rec.get(key), str) or not rec.get(key, "").strip():
                record_defects.append(f"{rid}:empty_{key}")
        if rec.get("factuality") not in FACTUALITY:
            record_defects.append(f"{rid}:bad_factuality:{rec.get('factuality')}")
        quote = rec.get("evidence_quote")
        local = primary.find(quote) if isinstance(quote, str) else -1
        if local < 0:
            record_defects.append(f"{rid}:quote_not_exact_in_primary_text")
        tom = rec.get("tom")
        if tom is not None:
            if (
                not isinstance(tom, dict)
                or set(tom) != TOM_KEYS
                or tom.get("mental_state") not in TOM_STATES
                or not tom.get("holder")
                or not tom.get("target")
            ):
                record_defects.append(f"{rid}:bad_tom_shape")
        key = (
            str(rec.get("question", "")).strip().lower(),
            str(rec.get("answer", "")).strip().lower(),
            str(rec.get("claim", "")).strip().lower(),
            str(rec.get("evidence_quote", "")).strip(),
        )
        if key in seen:
            record_defects.append(f"{rid}:duplicate")
        seen.add(key)

        if record_defects:
            report["dropped_records"].append({"line": idx, "defects": record_defects, "record": rec})
        else:
            valid_records.append(rec)

    if report["dropped_records"]:
        report["warnings"].append(f"dropped_invalid_records:{len(report['dropped_records'])}")

    report["records"] = valid_records
    report["record_count"] = len(valid_records)
    report["record_count_target_ok"] = min_records <= len(valid_records) <= max_records
    report["record_count_hard_ok"] = 1 <= len(valid_records) <= max_records
    if valid_records and not report["record_count_target_ok"]:
        report["warnings"].append(f"density_warning:expected_{min_records}_{max_records}:got_{len(valid_records)}")
    report["accepted"] = all(
        bool(report[key])
        for key in (
            "parse_ok",
            "raw_jsonl_only_ok",
            "record_count_hard_ok",
            "schema_ok",
            "quotes_exact_ok",
            "quotes_primary_span_ok",
            "closed_vocab_ok",
            "tom_shape_ok",
            "nonempty_fields_ok",
            "duplicates_ok",
        )
    )
    return report


async def extract_one(
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
    chunk: dict[str, Any],
    config: BatchConfig,
    retry_plan: list[dict[str, int]],
    meta: dict[str, str],
) -> ChunkResult:
    chunk_id = chunk["chunk_id"]
    chunk_dir = config.out_dir / "chunks" / chunk_id
    chunk_dir.mkdir(parents=True, exist_ok=True)
    (chunk_dir / "input_chunk_metadata.json").write_text(
        json.dumps({k: v for k, v in chunk.items() if k != "chunk_text"}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    last_validation: dict[str, Any] = {"accepted": False, "record_count": 0, "defects": ["no_attempts_run"]}
    total_started = time.time()
    existing_attempt_numbers = [
        int(match.group(1))
        for path in chunk_dir.glob("attempt_*")
        if (match := re.search(r"attempt_(\d+)$", path.name))
    ]
    next_attempt_no = 1 if config.force else max(existing_attempt_numbers, default=0) + 1

    for retry_index, attempt in enumerate(retry_plan, start=1):
        attempt_no = next_attempt_no + retry_index - 1
        attempt_dir = chunk_dir / f"attempt_{attempt_no:02d}"
        attempt_dir.mkdir(parents=True, exist_ok=True)
        min_records = attempt["min_records"]
        max_records = attempt["max_records"]
        timeout_s = attempt["timeout_s"]
        payload = make_payload(
            chunk,
            min_records,
            max_records,
            meta,
            config.model,
            config.max_tokens,
            config.json_object,
        )
        (attempt_dir / "prompt_payload.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        started = time.time()
        http_status: int | None = None
        raw_parts: list[str] = []
        request_defects: list[str] = []
        stream_path = attempt_dir / "stream.raw.sse"
        async with semaphore:
            response_cm = None
            resp = None
            try:
                response_cm = session.post(
                    config.url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(
                        total=timeout_s,
                        sock_read=config.stream_idle_timeout,
                    ),
                )
                try:
                    async with asyncio.timeout(config.response_start_timeout):
                        resp = await response_cm.__aenter__()
                except TimeoutError as exc:
                    raise TimeoutError(f"response_start_timeout_{config.response_start_timeout}s") from exc

                http_status = resp.status
                with stream_path.open("w", encoding="utf-8") as stream_out:
                    async for data in resp.content.iter_any():
                        if data:
                            text = data.decode("utf-8", errors="replace")
                            raw_parts.append(text)
                            stream_out.write(text)
                            stream_out.flush()
            except Exception as exc:
                request_defects.append(f"request_failed:{type(exc).__name__}:{exc}")
            finally:
                if response_cm is not None and resp is not None:
                    try:
                        await response_cm.__aexit__(None, None, None)
                    except Exception:
                        pass

        raw_sse = "".join(raw_parts)
        elapsed_s = round(time.time() - started, 3)
        if not stream_path.exists():
            stream_path.write_text(raw_sse, encoding="utf-8")
        content, stream_report = parse_sse_content(raw_sse)
        (attempt_dir / "model_content.raw.jsonl").write_text(content, encoding="utf-8")
        validation = validate_content(content, chunk, min_records, max_records) if content else {
            "accepted": False,
            "record_count": 0,
            "defects": ["empty_model_content"],
        }
        validation.update(stream_report)
        if not validation.get("stream_complete_ok"):
            validation["accepted"] = False
            validation.setdefault("defects", []).append("stream_incomplete")
        if "length" in validation.get("finish_reasons", []):
            validation["accepted"] = False
            validation.setdefault("defects", []).append("finish_reason_length")
        if http_status != 200:
            validation["accepted"] = False
            validation.setdefault("defects", []).append(f"http_status_{http_status}")
        validation.setdefault("defects", []).extend(request_defects)
        validation["attempt_no"] = attempt_no
        validation["attempt_contract"] = attempt
        validation["http_status"] = http_status
        validation["elapsed_s"] = elapsed_s
        validation["stream_bytes"] = len(raw_sse.encode("utf-8"))
        (attempt_dir / "validation_report.json").write_text(
            json.dumps(validation, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        last_validation = validation
        if validation.get("accepted") and not request_defects:
            enriched_records = enrich_records(validation.get("records", []), chunk, meta)
            accepted_content = "\n".join(
                json.dumps(record, ensure_ascii=False, separators=(",", ":"))
                for record in enriched_records
            )
            if accepted_content:
                accepted_content += "\n"
            (chunk_dir / "accepted_attempt.txt").write_text(f"attempt_{attempt_no:02d}\n", encoding="utf-8")
            (chunk_dir / "accepted_records.jsonl").write_text(accepted_content, encoding="utf-8")
            return ChunkResult(
                chunk_id=chunk_id,
                accepted=True,
                record_count=int(validation.get("record_count") or 0),
                elapsed_s=round(time.time() - total_started, 3),
                http_status=http_status,
                defects=list(validation.get("defects") or []),
                chunk_dir=str(chunk_dir),
                accepted_attempt=attempt_no,
                attempts=attempt_no,
            )
        if retry_index < len(retry_plan) and config.retry_delay > 0:
            await asyncio.sleep(config.retry_delay)

    (chunk_dir / "validation_report.final.json").write_text(
        json.dumps(last_validation, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return ChunkResult(
        chunk_id=chunk_id,
        accepted=False,
        record_count=int(last_validation.get("record_count") or 0),
        elapsed_s=round(time.time() - total_started, 3),
        http_status=last_validation.get("http_status"),
        defects=list(last_validation.get("defects") or []),
        chunk_dir=str(chunk_dir),
        accepted_attempt=None,
        attempts=len(retry_plan),
    )


def collect_existing_results(out_dir: Path) -> list[ChunkResult]:
    results: list[ChunkResult] = []
    chunks_dir = out_dir / "chunks"
    if not chunks_dir.exists():
        return results
    for chunk_dir in sorted(path for path in chunks_dir.iterdir() if path.is_dir()):
        accepted_records = chunk_dir / "accepted_records.jsonl"
        if not accepted_records.exists():
            continue
        records = [line for line in accepted_records.read_text(encoding="utf-8").splitlines() if line.strip()]
        attempt_path = chunk_dir / "accepted_attempt.txt"
        attempt_no: int | None = None
        if attempt_path.exists():
            match = re.search(r"(\d+)", attempt_path.read_text(encoding="utf-8"))
            attempt_no = int(match.group(1)) if match else None
        results.append(
            ChunkResult(
                chunk_id=chunk_dir.name,
                accepted=True,
                record_count=len(records),
                elapsed_s=0,
                http_status=None,
                defects=[],
                chunk_dir=str(chunk_dir),
                accepted_attempt=attempt_no,
                attempts=attempt_no or 0,
            )
        )
    return results


def recover_existing_attempts(out_dir: Path, chunks: list[dict[str, Any]], meta: dict[str, str]) -> list[ChunkResult]:
    results: list[ChunkResult] = []
    chunks_dir = out_dir / "chunks"
    if not chunks_dir.exists():
        return results

    for chunk in chunks:
        chunk_id = chunk["chunk_id"]
        chunk_dir = chunks_dir / chunk_id
        if not chunk_dir.exists() or (chunk_dir / "accepted_records.jsonl").exists():
            continue

        for attempt_dir in sorted(path for path in chunk_dir.glob("attempt_*") if path.is_dir()):
            content_path = attempt_dir / "model_content.raw.jsonl"
            old_report_path = attempt_dir / "validation_report.json"
            if not content_path.exists() or not old_report_path.exists():
                continue

            old_report = json.loads(old_report_path.read_text(encoding="utf-8"))
            attempt_contract = old_report.get("attempt_contract") or {}
            min_records = int(attempt_contract.get("min_records") or 1)
            max_records = int(attempt_contract.get("max_records") or max(min_records, 1))
            content = content_path.read_text(encoding="utf-8")
            validation = validate_content(content, chunk, min_records, max_records) if content else {
                "accepted": False,
                "record_count": 0,
                "defects": ["empty_model_content"],
            }

            validation["sse_data_events"] = old_report.get("sse_data_events")
            validation["sse_done_seen"] = old_report.get("sse_done_seen")
            validation["sse_parse_errors"] = old_report.get("sse_parse_errors", [])
            validation["finish_reasons"] = old_report.get("finish_reasons", [])
            validation["stream_complete_ok"] = bool(old_report.get("stream_complete_ok"))
            validation["attempt_no"] = old_report.get("attempt_no")
            validation["attempt_contract"] = attempt_contract
            validation["http_status"] = old_report.get("http_status")
            validation["elapsed_s"] = old_report.get("elapsed_s")
            validation["stream_bytes"] = old_report.get("stream_bytes")

            old_defects = list(old_report.get("defects") or [])
            request_defects = [defect for defect in old_defects if str(defect).startswith("request_failed:")]
            if not validation.get("stream_complete_ok"):
                validation["accepted"] = False
                validation.setdefault("defects", []).append("stream_incomplete")
            if "length" in validation.get("finish_reasons", []):
                validation["accepted"] = False
                validation.setdefault("defects", []).append("finish_reason_length")
            if validation.get("http_status") != 200:
                validation["accepted"] = False
                validation.setdefault("defects", []).append(f"http_status_{validation.get('http_status')}")
            if request_defects:
                validation["accepted"] = False
                validation.setdefault("defects", []).extend(request_defects)

            (attempt_dir / "validation_report.revalidated.json").write_text(
                json.dumps(validation, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            if validation.get("accepted"):
                attempt_no = validation.get("attempt_no")
                enriched_records = enrich_records(validation.get("records", []), chunk, meta)
                accepted_content = "\n".join(
                    json.dumps(record, ensure_ascii=False, separators=(",", ":"))
                    for record in enriched_records
                )
                if accepted_content:
                    accepted_content += "\n"
                (chunk_dir / "accepted_attempt.txt").write_text(f"attempt_{attempt_no:02d}\n", encoding="utf-8")
                (chunk_dir / "accepted_records.jsonl").write_text(accepted_content, encoding="utf-8")
                results.append(
                    ChunkResult(
                        chunk_id=chunk_id,
                        accepted=True,
                        record_count=int(validation.get("record_count") or 0),
                        elapsed_s=0,
                        http_status=validation.get("http_status"),
                        defects=list(validation.get("defects") or []),
                        chunk_dir=str(chunk_dir),
                        accepted_attempt=int(attempt_no) if attempt_no is not None else None,
                        attempts=int(attempt_no) if attempt_no is not None else 0,
                    )
                )
                break

    return results


def write_aggregate(out_dir: Path, chunks: list[dict[str, Any]], results: list[ChunkResult]) -> dict[str, Any]:
    by_id = {result.chunk_id: result for result in results}
    ordered_results = [by_id[chunk["chunk_id"]] for chunk in chunks if chunk["chunk_id"] in by_id]
    accepted = [result for result in ordered_results if result.accepted]
    missing = [chunk["chunk_id"] for chunk in chunks if chunk["chunk_id"] not in by_id]
    aggregate_defects: list[str] = []
    if not chunks:
        aggregate_defects.append("zero_chunks_selected")
    metadata_defects: list[str] = []
    accepted_record_lines: list[str] = []
    for result in accepted:
        records_path = Path(result.chunk_dir) / "accepted_records.jsonl"
        if not records_path.exists():
            metadata_defects.append(f"{records_path}:missing_accepted_records_jsonl")
            continue
        for line_no, line in enumerate(records_path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except Exception as exc:
                metadata_defects.append(f"{records_path}:line_{line_no}:json_parse_failed:{exc}")
                continue
            metadata_defects.extend(accepted_metadata_defects(record, records_path, line_no))
            accepted_record_lines.append(line)
    metadata_ok = not metadata_defects
    aggregate = {
        "schema_version": "fact-extractor-result.v1",
        "created_at": now(),
        "accepted": bool(chunks) and len(accepted) == len(chunks) and not missing and metadata_ok,
        "completed_chunks": len(ordered_results),
        "accepted_chunks": len(accepted),
        "failed_chunks": len(chunks) - len(accepted),
        "missing_chunks": missing,
        "aggregate_defects": aggregate_defects,
        "total_records": sum(result.record_count for result in accepted),
        "accepted_record_metadata_ok": metadata_ok,
        "accepted_record_metadata_defects": metadata_defects,
        "memory_writes_performed": False,
        "forbidden_writes": ["persona_memory", "lessons", "arangodb"],
        "results": [asdict(result) for result in ordered_results],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "aggregate_report.json").write_text(json.dumps(aggregate, indent=2, ensure_ascii=False), encoding="utf-8")
    accepted_path = out_dir / "accepted_records.jsonl"
    with accepted_path.open("w", encoding="utf-8") as out:
        if accepted_record_lines:
            out.write("\n".join(accepted_record_lines))
            out.write("\n")
    (out_dir / "status.md").write_text(
        "\n".join(
            [
                f"Status: {'ACCEPTED_FACT_EXTRACTION_ARTIFACT' if aggregate['accepted'] else 'REVISE_FACT_EXTRACTION_ARTIFACT'}",
                f"Completed chunks: {aggregate['completed_chunks']}",
                f"Accepted chunks: {aggregate['accepted_chunks']}",
                f"Failed chunks: {aggregate['failed_chunks']}",
                f"Accepted record total: {aggregate['total_records']}",
                f"Accepted record metadata: {'ok' if metadata_ok else 'failed'}",
                "",
                "No memory writes were performed.",
            ]
        ),
        encoding="utf-8",
    )
    return aggregate


def count_jsonl_rows(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def chapter_progress_counts(chapter_out: Path) -> dict[str, Any]:
    chunks_path = chapter_out / "chunks.jsonl"
    progress_path = chapter_out / "progress.as_completed.jsonl"
    aggregate_path = chapter_out / "aggregate_report.json"
    total_chunks = count_jsonl_rows(chunks_path)
    completed_chunks = 0
    accepted_chunks = 0
    failed_chunks = 0
    accepted_records = 0

    if progress_path.exists():
        progress_rows = load_jsonl(progress_path)
        completed_chunks = len(progress_rows)
        accepted_chunks = sum(1 for row in progress_rows if row.get("accepted") is True)
        failed_chunks = sum(1 for row in progress_rows if row.get("accepted") is False)
        accepted_records = sum(int(row.get("record_count") or 0) for row in progress_rows if row.get("accepted") is True)

    aggregate: dict[str, Any] = {}
    if aggregate_path.exists():
        aggregate = json.loads(aggregate_path.read_text(encoding="utf-8") or "{}")
        total_chunks = total_chunks or len(aggregate.get("results") or [])
        completed_chunks = int(aggregate.get("completed_chunks") or completed_chunks)
        accepted_chunks = int(aggregate.get("accepted_chunks") or accepted_chunks)
        failed_chunks = int(aggregate.get("failed_chunks") or failed_chunks)
        accepted_records = int(aggregate.get("total_records") or accepted_records)

    return {
        "total_chunks": total_chunks,
        "completed_chunks": completed_chunks,
        "accepted_chunks": accepted_chunks,
        "failed_chunks": failed_chunks,
        "accepted_records": accepted_records,
        "aggregate": aggregate,
    }


def append_book_progress_event(
    *,
    book_root: Path,
    chapter_out: Path,
    book: str,
    book_id: str,
    chapter: str,
    chapter_id: str,
    status: str,
) -> dict[str, Any]:
    allowed = {"started", "running", "accepted", "failed"}
    if status not in allowed:
        raise ValueError(f"invalid_book_progress_status:{status}")

    counts = chapter_progress_counts(chapter_out)
    timestamp = now()
    event = {
        "schema_version": "fact-extractor-book-progress.v1",
        "timestamp": timestamp,
        "book": book,
        "book_id": book_id,
        "chapter": chapter,
        "chapter_id": chapter_id,
        "status": status,
        "total_chunks": counts["total_chunks"],
        "completed_chunks": counts["completed_chunks"],
        "accepted_chunks": counts["accepted_chunks"],
        "failed_chunks": counts["failed_chunks"],
        "accepted_records": counts["accepted_records"],
        "artifacts": {
            "book_root": str(book_root),
            "chapter_out": str(chapter_out),
            "chunks": str(chapter_out / "chunks.jsonl"),
            "progress": str(chapter_out / "progress.as_completed.jsonl"),
            "aggregate_report": str(chapter_out / "aggregate_report.json"),
            "accepted_records": str(chapter_out / "accepted_records.jsonl"),
        },
        "memory_writes_performed": False,
        "forbidden_writes": ["persona_memory", "lessons", "arangodb"],
    }
    if status == "started":
        event["started_at"] = timestamp
    if status in {"accepted", "failed"}:
        event["completed_at"] = timestamp
        aggregate = counts.get("aggregate") or {}
        if aggregate:
            event["chapter_aggregate_accepted"] = bool(aggregate.get("accepted"))

    book_root.mkdir(parents=True, exist_ok=True)
    progress_path = book_root / "book_progress.jsonl"
    with progress_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False))
        handle.write("\n")
    return event


def summarize_book_progress(book_root: Path) -> dict[str, Any]:
    progress_path = book_root / "book_progress.jsonl"
    if not progress_path.exists():
        raise FileNotFoundError(f"{progress_path}:missing_book_progress_jsonl")

    rows = load_jsonl(progress_path)
    latest_by_chapter: dict[str, dict[str, Any]] = {}
    for line_no, row in enumerate(rows, start=1):
        chapter_id = str(row.get("chapter_id") or "").strip()
        if not chapter_id:
            raise ValueError(f"{progress_path}:line_{line_no}:missing_chapter_id")
        latest_by_chapter[chapter_id] = {**row, "event_index": line_no}

    status_counts = {"started": 0, "running": 0, "accepted": 0, "failed": 0}
    chapters = sorted(latest_by_chapter.values(), key=lambda row: str(row.get("chapter_id") or ""))
    for chapter in chapters:
        status = str(chapter.get("status") or "")
        if status in status_counts:
            status_counts[status] += 1

    def sum_int(key: str) -> int:
        return sum(int(chapter.get(key) or 0) for chapter in chapters)

    latest_event = rows[-1] if rows else {}
    summary = {
        "schema_version": "fact-extractor-book-progress-summary.v1",
        "book_root": str(book_root),
        "progress_path": str(progress_path),
        "book": latest_event.get("book"),
        "book_id": latest_event.get("book_id"),
        "event_count": len(rows),
        "chapter_count": len(chapters),
        "chapters_started": status_counts["started"],
        "chapters_running": status_counts["running"],
        "chapters_accepted": status_counts["accepted"],
        "chapters_failed": status_counts["failed"],
        "completed_chunks": sum_int("completed_chunks"),
        "total_chunks": sum_int("total_chunks"),
        "accepted_chunks": sum_int("accepted_chunks"),
        "failed_chunks": sum_int("failed_chunks"),
        "accepted_records": sum_int("accepted_records"),
        "latest_event_timestamp": latest_event.get("timestamp"),
        "chapters": chapters,
        "memory_writes_performed": False,
        "forbidden_writes": ["persona_memory", "lessons", "arangodb"],
    }
    return summary


async def run_batch(config: BatchConfig) -> int:
    config.out_dir.mkdir(parents=True, exist_ok=True)
    if config.force:
        stale_paths = [
            config.out_dir / "chunks",
            config.out_dir / "progress.as_completed.jsonl",
            config.out_dir / "aggregate_report.json",
            config.out_dir / "accepted_records.jsonl",
            config.out_dir / "status.md",
            config.out_dir / "run_manifest.json",
        ]
        for stale_path in stale_paths:
            if stale_path.is_dir():
                shutil.rmtree(stale_path)
            elif stale_path.exists():
                stale_path.unlink()
    chunks = load_chunks(config.chunks_path)
    selected = chunks[: config.limit] if config.limit else chunks
    meta = {
        "book": config.book,
        "chapter": config.chapter,
        "chapter_id": config.chapter_id,
        "persona_id": config.persona_id,
    }
    retry_plan = [
        {"min_records": config.min_records, "max_records": config.max_records, "timeout_s": config.timeout},
        {"min_records": 5, "max_records": 8, "timeout_s": config.timeout},
        {"min_records": 2, "max_records": 4, "timeout_s": min(config.timeout, 240)},
    ]
    existing = collect_existing_results(config.out_dir) if not config.force else []
    recovered = recover_existing_attempts(config.out_dir, selected, meta) if not config.force else []
    existing_by_id = {result.chunk_id: result for result in [*existing, *recovered]}
    existing = list(existing_by_id.values())
    existing_ids = set(existing_by_id)
    pending = [chunk for chunk in selected if chunk["chunk_id"] not in existing_ids]
    manifest = {
        "schema_version": "fact-extractor-run-manifest.v1",
        "created_at": now(),
        "chunks_path": str(config.chunks_path),
        "out_dir": str(config.out_dir),
        "chunk_count": len(selected),
        "pending_chunk_count": len(pending),
        "concurrency": config.concurrency,
        "retry_plan": retry_plan,
        "model": config.model,
        "max_tokens": config.max_tokens,
        "json_object": config.json_object,
        "response_start_timeout": config.response_start_timeout,
        "stream_idle_timeout": config.stream_idle_timeout,
        "retry_delay": config.retry_delay,
        "metadata": meta,
        "url": config.url,
        "contract": "asyncio.as_completed + semaphore + streaming SSE + split primary/context prompt + retry degradation + minimal JSONL validation",
        "resume": not config.force,
        "memory_writes_performed": False,
        "forbidden_writes": ["persona_memory", "lessons", "arangodb"],
    }
    (config.out_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    results: list[ChunkResult] = list(existing)
    if pending:
        token = os.environ.get("SCILLM_PROXY_TOKEN") or os.environ.get("CHUTES_PROXY_TOKEN", DEFAULT_TOKEN)
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Caller-Skill": "fact-extractor",
            "Content-Type": "application/json",
        }
        semaphore = asyncio.Semaphore(config.concurrency)
        connector = aiohttp.TCPConnector(limit=config.concurrency)
        progress_path = config.out_dir / "progress.as_completed.jsonl"
        async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
            tasks = [
                asyncio.create_task(extract_one(session, semaphore, chunk, config, retry_plan, meta))
                for chunk in pending
            ]
            with progress_path.open("a", encoding="utf-8") as progress:
                for fut in asyncio.as_completed(tasks):
                    result = await fut
                    results.append(result)
                    progress.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")
                    progress.flush()
                    print(
                        json.dumps(
                            {
                                "completed": len([r for r in results if r.chunk_id in {c["chunk_id"] for c in pending}]),
                                "total": len(pending),
                                "chunk_id": result.chunk_id,
                                "accepted": result.accepted,
                                "record_count": result.record_count,
                                "elapsed_s": result.elapsed_s,
                                "accepted_attempt": result.accepted_attempt,
                                "attempts": result.attempts,
                                "defects": result.defects,
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )

    aggregate = write_aggregate(config.out_dir, selected, results)
    print(json.dumps(aggregate, indent=2, ensure_ascii=False))
    return 0 if aggregate["accepted"] else 1


@app.command()
def doctor(json_output: Annotated[bool, typer.Option("--json", help="Emit JSON only.")] = False) -> None:
    report = {
        "schema_version": "fact-extractor-doctor.v1",
        "ok": True,
        "python_imports": {
            "aiohttp": True,
            "typer": True,
        },
        "entrypoint": str(Path(__file__).resolve()),
        "scillm_proxy_token_present": bool(os.environ.get("SCILLM_PROXY_TOKEN")),
        "chutes_proxy_token_present": bool(os.environ.get("CHUTES_PROXY_TOKEN")),
        "default_url": DEFAULT_URL,
    }
    if json_output:
        typer.echo(json.dumps(report, indent=2))
    else:
        typer.echo("fact-extractor doctor ok")


@app.command("stage-book")
def stage_book_command(
    source: Annotated[Path, typer.Argument(exists=True, readable=True)],
    out: Annotated[Path, typer.Option("--out", help="Output staging directory.")],
    book: Annotated[str, typer.Option("--book", help="Book or document title.")],
    book_id: Annotated[str | None, typer.Option("--book-id", help="Stable book id. Defaults to slugified book title.")] = None,
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing staged files.")] = False,
) -> None:
    manifest = stage_book_source(
        source=source,
        out=out,
        book=book,
        book_id=book_id or slugify(book),
        force=force,
    )
    typer.echo(json.dumps(manifest, indent=2, ensure_ascii=False))


@app.command("chunk")
def chunk_command(
    input_path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    out: Annotated[Path, typer.Option("--out", help="Output chunks JSONL path.")],
    document_id: Annotated[str, typer.Option("--document-id", help="Stable document or chapter id.")],
    target_chars: Annotated[int, typer.Option("--target-chars")] = 3500,
    max_chars: Annotated[int, typer.Option("--max-chars")] = 4500,
    overlap_before_sentences: Annotated[int, typer.Option("--overlap-before-sentences")] = 2,
    overlap_after_sentences: Annotated[int, typer.Option("--overlap-after-sentences")] = 2,
) -> None:
    chunks = make_chunks(
        input_path.read_text(encoding="utf-8"),
        document_id=document_id,
        source_path=str(input_path),
        target_chars=target_chars,
        max_chars=max_chars,
        overlap_before_sentences=overlap_before_sentences,
        overlap_after_sentences=overlap_after_sentences,
    )
    write_chunks_jsonl(chunks, out)
    typer.echo(
        json.dumps(
            {
                "schema_version": "fact-extractor-chunks.v1",
                "input": str(input_path),
                "out": str(out),
                "document_id": document_id,
                "chunks": len(chunks),
                "target_chars": target_chars,
                "max_chars": max_chars,
                "overlap_before_sentences": overlap_before_sentences,
                "overlap_after_sentences": overlap_after_sentences,
            },
            indent=2,
        )
    )


@app.command("chunk-book")
def chunk_book_command(
    chapters: Annotated[Path, typer.Option("--chapters", exists=True, readable=True, help="Book chapters JSONL from extract-audiobook.")],
    out: Annotated[Path, typer.Option("--out", help="Output book-level chunks JSONL path.")],
    book: Annotated[str, typer.Option("--book", help="Book title.")],
    book_id: Annotated[str, typer.Option("--book-id", help="Stable book id.")],
    target_chars: Annotated[int, typer.Option("--target-chars")] = 3500,
    max_chars: Annotated[int, typer.Option("--max-chars")] = 4500,
    overlap_before_sentences: Annotated[int, typer.Option("--overlap-before-sentences")] = 2,
    overlap_after_sentences: Annotated[int, typer.Option("--overlap-after-sentences")] = 2,
) -> None:
    chunks = make_book_chunks(
        chapters_path=chapters,
        book=book,
        book_id=book_id,
        target_chars=target_chars,
        max_chars=max_chars,
        overlap_before_sentences=overlap_before_sentences,
        overlap_after_sentences=overlap_after_sentences,
    )
    write_chunk_dicts_jsonl(chunks, out)
    typer.echo(
        json.dumps(
            {
                "schema_version": "fact-extractor-book-chunks.v1",
                "chapters": str(chapters),
                "out": str(out),
                "book": book,
                "book_id": book_id,
                "chapter_count": len({chunk["chapter_id"] for chunk in chunks}),
                "chunks": len(chunks),
                "target_chars": target_chars,
                "max_chars": max_chars,
                "overlap_before_sentences": overlap_before_sentences,
                "overlap_after_sentences": overlap_after_sentences,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


@app.command("book-progress")
def book_progress_command(
    book_root: Annotated[Path, typer.Option("--book-root", help="Book-level fact output root.")],
    chapter_out: Annotated[Path, typer.Option("--chapter-out", exists=True, file_okay=False, readable=True, help="Per-chapter fact extraction output directory.")],
    book: Annotated[str, typer.Option("--book")],
    book_id: Annotated[str, typer.Option("--book-id")],
    chapter: Annotated[str, typer.Option("--chapter")],
    chapter_id: Annotated[str, typer.Option("--chapter-id")],
    status: Annotated[str, typer.Option("--status", help="started, running, accepted, or failed.")],
) -> None:
    try:
        event = append_book_progress_event(
            book_root=book_root,
            chapter_out=chapter_out,
            book=book,
            book_id=book_id,
            chapter=chapter,
            chapter_id=chapter_id,
            status=status,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--status") from exc
    typer.echo(json.dumps(event, indent=2, ensure_ascii=False))


@app.command("book-progress-summary")
def book_progress_summary_command(
    book_root: Annotated[Path, typer.Argument(exists=True, file_okay=False, readable=True)],
) -> None:
    try:
        summary = summarize_book_progress(book_root)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps(summary, indent=2, ensure_ascii=False))


@app.command("extract")
def extract_command(
    chunks: Annotated[Path, typer.Option("--chunks", exists=True, readable=True)],
    out: Annotated[Path, typer.Option("--out")],
    book: Annotated[str, typer.Option("--book")],
    chapter: Annotated[str, typer.Option("--chapter")],
    chapter_id: Annotated[str, typer.Option("--chapter-id")],
    persona_id: Annotated[str, typer.Option("--persona-id", help="Optional persona id for memory-upsert-shaped persona_memory records.")] = "",
    url: Annotated[str, typer.Option("--url")] = DEFAULT_URL,
    model: Annotated[str, typer.Option("--model")] = DEFAULT_MODEL,
    concurrency: Annotated[int, typer.Option("--concurrency", min=1)] = 1,
    timeout: Annotated[int, typer.Option("--timeout", min=1)] = 360,
    response_start_timeout: Annotated[int, typer.Option("--response-start-timeout", min=1)] = 45,
    stream_idle_timeout: Annotated[int, typer.Option("--stream-idle-timeout", min=1)] = 90,
    retry_delay: Annotated[int, typer.Option("--retry-delay", min=0)] = 30,
    min_records: Annotated[int, typer.Option("--min-records", min=1)] = 8,
    max_records: Annotated[int, typer.Option("--max-records", min=1)] = 12,
    max_tokens: Annotated[int, typer.Option("--max-tokens", help="Use 0 to omit max_tokens from provider payload.")] = 0,
    json_object: Annotated[bool, typer.Option("--json-object/--no-json-object", help="Request OpenAI-compatible JSON object response_format when supported.")] = False,
    limit: Annotated[int, typer.Option("--limit", min=0)] = 0,
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    config = BatchConfig(
        chunks_path=chunks,
        out_dir=out,
        book=book,
        chapter=chapter,
        chapter_id=chapter_id,
        persona_id=persona_id,
        url=url,
        model=model,
        concurrency=concurrency,
        timeout=timeout,
        response_start_timeout=response_start_timeout,
        stream_idle_timeout=stream_idle_timeout,
        retry_delay=retry_delay,
        min_records=min_records,
        max_records=max_records,
        max_tokens=max_tokens,
        json_object=json_object,
        limit=limit,
        force=force,
    )
    raise typer.Exit(asyncio.run(run_batch(config)))


@app.command("chapter")
def chapter_command(
    input_path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    out: Annotated[Path, typer.Option("--out")],
    book: Annotated[str, typer.Option("--book")],
    chapter: Annotated[str, typer.Option("--chapter")],
    chapter_id: Annotated[str, typer.Option("--chapter-id")],
    persona_id: Annotated[str, typer.Option("--persona-id", help="Optional persona id for memory-upsert-shaped persona_memory records.")] = "",
    target_chars: Annotated[int, typer.Option("--target-chars")] = 3500,
    max_chars: Annotated[int, typer.Option("--max-chars")] = 4500,
    overlap_before_sentences: Annotated[int, typer.Option("--overlap-before-sentences")] = 2,
    overlap_after_sentences: Annotated[int, typer.Option("--overlap-after-sentences")] = 2,
    url: Annotated[str, typer.Option("--url")] = DEFAULT_URL,
    model: Annotated[str, typer.Option("--model")] = DEFAULT_MODEL,
    concurrency: Annotated[int, typer.Option("--concurrency", min=1)] = 1,
    timeout: Annotated[int, typer.Option("--timeout", min=1)] = 360,
    response_start_timeout: Annotated[int, typer.Option("--response-start-timeout", min=1)] = 45,
    stream_idle_timeout: Annotated[int, typer.Option("--stream-idle-timeout", min=1)] = 90,
    retry_delay: Annotated[int, typer.Option("--retry-delay", min=0)] = 30,
    min_records: Annotated[int, typer.Option("--min-records", min=1)] = 8,
    max_records: Annotated[int, typer.Option("--max-records", min=1)] = 12,
    max_tokens: Annotated[int, typer.Option("--max-tokens", help="Use 0 to omit max_tokens from provider payload.")] = 0,
    json_object: Annotated[bool, typer.Option("--json-object/--no-json-object", help="Request OpenAI-compatible JSON object response_format when supported.")] = False,
    limit: Annotated[int, typer.Option("--limit", min=0)] = 0,
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    chunks_path = out / "chunks.jsonl"
    chunks = make_chunks(
        input_path.read_text(encoding="utf-8"),
        document_id=chapter_id,
        source_path=str(input_path),
        target_chars=target_chars,
        max_chars=max_chars,
        overlap_before_sentences=overlap_before_sentences,
        overlap_after_sentences=overlap_after_sentences,
    )
    write_chunks_jsonl(chunks, chunks_path)
    config = BatchConfig(
        chunks_path=chunks_path,
        out_dir=out,
        book=book,
        chapter=chapter,
        chapter_id=chapter_id,
        persona_id=persona_id,
        url=url,
        model=model,
        concurrency=concurrency,
        timeout=timeout,
        response_start_timeout=response_start_timeout,
        stream_idle_timeout=stream_idle_timeout,
        retry_delay=retry_delay,
        min_records=min_records,
        max_records=max_records,
        max_tokens=max_tokens,
        json_object=json_object,
        limit=limit,
        force=force,
    )
    raise typer.Exit(asyncio.run(run_batch(config)))


@app.command("rebuild-aggregate")
def rebuild_aggregate_command(
    chunks: Annotated[Path, typer.Option("--chunks", exists=True, readable=True)],
    out: Annotated[Path, typer.Option("--out")],
) -> None:
    aggregate = write_aggregate(out, load_chunks(chunks), collect_existing_results(out))
    typer.echo(json.dumps(aggregate, indent=2, ensure_ascii=False))


@app.command("merge-accepted")
def merge_accepted_command(
    fact_root: Annotated[Path, typer.Argument(exists=True, file_okay=False, readable=True)],
    out: Annotated[Path, typer.Option("--out", help="Output merged accepted records JSONL path.")],
) -> None:
    records, defects = merge_accepted_records(fact_root)
    if records:
        write_chunk_dicts_jsonl(records, out)
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("", encoding="utf-8")
    report = {
        "schema_version": "fact-extractor-merged-accepted.v1",
        "fact_root": str(fact_root),
        "out": str(out),
        "record_count": len(records),
        "defects": defects,
        "accepted": not defects and bool(records),
    }
    typer.echo(json.dumps(report, indent=2, ensure_ascii=False))
    if defects:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
