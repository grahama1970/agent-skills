"""Exact current-source fallback using ripgrep fixed-string search."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path
from time import monotonic, sleep
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from ..config import AppSettings, InterviewProfile
from ..models import EvidenceSource, Freshness, RetrievalLane
from ..trigger import CODE_PROMPT_TERMS, search_terms

load_dotenv(override=False)


INCLUDE_GLOBS = (
    "*.md",
    "*.txt",
    "*.py",
    "*.ts",
    "*.tsx",
    "*.js",
    "*.jsx",
    "*.rs",
    "*.go",
    "*.java",
    "*.json",
    "*.yaml",
    "*.yml",
    "*.toml",
)

SKIP_GLOBS = (
    "!**/.git/**",
    "!**/node_modules/**",
    "!**/.venv/**",
    "!**/dist/**",
    "!**/build/**",
    "!**/artifacts/**",
    "!**/sessions/**",
)

LOW_SIGNAL_TERMS = {
    "actually",
    "agent",
    "agents",
    "always",
    "answer",
    "answers",
    "before",
    "code",
    "come",
    "comes",
    "correct",
    "current",
    "different",
    "during",
    "evidence",
    "ignore",
    "looking",
    "order",
    "orders",
    "memory",
    "project",
    "really",
    "right",
    "sample",
    "samples",
    "sort",
    "system",
    "terms",
    "thing",
    "things",
    "through",
    "work",
}

CODE_TERM_PRIORITY = (
    "parentheses",
    "parenthesis",
    "minimum",
    "remove",
    "removal",
    "invalid",
    "valid",
    "stack",
    "input",
    "output",
    "opening",
    "closing",
    "characters",
    "string",
    "strings",
)


class RipgrepResult(BaseModel):
    """Bounded ripgrep lane result."""

    sources: list[EvidenceSource] = Field(default_factory=list)
    latency_ms: int = Field(ge=0)
    detail: str
    ok: bool


class RipgrepEvidenceClient:
    """Search explicit repository roots without interpreting query as regex."""

    def __init__(self, settings: AppSettings, profile: InterviewProfile) -> None:
        self._settings = settings
        self._profile = profile

    async def retrieve(self, query: str) -> RipgrepResult:
        """Run fixed-string searches in parallel across the allowlist."""

        started = monotonic()
        if not self._settings.repo_roots:
            return RipgrepResult(
                sources=[],
                latency_ms=0,
                detail="No repository roots configured",
                ok=False,
            )
        terms = _prioritized_terms(query, self._profile)
        if not terms:
            return RipgrepResult(sources=[], latency_ms=0, detail="No lexical terms", ok=False)
        results = await asyncio.gather(
            *(asyncio.to_thread(self._search_repo, root, terms) for root in self._settings.repo_roots),
            return_exceptions=True,
        )
        sources: list[EvidenceSource] = []
        errors = 0
        for result in results:
            if isinstance(result, Exception):
                errors += 1
            else:
                sources.extend(result)
        sources = _dedupe(sources)[:12]
        latency_ms = int((monotonic() - started) * 1000)
        detail = f"Current source {len(sources)}"
        if errors:
            detail += f"; {errors} repo error(s)"
        return RipgrepResult(sources=sources, latency_ms=latency_ms, detail=detail, ok=bool(sources))

    def _search_repo(self, root: Path, terms: list[str]) -> list[EvidenceSource]:
        command = [
            "rg",
            "--json",
            "--fixed-strings",
            "--ignore-case",
            "--line-number",
            "--max-count",
            "3",
            "--max-filesize",
            "2M",
        ]
        for glob in INCLUDE_GLOBS:
            command.extend(["--glob", glob])
        for glob in SKIP_GLOBS:
            command.extend(["--glob", glob])
        for term in terms[:8]:
            command.extend(["--regexp", term])
        command.append(str(root))
        stdout, stderr, returncode, truncated = _run_rg_bounded(
            command,
            timeout_s=self._settings.subprocess_timeout_s,
            max_matches=24,
        )
        if returncode not in {0, 1} and not truncated:
            raise RuntimeError(f"rg exited {returncode}: {stderr[:200]}")
        return _parse_rg_json(root, stdout)


def _prioritized_terms(query: str, profile: InterviewProfile) -> list[str]:
    lower = query.casefold()
    aliases = [
        alias
        for project, values in profile.project_aliases.items()
        for alias in [project, *values]
        if alias.casefold() in lower
    ]
    profile_terms = [
        term
        for term in profile.watch_terms
        if term.casefold() in lower and _term_is_specific(term)
    ]
    code_terms = [
        term
        for term in CODE_TERM_PRIORITY
        if term in CODE_PROMPT_TERMS and term in lower and _term_is_specific(term)
    ]
    lexical = [term for term in search_terms(query, limit=10) if _term_is_specific(term)]
    return _unique([*aliases, *profile_terms, *code_terms, *lexical])[:8]


def _term_is_specific(term: str) -> bool:
    clean = " ".join(term.split()).casefold()
    if not clean or clean in LOW_SIGNAL_TERMS:
        return False
    return " " in clean or "-" in clean or len(clean) >= 6


def _run_rg_bounded(
    command: list[str],
    *,
    timeout_s: float,
    max_matches: int,
) -> tuple[str, str, int, bool]:
    """Capture only a bounded number of rg match events and enforce a deadline."""

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "RIPGREP_CONFIG_PATH": ""},
    )
    if process.stdout is None or process.stderr is None:
        process.kill()
        raise RuntimeError("rg pipes were not created")
    os.set_blocking(process.stdout.fileno(), False)
    os.set_blocking(process.stderr.fileno(), False)

    deadline = monotonic() + timeout_s
    stdout_buffer = bytearray()
    stderr_buffer = bytearray()
    pending = bytearray()
    match_lines: list[bytes] = []
    truncated = False

    while True:
        _read_nonblocking(process.stdout.fileno(), pending, 65_536)
        _read_nonblocking(process.stderr.fileno(), stderr_buffer, 4_096)
        while b"\n" in pending:
            line, _, remainder = pending.partition(b"\n")
            pending = bytearray(remainder)
            if _is_match_event(line):
                match_lines.append(line)
                if len(match_lines) >= max_matches:
                    truncated = True
                    process.terminate()
                    break
        if truncated:
            break
        if process.poll() is not None:
            break
        if monotonic() >= deadline:
            truncated = True
            process.terminate()
            break
        sleep(0.01)

    try:
        process.wait(timeout=0.75)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=0.75)
    _read_nonblocking(process.stdout.fileno(), pending, 65_536)
    _read_nonblocking(process.stderr.fileno(), stderr_buffer, 4_096)
    if pending and len(match_lines) < max_matches and _is_match_event(bytes(pending)):
        match_lines.append(bytes(pending))
    stdout_buffer.extend(b"\n".join(match_lines))
    return (
        stdout_buffer.decode("utf-8", errors="replace"),
        stderr_buffer.decode("utf-8", errors="replace"),
        int(process.returncode or 0),
        truncated,
    )


def _read_nonblocking(fd: int, target: bytearray, limit: int) -> None:
    if len(target) >= limit:
        return
    try:
        chunk = os.read(fd, min(16_384, limit - len(target)))
    except BlockingIOError:
        return
    if chunk:
        target.extend(chunk)


def _is_match_event(line: bytes) -> bool:
    try:
        event = json.loads(line)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False
    return isinstance(event, dict) and event.get("type") == "match"


def _parse_rg_json(root: Path, stdout: str) -> list[EvidenceSource]:
    sources: list[EvidenceSource] = []
    repository = root.name
    for raw_line in stdout.splitlines():
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("type") != "match":
            continue
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        path_payload = data.get("path") if isinstance(data.get("path"), dict) else {}
        line_payload = data.get("lines") if isinstance(data.get("lines"), dict) else {}
        path_text = str(path_payload.get("text") or "")
        excerpt = " ".join(str(line_payload.get("text") or "").split())
        line_number = data.get("line_number")
        if not path_text or not excerpt:
            continue
        path = Path(path_text)
        try:
            relative = path.resolve().relative_to(root.resolve())
        except ValueError:
            continue
        matched_terms = _matched_texts(data.get("submatches"))
        specific_matches = [term for term in matched_terms if _term_is_specific(term)]
        if not specific_matches:
            continue
        score = _source_score(path, specific_matches)
        sources.append(
            EvidenceSource(
                lane=RetrievalLane.RIPGREP,
                label=f"{repository}/{relative.as_posix()}",
                excerpt=excerpt[:4_000],
                score=score,
                freshness=Freshness.CURRENT,
                repository=repository,
                path=str(path.resolve()),
                line_start=_positive_int(line_number),
                line_end=_positive_int(line_number),
                metadata={"matched_terms": matched_terms, "root": str(root)},
            )
        )
    return sources


def _matched_texts(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        match = item.get("match") if isinstance(item.get("match"), dict) else {}
        text = match.get("text")
        if isinstance(text, str) and text.casefold() not in {part.casefold() for part in result}:
            result.append(text)
    return result


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 1 else None


def _source_score(path: Path, matched_terms: list[str]) -> float:
    """Score exact matches higher when the current source path is also topical."""

    path_tokens = _path_tokens(path)
    matched_tokens = {
        token
        for term in matched_terms
        for token in _path_tokens(Path(term))
        if token
    }
    path_overlap = len(path_tokens & matched_tokens)
    suffix_bonus = 0.04 if path.suffix.casefold() in {".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go"} else 0.0
    path_bonus = min(0.18, path_overlap * 0.09)
    return min(0.93, 0.56 + (0.10 * len(matched_terms)) + path_bonus + suffix_bonus)


def _path_tokens(path: Path) -> set[str]:
    tokens: set[str] = set()
    current: list[str] = []
    for char in path.as_posix().casefold():
        if char.isalnum():
            current.append(char)
        elif current:
            token = "".join(current)
            if len(token) >= 3:
                tokens.add(token)
            current = []
    if current:
        token = "".join(current)
        if len(token) >= 3:
            tokens.add(token)
    return tokens


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = " ".join(value.split())
        key = clean.casefold()
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return result


def _dedupe(sources: list[EvidenceSource]) -> list[EvidenceSource]:
    seen: set[tuple[str, int | None, str]] = set()
    result: list[EvidenceSource] = []
    for source in sorted(sources, key=lambda item: item.score, reverse=True):
        key = (source.path or "", source.line_start, source.excerpt.casefold())
        if key in seen:
            continue
        seen.add(key)
        result.append(source)
    return result
