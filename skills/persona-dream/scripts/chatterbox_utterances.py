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
PAUSE_IMPLEMENTATION = "chatterbox_render_chunks_post_render_stitching"
EXACT_PAUSE_CROSSFADE_MS = 0


def exact_pause_request_fields() -> dict[str, int]:
    """Request fields that keep render_chunks pauses exact after stitching."""
    return {"crossfade_ms": EXACT_PAUSE_CROSSFADE_MS}


def exact_pause_receipt_fields(actual_crossfade_ms: object = None) -> dict[str, object]:
    """Receipt fields proving the renderer used the exact-pause path."""
    return {
        "pause_implementation": PAUSE_IMPLEMENTATION,
        "requested_crossfade_ms": EXACT_PAUSE_CROSSFADE_MS,
        "actual_crossfade_ms": actual_crossfade_ms,
    }


def strip_inline_markup(text: str) -> str:
    """Remove Chatterbox-only markup before comparing rendered text to source text."""
    tagless = re.sub(r"\[[^\]]+\]", " ", str(text or ""))
    tagless = tagless.replace("...", " ").replace("—", " ").replace("--", " ")
    return " ".join(tagless.split())


def preserves_source_words(source: str, utterance: str, *, min_ratio: float = 0.55) -> bool:
    """Return true when Chatterbox markup preserved enough source words.

    The model may add bracket tags and cadence marks, but it must not rewrite the
    journal or clean reply into a different utterance.
    """
    source_words = {
        word.lower()
        for word in re.findall(r"[A-Za-z][A-Za-z']{3,}", str(source or ""))
        if word.lower() not in {"that", "with", "from", "this", "they", "were", "have", "been"}
    }
    if len(source_words) < 6:
        return True
    utterance_words = {
        word.lower()
        for word in re.findall(r"[A-Za-z][A-Za-z']{3,}", strip_inline_markup(utterance))
    }
    return len(source_words & utterance_words) / len(source_words) >= min_ratio


def prompt_guidance(*, include_clean_reply_rule: bool = False) -> str:
    """Shared Chatterbox prompt contract for journal and reply utterances."""
    clean_rule = (
        "Write the clean reply field with no Chatterbox bracket tags; only the "
        "chatterbox_utterance_text field may contain inline renderer tags.\n\n"
        if include_clean_reply_rule else ""
    )
    return f"""{clean_rule}Native vocal event tags available: [clear throat], [sigh], [shush], [cough],
[groan], [sniff], [gasp], [chuckle], [laugh].

Extended tokenizer style/emotion tokens available when genuinely relevant:
[angry], [fear], [surprised], [whispering], [advertisement], [dramatic],
[narration], [crying], [happy], [sarcastic]. Prefer the native vocal event tags
for audible utterances; use extended style tokens sparingly because their effect
varies.

Delay and cadence marks available: comma for short breath, semicolon or period
for sentence pause, spaced ellipsis ( ... ) for hesitation/longer pause, em dash
or -- for an abrupt break. Use spaces around ellipses: write "Kai ... and I",
not "Kai...and I". Put pauses where Embry is thinking or feeling, not mechanically.
Do not end the utterance on an ellipsis, dash, tag, or unfinished thought.
For tenderness, grief, fear, or a moment where she has to collect herself, prefer
repeated embodied cues such as "[sniff] [sniff] ... give me a second" and use
[crying] only when the line genuinely carries tears. Persona Dream will convert
these ellipses and collection cues into exact Chatterbox render_chunks
pause_after_ms silence, stitched after each generated segment with crossfade_ms={EXACT_PAUSE_CROSSFADE_MS};
your job is to put the affect beats at honest locations.
Do not prefix every line with the same tag. Put tags where Embry would actually
sigh, gasp, sniff, chuckle, or clear her throat. Tags belong before a clause or
after a complete phrase, never inside a noun phrase or immediately before a
proper name/object. Write "I thought about Kai. [sniff]" or "[sniff] I thought
about Kai", not "I thought about [sniff] Kai"."""


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
_ELLIPSIS_PAUSE_MARKER = "<PD_EXACT_ELLIPSIS_PAUSE>"


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


def compile_render_chunks(text: str, tone: str, *, max_chunk_chars: int = 180,
                          min_final_chars: int = 60) -> list[dict[str, object]]:
    """Build caller-owned Chatterbox chunks with exact silence pauses.

    Chatterbox's batch endpoint turns each ``pause_after_ms`` into real silence
    while stitching generated WAV chunks. This is the programmatic silence path;
    punctuation remains a natural prosody hint inside each generated chunk.
    """
    clean = normalize_collect_cues(str(text or ""))
    if not clean:
        return []
    split_clean = re.sub(r"(\[sniff\]\s*\[sniff\]\s*\.\.\.)\s*(give me a second[.!?]?)", rf"\1 {_ELLIPSIS_PAUSE_MARKER}\n\2", clean, flags=re.I)
    split_clean = re.sub(r"\s+\.\.\.\s+", f" {_ELLIPSIS_PAUSE_MARKER}\n", split_clean)
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
    merged_chunks: list[str] = []
    for chunk in chunks:
        speakable = " ".join(chunk.replace(_ELLIPSIS_PAUSE_MARKER, "").replace("...", "").split())
        tagless = strip_inline_markup(speakable)
        if not tagless and merged_chunks:
            merged_chunks[-1] = f"{merged_chunks[-1]} {chunk}"
        elif not tagless:
            merged_chunks.append(chunk)
        elif merged_chunks and not strip_inline_markup(" ".join(merged_chunks[-1].replace(_ELLIPSIS_PAUSE_MARKER, "").replace("...", "").split())):
            merged_chunks[-1] = f"{merged_chunks[-1]} {chunk}"
        else:
            merged_chunks.append(chunk)
    chunks = merged_chunks

    if (
        len(chunks) > 1
        and len(chunks[-1]) < min_final_chars
        and len(chunks[-2]) >= int(max_chunk_chars * 0.85)
        and not _COLLECT_RE.search(chunks[-2])
    ):
        # Chatterbox ASR is flaky on tiny final tails after a near-max chunk
        # ("Kai stood" -> "Kais didn't"). Merge only that pathological tail;
        # keep ordinary ellipsis pauses split for exact-silence tests.
        chunks[-2] = f"{chunks[-2]} {chunks[-1]}"
        chunks.pop()
    if not chunks:
        chunks = [clean]
    planned: list[dict[str, object]] = []
    for idx, chunk in enumerate(chunks):
        had_ellipsis_pause = _ELLIPSIS_PAUSE_MARKER in chunk
        speakable_chunk = " ".join(chunk.replace(_ELLIPSIS_PAUSE_MARKER, "").replace("...", "").split())
        if not speakable_chunk:
            continue
        pause_after_ms = 900 if had_ellipsis_pause and idx != len(chunks) - 1 else pause_ms_for_chunk(speakable_chunk, final=idx == len(chunks) - 1)
        planned.append({
            "text": speakable_chunk,
            "tone": tone,
            "pause_after_ms": pause_after_ms,
            "role": "persona_affect_beat",
            "interruptible": True,
        })
    return planned
