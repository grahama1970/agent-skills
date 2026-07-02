"""Registry loading for delegate resolution."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

from .models import DelegateError, DelegateRegistry, RegistryEntry, normalize_token


BROWSER_ORACLE_ENTRIES = (
    RegistryEntry(
        id="webgemini",
        kind="oracle",
        aliases=("gemini",),
        target_type="browser_oracle",
        default_mode="browser_review",
        allowed_modes=("browser_review", "oracle_review"),
        default_runtime="webgemini_browser",
        eligible_runtimes=("webgemini_browser",),
        title="WebGemini",
    ),
    RegistryEntry(
        id="webkimi",
        kind="oracle",
        aliases=("kimi",),
        target_type="browser_oracle",
        default_mode="browser_review",
        allowed_modes=("browser_review", "oracle_review"),
        default_runtime="webkimi_browser",
        eligible_runtimes=("webkimi_browser",),
        title="WebKimi",
    ),
    RegistryEntry(
        id="webperplexity",
        kind="oracle",
        aliases=("perplexity",),
        target_type="browser_oracle",
        default_mode="browser_research",
        allowed_modes=("browser_research", "oracle_review"),
        default_runtime="webperplexity_browser",
        eligible_runtimes=("webperplexity_browser",),
        title="WebPerplexity",
    ),
)

BUILTIN_PERSONA_ENTRIES = (
    RegistryEntry(
        id="brandon",
        kind="persona",
        aliases=("Brandon", "brandon-bailey"),
        target_type="persona",
        default_mode="persona_review",
        allowed_modes=("persona_review", "critique"),
        default_runtime="scillm_chat",
        eligible_runtimes=("scillm_chat",),
        title="Brandon",
        metadata={"source": "builtin_milestone_1_fixture"},
    ),
)


def load_delegate_registry(root: Path, *, include_builtins: bool = True) -> DelegateRegistry:
    """Load workers, skills, browser oracles, and milestone persona fixtures."""

    root = Path(root)
    entries: list[RegistryEntry] = []
    entries.extend(_load_agent_entries(root / "agents", root=root))
    entries.extend(_load_skill_entries(root / "skills", root=root))
    if include_builtins:
        entries.extend(BROWSER_ORACLE_ENTRIES)
        entries.extend(BUILTIN_PERSONA_ENTRIES)
    _validate_registry(entries)
    return DelegateRegistry(tuple(entries))


def _load_agent_entries(agents_dir: Path, *, root: Path) -> list[RegistryEntry]:
    if not agents_dir.is_dir():
        return []
    entries = []
    for agent_file in sorted(agents_dir.glob("*/AGENTS.md")):
        frontmatter = _read_frontmatter(agent_file)
        if not frontmatter:
            continue
        entry = _agent_entry_from_frontmatter(frontmatter, agent_file, root=root)
        if entry:
            entries.append(entry)
    return entries


def _agent_entry_from_frontmatter(data: dict[str, Any], path: Path, *, root: Path) -> RegistryEntry | None:
    raw_id = str(data.get("id") or data.get("name") or path.parent.name).strip()
    if not raw_id:
        return None
    source_kind = str(data.get("kind") or "agent").strip().lower()
    kind = "agent" if source_kind == "worker" else source_kind
    target_type = str(data.get("target_type") or "").strip()
    if not target_type and source_kind == "worker":
        target_type = "repo_worker"
    default_runtime = str(data.get("default_runtime") or "").strip()
    surface = str(data.get("surface") or "").strip()
    if not default_runtime and surface == "opencode_transport":
        default_runtime = "opencode_transport"
    default_mode = str(data.get("default_mode") or data.get("mode") or "").strip()
    aliases = _string_tuple(data.get("aliases", ()))
    composes = _string_tuple(data.get("composes", ()))
    allowed_modes = _string_tuple(data.get("allowed_modes", (default_mode,) if default_mode else ()))
    eligible = _string_tuple(data.get("eligible_runtimes", (default_runtime,) if default_runtime else ()))
    return RegistryEntry(
        id=raw_id,
        kind=kind,
        aliases=aliases,
        target_type=target_type,
        default_mode=default_mode,
        allowed_modes=allowed_modes,
        default_runtime=default_runtime,
        eligible_runtimes=eligible,
        composes=composes,
        source_kind=source_kind if source_kind != kind else "",
        source_path=_relative_to(path, root),
        title=str(data.get("title") or raw_id).strip(),
        metadata={key: value for key, value in data.items() if key not in {"id", "kind", "aliases", "composes"}},
    )


def _load_skill_entries(skills_dir: Path, *, root: Path) -> list[RegistryEntry]:
    if not skills_dir.is_dir():
        return []
    entries = []
    for skill_file in sorted(skills_dir.glob("*/SKILL.md")):
        frontmatter = _read_frontmatter(skill_file)
        if not frontmatter:
            continue
        raw_id = str(frontmatter.get("name") or skill_file.parent.name).strip()
        if not raw_id:
            continue
        metadata = frontmatter.get("metadata") if isinstance(frontmatter.get("metadata"), dict) else {}
        aliases = _string_tuple(frontmatter.get("aliases", ()))
        entries.append(
            RegistryEntry(
                id=raw_id,
                kind="skill",
                aliases=aliases,
                target_type="skill",
                composes=_string_tuple(frontmatter.get("composes", ())),
                version_or_digest=str(frontmatter.get("version") or _sha256_file(skill_file)).strip(),
                source_path=_relative_to(skill_file, root),
                title=str(metadata.get("short-description") or raw_id).strip(),
                description=str(frontmatter.get("description") or "").strip(),
                metadata={key: value for key, value in frontmatter.items() if key not in {"name", "aliases", "composes"}},
            )
        )
    return entries


def _read_frontmatter(path: Path) -> dict[str, Any]:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not content.startswith("---"):
        return {}
    end_idx = content.find("\n---", 3)
    if end_idx == -1:
        return {}
    payload = yaml.safe_load(content[4:end_idx])
    return payload if isinstance(payload, dict) else {}


def _sha256_file(path: Path) -> str:
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""
    return f"sha256:{digest}"


def _validate_registry(entries: list[RegistryEntry]) -> None:
    seen: dict[tuple[str, str], RegistryEntry] = {}
    for entry in entries:
        if entry.kind not in {"agent", "persona", "skill", "oracle"}:
            raise DelegateError(
                "invalid_registry_entry_kind",
                f"Invalid registry kind for {entry.id}: {entry.kind}",
                details={"entry": entry.as_dict()},
            )
        keys = [normalize_token(entry.id), *(normalize_token(alias) for alias in entry.aliases)]
        for key in keys:
            scoped = (entry.kind, key)
            existing = seen.get(scoped)
            if existing is not None and existing.id != entry.id:
                raise DelegateError(
                    "duplicate_registry_token",
                    f"Duplicate {entry.kind} registry token: {key}",
                    details={"first": existing.as_dict(), "second": entry.as_dict(), "token": key},
                )
            seen[scoped] = entry


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _relative_to(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
