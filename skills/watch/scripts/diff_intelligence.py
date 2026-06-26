"""Classify meaningful SRT-vs-Whisper differences.

SRT and Whisper are complementary sources, not competitors:
- SRT = official script with audio cues (SIGHS), speaker labels (Name:)
- Whisper = raw audio transcription, catches ad-libs and background dialogue

We only flag semantically meaningful differences:
- hidden_dialogue: Whisper caught dialogue SRT omitted entirely
- sanitized: SRT cleaned up profanity or raw language vs Whisper
- acoustic_context: SRT has audio cues but Whisper heard no speech

Everything else is nominal — different phrasings of the same content is expected.
"""
from __future__ import annotations

import re
from typing import Any

_SOUND_CUE_RE = re.compile(r"[\[\(][A-Z\s,]+[\]\)]")

_SANITIZATION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(jesus|christ|god|damn|hell|fuck|shit|ass|crap|cock|dick|piss|bastard|bitch)\b", re.IGNORECASE), "profanity"),
    (re.compile(r"\b(screw|darn|freakin|frickin|gosh|heck)\b", re.IGNORECASE), "euphemism"),
]


def _has_content(text: str | None) -> bool:
    if not text:
        return False
    cleaned = text.strip().lower()
    return bool(cleaned) and "no transcript" not in cleaned

_ALL_SOUND_OR_EMPTY_RE = re.compile(r"^[\[\(][A-Z\s,]+[\]\)]$")


def classify_row(srt_text: str | None, whisper_text: str | None) -> dict[str, Any]:
    srt = (srt_text or "").strip()
    whisper = (whisper_text or "").strip()
    srt_has = _has_content(srt)
    whisper_has = _has_content(whisper)
    srt_only_cues = srt_has and bool(_ALL_SOUND_OR_EMPTY_RE.match(srt))

    if not srt_has and whisper_has:
        return {"category": "hidden_dialogue", "confidence": 0.9,
                "detail": "Whisper caught dialogue SRT omitted entirely"}

    if srt_only_cues and not whisper_has:
        return {"category": "acoustic_context", "confidence": 0.85,
                "detail": f"SRT has audio cue \"{srt}\" but Whisper detected no speech"}
    if srt_only_cues and whisper_has:
        return {"category": "hidden_dialogue", "confidence": 0.8,
                "detail": f"Whisper caught dialogue under SRT sound cue \"{srt}\""}

    if srt_has and not whisper_has:
        return {"category": "acoustic_context", "confidence": 0.6,
                "detail": "SRT has dialogue Whisper did not capture"}

    if not srt_has and not whisper_has:
        return {"category": "match", "confidence": 1.0, "detail": "Both empty"}

    for pattern, label in _SANITIZATION_PATTERNS:
        if pattern.search(whisper) and not pattern.search(srt):
            return {"category": "sanitized", "confidence": 0.8,
                    "detail": f"Whisper captures raw language ({label}) that SRT cleaned"}

    return {"category": "match", "confidence": 0.9,
            "detail": "Both describe the same scene (expected wording variation)"}


def get_row_diff(scene_element: dict) -> dict[str, Any] | None:
    result = classify_row(scene_element.get("srt_text"), scene_element.get("text"))
    if result["category"] == "match":
        return None
    return result


COLON_SPEAKER_RE = re.compile(r"^([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)?):\s")

def _extract_character(text: str | None) -> str | None:
    if not text:
        return None
    m = COLON_SPEAKER_RE.search(text)
    return m.group(1) if m else None


def build_diff_intelligence(scene_elements: list[dict]) -> dict[str, Any]:
    anomalies: list[dict[str, Any]] = []
    category_counts: dict[str, int] = {}
    char_map: dict[str, dict[str, Any]] = {}

    for row in scene_elements:
        result = classify_row(row.get("srt_text"), row.get("text"))
        cat = result["category"]
        category_counts[cat] = category_counts.get(cat, 0) + 1
        if cat != "match":
            anomaly = {
                "index": row.get("index"),
                "timecode": row.get("timecode"),
                "category": cat,
                "confidence": round(result["confidence"], 3),
                "detail": result["detail"],
            }
            anomalies.append(anomaly)

            speaker = _extract_character(row.get("srt_text")) or _extract_character(row.get("text"))
            if speaker:
                if speaker not in char_map:
                    char_map[speaker] = {"name": speaker, "scene_count": 0, "divergence_count": 0, "top_divergences": []}
                ci = char_map[speaker]
                ci["scene_count"] += 1
                ci["divergence_count"] += 1
                ci["top_divergences"].append({"timecode": row.get("timecode", ""), "category": cat, "detail": result.get("detail", "")[:80]})

    character_intel = []
    for ci in char_map.values():
        ci["top_divergences"] = ci["top_divergences"][:3]
        ci["insight"] = (
            f"{ci['name']} has {ci['divergence_count']} divergence(s) across {ci['scene_count']} scene(s)"
            if ci["divergence_count"] > 1
            else f"{ci['name']} has 1 divergence in their dialogue"
        )
        character_intel.append(ci)
    character_intel.sort(key=lambda c: c["divergence_count"], reverse=True)

    total = len(scene_elements)
    match_count = category_counts.get("match", 0)
    overall_diff_pct = round((total - match_count) / total * 100) if total > 0 else 0

    takeaways: list[str] = []
    sanitized = category_counts.get("sanitized", 0)
    hidden = category_counts.get("hidden_dialogue", 0)
    occluded = category_counts.get("acoustic_context", 0)

    if sanitized:
        takeaways.append(
            f"SRT sanitized dialogue in {sanitized} scene(s) — "
            "Whisper caught profanity the official subtitles cleaned"
        )
    if hidden:
        takeaways.append(
            f"Whisper uncovered {hidden} scene(s) of hidden dialogue — "
            "background chatter or hot-mic moments missing from SRT"
        )
    if occluded:
        takeaways.append(
            f"Whisper missed {occluded} scene(s) of acoustic context — "
            "SRT captured audio cues Whisper did not transcribe"
        )
    if not takeaways:
        takeaways.append("No meaningful divergence — SRT and Whisper agree on all scenes")

    return {
        "overall_diff_percentage": overall_diff_pct,
        "category_counts": category_counts,
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
        "character_intel": character_intel,
        "takeaways": takeaways,
    }
