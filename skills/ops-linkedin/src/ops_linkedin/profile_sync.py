"""Source-derived LinkedIn own-profile sync planning.

This module turns the public resume Markdown into a bounded profile-sync packet.
It does not open LinkedIn, inspect a browser session, save profile edits, or read
third-party LinkedIn data. The packet is an execution plan for a later, explicit
Surf-controlled own-profile operation.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

PROFILE_ENTRY_SCHEMA = "ops-linkedin.profile_entry.v1"
PROFILE_SYNC_SCHEMA = "ops-linkedin.profile_sync.v1"
DEFAULT_SURF_RUN = Path("/home/graham/workspace/experiments/agent-skills/skills/surf/run.sh")


def utc_now() -> datetime:
    """Return one timezone-aware UTC timestamp."""

    return datetime.now(UTC)


def _strip_inline_markdown(text: str) -> str:
    """Remove the small Markdown subset used by the canonical resume."""

    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = text.replace("**", "")
    text = text.replace("__", "")
    return text.strip()


def _section(markdown: str, heading: str) -> str:
    """Return one top-level Markdown section body by exact heading."""

    lines = markdown.splitlines()
    wanted = f"## {heading}"
    capture = False
    collected: list[str] = []
    for line in lines:
        if line.strip() == wanted:
            capture = True
            continue
        if capture and line.startswith("## "):
            break
        if capture:
            collected.append(line)
    return "\n".join(collected).strip()


def _nonempty_lines(markdown: str) -> list[str]:
    """Return meaningful source lines without HTML comments."""

    return [
        line.strip().rstrip(" ")
        for line in markdown.splitlines()
        if line.strip() and not line.strip().startswith("<!--")
    ]


class ProfileSyncSource(BaseModel):
    """Source file identity for a generated profile-sync packet."""

    model_config = ConfigDict(extra="forbid")

    path: Path
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    generated_at: datetime

    @field_validator("generated_at")
    @classmethod
    def generated_at_is_utc(cls, value: datetime) -> datetime:
        """Require an aware UTC timestamp for receipt comparison."""

        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("generated_at must be timezone-aware UTC")
        return value


class LinkedInExperienceEntry(BaseModel):
    """Editable LinkedIn experience entry generated from one resume role."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=300)
    organization: str | None = Field(default=None, max_length=300)
    dates: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=4_000)
    source_ref: str = Field(min_length=1, max_length=300)


class FeaturedLink(BaseModel):
    """Editable Featured-section link for the LinkedIn profile."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    label: str = Field(min_length=1, max_length=120)
    url: AnyHttpUrl
    source_ref: str = Field(min_length=1, max_length=300)


class LinkedInProfileEntry(BaseModel):
    """Single editable JSON document representing Graham's LinkedIn profile entry."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_version: Literal[PROFILE_ENTRY_SCHEMA] = PROFILE_ENTRY_SCHEMA
    source: ProfileSyncSource
    profile_url: AnyHttpUrl
    name: str = Field(min_length=1, max_length=120)
    location: str = Field(min_length=1, max_length=120)
    headline: str = Field(min_length=1, max_length=220)
    about: str = Field(min_length=1, max_length=2_600)
    featured_links: list[FeaturedLink] = Field(default_factory=list)
    experience: list[LinkedInExperienceEntry] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    editor_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def profile_url_is_linkedin_profile(self) -> LinkedInProfileEntry:
        """Limit the editable entry to one LinkedIn profile URL shape."""

        url = str(self.profile_url)
        if not url.startswith("https://www.linkedin.com/in/"):
            raise ValueError("profile_url must be an https://www.linkedin.com/in/... URL")
        return self


class ProfileSyncField(BaseModel):
    """One LinkedIn profile field proposed from the resume source."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    field: Literal["name", "location", "headline", "about", "featured_resume_url"]
    source_ref: str = Field(min_length=1, max_length=300)
    source_text: str = Field(min_length=1, max_length=8_000)
    linkedin_target_text: str = Field(min_length=1, max_length=8_000)


class ProfileSyncGuardrails(BaseModel):
    """Hard limits for the opt-in own-profile sync workflow."""

    model_config = ConfigDict(extra="forbid")

    own_profile_only: Literal[True] = True
    account_risk_accepted: Literal[True] = True
    no_third_party_profile_access: Literal[True] = True
    no_scraping: Literal[True] = True
    no_outbound_social_actions: Literal[True] = True
    no_cookie_or_secret_access: Literal[True] = True
    external_effects: Literal[False] = False
    platform_verified: Literal[False] = False


class ProfileSyncPacket(BaseModel):
    """A source-derived packet for keeping Graham's own LinkedIn profile aligned."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[PROFILE_SYNC_SCHEMA] = PROFILE_SYNC_SCHEMA
    profile_url: AnyHttpUrl
    source: ProfileSyncSource
    profile_entry: LinkedInProfileEntry
    fields: list[ProfileSyncField] = Field(min_length=1)
    guardrails: ProfileSyncGuardrails = Field(default_factory=ProfileSyncGuardrails)
    surf_commands: list[list[str]] = Field(min_length=1)
    manual_review_steps: list[str] = Field(min_length=1)
    execution_claim: Literal["NOT_EXECUTED"] = "NOT_EXECUTED"

    @model_validator(mode="after")
    def profile_url_is_linkedin_profile(self) -> ProfileSyncPacket:
        """Limit the packet to one LinkedIn profile URL shape."""

        url = str(self.profile_url)
        if not url.startswith("https://www.linkedin.com/in/"):
            raise ValueError("profile_url must be an https://www.linkedin.com/in/... URL")
        return self


def fields_from_resume(markdown: str) -> list[ProfileSyncField]:
    """Extract LinkedIn-facing profile fields from the canonical resume Markdown."""

    entry = entry_from_resume_text(
        markdown=markdown,
        source=ProfileSyncSource(
            path=Path("RESUME.md"),
            sha256=hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
            generated_at=utc_now(),
        ),
        profile_url="https://www.linkedin.com/in/grahamanderson/",
    )
    return fields_from_entry(entry)


def _headline_from_lines(lines: list[str]) -> str:
    """Derive the LinkedIn headline from the resume role summary."""

    role_line = _strip_inline_markdown(lines[4]) if len(lines) > 4 else ""
    focus_line = _strip_inline_markdown(lines[5]) if len(lines) > 5 else ""
    headline = f"{role_line} | {focus_line}".strip(" |")
    if len(headline) > 220:
        return headline[:217].rstrip() + "..."
    return headline


def _experience_entries(markdown: str) -> list[LinkedInExperienceEntry]:
    """Parse resume experience roles into editable LinkedIn experience entries."""

    section = _section(markdown, "EXPERIENCE")
    roles: list[LinkedInExperienceEntry] = []
    current_title: str | None = None
    current_org: str | None = None
    current_dates = ""
    body_lines: list[str] = []
    role_index = 0

    def flush() -> None:
        nonlocal role_index
        if current_title is None or not current_dates or not body_lines:
            return
        role_index += 1
        roles.append(
            LinkedInExperienceEntry(
                title=current_title,
                organization=current_org,
                dates=current_dates,
                body="\n".join(body_lines).strip(),
                source_ref=f"RESUME.md#experience-{role_index}",
            )
        )

    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("### "):
            flush()
            heading = _strip_inline_markdown(line.removeprefix("### "))
            title, sep, org = heading.partition(" | ")
            current_title = title.strip()
            current_org = org.strip() if sep else None
            current_dates = ""
            body_lines = []
            continue
        if current_title and not current_dates:
            current_dates = _strip_inline_markdown(line)
            continue
        if current_title:
            body_lines.append(_strip_inline_markdown(line.removeprefix("- ")))
    flush()
    return roles


def _skills(markdown: str) -> list[str]:
    """Parse CORE COMPETENCIES into a flat editable skill list."""

    section = _section(markdown, "CORE COMPETENCIES")
    skills: list[str] = []
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line.startswith("- "):
            continue
        _, _, values = line.partition(":")
        source = values if values else line.removeprefix("- ")
        for item in source.split(","):
            cleaned = _strip_inline_markdown(item)
            if cleaned and cleaned not in skills:
                skills.append(cleaned)
    return skills


def entry_from_resume_text(
    *,
    markdown: str,
    source: ProfileSyncSource,
    profile_url: str,
) -> LinkedInProfileEntry:
    """Build the editable profile-entry JSON model from resume Markdown text."""

    lines = _nonempty_lines(markdown)
    if not lines or not lines[0].startswith("# "):
        raise ValueError("resume source must start with an H1 name")

    name = _strip_inline_markdown(lines[0].removeprefix("# "))
    location = _strip_inline_markdown(lines[1])
    headline = _headline_from_lines(lines) or name
    about = "\n\n".join(
        paragraph.strip()
        for paragraph in _section(markdown, "ABOUT").split("\n\n")
        if paragraph.strip()
    )
    about = _strip_inline_markdown(about)
    return LinkedInProfileEntry(
        source=source,
        profile_url=profile_url,
        name=name,
        location=location,
        headline=headline,
        about=about,
        featured_links=[
            FeaturedLink(
                label="Resume",
                url="https://grahama.co/resume",
                source_ref="RESUME.md#contact",
            )
        ],
        experience=_experience_entries(markdown),
        skills=_skills(markdown),
        editor_notes=[
            "Project agents may edit this JSON directly before a profile sync plan is run.",
            (
                "Do not add claims that are not already supported by RESUME.md or the "
                "career_profile ledger."
            ),
        ],
    )


def fields_from_entry(entry: LinkedInProfileEntry) -> list[ProfileSyncField]:
    """Flatten an editable profile entry into profile sync fields."""

    fields = [
        ProfileSyncField(
            field="name",
            source_ref="RESUME.md#heading",
            source_text=entry.name,
            linkedin_target_text=entry.name,
        ),
        ProfileSyncField(
            field="location",
            source_ref="RESUME.md:2",
            source_text=entry.location,
            linkedin_target_text=entry.location,
        ),
        ProfileSyncField(
            field="headline",
            source_ref="RESUME.md#role-summary",
            source_text=entry.headline,
            linkedin_target_text=entry.headline,
        ),
        ProfileSyncField(
            field="about",
            source_ref="RESUME.md#about",
            source_text=entry.about,
            linkedin_target_text=entry.about,
        ),
    ]
    if entry.featured_links:
        fields.append(
            ProfileSyncField(
                field="featured_resume_url",
                source_ref="RESUME.md#contact",
                source_text="https://grahama.co/resume",
                linkedin_target_text=str(entry.featured_links[0].url),
            )
        )
    return fields


def build_profile_entry(
    *,
    resume_path: Path,
    profile_url: str,
    now: datetime | None = None,
) -> LinkedInProfileEntry:
    """Build an editable profile-entry JSON document from a resume Markdown file."""

    source_text = resume_path.read_text(encoding="utf-8")
    digest = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    source = ProfileSyncSource(
        path=resume_path.resolve(),
        sha256=digest,
        generated_at=now or utc_now(),
    )
    return entry_from_resume_text(markdown=source_text, source=source, profile_url=profile_url)


def build_profile_sync_packet(
    *,
    resume_path: Path,
    profile_url: str,
    surf_run: Path = DEFAULT_SURF_RUN,
    now: datetime | None = None,
) -> ProfileSyncPacket:
    """Build a non-executing Surf profile-sync plan from a resume Markdown file."""

    profile_entry = build_profile_entry(
        resume_path=resume_path,
        profile_url=profile_url,
        now=now,
    )
    surf = str(surf_run)
    return ProfileSyncPacket(
        profile_url=profile_url,
        source=profile_entry.source,
        profile_entry=profile_entry,
        fields=fields_from_entry(profile_entry),
        surf_commands=[
            ["bash", surf, "tab.list", "--json"],
            ["bash", surf, "go", profile_url],
            ["bash", surf, "read"],
            ["bash", surf, "snap", "--output", "/tmp/ops-linkedin-profile-sync-before.png"],
        ],
        manual_review_steps=[
            "Open only Graham's own LinkedIn profile URL.",
            "Compare the visible profile fields to the packet's fields array.",
            "Apply only matching source-derived edits from RESUME.md.",
            "Do not open third-party profiles, search results, feeds, posts, messages, or jobs.",
            "Capture a before/after Surf screenshot if an edit is performed.",
        ],
    )


def build_profile_sync_packet_from_entry(
    *,
    profile_entry: LinkedInProfileEntry,
    surf_run: Path = DEFAULT_SURF_RUN,
) -> ProfileSyncPacket:
    """Build a non-executing Surf profile-sync plan from an editable entry JSON."""

    surf = str(surf_run)
    profile_url = str(profile_entry.profile_url)
    return ProfileSyncPacket(
        profile_url=profile_entry.profile_url,
        source=profile_entry.source,
        profile_entry=profile_entry,
        fields=fields_from_entry(profile_entry),
        surf_commands=[
            ["bash", surf, "tab.list", "--json"],
            ["bash", surf, "go", profile_url],
            ["bash", surf, "read"],
            ["bash", surf, "snap", "--output", "/tmp/ops-linkedin-profile-sync-before.png"],
        ],
        manual_review_steps=[
            "Open only Graham's own LinkedIn profile URL.",
            "Compare the visible profile fields to the editable profile_entry object.",
            "Apply only matching source-derived edits from the approved JSON profile entry.",
            "Do not open third-party profiles, search results, feeds, posts, messages, or jobs.",
            "Capture a before/after Surf screenshot if an edit is performed.",
        ],
    )
