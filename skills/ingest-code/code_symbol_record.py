"""Structured code symbol records for memory-backed code indexing."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

IDENTITY_ALGORITHM_VERSION = "ingest-code.symbol-identity.v2"


def split_identifier(value: str) -> list[str]:
    """Split code identifiers into lexical search terms."""
    if not value:
        return []

    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    pieces = re.split(r"[^A-Za-z0-9]+", spaced)
    terms: list[str] = []
    for piece in pieces:
        normalized = piece.strip().lower()
        if normalized and len(normalized) > 1:
            terms.append(normalized)
    return terms


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _normalize_repo_path(value: str) -> str:
    """Normalize a repository-relative path without resolving filesystem state."""
    normalized = re.sub(r"/+", "/", value.replace("\\", "/").strip())
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if not normalized or normalized.startswith("/") or normalized == ".." or normalized.startswith("../"):
        raise ValueError(f"unsafe repository-relative path: {value}")
    if normalized.startswith("~") or re.match(r"^[A-Za-z]:/", normalized):
        raise ValueError(f"unsafe repository-relative path: {value}")
    if "/../" in f"/{normalized}/":
        raise ValueError(f"unsafe repository-relative path: {value}")
    return normalized


def _sha256_id(prefix: str, values: list[str]) -> str:
    basis = "\x1f".join(values)
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:40]
    return f"{prefix}_{digest}"


@dataclass(frozen=True)
class CodeSymbolRecord:
    """Memory-owned code index record emitted by ingest-code.

    ``symbol_id`` identifies the logical symbol currently represented by this
    document. ``symbol_version_id`` identifies one indexed source version of
    that symbol. Keeping those identities separate lets ordinary Memory upserts
    replace the current projection without treating line or body changes as a
    new entity.
    """

    scope: str
    repo: str
    root: str
    branch: str
    commit: str
    path: str
    language: str
    symbol_kind: str
    symbol_name: str
    qualified_name: str
    start_line: int
    end_line: int
    signature: str = ""
    docstring: str = ""
    code: str = ""
    imports: list[str] = field(default_factory=list)
    parameters: list[str] = field(default_factory=list)
    local_variables: list[str] = field(default_factory=list)
    called_symbols: list[str] = field(default_factory=list)
    string_literals: list[str] = field(default_factory=list)
    content_hash: str = ""
    repository_id: str = ""
    repository_id_authoritative: bool = True
    identity_discriminator: str = ""
    identity_algorithm_version: str = IDENTITY_ALGORITHM_VERSION
    tags: list[str] = field(default_factory=list)

    @property
    def effective_repository_id(self) -> str:
        """Return the canonical repository identity used for logical identity."""
        return (self.repository_id or self.repo).strip()

    @property
    def normalized_path(self) -> str:
        """Return the path form used for logical identity and retrieval."""
        return _normalize_repo_path(self.path)

    @property
    def effective_content_hash(self) -> str:
        """Return the supplied source hash or a deterministic local fallback."""
        if self.content_hash:
            return self.content_hash
        source = self.code or self.signature or self.docstring or self.symbol_name
        return hashlib.sha256(source.encode("utf-8")).hexdigest()

    @property
    def symbol_id(self) -> str:
        """Return the stable logical identity for the current symbol."""
        return _sha256_id(
            "cs",
            [
                self.identity_algorithm_version.strip(),
                self.effective_repository_id,
                self.branch.strip(),
                self.normalized_path,
                self.language.strip().lower(),
                self.symbol_kind.strip().lower(),
                self.qualified_name.strip(),
                self.identity_discriminator.strip(),
            ],
        )

    @property
    def symbol_version_id(self) -> str:
        """Return the identity of this indexed source version."""
        return _sha256_id(
            "csv",
            [
                self.symbol_id,
                self.commit.strip(),
                str(self.start_line),
                str(self.end_line),
                self.effective_content_hash,
            ],
        )

    @property
    def legacy_key(self) -> str:
        """Return the pre-v2 line/content-shaped key for migration diagnostics."""
        basis = "|".join([
            self.repo,
            self.branch,
            self.commit,
            self.path,
            self.qualified_name,
            str(self.start_line),
            str(self.end_line),
            self.content_hash,
        ])
        return f"cs_{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:40]}"

    @property
    def key(self) -> str:
        """Compatibility alias for the stable current-projection key."""
        return self.symbol_id

    @property
    def problem(self) -> str:
        file_name = Path(self.normalized_path).name
        return f"What is {self.symbol_name} in {file_name}?"

    @property
    def solution(self) -> str:
        parts = [f"File: {self.normalized_path}:{self.start_line}-{self.end_line}"]
        parts.append(f"Kind: {self.symbol_kind}")
        parts.append(f"Qualified name: {self.qualified_name}")
        if self.signature:
            parts.append(f"Signature: {self.signature}")
        if self.imports:
            parts.append(f"Imports: {', '.join(self.imports[:20])}")
        if self.parameters:
            parts.append(f"Parameters: {', '.join(self.parameters[:20])}")
        if self.called_symbols:
            parts.append(f"Calls: {', '.join(self.called_symbols[:20])}")
        if self.docstring:
            parts.append(f"Docstring:\n{self.docstring[:1200]}")
        if self.code:
            parts.append(f"Code:\n{self.code[:6000]}")
        return "\n".join(parts)

    @property
    def lexical_terms(self) -> list[str]:
        terms = [
            "type:code_symbol",
            f"repo:{self.repo}",
            f"branch:{self.branch}",
            f"path:{self.normalized_path}",
            f"lang:{self.language}",
            f"kind:{self.symbol_kind}",
            f"symbol:{self.symbol_name}",
            f"qualified:{self.qualified_name}",
        ]

        def add(prefix: str, values: list[str]) -> None:
            for value in values:
                if not value:
                    continue
                terms.append(f"{prefix}:{value}")
                terms.extend(split_identifier(value))

        add("def", [self.symbol_name, self.qualified_name])
        add("param", self.parameters)
        add("var", self.local_variables)
        add("call", self.called_symbols)
        add("import", self.imports)
        add("literal", self.string_literals)
        add("path_token", split_identifier(self.normalized_path))
        return sorted(set(terms))

    def to_document(self) -> dict:
        """Return a /memory /upsert document for the code_symbols collection."""
        return {
            "_key": self.symbol_id,
            "type": "code_symbol",
            "scope": self.scope,
            "repo": self.repo,
            "repository_id": self.effective_repository_id,
            "repository_id_authoritative": self.repository_id_authoritative,
            "root": self.root,
            "branch": self.branch,
            "commit": self.commit,
            "path": self.normalized_path,
            "language": self.language,
            "symbol_kind": self.symbol_kind,
            "symbol_name": self.symbol_name,
            "qualified_name": self.qualified_name,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "signature": self.signature,
            "docstring": self.docstring,
            "code": self.code,
            "imports": _unique(self.imports),
            "parameters": _unique(self.parameters),
            "local_variables": _unique(self.local_variables),
            "called_symbols": _unique(self.called_symbols),
            "string_literals": _unique(self.string_literals),
            "content_hash": self.effective_content_hash,
            "symbol_id": self.symbol_id,
            "symbol_version_id": self.symbol_version_id,
            "identity_algorithm_version": self.identity_algorithm_version,
            "identity_discriminator": self.identity_discriminator,
            "legacy_key": self.legacy_key,
            "lexical_terms": self.lexical_terms,
            "tags": _unique(self.tags + self.lexical_terms[:50]),
            "problem": self.problem,
            "solution": self.solution,
            "text": self.solution,
            "code_symbol": True,
        }

    def to_legacy_lesson_document(self) -> dict:
        """Return a compatibility lesson document for old memory daemons."""
        return {
            "problem": self.problem,
            "solution": self.solution,
            "scope": self.scope,
            "tags": _unique(self.tags + ["code_symbol", self.symbol_name]),
            "code_symbol": True,
            "metadata": {
                "type": "code_symbol",
                "repo": self.repo,
                "repository_id": self.effective_repository_id,
                "repository_id_authoritative": self.repository_id_authoritative,
                "branch": self.branch,
                "commit": self.commit,
                "path": self.normalized_path,
                "language": self.language,
                "symbol_kind": self.symbol_kind,
                "symbol_name": self.symbol_name,
                "qualified_name": self.qualified_name,
                "start_line": self.start_line,
                "end_line": self.end_line,
                "content_hash": self.effective_content_hash,
                "symbol_id": self.symbol_id,
                "symbol_version_id": self.symbol_version_id,
                "identity_algorithm_version": self.identity_algorithm_version,
                "identity_discriminator": self.identity_discriminator,
                "legacy_key": self.legacy_key,
                "lexical_terms": self.lexical_terms,
            },
        }
