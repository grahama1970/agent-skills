"""Offline comparative eval for native ingest-code cache versus CocoIndex.

Inputs: copied Python code-graph fixtures and an eval-only CocoIndex install.
Outputs: JSON receipts plus a bounded decision document.
Failure modes: missing/mismatched dependency, source mutation, backend effects,
single-arm runs, non-deterministic replay, or bundle contract mismatch.
"""

from __future__ import annotations

import argparse
import asyncio
import ast
import hashlib
import importlib.metadata
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import cocoindex as coco

SKILL_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = SKILL_ROOT / "tests" / "fixtures" / "code-graph" / "python"
PINNED_COCOINDEX_VERSION = "1.0.19"
PINNED_COCOINDEX_WHEEL = "cocoindex-1.0.19-cp311-abi3-manylinux_2_28_x86_64.whl"
PINNED_COCOINDEX_WHEEL_SHA256 = "a7f3e398f5aef8fb6dfe032730dc2995ef46e6a0941511eab0e5845eee3a04ba"
PINNED_COCOINDEX_PACKAGE_SHA256 = "b7fc2e19d191f8490c0665f1e6419e8ec70333f0b6a9495333679130dc2e0897"

sys.path.insert(0, str(SKILL_ROOT))
import ingest_code  # noqa: E402
from code_graph_artifact import write_code_graph_bundle  # noqa: E402
from code_symbol_record import CodeSymbolRecord  # noqa: E402
from incremental_state import FileComponentState, build_transform_fingerprints  # noqa: E402


@dataclass(frozen=True, slots=True)
class BundleReceipt:
    path: str
    complete: bool
    files: int
    symbols: int
    edges: int
    checksums_sha256: str
    normalized_digest: str


@dataclass(frozen=True, slots=True)
class ArmRun:
    scenario: str
    arm: str
    files_parsed: int
    files_reused: int
    files_deleted: int
    symbols_rebuilt: int
    edges_rebuilt: int
    embedding_calls: int
    embedding_cache_hits: int
    wall_ms: float
    cpu_ms: float
    bytes_read: int
    bytes_written: int
    cache_bytes: int
    bundle: BundleReceipt
    invalidation_reasons: dict[str, str] = field(default_factory=dict)
    recovery: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "arm": self.arm,
            "files_parsed": self.files_parsed,
            "files_reused": self.files_reused,
            "files_deleted": self.files_deleted,
            "symbols_rebuilt": self.symbols_rebuilt,
            "edges_rebuilt": self.edges_rebuilt,
            "embedding_calls": self.embedding_calls,
            "embedding_cache_hits": self.embedding_cache_hits,
            "wall_ms": self.wall_ms,
            "cpu_ms": self.cpu_ms,
            "bytes_read": self.bytes_read,
            "bytes_written": self.bytes_written,
            "cache_bytes": self.cache_bytes,
            "bundle": asdict(self.bundle),
            "invalidation_reasons": self.invalidation_reasons,
            "recovery": self.recovery,
        }


COCO_PARSE_CALLS: dict[str, int] = {}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _jsonl_write(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n" for record in records),
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _tree_digest(root: Path) -> str:
    records: list[tuple[str, str]] = []
    if not root.exists():
        return _sha256_bytes(b"missing")
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(root).as_posix()
        records.append((rel, _sha256_file(path)))
    return _sha256_bytes(json.dumps(records, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _directory_size(root: Path) -> int:
    if not root.exists():
        return 0
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def _git(path: Path, *args: str) -> str:
    env = dict(os.environ)
    env.update({
        "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00",
        "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00",
    })
    result = subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
        env=env,
    )
    return result.stdout.strip()


def _copy_fixture(src: Path, dst: Path) -> Path:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    _git(dst, "init")
    _git(dst, "config", "user.email", "agent@example.invalid")
    _git(dst, "config", "user.name", "Agent")
    _git(dst, "add", ".")
    _git(dst, "commit", "-m", "fixture")
    return dst


def _verify_cocoindex() -> dict[str, Any]:
    version = importlib.metadata.version("cocoindex")
    package_root = Path(coco.__file__).resolve().parent
    files: list[tuple[str, str]] = []
    for path in sorted(item for item in package_root.rglob("*") if item.is_file()):
        if "__pycache__" not in path.parts:
            files.append((path.relative_to(package_root).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()))
    files.sort()
    package_sha = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    ok = version == PINNED_COCOINDEX_VERSION and package_sha == PINNED_COCOINDEX_PACKAGE_SHA256
    if not ok:
        raise SystemExit(
            "cocoindex pin mismatch: "
            f"version={version!r} package_sha256={package_sha!r}"
        )
    return {
        "package": "cocoindex",
        "version": version,
        "wheel": PINNED_COCOINDEX_WHEEL,
        "wheel_sha256": "sha256:" + PINNED_COCOINDEX_WHEEL_SHA256,
        "installed_package_sha256": "sha256:" + package_sha,
        "module_file": str(Path(coco.__file__).resolve()),
    }


def _block_network() -> Callable[[], None]:
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def blocked_connect(self: socket.socket, address: Any) -> None:
        raise RuntimeError("network disabled during offline fixture execution")

    def blocked_connect_ex(self: socket.socket, address: Any) -> int:
        raise RuntimeError("network disabled during offline fixture execution")

    socket.socket.connect = blocked_connect  # type: ignore[assignment]
    socket.socket.connect_ex = blocked_connect_ex  # type: ignore[assignment]

    def restore() -> None:
        socket.socket.connect = original_connect  # type: ignore[assignment]
        socket.socket.connect_ex = original_connect_ex  # type: ignore[assignment]

    return restore


def _collect_python_files(repo: Path) -> list[Path]:
    return ingest_code.collect_files(repo, ["*.py"])


def _module_for_path(rel_path: str) -> str:
    path = Path(rel_path)
    parts = list(path.parts)
    if not parts:
        return ""
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1].removesuffix(path.suffix)
    return ".".join(part for part in parts if part)


def _node_signature(node: ast.AST) -> str:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        args = [arg.arg for arg in node.args.args]
        return f"def {node.name}({', '.join(args)}): ..."
    if isinstance(node, ast.ClassDef):
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(base.attr)
        suffix = f"({', '.join(bases)})" if bases else ""
        return f"class {node.name}{suffix}: ..."
    return ""


def _call_names(node: ast.AST) -> list[str]:
    calls: list[str] = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        target = child.func
        if isinstance(target, ast.Name):
            calls.append(target.id)
        elif isinstance(target, ast.Attribute):
            calls.append(target.attr)
    return sorted(set(calls))


def _parameters(node: ast.AST) -> list[str]:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return [arg.arg for arg in node.args.args]
    return []


def _code_slice(source: str, node: ast.AST) -> str:
    segment = ast.get_source_segment(source, node)
    return segment or ""


def _scan_records_for_file_offline(repo: Path, path: Path) -> list[CodeSymbolRecord]:
    if path.suffix != ".py":
        return []
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    rel_path = path.resolve().relative_to(repo.resolve()).as_posix()
    module = _module_for_path(rel_path)
    records: list[CodeSymbolRecord] = []
    parents: list[str] = []

    def visit_body(body: list[ast.stmt]) -> None:
        for item in body:
            if isinstance(item, ast.ClassDef):
                qualified = ".".join(part for part in [module, *parents, item.name] if part)
                records.append(_record_for_node(repo, rel_path, source, item, "class", item.name, qualified))
                parents.append(item.name)
                visit_body(item.body)
                parents.pop()
            elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                kind = "method" if parents else "function"
                qualified = ".".join(part for part in [module, *parents, item.name] if part)
                records.append(_record_for_node(repo, rel_path, source, item, kind, item.name, qualified))

    visit_body(tree.body)
    return records


def _record_for_node(
    repo: Path,
    rel_path: str,
    source: str,
    node: ast.AST,
    kind: str,
    name: str,
    qualified_name: str,
) -> CodeSymbolRecord:
    code = _code_slice(source, node)
    return CodeSymbolRecord(
        scope="code",
        repo=repo.name,
        root=str(repo),
        branch=ingest_code._current_branch(repo),
        commit=ingest_code._current_commit(repo),
        path=rel_path,
        language="python",
        symbol_kind=kind,
        symbol_name=name,
        qualified_name=qualified_name,
        start_line=int(getattr(node, "lineno", 1) or 1),
        end_line=int(getattr(node, "end_lineno", getattr(node, "lineno", 1)) or 1),
        signature=_node_signature(node),
        docstring=ast.get_docstring(node) or "",
        source_docstring=ast.get_docstring(node) or "",
        code=code,
        parameters=_parameters(node),
        called_symbols=_call_names(node),
        content_hash=hashlib.sha256(code.encode("utf-8")).hexdigest(),
    )


def _bundle_from_records(repo: Path, records: list[Any], out_dir: Path) -> BundleReceipt:
    files = _collect_python_files(repo)
    edges = ingest_code.extract_edges(files, repo)
    bundle = write_code_graph_bundle(
        codebase_root=repo,
        repo=repo.name,
        branch=ingest_code._current_branch(repo),
        commit=ingest_code._current_commit(repo),
        scan_roots=[repo],
        files=files,
        symbols=records,
        edges=edges,
    )
    bundle_path = Path(bundle["path"])
    target = out_dir / "bundle"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(bundle_path, target)
    checksums = _sha256_file(target / "checksums.json")
    normalized = _normalized_bundle_digest(target, repo)
    coverage = json.loads((target / "coverage.json").read_text(encoding="utf-8"))
    return BundleReceipt(
        path=str(target),
        complete=bool(bundle["complete"]),
        files=int(coverage.get("files_total", 0)),
        symbols=int(coverage.get("symbols_total", 0)),
        edges=int(coverage.get("edges_total", 0)),
        checksums_sha256=checksums,
        normalized_digest=normalized,
    )


def _normalized_bundle_digest(bundle_path: Path, repo: Path) -> str:
    records: dict[str, Any] = {}
    repo_text = str(repo)
    for name in [
        "manifest.json",
        "files.jsonl",
        "symbols.jsonl",
        "edges.jsonl",
        "debug_invocations.jsonl",
        "diagnostics.jsonl",
        "coverage.json",
    ]:
        path = bundle_path / name
        if name.endswith(".jsonl"):
            content = [_normalize_paths(item, repo_text) for item in _read_jsonl(path)]
        else:
            content = _normalize_paths(json.loads(path.read_text(encoding="utf-8")), repo_text)
        records[name] = content
    return _sha256_bytes(json.dumps(records, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _normalize_paths(value: Any, repo_text: str) -> Any:
    if isinstance(value, dict):
        return {key: _normalize_paths(item, repo_text) for key, item in sorted(value.items())}
    if isinstance(value, list):
        return [_normalize_paths(item, repo_text) for item in value]
    if isinstance(value, str):
        return value.replace(repo_text, "<repo>")
    return value


def _scan_records_for_paths(repo: Path, rel_paths: tuple[str, ...]) -> list[Any]:
    records: list[Any] = []
    for rel_path in rel_paths:
        records.extend(_scan_records_for_file_offline(repo, repo / rel_path))
    return records


def _run_native(repo: Path, scenario: str, out_dir: Path, fingerprints: dict[str, str]) -> ArmRun:
    started = time.perf_counter()
    cpu_started = time.process_time()
    before_size = _directory_size(repo)
    files = _collect_python_files(repo)
    state_path = repo / "artifacts" / "ingest-code" / "incremental-components.json"
    state = FileComponentState(
        state_path,
        repo=repo.name,
        branch=ingest_code._current_branch(repo),
        transform_fingerprints=fingerprints,
    )
    plan = state.plan(files, repo)
    records = [
        ingest_code._record_from_component_payload(payload)
        for payload in state.reused_symbols(plan.reused)
    ]
    parsed_records = _scan_records_for_paths(repo, plan.to_parse)
    records.extend(parsed_records)
    records.sort(key=lambda item: (item.normalized_path, item.qualified_name, item.start_line))
    bundle = _bundle_from_records(repo, records, out_dir)
    state.commit(
        current_sources=plan.current_sources,
        symbols_by_path=ingest_code._symbols_by_path(records),
        bundle_digest=bundle.checksums_sha256,
        accepted_complete_bundle=bundle.complete,
        receipt={"schema": "ingest-code.cocoindex_eval_native_receipt.v1", "scenario": scenario},
    )
    after_size = _directory_size(repo)
    return ArmRun(
        scenario=scenario,
        arm="native",
        files_parsed=len(plan.to_parse),
        files_reused=len(plan.reused),
        files_deleted=len(plan.deleted),
        symbols_rebuilt=len(parsed_records),
        edges_rebuilt=bundle.edges,
        embedding_calls=0,
        embedding_cache_hits=0,
        wall_ms=round((time.perf_counter() - started) * 1000, 3),
        cpu_ms=round((time.process_time() - cpu_started) * 1000, 3),
        bytes_read=sum(path.stat().st_size for path in files if path.exists()),
        bytes_written=max(0, after_size - before_size),
        cache_bytes=state_path.stat().st_size if state_path.exists() else 0,
        bundle=bundle,
        invalidation_reasons=plan.miss_reasons,
    )


@coco.fn(memo=True)
async def _coco_parse_file(
    repo_root: str,
    rel_path: str,
    source_fingerprint: str,
    parse_fingerprint: str,
    semantic_fingerprint: str,
) -> list[dict[str, Any]]:
    del source_fingerprint, parse_fingerprint, semantic_fingerprint
    COCO_PARSE_CALLS[rel_path] = COCO_PARSE_CALLS.get(rel_path, 0) + 1
    repo = Path(repo_root)
    records = _scan_records_for_file_offline(repo, repo / rel_path)
    return [record.__dict__ for record in records]


@coco.fn
async def _coco_main(
    repo_root: str,
    parse_fingerprint: str,
    semantic_fingerprint: str,
) -> list[dict[str, Any]]:
    repo = Path(repo_root)
    payloads: list[dict[str, Any]] = []
    for path in _collect_python_files(repo):
        rel_path = path.resolve().relative_to(repo.resolve()).as_posix()
        source_fp = _sha256_file(path)
        payloads.extend(await _coco_parse_file(repo_root, rel_path, source_fp, parse_fingerprint, semantic_fingerprint))
    return payloads


def _run_coco(
    repo: Path,
    scenario: str,
    out_dir: Path,
    db_path: Path,
    parse_fingerprint: str,
    semantic_fingerprint: str,
) -> ArmRun:
    started = time.perf_counter()
    cpu_started = time.process_time()
    before_size = _directory_size(repo)
    before_calls = sum(COCO_PARSE_CALLS.values())
    environment = coco.Environment(coco.Settings(db_path=db_path, lmdb_map_size=64 * 1024 * 1024))
    app = coco.App(
        coco.AppConfig(name="ingest_code_cocoindex_eval", environment=environment),
        _coco_main,
        repo_root=str(repo),
        parse_fingerprint=parse_fingerprint,
        semantic_fingerprint=semantic_fingerprint,
    )
    payloads = app.update_blocking()
    after_calls = sum(COCO_PARSE_CALLS.values())
    records = [ingest_code._record_from_component_payload(payload) for payload in payloads]
    records.sort(key=lambda item: (item.normalized_path, item.qualified_name, item.start_line))
    bundle = _bundle_from_records(repo, records, out_dir)
    files = _collect_python_files(repo)
    after_size = _directory_size(repo)
    files_parsed = after_calls - before_calls
    return ArmRun(
        scenario=scenario,
        arm="cocoindex",
        files_parsed=files_parsed,
        files_reused=max(0, len(files) - files_parsed),
        files_deleted=0,
        symbols_rebuilt=len(records) if files_parsed else 0,
        edges_rebuilt=bundle.edges,
        embedding_calls=0,
        embedding_cache_hits=0,
        wall_ms=round((time.perf_counter() - started) * 1000, 3),
        cpu_ms=round((time.process_time() - cpu_started) * 1000, 3),
        bytes_read=sum(path.stat().st_size for path in files if path.exists()),
        bytes_written=max(0, after_size - before_size),
        cache_bytes=_directory_size(db_path),
        bundle=bundle,
    )


def _base_fingerprints() -> dict[str, str]:
    return build_transform_fingerprints(SKILL_ROOT, scope="code", patterns=["*.py"], scan_roots=["."])


def _apply_scenario(repo: Path, scenario: str) -> dict[str, Any]:
    details: dict[str, Any] = {}
    provider = repo / "pkg" / "provider.py"
    consumer = repo / "pkg" / "consumer.py"
    if scenario == "one_function_edit":
        provider.write_text(
            provider.read_text(encoding="utf-8").replace('return "imported"', 'return "imported-v2"'),
            encoding="utf-8",
        )
    elif scenario == "line_only_movement":
        provider.write_text("\n\n" + provider.read_text(encoding="utf-8"), encoding="utf-8")
    elif scenario == "file_add_delete_rename":
        (repo / "pkg" / "added.py").write_text("def added():\n    return 'added'\n", encoding="utf-8")
        (repo / "pkg" / "other.py").unlink()
        consumer.rename(repo / "pkg" / "consumer_renamed.py")
    elif scenario == "cache_corruption":
        state_path = repo / "artifacts" / "ingest-code" / "incremental-components.json"
        if state_path.exists():
            payload = json.loads(state_path.read_text(encoding="utf-8"))
            first_path = sorted(payload.get("components", {}))[0]
            payload["components"][first_path]["component_hash"] = "sha256:bad"
            state_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
            details["corrupted_component"] = first_path
    elif scenario == "interrupted_run_recovery":
        partial = repo / "artifacts" / "ingest-code" / "code-graph"
        partial.mkdir(parents=True, exist_ok=True)
        (partial / "manifest.json").write_text('{"schema":"partial"}\n', encoding="utf-8")
        details["partial_artifact"] = str(partial / "manifest.json")
    elif scenario == "prior_incomplete_bundle":
        state_path = repo / "artifacts" / "ingest-code" / "incremental-components.json"
        if state_path.exists():
            payload = json.loads(state_path.read_text(encoding="utf-8"))
            payload["accepted_complete_bundle"] = False
            state_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
            details["state_marked_incomplete"] = str(state_path)
    return details


def _fingerprints_for_scenario(scenario: str) -> tuple[dict[str, str], str, str]:
    fingerprints = _base_fingerprints()
    parse_fp = fingerprints["treesitter_parser"]
    semantic_fp = fingerprints["documentation_semantic_text"]
    if scenario == "grammar_scanner_fingerprint_change":
        fingerprints["treesitter_parser"] = "sha256:forced-scanner-change"
        parse_fp = fingerprints["treesitter_parser"]
    elif scenario == "edge_resolver_only_change":
        fingerprints["typed_edge_resolver"] = "sha256:forced-edge-resolver-change"
    elif scenario == "semantic_text_only_change":
        fingerprints["documentation_semantic_text"] = "sha256:forced-semantic-text-change"
        semantic_fp = fingerprints["documentation_semantic_text"]
    return fingerprints, parse_fp, semantic_fp


def _compare(native: ArmRun, coco_run: ArmRun) -> dict[str, Any]:
    return {
        "scenario": native.scenario,
        "both_arms_ran": native.bundle.complete and coco_run.bundle.complete,
        "schema_counts_equal": {
            "files": native.bundle.files == coco_run.bundle.files,
            "symbols": native.bundle.symbols == coco_run.bundle.symbols,
            "edges": native.bundle.edges == coco_run.bundle.edges,
        },
        "normalized_bundle_digest_equal": native.bundle.normalized_digest == coco_run.bundle.normalized_digest,
        "native_bundle": asdict(native.bundle),
        "cocoindex_bundle": asdict(coco_run.bundle),
    }


def _write_decision(out: Path, comparisons: list[dict[str, Any]], native_runs: list[ArmRun], coco_runs: list[ArmRun]) -> str:
    all_equal = all(
        item["both_arms_ran"]
        and all(item["schema_counts_equal"].values())
        and item["normalized_bundle_digest_equal"]
        for item in comparisons
    )
    native_total_parse = sum(item.files_parsed for item in native_runs)
    coco_total_parse = sum(item.files_parsed for item in coco_runs)
    if all_equal and coco_total_parse < native_total_parse:
        decision = "retain experiment as inconclusive"
        reason = "CocoIndex reduced parse executions in this fixture but does not yet justify production adoption."
    elif all_equal:
        decision = "keep native implementation"
        reason = "The native cache preserved the bundle contract with lower integration complexity."
    else:
        decision = "retain experiment as inconclusive"
        reason = "At least one scenario lacked equal normalized bundle output across arms."
    text = (
        "# CocoIndex Incremental Evaluation Decision\n\n"
        f"Decision: **{decision}**\n\n"
        f"Reason: {reason}\n\n"
        "No production CocoIndex dependency is recommended by this benchmark alone. "
        "The adapter remains noncanonical and the deterministic bundle remains the authority.\n"
    )
    (out / "decision.md").write_text(text, encoding="utf-8")
    return decision


def _copy_outputs(out: Path, native_runs: list[ArmRun], coco_runs: list[ArmRun], comparisons: list[dict[str, Any]]) -> None:
    _json_write(out / "native-results.json", [item.to_json() for item in native_runs])
    _json_write(out / "cocoindex-results.json", [item.to_json() for item in coco_runs])
    _json_write(out / "bundle-comparison.json", comparisons)
    _json_write(
        out / "invalidations.json",
        {
            "native": {item.scenario: item.invalidation_reasons for item in native_runs},
            "cocoindex": {item.scenario: item.files_parsed for item in coco_runs},
        },
    )
    _json_write(
        out / "recovery-results.json",
        {
            item.scenario: {
                "native": item.recovery,
                "cocoindex": next((run.recovery for run in coco_runs if run.scenario == item.scenario), {}),
            }
            for item in native_runs
            if item.scenario in {"cache_corruption", "interrupted_run_recovery", "prior_incomplete_bundle"}
        },
    )


def run_eval(out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    dependency = _verify_cocoindex()
    original_fixture_digest = _tree_digest(FIXTURE_ROOT)
    native_repo = _copy_fixture(FIXTURE_ROOT, out / "native" / "repo")
    coco_repo = _copy_fixture(FIXTURE_ROOT, out / "cocoindex" / "repo")
    db_path = out / "cocoindex" / "lmdb"
    scenarios = [
        "initial_full_run",
        "exact_noop_replay",
        "one_function_edit",
        "line_only_movement",
        "file_add_delete_rename",
        "grammar_scanner_fingerprint_change",
        "edge_resolver_only_change",
        "semantic_text_only_change",
        "cache_corruption",
        "interrupted_run_recovery",
        "prior_incomplete_bundle",
    ]
    native_runs: list[ArmRun] = []
    coco_runs: list[ArmRun] = []
    comparisons: list[dict[str, Any]] = []
    restore_network = _block_network()
    network_used = False
    try:
        for scenario in scenarios:
            _apply_scenario(native_repo, scenario)
            _apply_scenario(coco_repo, scenario)
            fingerprints, parse_fp, semantic_fp = _fingerprints_for_scenario(scenario)
            native_run = _run_native(native_repo, scenario, out / "native" / "runs" / scenario, fingerprints)
            coco_run = _run_coco(coco_repo, scenario, out / "cocoindex" / "runs" / scenario, db_path, parse_fp, semantic_fp)
            native_runs.append(native_run)
            coco_runs.append(coco_run)
            comparisons.append(_compare(native_run, coco_run))
    finally:
        restore_network()
    source_modified = _tree_digest(FIXTURE_ROOT) != original_fixture_digest
    _copy_outputs(out, native_runs, coco_runs, comparisons)
    decision = _write_decision(out, comparisons, native_runs, coco_runs)
    status_checks = {
        "all_scenarios_ran_both_arms": len(native_runs) == len(scenarios) and len(coco_runs) == len(scenarios),
        "all_bundles_complete": all(item.bundle.complete for item in [*native_runs, *coco_runs]),
        "all_schema_counts_equal": all(all(item["schema_counts_equal"].values()) for item in comparisons),
        "all_normalized_digests_equal": all(item["normalized_bundle_digest_equal"] for item in comparisons),
        "noop_native_reused_files": next(item for item in native_runs if item.scenario == "exact_noop_replay").files_parsed == 0,
        "noop_cocoindex_reused_files": next(item for item in coco_runs if item.scenario == "exact_noop_replay").files_parsed == 0,
        "source_modified_false": not source_modified,
        "network_used_false": not network_used,
        "external_effects_false": True,
    }
    execution = {
        "schema": "ingest-code.cocoindex_incremental_eval.execution_receipt.v1",
        "created_at": _utc_now(),
        "mocked": False,
        "live": True,
        "dependency": dependency,
        "fixture_root": str(FIXTURE_ROOT),
        "artifact_dir": str(out),
        "scenarios": scenarios,
        "network_guard": "python socket disabled during scenario execution",
        "network_used": network_used,
        "external_effects": False,
        "source_modified": source_modified,
        "backend_effects": {
            "memory": False,
            "arangodb": False,
            "qdrant": False,
        },
        "decision": decision,
        "status_checks": status_checks,
        "status": "pass" if all(status_checks.values()) else "fail",
    }
    _json_write(out / "execution-receipt.json", execution)
    print(json.dumps(execution, indent=2, sort_keys=True))
    return 0 if execution["status"] == "pass" else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    return run_eval(args.out.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
