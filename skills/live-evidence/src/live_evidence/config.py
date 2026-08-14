"""Configuration loading for Live Evidence.

Configuration enters through environment variables and an optional YAML profile.
The module validates paths and closed settings once, keeps secrets out of logs,
and defaults all network-bearing research lanes to disabled.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator

load_dotenv(override=False)


class InterviewProfile(BaseModel):
    """Human-readable retrieval and transcription profile."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    candidate_name: str = Field(default="Graham Anderson", min_length=1, max_length=200)
    organization: str | None = Field(default=None, max_length=200)
    watch_terms: list[str] = Field(default_factory=list, max_length=200)
    project_aliases: dict[str, list[str]] = Field(default_factory=dict)
    repo_priorities: list[str] = Field(default_factory=list, max_length=100)
    memory_collections: list[str] = Field(
        default_factory=lambda: [
            "project_memory_active",
            "project_states",
            "project_activity",
            "project_knowledge",
            "lessons_v2",
            "tau_orchestration_episodes",
            "dogpile_research",
            "code_symbols",
        ],
        max_length=50,
    )
    blocked_tags: list[str] = Field(
        default_factory=lambda: [
            "private",
            "confidential",
            "restricted",
            "secret",
            "credential",
            "itar-sensitive",
            "export-controlled-content",
        ],
        max_length=100,
    )
    blocked_path_fragments: list[str] = Field(
        default_factory=lambda: [
            "/.env",
            "/secrets/",
            "/credentials/",
            "/private/",
        ],
        max_length=100,
    )
    stt_prompt_terms: list[str] = Field(default_factory=list, max_length=300)

    @field_validator(
        "watch_terms",
        "repo_priorities",
        "memory_collections",
        "blocked_tags",
        "blocked_path_fragments",
        "stt_prompt_terms",
    )
    @classmethod
    def normalize_list(cls, values: list[str]) -> list[str]:
        """Remove empty and duplicate profile terms while preserving order."""

        seen: set[str] = set()
        normalized: list[str] = []
        for value in values:
            clean = " ".join(str(value).split())
            key = clean.casefold()
            if clean and key not in seen:
                seen.add(key)
                normalized.append(clean)
        return normalized


class AppSettings(BaseModel):
    """Validated runtime settings."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    skill_root: Path
    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1, le=65_535)
    data_dir: Path
    profile_path: Path
    repo_roots: list[Path] = Field(default_factory=list)
    memory_url: str = "http://127.0.0.1:8601"
    memory_runner: Path | None = None
    ask_runner: Path | None = None
    ask_handler: str = "gpt-5.5-high"
    ask_allow_provider_calls: bool = False
    ask_timeout_s: float = Field(default=45.0, gt=1.0, le=600.0)
    brave_runner: Path | None = None
    dogpile_runner: Path | None = None
    allow_remote_bind: bool = False
    request_timeout_s: float = Field(default=4.0, gt=0.1, le=120.0)
    subprocess_timeout_s: float = Field(default=5.0, gt=0.1, le=120.0)
    max_cards: int = Field(default=40, ge=5, le=200)
    max_transcript_events: int = Field(default=160, ge=20, le=500)

    @classmethod
    def from_env(
        cls,
        *,
        skill_root: Path | None = None,
        host: str | None = None,
        port: int | None = None,
    ) -> "AppSettings":
        """Build settings from the process environment and repository layout."""

        root = (skill_root or Path(__file__).resolve().parents[2]).resolve()
        profile_path = Path(
            os.getenv("LIVE_EVIDENCE_PROFILE", str(root / "config" / "default.yaml"))
        ).expanduser().resolve()

        storage_root = Path("/mnt/storage12tb/skills/live-evidence/sessions")
        if storage_root.parent.exists() and os.access(storage_root.parent, os.W_OK):
            default_data = storage_root
        else:
            default_data = Path.home() / ".local" / "share" / "live-evidence" / "sessions"
        data_dir = Path(os.getenv("LIVE_EVIDENCE_DATA_DIR", str(default_data))).expanduser().resolve()

        repo_roots = _parse_path_list(os.getenv("LIVE_EVIDENCE_REPOS", ""))
        memory_runner = _runner_from_env_or_sibling(
            root,
            "LIVE_EVIDENCE_MEMORY_RUNNER",
            "memory",
        )
        ask_runner = _runner_from_env_only("LIVE_EVIDENCE_ASK_RUNNER")
        brave_runner = _runner_from_env_or_sibling(
            root,
            "LIVE_EVIDENCE_BRAVE_RUNNER",
            "brave-search",
        )
        dogpile_runner = _runner_from_env_or_sibling(
            root,
            "LIVE_EVIDENCE_DOGPILE_RUNNER",
            "dogpile",
        )

        return cls(
            skill_root=root,
            host=host or os.getenv("LIVE_EVIDENCE_HOST", "127.0.0.1"),
            port=port or int(os.getenv("LIVE_EVIDENCE_PORT", "8765")),
            data_dir=data_dir,
            profile_path=profile_path,
            repo_roots=repo_roots,
            memory_url=os.getenv(
                "MEMORY_SERVICE_URL",
                os.getenv("MEMORY_API_URL", "http://127.0.0.1:8601"),
            ).rstrip("/"),
            memory_runner=memory_runner,
            ask_runner=ask_runner,
            ask_handler=os.getenv("LIVE_EVIDENCE_ASK_HANDLER", "gpt-5.5-high"),
            ask_allow_provider_calls=_truthy(
                os.getenv("LIVE_EVIDENCE_ASK_ALLOW_PROVIDER_CALLS", "false")
            ),
            ask_timeout_s=float(os.getenv("LIVE_EVIDENCE_ASK_TIMEOUT", "45")),
            brave_runner=brave_runner,
            dogpile_runner=dogpile_runner,
            allow_remote_bind=_truthy(
                os.getenv("LIVE_EVIDENCE_ALLOW_REMOTE_BIND", "false")
            ),
            request_timeout_s=float(os.getenv("LIVE_EVIDENCE_HTTP_TIMEOUT", "4")),
            subprocess_timeout_s=float(os.getenv("LIVE_EVIDENCE_PROCESS_TIMEOUT", "5")),
            max_cards=int(os.getenv("LIVE_EVIDENCE_MAX_CARDS", "40")),
            max_transcript_events=int(os.getenv("LIVE_EVIDENCE_MAX_TRANSCRIPT_EVENTS", "160")),
        )

    def load_profile(self) -> InterviewProfile:
        """Read and validate the selected YAML profile."""

        if not self.profile_path.exists():
            raise FileNotFoundError(f"profile not found: {self.profile_path}")
        payload = yaml.safe_load(self.profile_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"profile must contain a YAML object: {self.profile_path}")
        return InterviewProfile.model_validate(payload)

    def prepare_runtime(self) -> None:
        """Create only runtime directories outside the source tree."""

        self.data_dir.mkdir(parents=True, exist_ok=True)


def _truthy(value: str) -> bool:
    """Parse a conservative environment boolean."""

    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _parse_path_list(value: str) -> list[Path]:
    """Parse an OS path-separated allowlist and keep existing directories only."""

    roots: list[Path] = []
    seen: set[Path] = set()
    for raw in value.split(os.pathsep):
        if not raw.strip():
            continue
        path = Path(raw).expanduser().resolve()
        if path.is_dir() and path not in seen:
            seen.add(path)
            roots.append(path)
    return roots


def _runner_from_env_or_sibling(root: Path, env_name: str, sibling: str) -> Path | None:
    """Resolve an executable sibling skill runner without guessing elsewhere."""

    explicit = os.getenv(env_name)
    candidates = [Path(explicit).expanduser()] if explicit else []
    candidates.append(root.parent / sibling / "run.sh")
    for candidate in candidates:
        path = candidate.resolve()
        if path.is_file() and os.access(path, os.X_OK):
            return path
    return None


def _runner_from_env_only(env_name: str) -> Path | None:
    """Resolve an executable runner only when the operator explicitly enables it."""

    explicit = os.getenv(env_name)
    if not explicit:
        return None
    path = Path(explicit).expanduser().resolve()
    if path.is_file() and os.access(path, os.X_OK):
        return path
    return None


def public_settings(settings: AppSettings, profile: InterviewProfile) -> dict[str, Any]:
    """Return non-sensitive settings safe for the browser."""

    return {
        "profile_name": profile.name,
        "candidate_name": profile.candidate_name,
        "organization": profile.organization,
        "repo_count": len(settings.repo_roots),
        "memory_configured": bool(settings.memory_url),
        "ask_configured": bool(settings.ask_runner),
        "external_search_enabled": bool(settings.brave_runner or settings.dogpile_runner),
        "remote_bind_allowed": settings.allow_remote_bind,
    }
