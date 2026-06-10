"""Data models for deterministic delegate resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


DELEGATE_SCHEMA = "agent_skills.delegate.v1"
REGISTRY_KINDS = {"agent", "persona", "skill", "oracle"}
ACTOR_KINDS = {"agent", "persona", "oracle"}


class DelegateError(ValueError):
    """Structured fail-closed delegate resolution error."""

    def __init__(
        self,
        reason: str,
        question: str,
        *,
        safe_default: str = "do_not_delegate",
        suggestions: list[str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(question)
        self.reason = reason
        self.question = question
        self.safe_default = safe_default
        self.suggestions = suggestions or []
        self.details = details or {}

    def as_needs_attention(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "reason": self.reason,
            "question": self.question,
            "safe_default": self.safe_default,
            "resume_hint": "Clarify the delegate actor, skill, mode, or target and retry.",
        }
        if self.suggestions:
            payload["suggestions"] = self.suggestions
        if self.details:
            payload["details"] = self.details
        return payload


@dataclass(frozen=True)
class RegistryEntry:
    """Single normalized registry entry."""

    id: str
    kind: str
    aliases: tuple[str, ...] = ()
    target_type: str = ""
    default_mode: str = ""
    allowed_modes: tuple[str, ...] = ()
    default_runtime: str = ""
    eligible_runtimes: tuple[str, ...] = ()
    composes: tuple[str, ...] = ()
    version_or_digest: str = ""
    source_kind: str = ""
    source_path: str = ""
    title: str = ""
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "id": self.id,
            "kind": self.kind,
            "aliases": list(self.aliases),
            "target_type": self.target_type,
            "default_mode": self.default_mode,
            "allowed_modes": list(self.allowed_modes),
            "default_runtime": self.default_runtime,
            "eligible_runtimes": list(self.eligible_runtimes),
            "composes": list(self.composes),
            "version_or_digest": self.version_or_digest,
            "source_kind": self.source_kind,
            "source_path": self.source_path,
            "title": self.title,
            "description": self.description,
            "metadata": dict(self.metadata),
        }
        return {key: value for key, value in payload.items() if value not in ("", [], {})}


@dataclass(frozen=True)
class ParsedDelegateInvocation:
    """Public `$ask <actor> to <task> [with <skill>] [on <target>]` parse."""

    actor_token: str
    task: str
    skill_tokens: tuple[str, ...] = ()
    target: tuple[str, ...] = ()


@dataclass(frozen=True)
class DelegateRegistry:
    """In-memory typed registry with deterministic token lookup."""

    entries: tuple[RegistryEntry, ...]

    def find(self, token: str, *, kinds: set[str] | None = None) -> list[RegistryEntry]:
        normalized = normalize_token(token)
        allowed = kinds or REGISTRY_KINDS
        matches = []
        for entry in self.entries:
            if entry.kind not in allowed:
                continue
            names = {normalize_token(entry.id)}
            names.update(normalize_token(alias) for alias in entry.aliases)
            if normalized in names:
                matches.append(entry)
        return matches

    def require_one(self, token: str, *, kinds: set[str], position: str) -> RegistryEntry:
        matches = self.find(token, kinds=kinds)
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise DelegateError(
                f"unknown_{position}",
                f"Unknown delegate {position}: {token}",
                suggestions=[f"Register {token} or choose an existing {position}."],
                details={"token": token, "expected_kinds": sorted(kinds)},
            )
        raise DelegateError(
            f"ambiguous_{position}",
            f"Ambiguous delegate {position}: {token}",
            suggestions=["Use a fully-qualified or less ambiguous registry id."],
            details={
                "token": token,
                "matches": [entry.as_dict() for entry in matches],
                "expected_kinds": sorted(kinds),
            },
        )


def normalize_token(token: str) -> str:
    """Normalize public `$token` / display names to registry lookup keys."""

    cleaned = str(token or "").strip()
    cleaned = cleaned.strip("`'\".,:;()[]{}")
    while cleaned.startswith(("$", "/")):
        cleaned = cleaned[1:].strip()
    cleaned = "-".join(part for part in cleaned.replace("_", "-").split() if part)
    return cleaned.lower()
