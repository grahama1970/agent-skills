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

EXTENDED_STYLE_TOKENS = {
    "[angry]", "[fear]", "[surprised]", "[whispering]", "[advertisement]",
    "[dramatic]", "[narration]", "[crying]", "[happy]", "[sarcastic]",
}

ALL_SUPPORTED_INLINE_TOKENS = ACCEPTED_EVENT_TAGS | EXTENDED_STYLE_TOKENS

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
    (re.compile(r"\b(tender|tenderness|ache|aching|cry|crying|grief|sad|scared|afraid|fear|hurt|shame|lonely|alone|devastating|flinch)\b", re.I), "[sniff]"),
    (re.compile(r"\b(tender|tenderness|grief|ache|aching|devastating|cry|crying)\b", re.I), "[crying]"),
    (re.compile(r"\b(surprise|surprised|sudden|realized|realise|caught|startled|shock|shocked)\b", re.I), "[gasp]"),
    (re.compile(r"\b(warm|gentle|relieved|safe|soft|funny|laugh|light|permission)\b", re.I), "[chuckle]"),
]

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_DELAY_RE = re.compile(r"\.\.\.|--|—")
_COLLECT_RE = re.compile(r"\[sniff\]\s*\[sniff\]|give me a second|collect myself|catch my breath", re.I)
_GIVE_ME_SECOND_RE = re.compile(r"\[sniff\]\s*\[sniff\](?:\.\.\.)?\s*(give me a second[.!?]?)", re.I)
_UNFINISHED_TAIL_RE = re.compile(r"(?:\.{3}|--|—)\s*$")
_BROKEN_ELLIPSIS_RE = re.compile(r"\b(would|could|should|can|cannot|can't|is|are|was|were|be|been|being|to|the|a|an|and|or|but|of|for|with)\.\.\.\s*(?:\[|$)", re.I)


def has_delay_markup(text: str) -> bool:
    """Return true when text contains an explicit hesitation/break marker."""
    return bool(_DELAY_RE.search(text))


def normalize_delay_markup(text: str) -> str:
    """Make delay punctuation speakable and split-friendly.

    Chatterbox is more likely to realize a pause when an ellipsis is its own
    spoken beat: ``bottle rocket ... a room`` instead of ``bottle rocket... a``.
    The render-chunk compiler also uses the spaced marker as a hard boundary for
    exact tensor silence.
    """
    clean = " ".join(str(text or "").split())
    clean = re.sub(r"\s*\.\.\.\s*", " ... ", clean)
    clean = re.sub(r"\s+([,;!?])", r"\1", clean)
    return " ".join(clean.split())


def ensure_delay_markup(text: str) -> str:
    """Add one Chatterbox-readable hesitation after the first event tag if absent."""
    clean = normalize_delay_markup(text)
    if has_delay_markup(clean):
        return clean
    for tag in existing_event_tags(clean):
        return clean.replace(tag, f"{tag} ...", 1)
    return clean


def existing_event_tags(text: str) -> list[str]:
    """Return supported inline Chatterbox tokens already present, in text order."""
    hits: list[tuple[int, str]] = []
    for tag in ALL_SUPPORTED_INLINE_TOKENS:
        idx = text.find(tag)
        if idx >= 0:
            hits.append((idx, tag))
    return [tag for _, tag in sorted(hits)]


def _dedupe(tags: Iterable[str]) -> list[str]:
    out: list[str] = []
    for tag in tags:
        if tag in ALL_SUPPORTED_INLINE_TOKENS and tag not in out:
            out.append(tag)
    return out


def choose_event_tags(text: str, tone: str, *, max_tags: int = 5) -> list[str]:
    """Pick bounded inline tokens from tone plus local affect cues."""
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


def inject_event_tags(text: str, tone: str, *, max_tags: int = 5) -> tuple[str, list[str]]:
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

    if any(tag in {"[sniff]", "[crying]"} for tag in tags):
        opener = "[sniff] [sniff] ..." if "[sniff]" in tags else f"{tags[0]} ..."
        sentences[0] = f"{opener} {sentences[0]}"
        remaining = [tag for tag in tags if tag != "[sniff]"]
    else:
        sentences[0] = f"{tags[0]} ... {sentences[0]}"
        remaining = tags[1:]
    for idx, tag in enumerate(remaining, start=1):
        if idx < len(sentences):
            sentences[idx] = f"{tag} {sentences[idx]}"
        else:
            sentences[-1] = f"{sentences[-1]} {tag}"
    return " ".join(sentences), tags


def pause_ms_for_chunk(text: str, *, final: bool = False) -> int:
    """Convert spoken delay cues into exact Chatterbox pause_after_ms."""
    if final:
        return 0
    if _COLLECT_RE.search(text):
        return 1400
    if "[crying]" in text or "[groan]" in text:
        return 1100
    if "..." in text:
        return 900
    if any(tag in text for tag in ("[sniff]", "[sigh]", "[clear throat]", "[gasp]")):
        return 650
    if ";" in text or "—" in text or "--" in text:
        return 500
    return 300


def has_unfinished_tail(text: str) -> bool:
    """Return true when model output contains an incomplete ellipsis thought."""
    value = str(text or "").strip()
    return bool(_UNFINISHED_TAIL_RE.search(value) or _BROKEN_ELLIPSIS_RE.search(value))


def normalize_collect_cues(text: str) -> str:
    """Normalize collect-herself phrasing into a split-friendly sniff cue."""
    normalized = _GIVE_ME_SECOND_RE.sub(r"[sniff] [sniff] ... \1", str(text or ""))
    return normalize_delay_markup(normalized)


def compile_render_chunks(text: str, tone: str, *, max_chunk_chars: int = 300,
                          min_final_chars: int = 60) -> list[dict[str, object]]:
    """Build caller-owned Chatterbox chunks with exact silence pauses.

    Chatterbox's batch endpoint turns each ``pause_after_ms`` into real silence
    while stitching generated WAV chunks. This is the programmatic silence path;
    punctuation remains a natural prosody hint inside each generated chunk.
    """
    clean = normalize_collect_cues(str(text or ""))
    if not clean:
        return []
    split_clean = re.sub(r"(\[sniff\]\s*\[sniff\]\s*\.\.\.)\s*(give me a second[.!?]?)", r"\1\n\2", clean, flags=re.I)
    split_clean = re.sub(r"\s+\.\.\.\s+", " ...\n", split_clean)
    hard_parts = [part.strip() for part in split_clean.splitlines() if part.strip()] or [clean]
    chunks: list[str] = []
    for part in hard_parts:
        raw_sentences = [s.strip() for s in _SENTENCE_SPLIT.split(part) if s.strip()] or [part]
        current = ""
        for sentence in raw_sentences:
            if not current:
                current = sentence
            elif len(current) + 1 + len(sentence) <= max_chunk_chars:
                current = f"{current} {sentence}"
            else:
                chunks.append(current)
                current = sentence
        if current:
            chunks.append(current)
    if len(chunks) > 1 and len(chunks[-1]) < min_final_chars and not _COLLECT_RE.search(chunks[-2]):
        chunks[-2] = f"{chunks[-2]} {chunks[-1]}"
        chunks.pop()
    if not chunks:
        chunks = [clean]
    planned: list[dict[str, object]] = []
    for idx, chunk in enumerate(chunks):
        planned.append({
            "text": chunk,
            "tone": tone,
            "pause_after_ms": pause_ms_for_chunk(chunk, final=idx == len(chunks) - 1),
            "role": "persona_affect_beat",
            "interruptible": True,
        })
    return planned
