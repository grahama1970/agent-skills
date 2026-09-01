#!/usr/bin/env python3
"""Inject Chatterbox Turbo native paralinguistic utterance tags.

Delivery tone and emotional utterance are separate channels. ``voice_delivery``
selects the delivery preset; Turbo only produces paralinguistic vocal events when
accepted inline tags appear directly in ``answer_text``.
"""
from __future__ import annotations

import re
from typing import Iterable

ACCEPTED_EVENT_TAGS = {
    "[clear throat]", "[sigh]", "[shush]", "[cough]", "[groan]",
    "[sniff]", "[gasp]", "[chuckle]", "[laugh]",
}

_PRIMARY_BY_TONE = {
    "memory_uncertain": "[sigh]",
    "grief_safe": "[sniff]",
    "curious_searching": "[sigh]",
    "careful_concerned": "[sigh]",
    "serious_low_energy": "[sigh]",
    "firm_boundary": "[clear throat]",
    "identity_clarification": "[clear throat]",
    "wait_presence": "[sigh]",
    "relieved": "[chuckle]",
    "playful_light": "[chuckle]",
}

_SECONDARY_BY_TONE = {
    "memory_uncertain": ["[sniff]"],
    "grief_safe": ["[sigh]", "[sniff]"],
    "curious_searching": ["[gasp]"],
    "careful_concerned": ["[sniff]"],
    "serious_low_energy": ["[sigh]"],
    "firm_boundary": ["[sigh]"],
    "identity_clarification": ["[sigh]"],
    "wait_presence": ["[sigh]"],
    "relieved": ["[sigh]"],
    "playful_light": ["[laugh]"],
}

_CONTENT_TAGS = [
    (re.compile(r"\b(ache|aching|cry|grief|sad|scared|afraid|fear|hurt|shame|lonely|alone)\b", re.I), "[sniff]"),
    (re.compile(r"\b(surprise|surprised|sudden|realized|realise|caught|startled)\b", re.I), "[gasp]"),
    (re.compile(r"\b(warm|gentle|relieved|safe|soft|funny|laugh)\b", re.I), "[chuckle]"),
]

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_DELAY_RE = re.compile(r"\.\.\.|--|—")


def has_delay_markup(text: str) -> bool:
    """Return true when text contains an explicit hesitation/break marker."""
    return bool(_DELAY_RE.search(text))


def ensure_delay_markup(text: str) -> str:
    """Add one Chatterbox-readable hesitation after the first event tag if absent."""
    if has_delay_markup(text):
        return text
    for tag in existing_event_tags(text):
        return text.replace(tag, f"{tag}...", 1)
    return text


def existing_event_tags(text: str) -> list[str]:
    """Return accepted event tags already present, in text order."""
    hits: list[tuple[int, str]] = []
    for tag in ACCEPTED_EVENT_TAGS:
        idx = text.find(tag)
        if idx >= 0:
            hits.append((idx, tag))
    return [tag for _, tag in sorted(hits)]


def _dedupe(tags: Iterable[str]) -> list[str]:
    out: list[str] = []
    for tag in tags:
        if tag in ACCEPTED_EVENT_TAGS and tag not in out:
            out.append(tag)
    return out


def choose_event_tags(text: str, tone: str, *, max_tags: int = 3) -> list[str]:
    """Pick bounded native event tags from tone plus local text cues."""
    if max_tags <= 0:
        return []
    tags: list[str] = []
    primary = _PRIMARY_BY_TONE.get(tone, "[sigh]")
    tags.append(primary)
    for pattern, tag in _CONTENT_TAGS:
        if pattern.search(text):
            tags.append(tag)
    tags.extend(_SECONDARY_BY_TONE.get(tone, []))
    return _dedupe(tags)[:max_tags]


def inject_event_tags(text: str, tone: str, *, max_tags: int = 3) -> tuple[str, list[str]]:
    """Return text with inline native event tags and the tags used.

    Placement is intentionally sparse: first tag at the opening, later tags at
    sentence boundaries. This avoids stuffing bracket tokens before every clause
    while still giving Turbo multiple vocal events to realize.
    """
    clean = text.strip()
    already = existing_event_tags(clean)
    if already:
        return ensure_delay_markup(clean), already[:max_tags]

    tags = choose_event_tags(clean, tone, max_tags=max_tags)
    if not tags:
        return clean, []

    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(clean) if s.strip()]
    if not sentences:
        return f"{tags[0]}... {clean}".strip(), tags

    sentences[0] = f"{tags[0]}... {sentences[0]}"
    for idx, tag in enumerate(tags[1:], start=1):
        if idx < len(sentences):
            sentences[idx] = f"{tag} {sentences[idx]}"
        else:
            sentences[-1] = f"{sentences[-1]} {tag}"
    return " ".join(sentences), tags
