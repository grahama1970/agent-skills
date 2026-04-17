"""
Movie Ingest Skill - Transcription Module
Whisper transcription and PersonaPlex JSON generation.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from rich.console import Console

from config import EMOTION_DIMENSIONS, HORUS_ARCHETYPE_MAP
from scenes import (
    attach_tags_to_segments,
    attach_audio_intensity_tags,
    parse_subtitle_file,
)
from utils import get_whisper_bin, run_subprocess

console = Console()


def compute_emotional_dimensions(
    emotion_tag: Optional[str],
    wpm: float,
    pause_count: int,
    tags: set[str],
) -> Dict[str, Any]:
    """
    Compute ToM-aligned emotional dimensions from rhythm and tags.
    Returns valence, arousal, dominance + archetype mapping for Horus.
    """
    # Base dimensions from emotion tag
    emotion = emotion_tag.lower() if emotion_tag else "anger"
    base_dims = EMOTION_DIMENSIONS.get(emotion, EMOTION_DIMENSIONS["anger"])

    # Adjust arousal based on WPM (faster speech = higher arousal)
    wpm_arousal_modifier = min(1.0, max(0.0, (wpm - 80) / 100))

    # Adjust dominance based on pause patterns
    pause_dominance_modifier = max(0.0, 1.0 - (pause_count * 0.1))

    # Compute tag intensity boost
    intensity_tags = {"rage", "rage_candidate", "shout", "anger_candidate"}
    tag_intensity = len(tags & intensity_tags) / max(1, len(intensity_tags))

    # Final computed dimensions
    computed = {
        "emotional_valence": round(base_dims["valence"], 2),
        "emotional_arousal": round(
            min(1.0, base_dims["arousal"] * 0.6 + wpm_arousal_modifier * 0.4), 2
        ),
        "emotional_dominance": round(
            min(1.0, base_dims["dominance"] * 0.7 + pause_dominance_modifier * 0.3), 2
        ),
        "primary_emotion": emotion,
        "intensity_score": round(tag_intensity, 2),
    }

    # Add archetype mapping for Horus lore transfer
    archetype = HORUS_ARCHETYPE_MAP.get(emotion, HORUS_ARCHETYPE_MAP["anger"])
    computed["horus_archetype"] = {
        "primary": archetype["primary_archetype"],
        "actor_model": archetype.get("actor_model", "Unknown"),
        "voice_tone": archetype.get("voice_tone", "neutral"),
        "trauma_equivalent": archetype["trauma_equivalent"],
        "bdi_patterns": {
            "belief": archetype["belief_pattern"],
            "desire": archetype["desire_pattern"],
            "intention": archetype["intention_pattern"],
        },
    }

    return computed


def resolve_subtitle_file(input_file: Path, explicit: Optional[Path]) -> Path:
    """
    Find a subtitle file for a video.
    Uses explicit path if provided, otherwise searches next to video.
    """
    import typer

    if explicit:
        if not explicit.exists():
            raise typer.BadParameter(f"Subtitle file {explicit} does not exist")
        return explicit

    candidates = list(input_file.parent.glob(f"{input_file.stem}*.srt"))
    if not candidates:
        raise typer.BadParameter(
            "Subtitle .srt file not found. Provide --subtitle pointing to a release with emotion cues."
        )

    return sorted(candidates, key=lambda p: len(p.name))[0]


def run_whisper(
    audio_file: Path,
    output_dir: Path,
    model: str = "medium",
    timeout_sec: int = 1800,
) -> Optional[Path]:
    """
    Run Whisper transcription on an audio file.

    Args:
        audio_file: Input audio file
        output_dir: Directory for Whisper output
        model: Whisper model name
        timeout_sec: Command timeout

    Returns:
        Path to JSON transcript, or None on failure
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        get_whisper_bin(),
        str(audio_file),
        "--model", model,
        "--output_dir", str(output_dir),
        "--output_format", "json"
    ]

    console.print(f"[cyan]Running Whisper ({model})...[/cyan]")
    run_subprocess(cmd, timeout_sec=timeout_sec)

    json_file = output_dir / f"{audio_file.stem}.json"
    if json_file.exists():
        return json_file

    console.print(f"[red]Whisper JSON not found at {json_file}[/red]")
    return None


def create_persona_json(
    transcript_json: Path,
    audio_file: Path,
    input_file: Path,
    subtitle_path: Path,
    output_path: Path,
    emotion: Optional[str] = None,
    movie_title: Optional[str] = None,
    scene: Optional[str] = None,
    characters: Optional[str] = None,
    source_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create PersonaPlex-ready JSON from Whisper transcript.

    Args:
        transcript_json: Whisper output JSON
        audio_file: Audio file used for intensity tagging
        input_file: Original video file
        subtitle_path: SRT subtitle file
        output_path: Where to save persona JSON
        emotion: Emotion tag
        movie_title: Movie title
        scene: Scene description
        characters: Comma-separated character list
        source_id: Stable clip ID

    Returns:
        The persona payload dict
    """
    with open(transcript_json) as f:
        transcript = json.load(f)

    subtitle_entries = parse_subtitle_file(subtitle_path)

    segments = transcript.get("segments", []) or []
    formatted_segments = []
    full_text_parts = []
    last_end = 0.0
    pauses = 0

    for seg in segments:
        start = float(seg.get("start", 0))
        end = float(seg.get("end", start))
        duration = max(0.0, end - start)
        text = (seg.get("text") or "").strip()
        if start - last_end > 0.5:
            pauses += 1
        last_end = end
        formatted_segments.append({
            "text": text,
            "start": round(start, 3),
            "duration": round(duration, 3),
        })
        if text:
            full_text_parts.append(text)

    total_duration = float(transcript.get("duration", last_end))
    total_words = len((" ".join(full_text_parts)).split())
    wpm = (total_words / total_duration) * 60 if total_duration > 0 else 0.0

    clip_id = source_id or input_file.stem
    character_list = [c.strip() for c in (characters.split(",") if characters else []) if c.strip()]

    # Attach tags from subtitles
    attach_tags_to_segments(formatted_segments, subtitle_entries)
    subtitle_tag_set = {tag for entry in subtitle_entries for tag in entry["tags"]}

    # Attach audio intensity tags
    audio_tag_set = attach_audio_intensity_tags(audio_file, formatted_segments)
    aggregate_tags = sorted(subtitle_tag_set | audio_tag_set)

    # Compute ToM-aligned emotional dimensions
    emotional_dims = compute_emotional_dimensions(
        emotion_tag=emotion,
        wpm=wpm,
        pause_count=pauses,
        tags=subtitle_tag_set | audio_tag_set,
    )

    meta = {
        "video_id": clip_id,
        "source": "movie",
        "movie_title": movie_title or input_file.stem,
        "scene": scene,
        "characters": character_list,
        "emotion_tag": emotion,
        "language": transcript.get("language"),
        "duration_sec": round(total_duration, 3),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_file": str(input_file),
        "subtitle_file": str(subtitle_path),
        "subtitle_tags": sorted(subtitle_tag_set),
        "audio_tags": sorted(audio_tag_set),
        "rhythm_metrics": {
            "wpm": round(wpm, 1),
            "pause_count": pauses,
            "duration_sec": round(total_duration, 2)
        }
    }

    persona_payload = {
        "meta": meta,
        "emotional_dimensions": emotional_dims,
        "full_text": " ".join(full_text_parts),
        "transcript": formatted_segments,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(persona_payload, f, indent=2)

    console.print(f"[green]Persona JSON saved to {output_path}[/green]")
    console.print(f"Rhythm: {wpm:.1f} WPM, {pauses} significant pauses")
    if aggregate_tags:
        console.print(f"Detected cue tags: {', '.join(aggregate_tags)}")

    return persona_payload
