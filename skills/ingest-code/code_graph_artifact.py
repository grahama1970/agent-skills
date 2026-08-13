"""Deterministic code graph artifact bundle writer for ingest-code."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from code_edge_record import CodeEdgeRecord
from code_symbol_record import CodeSymbolRecord
from debug_affordance import build_debug_invocation_candidates

SCHEMA_VERSION = "ingest-code.code_graph_bundle.v1"
ARTIFACT_FILENAMES = (
    "manifest.json",
    "files.jsonl",
    "symbols.jsonl",
    "edges.jsonl",
    "debug_invocations.jsonl",
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


def _source_hash(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


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


def _file_records(
    *,
    root: Path,
    repo: str,
    branch: str,
    files: list[Path],
    ignored_files: list[Path],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    records: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    ids_by_path: dict[str, str] = {}

    for path in sorted(files, key=lambda item: normalized_rel_path(item, root)):
        rel_path = normalized_rel_path(path, root)
        language = _language_for_path(path)
        status = "parsed"
        reason = ""
        if language in {"markdown", "unknown"}:
            status = "skipped"
            reason = "unsupported_language"
        parse_error = _python_parse_error(path)
        if parse_error:
            status = "failed"
            reason = "parse_error"
        current_file_id = file_id(repo, branch, rel_path)
        ids_by_path[rel_path] = current_file_id
        record = {
            "file_id": current_file_id,
            "path": rel_path,
            "language": language,
            "status": status,
            "reason": reason,
            "size_bytes": path.stat().st_size if path.exists() else 0,
            "source_hash": _source_hash(path),
        }
        records.append(record)
        if reason:
            diagnostics.append({
                "diagnostic_id": _sha256_id("cd", [current_file_id, reason]),
                "file_id": current_file_id,
                "path": rel_path,
                "severity": "error" if status == "failed" else "info",
                "reason": reason,
                "message": parse_error or reason,
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
            "size_bytes": path.stat().st_size if path.exists() else 0,
            "source_hash": _source_hash(path),
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
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for symbol in symbols:
        rel_path = symbol.normalized_path
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
            "source_docstring": document.get("source_docstring", ""),
            "source_docstring_status": document.get("source_docstring_status", ""),
            "documentation_need": document.get("documentation_need", ""),
            "documentation_need_reasons": document.get("documentation_need_reasons", []),
            "summary_evidence": document.get("summary_evidence", {}),
            "derived_summary": document.get("derived_summary"),
            "semantic_input_schema": document.get("semantic_input_schema", ""),
            "retrieval_text_sha256": document.get("retrieval_text_sha256", ""),
            "purpose_source": document.get("purpose_source", ""),
            "memory_document": document,
        })
    return sorted(records, key=lambda item: (item["path"], item["qualified_name"], item["start_line"]))


def _name_from_ast_node(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _name_from_ast_node(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Subscript):
        return _name_from_ast_node(node.value)
    return ""


def _module_name_for_path(rel_path: str) -> str:
    path = Path(rel_path)
    parts = list(path.parts)
    if not parts:
        return ""
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1].removesuffix(path.suffix)
    return ".".join(part for part in parts if part)


def _module_paths(root: Path, files: list[Path]) -> dict[str, str]:
    paths: dict[str, str] = {}
    for path in files:
        if path.suffix != ".py":
            continue
        rel_path = normalized_rel_path(path, root)
        module = _module_name_for_path(rel_path)
        if module:
            paths[module] = rel_path
            parts = module.split(".")
            for idx in range(1, len(parts)):
                paths.setdefault(".".join(parts[idx:]), rel_path)
    return paths


def _symbol_indexes(symbols: list[CodeSymbolRecord]) -> dict[str, Any]:
    by_path: dict[str, list[CodeSymbolRecord]] = {}
    by_name: dict[str, list[CodeSymbolRecord]] = {}
    by_qualified: dict[str, list[CodeSymbolRecord]] = {}
    class_symbols: dict[str, list[CodeSymbolRecord]] = {}
    for symbol in symbols:
        by_path.setdefault(symbol.normalized_path, []).append(symbol)
        by_name.setdefault(symbol.symbol_name, []).append(symbol)
        by_qualified.setdefault(symbol.qualified_name, []).append(symbol)
        if symbol.symbol_kind == "class":
            class_symbols.setdefault(symbol.symbol_name, []).append(symbol)
    return {
        "by_path": by_path,
        "by_name": by_name,
        "by_qualified": by_qualified,
        "class_symbols": class_symbols,
    }


def _span_from_line(path: Path, line: int, needle: str = "") -> tuple[int, int, int, int]:
    start_line = max(1, int(line or 1))
    end_line = start_line
    try:
        text = path.read_text(errors="ignore").splitlines()[start_line - 1]
    except (IndexError, OSError):
        return start_line, end_line, 0, 0
    if needle:
        found = text.find(needle)
        if found >= 0:
            return start_line, end_line, found, found + len(needle)
    return start_line, end_line, 0, len(text)


def _single_or_candidates(candidates: list[CodeSymbolRecord]) -> tuple[CodeSymbolRecord | None, list[CodeSymbolRecord]]:
    ordered = sorted(candidates, key=lambda item: (item.normalized_path, item.qualified_name, item.start_line))
    if len(ordered) == 1:
        return ordered[0], []
    return None, ordered


def _python_class_bases(root: Path, files: list[Path]) -> dict[str, list[dict[str, Any]]]:
    bases: dict[str, list[dict[str, Any]]] = {}
    for path in files:
        if path.suffix != ".py":
            continue
        try:
            tree = ast.parse(path.read_text(errors="ignore"))
        except (SyntaxError, OSError):
            continue
        rel_path = normalized_rel_path(path, root)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            entries: list[dict[str, Any]] = []
            for base in node.bases:
                raw_reference = _name_from_ast_node(base)
                if not raw_reference:
                    continue
                line = int(getattr(base, "lineno", getattr(node, "lineno", 1)) or 1)
                col = int(getattr(base, "col_offset", 0) or 0)
                end_col = int(getattr(base, "end_col_offset", col + len(raw_reference)) or (col + len(raw_reference)))
                entries.append({
                    "class_name": node.name,
                    "base_name": raw_reference.split(".")[-1],
                    "raw_reference": raw_reference,
                    "source_path": rel_path,
                    "source_start_line": line,
                    "source_end_line": int(getattr(base, "end_lineno", line) or line),
                    "source_start_column": col,
                    "source_end_column": end_col,
                })
            if entries:
                bases[node.name] = entries
    return bases


def _relative_import_module(
    *,
    filepath: Path,
    root: Path,
    module: str,
    level: int,
) -> str:
    if level <= 0:
        return module
    try:
        rel = filepath.resolve().relative_to(root.resolve())
    except ValueError:
        return module
    package_parts = list(rel.parent.parts)
    keep_count = max(0, len(package_parts) - level + 1)
    prefix = package_parts[:keep_count]
    module_parts = [part for part in module.split(".") if part]
    return ".".join([*prefix, *module_parts])


def _python_import_aliases(root: Path, files: list[Path]) -> dict[str, dict[str, str]]:
    aliases_by_path: dict[str, dict[str, str]] = {}
    for path in files:
        if path.suffix != ".py":
            continue
        try:
            tree = ast.parse(path.read_text(errors="ignore"))
        except (SyntaxError, OSError):
            continue
        rel_path = normalized_rel_path(path, root)
        aliases: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    exposed = alias.asname or alias.name.split(".", 1)[0]
                    aliases[exposed] = f"module:{alias.name}"
            elif isinstance(node, ast.ImportFrom):
                base_module = _relative_import_module(
                    filepath=path,
                    root=root,
                    module=node.module or "",
                    level=int(node.level or 0),
                )
                for alias in node.names:
                    exposed = alias.asname or alias.name
                    target = ".".join(part for part in [base_module, alias.name] if part)
                    aliases[exposed] = f"symbol:{target}" if target else f"symbol:{alias.name}"
        aliases_by_path[rel_path] = aliases
    return aliases_by_path


def _find_enclosing_symbol(
    symbols_for_path: list[CodeSymbolRecord],
    line: int,
) -> CodeSymbolRecord | None:
    candidates = [
        symbol for symbol in symbols_for_path
        if symbol.start_line <= line <= symbol.end_line and symbol.symbol_kind in {"function", "method"}
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item.start_line, item.end_line))


def _python_call_occurrences(
    *,
    root: Path,
    files: list[Path],
    indexes: dict[str, Any],
) -> list[dict[str, Any]]:
    occurrences: list[dict[str, Any]] = []
    by_path = indexes["by_path"]
    for path in files:
        if path.suffix != ".py":
            continue
        try:
            tree = ast.parse(path.read_text(errors="ignore"))
        except (SyntaxError, OSError):
            continue
        rel_path = normalized_rel_path(path, root)
        symbols_for_path = by_path.get(rel_path, [])
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            raw_reference = _name_from_ast_node(node.func)
            if not raw_reference:
                continue
            caller = _find_enclosing_symbol(symbols_for_path, int(getattr(node, "lineno", 1) or 1))
            if caller is None:
                continue
            start_line = int(getattr(node, "lineno", caller.start_line) or caller.start_line)
            start_col = int(getattr(node, "col_offset", 0) or 0)
            end_line = int(getattr(node, "end_lineno", start_line) or start_line)
            end_col = int(getattr(node, "end_col_offset", start_col + len(raw_reference)) or (start_col + len(raw_reference)))
            occurrences.append({
                "caller": caller,
                "raw_reference": raw_reference,
                "source_path": rel_path,
                "source_start_line": start_line,
                "source_end_line": end_line,
                "source_start_column": start_col,
                "source_end_column": end_col,
            })
    return sorted(
        occurrences,
        key=lambda item: (
            item["source_path"],
            item["source_start_line"],
            item["source_start_column"],
            item["raw_reference"],
        ),
    )


def _resolve_call(
    *,
    caller: CodeSymbolRecord,
    raw_reference: str,
    indexes: dict[str, Any],
    inheritance: dict[str, list[str]],
    import_aliases: dict[str, dict[str, str]],
    module_path_index: dict[str, str],
) -> tuple[CodeSymbolRecord | None, list[CodeSymbolRecord], str, str]:
    by_path = indexes["by_path"]
    by_name = indexes["by_name"]
    by_qualified = indexes["by_qualified"]
    last_name = raw_reference.split(".")[-1]
    aliases = import_aliases.get(caller.normalized_path, {})

    alias_head, _, alias_tail = raw_reference.partition(".")
    if alias_head in aliases:
        target_ref = aliases[alias_head]
        ref_kind, _, ref_value = target_ref.partition(":")
        target_module = ref_value
        target_name = alias_tail or ref_value.split(".")[-1]
        if ref_kind == "symbol":
            parts = ref_value.split(".")
            target_name = alias_tail or parts[-1]
            target_module = ".".join(parts[:-1])
        target_path = module_path_index.get(target_module)
        if target_path:
            matches = [
                item
                for item in by_path.get(target_path, [])
                if item.symbol_name == target_name or item.qualified_name.endswith(f".{target_name}")
            ]
            exact, candidates = _single_or_candidates(matches)
            if exact:
                return exact, [], "explicit_import_alias_and_scope", ""
            if candidates:
                return None, candidates, "explicit_import_alias_and_scope", "ambiguous_import_alias_target"

    if "." in raw_reference:
        exact, candidates = _single_or_candidates(list(by_qualified.get(raw_reference, [])))
        if exact:
            return exact, [], "exact_qualified_reference", ""
        if candidates:
            return None, candidates, "exact_qualified_reference", "ambiguous_exact_qualified_reference"

    local_matches = [
        item
        for item in by_path.get(caller.normalized_path, [])
        if item.symbol_name == last_name or item.qualified_name.endswith(f".{last_name}")
    ]
    exact, candidates = _single_or_candidates(local_matches)
    if exact:
        return exact, [], "local_lexical_scope", ""
    if candidates:
        return None, candidates, "local_lexical_scope", "ambiguous_local_symbol"

    if raw_reference.startswith("self.") and "." in caller.qualified_name:
        class_name = caller.qualified_name.rsplit(".", 1)[0]
        for base_name in inheritance.get(class_name, []):
            qualified = f"{base_name}.{last_name}"
            exact, candidates = _single_or_candidates(list(by_qualified.get(qualified, [])))
            if exact:
                return exact, [], "enclosing_class_and_inheritance_scope", ""
            if candidates:
                return None, candidates, "enclosing_class_and_inheritance_scope", "ambiguous_inherited_symbol"

    exact, candidates = _single_or_candidates(list(by_name.get(last_name, [])))
    if exact:
        return exact, [], "same_module_package", ""
    if candidates:
        return None, candidates, "same_module_package", "ambiguous_same_named_symbols"

    return None, [], "candidate_or_unresolved", "unresolved_symbol_reference"


def _edge_records(
    *,
    root: Path,
    repo: str,
    branch: str,
    edges: list[dict[str, Any]],
    ids_by_path: dict[str, str],
    symbols: list[CodeSymbolRecord],
    files: list[Path],
) -> list[dict[str, Any]]:
    records: list[CodeEdgeRecord] = []
    indexes = _symbol_indexes(symbols)
    import_aliases = _python_import_aliases(root, files)
    module_path_index = _module_paths(root, files)
    symbol_ids = {symbol.symbol_id for symbol in symbols}
    file_ids = set(ids_by_path.values())

    for symbol in symbols:
        source_file_id = ids_by_path.get(symbol.normalized_path) or file_id(repo, branch, symbol.normalized_path)
        records.append(CodeEdgeRecord(
            from_id=source_file_id,
            from_entity_type="file",
            to_id=symbol.symbol_id,
            to_entity_type="symbol",
            edge_type="DEFINES",
            resolution_status="resolved",
            resolution_method="treesitter_symbol_extraction",
            confidence=1.0,
            provenance="static_exact",
            source_path=symbol.normalized_path,
            source_start_line=symbol.start_line,
            source_end_line=symbol.end_line,
            source_start_column=0,
            source_end_column=0,
            active_for_traversal=True,
        ))

    for edge in edges:
        from_rel = normalized_rel_path(Path(edge["from_file"]), root)
        source_file_id = ids_by_path.get(from_rel) or file_id(repo, branch, from_rel)
        names = sorted(str(name) for name in edge.get("names", []) if str(name))
        raw_reference = str(edge.get("module") or "")
        resolution_status = str(edge.get("resolution_status") or ("resolved" if edge.get("to_file") else "unresolved"))
        to_rel = normalized_rel_path(Path(edge["to_file"]), root) if edge.get("to_file") else ""
        target_file_id = (ids_by_path.get(to_rel) or file_id(repo, branch, to_rel)) if to_rel else None
        candidate_paths = sorted(str(item) for item in edge.get("candidate_files", []) if str(item))
        candidate_descriptors = [normalized_rel_path(Path(path), root) for path in candidate_paths]
        candidate_ids = [ids_by_path.get(path) or file_id(repo, branch, path) for path in candidate_descriptors]
        if edge.get("col_offset") is not None:
            line = int(edge.get("line") or 1)
            end_line = int(edge.get("end_line") or line)
            col = int(edge.get("col_offset") or 0)
            end_col = int(edge.get("end_col_offset") or col)
        else:
            line, end_line, col, end_col = _span_from_line(Path(edge["from_file"]), int(edge.get("line") or 1), raw_reference)
        edge_type = "IMPORTS"
        records.append(CodeEdgeRecord(
            from_id=source_file_id,
            from_entity_type="file",
            to_id=target_file_id,
            to_entity_type="file" if target_file_id else None,
            edge_type=edge_type,
            resolution_status=resolution_status,  # type: ignore[arg-type]
            resolution_method=str(edge.get("resolution_method") or "python_import_alias_and_scope"),
            confidence=1.0 if resolution_status == "resolved" else 0.0,
            provenance="static_import" if resolution_status == "resolved" else "static_import_unresolved",
            source_path=from_rel,
            source_start_line=line,
            source_end_line=end_line,
            source_start_column=col,
            source_end_column=end_col,
            active_for_traversal=resolution_status == "resolved",
            raw_reference=raw_reference,
            candidate_ids=candidate_ids,
            candidate_descriptors=candidate_descriptors,
            unresolved_reason=str(edge.get("unresolved_reason") or ("" if resolution_status == "resolved" else "module_not_in_scan")),
            attempted_resolution_stages=list(edge.get("attempted_resolution_stages") or ["exact_qualified_reference", "explicit_import_alias_and_scope", "candidate_or_unresolved"]),
            legacy_fields={
                "source_file_id": source_file_id,
                "target_file_id": target_file_id,
                "from_path": from_rel,
                "to_path": to_rel or None,
                "module": raw_reference,
                "names": names,
            },
        ))

    class_base_entries = _python_class_bases(root, files)
    inheritance = {
        class_name: [entry["base_name"] for entry in entries]
        for class_name, entries in class_base_entries.items()
    }
    for class_name, entries in class_base_entries.items():
        class_symbol, _ = _single_or_candidates(indexes["class_symbols"].get(class_name, []))
        if not class_symbol:
            continue
        for entry in entries:
            base_symbol, base_candidates = _single_or_candidates(indexes["class_symbols"].get(entry["base_name"], []))
            status = "resolved" if base_symbol else ("candidate" if base_candidates else "unresolved")
            records.append(CodeEdgeRecord(
                from_id=class_symbol.symbol_id,
                from_entity_type="symbol",
                to_id=base_symbol.symbol_id if base_symbol else None,
                to_entity_type="symbol" if base_symbol else None,
                edge_type="INHERITS",
                resolution_status=status,  # type: ignore[arg-type]
                resolution_method="enclosing_class_and_inheritance_scope",
                confidence=1.0 if status == "resolved" else 0.0,
                provenance="static_exact" if status == "resolved" else "heuristic",
                source_path=entry["source_path"],
                source_start_line=entry["source_start_line"],
                source_end_line=entry["source_end_line"],
                source_start_column=entry["source_start_column"],
                source_end_column=entry["source_end_column"],
                active_for_traversal=status == "resolved",
                raw_reference=entry["raw_reference"],
                candidate_ids=[item.symbol_id for item in base_candidates],
                candidate_descriptors=[f"{item.normalized_path}:{item.qualified_name}" for item in base_candidates],
                unresolved_reason="" if status == "resolved" else ("ambiguous_base_class" if base_candidates else "base_class_not_in_scan"),
                attempted_resolution_stages=["exact_qualified_reference", "enclosing_class_and_inheritance_scope", "candidate_or_unresolved"],
            ))

    for occurrence in _python_call_occurrences(root=root, files=files, indexes=indexes):
        caller = occurrence["caller"]
        raw_reference = occurrence["raw_reference"]
        target, candidates, method, unresolved_reason = _resolve_call(
            caller=caller,
            raw_reference=raw_reference,
            indexes=indexes,
            inheritance=inheritance,
            import_aliases=import_aliases,
            module_path_index=module_path_index,
        )
        status = "resolved" if target else ("candidate" if candidates else "unresolved")
        records.append(CodeEdgeRecord(
            from_id=caller.symbol_id,
            from_entity_type="symbol",
            to_id=target.symbol_id if target else None,
            to_entity_type="symbol" if target else None,
            edge_type="CALLS",
            resolution_status=status,  # type: ignore[arg-type]
            resolution_method=method,
            confidence=1.0 if status == "resolved" else 0.0,
            provenance="static_exact" if status == "resolved" else "heuristic",
            source_path=occurrence["source_path"],
            source_start_line=occurrence["source_start_line"],
            source_end_line=occurrence["source_end_line"],
            source_start_column=occurrence["source_start_column"],
            source_end_column=occurrence["source_end_column"],
            active_for_traversal=status == "resolved",
            raw_reference=raw_reference,
            candidate_ids=[item.symbol_id for item in candidates],
            candidate_descriptors=[f"{item.normalized_path}:{item.qualified_name}" for item in candidates],
            unresolved_reason=unresolved_reason,
            attempted_resolution_stages=[
                "exact_qualified_reference",
                "explicit_import_alias_and_scope",
                "local_lexical_scope",
                "enclosing_class_and_inheritance_scope",
                "same_module_package",
                "candidate_or_unresolved",
            ],
        ))

    serialized = [record.to_dict() for record in records]
    for record in serialized:
        if record["resolution_status"] == "resolved":
            if record["from_id"] not in file_ids and record["from_id"] not in symbol_ids:
                raise ValueError(f"resolved edge has unknown from_id: {record['edge_id']}")
            if record["to_id"] not in file_ids and record["to_id"] not in symbol_ids:
                raise ValueError(f"resolved edge has unknown to_id: {record['edge_id']}")
        elif record["active_for_traversal"]:
            raise ValueError(f"unresolved/candidate edge active for traversal: {record['edge_id']}")
    return sorted(serialized, key=lambda item: (item["source_path"], item["edge_type"], item["raw_reference"], item["edge_id"]))


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
    environment_manifest_digest: str | None = None,
) -> dict[str, Any]:
    """Write the deterministic ingest-code code graph bundle and return metadata."""
    root = codebase_root.resolve()
    output_dir = artifact_root or root / "artifacts" / "ingest-code" / "code-graph"
    output_dir.mkdir(parents=True, exist_ok=True)

    suffixes = {path.suffix for path in files if path.suffix}
    ignored = ignored_source_files(root, suffixes)
    file_records, diagnostics, ids_by_path = _file_records(
        root=root,
        repo=repo,
        branch=branch,
        files=files,
        ignored_files=ignored,
    )
    symbol_records = _symbol_records(root=root, repo=repo, branch=branch, symbols=symbols, ids_by_path=ids_by_path)
    edge_records = _edge_records(
        root=root,
        repo=repo,
        branch=branch,
        edges=edges,
        ids_by_path=ids_by_path,
        symbols=symbols,
        files=files,
    )
    debug_invocation_records = build_debug_invocation_candidates(
        root=root,
        repo=repo,
        branch=branch,
        commit=commit,
        symbols=symbols,
        files=files,
    )

    counts = {
        "files": len(file_records),
        "files_parsed": sum(1 for item in file_records if item["status"] == "parsed"),
        "files_failed": sum(1 for item in file_records if item["status"] == "failed"),
        "files_ignored": sum(1 for item in file_records if item["status"] == "ignored"),
        "files_skipped": sum(1 for item in file_records if item["status"] == "skipped"),
        "symbols": len(symbol_records),
        "edges": len(edge_records),
        "debug_invocation_candidates": 0,
        "edges_active_for_traversal": sum(1 for item in edge_records if item["active_for_traversal"]),
        "edges_candidate": sum(1 for item in edge_records if item["resolution_status"] == "candidate"),
        "edges_resolved": sum(1 for item in edge_records if item["resolution_status"] == "resolved"),
        "edges_unresolved": sum(1 for item in edge_records if item["resolution_status"] == "unresolved"),
        "debug_invocation_candidates": len(debug_invocation_records),
        "debug_invocation_runnable_static": sum(
            1 for item in debug_invocation_records if item["status"] == "candidate_static"
        ),
        "debug_invocation_needs_fixture": sum(
            1 for item in debug_invocation_records if item["status"] == "needs_fixture"
        ),
        "debug_invocation_unsafe_direct": sum(
            1 for item in debug_invocation_records if item["status"] == "unsafe_direct"
        ),
        "debug_invocation_attach_runtime": sum(
            1 for item in debug_invocation_records if item["status"] == "attach_runtime"
        ),
        "diagnostics": len(diagnostics),
    }
    coverage = {
        "schema_version": SCHEMA_VERSION,
        "complete": counts["files_failed"] == 0,
        "fail_closed": counts["files_failed"] > 0,
        "counts": counts,
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
        "counts": counts,
        "environment_manifest_digest": environment_manifest_digest,
    }

    payloads: dict[str, bytes] = {
        "manifest.json": _json_bytes(manifest),
        "files.jsonl": _jsonl_bytes(file_records),
        "symbols.jsonl": _jsonl_bytes(symbol_records),
        "edges.jsonl": _jsonl_bytes(edge_records),
        "debug_invocations.jsonl": _jsonl_bytes(debug_invocation_records),
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
        "debug_invocations": str(output_dir / "debug_invocations.jsonl"),
        "counts": counts,
        "complete": coverage["complete"],
    }
