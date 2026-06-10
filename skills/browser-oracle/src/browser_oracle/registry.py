"""Parse registry YAML and resolve project names for a path."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from .bindings import BindingState, load as load_binding
from .walkup import RegistryHit, find_registry


@dataclass(frozen=True)
class ResolveResult:
    backend: str
    project: str
    registry_path: Path | None
    registry_root: Path | None
    relative_path: str
    source: str
    binding: BindingState | None
    binding_path: Path | None


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"registry must be a mapping: {path}")
    return data


def _backend_section(data: dict[str, Any], backend: str) -> dict[str, Any]:
    section = data.get(backend)
    if isinstance(section, dict):
        return section
    legacy = data.get("webgpt") if backend == "webgpt" else None
    if backend == "webgpt" and isinstance(legacy, dict):
        return legacy
    return {}


def _match_relative_path(section: dict[str, Any], relative: str) -> tuple[str | None, str]:
    by_path = section.get("by_relative_path") or section.get("paths") or {}
    if not isinstance(by_path, dict):
        by_path = {}
    rel = relative.replace("\\", "/").strip("/")
    if rel in by_path:
        return str(by_path[rel]), "by_relative_path.exact"
    best_key = ""
    best_project = None
    for key, value in by_path.items():
        key_norm = str(key).replace("\\", "/").strip("/")
        if not key_norm:
            continue
        if rel == key_norm or rel.startswith(key_norm + "/"):
            if len(key_norm) >= len(best_key):
                best_key = key_norm
                best_project = str(value)
    if best_project:
        return best_project, f"by_relative_path.prefix:{best_key}"
    lanes = section.get("lanes") or {}
    if isinstance(lanes, dict) and rel:
        parts = rel.split("/")
        node: Any = lanes
        for part in parts:
            if not isinstance(node, dict):
                break
            if part in node:
                node = node[part]
            elif "default" in node:
                node = node["default"]
                break
            else:
                node = None
                break
        if isinstance(node, str) and node.strip():
            return node.strip(), "lanes"
        if isinstance(node, dict) and isinstance(node.get("default"), str):
            return str(node["default"]).strip(), "lanes.default"
    default = section.get("default")
    if isinstance(default, str) and default.strip():
        return default.strip(), "default"
    return None, "missing"


def resolve_project_name(
    *,
    start: Path | str,
    backend: str = "webgpt",
    project_override: str = "",
    lane: str = "",
) -> tuple[str | None, RegistryHit | None, str, str]:
    if project_override.strip():
        hit = find_registry(start)
        rel = ""
        if hit is not None:
            try:
                rel = str(_normalize_start(Path(start)).relative_to(hit.registry_root))
            except ValueError:
                rel = ""
        return project_override.strip(), hit, rel, "cli.project_override"

    hit = find_registry(start)
    if hit is None:
        return None, None, "", "no_registry"

    data = _load_yaml(hit.registry_path)
    section = _backend_section(data, backend)
    try:
        rel = str(_normalize_start(Path(start)).relative_to(hit.registry_root))
    except ValueError:
        rel = ""

    if lane.strip():
        lanes = section.get("lanes") or {}
        if isinstance(lanes, dict):
            value = lanes.get(lane.strip())
            if isinstance(value, str) and value.strip():
                return value.strip(), hit, rel, f"lane:{lane.strip()}"

    project, source = _match_relative_path(section, rel)
    return project, hit, rel, source


def _normalize_start(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.is_file():
        return resolved.parent
    return resolved


def resolve_project(
    *,
    start: Path | str,
    backend: str = "webgpt",
    project_override: str = "",
    lane: str = "",
    bindings_root: Path | None = None,
) -> ResolveResult:
    project, hit, rel, source = resolve_project_name(
        start=start,
        backend=backend,
        project_override=project_override,
        lane=lane,
    )
    binding = None
    binding_path = None
    if project:
        binding = load_binding(project, backend, root=bindings_root)
        if binding is not None:
            from .bindings import state_path

            binding_path = state_path(project, backend, root=bindings_root)
    return ResolveResult(
        backend=backend,
        project=project or "",
        registry_path=hit.registry_path if hit else None,
        registry_root=hit.registry_root if hit else None,
        relative_path=rel.replace("\\", "/"),
        source=source,
        binding=binding,
        binding_path=binding_path,
    )


def register_mapping(
    *,
    registry_root: Path,
    backend: str,
    project: str,
    relative_path: str = "",
    as_default: bool = False,
) -> Path:
    container = Path(registry_root) / ".ask"
    container.mkdir(parents=True, exist_ok=True)
    path = container / "browser-oracles.yaml"
    data: dict[str, Any]
    if path.exists():
        data = _load_yaml(path)
    else:
        data = {"version": 1}
    section = _backend_section(data, backend)
    if not section:
        section = {}
        data[backend] = section
    if as_default or not relative_path.strip():
        section["default"] = project
    else:
        by_path = section.setdefault("by_relative_path", {})
        if not isinstance(by_path, dict):
            by_path = {}
            section["by_relative_path"] = by_path
        key = relative_path.replace("\\", "/").strip("/")
        by_path[key] = project
    path.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=False))
    logger.info("updated registry at {}", path)
    return path
