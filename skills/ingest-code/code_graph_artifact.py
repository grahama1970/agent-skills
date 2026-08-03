"""Deterministic code graph artifact bundle writer for ingest-code."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from code_symbol_record import CodeSymbolRecord

SCHEMA_VERSION = "ingest-code.code_graph_bundle.v1"
DEFAULT_MAX_SOURCE_BYTES = 1024 * 1024
INCOMPLETE_FILE_STATUSES = {"failed", "unreadable", "binary", "too_large", "unsupported"}
INCOMPLETE_EXTRACTOR_OUTCOMES = {
    "failed",
    "unavailable",
    "timed_out",
    "invalid_output",
    "partial",
}
SUPPORTED_SOURCE_LANGUAGES = {
    "python",
    "typescript",
    "javascript",
    "rust",
    "go",
    "java",
    "c",
    "cpp",
    "ruby",
    "php",
    "swift",
    "kotlin",
    "scala",
}
ARTIFACT_FILENAMES = (
    "manifest.json",
    "files.jsonl",
    "symbols.jsonl",
    "edges.jsonl",
    "diagnostics.jsonl",
    "coverage.json",
)


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _jsonl_bytes(records: list[dict[str, Any]]) -> bytes:
    return b"".join(
        (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        for record in records
    )


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_id(prefix: str, values: list[str]) -> str:
    basis = "\x1f".join(values)
    return f"{prefix}_{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:40]}"


def normalized_rel_path(path: Path, root: Path) -> str:
    """Return a root-relative POSIX path and reject paths outside the scan root."""
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    try:
        rel = resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"path is outside code graph root: {path}") from exc
    rel_text = rel.as_posix()
    if rel_text.startswith("../") or rel_text == ".." or rel.is_absolute():
        raise ValueError(f"path is outside code graph root: {path}")
    return rel_text


def file_id(repo: str, branch: str, rel_path: str) -> str:
    return _sha256_id("cf", [repo.strip(), branch.strip(), rel_path.replace("\\", "/").strip()])


def edge_id(source_file_id: str, target_file_id: str, edge_type: str, module: str, names: list[str]) -> str:
    return _sha256_id(
        "ce",
        [source_file_id, target_file_id, edge_type, module, ",".join(sorted(names))],
    )


def _language_for_path(path: Path) -> str:
    mapping = {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
        ".rs": "rust",
        ".go": "go",
        ".java": "java",
        ".c": "c",
        ".h": "c",
        ".cpp": "cpp",
        ".hpp": "cpp",
        ".rb": "ruby",
        ".php": "php",
        ".swift": "swift",
        ".kt": "kotlin",
        ".scala": "scala",
        ".md": "markdown",
        ".mdx": "markdown",
    }
    return mapping.get(path.suffix, path.suffix.lstrip(".") or "unknown")


def _read_file_bytes(path: Path, max_source_bytes: int) -> tuple[bytes | None, str]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        return None, f"stat_failed:{exc}"
    if size > max_source_bytes:
        return None, "too_large"
    try:
        data = path.read_bytes()
    except OSError as exc:
        return None, f"read_failed:{exc}"
    if b"\0" in data[:8192]:
        return None, "binary"
    return data, ""


def _source_hash(path: Path, max_source_bytes: int) -> tuple[str, str]:
    data, reason = _read_file_bytes(path, max_source_bytes)
    if data is None:
        return "", reason
    return hashlib.sha256(data).hexdigest(), ""


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _python_parse_error(path: Path) -> str:
    if path.suffix != ".py":
        return ""
    try:
        ast.parse(path.read_text(errors="ignore"))
    except SyntaxError as exc:
        return str(exc)
    except OSError as exc:
        return str(exc)
    return ""


def _git_value(root: Path, args: list[str], default: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return default
    if result.returncode != 0:
        return default
    value = result.stdout.strip()
    return value or default


def tracked_worktree_dirty(root: Path) -> bool:
    value = _git_value(root, ["status", "--porcelain", "--untracked-files=no"], "")
    return bool(value.strip())


def ignored_source_files(root: Path, suffixes: set[str]) -> list[Path]:
    """Return ignored source-like files using git's ignore rules when available."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--ignored", "--others", "--exclude-standard", "-z"],
            cwd=str(root),
            capture_output=True,
            timeout=10,
        )
    except Exception:
        return []
    if result.returncode != 0 or not result.stdout:
        return []
    paths: list[Path] = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        rel = raw.decode("utf-8", errors="ignore")
        path = root / rel
        if path.suffix in suffixes and path.is_file():
            paths.append(path)
    return sorted(paths, key=lambda item: item.as_posix())


def _root_relative_or_dot(path: Path, root: Path) -> str:
    if path.resolve() == root.resolve():
        return "."
    return normalized_rel_path(path, root)


def _extractor_reported_paths(extractor_outcomes: list[dict[str, Any]]) -> set[str]:
    reported: set[str] = set()
    for outcome in extractor_outcomes:
        for rel_path in outcome.get("reported_paths", []):
            if isinstance(rel_path, str) and rel_path:
                reported.add(rel_path.replace("\\", "/").strip())
    return reported


def _outcome_for_path(rel_path: str, extractor_outcomes: list[dict[str, Any]]) -> dict[str, Any] | None:
    for outcome in extractor_outcomes:
        root = str(outcome.get("root") or ".").replace("\\", "/").strip() or "."
        if root == "." or rel_path == root or rel_path.startswith(f"{root}/"):
            return outcome
    return None


def _file_records(
    *,
    root: Path,
    repo: str,
    branch: str,
    files: list[Path],
    ignored_files: list[Path],
    extractor_outcomes: list[dict[str, Any]],
    max_source_bytes: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    records: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    ids_by_path: dict[str, str] = {}
    reported_paths = _extractor_reported_paths(extractor_outcomes)

    for path in sorted(files, key=lambda item: normalized_rel_path(item, root)):
        rel_path = normalized_rel_path(path, root)
        language = _language_for_path(path)
        status = "parsed"
        reason = ""
        message = ""
        source_hash, hash_error = _source_hash(path, max_source_bytes)
        path_outcome = _outcome_for_path(rel_path, extractor_outcomes)

        if hash_error == "too_large":
            status = "too_large"
            reason = "too_large"
            message = f"file exceeds max_source_bytes={max_source_bytes}"
        elif hash_error == "binary":
            status = "binary"
            reason = "binary"
            message = "file appears to be binary"
        elif hash_error:
            status = "unreadable"
            reason = "unreadable"
            message = hash_error
        elif language not in SUPPORTED_SOURCE_LANGUAGES:
            status = "unsupported"
            reason = "unsupported_language"
            message = reason
        else:
            outcome_status = str((path_outcome or {}).get("status") or "")
            if outcome_status in INCOMPLETE_EXTRACTOR_OUTCOMES:
                status = "failed"
                reason = f"extractor_{outcome_status}"
                message = str((path_outcome or {}).get("reason") or reason)
            elif language == "python":
                parse_error = _python_parse_error(path)
                if parse_error:
                    status = "failed"
                    reason = "parse_error"
                    message = parse_error
            elif extractor_outcomes and rel_path not in reported_paths:
                status = "failed"
                reason = "parser_no_report"
                message = "configured extractor did not report this non-Python source file"

        current_file_id = file_id(repo, branch, rel_path)
        ids_by_path[rel_path] = current_file_id
        record = {
            "file_id": current_file_id,
            "path": rel_path,
            "language": language,
            "status": status,
            "reason": reason,
            "size_bytes": _file_size(path),
            "source_hash": source_hash,
        }
        records.append(record)
        if reason:
            diagnostics.append({
                "diagnostic_id": _sha256_id("cd", [current_file_id, reason]),
                "file_id": current_file_id,
                "path": rel_path,
                "severity": "error" if status in INCOMPLETE_FILE_STATUSES else "info",
                "reason": reason,
                "message": message or reason,
            })

    known_paths = {record["path"] for record in records}
    for path in ignored_files:
        rel_path = normalized_rel_path(path, root)
        if rel_path in known_paths:
            continue
        current_file_id = file_id(repo, branch, rel_path)
        ids_by_path[rel_path] = current_file_id
        records.append({
            "file_id": current_file_id,
            "path": rel_path,
            "language": _language_for_path(path),
            "status": "ignored",
            "reason": "gitignore",
            "size_bytes": _file_size(path),
            "source_hash": _source_hash(path, max_source_bytes)[0],
        })
        diagnostics.append({
            "diagnostic_id": _sha256_id("cd", [current_file_id, "gitignore"]),
            "file_id": current_file_id,
            "path": rel_path,
            "severity": "info",
            "reason": "gitignore",
            "message": "file excluded by git ignore rules",
        })

    records.sort(key=lambda item: item["path"])
    diagnostics.sort(key=lambda item: (item["path"], item["reason"]))
    return records, diagnostics, ids_by_path


def _symbol_records(
    *,
    root: Path,
    repo: str,
    branch: str,
    symbols: list[CodeSymbolRecord],
    ids_by_path: dict[str, str],
    parsed_paths: set[str],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for symbol in symbols:
        rel_path = symbol.normalized_path
        if rel_path not in parsed_paths:
            continue
        current_file_id = ids_by_path.get(rel_path) or file_id(repo, branch, rel_path)
        document = symbol.to_document()
        records.append({
            "file_id": current_file_id,
            "symbol_id": symbol.symbol_id,
            "symbol_version_id": symbol.symbol_version_id,
            "legacy_key": symbol.legacy_key,
            "path": rel_path,
            "language": symbol.language,
            "symbol_kind": symbol.symbol_kind,
            "symbol_name": symbol.symbol_name,
            "qualified_name": symbol.qualified_name,
            "start_line": symbol.start_line,
            "end_line": symbol.end_line,
            "signature": symbol.signature,
            "content_hash": symbol.effective_content_hash,
            "memory_document": document,
        })
    return sorted(records, key=lambda item: (item["path"], item["qualified_name"], item["start_line"]))


def _edge_records(
    *,
    root: Path,
    repo: str,
    branch: str,
    edges: list[dict[str, Any]],
    ids_by_path: dict[str, str],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for edge in edges:
        from_rel = normalized_rel_path(Path(edge["from_file"]), root)
        to_rel = normalized_rel_path(Path(edge["to_file"]), root)
        source_file_id = ids_by_path.get(from_rel) or file_id(repo, branch, from_rel)
        target_file_id = ids_by_path.get(to_rel) or file_id(repo, branch, to_rel)
        names = sorted(str(name) for name in edge.get("names", []) if str(name))
        edge_type = "IMPORTS"
        records.append({
            "edge_id": edge_id(source_file_id, target_file_id, edge_type, str(edge.get("module") or ""), names),
            "edge_type": edge_type,
            "source_file_id": source_file_id,
            "target_file_id": target_file_id,
            "from_path": from_rel,
            "to_path": to_rel,
            "module": str(edge.get("module") or ""),
            "names": names,
            "status": "resolved",
            "provenance": "python_ast_imports",
        })
    return sorted(records, key=lambda item: (item["from_path"], item["to_path"], item["module"]))


def write_code_graph_bundle(
    *,
    codebase_root: Path,
    repo: str,
    branch: str,
    commit: str,
    scan_roots: list[Path],
    files: list[Path],
    symbols: list[CodeSymbolRecord],
    edges: list[dict[str, Any]],
    artifact_root: Path | None = None,
    extractor_outcomes: list[dict[str, Any]] | None = None,
    max_source_bytes: int = DEFAULT_MAX_SOURCE_BYTES,
) -> dict[str, Any]:
    """Write the deterministic ingest-code code graph bundle and return metadata."""
    root = codebase_root.resolve()
    output_dir = artifact_root or root / "artifacts" / "ingest-code" / "code-graph"
    output_dir.mkdir(parents=True, exist_ok=True)

    suffixes = {path.suffix for path in files if path.suffix}
    ignored = ignored_source_files(root, suffixes)
    outcomes = extractor_outcomes or [{
        "root": _root_relative_or_dot(scan_root, root),
        "status": "succeeded",
        "reason": "",
        "extractor": "unspecified",
        "command": [],
        "declared_languages": sorted({_language_for_path(path) for path in files}),
        "discovered_file_count": len(files),
        "reported_file_count": len(files),
        "reported_paths": sorted(normalized_rel_path(path, root) for path in files),
    } for scan_root in scan_roots]
    file_records, diagnostics, ids_by_path = _file_records(
        root=root,
        repo=repo,
        branch=branch,
        files=files,
        ignored_files=ignored,
        extractor_outcomes=outcomes,
        max_source_bytes=max_source_bytes,
    )
    parsed_paths = {record["path"] for record in file_records if record["status"] == "parsed"}
    symbol_records = _symbol_records(
        root=root,
        repo=repo,
        branch=branch,
        symbols=symbols,
        ids_by_path=ids_by_path,
        parsed_paths=parsed_paths,
    )
    edge_records = _edge_records(root=root, repo=repo, branch=branch, edges=edges, ids_by_path=ids_by_path)

    counts = {
        "files": len(file_records),
        "files_parsed": sum(1 for item in file_records if item["status"] == "parsed"),
        "files_failed": sum(1 for item in file_records if item["status"] == "failed"),
        "files_ignored": sum(1 for item in file_records if item["status"] == "ignored"),
        "files_skipped": sum(1 for item in file_records if item["status"] == "skipped"),
        "files_unsupported": sum(1 for item in file_records if item["status"] == "unsupported"),
        "files_binary": sum(1 for item in file_records if item["status"] == "binary"),
        "files_too_large": sum(1 for item in file_records if item["status"] == "too_large"),
        "files_unreadable": sum(1 for item in file_records if item["status"] == "unreadable"),
        "symbols": len(symbol_records),
        "edges": len(edge_records),
        "diagnostics": len(diagnostics),
    }
    incomplete_roots = [
        outcome for outcome in outcomes if str(outcome.get("status")) in INCOMPLETE_EXTRACTOR_OUTCOMES
    ]
    incomplete_files = [
        item for item in file_records if str(item.get("status")) in INCOMPLETE_FILE_STATUSES
    ]
    complete = not incomplete_roots and not incomplete_files
    coverage = {
        "schema_version": SCHEMA_VERSION,
        "complete": complete,
        "fail_closed": not complete,
        "reconciliation_eligible": complete,
        "counts": counts,
        "extractor_outcomes": outcomes,
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "repo": repo,
        "root": str(root),
        "branch": branch,
        "commit": commit,
        "tracked_worktree_dirty": tracked_worktree_dirty(root),
        "scan_roots": [normalized_rel_path(path, root) if path.resolve() != root else "." for path in scan_roots],
        "artifacts": list(ARTIFACT_FILENAMES) + ["checksums.json"],
        "coverage_complete": coverage["complete"],
        "reconciliation_eligible": coverage["reconciliation_eligible"],
        "counts": counts,
        "extractor_outcomes": outcomes,
    }

    payloads: dict[str, bytes] = {
        "manifest.json": _json_bytes(manifest),
        "files.jsonl": _jsonl_bytes(file_records),
        "symbols.jsonl": _jsonl_bytes(symbol_records),
        "edges.jsonl": _jsonl_bytes(edge_records),
        "diagnostics.jsonl": _jsonl_bytes(diagnostics),
        "coverage.json": _json_bytes(coverage),
    }
    for filename, data in payloads.items():
        (output_dir / filename).write_bytes(data)

    checksums = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": "sha256",
        "files": {filename: _sha256_bytes(data) for filename, data in sorted(payloads.items())},
    }
    (output_dir / "checksums.json").write_bytes(_json_bytes(checksums))

    return {
        "path": str(output_dir),
        "manifest": str(output_dir / "manifest.json"),
        "coverage": str(output_dir / "coverage.json"),
        "checksums": str(output_dir / "checksums.json"),
        "counts": counts,
        "complete": coverage["complete"],
        "reconciliation_eligible": coverage["reconciliation_eligible"],
    }
