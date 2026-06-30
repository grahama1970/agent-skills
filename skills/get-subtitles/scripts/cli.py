"""Module support for the get-subtitles skill."""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse
from typing import Any

import httpx
import typer


app = typer.Typer(help="Verify and recover movie subtitles through Bazarr.")

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
SKILLS_DIR = SKILL_DIR.parent
BRAVE_RUN = SKILLS_DIR / "brave-search" / "run.sh"
INGEST_MOVIE_RUN = SKILLS_DIR / "ingest-movie" / "run.sh"
VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".m4v", ".mov", ".webm"}
SUBTITLE_EXTENSIONS = [".srt", ".vtt", ".ass", ".ssa"]
PRIMARY_SUBTITLE_FORMAT = ".srt"
EXTERNAL_OUT_DIR = SKILL_DIR / "out" / "external-subtitles"
ORPHEUS_EMOTIONS = ["laugh", "chuckle", "sigh", "cough", "sniffle", "groan", "yawn", "gasp"]
EMOTION_MARKERS = {
    "laugh": ["laugh", "laughs", "laughing", "laughter"],
    "chuckle": ["chuckle", "chuckles", "chuckling"],
    "sigh": ["sigh", "sighs", "sighing"],
    "cough": ["cough", "coughs", "coughing"],
    "sniffle": ["sniffle", "sniffles", "sniffling", "sniff"],
    "groan": ["groan", "groans", "groaning"],
    "yawn": ["yawn", "yawns", "yawning"],
    "gasp": ["gasp", "gasps", "gasping"],
}
AMBIENT_REJECT_MARKERS = {"people chattering", "chattering", "chatting", "murmur", "crowd", "background", "music", "song", "noise"}
ACTION_CUE_CONNECTORS = {"continues", "continue", "starts", "start", "begins", "begin", "keeps", "keep", "is", "are", "still"}
SRT_TIMECODE_RE = re.compile(
    r"(?P<sh>\d{2}):(?P<sm>\d{2}):(?P<ss>\d{2}),(?P<sms>\d{3})\s*-->\s*"
    r"(?P<eh>\d{2}):(?P<em>\d{2}):(?P<es>\d{2}),(?P<ems>\d{3})"
)
VTT_TIMECODE_RE = re.compile(
    r"(?P<sh>\d{2}):(?P<sm>\d{2}):(?P<ss>\d{2})[,.](?P<sms>\d{3})\s*-->\s*"
    r"(?P<eh>\d{2}):(?P<em>\d{2}):(?P<es>\d{2})[,.](?P<ems>\d{3})"
)
ASS_DIALOGUE_RE = re.compile(r"^Dialogue:\s*(?P<body>.+)$", re.I)
VTT_SPEAKER_RE = re.compile(r"<v\s+([^>]+)>", re.I)
INLINE_SPEAKER_RE = re.compile(r"^\s*([A-Z][A-Za-z0-9 ._'’-]{1,40})\s*:\s+\S+")
YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
METADATA_LINE_RE = re.compile(r"^\s*(title|movie|film|year|actor|actors|cast|imdb|tmdb|source|release)\s*[:=-]\s*(.+)$", re.I)
SUBTITLECAT_EN_HREF_RE = re.compile(r'''href=["'](?P<href>[^"']+-en\.srt)["']''', re.I)
HTML_TAG_RE = re.compile(r"<[^>]+>")


def subtitle_metadata(subtitle_path: Path) -> dict[str, Any]:
    text = subtitle_path.read_text(encoding="utf-8", errors="replace")
    lines = [line.strip("\ufeff ").strip() for line in text.splitlines()[:80]]
    metadata: dict[str, Any] = {
        "subtitle_filename": subtitle_path.name,
        "subtitle_parent": str(subtitle_path.parent),
        "format": subtitle_path.suffix.lower().lstrip("."),
    }
    year_match = YEAR_RE.search(str(subtitle_path))
    if year_match:
        metadata["year_from_path"] = int(year_match.group(1))
    path_name = subtitle_path.parent.name or subtitle_path.stem
    cleaned_title = YEAR_RE.sub("", path_name)
    cleaned_title = re.sub(r"[._]+", " ", cleaned_title)
    cleaned_title = re.sub(r"\s+", " ", cleaned_title).strip(" -()[]")
    if cleaned_title:
        metadata["title_from_path"] = cleaned_title
    inline_fields: dict[str, list[str]] = {}
    vtt_speakers: set[str] = set()
    inline_speakers: set[str] = set()
    ass_speakers: set[str] = set()
    ass_format_fields: list[str] = []
    for line in lines:
        if not line or line.isdigit() or "-->" in line:
            continue
        match = METADATA_LINE_RE.match(line)
        if match:
            key = match.group(1).lower()
            inline_fields.setdefault(key, []).append(match.group(2).strip())
        for speaker_match in VTT_SPEAKER_RE.finditer(line):
            vtt_speakers.add(speaker_match.group(1).strip())
        inline_speaker_match = INLINE_SPEAKER_RE.match(line)
        if inline_speaker_match:
            inline_speakers.add(inline_speaker_match.group(1).strip())
        if line.lower().startswith("format:"):
            ass_format_fields = [part.strip().lower() for part in line.split(":", 1)[1].split(",")]
        dialogue_match = ASS_DIALOGUE_RE.match(line)
        if dialogue_match and ass_format_fields:
            values = [part.strip() for part in dialogue_match.group("body").split(",", maxsplit=max(0, len(ass_format_fields) - 1))]
            field_map = dict(zip(ass_format_fields, values))
            name = field_map.get("name")
            if name and name.lower() not in {"default", "*default", "unknown"}:
                ass_speakers.add(name)
    if inline_fields:
        metadata["inline_metadata"] = inline_fields
    if vtt_speakers:
        metadata["vtt_speakers"] = sorted(vtt_speakers)
    if ass_speakers:
        metadata["ass_speakers"] = sorted(ass_speakers)
    if inline_speakers:
        metadata["inline_speakers"] = sorted(inline_speakers)
    if ass_speakers:
        metadata["speaker_metadata_status"] = "structured_ass_name_field"
    elif vtt_speakers:
        metadata["speaker_metadata_status"] = "structured_vtt_voice_tags"
    elif inline_speakers:
        metadata["speaker_metadata_status"] = "inline_text_labels"
    else:
        metadata["speaker_metadata_status"] = "not_present"
    return metadata


def safe_slug(value: str, max_length: int = 96) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    slug = re.sub(r"-+", "-", slug).strip("-._")
    return (slug or "subtitle")[:max_length]


def fetch_text_url(url: str, timeout: float = 30.0) -> tuple[int, str, str]:
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml,text/plain;q=0.9,*/*;q=0.8",
    }
    with httpx.Client(timeout=httpx.Timeout(timeout, connect=5.0), follow_redirects=True, headers=headers) as client:
        response = client.get(url)
    return response.status_code, str(response.url), response.text


def html_to_text(html: str) -> str:
    text = re.sub(r"(?i)<br\s*/?>", "\n", html)
    text = re.sub(r"(?i)</p\s*>", "\n", text)
    text = HTML_TAG_RE.sub("", text)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&#x27;", "'")
        .replace("&#8217;", "'")
        .replace("&#8230;", "...")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def detect_subtitle_format_from_url(url: str, content_type: str | None = None) -> str:
    suffix = Path(urlparse(url).path).suffix.lower().lstrip(".")
    if suffix in {"srt", "vtt", "ass", "ssa"}:
        return suffix
    if content_type and "html" in content_type.lower():
        return "txt"
    return suffix or "txt"


def external_artifact_path(candidate: dict[str, Any], url: str, fmt: str) -> Path:
    title = str(candidate.get("title") or "unknown-title")
    year = str(candidate.get("year") or "unknown-year")
    host = urlparse(url).netloc or "external"
    name = f"{safe_slug(title)}-{safe_slug(year)}-{safe_slug(host)}.{fmt}"
    return EXTERNAL_OUT_DIR / name


def infer_title_year_from_subtitle_url(url: str) -> dict[str, Any]:
    stem = Path(urlparse(url).path).stem
    stem = re.sub(r"(?i)-en$", "", stem)
    year_match = YEAR_RE.search(stem)
    if not year_match:
        return {}
    year = int(year_match.group(1))
    title_part = stem[:year_match.start()]
    title_part = re.sub(r"[._-]+", " ", title_part)
    title_part = re.sub(r"\s+", " ", title_part).strip(" -()[]")
    if not title_part:
        return {"year": year}
    return {"title": title_part, "year": year}


def subtitlecat_english_srt_url(page_url: str, html: str) -> str | None:
    for match in SUBTITLECAT_EN_HREF_RE.finditer(html):
        href = match.group("href")
        if href.lower().endswith("-en.srt"):
            return urljoin(page_url, href)
    return None


def fetch_external_subtitle_artifact(candidate: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    url = str(evidence.get("url") or "")
    if not url:
        return {
            "status": "not_fetched",
            "reason": "missing_url",
            "candidate": candidate,
            "evidence": evidence,
        }
    try:
        status_code, final_url, body = fetch_text_url(url)
    except Exception as exc:
        return {
            "status": "not_fetched",
            "reason": f"fetch_failed:{type(exc).__name__}",
            "candidate": candidate,
            "url": url,
            "safe_default": "do_not_recommend_movie_download",
        }
    if status_code >= 400:
        return {
            "status": "not_fetched",
            "reason": f"http_{status_code}",
            "candidate": candidate,
            "url": url,
            "safe_default": "do_not_recommend_movie_download",
        }

    download_url: str | None = None
    if "subtitlecat.com" in urlparse(final_url).netloc.lower() and not final_url.lower().endswith(".srt"):
        download_url = subtitlecat_english_srt_url(final_url, body)
    if download_url:
        try:
            srt_status, srt_final_url, srt_body = fetch_text_url(download_url)
        except Exception as exc:
            return {
                "status": "not_fetched",
                "reason": f"subtitle_download_failed:{type(exc).__name__}",
                "candidate": candidate,
                "url": url,
                "download_url": download_url,
                "safe_default": "do_not_recommend_movie_download",
            }
        if srt_status >= 400:
            return {
                "status": "not_fetched",
                "reason": f"subtitle_download_http_{srt_status}",
                "candidate": candidate,
                "url": url,
                "download_url": download_url,
                "safe_default": "do_not_recommend_movie_download",
            }
        final_url = srt_final_url
        body = srt_body
        fmt = detect_subtitle_format_from_url(final_url)
    else:
        fmt = detect_subtitle_format_from_url(final_url, "text/html")
        if fmt == "txt":
            body = html_to_text(body)

    inferred = infer_title_year_from_subtitle_url(final_url)
    output_candidate = dict(candidate)
    if inferred.get("title") and (
        not output_candidate.get("title")
        or len(str(inferred["title"])) > len(str(output_candidate.get("title")))
    ):
        output_candidate["title"] = inferred["title"]
        output_candidate["title_source"] = "subtitle_url"
    if inferred.get("year") and not output_candidate.get("year"):
        output_candidate["year"] = inferred["year"]

    if not body.strip():
        return {
            "status": "not_fetched",
            "reason": "empty_body",
            "candidate": candidate,
            "url": url,
            "safe_default": "do_not_recommend_movie_download",
        }
    EXTERNAL_OUT_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = external_artifact_path(output_candidate, final_url, fmt)
    artifact_path.write_text(body, encoding="utf-8", errors="replace")
    has_timecodes = bool(SRT_TIMECODE_RE.search(body) or VTT_TIMECODE_RE.search(body) or ASS_DIALOGUE_RE.search(body))
    return {
        "status": "fetched",
        "candidate": output_candidate,
        "source_url": url,
        "final_url": final_url,
        "download_url": download_url,
        "artifact_path": str(artifact_path),
        "format": fmt,
        "byte_count": artifact_path.stat().st_size,
        "has_timecodes": has_timecodes,
        "evidence": evidence,
        "safe_default": "scan_before_recommendation",
    }


def scan_external_artifact(fetch_receipt: dict[str, Any], emotions: list[str]) -> dict[str, Any]:
    path_value = fetch_receipt.get("artifact_path")
    if fetch_receipt.get("status") != "fetched" or not path_value:
        return {
            "status": "not_scanned",
            "fetch": fetch_receipt,
            "reason": "not_fetched",
            "safe_default": "do_not_recommend_movie_download",
        }
    path = Path(str(path_value))
    if not path.exists() or path.stat().st_size == 0:
        return {
            "status": "not_scanned",
            "fetch": fetch_receipt,
            "reason": "artifact_missing_or_empty",
            "safe_default": "do_not_recommend_movie_download",
        }
    scan = scan_srt_for_emotions(path, emotions)
    return {
        "status": "scanned",
        "fetch": fetch_receipt,
        "scan": scan,
        "has_timecoded_orpheus_hits": bool(fetch_receipt.get("has_timecodes") and scan.get("matches")),
        "safe_default": "recommendation_allowed_only_for_timecoded_hits",
    }


def load_dotenv_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


for env_path in (SKILL_DIR / ".env", SKILLS_DIR.parent / ".env"):
    load_dotenv_file(env_path)


def emit(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True))
        return
    for key, value in data.items():
        print(f"{key}: {value}")


def bazarr_url() -> str:
    return os.environ.get("BAZARR_URL", "http://localhost:6767").rstrip("/")


def bazarr_headers() -> dict[str, str]:
    key = os.environ.get("BAZARR_API_KEY", "")
    return {"X-API-KEY": key} if key else {}


def radarr_url() -> str:
    return os.environ.get("RADARR_URL", "http://localhost:7878").rstrip("/")


def radarr_headers() -> dict[str, str]:
    key = os.environ.get("RADARR_API_KEY", "")
    return {"X-Api-Key": key} if key else {}


def bazarr_request(
    method: str,
    path: str,
    *,
    params: Any = None,
    json_body: Any = None,
    timeout: float = 10.0,
) -> httpx.Response:
    url = f"{bazarr_url()}/api{path}"
    with httpx.Client(timeout=httpx.Timeout(timeout, connect=2.0)) as client:
        response = client.request(method, url, params=params, json=json_body, headers=bazarr_headers())
        return response


def radarr_request(
    method: str,
    path: str,
    *,
    params: Any = None,
    json_body: Any = None,
    timeout: float = 20.0,
) -> httpx.Response:
    url = f"{radarr_url()}/api/v3{path}"
    with httpx.Client(timeout=httpx.Timeout(timeout, connect=2.0)) as client:
        response = client.request(method, url, params=params, json=json_body, headers=radarr_headers())
        return response


def radarr_quality_profile_id(preferred_name: str = "Orpheus-TTS") -> int | None:
    response = radarr_request("GET", "/qualityprofile", timeout=10.0)
    if response.status_code != 200:
        return None
    profiles = response.json()
    if not isinstance(profiles, list):
        return None
    for profile in profiles:
        if str(profile.get("name", "")).lower() == preferred_name.lower():
            return int(profile["id"])
    for profile in profiles:
        if str(profile.get("name", "")).lower() == "any":
            return int(profile["id"])
    return int(profiles[0]["id"]) if profiles else None


def radarr_root_folder() -> str | None:
    configured = os.environ.get("RADARR_ROOT_FOLDER")
    if configured:
        return configured
    response = radarr_request("GET", "/rootfolder", timeout=10.0)
    if response.status_code != 200:
        return None
    rows = response.json()
    if not isinstance(rows, list):
        return None
    accessible = [row for row in rows if row.get("accessible") and row.get("path")]
    selected = accessible[0] if accessible else (rows[0] if rows else None)
    return str(selected.get("path")) if selected else None


def radarr_lookup_candidate(candidate: dict[str, Any]) -> dict[str, Any] | None:
    title = str(candidate.get("title") or "").strip()
    year = candidate.get("year")
    if not title:
        return None
    term = f"{title} {year}" if year else title
    response = radarr_request("GET", "/movie/lookup", params={"term": term}, timeout=20.0)
    if response.status_code != 200:
        return None
    rows = response.json()
    if not isinstance(rows, list):
        return None
    for row in rows:
        if str(row.get("title", "")).lower() == title.lower() and (not year or int(row.get("year") or 0) == int(year)):
            return row
    return rows[0] if rows else None


def radarr_existing_movie_by_tmdb(tmdb_id: int | None) -> dict[str, Any] | None:
    if not tmdb_id:
        return None
    response = radarr_request("GET", "/movie", params={"tmdbId": tmdb_id}, timeout=10.0)
    if response.status_code != 200:
        return None
    rows = response.json()
    if isinstance(rows, list) and rows:
        return rows[0]
    return None


def radarr_movie_inventory() -> list[dict[str, Any]]:
    response = radarr_request("GET", "/movie", timeout=20.0)
    response.raise_for_status()
    rows = response.json()
    return rows if isinstance(rows, list) else []


def radarr_inventory_matches_for_candidate(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        rows = radarr_movie_inventory()
    except Exception as exc:
        return [{
            "status": "radarr_lookup_failed",
            "reason": type(exc).__name__,
            "candidate": candidate,
        }]
    matches: list[dict[str, Any]] = []
    for row in rows:
        if movie_record_title_matches(row, candidate):
            movie_file = row.get("movieFile") or {}
            matches.append({
                "status": "radarr_inventory_match",
                "candidate": candidate,
                "radarr_id": row.get("id"),
                "title": row.get("title"),
                "year": row.get("year"),
                "tmdb_id": row.get("tmdbId"),
                "imdb_id": row.get("imdbId"),
                "path": movie_file.get("path") or row.get("path"),
                "has_file": bool(row.get("movieFileId") or movie_file),
                "monitored": row.get("monitored"),
            })
    return matches


def radarr_add_metadata_stub(candidate: dict[str, Any]) -> dict[str, Any]:
    lookup = radarr_lookup_candidate(candidate)
    if not lookup:
        return {
            "status": "not_added",
            "reason": "radarr_lookup_no_match",
            "candidate": candidate,
            "safe_default": "do_not_recommend_movie_download",
        }
    existing = radarr_existing_movie_by_tmdb(lookup.get("tmdbId"))
    if existing:
        return {
            "status": "already_in_radarr",
            "candidate": candidate,
            "radarr_id": existing.get("id"),
            "tmdb_id": existing.get("tmdbId"),
            "monitored": existing.get("monitored"),
            "has_file": bool(existing.get("movieFile") or existing.get("movieFileId")),
        }
    profile_id = radarr_quality_profile_id()
    root_folder = radarr_root_folder()
    if not profile_id or not root_folder:
        return {
            "status": "not_added",
            "reason": "radarr_profile_or_root_folder_missing",
            "candidate": candidate,
            "safe_default": "do_not_recommend_movie_download",
        }
    payload = dict(lookup)
    payload.update({
        "qualityProfileId": profile_id,
        "rootFolderPath": root_folder,
        "monitored": False,
        "minimumAvailability": "released",
        "addOptions": {"searchForMovie": False},
    })
    response = radarr_request("POST", "/movie", json_body=payload, timeout=30.0)
    if response.status_code not in {200, 201, 202}:
        return {
            "status": "not_added",
            "reason": f"radarr_add_http_{response.status_code}",
            "body": response.text[:500],
            "candidate": candidate,
            "safe_default": "do_not_recommend_movie_download",
        }
    row = response.json()
    return {
        "status": "added_unmonitored_metadata_stub",
        "candidate": candidate,
        "radarr_id": row.get("id"),
        "tmdb_id": row.get("tmdbId"),
        "monitored": row.get("monitored"),
        "has_file": bool(row.get("movieFile") or row.get("movieFileId")),
        "search_for_movie": False,
        "quality_profile_id": profile_id,
        "root_folder_path": root_folder,
    }


def bazarr_swagger_paths() -> set[str]:
    response = httpx.get(f"{bazarr_url()}/api/swagger.json", timeout=httpx.Timeout(5.0, connect=2.0))
    response.raise_for_status()
    spec = response.json()
    return set(spec.get("paths", {}).keys())


def movie_file_from_record(record: dict[str, Any]) -> Path | None:
    value = record.get("path")
    if not value:
        return None
    path = Path(value)
    return path if path.suffix.lower() in VIDEO_EXTENSIONS else None


def existing_subtitle_candidates(media_path: Path, language: str) -> list[Path]:
    language = language.lower()
    parent = media_path.parent
    stem = media_path.stem
    candidates: list[Path] = []
    direct_names = []
    for ext in SUBTITLE_EXTENSIONS:
        direct_names.extend([
            parent / f"{stem}.{language}{ext}",
            parent / f"{stem}.{language.upper()}{ext}",
            parent / f"{stem}.eng{ext}" if language == "en" else parent / f"{stem}.{language}{ext}",
            media_path.with_suffix(ext),
        ])
    candidates.extend(direct_names)
    for ext in SUBTITLE_EXTENSIONS:
        candidates.extend(sorted(parent.glob(f"{stem}*.{language}{ext}")))
        if language == "en":
            candidates.extend(sorted(parent.glob(f"{stem}*.eng{ext}")))
        candidates.extend(sorted(parent.glob(f"{stem}*{ext}")))

    seen: set[Path] = set()
    unique: list[Path] = []
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        unique.append(candidate)
    return unique


def verified_subtitle_files_for_media(media_path: Path, language: str) -> list[dict[str, Any]]:
    if not media_path.exists():
        return []
    verified: list[dict[str, Any]] = []
    for candidate in existing_subtitle_candidates(media_path, language):
        if candidate.exists() and candidate.is_file() and candidate.stat().st_size > 0:
            metadata = subtitle_metadata(candidate)
            verified.append({
                "path": str(candidate),
                "format": candidate.suffix.lower().lstrip("."),
                "verified": True,
                "speaker_metadata_status": metadata.get("speaker_metadata_status", "not_present"),
                "metadata": metadata,
            })
    return verified


def embedded_text_subtitle_streams(media_path: Path, language: str) -> list[dict[str, Any]]:
    if not media_path.exists():
        return []
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", str(media_path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (subprocess.SubprocessError, FileNotFoundError, json.JSONDecodeError):
        return []
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    language_aliases = {language.lower()}
    if language.lower() == "en":
        language_aliases.update({"eng", "english"})
    text_codecs = {"subrip", "ass", "ssa", "webvtt", "mov_text"}
    streams: list[dict[str, Any]] = []
    for stream in payload.get("streams") or []:
        if stream.get("codec_type") != "subtitle":
            continue
        codec_name = str(stream.get("codec_name") or "").lower()
        if codec_name not in text_codecs:
            continue
        tags = stream.get("tags") or {}
        stream_language = str(tags.get("language") or "").lower()
        if stream_language and stream_language not in language_aliases:
            continue
        streams.append({
            "index": stream.get("index"),
            "codec_name": codec_name,
            "language": stream_language or None,
            "title": tags.get("title"),
        })
    return streams


def extract_embedded_text_subtitle(media_path: Path, language: str) -> Path | None:
    streams = embedded_text_subtitle_streams(media_path, language)
    if not streams:
        return None
    stream = streams[0]
    stream_index = stream.get("index")
    if stream_index is None:
        return None
    suffix = ".srt"
    output_path = media_path.with_name(f"{media_path.stem}.{language.lower()}{suffix}")
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-i",
                str(media_path),
                "-map",
                f"0:{stream_index}",
                "-c:s",
                "srt",
                str(output_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return None
    if output_path.exists() and output_path.is_file() and output_path.stat().st_size > 0:
        return output_path
    return None


def primary_subtitle_path(subtitle_files: list[dict[str, Any]]) -> Path | None:
    if not subtitle_files:
        return None
    for item in subtitle_files:
        if item.get("format") == PRIMARY_SUBTITLE_FORMAT.lstrip("."):
            return Path(str(item["path"]))
    return Path(str(subtitle_files[0]["path"]))


def verified_subtitle_for_media(media_path: Path, language: str) -> Path | None:
    return primary_subtitle_path(verified_subtitle_files_for_media(media_path, language))


def subtitle_from_bazarr_record(record: dict[str, Any], language: str) -> Path | None:
    for item in record.get("subtitles") or []:
        if str(item.get("code2", "")).lower() != language.lower():
            continue
        path_value = item.get("path")
        if not path_value:
            continue
        path = Path(path_value)
        if path.exists() and path.is_file() and path.stat().st_size > 0:
            return path
    return None


def verification_receipt(
    *,
    media_path: Path | None,
    language: str,
    subtitle_path: Path | None,
    subtitle_files: list[dict[str, Any]] | None = None,
    radarr_id: int | None = None,
    movie_title: str | None = None,
    movie_year: str | int | None = None,
    source: str = "filesystem",
    reason: str = "english_srt_missing",
) -> dict[str, Any]:
    if subtitle_files is None and media_path:
        subtitle_files = verified_subtitle_files_for_media(media_path, language)
    if subtitle_files is None:
        subtitle_files = []
    if not subtitle_files and subtitle_path:
        metadata = subtitle_metadata(subtitle_path)
        subtitle_files = [{
            "path": str(subtitle_path),
            "format": subtitle_path.suffix.lower().lstrip("."),
            "verified": True,
            "metadata": metadata,
            "speaker_metadata_status": metadata.get("speaker_metadata_status", "not_present"),
        }]
    if subtitle_path:
        return {
            "status": "verified",
            "language": language,
            "subtitle_path": str(subtitle_path),
            "primary_subtitle_format": subtitle_path.suffix.lower().lstrip("."),
            "subtitle_files": subtitle_files,
            "media_path": str(media_path) if media_path else None,
            "radarr_id": radarr_id,
            "movie_title": movie_title,
            "movie_year": movie_year,
            "source": source,
            "safe_default": "allow_watch_processing",
            "verified_at": int(time.time()),
        }
    return {
        "status": "not_verified",
        "language": language,
        "subtitle_files": subtitle_files,
        "media_path": str(media_path) if media_path else None,
        "radarr_id": radarr_id,
        "movie_title": movie_title,
        "movie_year": movie_year,
        "reason": reason,
        "safe_default": "do_not_process_for_watch_or_orpheus",
        "verified_at": int(time.time()),
    }


def scan_srt_for_emotions(subtitle_path: Path, emotions: list[str]) -> dict[str, Any]:
    text = subtitle_path.read_text(encoding="utf-8", errors="replace")
    target_emotions = emotions or ORPHEUS_EMOTIONS
    aliases = {
        emotion: EMOTION_MARKERS.get(emotion, [emotion])
        for emotion in target_emotions
    }
    matches: list[dict[str, Any]] = []
    counts = {emotion: 0 for emotion in target_emotions}
    current_timecode: str | None = None
    current_start_seconds: float | None = None
    current_end_seconds: float | None = None
    current_speaker: str | None = None
    ass_format_fields: list[str] = []

    def parse_timecode(stripped: str) -> tuple[str | None, float | None, float | None]:
        time_match = SRT_TIMECODE_RE.search(stripped) or VTT_TIMECODE_RE.search(stripped)
        if not time_match:
            return stripped, None, None
        start_seconds = (
            int(time_match.group("sh")) * 3600
            + int(time_match.group("sm")) * 60
            + int(time_match.group("ss"))
            + int(time_match.group("sms")) / 1000
        )
        end_seconds = (
            int(time_match.group("eh")) * 3600
            + int(time_match.group("em")) * 60
            + int(time_match.group("es"))
            + int(time_match.group("ems")) / 1000
        )
        return stripped, start_seconds, end_seconds

    def ass_time_to_seconds(value: str) -> float | None:
        match = re.match(r"(?P<h>\d+):(?P<m>\d{2}):(?P<s>\d{2})[.](?P<cs>\d{2})", value.strip())
        if not match:
            return None
        return int(match.group("h")) * 3600 + int(match.group("m")) * 60 + int(match.group("s")) + int(match.group("cs")) / 100

    def scan_text(stripped: str, speaker: str | None = None) -> None:
        bracketed_match_spans: list[tuple[int, int]] = []
        for marker_match in re.finditer(r"[\[(]([^\]\)]+)[\])]", stripped):
            bracketed_match_spans.append(marker_match.span())
            marker = marker_match.group(1).strip().lower()
            if marker in AMBIENT_REJECT_MARKERS:
                continue
            for emotion, emotion_aliases in aliases.items():
                if any(re.search(rf"\b{re.escape(alias)}\b", marker) for alias in emotion_aliases):
                    counts[emotion] += 1
                    matches.append({
                        "emotion": emotion,
                        "marker": marker_match.group(0),
                        "timecode": current_timecode,
                        "start_seconds": current_start_seconds,
                        "end_seconds": current_end_seconds,
                        "speaker": speaker,
                        "line": stripped,
                    })
        if bracketed_match_spans:
            return
        plain = HTML_TAG_RE.sub("", stripped).strip()
        letters = [char for char in plain if char.isalpha()]
        if not letters or len(plain) > 90 or ":" in plain:
            return
        uppercase_ratio = sum(1 for char in letters if char.isupper()) / len(letters)
        if uppercase_ratio < 0.8:
            return
        plain_lower = plain.lower()
        if any(marker in plain_lower for marker in AMBIENT_REJECT_MARKERS):
            return
        for emotion, emotion_aliases in aliases.items():
            for alias in emotion_aliases:
                alias_match = re.search(rf"\b{re.escape(alias)}(?:s|ing|ed)?\b", plain_lower)
                if not alias_match:
                    continue
                inferred_speaker = speaker
                prefix = re.sub(r"[^A-Za-z0-9 ._'’-]+", " ", plain[:alias_match.start()]).strip()
                prefix_words = [word for word in prefix.split() if word.lower() not in ACTION_CUE_CONNECTORS]
                if 0 < len(prefix_words) <= 4:
                    inferred_speaker = " ".join(prefix_words).title()
                counts[emotion] += 1
                matches.append({
                    "emotion": emotion,
                    "marker": plain,
                    "timecode": current_timecode,
                    "start_seconds": current_start_seconds,
                    "end_seconds": current_end_seconds,
                    "speaker": inferred_speaker,
                    "line": stripped,
                    "cue_type": "subtitle_action_line",
                })
                break

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("format:"):
            ass_format_fields = [part.strip().lower() for part in stripped.split(":", 1)[1].split(",")]
            continue
        dialogue_match = ASS_DIALOGUE_RE.match(stripped)
        if dialogue_match and ass_format_fields:
            values = [part.strip() for part in dialogue_match.group("body").split(",", maxsplit=max(0, len(ass_format_fields) - 1))]
            field_map = dict(zip(ass_format_fields, values))
            start = field_map.get("start")
            end = field_map.get("end")
            current_start_seconds = ass_time_to_seconds(start or "")
            current_end_seconds = ass_time_to_seconds(end or "")
            current_timecode = f"{start} --> {end}" if start and end else None
            current_speaker = field_map.get("name")
            scan_text(field_map.get("text", stripped), current_speaker)
            continue
        if "-->" in stripped:
            current_timecode, current_start_seconds, current_end_seconds = parse_timecode(stripped)
            continue
        vtt_speaker_match = VTT_SPEAKER_RE.search(stripped)
        speaker = vtt_speaker_match.group(1).strip() if vtt_speaker_match else current_speaker
        scan_text(stripped, speaker)
    missing = [emotion for emotion, count in counts.items() if count == 0]
    return {
        "subtitle_path": str(subtitle_path),
        "metadata": subtitle_metadata(subtitle_path),
        "target_emotions": target_emotions,
        "counts": counts,
        "missing": missing,
        "matches": matches,
        "status": "has_orpheus_tags" if matches else "no_orpheus_tags",
    }


def get_movies_by_radarr(radarr_id: int) -> list[dict[str, Any]]:
    response = bazarr_request("GET", "/movies", params=[("radarrid[]", radarr_id)])
    response.raise_for_status()
    data = response.json()
    return data.get("data", []) if isinstance(data, dict) else []


def find_movie_records(query: str | None, start: int, length: int) -> dict[str, Any]:
    fetch_length = length
    if query:
        # Bazarr filters are local to the page we request; for query mode fetch
        # the inventory window broadly enough to avoid false "not local" results
        # for movies outside the first page.
        fetch_length = max(length, 1000)
        start = 0
    response = bazarr_request("GET", "/movies", params={"start": start, "length": fetch_length})
    response.raise_for_status()
    data = response.json()
    if not query:
        return data
    q = query.lower()
    rows = [
        row for row in data.get("data", [])
        if q in str(row.get("title", "")).lower()
        or q in str(row.get("sceneName", "")).lower()
        or q in str(row.get("path", "")).lower()
    ]
    return {"data": rows, "total": len(rows), "source_total": data.get("total")}


def ensure_radarr_receipt_sync(radarr_id: int, language: str, download: bool) -> dict[str, Any]:
    try:
        records = get_movies_by_radarr(radarr_id)
    except Exception as exc:
        return verification_receipt(
            media_path=None,
            language=language,
            subtitle_path=None,
            radarr_id=radarr_id,
            reason=f"bazarr_lookup_failed:{type(exc).__name__}",
        )
    if not records:
        return verification_receipt(media_path=None, language=language, subtitle_path=None, radarr_id=radarr_id, reason="movie_not_found")
    record = records[0]
    media_path = movie_file_from_record(record)
    movie_title = record.get("title")
    movie_year = record.get("year")
    subtitle_path = subtitle_from_bazarr_record(record, language)
    subtitle_files = verified_subtitle_files_for_media(media_path, language) if media_path else []
    if not subtitle_path:
        subtitle_path = primary_subtitle_path(subtitle_files)
    if not subtitle_path and media_path:
        subtitle_path = extract_embedded_text_subtitle(media_path, language)
        subtitle_files = verified_subtitle_files_for_media(media_path, language)
    if subtitle_path or not download:
        return verification_receipt(
            media_path=media_path,
            language=language,
            subtitle_path=subtitle_path,
            subtitle_files=subtitle_files,
            radarr_id=radarr_id,
            movie_title=movie_title,
            movie_year=movie_year,
        )
    response = bazarr_request(
        "PATCH",
        "/movies/subtitles",
        params={"radarrid": radarr_id, "language": language, "forced": "False", "hi": "False"},
        timeout=30.0,
    )
    if response.status_code not in {200, 204}:
        receipt = verification_receipt(
            media_path=media_path,
            language=language,
            subtitle_path=None,
            radarr_id=radarr_id,
            movie_title=movie_title,
            movie_year=movie_year,
        )
        receipt["reason"] = f"bazarr_download_http_{response.status_code}"
        return receipt
    time.sleep(1.0)
    records = get_movies_by_radarr(radarr_id)
    refreshed = records[0] if records else record
    media_path = movie_file_from_record(refreshed) or media_path
    movie_title = refreshed.get("title") or movie_title
    movie_year = refreshed.get("year") or movie_year
    subtitle_path = subtitle_from_bazarr_record(refreshed, language)
    subtitle_files = verified_subtitle_files_for_media(media_path, language) if media_path else []
    if not subtitle_path:
        subtitle_path = primary_subtitle_path(subtitle_files)
    if not subtitle_path and media_path:
        subtitle_path = extract_embedded_text_subtitle(media_path, language)
        subtitle_files = verified_subtitle_files_for_media(media_path, language)
    receipt = verification_receipt(
        media_path=media_path,
        language=language,
        subtitle_path=subtitle_path,
        subtitle_files=subtitle_files,
        radarr_id=radarr_id,
        movie_title=movie_title,
        movie_year=movie_year,
        source="bazarr",
    )
    if not subtitle_path:
        receipt["reason"] = "bazarr_download_did_not_produce_verified_file"
    return receipt


@app.command()
def doctor(json_output: bool = typer.Option(False, "--json", help="Emit JSON.")) -> None:
    """Check Bazarr configuration without printing secrets."""
    result: dict[str, Any] = {
        "status": "not_verified",
        "bazarr_url": bazarr_url(),
        "bazarr_api_key": "set" if os.environ.get("BAZARR_API_KEY") else "missing",
        "safe_default": "do_not_process_for_watch_or_orpheus",
    }
    try:
        swagger = httpx.get(f"{bazarr_url()}/api/swagger.json", timeout=httpx.Timeout(5.0, connect=2.0))
        result["swagger_status_code"] = swagger.status_code
        if swagger.status_code == 200:
            spec = swagger.json()
            result["auth_header"] = spec.get("securityDefinitions", {}).get("apikey", {}).get("name")
            result["endpoints"] = [
                path for path in spec.get("paths", {})
                if path in {
                    "/movies",
                    "/providers/movies",
                    "/movies/subtitles",
                    "/subtitles",
                    "/subtitles/search",
                    "/subtitles/download",
                    "/system/searches",
                }
            ]
    except Exception as exc:
        result["reason"] = f"bazarr_unreachable:{type(exc).__name__}"
        emit(result, json_output)
        raise typer.Exit(1)

    if not os.environ.get("BAZARR_API_KEY"):
        result["reason"] = "missing_bazarr_api_key"
        emit(result, json_output)
        raise typer.Exit(1)

    try:
        movies_response = bazarr_request("GET", "/movies", params={"start": 0, "length": 1})
        result["movies_status_code"] = movies_response.status_code
        result["authenticated"] = movies_response.status_code == 200
        if movies_response.status_code == 200:
            result["status"] = "verified"
            result["safe_default"] = "allow_bazarr_subtitle_checks"
    except Exception as exc:
        result["reason"] = f"authenticated_call_failed:{type(exc).__name__}"
        emit(result, json_output)
        raise typer.Exit(1)

    emit(result, json_output)


@app.command()
def movies(
    query: str | None = typer.Option(None, "--query", "-q", help="Filter movies by title, scene name, or path."),
    start: int = typer.Option(0, "--start", help="Paging start."),
    length: int = typer.Option(20, "--length", help="Paging length."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """List Bazarr movies."""
    try:
        data = find_movie_records(query, start, length)
    except httpx.HTTPStatusError as exc:
        emit({"status": "error", "reason": f"bazarr_http_{exc.response.status_code}"}, json_output)
        raise typer.Exit(1)
    emit({"status": "ok", **data}, json_output)


@app.command("verify-file")
def verify_file(
    media_path: Path = typer.Option(..., "--media-path", exists=False, help="Local media file path."),
    language: str = typer.Option("en", "--language", "-l", help="Language code2."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Verify a real local subtitle file exists beside a media file."""
    subtitle_files = verified_subtitle_files_for_media(media_path, language)
    subtitle_path = primary_subtitle_path(subtitle_files)
    reason = "media_file_missing" if not media_path.exists() else "english_subtitle_missing"
    emit(verification_receipt(
        media_path=media_path,
        language=language,
        subtitle_path=subtitle_path,
        subtitle_files=subtitle_files,
        reason=reason,
    ), json_output)


@app.command("ensure-radarr")
def ensure_radarr(
    radarr_id: int = typer.Option(..., "--radarr-id", help="Radarr/Bazarr movie id."),
    language: str = typer.Option("en", "--language", "-l", help="Language code2."),
    download: bool = typer.Option(True, "--download/--no-download", help="Ask Bazarr to download missing subtitles."),
    forced: bool = typer.Option(False, "--forced/--not-forced", help="Forced subtitle flag."),
    hi: bool = typer.Option(False, "--hi/--no-hi", help="Hearing-impaired subtitle flag."),
    poll_seconds: float = typer.Option(1.0, "--poll-seconds", help="Delay after download request."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Ensure a Radarr/Bazarr movie has a verified subtitle file."""
    records = get_movies_by_radarr(radarr_id)
    if not records:
        emit(verification_receipt(media_path=None, language=language, subtitle_path=None, radarr_id=radarr_id, reason="movie_not_found"), json_output)
        raise typer.Exit(1)

    record = records[0]
    media_path = movie_file_from_record(record)
    movie_title = record.get("title")
    movie_year = record.get("year")
    subtitle_path = subtitle_from_bazarr_record(record, language)
    subtitle_files = verified_subtitle_files_for_media(media_path, language) if media_path else []
    if not subtitle_path:
        subtitle_path = primary_subtitle_path(subtitle_files)
    if not subtitle_path and media_path:
        subtitle_path = extract_embedded_text_subtitle(media_path, language)
        subtitle_files = verified_subtitle_files_for_media(media_path, language)
    if subtitle_path:
        emit(verification_receipt(
            media_path=media_path,
            language=language,
            subtitle_path=subtitle_path,
            subtitle_files=subtitle_files,
            radarr_id=radarr_id,
            movie_title=movie_title,
            movie_year=movie_year,
        ), json_output)
        return

    if not download:
        emit(verification_receipt(
            media_path=media_path,
            language=language,
            subtitle_path=None,
            radarr_id=radarr_id,
            movie_title=movie_title,
            movie_year=movie_year,
        ), json_output)
        raise typer.Exit(1)

    response = bazarr_request(
        "PATCH",
        "/movies/subtitles",
        params={
            "radarrid": radarr_id,
            "language": language,
            "forced": str(forced),
            "hi": str(hi),
        },
        timeout=30.0,
    )
    if response.status_code not in {200, 204}:
        emit({
            **verification_receipt(
                media_path=media_path,
                language=language,
                subtitle_path=None,
                radarr_id=radarr_id,
                movie_title=movie_title,
                movie_year=movie_year,
            ),
            "reason": f"bazarr_download_http_{response.status_code}",
            "bazarr_response": response.text[:500],
        }, json_output)
        raise typer.Exit(1)

    time.sleep(max(0.0, poll_seconds))
    records = get_movies_by_radarr(radarr_id)
    refreshed = records[0] if records else record
    media_path = movie_file_from_record(refreshed) or media_path
    movie_title = refreshed.get("title") or movie_title
    movie_year = refreshed.get("year") or movie_year
    subtitle_path = subtitle_from_bazarr_record(refreshed, language)
    subtitle_files = verified_subtitle_files_for_media(media_path, language) if media_path else []
    if not subtitle_path:
        subtitle_path = primary_subtitle_path(subtitle_files)
    if not subtitle_path and media_path:
        subtitle_path = extract_embedded_text_subtitle(media_path, language)
        subtitle_files = verified_subtitle_files_for_media(media_path, language)
    receipt = verification_receipt(
        media_path=media_path,
        language=language,
        subtitle_path=subtitle_path,
        subtitle_files=subtitle_files,
        radarr_id=radarr_id,
        movie_title=movie_title,
        movie_year=movie_year,
        source="bazarr",
    )
    if not subtitle_path:
        receipt["reason"] = "bazarr_download_did_not_produce_verified_file"
        emit(receipt, json_output)
        raise typer.Exit(1)
    emit(receipt, json_output)


@app.command()
def providers(
    radarr_id: int = typer.Option(..., "--radarr-id", help="Radarr/Bazarr movie id."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Ask Bazarr providers for manual movie subtitle candidates."""
    response = bazarr_request("GET", "/providers/movies", params={"radarrid": radarr_id}, timeout=60.0)
    if response.status_code != 200:
        emit({"status": "error", "reason": f"bazarr_http_{response.status_code}", "body": response.text[:500]}, json_output)
        raise typer.Exit(1)
    emit({"status": "ok", "radarr_id": radarr_id, "providers": response.json()}, json_output)


@app.command("download-provider")
def download_provider(
    radarr_id: int = typer.Option(..., "--radarr-id", help="Radarr/Bazarr movie id."),
    provider: str = typer.Option(..., "--provider", help="Provider name returned by providers."),
    subtitle: str = typer.Option(..., "--subtitle", help="Provider subtitle payload returned by providers."),
    language: str = typer.Option("en", "--language", "-l", help="Language code2 for verification after download."),
    original_format: bool = typer.Option(True, "--original-format/--convert-format", help="Ask Bazarr to preserve source format when possible."),
    forced: bool = typer.Option(False, "--forced/--not-forced", help="Forced subtitle flag."),
    hi: bool = typer.Option(False, "--hi/--no-hi", help="Hearing-impaired subtitle flag."),
    poll_seconds: float = typer.Option(1.0, "--poll-seconds", help="Delay after download request."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Manually download a provider result and verify the created subtitle file."""
    records = get_movies_by_radarr(radarr_id)
    record = records[0] if records else {}
    media_path = movie_file_from_record(record) if record else None
    response = bazarr_request(
        "POST",
        "/providers/movies",
        params={
            "radarrid": radarr_id,
            "hi": str(hi),
            "forced": str(forced),
            "original_format": str(original_format),
            "provider": provider,
            "subtitle": subtitle,
        },
        timeout=60.0,
    )
    if response.status_code not in {200, 204}:
        emit({
            "status": "error",
            "reason": f"bazarr_provider_download_http_{response.status_code}",
            "body": response.text[:500],
            "safe_default": "do_not_process_for_watch_or_orpheus",
        }, json_output)
        raise typer.Exit(1)
    time.sleep(max(0.0, poll_seconds))
    subtitle_files = verified_subtitle_files_for_media(media_path, language) if media_path else []
    subtitle_path = primary_subtitle_path(subtitle_files)
    emit(verification_receipt(
        media_path=media_path,
        language=language,
        subtitle_path=subtitle_path,
        subtitle_files=subtitle_files,
        radarr_id=radarr_id,
        movie_title=record.get("title"),
        movie_year=record.get("year"),
        source="bazarr_provider_original_format" if original_format else "bazarr_provider_converted",
        reason="bazarr_provider_download_did_not_produce_verified_file",
    ), json_output)


def normalize_subtitle_search_results(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        for key in ("data", "results", "subtitles"):
            value = payload.get(key)
            if isinstance(value, list):
                rows = value
                break
        else:
            rows = []
    else:
        rows = []
    return [row for row in rows if isinstance(row, dict)]


def subtitle_result_format(row: dict[str, Any]) -> str:
    for key in ("ext", "format", "extension", "subtitle_format"):
        value = row.get(key)
        if value:
            return str(value).lower().lstrip(".")
    filename = str(row.get("filename") or row.get("release") or row.get("version") or "")
    suffix = Path(filename).suffix.lower().lstrip(".")
    return suffix


def select_subtitle_result(rows: list[dict[str, Any]], preferred_formats: list[str]) -> dict[str, Any] | None:
    scored: list[tuple[int, int, dict[str, Any]]] = []
    for index, row in enumerate(rows):
        row_format = subtitle_result_format(row)
        try:
            format_score = preferred_formats.index(row_format)
        except ValueError:
            format_score = len(preferred_formats) + 1
        score_value = row.get("score") or row.get("matches") or 0
        try:
            provider_score = -int(float(score_value))
        except (TypeError, ValueError):
            provider_score = 0
        scored.append((format_score, provider_score, row))
    if not scored:
        return None
    scored.sort(key=lambda item: (item[0], item[1]))
    return scored[0][2]


def provider_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
        for key in ("results", "subtitles", "providers"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def trigger_bazarr_movie_sync() -> dict[str, Any]:
    response = bazarr_request("POST", "/system/tasks", params={"taskid": "update_movies"}, timeout=10.0)
    return {
        "status_code": response.status_code,
        "status": "started" if response.status_code in {200, 202, 204} else "error",
        "body": response.text[:300],
    }


def wait_for_bazarr_movie(radarr_id: int, wait_seconds: float) -> dict[str, Any]:
    deadline = time.time() + max(0.0, wait_seconds)
    attempts: list[dict[str, Any]] = []
    while True:
        response = bazarr_request("GET", "/movies", params=[("radarrid[]", radarr_id)], timeout=10.0)
        rows: list[dict[str, Any]] = []
        if response.status_code == 200:
            payload = response.json()
            rows = payload.get("data", []) if isinstance(payload, dict) else payload
        attempts.append({
            "status_code": response.status_code,
            "row_count": len(rows or []),
        })
        if rows:
            return {"status": "found", "attempts": attempts, "records": rows}
        if time.time() >= deadline:
            return {"status": "not_found", "attempts": attempts, "records": []}
        time.sleep(2.0)


def bazarr_provider_probe_for_radarr(radarr_id: int) -> dict[str, Any]:
    response = bazarr_request("GET", "/providers/movies", params={"radarrid": radarr_id}, timeout=60.0)
    if response.status_code != 200:
        return {
            "status": "not_available",
            "reason": f"bazarr_providers_http_{response.status_code}",
            "body": response.text[:500],
            "provider_count": 0,
            "providers": [],
        }
    payload = response.json()
    rows = provider_rows(payload)
    return {
        "status": "provider_results_found" if rows else "no_provider_results",
        "provider_count": len(rows),
        "providers": rows,
    }


def bazarr_nonlocal_subtitle_probe(
    candidate: dict[str, Any],
    *,
    create_radarr_stub: bool,
    sync_wait_seconds: float,
) -> dict[str, Any]:
    title = str(candidate.get("title") or "")
    bazarr_title_search: dict[str, Any]
    response = bazarr_request("GET", "/system/searches", params={"query": title}, timeout=10.0)
    if response.status_code == 200:
        results = response.json()
        bazarr_title_search = {
            "status": "ok",
            "result_count": len(results if isinstance(results, list) else results.get("data", [])),
            "results": results,
        }
    else:
        bazarr_title_search = {
            "status": "error",
            "reason": f"bazarr_system_search_http_{response.status_code}",
            "body": response.text[:300],
        }
    if not create_radarr_stub:
        return {
            "candidate": candidate,
            "status": "not_vetted",
            "bazarr_title_search": bazarr_title_search,
            "radarr_stub": {"status": "not_attempted", "reason": "create_radarr_stub_disabled"},
            "provider_probe": {"status": "not_attempted"},
            "safe_default": "do_not_recommend_movie_download",
        }
    radarr_stub = radarr_add_metadata_stub(candidate)
    radarr_id = radarr_stub.get("radarr_id")
    if not radarr_id:
        return {
            "candidate": candidate,
            "status": "not_vetted",
            "bazarr_title_search": bazarr_title_search,
            "radarr_stub": radarr_stub,
            "provider_probe": {"status": "not_attempted", "reason": "no_radarr_id"},
            "safe_default": "do_not_recommend_movie_download",
        }
    sync_receipt = trigger_bazarr_movie_sync()
    bazarr_movie = wait_for_bazarr_movie(int(radarr_id), sync_wait_seconds)
    if bazarr_movie.get("status") != "found":
        return {
            "candidate": candidate,
            "status": "not_vetted",
            "bazarr_title_search": bazarr_title_search,
            "radarr_stub": radarr_stub,
            "bazarr_sync": sync_receipt,
            "bazarr_movie": bazarr_movie,
            "provider_probe": {
                "status": "not_attempted",
                "reason": "bazarr_did_not_index_radarr_metadata_stub_without_movie_file",
            },
            "safe_default": "do_not_recommend_movie_download",
        }
    provider_probe = bazarr_provider_probe_for_radarr(int(radarr_id))
    return {
        "candidate": candidate,
        "status": "subtitle_provider_vetted" if provider_probe.get("provider_count", 0) > 0 else "no_provider_subtitles_found",
        "bazarr_title_search": bazarr_title_search,
        "radarr_stub": radarr_stub,
        "bazarr_sync": sync_receipt,
        "bazarr_movie": bazarr_movie,
        "provider_probe": provider_probe,
        "safe_default": "do_not_recommend_movie_download_until_subtitle_text_is_downloaded_and_scanned",
    }


@app.command("api-search-download")
def api_search_download(
    language: str = typer.Option("en", "--language", "-l", help="Language code2."),
    preferred_formats: str = typer.Option("vtt,ass,ssa,srt", "--preferred-formats", help="Comma-separated format preference."),
    radarr_id: int | None = typer.Option(None, "--radarr-id", help="Movie/Radarr ID when supported by Bazarr."),
    series_id: int | None = typer.Option(None, "--series-id", help="Series ID for episode subtitle search."),
    episode_id: int | None = typer.Option(None, "--episode-id", help="Episode ID for episode subtitle search."),
    subtitle_id: str | None = typer.Option(None, "--subtitle-id", help="Specific subtitle ID to download."),
    media_path: Path | None = typer.Option(None, "--media-path", exists=False, help="Optional media path for post-download verification."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Search and select without downloading."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Use the generic /subtitles/search + /subtitles/download API when this Bazarr exposes it."""
    required_paths = {"/subtitles/search", "/subtitles/download"}
    try:
        paths = bazarr_swagger_paths()
    except Exception as exc:
        emit({
            "status": "error",
            "reason": f"bazarr_swagger_unavailable:{type(exc).__name__}",
            "safe_default": "do_not_process_for_watch_or_orpheus",
        }, json_output)
        raise typer.Exit(1)
    if not required_paths.issubset(paths):
        emit({
            "status": "not_available",
            "reason": "generic_subtitle_search_download_endpoints_not_exposed_by_this_bazarr",
            "requested_endpoints": sorted(required_paths),
            "available_alternative": "GET /api/providers/movies then POST /api/providers/movies with original_format=True",
            "safe_default": "use_download_provider_or_patch_movies_subtitles_then_verify_local_file",
        }, json_output)
        raise typer.Exit(2)

    params: dict[str, Any] = {"languages": language}
    if radarr_id is not None:
        params["radarrid"] = radarr_id
    if series_id is not None:
        params["seriesid"] = series_id
    if episode_id is not None:
        params["episodeid"] = episode_id
    response = bazarr_request("GET", "/subtitles/search", params=params, timeout=60.0)
    if response.status_code != 200:
        emit({
            "status": "error",
            "reason": f"bazarr_subtitles_search_http_{response.status_code}",
            "body": response.text[:500],
            "safe_default": "do_not_process_for_watch_or_orpheus",
        }, json_output)
        raise typer.Exit(1)

    rows = normalize_subtitle_search_results(response.json())
    formats = [part.strip().lower().lstrip(".") for part in preferred_formats.split(",") if part.strip()]
    selected = next((row for row in rows if str(row.get("id")) == subtitle_id), None) if subtitle_id else select_subtitle_result(rows, formats)
    if not selected:
        emit({
            "status": "not_verified",
            "reason": "no_subtitle_search_result_matched_preferences",
            "preferred_formats": formats,
            "result_count": len(rows),
            "safe_default": "do_not_process_for_watch_or_orpheus",
        }, json_output)
        raise typer.Exit(1)
    selected_id = selected.get("id") or selected.get("subtitle_id")
    if dry_run:
        emit({
            "status": "planned",
            "selected": selected,
            "selected_format": subtitle_result_format(selected),
            "result_count": len(rows),
            "safe_default": "search_only_no_verified_local_file",
        }, json_output)
        return
    if not selected_id:
        emit({
            "status": "not_verified",
            "reason": "selected_result_has_no_download_id",
            "selected": selected,
            "safe_default": "do_not_process_for_watch_or_orpheus",
        }, json_output)
        raise typer.Exit(1)

    download_response = bazarr_request(
        "POST",
        "/subtitles/download",
        json_body={"subtitle_id": selected_id},
        timeout=60.0,
    )
    if download_response.status_code not in {200, 204}:
        emit({
            "status": "error",
            "reason": f"bazarr_subtitles_download_http_{download_response.status_code}",
            "body": download_response.text[:500],
            "selected": selected,
            "safe_default": "do_not_process_for_watch_or_orpheus",
        }, json_output)
        raise typer.Exit(1)
    time.sleep(1.0)
    subtitle_files = verified_subtitle_files_for_media(media_path, language) if media_path else []
    subtitle_path = primary_subtitle_path(subtitle_files)
    receipt = verification_receipt(
        media_path=media_path,
        language=language,
        subtitle_path=subtitle_path,
        subtitle_files=subtitle_files,
        source="bazarr_generic_subtitles_api",
        reason="generic_api_download_did_not_produce_verified_file",
    )
    receipt["selected"] = selected
    receipt["selected_format"] = subtitle_result_format(selected)
    emit(receipt, json_output)
    if receipt["status"] != "verified":
        raise typer.Exit(1)


@app.command()
def search(
    query: str = typer.Option(..., "--query", "-q", help="Movie title query for Bazarr system search."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Search Bazarr/Sonarr/Radarr for a movie or series name."""
    response = bazarr_request("GET", "/system/searches", params={"query": query}, timeout=10.0)
    if response.status_code != 200:
        emit({"status": "error", "reason": f"bazarr_http_{response.status_code}", "body": response.text[:500]}, json_output)
        raise typer.Exit(1)
    emit({"status": "ok", "query": query, "results": response.json()}, json_output)


@app.command("scan-srt")
def scan_srt(
    subtitle_path: Path = typer.Option(..., "--subtitle", exists=True, help="SRT file to scan."),
    emotion: str | None = typer.Option(None, "--emotion", help="Orpheus emotion hint or comma list."),
    all_orpheus_emotions: bool = typer.Option(True, "--all-orpheus-emotions/--targeted-emotions", help="Scan all default Orpheus emotion tags."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Scan an SRT for explicit Orpheus cue markers with exact timecodes."""
    emotions = parse_emotions(emotion, all_orpheus_emotions)
    emit(scan_srt_for_emotions(subtitle_path, emotions), json_output)


async def ensure_and_scan_one(radarr_id: int, language: str, emotions: list[str], download: bool) -> dict[str, Any]:
    receipt = await asyncio.to_thread(ensure_radarr_receipt_sync, radarr_id, language, download)
    result: dict[str, Any] = {
        "radarr_id": radarr_id,
        "subtitle_receipt": receipt,
        "scan": None,
        "status": "not_scanned",
    }
    subtitle_path = receipt.get("subtitle_path")
    if receipt.get("status") == "verified" and subtitle_path:
        scan = await asyncio.to_thread(scan_srt_for_emotions, Path(subtitle_path), emotions)
        result["scan"] = scan
        result["status"] = "usable_srt_has_tags" if scan["matches"] else "verified_srt_no_target_tags"
    return result


@app.command("batch-ensure-radarr")
def batch_ensure_radarr(
    radarr_ids: str = typer.Option(..., "--radarr-ids", help="Comma-separated Radarr/Bazarr movie IDs."),
    language: str = typer.Option("en", "--language", "-l", help="Language code2."),
    emotion: str | None = typer.Option(None, "--emotion", help="Orpheus emotion hint or comma list."),
    all_orpheus_emotions: bool = typer.Option(True, "--all-orpheus-emotions/--targeted-emotions", help="Scan all default Orpheus emotion tags."),
    download: bool = typer.Option(True, "--download/--no-download", help="Ask Bazarr to download missing subtitles."),
    concurrency: int = typer.Option(4, "--concurrency", min=1, max=12, help="Concurrent Bazarr ensure tasks."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Concurrently ensure SRTs and scan each file as soon as it is verified."""
    ids = [int(part.strip()) for part in radarr_ids.split(",") if part.strip()]
    emotions = parse_emotions(emotion, all_orpheus_emotions)

    async def run_batch() -> dict[str, Any]:
        semaphore = asyncio.Semaphore(concurrency)

        async def bounded(movie_id: int) -> dict[str, Any]:
            async with semaphore:
                return await ensure_and_scan_one(movie_id, language, emotions, download)

        tasks = [asyncio.create_task(bounded(movie_id)) for movie_id in ids]
        results: list[dict[str, Any]] = []
        for task in asyncio.as_completed(tasks):
            results.append(await task)
        coverage = {emotion_name: 0 for emotion_name in (emotions or ORPHEUS_EMOTIONS)}
        for result in results:
            scan = result.get("scan") or {}
            for emotion_name, count in (scan.get("counts") or {}).items():
                coverage[emotion_name] = coverage.get(emotion_name, 0) + count
        missing = [emotion_name for emotion_name, count in coverage.items() if count == 0]
        return {
            "status": "ok",
            "radarr_ids": ids,
            "target_emotions": emotions or ORPHEUS_EMOTIONS,
            "processed_as_completed": True,
            "concurrency": concurrency,
            "coverage": coverage,
            "missing_emotions": missing,
            "results": results,
            "safe_default": "only_verified_srt_matches_can_feed_watch_or_orpheus",
        }

    emit(asyncio.run(run_batch()), json_output)


def parse_emotions(emotion: str | None, all_orpheus_emotions: bool) -> list[str]:
    if all_orpheus_emotions:
        return ORPHEUS_EMOTIONS
    if not emotion:
        return []
    values = [part.strip().lower() for part in emotion.split(",")]
    return [value for value in values if value]


def discovery_queries(actor: str, genre: str | None, emotions: list[str]) -> list[str]:
    parts = [actor.strip()]
    queries = []
    if genre and emotions:
        for emotion in emotions:
            queries.append(f"{actor} {genre} movies year likely {emotion} scenes")
            queries.append(f"{actor} movies with {emotion} scenes year")
        queries.append(f"What {genre} movies and year has actor {actor} been in")
        queries.append(f"{actor} filmography {genre} year")
    elif genre:
        queries.append(f"What {genre} movies and year has actor {actor} been in")
        queries.append(f"{actor} {genre} filmography year")
    elif emotions:
        for emotion in emotions:
            queries.append(f"{actor} movies likely {emotion} scenes year")
            queries.append(f"{actor} film scenes {emotion} year")
        queries.append(f"{actor} comedy drama filmography year")
    else:
        queries.append(f"{actor} filmography movies year")
    queries.append(" ".join(parts + ["movie credits year"]))
    return list(dict.fromkeys(queries))


def query_emotions(query: str, emotions: list[str]) -> list[str]:
    query_lower = query.lower()
    return [
        emotion for emotion in emotions
        if re.search(rf"\b{re.escape(emotion)}(?:s|ing|ed)?\b", query_lower)
    ]


MOVIE_YEAR_RE = re.compile(r"\b(?P<title>[A-Z][A-Za-z0-9'’:&.,!?\- ]{2,80}?)\s*\((?P<year>19\d{2}|20\d{2})\)")


def extract_movie_candidates(results: Any, actor: str, limit: int = 12) -> list[dict[str, Any]]:
    """Extract title/year candidate seeds from raw Brave snippets.

    These are not evidence. They are only a project-agent queue for local
    subtitle verification and ingest-movie acquisition.
    """
    candidates: dict[tuple[str, str], dict[str, Any]] = {}
    if not isinstance(results, dict):
        return []
    for query_key, query_result in results.items():
        web_results = ((query_result or {}).get("web") or {}).get("results") or []
        for web_result in web_results:
            haystack = " ".join([
                str(web_result.get("title", "")),
                str(web_result.get("description", "")),
            ])
            for match in MOVIE_YEAR_RE.finditer(haystack):
                title = re.sub(r"\s+", " ", match.group("title")).strip(" -–—:,.\"'")
                year = match.group("year")
                if len(title.split()) > 8 or actor.lower() in title.lower():
                    continue
                key = (title.lower(), year)
                if key not in candidates:
                    candidates[key] = {
                        "title": title,
                        "year": int(year),
                        "source_query": query_key,
                        "source_title": web_result.get("title"),
                        "source_url": web_result.get("url"),
                        "status": "candidate_seed_not_verified",
                    }
    return list(candidates.values())[:limit]


def extract_movie_candidates_with_queries(
    results: Any,
    actor: str,
    queries: list[str],
    emotions: list[str],
    limit: int = 40,
) -> list[dict[str, Any]]:
    candidates: dict[tuple[str, str], dict[str, Any]] = {}
    if not isinstance(results, dict):
        return []
    for query_key, query_result in results.items():
        query_index_match = re.match(r"q(\d+)$", str(query_key))
        query_text = ""
        if query_index_match:
            query_index = int(query_index_match.group(1))
            if 0 <= query_index < len(queries):
                query_text = queries[query_index]
        query_text = query_text or str((query_result or {}).get("query") or query_key)
        matched_emotions = query_emotions(query_text, emotions)
        web_results = ((query_result or {}).get("web") or {}).get("results") or []
        for web_result in web_results:
            haystack = " ".join([
                str(web_result.get("title", "")),
                str(web_result.get("description", "")),
            ])
            for match in MOVIE_YEAR_RE.finditer(haystack):
                title = re.sub(r"\s+", " ", match.group("title")).strip(" -–—:,.\"'")
                year = match.group("year")
                if len(title.split()) > 8 or actor.lower() in title.lower():
                    continue
                key = (title.lower(), year)
                entry = candidates.setdefault(key, {
                    "title": title,
                    "year": int(year),
                    "status": "candidate_seed_not_verified",
                    "source_queries": [],
                    "target_emotions": [],
                })
                entry["source_queries"].append({
                    "query_key": query_key,
                    "query": query_text,
                    "source_title": web_result.get("title"),
                    "source_url": web_result.get("url"),
                })
                for emotion in matched_emotions:
                    if emotion not in entry["target_emotions"]:
                        entry["target_emotions"].append(emotion)
    return list(candidates.values())[:limit]


def movie_record_title_matches(record: dict[str, Any], candidate: dict[str, Any]) -> bool:
    candidate_title = str(candidate.get("title", "")).lower()
    candidate_year = str(candidate.get("year", ""))
    titles: list[str] = [str(record.get("title", ""))]
    for value in record.get("alternativeTitles") or []:
        if isinstance(value, dict):
            titles.append(str(value.get("title") or value.get("name") or ""))
        else:
            titles.append(str(value))
    title_match = any(candidate_title == title.lower() for title in titles)
    loose_match = any(candidate_title in title.lower() or title.lower() in candidate_title for title in titles if title)
    year_match = not candidate_year or str(record.get("year", "")) == candidate_year
    return year_match and (title_match or loose_match)


def ingest_movie_release_availability_for_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    title = str(candidate.get("title") or "").strip()
    year = candidate.get("year")
    query = f"{title} {year}".strip() if year else title
    if not query:
        return {
            "candidate": candidate,
            "status": "not_checked",
            "reason": "missing_title",
            "release_found": False,
        }
    if not INGEST_MOVIE_RUN.exists():
        return {
            "candidate": candidate,
            "status": "not_checked",
            "reason": "ingest_movie_skill_missing",
            "path": str(INGEST_MOVIE_RUN),
            "release_found": False,
        }
    process = subprocess.run(
        [str(INGEST_MOVIE_RUN), "search", query],
        text=True,
        capture_output=True,
        timeout=45,
        check=False,
    )
    output = "\n".join(part for part in [process.stdout, process.stderr] if part).strip()
    no_results = "No results found" in output
    release_found = process.returncode == 0 and "Results for" in output and not no_results
    return {
        "candidate": candidate,
        "status": "checked",
        "composed_skill": "ingest-movie",
        "query": query,
        "release_found": release_found,
        "returncode": process.returncode,
        "evidence_level": "nzbgeek_release_search_only",
        "safe_default": "release_availability_is_not_subtitle_or_orpheus_evidence",
        "stdout_excerpt": output[:2000],
    }


def bazarr_local_matches_for_candidate(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        data = find_movie_records(str(candidate["title"]), 0, 100)
    except Exception as exc:
        return [{
            "status": "bazarr_lookup_failed",
            "reason": type(exc).__name__,
            "candidate": candidate,
        }]
    return [
        record for record in data.get("data", [])
        if movie_record_title_matches(record, candidate)
    ]


def movie_recommendation(candidate: dict[str, Any], reason: str) -> dict[str, Any]:
    title = candidate.get("title")
    year = candidate.get("year")
    return {
        "movie": f"{title} ({year})" if year else str(title),
        "reason": reason,
        "target_emotions": candidate.get("target_emotions", []),
        "commands": [
            f"skills/ingest-movie/run.sh search {json.dumps(str(title))}",
            "Prefer subtitle-rich WEB-DL/WEBRip/HDTV candidates, but require verified English .srt after import.",
            "After Radarr/Bazarr import: skills/get-subtitles/run.sh ensure-radarr --radarr-id <RADARR_ID> --language en --json",
            "Then rerun: skills/get-subtitles/run.sh orpheus-sanity --actor <ACTOR> --json",
        ],
    }


def split_movie_label(movie: str) -> tuple[str, int | None]:
    match = re.match(r"^(?P<title>.+?)\s*\((?P<year>19\d{2}|20\d{2})\)$", movie.strip())
    if not match:
        return movie.strip(), None
    return match.group("title").strip(), int(match.group("year"))


def build_ingest_movie_handoff(
    *,
    recommendations: list[dict[str, Any]],
    verified_hits: list[dict[str, Any]],
    actor: str,
) -> list[dict[str, Any]]:
    handoff: list[dict[str, Any]] = []
    for recommendation in recommendations:
        title, year = split_movie_label(str(recommendation.get("movie") or ""))
        movie_hits = [
            hit for hit in verified_hits
            if str(hit.get("movie_title") or "").lower() == title.lower()
            and (year is None or int(hit.get("movie_year") or 0) == year)
        ]
        emotion_counts: dict[str, int] = {}
        cue_windows: list[dict[str, Any]] = []
        for hit in sorted(movie_hits, key=lambda item: (float(item.get("start_seconds") or 0), str(item.get("emotion") or ""))):
            emotion = str(hit.get("emotion") or "")
            emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1
            cue_windows.append({
                "emotion": emotion,
                "timecode": hit.get("timecode"),
                "start_seconds": hit.get("start_seconds"),
                "end_seconds": hit.get("end_seconds"),
                "marker": hit.get("marker"),
                "line": hit.get("line"),
                "speaker_from_subtitle": hit.get("speaker"),
                "speaker_attribution_status": "subtitle_provided" if hit.get("speaker") else "unresolved_requires_watch_or_memory",
            })
        movie_query = f"{title} {year}" if year else title
        subtitle_query = f"{movie_query} WEB-DL English Subs SRT SDH CC"
        handoff.append({
            "title": title,
            "year": year,
            "actor_query": actor,
            "scope": recommendation.get("scope"),
            "recommendation_type": recommendation.get("recommendation_type"),
            "requires_ingest_movie": recommendation.get("requires_ingest_movie"),
            "ingest_status": "candidate_not_local" if recommendation.get("requires_ingest_movie") else "local_verified_subtitle_ready",
            "required_profile": "Orpheus-TTS",
            "preferred_release_query": subtitle_query,
            "nzbgeek_search": {
                "category": "movies-hd",
                "maxsize_bytes": 16106127360,
                "extended": True,
                "prefer_terms": ["WEB-DL", "WEBRip", "English Subs", "SRT", "SDH", "CC"],
                "avoid_terms": ["HC", "Hardcoded"],
                "commands": [
                    f"skills/ops-nzbgeek/run.sh search {json.dumps(subtitle_query)} --category movies-hd --maxsize 16106127360 --extended --json",
                    f"skills/ingest-movie/run.sh search {json.dumps(subtitle_query)}",
                ],
            },
            "subtitle_evidence": {
                "subtitle_path": recommendation.get("subtitle_path"),
                "source_url": recommendation.get("source_url"),
                "final_url": recommendation.get("final_url"),
                "evidence_level": recommendation.get("evidence_level"),
                "verified_emotions": recommendation.get("verified_emotions", []),
                "cue_count": recommendation.get("cue_count", len(cue_windows)),
                "emotion_counts": emotion_counts,
                "cue_windows": cue_windows,
            },
            "post_import_required_checks": [
                "movie file exists",
                "English .srt exists beside movie",
                "skills/get-subtitles/run.sh ensure-radarr --radarr-id <RADARR_ID> --language en --download --json",
                "skills/ingest-movie/run.sh scenes quality --subtitle <LOCAL_ENGLISH_SRT> --strict",
            ],
            "post_import_extraction_commands": [
                "skills/ingest-movie/run.sh scenes extract --subtitle <LOCAL_ENGLISH_SRT> --tag <EMOTION> --video <LOCAL_MOVIE_FILE> --clip-dir <CLIP_DIR> --output-json <SCENES_JSON>",
                "skills/ingest-movie/run.sh transcribe <CLIP_FILE> --subtitle <CLIP_SRT> --emotion <EMOTION> --movie-title " + json.dumps(title),
            ],
            "safe_default": "do_not_treat_as_training_ready_until_local_movie_audio_and_local_english_srt_are_verified",
        })
    return handoff


def subtitle_artifact_is_timecoded(path_value: Any) -> bool:
    if not path_value:
        return False
    path = Path(str(path_value))
    return path.suffix.lower() in {".srt", ".vtt", ".ass", ".ssa"} and path.exists()


def build_movie_acquisition_report(
    *,
    actor: str,
    genre: str | None,
    emotions: list[str],
    brave_query_count: int,
    candidate_count: int,
    external_subtitle_fetch_count: int,
    ingest_movie_handoff: list[dict[str, Any]],
    combined_coverage: dict[str, int],
    local_radarr_matches: list[dict[str, Any]] | None = None,
    ingest_movie_availability: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    recommendations: list[dict[str, Any]] = []
    report_coverage = {emotion: 0 for emotion in emotions}
    for handoff in ingest_movie_handoff:
        evidence = handoff.get("subtitle_evidence") or {}
        subtitle_path = evidence.get("subtitle_path")
        cue_windows = evidence.get("cue_windows") or []
        if not subtitle_artifact_is_timecoded(subtitle_path):
            continue
        if not cue_windows:
            continue
        cue_windows = [
            cue for cue in cue_windows
            if cue.get("timecode") is not None
            and cue.get("emotion") is not None
            and cue.get("start_seconds") is not None
            and cue.get("end_seconds") is not None
        ]
        if not cue_windows:
            continue
        emotion_counts: dict[str, int] = {}
        for cue in cue_windows:
            emotion = str(cue.get("emotion") or "")
            emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1
            report_coverage[emotion] = report_coverage.get(emotion, 0) + 1
        recommendations.append({
            "title": handoff.get("title"),
            "year": handoff.get("year"),
            "actor_query": handoff.get("actor_query") or actor,
            "scope": handoff.get("scope"),
            "recommendation_type": handoff.get("recommendation_type"),
            "requires_ingest_movie": handoff.get("requires_ingest_movie"),
            "required_profile": "Orpheus-TTS",
            "preferred_release_query": handoff.get("preferred_release_query"),
            "subtitle_path": subtitle_path,
            "subtitle_format": Path(str(subtitle_path)).suffix.lower().lstrip("."),
            "subtitle_exists": True,
            "verified_emotions": sorted(emotion_counts),
            "emotion_counts": emotion_counts,
            "cue_count": len(cue_windows),
            "timecoded_emotion_cues": cue_windows,
            "acquisition": handoff.get("nzbgeek_search"),
            "post_download_gates": handoff.get("post_import_required_checks"),
            "safe_default": handoff.get("safe_default"),
        })
    missing = [emotion for emotion in emotions if report_coverage.get(emotion, 0) == 0]
    availability = ingest_movie_availability or []
    local_matches = local_radarr_matches or []
    return {
        "artifact_type": "orpheus_tts_movie_acquisition_recommendations",
        "schema_version": "0.6",
        "status": "subtitle_vetted_recommendations_pending_movie_acquisition",
        "actor": actor,
        "genre": genre,
        "target_emotions": emotions,
        "brave_query_count": brave_query_count,
        "candidate_count": candidate_count,
        "external_subtitle_fetch_count": external_subtitle_fetch_count,
        "local_radarr_match_count": len(local_matches),
        "local_radarr_matches": local_matches,
        "ingest_movie_available_release_count": sum(1 for item in availability if item.get("release_found")),
        "ingest_movie_availability": availability,
        "recommendation_invariant": "For this pipeline, an Orpheus emotion exists only if it appears in a verified timecoded subtitle artifact (.srt/.vtt/.ass/.ssa). Each recommendation exposes exact cue timecodes in timecoded_emotion_cues.",
        "combined_emotion_coverage": report_coverage,
        "raw_combined_emotion_coverage": combined_coverage,
        "missing_emotions": missing,
        "movie_acquisition_recommendations": recommendations,
        "recommendation_count": len(recommendations),
        "not_training_ready_reason": "These recommendations are based on subtitle cue availability only. Movies must be acquired locally, English subtitles verified by Bazarr, then Watch must verify speaker/audio/clip quality before watch_orpheus_segments writes.",
    }


SUBTITLE_SOURCE_TERMS = {
    "subtitle",
    "subtitles",
    "srt",
    "vtt",
    "transcript",
    "caption",
    "captions",
    "opensubtitles",
    "subdl",
    "subscene",
    "yify subtitles",
}


def external_subtitle_probe_plan(
    candidates: list[dict[str, Any]],
    emotions: list[str],
    limit: int,
) -> list[dict[str, Any]]:
    probes: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        title = candidate.get("title")
        year = candidate.get("year")
        target_emotions = candidate.get("target_emotions") or emotions
        for emotion in target_emotions:
            aliases = EMOTION_MARKERS.get(emotion, [emotion])
            alias_query = " OR ".join([f'"{alias}"' for alias in aliases[:3]])
            probes.append({
                "candidate_index": index,
                "candidate": {"title": title, "year": year},
                "emotion": emotion,
                "query": f'"{title}" "{year}" subtitles SRT transcript {alias_query}',
            })
            if len(probes) >= limit:
                return probes
    return probes


def run_brave_batch(queries: list[str], workers: int, timeout_seconds: int) -> Any:
    process = subprocess.run(
        [str(BRAVE_RUN), "batch", "-f", "-", "-w", str(workers)],
        input=json.dumps(queries),
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    if process.returncode != 0:
        return {
            "status": "error",
            "reason": "brave_search_failed",
            "stderr": process.stderr[-1000:],
        }
    try:
        return json.loads(process.stdout)
    except json.JSONDecodeError:
        return {"raw_stdout": process.stdout[-4000:]}


def external_subtitle_evidence_from_results(
    probes: list[dict[str, Any]],
    results: Any,
) -> list[dict[str, Any]]:
    evidence_by_candidate: dict[tuple[str, str], dict[str, Any]] = {}
    if not isinstance(results, dict):
        return []
    for key, result in results.items():
        index_match = re.match(r"q(\d+)$", str(key))
        if not index_match:
            continue
        probe_index = int(index_match.group(1))
        if probe_index >= len(probes):
            continue
        probe = probes[probe_index]
        candidate = probe["candidate"]
        candidate_key = (str(candidate.get("title")), str(candidate.get("year")))
        entry = evidence_by_candidate.setdefault(candidate_key, {
            "candidate": candidate,
            "status": "external_subtitle_candidate_not_verified",
            "evidence_level": "external_search_snippet_only",
            "target_emotions": [],
            "evidence": [],
            "evidence_policy": "brave_snippets_are_not_subtitle_files",
            "safe_default": "do_not_recommend_movie_download_until_subtitle_file_is_downloaded_and_scanned",
        })
        emotion = probe["emotion"]
        if emotion not in entry["target_emotions"]:
            entry["target_emotions"].append(emotion)
        web_results = ((result or {}).get("web") or {}).get("results") or []
        aliases = EMOTION_MARKERS.get(emotion, [emotion])
        for web_result in web_results:
            haystack = " ".join([
                str(web_result.get("title", "")),
                str(web_result.get("description", "")),
                str(web_result.get("url", "")),
            ])
            haystack_lower = haystack.lower()
            has_subtitle_signal = any(term in haystack_lower for term in SUBTITLE_SOURCE_TERMS)
            has_emotion_signal = any(re.search(rf"\b{re.escape(alias)}(?:s|ing|ed)?\b", haystack_lower) for alias in aliases)
            if has_subtitle_signal or has_emotion_signal:
                entry["evidence"].append({
                    "emotion": emotion,
                    "query": probe["query"],
                    "has_subtitle_signal": has_subtitle_signal,
                    "has_emotion_signal": has_emotion_signal,
                    "title": web_result.get("title"),
                    "url": web_result.get("url"),
                    "description": web_result.get("description"),
                })
    return [
        entry for entry in evidence_by_candidate.values()
        if any(item.get("has_subtitle_signal") for item in entry["evidence"])
    ]


def handoff_actions(
    *,
    actor: str,
    emotions: list[str],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    emotion_values = emotions or ["target-emotion"]
    ingest_movie = []
    watch_subagent = []
    for candidate in candidates:
        title = candidate["title"]
        year = candidate["year"]
        ingest_movie.append({
            "movie": f"{title} ({year})",
            "reason": "Candidate from brave-search; acquire only if local Bazarr/Radarr inventory lacks verified English SRT coverage.",
            "commands": [
                f"skills/ingest-movie/run.sh search {json.dumps(title)}",
                "After acquisition: skills/get-subtitles/run.sh ensure-radarr --radarr-id <RADARR_ID> --language en --json",
            ],
            "must_verify": [
                "movie file exists",
                "English .srt exists beside movie file",
                "ingest-movie scenes quality --strict passes",
            ],
        })
        watch_subagent.append({
            "movie": f"{title} ({year})",
            "reason": "Once subtitle is verified, scan SRT cue markers for Orpheus coverage before video/Whisper work.",
            "commands": [
                f"skills/ingest-movie/run.sh scenes analyze --subtitle <{title}.en.srt> --output-json <report.json>",
                *[
                    f"skills/ingest-movie/run.sh scenes find --subtitle <{title}.en.srt> --tag {emotion_value}"
                    for emotion_value in emotion_values
                ],
            ],
            "must_report": [
                "count per Orpheus emotion tag",
                "missing target emotion tags",
                "rejected SRTs with no usable cue markers",
            ],
        })
    return {
        "ingest_movie_next_actions": ingest_movie,
        "watch_subagent_next_actions": watch_subagent,
        "if_no_candidates": {
            "status": "needs_more_discovery",
            "next": "Run additional brave-search genre/emotion queries before invoking ingest-movie.",
        },
    }


@app.command()
def discover(
    actor: str = typer.Option(..., "--actor", help="Actor/actress/person name."),
    genre: str | None = typer.Option(None, "--genre", help="Genre hint, e.g. comedy."),
    emotion: str | None = typer.Option(None, "--emotion", help="Orpheus emotion hint or comma list, e.g. laugh,chuckle."),
    all_orpheus_emotions: bool = typer.Option(False, "--all-orpheus-emotions", help="Search across all default Orpheus emotion tags."),
    count: int = typer.Option(3, "--count", min=1, max=10, help="Brave results per query."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Plan Brave queries without calling Brave."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Use brave-search to discover candidate movies; this does not verify subtitles."""
    emotions = parse_emotions(emotion, all_orpheus_emotions)
    queries = discovery_queries(actor, genre, emotions)
    if dry_run:
        planned_candidates: list[dict[str, Any]] = []
        emit({
            "status": "planned",
            "composed_skill": "brave-search",
            "queries": queries,
            "target_emotions": emotions,
            "movie_candidates": planned_candidates,
            "handoff": handoff_actions(actor=actor, emotions=emotions, candidates=planned_candidates),
            "safe_default": "candidate_discovery_only",
        }, json_output)
        return
    if not BRAVE_RUN.exists():
        emit({"status": "error", "reason": "brave_search_skill_missing", "path": str(BRAVE_RUN)}, json_output)
        raise typer.Exit(1)

    process = subprocess.run(
        [str(BRAVE_RUN), "batch", "-f", "-", "-w", "3"],
        input=json.dumps(queries),
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    if process.returncode != 0:
        emit({
            "status": "error",
            "composed_skill": "brave-search",
            "reason": "brave_search_failed",
            "stderr": process.stderr[-1000:],
        }, json_output)
        raise typer.Exit(1)

    try:
        results = json.loads(process.stdout)
    except json.JSONDecodeError:
        results = {"raw_stdout": process.stdout[-4000:]}
    candidates = extract_movie_candidates(results, actor)
    emit({
        "status": "ok",
        "composed_skill": "brave-search",
        "queries": queries,
        "target_emotions": emotions,
        "results": results,
        "movie_candidates": candidates,
        "handoff": handoff_actions(actor=actor, emotions=emotions, candidates=candidates),
        "safe_default": "candidate_discovery_only_until_bazarr_and_filesystem_verify_subtitles",
    }, json_output)


@app.command("orpheus-sanity")
def orpheus_sanity(
    actor: str = typer.Option(..., "--actor", help="Actor/actress/person name."),
    genre: str | None = typer.Option(None, "--genre", help="Genre hint, e.g. comedy."),
    emotion: str | None = typer.Option(None, "--emotion", help="Orpheus emotion hint or comma list."),
    all_orpheus_emotions: bool = typer.Option(True, "--all-orpheus-emotions/--targeted-emotions", help="Search all default Orpheus emotion tags."),
    download: bool = typer.Option(True, "--download/--no-download", help="Ask Bazarr to download missing English subtitles for local matches."),
    external_subtitle_probes: bool = typer.Option(True, "--external-subtitle-probes/--no-external-subtitle-probes", help="Search externally for subtitle/tag leads for non-local candidates; leads are not trusted until subtitle text is verified."),
    external_probe_limit: int = typer.Option(48, "--external-probe-limit", min=0, max=200, help="Maximum external subtitle/tag probe queries."),
    fetch_external_subtitles: bool = typer.Option(True, "--fetch-external-subtitles/--no-fetch-external-subtitles", help="Fetch subtitle/transcript URLs discovered by Brave and scan saved local artifacts."),
    max_external_fetches: int = typer.Option(8, "--max-external-fetches", min=0, max=100, help="Maximum external subtitle/transcript URLs to fetch and scan."),
    probe_nonlocal_bazarr: bool = typer.Option(True, "--probe-nonlocal-bazarr/--no-probe-nonlocal-bazarr", help="Try to vet non-local Brave candidates through Bazarr/Radarr metadata stubs."),
    create_radarr_stubs: bool = typer.Option(False, "--create-radarr-stubs/--no-create-radarr-stubs", help="Add unmonitored Radarr metadata stubs with searchForMovie=false so Bazarr can try provider search."),
    probe_ingest_movie_availability: bool = typer.Option(True, "--probe-ingest-movie-availability/--no-probe-ingest-movie-availability", help="Use ingest-movie/NZBGeek broad title-year search to report movie acquisition availability separately from subtitle evidence."),
    max_nonlocal_probes: int = typer.Option(5, "--max-nonlocal-probes", min=0, max=100, help="Maximum non-local Brave candidates to probe through Bazarr/Radarr."),
    bazarr_sync_wait_seconds: float = typer.Option(20.0, "--bazarr-sync-wait-seconds", min=0.0, max=180.0, help="Seconds to wait for Bazarr to see a newly added Radarr metadata stub."),
    count: int = typer.Option(3, "--count", min=1, max=10, help="Brave results per query."),
    candidate_limit: int = typer.Option(40, "--candidate-limit", min=1, max=200, help="Maximum candidate movie seeds to inspect locally."),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write final JSON artifact."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Run the Orpheus e2e sanity check for one actor, including Bazarr subtitle recovery."""
    if not isinstance(probe_ingest_movie_availability, bool):
        probe_ingest_movie_availability = True
    emotions = parse_emotions(emotion, all_orpheus_emotions)
    if not emotions:
        emotions = ORPHEUS_EMOTIONS
    queries = discovery_queries(actor, genre, emotions)
    if not BRAVE_RUN.exists():
        emit({"status": "error", "reason": "brave_search_skill_missing", "path": str(BRAVE_RUN)}, json_output)
        raise typer.Exit(1)

    process = subprocess.run(
        [str(BRAVE_RUN), "batch", "-f", "-", "-w", "6"],
        input=json.dumps(queries),
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )
    if process.returncode != 0:
        emit({
            "status": "error",
            "composed_skill": "brave-search",
            "reason": "brave_search_failed",
            "stderr": process.stderr[-1000:],
        }, json_output)
        raise typer.Exit(1)
    try:
        brave_results = json.loads(process.stdout)
    except json.JSONDecodeError:
        brave_results = {"raw_stdout": process.stdout[-4000:]}

    candidates = extract_movie_candidates_with_queries(
        brave_results,
        actor=actor,
        queries=queries,
        emotions=emotions,
        limit=candidate_limit,
    )
    external_subtitle_probe_receipt: dict[str, Any] = {
        "status": "not_run",
        "reason": "external_subtitle_probes_disabled",
        "queries": [],
        "candidates": [],
    }
    if external_subtitle_probes and candidates and external_probe_limit > 0:
        probes = external_subtitle_probe_plan(candidates, emotions, external_probe_limit)
        probe_results = run_brave_batch([probe["query"] for probe in probes], workers=6, timeout_seconds=180) if probes else {}
        external_candidates = external_subtitle_evidence_from_results(probes, probe_results)
        external_subtitle_probe_receipt = {
            "status": "external_search_leads_only",
            "evidence_policy": "brave_snippets_are_not_subtitle_files",
            "external_subtitle_download_supported": False,
            "external_subtitle_download_attempted": False,
            "external_subtitle_download_reason": "orpheus-sanity only uses Brave for discovery and Bazarr for local subtitle recovery; it does not download external subtitle files",
            "query_count": len(probes),
            "queries": probes,
            "candidates": external_candidates,
            "raw_results_included": False,
        }
    external_fetched_subtitle_scans: list[dict[str, Any]] = []
    if fetch_external_subtitles and max_external_fetches > 0:
        seen_urls: set[str] = set()
        fetch_jobs: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for item in external_subtitle_probe_receipt.get("candidates", []):
            candidate = {
                **(item.get("candidate") or {}),
                "target_emotions": item.get("target_emotions", []),
            }
            for evidence in item.get("evidence") or []:
                url = str(evidence.get("url") or "")
                if not url or url in seen_urls:
                    continue
                if not (evidence.get("has_subtitle_signal") or evidence.get("has_emotion_signal")):
                    continue
                seen_urls.add(url)
                fetch_jobs.append((candidate, evidence))
                if len(fetch_jobs) >= max_external_fetches:
                    break
            if len(fetch_jobs) >= max_external_fetches:
                break
        for candidate, evidence in fetch_jobs:
            fetch_receipt = fetch_external_subtitle_artifact(candidate, evidence)
            external_fetched_subtitle_scans.append(scan_external_artifact(fetch_receipt, emotions))
    local_matches: list[dict[str, Any]] = []
    local_radarr_matches: list[dict[str, Any]] = []
    radarr_ids: list[int] = []
    blocked_or_unverified: list[dict[str, Any]] = []
    nonlocal_candidates: list[dict[str, Any]] = []
    for candidate in candidates:
        radarr_records = radarr_inventory_matches_for_candidate(candidate)
        real_radarr_records = [record for record in radarr_records if record.get("status") == "radarr_inventory_match"]
        local_radarr_matches.extend(real_radarr_records)
        records = bazarr_local_matches_for_candidate(candidate)
        if not records:
            if real_radarr_records:
                blocked_or_unverified.append({
                    "candidate": candidate,
                    "status": "in_radarr_not_verified_by_bazarr",
                    "blocked_reason": "candidate is present in Radarr inventory but Bazarr has no indexed/verified subtitle record for it",
                    "radarr_matches": real_radarr_records,
                    "evidence_level": "radarr_metadata_or_file_only",
                    "next_required_evidence": "movie file and English subtitle must be verified by Bazarr/get-subtitles before Orpheus use",
                    "safe_default": "do_not_treat_as_local_orpheus_coverage",
                })
                for record in real_radarr_records:
                    if record.get("has_file") and record.get("radarr_id") is not None:
                        radarr_ids.append(int(record["radarr_id"]))
            else:
                nonlocal_candidates.append(candidate)
                blocked_or_unverified.append({
                    "candidate": candidate,
                    "status": "not_in_local_bazarr_inventory",
                    "blocked_reason": "candidate found by Brave but not present in local Radarr/Bazarr inventory",
                    "evidence_level": "movie_candidate_only",
                    "next_required_evidence": "download and scan a real subtitle file before recommending movie acquisition",
                    "safe_default": "do_not_recommend_movie_download",
                })
            continue
        if records and records[0].get("status") == "bazarr_lookup_failed":
            blocked_or_unverified.append({
                "candidate": candidate,
                "status": "bazarr_lookup_failed",
                "blocked_reason": records[0].get("reason"),
                "radarr_matches": real_radarr_records,
                "safe_default": "do_not_treat_as_local_orpheus_coverage",
            })
            continue
        for record in records:
            radarr_id = record.get("radarrId") or record.get("radarr_id")
            match = {
                "candidate": candidate,
                "radarr_id": radarr_id,
                "title": record.get("title"),
                "year": record.get("year"),
                "path": record.get("path"),
                "scene_name": record.get("sceneName"),
            }
            local_matches.append(match)
            if radarr_id is not None:
                radarr_ids.append(int(radarr_id))

    ingest_movie_availability: list[dict[str, Any]] = []
    if probe_ingest_movie_availability:
        for candidate in candidates:
            ingest_movie_availability.append(ingest_movie_release_availability_for_candidate(candidate))

    nonlocal_bazarr_subtitle_vetting: list[dict[str, Any]] = []
    if probe_nonlocal_bazarr and max_nonlocal_probes > 0:
        for candidate in nonlocal_candidates[:max_nonlocal_probes]:
            try:
                nonlocal_bazarr_subtitle_vetting.append(bazarr_nonlocal_subtitle_probe(
                    candidate,
                    create_radarr_stub=create_radarr_stubs,
                    sync_wait_seconds=bazarr_sync_wait_seconds,
                ))
            except Exception as exc:
                nonlocal_bazarr_subtitle_vetting.append({
                    "candidate": candidate,
                    "status": "not_vetted",
                    "reason": f"nonlocal_bazarr_probe_failed:{type(exc).__name__}",
                    "safe_default": "do_not_recommend_movie_download",
                })

    async def scan_local() -> list[dict[str, Any]]:
        tasks = [
            asyncio.create_task(ensure_and_scan_one(radarr_id, "en", emotions, download))
            for radarr_id in sorted(set(radarr_ids))
        ]
        results: list[dict[str, Any]] = []
        for task in asyncio.as_completed(tasks):
            results.append(await task)
        return results

    scan_results = asyncio.run(scan_local()) if radarr_ids else []
    coverage = {emotion_name: 0 for emotion_name in emotions}
    subtitle_hits: list[dict[str, Any]] = []
    local_verified_hits: list[dict[str, Any]] = []
    verified_subtitles: list[dict[str, Any]] = []
    for result in scan_results:
        receipt = result.get("subtitle_receipt") or {}
        if receipt.get("status") == "verified":
            verified_subtitles.extend(receipt.get("subtitle_files") or [])
        scan = result.get("scan") or {}
        for emotion_name, count_value in (scan.get("counts") or {}).items():
            coverage[emotion_name] = coverage.get(emotion_name, 0) + count_value
        for match in scan.get("matches") or []:
            subtitle_hits.append({
                "radarr_id": result.get("radarr_id"),
                "movie_title": receipt.get("movie_title"),
                "movie_year": receipt.get("movie_year"),
                "subtitle_path": receipt.get("subtitle_path"),
                "subtitle_format": receipt.get("primary_subtitle_format"),
                **match,
            })
            local_verified_hits.append({
                "radarr_id": result.get("radarr_id"),
                "movie_title": receipt.get("movie_title"),
                "movie_year": receipt.get("movie_year"),
                "subtitle_path": receipt.get("subtitle_path"),
                "subtitle_format": receipt.get("primary_subtitle_format"),
                **match,
            })
        if receipt.get("status") != "verified":
            matching_candidates = [
                item["candidate"] for item in local_matches
                if item.get("radarr_id") == result.get("radarr_id")
            ]
            blocked_or_unverified.append({
                "radarr_id": result.get("radarr_id"),
                "status": "local_movie_without_verified_english_subtitle",
                "subtitle_receipt": receipt,
                "candidates": matching_candidates,
            })

    missing_emotions = [emotion_name for emotion_name, count_value in coverage.items() if count_value == 0]
    external_coverage = {emotion_name: 0 for emotion_name in emotions}
    external_verified_hits: list[dict[str, Any]] = []
    external_untimed_hits: list[dict[str, Any]] = []
    for item in external_fetched_subtitle_scans:
        fetch_receipt = item.get("fetch") or {}
        scan = item.get("scan") or {}
        if item.get("status") != "scanned":
            continue
        has_timecodes = bool(fetch_receipt.get("has_timecodes"))
        if has_timecodes:
            for emotion_name, count_value in (scan.get("counts") or {}).items():
                external_coverage[emotion_name] = external_coverage.get(emotion_name, 0) + count_value
        for match in scan.get("matches") or []:
            candidate = fetch_receipt.get("candidate") or {}
            hit = {
                "movie_title": candidate.get("title"),
                "movie_year": candidate.get("year"),
                "subtitle_path": fetch_receipt.get("artifact_path"),
                "subtitle_format": fetch_receipt.get("format"),
                "source_url": fetch_receipt.get("source_url"),
                "final_url": fetch_receipt.get("final_url"),
                "has_timecodes": has_timecodes,
                **match,
            }
            if has_timecodes:
                external_verified_hits.append(hit)
            else:
                external_untimed_hits.append(hit)
    combined_coverage = {
        emotion_name: coverage.get(emotion_name, 0) + external_coverage.get(emotion_name, 0)
        for emotion_name in emotions
    }
    combined_missing_emotions = [emotion_name for emotion_name, count_value in combined_coverage.items() if count_value == 0]
    vetted_download_recommendations: list[dict[str, Any]] = []
    for result in scan_results:
        scan = result.get("scan") or {}
        receipt = result.get("subtitle_receipt") or {}
        if scan.get("matches"):
            vetted_download_recommendations.append({
                "movie": f"{receipt.get('movie_title')} ({receipt.get('movie_year')})",
                "reason": "Verified local subtitle file contains Orpheus cue tags. If not already downloaded in usable quality, download/reacquire this movie through Orpheus-TTS profile.",
                "radarr_id": result.get("radarr_id"),
                "subtitle_path": receipt.get("subtitle_path"),
                "verified_emotions": sorted({match["emotion"] for match in scan.get("matches", [])}),
                "cue_count": len(scan.get("matches", [])),
                "safe_default": "usable_only_after_local_media_and_subtitle_are_verified",
            })
    nonlocal_movie_download_recommendations: list[dict[str, Any]] = []
    for item in external_fetched_subtitle_scans:
        fetch_receipt = item.get("fetch") or {}
        scan = item.get("scan") or {}
        matches = scan.get("matches") or []
        if not matches or not fetch_receipt.get("has_timecodes"):
            continue
        candidate = fetch_receipt.get("candidate") or {}
        title = candidate.get("title")
        year = candidate.get("year")
        nonlocal_movie_download_recommendations.append({
            "movie": f"{title} ({year})" if year else str(title),
            "reason": "Fetched external subtitle artifact contains timecoded Orpheus cue tags. Acquire movie through Orpheus-TTS profile, then verify local subtitles after import.",
            "target_emotions": candidate.get("target_emotions", []),
            "verified_emotions": sorted({match["emotion"] for match in matches}),
            "cue_count": len(matches),
            "subtitle_path": fetch_receipt.get("artifact_path"),
            "source_url": fetch_receipt.get("source_url"),
            "final_url": fetch_receipt.get("final_url"),
            "evidence_level": "external_subtitle_file_fetched_and_scanned_with_timecodes",
            "safe_default": "acquisition_queue_candidate_then_verify_local_subtitle_after_ingest",
        })
    for probe in nonlocal_bazarr_subtitle_vetting:
        provider_probe = probe.get("provider_probe") or {}
        if provider_probe.get("provider_count", 0) > 0:
            candidate = probe.get("candidate") or {}
            title = candidate.get("title")
            year = candidate.get("year")
            nonlocal_movie_download_recommendations.append({
                "movie": f"{title} ({year})" if year else str(title),
                "reason": "Bazarr provider search found subtitle candidates for this non-local movie metadata record. Download the movie only through Orpheus-TTS profile, then download and scan the subtitle text before using it for Orpheus.",
                "target_emotions": candidate.get("target_emotions", []),
                "radarr_id": (probe.get("radarr_stub") or {}).get("radarr_id"),
                "provider_count": provider_probe.get("provider_count", 0),
                "evidence_level": "bazarr_provider_available_subtitle_text_not_scanned",
                "safe_default": "recommend_for_acquisition_queue_only_not_orpheus_training",
            })
    local_movie_recommendations = [
        {
            **recommendation,
            "scope": "local",
            "recommendation_type": "local_verified_subtitle_hit",
            "requires_ingest_movie": False,
        }
        for recommendation in vetted_download_recommendations
    ]
    nonlocal_movie_recommendations = [
        {
            **recommendation,
            "scope": "nonlocal",
            "recommendation_type": "acquisition_candidate",
            "requires_ingest_movie": True,
        }
        for recommendation in nonlocal_movie_download_recommendations
    ]
    unified_movie_recommendations = [
        *local_movie_recommendations,
        *nonlocal_movie_recommendations,
    ]
    ingest_movie_handoff_recommendations = [
        recommendation for recommendation in unified_movie_recommendations
        if recommendation.get("subtitle_path")
    ]
    ingest_movie_handoff = build_ingest_movie_handoff(
        recommendations=ingest_movie_handoff_recommendations,
        verified_hits=[*local_verified_hits, *external_verified_hits],
        actor=actor,
    )
    movie_acquisition_report = build_movie_acquisition_report(
        actor=actor,
        genre=genre,
        emotions=emotions,
        brave_query_count=len(queries),
        candidate_count=len(candidates),
        external_subtitle_fetch_count=len(external_fetched_subtitle_scans),
        ingest_movie_handoff=ingest_movie_handoff,
        combined_coverage=combined_coverage,
        local_radarr_matches=local_radarr_matches,
        ingest_movie_availability=ingest_movie_availability,
    )
    final = {
        "status": "ok",
        "mode": "subtitle_discovery_bazarr_local_recovery_nonlocal_bazarr_probe",
        "movie_acquisition_report": movie_acquisition_report,
        "actor": actor,
        "genre": genre,
        "target_emotions": emotions,
        "bazarr_download_enabled": download,
        "bazarr_download_attempted": bool(radarr_ids and download),
        "bazarr_download_radarr_ids": sorted(set(radarr_ids)) if download else [],
        "nonlocal_bazarr_probe_enabled": probe_nonlocal_bazarr,
        "nonlocal_bazarr_probe_count": len(nonlocal_bazarr_subtitle_vetting),
        "nonlocal_radarr_stub_creation_enabled": create_radarr_stubs,
        "ingest_movie_availability_probe_enabled": probe_ingest_movie_availability,
        "ingest_movie_availability": ingest_movie_availability,
        "ingest_movie_available_release_count": sum(1 for item in ingest_movie_availability if item.get("release_found")),
        "external_subtitle_download_supported": True,
        "external_subtitle_download_attempted": bool(fetch_external_subtitles and external_fetched_subtitle_scans),
        "external_subtitle_download_reason": "external Brave result URLs are fetched directly when supported; Bazarr remains the verifier/downloader for local movies",
        "external_subtitle_fetch_enabled": fetch_external_subtitles,
        "external_subtitle_fetch_count": len(external_fetched_subtitle_scans),
        "composed_skill": "brave-search",
        "brave_query_count": len(queries),
        "brave_queries": queries,
        "candidate_movies": candidates,
        "candidate_count": len(candidates),
        "local_bazarr_matches": local_matches,
        "local_bazarr_match_count": len(local_matches),
        "local_radarr_matches": local_radarr_matches,
        "local_radarr_match_count": len(local_radarr_matches),
        "verified_subtitles": verified_subtitles,
        "local_verified_hits": local_verified_hits,
        "local_bazarr_recovery": scan_results,
        "nonlocal_bazarr_subtitle_vetting": nonlocal_bazarr_subtitle_vetting,
        "external_subtitle_candidates": external_subtitle_probe_receipt,
        "external_fetched_subtitle_scans": external_fetched_subtitle_scans,
        "external_verified_hits": external_verified_hits,
        "external_untimed_hits": external_untimed_hits,
        "movie_recommendations": unified_movie_recommendations,
        "movie_recommendation_count": len(unified_movie_recommendations),
        "local_movie_recommendations": local_movie_recommendations,
        "local_movie_recommendation_count": len(local_movie_recommendations),
        "nonlocal_movie_recommendation_count": len(nonlocal_movie_recommendations),
        "ingest_movie_handoff": ingest_movie_handoff,
        "ingest_movie_handoff_count": len(ingest_movie_handoff),
        "movie_download_recommendations": vetted_download_recommendations,
        "nonlocal_movie_download_recommendations": nonlocal_movie_download_recommendations,
        "emotion_coverage": coverage,
        "external_emotion_coverage": external_coverage,
        "combined_emotion_coverage": combined_coverage,
        "missing_emotions": missing_emotions,
        "unfound_emotion_tags": combined_missing_emotions,
        "subtitle_hits": subtitle_hits,
        "blocked_or_unverified_candidates": blocked_or_unverified,
        "recommended_ingest_movie_actions": ingest_movie_handoff,
        "unvetted_external_leads": external_subtitle_probe_receipt.get("candidates", []),
        "recommendation_policy": "movie_download_recommendations require verified local subtitle files; nonlocal_movie_download_recommendations require fetched external subtitle/transcript artifacts scanned for Orpheus tags and remain acquisition-queue only until local post-ingest verification",
        "safe_default": "only_verified_subtitle_hits_can_feed_watch_or_orpheus",
        "generated_at": int(time.time()),
    }
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        final["output_path"] = str(output)
        output.write_text(json.dumps(final, indent=2, sort_keys=True), encoding="utf-8")
    emit(final, json_output)


if __name__ == "__main__":
    app()
