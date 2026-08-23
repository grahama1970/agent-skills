"""Write dependency evidence consumed by the cleanup skill."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from code_graph_artifact import normalized_rel_path

CONTRACT = "cleanup.evidence.v1"
FILENAME = ".cleanup-evidence.json"
EDGE_RESOLVED_LANGUAGES = {"python"}


def _sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _git_blob_id(root: Path, rel_path: str) -> str:
    try:
        result = subprocess.run(
            ["git", "hash-object", "--", rel_path],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _language(path: Path) -> str:
    if path.suffix == ".py":
        return "python"
    if path.suffix in {".js", ".jsx"}:
        return "javascript"
    if path.suffix in {".ts", ".tsx"}:
        return "typescript"
    if path.suffix == ".rs":
        return "rust"
    if path.suffix == ".go":
        return "go"
    if path.suffix in {".sh", ".bash", ".zsh"}:
        return "shell"
    if path.suffix in {".md", ".mdx"}:
        return "markdown"
    return path.suffix.lstrip(".") or "unknown"


def _python_parse_status(path: Path) -> tuple[str, str]:
    if path.suffix != ".py":
        return "not_analyzed", ""
    try:
        ast.parse(path.read_text(errors="ignore"))
    except SyntaxError as exc:
        return "failed", str(exc)
    except OSError as exc:
        return "failed", str(exc)
    return "ok", ""


def _entry_kinds(path: Path, rel_path: str) -> list[str]:
    kinds: list[str] = []
    name = path.name
    if name in {"conftest.py", "__main__.py"}:
        kinds.append("pytest_conftest" if name == "conftest.py" else "module_main")
    if rel_path.startswith("tests/") and name.startswith("test_") and name.endswith(".py"):
        kinds.append("pytest_test")
    try:
        text = path.read_text(errors="ignore")
    except OSError:
        text = ""
    if path.suffix == ".py" and 'if __name__ == "__main__"' in text:
        kinds.append("script_main")
    if path.suffix in {".sh", ".bash", ".zsh"} and path.stat().st_mode & 0o111:
        kinds.append("script_main")
    return sorted(set(kinds))


def _dynamic_reference_warnings(path: Path, rel_path: str) -> list[dict[str, Any]]:
    if path.suffix != ".py":
        return []
    try:
        tree = ast.parse(path.read_text(errors="ignore"))
    except (SyntaxError, OSError):
        return []
    warnings: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        kind = ""
        if isinstance(func, ast.Name) and func.id == "__import__":
            kind = "__import__"
        elif (
            isinstance(func, ast.Attribute)
            and func.attr == "import_module"
            and isinstance(func.value, ast.Name)
            and func.value.id == "importlib"
        ):
            kind = "importlib"
        if not kind:
            continue
        first_arg = node.args[0] if node.args else None
        if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
            continue
        warnings.append({
            "from_path": rel_path,
            "kind": kind,
            "detail": f"{kind} call with non-literal module name",
            "line": int(getattr(node, "lineno", 0) or 0),
        })
    return warnings


def _edge_reference(edge: dict[str, Any], root: Path) -> dict[str, Any]:
    from_file = edge.get("from_file") or ""
    try:
        from_path = normalized_rel_path(Path(from_file), root)
    except ValueError:
        from_path = str(from_file)
    return {
        "from_path": from_path,
        "kind": "static_import",
        "module": edge.get("module", ""),
        "names": edge.get("names", []),
        "line": edge.get("line"),
    }


def write_cleanup_evidence(
    *,
    codebase_root: Path,
    files: list[Path],
    edges: list[dict[str, Any]],
) -> dict[str, Any]:
    """Write `.cleanup-evidence.json` for exactly the scanned file set."""
    root = codebase_root.resolve()
    by_rel_path: dict[str, Path] = {}
    for file_path in files:
        try:
            by_rel_path[normalized_rel_path(file_path, root)] = file_path.resolve()
        except ValueError:
            continue

    inbound_by_path: dict[str, list[dict[str, Any]]] = {rel: [] for rel in by_rel_path}
    outbound_by_path: dict[str, list[dict[str, Any]]] = {rel: [] for rel in by_rel_path}
    for edge in edges:
        if edge.get("resolution_status", "resolved") != "resolved" or not edge.get("to_file"):
            continue
        try:
            from_rel = normalized_rel_path(Path(edge["from_file"]), root)
            to_rel = normalized_rel_path(Path(edge["to_file"]), root)
        except (KeyError, ValueError):
            continue
        reference = _edge_reference(edge, root)
        inbound_by_path.setdefault(to_rel, []).append(reference)
        outbound_by_path.setdefault(from_rel, []).append({
            "to_path": to_rel,
            "kind": "static_import",
            "module": edge.get("module", ""),
            "names": edge.get("names", []),
            "line": edge.get("line"),
        })

    scan_failures: list[dict[str, Any]] = []
    records: dict[str, dict[str, Any]] = {}
    parsed_without_edges: set[str] = set()
    for rel_path, file_path in sorted(by_rel_path.items()):
        language = _language(file_path)
        parse_status, parse_error = _python_parse_status(file_path)
        if language != "python":
            parsed_without_edges.add(language)
        if parse_error:
            scan_failures.append({"path": rel_path, "phase": "parse", "detail": parse_error})
        records[rel_path] = {
            "content_sha256": _sha256_file(file_path),
            "git_blob_id": _git_blob_id(root, rel_path),
            "language": language,
            "parse_status": parse_status,
            "symbol_count": 0,
            "outbound_edges": sorted(outbound_by_path.get(rel_path, []), key=lambda item: (item["to_path"], item["line"] or 0)),
            "inbound_references": sorted(inbound_by_path.get(rel_path, []), key=lambda item: (item["from_path"], item["line"] or 0)),
            "entrypoint_references": [],
            "entry_kinds": _entry_kinds(file_path, rel_path),
            "dynamic_reference_warnings": _dynamic_reference_warnings(file_path, rel_path),
        }

    payload = {
        "contract": CONTRACT,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository_path": str(root),
        "analysis_complete": True,
        "producer": "ingest-code scan --cleanup-evidence",
        "proof_scope": {
            "languages_with_resolved_edges": sorted(EDGE_RESOLVED_LANGUAGES),
            "languages_parsed_without_edges": sorted(parsed_without_edges - EDGE_RESOLVED_LANGUAGES),
            "edge_kinds": ["static_import"],
            "reference_sources": ["static_import", "entrypoint", "test"],
            "known_blind_spots": [
                "runtime importlib / __import__ resolution",
                "plugin discovery by naming convention",
                "shell and CI invocation of scripts by path",
                "template and data-file references",
            ],
        },
        "scan_failures": scan_failures,
        "files": records,
    }
    artifact = root / FILENAME
    artifact.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return {
        "path": str(artifact),
        "contract": CONTRACT,
        "file_count": len(records),
        "scan_failure_count": len(scan_failures),
        "analysis_complete": True,
    }
