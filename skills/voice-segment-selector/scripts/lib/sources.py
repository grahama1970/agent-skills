"""Resolve prepare inputs from paths, URLs, and list files."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse


YOUTUBE_RE = re.compile(
    r"^(https?://)?(www\.)?(youtube\.com/watch\?.*v=|youtu\.be/|youtube\.com/shorts/)[\w-]+",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SourceInput:
    value: str
    start_sec: float | None = None
    end_sec: float | None = None
    label: str | None = None

    @property
    def is_youtube(self) -> bool:
        return is_youtube_url(self.value)


def is_youtube_url(value: str) -> bool:
    value = value.strip()
    if not value:
        return False
    if YOUTUBE_RE.match(value):
        return True
    parsed = urlparse(value)
    if parsed.netloc.endswith("youtube.com") and parsed.path == "/watch":
        return bool(parse_qs(parsed.query).get("v"))
    if parsed.netloc in {"youtu.be", "www.youtu.be"} and parsed.path.strip("/"):
        return True
    return False


def youtube_video_id(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.netloc in {"youtu.be", "www.youtu.be"}:
        return parsed.path.strip("/").split("/")[0]
    if "youtube.com" in parsed.netloc:
        if parsed.path.startswith("/shorts/"):
            return parsed.path.split("/")[2]
        query = parse_qs(parsed.query)
        video_id = query.get("v", [None])[0]
        if video_id:
            return video_id
    raise ValueError(f"Could not parse YouTube video id from: {value}")


def _coerce_source_row(raw: object, line_no: int) -> SourceInput:
    if isinstance(raw, str):
        value = raw.strip()
        if not value or value.startswith("#"):
            raise ValueError(f"Empty source on line {line_no}")
        return SourceInput(value=value)
    if isinstance(raw, dict):
        value = str(raw.get("input") or raw.get("url") or raw.get("path") or "").strip()
        if not value:
            raise ValueError(f"Missing input/url/path on line {line_no}")
        start = raw.get("start_sec")
        end = raw.get("end_sec")
        label = raw.get("label")
        return SourceInput(
            value=value,
            start_sec=float(start) if start is not None else None,
            end_sec=float(end) if end is not None else None,
            label=str(label).strip() if label else None,
        )
    raise ValueError(f"Invalid source entry on line {line_no}: {raw!r}")


def load_sources_from_file(path: Path) -> list[SourceInput]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Inputs file is empty: {path}")

    if path.suffix.lower() == ".json":
        payload = json.loads(text)
        if isinstance(payload, list):
            return [_coerce_source_row(row, idx + 1) for idx, row in enumerate(payload)]
        raise ValueError("JSON inputs file must be an array of strings or objects")

    sources: list[SourceInput] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("{"):
            sources.append(_coerce_source_row(json.loads(stripped), line_no))
        else:
            sources.append(SourceInput(value=stripped))
    if not sources:
        raise ValueError(f"No sources found in {path}")
    return sources


def load_sources(
    *,
    inputs: list[Path | str] | None = None,
    inputs_file: Path | None = None,
) -> list[SourceInput]:
    sources: list[SourceInput] = []
    if inputs_file is not None:
        sources.extend(load_sources_from_file(inputs_file))
    if inputs:
        for item in inputs:
            value = str(item).strip()
            if not value:
                continue
            sources.append(SourceInput(value=value))
    if not sources:
        raise ValueError("Provide at least one --input or --inputs-file")
    return sources


def download_youtube_source(source: SourceInput, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    video_id = youtube_video_id(source.value)
    output_template = str(dest_dir / f"{video_id}.%(ext)s")
    completed = dest_dir / f"{video_id}.mp3"
    if completed.exists():
        return completed
    cmd = [
        "yt-dlp",
        "-x",
        "--audio-format",
        "mp3",
        "-o",
        output_template,
        source.value.strip(),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if completed.exists():
        return completed
    matches = sorted(dest_dir.glob(f"{video_id}.*"))
    if not matches:
        raise RuntimeError(f"yt-dlp did not produce output for {source.value}")
    return matches[0]


def resolve_source_path(
    source: SourceInput,
    *,
    job_dir: Path,
    source_index: int,
    download_youtube: bool,
) -> tuple[Path, str]:
    if source.is_youtube:
        if not download_youtube:
            raise ValueError(
                f"YouTube URL requires download enabled: {source.value} "
                "(omit --no-download-youtube or pre-download with /ingest-youtube)"
            )
        video_id = youtube_video_id(source.value)
        dest = job_dir / "sources" / f"{source_index:03d}_{video_id}"
        path = download_youtube_source(source, dest)
        label = source.label or f"youtube:{video_id}"
        return path, label

    path = Path(source.value).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Input not found: {path}")
    label = source.label or path.name
    return path.resolve(), label
