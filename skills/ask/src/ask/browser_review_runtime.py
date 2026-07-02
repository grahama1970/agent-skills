"""Shared helpers for browser-backed ask oracle lanes."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any


class BrowserReviewBundleError(RuntimeError):
    """Browser reviewer cannot consume path-only evidence bundles."""

    FRIENDLY = (
        "I'm a web-based agent and I can't read local file paths. "
        "Please provide a concatenated text file."
    )

    def __init__(self, *, backend: str, detail: str = "") -> None:
        message = self.FRIENDLY
        if detail:
            message = f"{message}\n\nDetected issue: {detail}"
        super().__init__(message)
        self.backend = backend
        self.detail = detail


_PATH_TOKEN_RE = re.compile(r"(?:(?:^|\s)|`)((?:~|/|\./|\.\./)[^\s`]+)")
_ARCHIVE_EXTENSIONS = (
    ".zip",
    ".tar",
    ".tgz",
    ".tar.gz",
    ".tar.bz2",
    ".7z",
)


def extract_path_tokens(text: str) -> list[str]:
    """Return unique filesystem path tokens referenced in *text*."""
    seen: set[str] = set()
    out: list[str] = []
    for match in _PATH_TOKEN_RE.finditer(text):
        token = match.group(1).rstrip(".,;:)>")
        if token.startswith("/") and "/" not in token[1:]:
            continue
        if token not in seen:
            seen.add(token)
            out.append(token)
    return out


def _resolve_path_token(token: str) -> Path | None:
    try:
        path = Path(token).expanduser()
    except Exception:
        return None
    if not path.is_absolute():
        try:
            path = path.resolve(strict=False)
        except Exception:
            return None
    return path


def _is_archive_path(path: Path) -> bool:
    lower = path.name.lower()
    return any(lower.endswith(ext) for ext in _ARCHIVE_EXTENSIONS)


def _attachment_has_text(att: dict[str, Any]) -> bool:
    return bool(att.get("text")) and not att.get("error")


def _zip_member_count(path: Path, *, max_files: int = 5) -> tuple[int, str | None]:
    try:
        with zipfile.ZipFile(path) as zf:
            members = [info for info in zf.infolist() if not info.is_dir()]
    except Exception as exc:
        return 0, f"could not read zip archive: {exc}"
    if not members:
        return 0, "zip archive is empty"
    if len(members) > max_files:
        return len(members), f"zip contains {len(members)} files (maximum {max_files})"
    return len(members), None


def resolve_browser_review_delivery(
    question: str,
    attachments: list[dict[str, Any]],
    *,
    backend: str,
) -> str:
    """Validate browser-review evidence.

    Ask no longer owns WebGPT zip attachment delivery. Browser lanes in ask must
    receive readable evidence as inlined text or a single concatenated text file.
    """
    question_refs = extract_path_tokens(question)
    zip_refs = [
        token
        for token in question_refs
        if (p := _resolve_path_token(token)) is not None and _is_archive_path(p)
    ]
    if zip_refs:
        archive = _resolve_path_token(zip_refs[0])
        if archive is None or not archive.is_file():
            raise BrowserReviewBundleError(
                backend=backend,
                detail=f"archive path does not exist: {zip_refs[0]}",
            )
        _, zip_err = _zip_member_count(archive)
        detail = zip_err or (
            "archive attachment delivery moved to $webgpt; "
            "use a concatenated text/markdown file for $ask browser backends"
        )
        raise BrowserReviewBundleError(backend=backend, detail=detail)

    _validate_inlined_browser_review_evidence(question, attachments, backend=backend)
    return ""


def _validate_inlined_browser_review_evidence(
    question: str,
    attachments: list[dict[str, Any]],
    *,
    backend: str,
) -> None:
    """Require concatenated inlined text for local filesystem evidence."""
    question_refs = extract_path_tokens(question)
    referenced_set = set(question_refs)
    for att in attachments:
        if _attachment_has_text(att):
            for token in extract_path_tokens(str(att.get("text", ""))):
                referenced_set.add(token)
    referenced: list[str] = list(referenced_set)
    if not referenced:
        return

    inlined_paths: set[str] = set()
    for att in attachments:
        if not _attachment_has_text(att):
            continue
        raw_path = str(att.get("path", ""))
        inlined_paths.add(raw_path)
        resolved = _resolve_path_token(raw_path)
        if resolved is not None:
            inlined_paths.add(str(resolved))

    details: list[str] = []
    directories: list[str] = []
    missing: list[str] = []
    path_only: list[str] = []
    archives: list[str] = []

    for token in referenced:
        path = _resolve_path_token(token)
        if path is None:
            missing.append(token)
            continue
        if _is_archive_path(path):
            archives.append(token)
            continue
        if path.is_dir():
            directories.append(token)
            continue
        if not path.is_file():
            missing.append(token)
            continue
        if token not in inlined_paths and str(path) not in inlined_paths:
            path_only.append(token)

    if directories:
        details.append("directory paths were referenced (" + ", ".join(directories) + ")")
    if missing:
        details.append("some referenced paths do not exist (" + ", ".join(missing) + ")")
    if path_only:
        details.append(
            "these files were referenced by path only, without inlined content: "
            + ", ".join(path_only)
        )
    if archives:
        details.append(
            "archive paths were referenced ("
            + ", ".join(archives)
            + "); archive delivery moved to $webgpt"
        )
    if question_refs and not any(_attachment_has_text(a) for a in attachments):
        details.append(
            "the prompt references filesystem paths but no readable text was inlined"
        )
    failed_reads = [a["path"] for a in attachments if a.get("error")]
    if failed_reads:
        details.append("attachment read failed: " + ", ".join(failed_reads))

    if details:
        raise BrowserReviewBundleError(backend=backend, detail="; ".join(details))


def extract_file_attachments(question: str, *, max_bytes: int = 2_000_000) -> list[dict[str, Any]]:
    """Find readable file paths referenced in the question and inline them."""
    seen: set[Path] = set()
    out: list[dict[str, Any]] = []
    for match in _PATH_TOKEN_RE.finditer(question):
        token = match.group(1).rstrip(".,;:)>")
        try:
            path = Path(token).expanduser()
        except Exception:
            continue
        if not path.is_absolute():
            try:
                path = path.resolve(strict=False)
            except Exception:
                continue
        if not path.exists() or not path.is_file() or _is_archive_path(path):
            continue
        if path in seen:
            continue
        seen.add(path)
        try:
            data = path.read_bytes()
        except Exception as exc:
            out.append({
                "path": str(path),
                "error": f"read failed: {exc}",
                "bytes": 0,
                "truncated": False,
            })
            continue
        truncated = len(data) > max_bytes
        try:
            text = data[:max_bytes].decode("utf-8", errors="replace")
        except Exception:
            text = "<binary content omitted>"
            truncated = True
        out.append({
            "path": str(path),
            "bytes": len(data),
            "truncated": truncated,
            "text": text,
        })
    return out


def build_browser_oracle_prompt(
    base_prompt: str,
    attachments: list[dict[str, Any]],
    *,
    system_preamble: str | None = None,
) -> str:
    """Compose a browser-oracle prompt with readable files inlined."""
    parts: list[str] = []
    if system_preamble:
        parts.append(system_preamble.strip())
        parts.append("")
    parts.append(base_prompt.strip())
    if attachments:
        parts.append("")
        parts.append("---")
        parts.append("")
        parts.append("## Attached files")
        parts.append("")
        for att in attachments:
            parts.append(f"### {att['path']}")
            if "error" in att:
                parts.append(f"_could not read: {att['error']}_")
                parts.append("")
                continue
            if att.get("truncated"):
                parts.append(
                    f"_truncated to {len(att['text']):,} chars (file was {att['bytes']:,} bytes)_"
                )
            parts.append("")
            parts.append("```")
            parts.append(att["text"])
            parts.append("```")
            parts.append("")
    return "\n".join(parts).rstrip() + "\n"
