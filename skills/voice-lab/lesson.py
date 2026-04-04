"""Voice lesson package creation and storage.

Assembles complete voice lesson packages for Horus:
  - SRT (text + timing)
  - Stems (original artist vocals)
  - .pt file (current PersonaPlex voice anchor)
  - graham.wav (human performance)
  - prompt.md (learning guidance)
  - alignment.json (per-segment timing + scores)

Also supports exporting to Qwen3-TTS fine-tuning JSONL format.
"""

from __future__ import annotations

import os

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

STORAGE_ROOT = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb")) / "media"


@dataclass
class LessonManifest:
    """Manifest for a voice lesson package."""

    persona: str
    source: str = ""
    scene: str = ""
    date: str = ""
    segments: int = 0
    avg_similarity: float = 0.0
    registers: list[str] = field(default_factory=list)
    emotions: list[str] = field(default_factory=list)
    prompt_file: str = "prompt.md"
    training_ready: bool = False
    qwen3_jsonl: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "persona": self.persona,
            "source": self.source,
            "scene": self.scene,
            "date": self.date,
            "segments": self.segments,
            "avg_similarity": round(self.avg_similarity, 3),
            "registers": self.registers,
            "emotions": self.emotions,
            "prompt_file": self.prompt_file,
            "training_ready": self.training_ready,
            "qwen3_jsonl": self.qwen3_jsonl,
        }


QWEN3_SAMPLE_RATE = 24000


def _resample_to_24k(audio_path: Path, output_path: Path) -> Path:
    """Resample audio to 24kHz mono for Qwen3-TTS compatibility."""
    from scipy.signal import resample_poly
    from math import gcd

    audio, sr = sf.read(str(audio_path), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    if sr != QWEN3_SAMPLE_RATE:
        g = gcd(sr, QWEN3_SAMPLE_RATE)
        audio = resample_poly(audio, QWEN3_SAMPLE_RATE // g, sr // g).astype(np.float32)

    sf.write(str(output_path), audio, QWEN3_SAMPLE_RATE)
    return output_path


def _find_voice_anchor(persona: str) -> Optional[Path]:
    """Find the latest PersonaPlex voice anchor .pt file."""
    anchor_dir = STORAGE_ROOT / "personas" / persona / "personaplex" / "voices"
    if not anchor_dir.exists():
        return None
    pt_files = sorted(anchor_dir.glob("*.pt"))
    return pt_files[-1] if pt_files else None


def _generate_prompt(
    persona: str,
    source: str,
    registers: list[str],
    emotions: list[str],
    custom_prompt: Optional[str] = None,
) -> str:
    """Generate learning guidance prompt for Horus."""
    if custom_prompt:
        return custom_prompt

    register_str = ", ".join(registers) if registers else "natural speaking"
    emotion_str = ", ".join(emotions) if emotions else "neutral to moderate"

    return f"""# Voice Lesson: {source}

## Target Persona: {persona}

## Focus Areas
- **Registers**: {register_str}
- **Emotions**: {emotion_str}

## Guidance
Listen to Graham's recording and compare with the original vocals.
Pay attention to:
1. How Graham naturally inflects these registers
2. The timing and rhythm of emotional transitions
3. Breathing patterns and pause placement
4. Vocal texture differences between Graham and the original

## Training Notes
- Use this lesson's JSONL for Qwen3-TTS fine-tuning
- Reference audio should be consistent across all segments
- Ideal segment duration: 1.5-15 seconds
- Discard segments with clipping or excessive background noise
"""


def create_lesson(
    session_dir: Path,
    persona: str = "embry",
    source: str = "",
    scene: str = "",
    registers: Optional[list[str]] = None,
    emotions: Optional[list[str]] = None,
    custom_prompt: Optional[str] = None,
    qwen3_ready: bool = False,
) -> Optional[Path]:
    """Create a voice lesson package from a session directory.

    Expects session_dir to contain:
    - graham.wav (recorded performance)
    - alignment.json (from alignment.py)
    - Optionally: segments/ directory

    Args:
        session_dir: Path to session output directory.
        persona: Persona name.
        source: Source content (e.g. "blade_runner_2049").
        scene: Scene identifier.
        registers: Voice registers (e.g. ["tired", "tense"]).
        emotions: Emotions present (e.g. ["melancholy"]).
        custom_prompt: Custom learning prompt (overrides generated one).
        qwen3_ready: Resample segments to 24kHz mono for Qwen3-TTS.

    Returns:
        Path to lesson directory, or None on failure.
    """
    registers = registers or []
    emotions = emotions or []

    # Validate session directory
    graham_wav = session_dir / "graham.wav"
    if not graham_wav.exists():
        console.print(f"[red]graham.wav not found in {session_dir}[/red]")
        return None

    # Create lesson directory
    date_str = datetime.now().strftime("%Y%m%d")
    source_slug = source.lower().replace(" ", "_") if source else "unknown"
    scene_slug = scene.lower().replace(" ", "_") if scene else "session"
    lesson_id = f"{source_slug}_{scene_slug}_{date_str}"
    lesson_dir = STORAGE_ROOT / "personas" / persona / "voice-lessons" / lesson_id
    lesson_dir.mkdir(parents=True, exist_ok=True)

    console.print(Panel(f"Creating voice lesson: {lesson_id}", title="voice-lab"))

    # Copy graham.wav
    shutil.copy2(graham_wav, lesson_dir / "graham.wav")
    console.print("  [green]+[/green] graham.wav")

    # Copy alignment.json if exists
    alignment_path = session_dir / "alignment.json"
    segments_count = 0
    avg_similarity = 0.0
    if alignment_path.exists():
        shutil.copy2(alignment_path, lesson_dir / "alignment.json")
        alignment_data = json.loads(alignment_path.read_text())
        segments_count = len(alignment_data)
        sims = [s["similarity"] for s in alignment_data if s.get("similarity", 0) > 0]
        avg_similarity = sum(sims) / len(sims) if sims else 0.0
        console.print(f"  [green]+[/green] alignment.json ({segments_count} segments)")

    # Copy SRT if exists in parent or session dir
    srt_files = list(session_dir.glob("*.srt"))
    if srt_files:
        shutil.copy2(srt_files[0], lesson_dir / "subtitles.srt")
        console.print(f"  [green]+[/green] subtitles.srt")

    # Copy segments directory
    segments_dir = session_dir / "segments"
    if segments_dir.exists():
        shutil.copytree(segments_dir, lesson_dir / "segments", dirs_exist_ok=True)
        console.print("  [green]+[/green] segments/")

    # Find and copy voice anchor
    anchor = _find_voice_anchor(persona)
    if anchor:
        shutil.copy2(anchor, lesson_dir / "voice_anchor.pt")
        console.print(f"  [green]+[/green] voice_anchor.pt ({anchor.name})")
    else:
        console.print("  [yellow]-[/yellow] voice_anchor.pt (not found)")

    # Find and copy original vocals stem
    # Check session dir for original vocals
    for stem_name in ["original_vocals.wav", "vocals.wav"]:
        stem_src = session_dir / stem_name
        if stem_src.exists():
            shutil.copy2(stem_src, lesson_dir / "original_vocals.wav")
            console.print(f"  [green]+[/green] original_vocals.wav")
            break

    # Generate prompt
    prompt_text = _generate_prompt(
        persona=persona,
        source=source,
        registers=registers,
        emotions=emotions,
        custom_prompt=custom_prompt,
    )
    (lesson_dir / "prompt.md").write_text(prompt_text)
    console.print("  [green]+[/green] prompt.md")

    # Determine training readiness (unified with GateReport: 70% pass rate)
    # Count segments that pass basic quality (no clipping, not too quiet, 2-12s)
    passed_segments = 0
    if alignment_path.exists():
        for seg in alignment_data:
            quality = seg.get("quality", {})
            if quality.get("clipping") or quality.get("too_quiet"):
                continue
            dur_ms = seg.get("end_ms", 0) - seg.get("start_ms", 0)
            if 2000 <= dur_ms <= 12000:
                passed_segments += 1

    training_ready = (
        segments_count >= 5
        and passed_segments >= segments_count * 0.7
        and avg_similarity >= 0.5
        and graham_wav.exists()
    )

    # Generate Qwen3-TTS fine-tuning JSONL
    jsonl_path = None
    if training_ready and alignment_path.exists():
        jsonl_path = _export_qwen3_jsonl(
            lesson_dir=lesson_dir,
            alignment_data=alignment_data,
            persona=persona,
            qwen3_ready=qwen3_ready,
        )

    # Create manifest
    manifest = LessonManifest(
        persona=persona,
        source=source,
        scene=scene,
        date=date_str,
        segments=segments_count,
        avg_similarity=avg_similarity,
        registers=registers,
        emotions=emotions,
        training_ready=training_ready,
        qwen3_jsonl=str(jsonl_path) if jsonl_path else None,
    )

    manifest_path = lesson_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest.to_dict(), indent=2))
    console.print("  [green]+[/green] manifest.json")

    # Summary
    console.print(f"\n[bold]Lesson created:[/bold] {lesson_dir}")
    console.print(f"  Segments: {segments_count}")
    console.print(f"  Avg similarity: {avg_similarity:.3f}")
    ready_str = "[green]YES[/green]" if training_ready else "[red]NO[/red]"
    console.print(f"  Training ready: {ready_str}")

    return lesson_dir


def _export_qwen3_jsonl(
    lesson_dir: Path,
    alignment_data: list[dict],
    persona: str,
    qwen3_ready: bool = False,
) -> Optional[Path]:
    """Export alignment data as Qwen3-TTS fine-tuning JSONL.

    Format per line: {"audio": "path.wav", "text": "...", "ref_audio": "ref.wav", "duration": N}

    If qwen3_ready=True, resamples segments to 24kHz mono.
    """
    graham_segments_dir = lesson_dir / "segments" / "graham"
    ref_audio = lesson_dir / "graham.wav"  # Use full recording as reference

    # Resample ref_audio to 24kHz if needed
    if qwen3_ready and ref_audio.exists():
        ref_24k = lesson_dir / "graham_24k.wav"
        _resample_to_24k(ref_audio, ref_24k)
        ref_audio = ref_24k
        console.print("  [green]+[/green] graham_24k.wav (resampled to 24kHz)")

    if not graham_segments_dir.exists():
        logger.warning("No graham segments directory for JSONL export")
        return None

    jsonl_path = lesson_dir / "training_data.jsonl"
    entries = 0

    with open(jsonl_path, "w") as f:
        for seg in alignment_data:
            seg_path = seg.get("graham_segment")
            if not seg_path:
                continue

            seg_file = Path(seg_path)
            if not seg_file.exists():
                # Try relative path from lesson dir
                seg_file = graham_segments_dir / seg_file.name
                if not seg_file.exists():
                    continue

            text = seg.get("text", "")
            if not text:
                continue

            # Skip low-quality segments
            quality = seg.get("quality", {})
            if quality.get("clipping") or quality.get("too_quiet"):
                continue

            # Skip segments outside Qwen3-TTS training range (2-12s)
            dur_ms = seg.get("end_ms", 0) - seg.get("start_ms", 0)
            if dur_ms < 2000 or dur_ms > 12000:
                continue

            # Resample segment to 24kHz if qwen3_ready
            if qwen3_ready:
                seg_24k_dir = lesson_dir / "segments" / "graham_24k"
                seg_24k_dir.mkdir(parents=True, exist_ok=True)
                seg_24k = seg_24k_dir / seg_file.name
                _resample_to_24k(seg_file, seg_24k)
                seg_file = seg_24k

            # Compute duration from alignment timing
            duration_s = (seg.get("end_ms", 0) - seg.get("start_ms", 0)) / 1000.0

            entry = {
                "audio": str(seg_file),
                "text": text,
                "ref_audio": str(ref_audio),
                "duration": round(duration_s, 3),
            }
            f.write(json.dumps(entry) + "\n")
            entries += 1

    if entries > 0:
        console.print(f"  [green]+[/green] training_data.jsonl ({entries} entries)")
        return jsonl_path

    jsonl_path.unlink(missing_ok=True)
    return None


def list_lessons(persona: str) -> list[dict]:
    """List all voice lessons for a persona."""
    lessons_dir = STORAGE_ROOT / "personas" / persona / "voice-lessons"
    if not lessons_dir.exists():
        return []

    lessons = []
    for lesson_dir in sorted(lessons_dir.iterdir()):
        if not lesson_dir.is_dir():
            continue
        manifest_path = lesson_dir / "manifest.json"
        if manifest_path.exists():
            data = json.loads(manifest_path.read_text())
            data["path"] = str(lesson_dir)
            lessons.append(data)

    return lessons


def print_lessons(persona: str) -> None:
    """Display all lessons in a table."""
    lessons = list_lessons(persona)
    if not lessons:
        console.print(f"[yellow]No voice lessons for {persona}[/yellow]")
        return

    table = Table(title=f"Voice Lessons: {persona}")
    table.add_column("Lesson ID")
    table.add_column("Source")
    table.add_column("Date")
    table.add_column("Segments", justify="right")
    table.add_column("Similarity", justify="right")
    table.add_column("Ready", justify="center")

    for lesson in lessons:
        ready = "[green]YES[/green]" if lesson.get("training_ready") else "[red]NO[/red]"
        table.add_row(
            Path(lesson.get("path", "")).name,
            lesson.get("source", ""),
            lesson.get("date", ""),
            str(lesson.get("segments", 0)),
            f"{lesson.get('avg_similarity', 0):.3f}",
            ready,
        )

    console.print(table)
