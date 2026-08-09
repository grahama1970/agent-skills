"""File-component reuse state for complete ingest-code bundles."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

STATE_SCHEMA = "ingest-code.incremental_components.v1"
FINGERPRINT_SCHEMA = "ingest-code.transform_fingerprints.v1"


def _canonical_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_payload(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _git(root: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _is_tracked_and_clean(root: Path, rel_path: str) -> bool:
    tracked = _git(root, ["ls-files", "--error-unmatch", "--", rel_path])
    if not tracked:
        return False
    status = _git(root, ["status", "--porcelain", "--", rel_path])
    return status == ""


def source_fingerprint(path: Path, root: Path) -> str:
    """Return a Git blob fingerprint when authoritative, else exact bytes."""
    rel_path = path.resolve().relative_to(root.resolve()).as_posix()
    if _is_tracked_and_clean(root, rel_path):
        blob = _git(root, ["rev-parse", f"HEAD:{rel_path}"])
        if blob:
            return f"git-blob:{blob}"
    return _sha256_file(path)


def transform_fingerprint(name: str, sources: Iterable[Path], *, extra: str = "") -> str:
    digest = hashlib.sha256()
    digest.update(name.encode("utf-8"))
    for path in sorted((Path(item) for item in sources), key=lambda item: item.as_posix()):
        digest.update(path.name.encode("utf-8"))
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"\0missing\0")
    if extra:
        digest.update(extra.encode("utf-8"))
    return "sha256:" + digest.hexdigest()


def build_transform_fingerprints(skill_root: Path, *, scope: str, patterns: Iterable[str], scan_roots: Iterable[str]) -> dict[str, str]:
    """Build explicit layer fingerprints used to decide component reuse."""
    base = {
        "scope": scope,
        "patterns": sorted(str(item) for item in patterns),
        "scan_roots": sorted(str(item) for item in scan_roots),
    }
    return {
        "schema": FINGERPRINT_SCHEMA,
        "discovery_config": sha256_payload(base),
        "treesitter_parser": transform_fingerprint(
            "treesitter_parser",
            [skill_root / "ingest_code.py", skill_root / "treesitter_scan.py"],
            extra=scope,
        ),
        "symbol_identity_schema": transform_fingerprint(
            "symbol_identity_schema",
            [skill_root / "code_symbol_record.py"],
            extra=scope,
        ),
        "documentation_semantic_text": transform_fingerprint(
            "documentation_semantic_text",
            [skill_root / "code_symbol_record.py"],
            extra="solution-v1",
        ),
        "typed_edge_resolver": transform_fingerprint(
            "typed_edge_resolver",
            [skill_root / "code_graph_artifact.py"],
            extra="typed-edges-v1",
        ),
        "artifact_writer_schema": transform_fingerprint(
            "artifact_writer_schema",
            [skill_root / "code_graph_artifact.py"],
            extra="bundle-v1",
        ),
    }


def component_key(repo: str, branch: str, rel_path: str) -> str:
    basis = "\x1f".join([repo.strip(), branch.strip(), rel_path.replace("\\", "/").strip()])
    return "fc_" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:40]


@dataclass(frozen=True)
class ComponentPlan:
    added: tuple[str, ...] = ()
    changed: tuple[str, ...] = ()
    reused: tuple[str, ...] = ()
    deleted: tuple[str, ...] = ()
    miss_reasons: dict[str, str] = field(default_factory=dict)
    current_sources: dict[str, str] = field(default_factory=dict)

    @property
    def to_parse(self) -> tuple[str, ...]:
        return self.added + self.changed

    def summary(self) -> dict[str, Any]:
        return {
            "files_added": len(self.added),
            "files_changed": len(self.changed),
            "files_reused": len(self.reused),
            "files_deleted": len(self.deleted),
            "files_to_parse": len(self.to_parse),
            "miss_reasons": dict(sorted(self.miss_reasons.items())),
        }


class FileComponentState:
    """Disposable cache for parsed file components from accepted complete bundles."""

    def __init__(self, state_path: Path, *, repo: str, branch: str, transform_fingerprints: Mapping[str, str]):
        self.state_path = Path(state_path)
        self.repo = repo
        self.branch = branch
        self.transform_fingerprints = dict(transform_fingerprints)
        self._payload = self._load()

    def _load(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"schema": STATE_SCHEMA, "components": {}, "accepted_complete_bundle": False}
        if not isinstance(payload, dict) or payload.get("schema") != STATE_SCHEMA:
            return {"schema": STATE_SCHEMA, "components": {}, "accepted_complete_bundle": False}
        components = payload.get("components")
        if not isinstance(components, dict):
            payload["components"] = {}
        return payload

    @property
    def components(self) -> dict[str, dict[str, Any]]:
        raw = self._payload.get("components")
        return raw if isinstance(raw, dict) else {}

    def plan(self, files: Iterable[Path], root: Path) -> ComponentPlan:
        current_sources: dict[str, str] = {}
        added: list[str] = []
        changed: list[str] = []
        reused: list[str] = []
        miss_reasons: dict[str, str] = {}
        root = root.resolve()
        for path in sorted(files, key=lambda item: item.resolve().as_posix()):
            if not path.exists():
                continue
            rel_path = path.resolve().relative_to(root).as_posix()
            current_source = source_fingerprint(path, root)
            current_sources[rel_path] = current_source
            component = self.components.get(rel_path)
            if component is None:
                added.append(rel_path)
                miss_reasons[rel_path] = "missing_component"
                continue
            reason = self._reuse_blocker(component, current_source)
            if reason:
                changed.append(rel_path)
                miss_reasons[rel_path] = reason
            else:
                reused.append(rel_path)
        deleted = [rel_path for rel_path in self.components if rel_path not in current_sources]
        return ComponentPlan(
            added=tuple(sorted(added)),
            changed=tuple(sorted(changed)),
            reused=tuple(sorted(reused)),
            deleted=tuple(sorted(deleted)),
            miss_reasons=miss_reasons,
            current_sources=current_sources,
        )

    def _reuse_blocker(self, component: Mapping[str, Any], current_source: str) -> str:
        if not self._payload.get("accepted_complete_bundle"):
            return "prior_bundle_not_complete"
        if component.get("source_fingerprint") != current_source:
            return "source_fingerprint_changed"
        if component.get("transform_fingerprints") != self.transform_fingerprints:
            return "transform_fingerprint_changed"
        symbols = component.get("symbols")
        if not isinstance(symbols, list):
            return "missing_symbols"
        expected_hash = component.get("component_hash")
        actual_hash = sha256_payload({
            "source_fingerprint": current_source,
            "transform_fingerprints": self.transform_fingerprints,
            "symbols": symbols,
        })
        if expected_hash != actual_hash:
            return "component_hash_mismatch"
        return ""

    def reused_symbols(self, rel_paths: Iterable[str]) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for rel_path in sorted(rel_paths):
            component = self.components.get(rel_path) or {}
            symbols = component.get("symbols")
            if isinstance(symbols, list):
                records.extend(item for item in symbols if isinstance(item, dict))
        return records

    def commit(
        self,
        *,
        current_sources: Mapping[str, str],
        symbols_by_path: Mapping[str, list[Mapping[str, Any]]],
        bundle_digest: str,
        accepted_complete_bundle: bool,
        receipt: Mapping[str, Any],
    ) -> Path:
        components: dict[str, dict[str, Any]] = {}
        for rel_path, source in sorted(current_sources.items()):
            symbols = [dict(item) for item in symbols_by_path.get(rel_path, [])]
            components[rel_path] = {
                "component_key": component_key(self.repo, self.branch, rel_path),
                "repo": self.repo,
                "branch": self.branch,
                "path": rel_path,
                "source_fingerprint": source,
                "transform_fingerprints": self.transform_fingerprints,
                "symbols": symbols,
                "component_hash": sha256_payload({
                    "source_fingerprint": source,
                    "transform_fingerprints": self.transform_fingerprints,
                    "symbols": symbols,
                }),
            }
        payload = {
            "schema": STATE_SCHEMA,
            "repo": self.repo,
            "branch": self.branch,
            "accepted_complete_bundle": bool(accepted_complete_bundle),
            "bundle_digest": bundle_digest,
            "transform_fingerprints": self.transform_fingerprints,
            "components": components,
            "last_receipt": dict(receipt),
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=str(self.state_path.parent), delete=False, suffix=".tmp"
        )
        try:
            with handle as fh:
                json.dump(payload, fh, indent=2, sort_keys=True)
                fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(handle.name, self.state_path)
        except BaseException:
            Path(handle.name).unlink(missing_ok=True)
            raise
        self._payload = payload
        return self.state_path
