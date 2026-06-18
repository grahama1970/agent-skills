"""Recall previously watched video records from memory.

Input: a natural-language question about a watched video.
Output: the memory `/recall` response scoped to `watch_content`.
Failure modes: memory daemon connection errors or weak recall are returned to
callers as ordinary response metadata; callers should ask clarification instead
of inventing video facts when recall misses.
"""
from __future__ import annotations

import httpx
import importlib.util
from pathlib import Path


MEMORY_BASE_URL = "http://127.0.0.1:8601"
WATCH_COLLECTION = "watch_content"
SKILLS_DIR = Path(__file__).resolve().parents[2]
BRAVE_SEARCH_SCRIPT = SKILLS_DIR / "brave-search" / "brave_search.py"


def recall_video_question(
    question: str,
    k: int = 5,
    timeout: float = 10.0,
    *,
    media_title: str | None = None,
    media_key: str | None = None,
    media_slug: str | None = None,
    extra_tags: list[str] | None = None,
    strict_media: bool = True,
) -> dict:
    """Ask memory a natural-language question about watched video content."""
    if not question or not question.strip():
        raise ValueError("question must be non-empty")
    tags = []
    if media_slug:
        tags.append(media_slug)
    tags.extend(extra_tags or [])
    payload = {"q": question.strip(), "collections": [WATCH_COLLECTION], "k": k}
    if tags:
        payload["tags"] = tags
    with httpx.Client(base_url=MEMORY_BASE_URL, timeout=httpx.Timeout(timeout, connect=2.0)) as client:
        response = client.post(
            "/recall",
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
    data.setdefault("items", [])
    data["media_filter"] = {
        "media_title": media_title,
        "media_key": media_key,
        "media_slug": media_slug,
        "extra_tags": extra_tags or [],
        "strict": strict_media,
    }
    if media_title or media_key or media_slug:
        original_items = list(data["items"])
        matched = [
            item for item in original_items
            if _matches_media(item, media_title=media_title, media_key=media_key, media_slug=media_slug)
        ]
        data["items"] = matched
        data["wrong_media_items"] = [
            _item_summary(item) for item in original_items
            if not _matches_media(item, media_title=media_title, media_key=media_key, media_slug=media_slug)
        ]
        data["media_match_count"] = len(matched)
        if strict_media and not matched:
            data["found"] = False
            data["should_scan"] = False
            data["failure"] = "wrong_media_or_missing_media_match"
    return data


def corroborate_movie_question(question: str, movie_title: str | None = None, count: int = 5) -> dict:
    """Use Brave Search to corroborate expected public movie facts."""
    query = _movie_query(question, movie_title)
    try:
        brave = _load_brave_search_client()
        result = brave.web_search(query, count=count)
    except Exception as exc:
        return {"available": False, "query": query, "error": str(exc), "results": []}
    return {"available": True, "query": query, "results": result.get("results", [])}


def ask_movie_question(
    question: str,
    movie_title: str | None = None,
    *,
    use_brave: bool = True,
    k: int = 5,
    media_key: str | None = None,
    media_slug: str | None = None,
    extra_tags: list[str] | None = None,
) -> dict:
    """Return watched-video recall plus optional Brave corroboration."""
    recall = recall_video_question(
        question,
        k=k,
        media_title=movie_title,
        media_key=media_key,
        media_slug=media_slug,
        extra_tags=extra_tags,
    )
    corroboration = corroborate_movie_question(question, movie_title, count=k) if use_brave else None
    status = "verified" if recall.get("found") and recall.get("items") else "missing_extraction"
    if recall.get("failure"):
        status = recall["failure"]
    return {
        "question": question,
        "movie_title": movie_title,
        "watch_recall": recall,
        "brave_corroboration": corroboration,
        "status": status,
        "answer_contract": "answer from watch_recall evidence; use Brave only to corroborate expected public facts",
    }


def _movie_query(question: str, movie_title: str | None) -> str:
    if movie_title and movie_title.strip():
        return f'{movie_title.strip()} movie {question.strip()}'
    return f"movie {question.strip()}"


def _load_brave_search_client():
    if not BRAVE_SEARCH_SCRIPT.exists():
        raise RuntimeError(f"brave-search script not found: {BRAVE_SEARCH_SCRIPT}")
    spec = importlib.util.spec_from_file_location("watch_brave_search", BRAVE_SEARCH_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load brave-search module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _matches_media(
    item: dict,
    *,
    media_title: str | None = None,
    media_key: str | None = None,
    media_slug: str | None = None,
) -> bool:
    if media_key and item.get("_key") == media_key:
        return True
    if media_slug and _tag_contains(item.get("tags"), media_slug):
        return True
    if media_slug and media_slug in str(item.get("frame_dir", "")).lower():
        return True
    if media_title:
        wanted = _norm(media_title)
        title = _norm(str(item.get("title", "")))
        source = _norm(str(item.get("source", "")))
        if wanted and (wanted in title or wanted in source or title in wanted):
            return True
        if _title_tokens_match(media_title, str(item.get("title", ""))) or _title_tokens_match(media_title, str(item.get("source", ""))):
            return True
    return not (media_title or media_key or media_slug)


def _tag_contains(tags: object, wanted: str) -> bool:
    wanted_norm = _norm(wanted)
    if isinstance(tags, list):
        return any(_norm(str(tag)) == wanted_norm for tag in tags)
    if isinstance(tags, str):
        return wanted_norm in _norm(tags)
    return False


def _norm(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _title_tokens_match(wanted: str, candidate: str) -> bool:
    wanted_tokens = [t for t in _tokens(wanted) if not (len(t) == 4 and t.isdigit())]
    candidate_tokens = set(_tokens(candidate))
    if not wanted_tokens:
        return False
    return all(token in candidate_tokens for token in wanted_tokens)


def _tokens(value: str) -> list[str]:
    token = ""
    tokens: list[str] = []
    for ch in value.lower():
        if ch.isalnum():
            token += ch
        elif token:
            tokens.append(token)
            token = ""
    if token:
        tokens.append(token)
    return tokens


def _item_summary(item: dict) -> dict:
    return {
        "_key": item.get("_key"),
        "title": item.get("title"),
        "source": item.get("source"),
        "scores": item.get("scores"),
    }
