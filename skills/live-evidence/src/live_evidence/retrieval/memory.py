"""Graph Memory and indexed-code retrieval through supported boundaries.

This client never imports ArangoDB or Qdrant. General recall uses the Memory HTTP
service; code navigation uses the sibling memory skill runner so Graph Memory
retains source-lifecycle and freshness authority.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path
from time import monotonic
from typing import Any

import httpx
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from ..config import AppSettings, InterviewProfile
from ..models import EvidenceSource, Freshness, RetrievalLane
from ..trigger import search_terms


class FlexibleMemoryResponse(BaseModel):
    """Minimal validated shell around evolving Memory response payloads."""

    model_config = ConfigDict(extra="allow")

    found: bool | None = None
    items: list[dict[str, Any]] = Field(default_factory=list)
    results: list[dict[str, Any]] = Field(default_factory=list)


class FlexibleIntentResponse(BaseModel):
    """Minimal validated shell around the Memory intent product."""

    model_config = ConfigDict(extra="allow")

    recall_profile: str | dict[str, Any] | None = None


class MemoryRetrievalResult(BaseModel):
    """One lane result with explicit degradation."""

    sources: list[EvidenceSource] = Field(default_factory=list)
    latency_ms: int = Field(ge=0)
    detail: str
    ok: bool


class MemoryEvidenceClient:
    """Retrieve broad memory and exact code evidence."""

    def __init__(self, settings: AppSettings, profile: InterviewProfile) -> None:
        self._settings = settings
        self._profile = profile
        self._timeout = httpx.Timeout(
            connect=min(2.0, settings.request_timeout_s),
            read=settings.request_timeout_s,
            write=min(3.0, settings.request_timeout_s),
            pool=min(2.0, settings.request_timeout_s),
        )

    async def retrieve(self, query: str) -> MemoryRetrievalResult:
        """Run bounded hybrid recall and code search concurrently."""

        started = monotonic()
        recall_task = asyncio.create_task(self._recall(query))
        code_task = asyncio.create_task(self._code_search(query))
        recall_sources, recall_detail = await recall_task
        code_sources, code_detail = await code_task
        sources = _dedupe_sources([*recall_sources, *code_sources])
        latency_ms = int((monotonic() - started) * 1000)
        details = [detail for detail in (recall_detail, code_detail) if detail]
        ok = bool(sources)
        return MemoryRetrievalResult(
            sources=sources,
            latency_ms=latency_ms,
            detail="; ".join(details)[:300] or ("No results" if not ok else "Memory ready"),
            ok=ok,
        )

    async def _recall(self, query: str) -> tuple[list[EvidenceSource], str]:
        selected_profile = await self._intent_profile(query)
        profiles = _unique_text(
            [
                selected_profile or "",
                "procedural_memory",
                "temporal_project_state",
            ]
        )
        payloads = await asyncio.gather(
            *(self._post_recall(query, profile) for profile in profiles),
            return_exceptions=True,
        )
        sources: list[EvidenceSource] = []
        errors: list[str] = []
        for profile, payload in zip(profiles, payloads, strict=True):
            if isinstance(payload, Exception):
                errors.append(f"{profile}:{_exception_summary(payload)}")
                continue
            sources.extend(_memory_items_to_sources(payload, profile, self._profile))
        route = f"intent={selected_profile}" if selected_profile else "intent=degraded"
        if sources:
            return sources, f"Hybrid recall {len(sources)} ({route})"
        return [], "Memory unavailable or no grounded result" + (
            f" ({route}; {', '.join(errors)})" if errors else f" ({route})"
        )

    async def _intent_profile(self, query: str) -> str | None:
        """Ask Memory to select a recall profile without making it mandatory."""

        url = f"{self._settings.memory_url}/intent"
        request = {"q": query, "fast": True, "app": "live-evidence"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout, trust_env=False) as client:
                response = await client.post(
                    url,
                    json=request,
                    headers={"X-Caller-Skill": "live-evidence"},
                )
                if response.status_code in {400, 404, 422}:
                    return None
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError):
            return None
        if not isinstance(payload, dict):
            return None
        validated = FlexibleIntentResponse.model_validate(payload)
        candidate = validated.recall_profile
        if isinstance(candidate, dict):
            candidate = candidate.get("name")
        if not isinstance(candidate, str):
            return None
        clean = candidate.strip().casefold()
        if not clean or len(clean) > 80 or not clean.replace("_", "").isalnum():
            return None
        return clean

    async def _post_recall(self, query: str, profile: str) -> dict[str, Any]:
        url = f"{self._settings.memory_url}/recall"
        request = {
            "q": query,
            "recall_profile": profile,
            "k": 6,
            "scope": "",
            "collections": self._profile.memory_collections,
        }
        async with httpx.AsyncClient(timeout=self._timeout, trust_env=False) as client:
            response = await client.post(url, json=request, headers={"X-Caller-Skill": "live-evidence"})
            if response.status_code in {400, 404, 422}:
                fallback = await client.post(
                    url,
                    json={
                        "q": query,
                        "k": 8,
                        "collections": self._profile.memory_collections,
                    },
                    headers={"X-Caller-Skill": "live-evidence"},
                )
                fallback.raise_for_status()
                return _validated_payload(fallback.json())
            response.raise_for_status()
            return _validated_payload(response.json())

    async def _code_search(self, query: str) -> tuple[list[EvidenceSource], str]:
        runner = self._settings.memory_runner
        if runner is None:
            return [], "Memory code runner not configured"
        queries = _code_queries(query, self._profile)
        if not queries:
            return [], "No code-navigation terms"
        results = await asyncio.gather(
            *(asyncio.to_thread(self._code_search_one_sync, runner, term) for term in queries),
            return_exceptions=True,
        )
        sources: list[EvidenceSource] = []
        symbol_ids: list[str] = []
        errors = 0
        for result in results:
            if isinstance(result, Exception):
                errors += 1
                continue
            term_sources, term_symbol_ids = result
            sources.extend(term_sources)
            symbol_ids.extend(term_symbol_ids)
        sources = _dedupe_sources(sources)
        if symbol_ids:
            node = await asyncio.to_thread(self._code_node_sync, runner, symbol_ids[0])
            if node is not None:
                sources.insert(0, node)
                sources = _dedupe_sources(sources)
        if not sources:
            detail = "Indexed code returned no exact source"
            if errors:
                detail += f"; {errors} query error(s)"
            return [], detail
        return sources, f"Indexed code {len(sources)} across {len(queries)} term(s)"

    def _code_search_one_sync(
        self,
        runner: Path,
        query: str,
    ) -> tuple[list[EvidenceSource], list[str]]:
        command = [str(runner), "code-search", "--q", query, "--limit", "4"]
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self._settings.subprocess_timeout_s,
                env=_subprocess_env(),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning("memory code search degraded: {}", type(exc).__name__)
            return [], []
        if result.returncode != 0:
            return [], []
        payload = _parse_json_output(result.stdout)
        items = payload.get("items", []) if isinstance(payload, dict) else []
        sources: list[EvidenceSource] = []
        symbol_ids: list[str] = []
        for item in items[:4]:
            if not isinstance(item, dict) or not _code_item_allowed(item, self._profile):
                continue
            source = _code_item_to_source(item)
            if source is not None:
                sources.append(source)
            symbol_id = str(item.get("symbol_id") or item.get("stable_id") or "").strip()
            if symbol_id:
                symbol_ids.append(symbol_id)
        return sources, symbol_ids

    def _code_node_sync(self, runner: Path, symbol_id: str) -> EvidenceSource | None:
        command = [str(runner), "code-node", "--symbol-id", symbol_id, "--source"]
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self._settings.subprocess_timeout_s,
                env=_subprocess_env(),
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0:
            return None
        payload = _parse_json_output(result.stdout)
        if not isinstance(payload, dict) or payload.get("status") != "ok":
            return None
        symbol = payload.get("symbol") if isinstance(payload.get("symbol"), dict) else {}
        source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
        freshness_payload = payload.get("freshness") if isinstance(payload.get("freshness"), dict) else {}
        excerpt = str(source.get("text") or symbol.get("qualified_name") or "").strip()
        path = str(source.get("path") or symbol.get("path") or "").strip()
        if not excerpt or not path:
            return None
        freshness = (
            Freshness.CURRENT
            if freshness_payload.get("status") == "current"
            else Freshness.STALE
            if freshness_payload.get("status") == "stale"
            else Freshness.UNKNOWN
        )
        return EvidenceSource(
            lane=RetrievalLane.CODE,
            label=str(symbol.get("qualified_name") or symbol.get("symbol_name") or path),
            excerpt=excerpt[:4_000],
            score=0.94 if freshness is Freshness.CURRENT else 0.62,
            freshness=freshness,
            repository=_optional_text(symbol.get("repository")),
            branch=_optional_text(symbol.get("branch")),
            path=path,
            line_start=_optional_int(source.get("start_line")),
            line_end=_optional_int(source.get("end_line")),
            metadata={
                "symbol_id": symbol.get("symbol_id"),
                "indexed_hash": freshness_payload.get("indexed_hash"),
                "current_hash": freshness_payload.get("current_hash"),
            },
        )


def _validated_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Memory response must be a JSON object")
    FlexibleMemoryResponse.model_validate(value)
    return value


def _exception_summary(exc: Exception) -> str:
    message = str(exc).strip()
    if not message:
        return type(exc).__name__
    return f"{type(exc).__name__}({message[:160]})"


def _subprocess_env() -> dict[str, str]:
    env = dict(os.environ)
    for key in (
        "VIRTUAL_ENV",
        "UV_PROJECT_ENVIRONMENT",
        "PYTHONHOME",
        "PYTHONPATH",
    ):
        env.pop(key, None)
    env.setdefault("UV_LINK_MODE", "copy")
    return env


def _parse_json_output(stdout: str) -> dict[str, Any]:
    text = stdout.strip()
    if not text:
        return {}
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return {}
        try:
            value = json.loads(text[start : end + 1])
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            return {}


def _memory_items_to_sources(
    payload: dict[str, Any],
    profile: str,
    interview_profile: InterviewProfile,
) -> list[EvidenceSource]:
    candidates = payload.get("items") or payload.get("results") or payload.get("memories") or []
    if not isinstance(candidates, list):
        return []
    sources: list[EvidenceSource] = []
    for item in candidates[:8]:
        if not isinstance(item, dict) or not _memory_item_allowed(item, interview_profile):
            continue
        excerpt = _first_text(item, "solution", "text", "answer", "content", "problem")
        path = _first_text(item, "path", "source_path", "file_path")
        repository = _first_text(item, "repo", "repository", "project")
        url = _first_text(item, "url", "source_url")
        key = _first_text(item, "_key", "key", "id")
        if not excerpt or not any((path, repository, url, key)):
            continue
        raw_score = item.get("score", item.get("combined_score", item.get("relevance", 0.55)))
        score = _bounded_score(raw_score)
        sources.append(
            EvidenceSource(
                lane=RetrievalLane.MEMORY,
                label=_first_text(item, "problem", "title", "name") or f"Memory · {profile}",
                excerpt=excerpt[:4_000],
                score=score,
                freshness=Freshness.UNKNOWN,
                repository=repository or None,
                branch=_first_text(item, "branch") or None,
                commit=_first_text(item, "commit", "source_commit") or None,
                path=path or None,
                line_start=_optional_int(item.get("start_line")),
                line_end=_optional_int(item.get("end_line")),
                url=url or None,
                metadata={"_key": key or None, "profile": profile, "tags": item.get("tags", [])},
            )
        )
    return sources


def _memory_item_allowed(item: dict[str, Any], profile: InterviewProfile) -> bool:
    """Fail closed on explicit restricted tags, visibility, or source paths."""

    visibility = _first_text(item, "visibility", "classification", "access")
    if visibility.casefold() in {"private", "confidential", "restricted", "secret"}:
        return False
    raw_tags = item.get("tags", [])
    if isinstance(raw_tags, str):
        tags = {raw_tags.casefold()}
    elif isinstance(raw_tags, list):
        tags = {str(tag).casefold() for tag in raw_tags}
    else:
        tags = set()
    if tags.intersection(tag.casefold() for tag in profile.blocked_tags):
        return False
    path = _first_text(item, "path", "source_path", "file_path").replace("\\", "/").casefold()
    return not any(fragment.casefold() in path for fragment in profile.blocked_path_fragments)


def _code_item_allowed(item: dict[str, Any], profile: InterviewProfile) -> bool:
    """Limit indexed-code evidence to the profile's declared repository set."""

    if not profile.repo_priorities:
        return True
    repository = _first_text(item, "repository", "repo", "project").casefold()
    if not repository:
        return False
    allowed = {value.casefold() for value in profile.repo_priorities}
    return repository in allowed or repository.rsplit("/", 1)[-1] in allowed


def _code_item_to_source(item: dict[str, Any]) -> EvidenceSource | None:
    path = _first_text(item, "path", "file_path")
    qualified = _first_text(item, "qualified_name", "symbol_name", "name")
    if not path or not qualified:
        return None
    return EvidenceSource(
        lane=RetrievalLane.CODE,
        label=qualified,
        excerpt=f"Indexed symbol {qualified} in {path}",
        score=0.74,
        freshness=Freshness.UNKNOWN,
        repository=_first_text(item, "repository", "repo") or None,
        branch=_first_text(item, "branch") or None,
        path=path,
        line_start=_optional_int(item.get("start_line")),
        line_end=_optional_int(item.get("end_line")),
        metadata={"symbol_id": item.get("symbol_id") or item.get("stable_id")},
    )


def _code_queries(query: str, profile: InterviewProfile) -> list[str]:
    """Select a few exact lexical anchors for GMO code navigation."""

    lower = query.casefold()
    matched_projects = [
        project
        for project, aliases in profile.project_aliases.items()
        if any(alias.casefold() in lower for alias in [project, *aliases])
    ]
    matched_watch = [term for term in profile.watch_terms if term.casefold() in lower]
    return _unique_text([*matched_projects, *matched_watch, *search_terms(query, limit=5)])[:3]


def _unique_text(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = " ".join(str(value).split())
        key = clean.casefold()
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return result


def _first_text(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())
    return ""


def _optional_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _optional_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 1 else None


def _bounded_score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.55
    if score > 1.0:
        score = score / 100.0 if score <= 100 else 1.0
    return max(0.0, min(1.0, score))


def _dedupe_sources(sources: list[EvidenceSource]) -> list[EvidenceSource]:
    seen: set[tuple[str, str, str]] = set()
    result: list[EvidenceSource] = []
    for source in sorted(sources, key=lambda item: item.score, reverse=True):
        key = (
            source.repository or "",
            source.path or source.url or str(source.metadata.get("_key") or ""),
            source.excerpt[:120].casefold(),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(source)
    return result[:10]
