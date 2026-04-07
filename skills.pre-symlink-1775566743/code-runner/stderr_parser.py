"""Deterministic stderr condensation for /code-runner.

Extracts structured error evidence from raw stderr/stdout without LLM calls.
Layered pipeline: normalization -> tool-aware parsers -> generic ranking.

The condensed ErrorEvidence replaces raw stderr in the fix prompt, giving the LLM
high-signal failure details without install logs, duplicate lines, ANSI noise,
or irrelevant stack frames.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable


_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")

_FILE_LINE_RE = re.compile(
    r'(?P<file>(?:[A-Za-z]:)?[^\s:()]+\.(?:py|pyi|ts|tsx|js|jsx|mjs|cjs|json|ya?ml|toml|rs|go|java|kt|swift|sh|bash|zsh|c|cc|cpp|h|hpp))'
    r'(?::|\()(?P<line>\d+)(?:[: ,)](?P<col>\d+))?'
)

_PY_FRAME_RE = re.compile(r'  File "([^"]+)", line (\d+)(?:, in ([^\n]+))?')

_ERROR_KEYWORDS_RE = re.compile(
    r"\b(error|exception|failed|failure|undefined|cannot|missing|fatal|panic|traceback|assert(?:ion)?error)\b",
    re.IGNORECASE,
)


@dataclass
class ErrorLocation:
    file: str | None = None
    line: int | None = None
    column: int | None = None


@dataclass
class ErrorEvidence:
    failure_type: str  # python_traceback, python_syntax, pytest, ruff_mypy, typescript, import_error, build, runtime, generic
    summary: str
    primary_location: ErrorLocation | None = None
    root_cause_lines: list[str] = field(default_factory=list)
    traceback_tail: list[str] = field(default_factory=list)
    failing_tests: list[str] = field(default_factory=list)
    raw_stderr_tail: str = ""
    confidence: float = 0.0

    def to_prompt_block(self, include_raw_on_low_confidence: bool = True) -> str:
        """Format as compact text block for the LLM fix prompt."""
        lines = [
            f"Failure type: {self.failure_type}",
            f"Summary: {self.summary}",
            f"Confidence: {self.confidence:.2f}",
        ]

        if self.primary_location and self.primary_location.file:
            loc = self.primary_location
            pos = loc.file
            if loc.line is not None:
                pos += f":{loc.line}"
            if loc.column is not None:
                pos += f":{loc.column}"
            lines.append(f"Location: {pos}")

        if self.failing_tests:
            lines.append(f"Failing tests: {', '.join(self.failing_tests[:5])}")

        if self.root_cause_lines:
            lines.append("Root cause:")
            for rc in self.root_cause_lines[:6]:
                lines.append(f"  {rc.rstrip()}")

        if self.traceback_tail:
            lines.append("Traceback tail:")
            for tb in self.traceback_tail[:8]:
                lines.append(f"  {tb.rstrip()}")

        if include_raw_on_low_confidence and self.confidence < 0.60 and self.raw_stderr_tail:
            lines.append("Raw stderr tail:")
            for raw in self.raw_stderr_tail.splitlines()[-10:]:
                if raw.strip():
                    lines.append(f"  {raw.rstrip()}")

        return "\n".join(lines)


# ── Shared Helpers ───────────────────────────────────────────────────────────


def _normalize_text(text: str) -> str:
    """Strip ANSI escapes, normalize newlines, and remove NULs."""
    if not text:
        return ""
    text = text.replace("\x00", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _ANSI_RE.sub("", text)
    return text


def _clean_line(line: str, max_len: int = 240) -> str:
    """Collapse whitespace and bound line length."""
    line = re.sub(r"\s+", " ", line.strip())
    return line[:max_len]


def _dedupe_preserve_order(lines: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        cleaned = _clean_line(line)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
    return out


def _nonempty_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip()]


def _take_last_nonempty_line(text: str) -> str:
    for line in reversed(text.splitlines()):
        if line.strip():
            return _clean_line(line)
    return ""


def _tail_lines(text: str, n: int) -> list[str]:
    return _dedupe_preserve_order(_nonempty_lines(text)[-n:])


def _stderr_tail(stderr: str, max_chars: int = 700) -> str:
    tail = stderr[-max_chars:]
    return "\n".join(_nonempty_lines(tail)[-12:])


def _is_user_code_path(path: str) -> bool:
    lowered = path.replace("\\", "/").lower()
    noise_markers = (
        "/site-packages/",
        "/dist-packages/",
        "/node_modules/",
        "/.venv/",
        "/venv/",
        "/usr/lib/",
        "/lib/python",
        "<frozen ",
        "<string>",
    )
    return not any(marker in lowered for marker in noise_markers)


def _best_location_from_text(text: str) -> ErrorLocation | None:
    for line in _nonempty_lines(text):
        match = _FILE_LINE_RE.search(line)
        if match:
            return ErrorLocation(
                file=match.group("file"),
                line=int(match.group("line")),
                column=int(match.group("col")) if match.group("col") else None,
            )
    return None


# ── Layer 1: Tool-Aware Parsers ──────────────────────────────────────────────


def _parse_python_syntax_error(stderr: str) -> ErrorEvidence | None:
    """Extract SyntaxError / IndentationError / TabError blocks."""
    lines = _nonempty_lines(stderr)
    if not lines:
        return None

    syntax_kinds = ("SyntaxError:", "IndentationError:", "TabError:")
    last_idx: int | None = None

    for i, line in enumerate(lines):
        if any(kind in line for kind in syntax_kinds):
            last_idx = i

    if last_idx is None:
        return None

    error_line = lines[last_idx].strip()
    file_line_idx: int | None = None

    for i in range(last_idx - 1, -1, -1):
        if re.search(r'^File "([^"]+)", line (\d+)$', lines[i].strip()):
            file_line_idx = i
            break

    location = None
    snippet: list[str] = []

    if file_line_idx is not None:
        match = re.search(r'^File "([^"]+)", line (\d+)$', lines[file_line_idx].strip())
        if match:
            location = ErrorLocation(file=match.group(1), line=int(match.group(2)))

        snippet = lines[file_line_idx:last_idx + 1]

    root = _dedupe_preserve_order(snippet or [error_line])[:6]

    return ErrorEvidence(
        failure_type="python_syntax",
        summary=_clean_line(error_line, 200),
        primary_location=location,
        root_cause_lines=root,
        traceback_tail=[],
        raw_stderr_tail=_stderr_tail(stderr),
        confidence=0.92 if location else 0.82,
    )


def _parse_python_traceback(stderr: str) -> ErrorEvidence | None:
    """Extract from Python tracebacks."""
    if "Traceback (most recent call last):" not in stderr:
        return None

    blocks = re.findall(
        r"Traceback \(most recent call last\):\n(?P<body>.*?)(?P<final>^[A-Za-z_][\w.]*?(?:Error|Exception|Warning|Exit):?.*$)",
        stderr,
        re.DOTALL | re.MULTILINE,
    )
    if not blocks:
        return None

    tb_body, error_line = blocks[-1]
    frames = _PY_FRAME_RE.findall(tb_body)
    if not frames:
        return None

    user_frames = [f for f in frames if _is_user_code_path(f[0])]
    chosen = user_frames[-1] if user_frames else frames[-1]
    location = ErrorLocation(file=chosen[0], line=int(chosen[1]))

    tb_tail = _tail_lines(tb_body + "\n" + error_line, 8)

    root_lines = [error_line]
    for line in reversed(_nonempty_lines(tb_body)):
        stripped = line.strip()
        if stripped and not stripped.startswith("File "):
            root_lines.insert(0, stripped)
            break

    return ErrorEvidence(
        failure_type="python_traceback",
        summary=_clean_line(error_line, 200),
        primary_location=location,
        root_cause_lines=_dedupe_preserve_order(root_lines)[:4],
        traceback_tail=tb_tail,
        raw_stderr_tail=_stderr_tail(stderr),
        confidence=0.90,
    )


def _parse_import_error(stderr: str) -> ErrorEvidence | None:
    """Extract ModuleNotFoundError / ImportError, preferring the last one."""
    matches = list(re.finditer(r"^(ModuleNotFoundError|ImportError):\s*(.+)$", stderr, re.MULTILINE))
    if not matches:
        return None

    match = matches[-1]
    error_type, message = match.group(1), match.group(2).strip()

    tb_before = stderr[:match.start()]
    frames = _PY_FRAME_RE.findall(tb_before)
    user_frames = [f for f in frames if _is_user_code_path(f[0])]
    chosen = user_frames[-1] if user_frames else (frames[-1] if frames else None)

    location = None
    if chosen:
        location = ErrorLocation(file=chosen[0], line=int(chosen[1]))

    return ErrorEvidence(
        failure_type="import_error",
        summary=f"{error_type}: {_clean_line(message, 160)}",
        primary_location=location,
        root_cause_lines=[f"{error_type}: {_clean_line(message, 220)}"],
        traceback_tail=_tail_lines(tb_before + "\n" + match.group(0), 6),
        raw_stderr_tail=_stderr_tail(stderr),
        confidence=0.94 if location else 0.86,
    )


def _parse_pytest(stderr: str, stdout: str) -> ErrorEvidence | None:
    """Extract failing test names, assertion lines, and primary location from pytest."""
    combined = "\n".join(part for part in (stdout, stderr) if part)
    if "pytest" not in combined.lower() and "== FAILURES ==" not in combined and "\nFAILED " not in combined:
        return None

    failed_tests = _dedupe_preserve_order(
        re.findall(r"^FAILED\s+([^\s]+)", combined, re.MULTILINE)
    )
    if not failed_tests and "failed" not in combined.lower():
        return None

    candidate_lines: list[str] = []
    for line in _nonempty_lines(combined):
        stripped = line.strip()
        if stripped.startswith("E ") and len(stripped) <= 220:
            candidate_lines.append(stripped)
        elif "AssertionError" in stripped:
            candidate_lines.append(stripped)
        elif re.search(r"\bassert\b", stripped) and len(stripped) <= 220:
            candidate_lines.append(stripped)
        elif stripped.startswith("FAILED ") and len(stripped) <= 220:
            candidate_lines.append(stripped)

    root_lines = _dedupe_preserve_order(candidate_lines)[:6]

    location = None
    for line in root_lines + _nonempty_lines(combined):
        match = re.search(r"(\S+\.py):(\d+)(?::\s*|\s+)", line)
        if match:
            location = ErrorLocation(file=match.group(1), line=int(match.group(2)))
            break

    summary = root_lines[0] if root_lines else f"{len(failed_tests) or 1} test(s) failed"

    return ErrorEvidence(
        failure_type="pytest",
        summary=_clean_line(summary, 200),
        primary_location=location,
        root_cause_lines=root_lines,
        traceback_tail=[],
        failing_tests=failed_tests[:10],
        raw_stderr_tail=_stderr_tail(stderr or combined),
        confidence=0.96 if failed_tests else 0.88,
    )


def _parse_ruff_mypy(stderr: str, stdout: str) -> ErrorEvidence | None:
    """Extract ruff / mypy / pyright diagnostics from either stderr or stdout."""
    text = "\n".join(part for part in (stderr, stdout) if part)
    rows: list[tuple[str, int, int | None, str, str]] = []

    # Ruff / pyright style: file:line:col: CODE message
    for f, l, c, code, msg in re.findall(
        r"^(\S+\.pyi?):(\d+):(\d+):\s*([A-Za-z0-9_-]+)\s+(.+)$",
        text,
        re.MULTILINE,
    ):
        rows.append((f, int(l), int(c), code, _clean_line(msg, 180)))

    # mypy style: file:line: error|note: message
    for f, l, severity, msg in re.findall(
        r"^(\S+\.pyi?):(\d+):\s*(error|note):\s+(.+)$",
        text,
        re.MULTILINE,
    ):
        rows.append((f, int(l), None, severity, _clean_line(msg, 180)))

    if not rows:
        return None

    unique: list[tuple[str, int, int | None, str, str]] = []
    seen: set[tuple[str, int, int | None, str, str]] = set()
    for item in rows:
        if item not in seen:
            seen.add(item)
            unique.append(item)
        if len(unique) >= 6:
            break

    first = unique[0]
    location = ErrorLocation(file=first[0], line=first[1], column=first[2])

    root = [
        f"{f}:{l}" + (f":{c}" if c is not None else "") + f": {code} {msg}".strip()
        for f, l, c, code, msg in unique
    ]

    return ErrorEvidence(
        failure_type="ruff_mypy",
        summary=f"{len(rows)} diagnostic(s): {first[3]} {first[4][:120]}",
        primary_location=location,
        root_cause_lines=root,
        raw_stderr_tail=_stderr_tail(stderr or text),
        confidence=0.91,
    )


def _parse_typescript(stderr: str, stdout: str) -> ErrorEvidence | None:
    """Extract TypeScript / ESLint diagnostics from either stderr or stdout."""
    text = "\n".join(part for part in (stderr, stdout) if part)

    ts_diags = re.findall(
        r"^(\S+\.(?:ts|tsx|js|jsx|mts|cts))\((\d+),(\d+)\):\s+error\s+([A-Z]+\d+):\s+(.+)$",
        text,
        re.MULTILINE,
    )
    eslint_diags = re.findall(
        r"^(\S+\.(?:ts|tsx|js|jsx|mts|cts)):(\d+):(\d+):\s+(error|warning)\s+(.+?)(?:\s{2,}\S+)?$",
        text,
        re.MULTILINE,
    )

    rows: list[tuple[str, int, int, str, str]] = [
        (f, int(l), int(c), code, _clean_line(msg, 180))
        for f, l, c, code, msg in ts_diags
    ]
    rows.extend(
        (f, int(l), int(c), severity, _clean_line(msg, 180))
        for f, l, c, severity, msg in eslint_diags
    )

    if not rows:
        return None

    unique: list[tuple[str, int, int, str, str]] = []
    seen: set[tuple[str, int, int, str, str]] = set()
    for row in rows:
        if row not in seen:
            seen.add(row)
            unique.append(row)
        if len(unique) >= 6:
            break

    first = unique[0]
    location = ErrorLocation(file=first[0], line=first[1], column=first[2])

    return ErrorEvidence(
        failure_type="typescript",
        summary=f"{len(rows)} error(s): {first[3]} {first[4][:120]}".strip(),
        primary_location=location,
        root_cause_lines=[f"{f}:{l}:{c}: {code} {msg}".strip() for f, l, c, code, msg in unique],
        raw_stderr_tail=_stderr_tail(stderr or text),
        confidence=0.91,
    )


# ── Layer 2: Generic Heuristics ──────────────────────────────────────────────


def _parse_generic(stderr: str, stdout: str = "", command: str = "") -> ErrorEvidence:
    """Fallback: rank the most diagnostic lines from combined output."""
    text = "\n".join(part for part in (stderr, stdout) if part)
    lines = _nonempty_lines(text)

    scored: list[tuple[int, int, str]] = []
    for idx, raw_line in enumerate(lines):
        line = raw_line.strip()
        score = 0

        if _FILE_LINE_RE.search(line):
            score += 5
        if "traceback" in line.lower():
            score += 4
        if line.startswith("E "):
            score += 4
        if "caused by:" in line.lower():
            score += 4
        if _ERROR_KEYWORDS_RE.search(line):
            score += 3
        if command and any(tok in command for tok in ("pytest", "ruff", "mypy", "tsc", "eslint", "npm", "pnpm", "yarn")):
            if any(tok in line.lower() for tok in ("error", "failed", "assert", "exception")):
                score += 1
        if len(line) > 260:
            score -= 1

        if score > 0:
            scored.append((score, idx, _clean_line(line, 240)))

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    top_lines = _dedupe_preserve_order(line for _, _, line in scored)[:6]

    location = _best_location_from_text("\n".join(top_lines)) or _best_location_from_text(text)
    summary = top_lines[0] if top_lines else _take_last_nonempty_line(text) or "Unknown error"

    failure_type = "generic"
    lowered = text.lower()
    if any(token in lowered for token in ("build failed", "compilation failed", "webpack compiled with", "vite build", "npm err!")):
        failure_type = "build"
    elif any(token in lowered for token in ("segmentation fault", "panic:", "fatal runtime error")):
        failure_type = "runtime"

    confidence = 0.45
    if location and top_lines:
        confidence = 0.58
    elif top_lines:
        confidence = 0.50

    return ErrorEvidence(
        failure_type=failure_type,
        summary=summary[:200],
        primary_location=location,
        root_cause_lines=top_lines,
        raw_stderr_tail=_stderr_tail(stderr or text),
        confidence=confidence,
    )


# ── Layer 3: Pipeline ────────────────────────────────────────────────────────


def condense_stderr(stderr: str, stdout: str = "", command: str = "") -> ErrorEvidence:
    """Deterministic stderr condensation pipeline.

    Normalizes output, tries tool-specific parsers in priority order,
    then falls back to generic heuristics.
    """
    stderr_n = _normalize_text(stderr)
    stdout_n = _normalize_text(stdout)

    parsers = (
        lambda: _parse_pytest(stderr_n, stdout_n),
        lambda: _parse_python_syntax_error(stderr_n),
        lambda: _parse_python_traceback(stderr_n),
        lambda: _parse_import_error(stderr_n),
        lambda: _parse_ruff_mypy(stderr_n, stdout_n),
        lambda: _parse_typescript(stderr_n, stdout_n),
    )

    for parser in parsers:
        result = parser()
        if result:
            return result

    return _parse_generic(stderr_n, stdout_n, command)


__all__ = [
    "ErrorLocation",
    "ErrorEvidence",
    "condense_stderr",
]
