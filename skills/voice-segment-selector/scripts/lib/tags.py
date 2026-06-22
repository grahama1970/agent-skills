"""Orpheus event-tag validation and proposal helpers."""

from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path

from lib.constants import (
    ORPHEUS_EVENT_TAGS,
    SCILLM_AUTH,
    SCILLM_TAG_MODEL,
    SCILLM_URL,
    TAG_AUTO_INSERT_MIN_CONFIDENCE,
)

TAG_PATTERN = re.compile(r"<(laugh|chuckle|sigh|cough|sniffle|groan|yawn|gasp)>", re.IGNORECASE)
ANY_TAG_PATTERN = re.compile(r"<([^>/][^>]*)>")
YOUTUBE_TAG_MAP = {
    "[laughter]": "<laugh>",
    "[laughing]": "<laugh>",
    "[laughs]": "<laugh>",
    "(laughs)": "<laugh>",
    "(laughing)": "<laugh>",
    "[chuckle]": "<chuckle>",
    "[chuckles]": "<chuckle>",
    "[sigh]": "<sigh>",
    "[sighs]": "<sigh>",
    "(sighs)": "<sigh>",
    "[cough]": "<cough>",
    "[coughs]": "<cough>",
    "[sniffle]": "<sniffle>",
    "[sniffles]": "<sniffle>",
    "[groan]": "<groan>",
    "[groans]": "<groan>",
    "[yawn]": "<yawn>",
    "[yawns]": "<yawn>",
    "[gasp]": "<gasp>",
    "[gasps]": "<gasp>",
}


def normalize_orpheus_tag(tag: str) -> str:
    lowered = tag.strip().lower()
    if not lowered.startswith("<"):
        lowered = f"<{lowered.strip('<>')}>"
    if lowered not in ORPHEUS_EVENT_TAGS:
        raise ValueError(f"Unsupported Orpheus tag: {tag}")
    return lowered


def find_disallowed_tags(text: str) -> list[str]:
    disallowed: list[str] = []
    for match in ANY_TAG_PATTERN.finditer(text):
        token = f"<{match.group(1).lower()}>"
        if token not in ORPHEUS_EVENT_TAGS:
            disallowed.append(token)
    return disallowed


def normalize_caption_tags(text: str) -> tuple[str, list[dict]]:
    updated = text
    proposals: list[dict] = []
    for source, target in YOUTUBE_TAG_MAP.items():
        pattern = re.compile(re.escape(source), re.IGNORECASE)
        if not pattern.search(updated):
            continue
        updated = pattern.sub(target, updated)
        proposals.append(
            {
                "tag": target,
                "confidence": 0.95,
                "method": "caption-normalizer",
                "reason": f"Mapped caption token {source}",
            }
        )
    return updated, proposals


def strip_tags(text: str) -> str:
    cleaned = TAG_PATTERN.sub(" ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def validate_tagged_transcript(plain_caption: str, candidate_tts_text: str) -> list[str]:
    errors: list[str] = []
    if strip_tags(plain_caption) != strip_tags(candidate_tts_text):
        errors.append("Tagged tts_text changed spoken words; only inline Orpheus tags may be inserted.")
    errors.extend(f"Unsupported custom tag: {token}" for token in find_disallowed_tags(candidate_tts_text))
    return errors


def extract_tag_tokens(text: str) -> list[str]:
    return [f"<{match.group(1).lower()}>" for match in TAG_PATTERN.finditer(text)]


def plain_caption(row: dict) -> str:
    return str(row.get("plain_caption") or row.get("transcript_draft") or row.get("transcript") or "").strip()


def tts_text_candidate(row: dict) -> str:
    return str(row.get("tts_text_candidate") or row.get("transcript_tagged") or "").strip()


def alignment_metadata(row: dict) -> dict:
    return {
        "start_sec": row.get("start_sec"),
        "end_sec": row.get("end_sec"),
        "duration_sec": row.get("duration_sec"),
        "asr_confidence": row.get("asr_confidence"),
        "language": row.get("language"),
        "source": row.get("source"),
    }


def emotion_tags(row: dict) -> list[str]:
    explicit = row.get("emotion_tags")
    if isinstance(explicit, list) and explicit:
        return [normalize_orpheus_tag(str(tag)) for tag in explicit]
    candidate = tts_text_candidate(row) or str(row.get("tts_text") or row.get("transcript_final") or "")
    return extract_tag_tokens(candidate)


def tag_source(row: dict) -> str:
    return str(row.get("tag_source") or row.get("tag_method") or "none")


def tag_confidence(row: dict) -> float | None:
    value = row.get("tag_confidence")
    return float(value) if value is not None else None


def exportable_tts_text(row: dict) -> str:
    """Training text for Orpheus export. Never returns unreviewed auto-tags by default."""
    reviewed = str(row.get("tts_text") or row.get("transcript_final") or "").strip()
    if reviewed:
        return reviewed
    status = str(row.get("review_status") or "pending")
    candidate = tts_text_candidate(row)
    if status == "auto_high_confidence" and candidate:
        return candidate
    return ""


def effective_transcript(row: dict) -> str:
    """General metadata export text: reviewed tts_text, else plain caption."""
    reviewed = exportable_tts_text(row)
    if reviewed:
        return reviewed
    return plain_caption(row)


def sync_canonical_fields(row: dict) -> dict:
    caption = plain_caption(row)
    candidate = tts_text_candidate(row)
    reviewed = str(row.get("tts_text") or row.get("transcript_final") or "").strip()
    synced = {
        **row,
        "plain_caption": caption,
        "transcript_draft": caption,
        "tts_text_candidate": candidate,
        "transcript_tagged": candidate,
        "emotion_tags": emotion_tags(row),
        "tag_source": tag_source(row),
        "alignment": alignment_metadata(row),
    }
    if reviewed:
        synced["tts_text"] = reviewed
        synced["transcript_final"] = reviewed
        synced["transcript"] = reviewed
    else:
        synced["transcript"] = caption
    return synced


def _parse_json_payload(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.DOTALL).strip()
    return json.loads(raw)



def _scillm_headers(scillm_auth: str) -> dict[str, str]:
    return {"Authorization": scillm_auth, "X-Caller-Skill": "voice-segment-selector"}


def propose_tags_scillm_text(
    *,
    row: dict,
    draft: str,
    scillm_url: str = SCILLM_URL,
    scillm_auth: str = SCILLM_AUTH,
    model: str = SCILLM_TAG_MODEL,
    timeout_sec: float = 120.0,
) -> dict:
    """Cheap text-only tag proposal via Chutes/scillm (no audio attachment)."""
    try:
        import httpx
    except ImportError as exc:
        raise RuntimeError("Install httpx for tag-propose") from exc

    words = row.get("words") or []
    allowed = ", ".join(ORPHEUS_EVENT_TAGS)
    bundle = {
        "plain_caption": draft,
        "words": words,
        "prosody_events": row.get("prosody_events") or [],
        "emotion_probs": row.get("emotion_probs") or {},
        "emotion_top": row.get("emotion_top"),
        "speaker_id": row.get("speaker_id"),
        "allowed_tags": list(ORPHEUS_EVENT_TAGS),
    }
    prompt = f"""You are proposing Orpheus TTS event tags from structured sidecar metadata.

Input JSON:
{json.dumps(bundle, indent=2)}

Allowed tags ONLY: {allowed}

Rules:
- Return tag insertions at word indices, not rewritten prose.
- Do not change spoken words; only choose where tags belong.
- Prefer no tag over guessing.
- Do not map emotion labels (angry/happy/sad) to tags.
- Use prosody_events as hints; they are not ground truth.

Return JSON only:
{{
  "confidence": 0.0,
  "tags": [
    {{"tag": "<laugh>", "before_word_index": 0, "confidence": 0.0, "reason": "..."}}
  ]
}}"""

    response = httpx.post(
        scillm_url,
        headers=_scillm_headers(scillm_auth),
        json={"model": model, "messages": [{"role": "user", "content": prompt}]},
        timeout=timeout_sec,
    )
    response.raise_for_status()
    payload = response.json()
    content = payload["choices"][0]["message"]["content"]
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    parsed = _parse_json_payload(str(content))
    confidence = float(parsed.get("confidence") or 0.0)
    tag_by_index: dict[int, str] = {}
    normalized_tags = []
    for item in parsed.get("tags") or []:
        try:
            tag = normalize_orpheus_tag(str(item.get("tag", "")))
            index = int(item.get("before_word_index", 0))
            tag_by_index[index] = tag
            normalized_tags.append(
                {
                    "tag": tag,
                    "confidence": float(item.get("confidence") or confidence),
                    "method": "scillm-text",
                    "reason": str(item.get("reason") or "").strip(),
                    "before_word_index": index,
                }
            )
        except (ValueError, TypeError):
            continue

    if words and tag_by_index:
        candidate = splice_tags_at_word_indices(words, tag_by_index)
    elif tag_by_index and not words:
        candidate = draft
    else:
        candidate = draft

    return {
        "tts_text_candidate": candidate,
        "confidence": confidence,
        "tags": normalized_tags,
        "tag_source": "scillm-text",
    }


def propose_tags_scillm_audio(
    *,
    clip_path: Path,
    draft: str,
    scillm_url: str = SCILLM_URL,
    scillm_auth: str = SCILLM_AUTH,
    model: str = SCILLM_TAG_MODEL,
    timeout_sec: float = 120.0,
) -> dict:
    try:
        import httpx
    except ImportError as exc:
        raise RuntimeError("Install httpx for tag-propose") from exc

    audio_b64 = base64.b64encode(clip_path.read_bytes()).decode()
    allowed = ", ".join(ORPHEUS_EVENT_TAGS)
    prompt = f"""Listen to the attached audio clip and review this plain caption.

Plain caption:
{draft}

Propose inline Orpheus event tags ONLY where clearly audible:
{allowed}

Rules:
- Do not change spoken words except inserting tags.
- Prefer no tag over guessing.
- Do not use custom style tags like <angry> or <sarcastic>.
- Return JSON only:
{{
  "tts_text_candidate": "...",
  "confidence": 0.0,
  "tags": [{{"tag": "<laugh>", "confidence": 0.0, "reason": "..."}}]
}}"""

    response = httpx.post(
        scillm_url,
        headers={"Authorization": scillm_auth, "X-Caller-Skill": "voice-segment-selector"},
        json={
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"inlineData": {"mimeType": "audio/wav", "data": audio_b64}},
                    ],
                }
            ],
        },
        timeout=timeout_sec,
    )
    response.raise_for_status()
    payload = response.json()
    content = payload["choices"][0]["message"]["content"]
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    parsed = _parse_json_payload(str(content))
    tagged = str(parsed.get("tts_text_candidate") or parsed.get("transcript_tagged") or draft).strip()
    confidence = float(parsed.get("confidence") or 0.0)
    tags = parsed.get("tags") or []
    normalized_tags = []
    for item in tags:
        try:
            normalized_tags.append(
                {
                    "tag": normalize_orpheus_tag(str(item.get("tag", ""))),
                    "confidence": float(item.get("confidence") or confidence),
                    "method": "scillm-audio",
                    "reason": str(item.get("reason") or "").strip(),
                }
            )
        except ValueError:
            continue
    return {
        "tts_text_candidate": tagged,
        "confidence": confidence,
        "tags": normalized_tags,
        "tag_source": "scillm-audio",
    }


def propose_tags_for_clip(
    *,
    clip_path: Path,
    draft: str,
    row: dict | None = None,
    use_scillm: bool = True,
    use_audio_llm: bool = False,
    auto_insert_high_confidence: bool = False,
    scillm_url: str | None = None,
    scillm_auth: str | None = None,
    model: str = SCILLM_TAG_MODEL,
    audio_model: str | None = None,
) -> dict:
    from lib.constants import SCILLM_TAG_AUDIO_MODEL

    caption_text, caption_tags = normalize_caption_tags(draft)
    error = ""
    row = row or {}
    url = scillm_url or os.getenv("SCILLM_URL", SCILLM_URL)
    auth = scillm_auth or os.getenv("SCILLM_AUTH", SCILLM_AUTH)
    candidate = caption_text
    tags = list(caption_tags)
    confidence = 0.95 if caption_tags else 0.0
    tag_source_value = "caption-normalizer"

    if use_scillm:
        try:
            if use_audio_llm and clip_path.exists():
                proposal = propose_tags_scillm_audio(
                    clip_path=clip_path,
                    draft=caption_text,
                    scillm_url=url,
                    scillm_auth=auth,
                    model=audio_model or SCILLM_TAG_AUDIO_MODEL,
                )
            else:
                proposal = propose_tags_scillm_text(
                    row={**row, "plain_caption": caption_text},
                    draft=caption_text,
                    scillm_url=url,
                    scillm_auth=auth,
                    model=model,
                )
            candidate = proposal["tts_text_candidate"]
            tags = caption_tags + proposal.get("tags", [])
            confidence = float(proposal.get("confidence") or 0.0)
            tag_source_value = proposal.get("tag_source", "scillm-text")
        except Exception as exc:
            candidate = caption_text
            tags = caption_tags
            confidence = 0.95 if caption_tags else 0.0
            tag_source_value = "caption-normalizer"
            error = str(exc)
    elif not caption_tags:
        candidate = caption_text
        tags = caption_tags
        confidence = 0.0
        tag_source_value = "caption-normalizer"

    errors = validate_tagged_transcript(caption_text, candidate)
    review_status = "pending"
    tts_text = ""
    if (
        auto_insert_high_confidence
        and not errors
        and confidence >= TAG_AUTO_INSERT_MIN_CONFIDENCE
        and candidate != draft
    ):
        review_status = "auto_high_confidence"
        tts_text = candidate

    emotion_tag_list = [str(item.get("tag")) for item in tags if item.get("tag")]
    return sync_canonical_fields(
        {
            "plain_caption": draft,
            "tts_text_candidate": candidate,
            "tts_text": tts_text,
            "transcript_final": tts_text,
            "transcript": draft,
            "tag_confidence": round(confidence, 4),
            "tag_proposals": tags,
            "tag_source": tag_source_value,
            "tag_method": tag_source_value,
            "emotion_tags": emotion_tag_list,
            "tag_errors": errors,
            "review_status": review_status,
            "tag_error": error,
        }
    )


def caption_from_words(words: list[dict]) -> str:
    return " ".join(str(word.get("word", "")).strip() for word in words if str(word.get("word", "")).strip())


def splice_tags_at_word_indices(words: list[dict], tag_by_index: dict[int, str]) -> str:
    if not words:
        return ""
    parts: list[str] = []
    for index, word in enumerate(words):
        if index in tag_by_index:
            parts.append(normalize_orpheus_tag(tag_by_index[index]))
        parts.append(str(word.get("word", "")).strip())
    return " ".join(part for part in parts if part)


def propose_tags_from_prosody(
    row: dict,
    *,
    auto_insert_high_confidence: bool = False,
    min_confidence: float | None = None,
    use_scillm_refine: bool = False,
    scillm_url: str | None = None,
    scillm_auth: str | None = None,
    model: str = SCILLM_TAG_MODEL,
) -> dict:
    from lib.constants import PROSODY_AUTO_INSERT_MIN_CONFIDENCE

    threshold = min_confidence if min_confidence is not None else PROSODY_AUTO_INSERT_MIN_CONFIDENCE
    words = row.get("words") or []
    caption = plain_caption(row) or caption_from_words(words)
    events = row.get("prosody_events") or []
    tag_by_index: dict[int, str] = {}
    proposals: list[dict] = []
    for event in sorted(events, key=lambda item: float(item.get("confidence") or 0.0), reverse=True):
        try:
            tag = normalize_orpheus_tag(str(event.get("tag", "")))
        except ValueError:
            continue
        index = int(event.get("before_word_index", 0))
        confidence = float(event.get("confidence") or 0.0)
        if index in tag_by_index:
            continue
        tag_by_index[index] = tag
        proposals.append(
            {
                "tag": tag,
                "confidence": confidence,
                "method": str(event.get("source") or "prosody-heuristic"),
                "reason": str(event.get("reason") or ""),
                "before_word_index": index,
                "at_sec": event.get("at_sec"),
            }
        )

    candidate = splice_tags_at_word_indices(words, tag_by_index) if tag_by_index else caption
    errors = validate_tagged_transcript(caption, candidate) if tag_by_index else []
    if use_scillm_refine and not tag_by_index:
        try:
            llm = propose_tags_scillm_text(
                row=row,
                draft=caption,
                scillm_url=scillm_url or os.getenv("SCILLM_URL", SCILLM_URL),
                scillm_auth=scillm_auth or os.getenv("SCILLM_AUTH", SCILLM_AUTH),
                model=model,
            )
            for item in llm.get("tags") or []:
                index = int(item.get("before_word_index", 0))
                if index in tag_by_index:
                    continue
                tag_by_index[index] = str(item.get("tag"))
                proposals.append(item)
            if tag_by_index:
                candidate = splice_tags_at_word_indices(words, tag_by_index)
                errors = validate_tagged_transcript(caption, candidate)
        except Exception:
            pass

    max_conf = max((float(item.get("confidence") or 0.0) for item in proposals), default=0.0)
    review_status = "pending"
    tts_text = ""
    if (
        auto_insert_high_confidence
        and not errors
        and tag_by_index
        and max_conf >= threshold
    ):
        review_status = "auto_high_confidence"
        tts_text = candidate

    return sync_canonical_fields(
        {
            **row,
            "plain_caption": caption,
            "tts_text_candidate": candidate,
            "tts_text": tts_text,
            "transcript_final": tts_text,
            "transcript": caption,
            "tag_confidence": round(max_conf, 4),
            "tag_proposals": proposals,
            "tag_source": "prosody-heuristic" if proposals else "none",
            "tag_method": "prosody-heuristic" if proposals else "none",
            "emotion_tags": [item["tag"] for item in proposals],
            "tag_errors": errors,
            "review_status": review_status,
        }
    )
