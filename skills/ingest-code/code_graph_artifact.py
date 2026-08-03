"""Deterministic code graph artifact bundle writer for ingest-code."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from code_symbol_record import IDENTITY_ALGORITHM_VERSION, CodeSymbolRecord

SCHEMA_VERSION = "ingest-code.code_graph_bundle.v1"
ARTIFACT_WRITER_VERSION = "ingest-code.artifact-writer.v1"
INGEST_CODE_VERSION = "ingest-code.skill.v1"
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
CHECKSUMS_FILENAME = "checksums.json"
ALLOWED_ARTIFACT_FILENAMES = ARTIFACT_FILENAMES + (CHECKSUMS_FILENAME,)
ARTIFACT_SCHEMA_VERSIONS = {filename: SCHEMA_VERSION for filename in ARTIFACT_FILENAMES}


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _jsonl_bytes(records: list[dict[str, Any]]) -> bytes:
    return b"".join(
        (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        for record in records
    )


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_json(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


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


def untracked_included_source_files(root: Path, included_paths: set[str]) -> list[str]:
    """Return untracked, non-ignored source files that are part of this bundle."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            cwd=str(root),
            capture_output=True,
            timeout=10,
        )
    except Exception:
        return []
    if result.returncode != 0 or not result.stdout:
        return []
    paths: list[str] = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        rel = raw.decode("utf-8", errors="ignore").replace("\\", "/").strip()
        if rel in included_paths:
            paths.append(rel)
    return sorted(set(paths))


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


def _canonical_scan_roots(scan_roots: list[Path], root: Path) -> list[str]:
    return [_root_relative_or_dot(path, root) for path in scan_roots]


def _configuration_payload(
    *,
    root: Path,
    scan_roots: list[Path],
    files: list[Path],
    extractor_outcomes: list[dict[str, Any]],
    max_source_bytes: int,
    scan_config: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return normalized portable configuration metadata for this extraction."""
    declared_languages = sorted({
        str(language)
        for outcome in extractor_outcomes
        for language in outcome.get("declared_languages", [])
        if str(language)
    })
    if not declared_languages:
        declared_languages = sorted({_language_for_path(path) for path in files})
    config = dict(scan_config or {})
    payload = {
        "glob_patterns": sorted(str(pattern) for pattern in config.get("glob_patterns", [])),
        "scan_roots": _canonical_scan_roots(scan_roots, root),
        "exclude_dirs": sorted(str(item) for item in config.get("exclude_dirs", [])),
        "ignore_rules": str(config.get("ignore_rules", "git_exclude_standard")),
        "language_support": declared_languages,
        "max_source_bytes": max_source_bytes,
        "feature_flags": {
            "treesitter": bool(config.get("treesitter", True)),
            "code_index": bool(config.get("code_index", True)),
            "dry_run": bool(config.get("dry_run", False)),
            "cwe_only": bool(config.get("cwe_only", False)),
        },
        "monitor_config": config.get("monitor_config") or {},
    }
    return payload


def calculate_configuration_digest(
    *,
    root: Path,
    scan_roots: list[Path],
    files: list[Path],
    extractor_outcomes: list[dict[str, Any]],
    max_source_bytes: int = DEFAULT_MAX_SOURCE_BYTES,
    scan_config: dict[str, Any] | None = None,
) -> str:
    """Return the v1 digest for normalized code-graph extraction configuration."""
    return _sha256_json(_configuration_payload(
        root=root,
        scan_roots=scan_roots,
        files=files,
        extractor_outcomes=extractor_outcomes,
        max_source_bytes=max_source_bytes,
        scan_config=scan_config,
    ))


def _extractor_versions(extractor_outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    versions: list[dict[str, Any]] = []
    for outcome in extractor_outcomes:
        versions.append({
            "extractor": str(outcome.get("extractor") or "unknown"),
            "version": str(outcome.get("extractor_version") or "unknown"),
            "root": str(outcome.get("root") or "."),
            "declared_languages": sorted(str(item) for item in outcome.get("declared_languages", [])),
        })
    return versions


def calculate_bundle_digest(checksums: dict[str, Any]) -> str:
    """Return the portable digest for all non-checksum artifact hashes."""
    files = checksums.get("files", {})
    schema_versions = checksums.get("artifact_schema_versions", {})
    entries = [
        {
            "artifact": filename,
            "schema_version": schema_versions.get(filename, SCHEMA_VERSION),
            "sha256": files[filename],
        }
        for filename in sorted(files)
        if filename != CHECKSUMS_FILENAME
    ]
    return _sha256_json({
        "algorithm": "ingest-code.bundle-digest.v1",
        "entries": entries,
    })


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _assert_manifest_required_fields(manifest: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "artifact_schema_versions",
        "artifact_writer_version",
        "ingest_code_version",
        "repo",
        "repository_id",
        "repository_id_authoritative",
        "repository_id_source",
        "branch",
        "ref",
        "commit",
        "identity_algorithm_version",
        "configuration",
        "configuration_digest",
        "worktree_state",
        "authoritative_scan_roots",
        "artifacts",
        "coverage_complete",
        "reconciliation_eligible",
        "counts",
        "extractor_versions",
        "parser_versions",
        "bundle_digest_algorithm",
    }
    missing = sorted(required - set(manifest))
    if missing:
        raise ValueError(f"manifest missing required fields: {', '.join(missing)}")


def _assert_symbol_projection_agrees(symbols: list[dict[str, Any]]) -> None:
    canonical_fields = [
        "symbol_id",
        "symbol_version_id",
        "legacy_key",
        "repository_id",
        "identity_algorithm_version",
        "path",
        "language",
        "symbol_kind",
        "symbol_name",
        "qualified_name",
        "start_line",
        "end_line",
        "content_hash",
    ]
    for symbol in symbols:
        projection = symbol.get("memory_document")
        if not isinstance(projection, dict):
            continue
        for field in canonical_fields:
            if field in projection and projection[field] != symbol.get(field):
                raise ValueError(
                    "symbol memory_document disagrees with canonical field "
                    f"{field} for {symbol.get('symbol_id')}"
                )


def validate_code_graph_bundle(bundle_dir: Path) -> dict[str, Any]:
    """Validate a published code graph bundle without source or Memory access."""
    actual_files = sorted(path.name for path in bundle_dir.iterdir() if path.is_file())
    expected_files = sorted(ALLOWED_ARTIFACT_FILENAMES)
    if actual_files != expected_files:
        raise ValueError(f"unexpected artifact file set: expected {expected_files}, got {actual_files}")

    checksums = _read_json(bundle_dir / CHECKSUMS_FILENAME)
    if checksums.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported checksums schema_version")
    if checksums.get("algorithm") != "sha256":
        raise ValueError("unsupported checksums algorithm")

    checksum_files = checksums.get("files", {})
    if sorted(checksum_files) != sorted(ARTIFACT_FILENAMES):
        raise ValueError("checksums file set does not match non-checksum artifacts")
    for filename in ARTIFACT_FILENAMES:
        actual = _sha256_bytes((bundle_dir / filename).read_bytes())
        if actual != checksum_files.get(filename):
            raise ValueError(f"checksum mismatch for {filename}")

    expected_schema_versions = {filename: SCHEMA_VERSION for filename in ARTIFACT_FILENAMES}
    if checksums.get("artifact_schema_versions") != expected_schema_versions:
        raise ValueError("artifact schema versions do not match v1 envelope")
    bundle_digest = calculate_bundle_digest(checksums)
    if checksums.get("bundle_digest") != bundle_digest:
        raise ValueError("bundle_digest mismatch")

    manifest = _read_json(bundle_dir / "manifest.json")
    _assert_manifest_required_fields(manifest)
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported manifest schema_version")
    if manifest.get("artifact_schema_versions") != expected_schema_versions:
        raise ValueError("manifest artifact schema versions do not match")
    if sorted(manifest.get("artifacts", [])) != expected_files:
        raise ValueError("manifest artifact list does not match allowed file set")
    if manifest.get("configuration_digest") != _sha256_json(manifest.get("configuration", {})):
        raise ValueError("configuration_digest mismatch")

    files = _read_jsonl(bundle_dir / "files.jsonl")
    symbols = _read_jsonl(bundle_dir / "symbols.jsonl")
    edges = _read_jsonl(bundle_dir / "edges.jsonl")
    diagnostics = _read_jsonl(bundle_dir / "diagnostics.jsonl")
    coverage = _read_json(bundle_dir / "coverage.json")

    expected_counts = {
        "files": len(files),
        "files_parsed": sum(1 for item in files if item.get("status") == "parsed"),
        "files_failed": sum(1 for item in files if item.get("status") == "failed"),
        "files_ignored": sum(1 for item in files if item.get("status") == "ignored"),
        "files_skipped": sum(1 for item in files if item.get("status") == "skipped"),
        "files_unsupported": sum(1 for item in files if item.get("status") == "unsupported"),
        "files_binary": sum(1 for item in files if item.get("status") == "binary"),
        "files_too_large": sum(1 for item in files if item.get("status") == "too_large"),
        "files_unreadable": sum(1 for item in files if item.get("status") == "unreadable"),
        "symbols": len(symbols),
        "edges": len(edges),
        "diagnostics": len(diagnostics),
    }
    if manifest.get("counts") != expected_counts or coverage.get("counts") != expected_counts:
        raise ValueError("artifact counts do not match manifest/coverage")
    if manifest.get("coverage_complete") != coverage.get("complete"):
        raise ValueError("manifest coverage_complete disagrees with coverage")
    if manifest.get("reconciliation_eligible") != coverage.get("reconciliation_eligible"):
        raise ValueError("manifest reconciliation eligibility disagrees with coverage")
    if coverage.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported coverage schema_version")

    _assert_symbol_projection_agrees(symbols)
    return {
        "ok": True,
        "bundle_digest": bundle_digest,
        "manifest_hash": checksum_files["manifest.json"],
        "checksums_hash": _sha256_bytes((bundle_dir / CHECKSUMS_FILENAME).read_bytes()),
        "counts": expected_counts,
    }


def _extractor_reported_paths(extractor_outcomes: list[dict[str, Any]]) -> set[str]:
    reported: set[str] = set()
    for outcome in extractor_outcomes:
        for rel_path in outcome.get("reported_paths", []):
            if isinstance(rel_path, str) and rel_path:
                reported.add(rel_path.replace("\\", "/").strip())
    return reported


def _portable_command_token(value: Any, root: Path) -> Any:
    if not isinstance(value, str):
        return value
    normalized = value.replace("\\", "/")
    root_text = root.as_posix()
    if normalized == root_text:
        return "."
    if normalized.startswith(f"{root_text}/"):
        return normalized[len(root_text) + 1 :]
    if normalized.endswith("/skills/treesitter/run.sh"):
        return "skills/treesitter/run.sh"
    if Path(normalized).is_absolute():
        return Path(normalized).name
    return value


def _portable_extractor_outcomes(extractor_outcomes: list[dict[str, Any]], root: Path) -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []
    for outcome in extractor_outcomes:
        portable = dict(outcome)
        portable["command"] = [
            _portable_command_token(item, root) for item in outcome.get("command", [])
        ]
        outcomes.append(portable)
    return outcomes


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
        document["root"] = "."
        records.append({
            "file_id": current_file_id,
            "symbol_id": symbol.symbol_id,
            "symbol_version_id": symbol.symbol_version_id,
            "legacy_key": symbol.legacy_key,
            "repository_id": symbol.effective_repository_id,
            "repository_id_authoritative": symbol.repository_id_authoritative,
            "identity_algorithm_version": symbol.identity_algorithm_version,
            "identity_discriminator": symbol.identity_discriminator,
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


def _write_payload_files(directory: Path, payloads: dict[str, bytes]) -> None:
    directory.mkdir(parents=True, exist_ok=False)
    for filename, data in payloads.items():
        (directory / filename).write_bytes(data)


def _publish_validated_bundle(temp_dir: Path, output_dir: Path) -> None:
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    if not output_dir.exists():
        os.replace(temp_dir, output_dir)
        return
    backup_dir = output_dir.with_name(f".{output_dir.name}.previous-{os.getpid()}")
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    output_dir.rename(backup_dir)
    try:
        os.replace(temp_dir, output_dir)
    except Exception:
        os.replace(backup_dir, output_dir)
        raise
    shutil.rmtree(backup_dir)


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
    repository_id_authoritative: bool = True,
    repository_id_source: str = "legacy_repo",
    identity_algorithm_version: str = IDENTITY_ALGORITHM_VERSION,
    scan_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write the deterministic ingest-code code graph bundle and return metadata."""
    root = codebase_root.resolve()
    output_dir = artifact_root or root / "artifacts" / "ingest-code" / "code-graph"

    suffixes = {path.suffix for path in files if path.suffix}
    ignored = ignored_source_files(root, suffixes)
    raw_outcomes = extractor_outcomes or [{
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
    outcomes = _portable_extractor_outcomes(raw_outcomes, root)
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
    reconciliation_eligible = complete and repository_id_authoritative
    included_paths = {record["path"] for record in file_records if record["status"] != "ignored"}
    untracked_sources = untracked_included_source_files(root, included_paths)
    worktree_state = {
        "tracked_modified": tracked_worktree_dirty(root),
        "untracked_included_source": bool(untracked_sources),
        "untracked_included_source_paths": untracked_sources,
    }
    configuration = _configuration_payload(
        root=root,
        scan_roots=scan_roots,
        files=files,
        extractor_outcomes=outcomes,
        max_source_bytes=max_source_bytes,
        scan_config=scan_config,
    )
    configuration_digest = calculate_configuration_digest(
        root=root,
        scan_roots=scan_roots,
        files=files,
        extractor_outcomes=outcomes,
        max_source_bytes=max_source_bytes,
        scan_config=scan_config,
    )
    artifact_schema_versions = dict(ARTIFACT_SCHEMA_VERSIONS)
    extractor_versions = _extractor_versions(outcomes)
    coverage = {
        "schema_version": SCHEMA_VERSION,
        "complete": complete,
        "fail_closed": not complete,
        "reconciliation_eligible": reconciliation_eligible,
        "repository_id_authoritative": repository_id_authoritative,
        "counts": counts,
        "extractor_outcomes": outcomes,
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "artifact_schema_versions": artifact_schema_versions,
        "artifact_writer_version": ARTIFACT_WRITER_VERSION,
        "ingest_code_version": INGEST_CODE_VERSION,
        "repo": repo,
        "repository_id": repo,
        "repository_id_authoritative": repository_id_authoritative,
        "repository_id_source": repository_id_source,
        "identity_algorithm_version": identity_algorithm_version,
        "root": ".",
        "root_metadata": {
            "portable": True,
            "description": "Repository root is represented as '.'; host absolute paths are not part of the portable bundle.",
        },
        "branch": branch,
        "ref": branch,
        "commit": commit,
        "tracked_worktree_dirty": worktree_state["tracked_modified"],
        "untracked_included_source": worktree_state["untracked_included_source"],
        "worktree_state": worktree_state,
        "configuration": configuration,
        "configuration_digest": configuration_digest,
        "scan_roots": configuration["scan_roots"],
        "authoritative_scan_roots": configuration["scan_roots"],
        "artifacts": list(ALLOWED_ARTIFACT_FILENAMES),
        "coverage_complete": coverage["complete"],
        "reconciliation_eligible": coverage["reconciliation_eligible"],
        "counts": counts,
        "extractor_outcomes": outcomes,
        "extractor_versions": extractor_versions,
        "parser_versions": extractor_versions,
        "bundle_digest_algorithm": "ingest-code.bundle-digest.v1",
    }

    payloads: dict[str, bytes] = {
        "manifest.json": _json_bytes(manifest),
        "files.jsonl": _jsonl_bytes(file_records),
        "symbols.jsonl": _jsonl_bytes(symbol_records),
        "edges.jsonl": _jsonl_bytes(edge_records),
        "diagnostics.jsonl": _jsonl_bytes(diagnostics),
        "coverage.json": _json_bytes(coverage),
    }

    checksums = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": "sha256",
        "artifact_schema_versions": artifact_schema_versions,
        "files": {filename: _sha256_bytes(data) for filename, data in sorted(payloads.items())},
    }
    checksums["bundle_digest"] = calculate_bundle_digest(checksums)
    payloads[CHECKSUMS_FILENAME] = _json_bytes(checksums)

    temp_parent = output_dir.parent
    temp_parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.tmp-", dir=str(temp_parent)))
    try:
        temp_dir.rmdir()
        _write_payload_files(temp_dir, payloads)
        validation = validate_code_graph_bundle(temp_dir)
        _publish_validated_bundle(temp_dir, output_dir)
    except Exception:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        raise

    checksums_hash = _sha256_bytes((output_dir / CHECKSUMS_FILENAME).read_bytes())

    return {
        "path": str(output_dir),
        "manifest": str(output_dir / "manifest.json"),
        "coverage": str(output_dir / "coverage.json"),
        "checksums": str(output_dir / "checksums.json"),
        "manifest_hash": checksums["files"]["manifest.json"],
        "checksums_hash": checksums_hash,
        "bundle_digest": checksums["bundle_digest"],
        "configuration_digest": configuration_digest,
        "commit": commit,
        "coverage_complete": coverage["complete"],
        "counts": counts,
        "complete": coverage["complete"],
        "reconciliation_eligible": coverage["reconciliation_eligible"],
        "validation": validation,
    }
