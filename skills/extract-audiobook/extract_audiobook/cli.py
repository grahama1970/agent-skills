from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal

import typer


app = typer.Typer(no_args_is_help=True)
OutputMode = Literal["chapter-text", "transcript-jsonl", "both"]


@dataclass(frozen=True)
class AudioChapter:
    index: int
    chapter_id: str
    book: str
    book_id: str
    title: str
    start_time: float
    end_time: float
    duration: float
    audio_path: str
    text_path: str
    transcript_jsonl_path: str


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def run_json(cmd: list[str]) -> dict[str, Any]:
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"command failed {cmd!r}: {result.stderr.strip()}")
    return json.loads(result.stdout)


def run_checked(cmd: list[str]) -> None:
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"command failed {cmd!r}: {result.stderr.strip()[:1000]}")


def probe_audio(audio: Path) -> dict[str, Any]:
    data = run_json(["ffprobe", "-v", "error", "-print_format", "json", "-show_chapters", str(audio)])
    chapters = data.get("chapters") or []
    if not isinstance(chapters, list) or not chapters:
        raise RuntimeError(f"no embedded chapters found in {audio}")
    return data


def chapter_title(raw: dict[str, Any], index: int) -> str:
    title = ((raw.get("tags") or {}).get("title") or "").strip()
    return title or f"Chapter {index:02d}"


def build_chapter_plan(
    audio: Path,
    out: Path,
    book: str,
    book_id: str | dict[str, Any],
    ffprobe_data: dict[str, Any] | None = None,
) -> list[AudioChapter]:
    if ffprobe_data is None:
        ffprobe_data = dict(book_id)
        book_id = book
    chapters: list[AudioChapter] = []
    for one_based, raw in enumerate(ffprobe_data.get("chapters") or [], start=1):
        start = float(raw.get("start_time") or 0)
        end = float(raw.get("end_time") or 0)
        if end <= start:
            raise RuntimeError(f"bad chapter timing for chapter {one_based}: start={start} end={end}")
        chapter_id = f"{book_id}_ch{one_based:02d}"
        chapters.append(
            AudioChapter(
                index=one_based,
                chapter_id=chapter_id,
                book=book,
                book_id=book_id,
                title=chapter_title(raw, one_based),
                start_time=start,
                end_time=end,
                duration=end - start,
                audio_path=str(out / "audio_chapters" / f"chapter_{one_based:02d}.m4a"),
                text_path=str(out / "cleaned_chapters" / f"chapter_{one_based:02d}.txt"),
                transcript_jsonl_path=str(out / "transcript_jsonl" / f"chapter_{one_based:02d}.jsonl"),
            )
        )
    return chapters


def write_chapters_jsonl(chapters: list[AudioChapter], out: Path) -> None:
    path = out / "chapters.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for chapter in chapters:
            row = asdict(chapter)
            row.update(
                {
                    "_key": chapter.chapter_id,
                    "type": "book_chapter_record",
                    "record_id": chapter.chapter_id,
                    "record_type": "book_chapter",
                    "memory_collection": "book_chapters",
                    "title": chapter.title,
                    "text": f"{chapter.book} {chapter.title}",
                    "retrieval_text": f"{chapter.book} {chapter.title}",
                    "validation_status": "accepted",
                    "canon_status": "source_grounded",
                    "upsert_eligible": True,
                    "tags": [
                        "book_chapter",
                        f"book:{chapter.book_id}",
                        f"chapter:{chapter.chapter_id}",
                    ],
                }
            )
            f.write(json.dumps(row, ensure_ascii=False))
            f.write("\n")


def sentence_or_paragraph_boundaries(text: str) -> list[int]:
    boundaries = {0, len(text)}
    for match in re.finditer(r"\n\s*\n", text):
        boundaries.add(match.end())
    for match in re.finditer(r"""(?<=[.!?])(?:["'”’)\]]*)\s+(?=["'“‘(\[]*[A-Z0-9])""", text):
        boundaries.add(match.end())
    return sorted(boundaries)


def nearest_boundary(boundaries: list[int], target: int, floor: int, ceiling: int) -> int:
    candidates = [pos for pos in boundaries if floor < pos < ceiling]
    if not candidates:
        return max(floor, min(target, ceiling))
    return min(candidates, key=lambda pos: (abs(pos - target), pos))


def split_text_by_chapter_durations(text: str, chapters: list[AudioChapter]) -> list[str]:
    if not chapters:
        return []
    total_duration = sum(chapter.duration for chapter in chapters)
    if total_duration <= 0:
        raise RuntimeError("cannot split transcript by chapter durations without positive total duration")

    boundaries = sentence_or_paragraph_boundaries(text)
    parts: list[str] = []
    start = 0
    elapsed = 0.0
    for chapter in chapters[:-1]:
        elapsed += chapter.duration
        target = round(len(text) * (elapsed / total_duration))
        remaining = len(chapters) - len(parts) - 1
        min_end = min(len(text), start + 1)
        max_end = max(min_end, len(text) - remaining)
        end = nearest_boundary(boundaries, target, min_end, max_end)
        parts.append(text[start:end].strip() + "\n")
        start = end
    parts.append(text[start:].strip() + "\n")
    return parts


def write_estimated_chapters_jsonl(
    chapters: list[AudioChapter],
    chapter_texts: list[str],
    out: Path,
    source_transcript: Path,
) -> None:
    path = out / "chapters.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for chapter, text in zip(chapters, chapter_texts, strict=True):
            row = asdict(chapter)
            row.update(
                {
                    "_key": chapter.chapter_id,
                    "type": "book_chapter_record",
                    "record_id": chapter.chapter_id,
                    "record_type": "book_chapter",
                    "memory_collection": "book_chapters",
                    "title": chapter.title,
                    "text": text,
                    "retrieval_text": f"{chapter.book} {chapter.title}\n\n{text}",
                    "validation_status": "accepted",
                    "canon_status": "source_grounded",
                    "upsert_eligible": True,
                    "source_transcript_path": str(source_transcript),
                    "source_grounding_kind": "flat_transcript_duration_split",
                    "chapter_split_confidence": "estimated",
                    "warnings": [
                        "chapter_text_split_estimated_from_flat_transcript_and_audio_durations",
                        "not_a_fresh_chapter_audio_transcription",
                    ],
                    "text_sha256": sha256_text(text),
                    "text_chars": len(text),
                    "tags": [
                        "book_chapter",
                        f"book:{chapter.book_id}",
                        f"chapter:{chapter.chapter_id}",
                        "chapter_split:estimated",
                    ],
                }
            )
            f.write(json.dumps(row, ensure_ascii=False))
            f.write("\n")


def audio_chapter_from_row(row: dict[str, Any], book: str, book_id: str) -> AudioChapter:
    return AudioChapter(
        index=int(row["index"]),
        chapter_id=str(row["chapter_id"]),
        book=str(row.get("book") or book),
        book_id=str(row.get("book_id") or book_id),
        title=str(row["title"]),
        start_time=float(row["start_time"]),
        end_time=float(row["end_time"]),
        duration=float(row["duration"]),
        audio_path=str(row["audio_path"]),
        text_path=str(row["text_path"]),
        transcript_jsonl_path=str(row["transcript_jsonl_path"]),
    )


def valid_audio(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def valid_text(path: Path) -> bool:
    return path.exists() and bool(path.read_text(encoding="utf-8", errors="replace").strip())


def valid_jsonl(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        return any(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    except Exception:
        return False


def split_one(audio: Path, chapter: AudioChapter, force: bool, limit_seconds: float) -> str:
    out_path = Path(chapter.audio_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if valid_audio(out_path) and not force:
        return "skipped_existing"
    duration = min(chapter.duration, limit_seconds) if limit_seconds > 0 else chapter.duration
    run_checked(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{chapter.start_time:.3f}",
            "-t",
            f"{duration:.3f}",
            "-i",
            str(audio),
            "-vn",
            "-c:a",
            "copy",
            str(out_path),
            "-y",
        ]
    )
    return "created"


def transcribe_one(
    chapter: AudioChapter,
    book: str,
    mode: OutputMode,
    model_name: str,
    force: bool,
    device: str,
    compute_type: str,
) -> str:
    text_path = Path(chapter.text_path)
    jsonl_path = Path(chapter.transcript_jsonl_path)
    wants_text = mode in {"chapter-text", "both"}
    wants_jsonl = mode in {"transcript-jsonl", "both"}
    if (
        (not wants_text or valid_text(text_path))
        and (not wants_jsonl or valid_jsonl(jsonl_path))
        and not force
    ):
        return "skipped_existing"

    try:
        from faster_whisper import WhisperModel
    except Exception as exc:
        raise RuntimeError("faster_whisper is required for transcription; install or use split/probe only") from exc

    text_path.parent.mkdir(parents=True, exist_ok=True)
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    model = WhisperModel(model_name, device=device, compute_type=compute_type)
    segments, info = model.transcribe(chapter.audio_path, language="en", beam_size=1, vad_filter=True)
    texts: list[str] = []
    jsonl_rows: list[dict[str, Any]] = []
    for segment_index, segment in enumerate(segments, start=1):
        text = segment.text.strip()
        if not text:
            continue
        texts.append(text)
        jsonl_rows.append(
            {
                "schema_version": "extract-audiobook-transcript-segment.v1",
                "book": book,
                "chapter": chapter.title,
                "chapter_id": chapter.chapter_id,
                "chapter_index": chapter.index,
                "segment_index": segment_index,
                "start_s": float(segment.start),
                "end_s": float(segment.end),
                "audio_start_s": chapter.start_time + float(segment.start),
                "audio_end_s": chapter.start_time + float(segment.end),
                "text": text,
                "language": getattr(info, "language", None),
            }
        )

    if wants_text:
        text_path.write_text("\n".join(texts).strip() + "\n", encoding="utf-8")
    if wants_jsonl:
        with jsonl_path.open("w", encoding="utf-8") as f:
            for row in jsonl_rows:
                f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
                f.write("\n")
    return "created"


def write_manifest(
    out: Path,
    audio: Path,
    book: str,
    book_id: str,
    mode: str,
    chapters: list[AudioChapter],
    actions: list[dict[str, Any]],
) -> dict[str, Any]:
    manifest = {
        "schema_version": "extract-audiobook-manifest.v1",
        "created_at": now(),
        "book": book,
        "book_id": book_id,
        "audio_path": str(audio),
        "audio_sha256": sha256_file(audio),
        "mode": mode,
        "chapter_count": len(chapters),
        "chapters": [asdict(chapter) for chapter in chapters],
        "actions": actions,
        "memory_writes_performed": False,
        "forbidden_writes": ["persona_memory", "lessons", "arangodb"],
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def prepare(audio: Path, out: Path, book: str, book_id: str) -> tuple[dict[str, Any], list[AudioChapter]]:
    out.mkdir(parents=True, exist_ok=True)
    ffprobe_data = probe_audio(audio)
    (out / "ffprobe_chapters.json").write_text(json.dumps(ffprobe_data, indent=2), encoding="utf-8")
    chapters = build_chapter_plan(audio, out, book, book_id, ffprobe_data)
    write_chapters_jsonl(chapters, out)
    return ffprobe_data, chapters


def write_transcript_segment(chapter: AudioChapter, text: str) -> None:
    path = Path(chapter.transcript_jsonl_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "schema_version": "extract-audiobook-transcript-segment.v1",
        "book": chapter.book,
        "chapter": chapter.title,
        "chapter_id": chapter.chapter_id,
        "chapter_index": chapter.index,
        "segment_index": 1,
        "start_s": 0.0,
        "end_s": chapter.duration,
        "audio_start_s": chapter.start_time,
        "audio_end_s": chapter.end_time,
        "text": text.strip(),
        "language": "en",
        "source_grounding_kind": "flat_transcript_duration_split",
    }
    path.write_text(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


@app.command()
def doctor(json_output: Annotated[bool, typer.Option("--json")] = False) -> None:
    report = {
        "schema_version": "extract-audiobook-doctor.v1",
        "ffprobe": bool(shutil.which("ffprobe")),
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "faster_whisper": None,
    }
    try:
        import faster_whisper  # noqa: F401

        report["faster_whisper"] = True
    except Exception:
        report["faster_whisper"] = False
    report["ok"] = bool(report["ffprobe"] and report["ffmpeg"])
    if json_output:
        typer.echo(json.dumps(report, indent=2))
    else:
        typer.echo("extract-audiobook doctor ok" if report["ok"] else json.dumps(report, indent=2))


@app.command()
def probe(
    audio: Annotated[Path, typer.Argument(exists=True, readable=True)],
    out: Annotated[Path | None, typer.Option("--out")] = None,
) -> None:
    data = probe_audio(audio)
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        (out / "ffprobe_chapters.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    typer.echo(json.dumps({"schema_version": "extract-audiobook-probe.v1", "audio": str(audio), "chapter_count": len(data.get("chapters") or []), "chapters": data.get("chapters")}, indent=2))


@app.command()
def split(
    audio: Annotated[Path, typer.Argument(exists=True, readable=True)],
    out: Annotated[Path, typer.Option("--out")],
    book: Annotated[str, typer.Option("--book")],
    book_id: Annotated[str, typer.Option("--book-id")],
    limit: Annotated[int, typer.Option("--limit", min=0)] = 0,
    limit_seconds: Annotated[float, typer.Option("--limit-seconds", min=0)] = 0,
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    _data, chapters = prepare(audio, out, book, book_id)
    selected = chapters[:limit] if limit else chapters
    actions = [
        {"chapter_id": chapter.chapter_id, "split": split_one(audio, chapter, force, limit_seconds)}
        for chapter in selected
    ]
    manifest = write_manifest(out, audio, book, book_id, "split", chapters, actions)
    typer.echo(json.dumps({**manifest, "chapters": manifest["chapters"][: len(selected)]}, indent=2, ensure_ascii=False))


@app.command()
def transcribe(
    out: Annotated[Path, typer.Option("--out", exists=True, readable=True)],
    book: Annotated[str, typer.Option("--book")],
    book_id: Annotated[str, typer.Option("--book-id")],
    mode: Annotated[OutputMode, typer.Option("--mode")] = "both",
    model: Annotated[str, typer.Option("--model")] = "tiny",
    device: Annotated[str, typer.Option("--device")] = "cpu",
    compute_type: Annotated[str, typer.Option("--compute-type")] = "int8",
    limit: Annotated[int, typer.Option("--limit", min=0)] = 0,
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    chapters = [
        audio_chapter_from_row(json.loads(line), book, book_id)
        for line in (out / "chapters.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    selected = chapters[:limit] if limit else chapters
    actions = [
        {
            "chapter_id": chapter.chapter_id,
            "transcribe": transcribe_one(chapter, book, mode, model, force, device, compute_type),
        }
        for chapter in selected
    ]
    manifest = write_manifest(out, Path(selected[0].audio_path if selected else ""), book, book_id, mode, chapters, actions)
    typer.echo(json.dumps({**manifest, "chapters": manifest["chapters"][: len(selected)]}, indent=2, ensure_ascii=False))


@app.command()
def extract(
    audio: Annotated[Path, typer.Argument(exists=True, readable=True)],
    out: Annotated[Path, typer.Option("--out")],
    book: Annotated[str, typer.Option("--book")],
    book_id: Annotated[str, typer.Option("--book-id")],
    mode: Annotated[OutputMode, typer.Option("--mode")] = "both",
    model: Annotated[str, typer.Option("--model")] = "tiny",
    device: Annotated[str, typer.Option("--device")] = "cpu",
    compute_type: Annotated[str, typer.Option("--compute-type")] = "int8",
    limit: Annotated[int, typer.Option("--limit", min=0)] = 0,
    limit_seconds: Annotated[float, typer.Option("--limit-seconds", min=0)] = 0,
    split_only: Annotated[bool, typer.Option("--split-only")] = False,
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    _data, chapters = prepare(audio, out, book, book_id)
    selected = chapters[:limit] if limit else chapters
    actions: list[dict[str, Any]] = []
    for chapter in selected:
        action: dict[str, Any] = {"chapter_id": chapter.chapter_id}
        action["split"] = split_one(audio, chapter, force, limit_seconds)
        if not split_only:
            action["transcribe"] = transcribe_one(chapter, book, mode, model, force, device, compute_type)
        actions.append(action)
    manifest = write_manifest(out, audio, book, book_id, mode if not split_only else "split", chapters, actions)
    typer.echo(json.dumps({**manifest, "chapters": manifest["chapters"][: len(selected)]}, indent=2, ensure_ascii=False))


@app.command("normalize-transcript")
def normalize_transcript(
    audio: Annotated[Path, typer.Argument(exists=True, readable=True)],
    transcript: Annotated[Path, typer.Option("--transcript", exists=True, readable=True)],
    out: Annotated[Path, typer.Option("--out")],
    book: Annotated[str, typer.Option("--book")],
    book_id: Annotated[str, typer.Option("--book-id")],
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    """Create chapter artifacts from an existing flat transcript without retranscribing audio."""
    if force and out.exists():
        shutil.rmtree(out)
    ffprobe_data, chapters = prepare(audio, out, book, book_id)
    text = normalize_newlines(transcript.read_text(encoding="utf-8", errors="replace")).strip()
    chapter_texts = split_text_by_chapter_durations(text, chapters)
    for chapter, chapter_text in zip(chapters, chapter_texts, strict=True):
        text_path = Path(chapter.text_path)
        text_path.parent.mkdir(parents=True, exist_ok=True)
        text_path.write_text(chapter_text, encoding="utf-8")
        write_transcript_segment(chapter, chapter_text)
    write_estimated_chapters_jsonl(chapters, chapter_texts, out, transcript)
    actions = [
        {
            "chapter_id": chapter.chapter_id,
            "normalize_transcript": "created",
            "text_path": chapter.text_path,
            "transcript_jsonl_path": chapter.transcript_jsonl_path,
            "source_grounding_kind": "flat_transcript_duration_split",
        }
        for chapter in chapters
    ]
    manifest = write_manifest(out, audio, book, book_id, "normalize-transcript", chapters, actions)
    manifest.update(
        {
            "source_transcript_path": str(transcript),
            "source_transcript_sha256": sha256_file(transcript),
            "source_transcript_chars": len(text),
            "chapter_split_confidence": "estimated",
            "warnings": [
                "flat_transcript_had_insufficient_chapter_markers; chapter text split by embedded audio duration proportions",
                "not_a_fresh_chapter_audio_transcription",
            ],
        }
    )
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    typer.echo(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    app()
