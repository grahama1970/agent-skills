"""Humming pipeline: melody guide + Orpheus ref + Seed-VC conversion."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console

from .cache import HumCache, HumTrack
from .defaults import DEFAULT_SOURCE_HUM_RENDERER
console = Console()

SKILLS_ROOT = Path(__file__).resolve().parent.parent.parent
STORAGE_ROOT = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb")) / "media"
ORPHEUS_CHECKPOINTS = Path(
    os.environ.get(
        "ORPHEUS_CHECKPOINTS_ROOT",
        "/mnt/storage12tb/skills/voice-segment-selector/checkpoints",
    )
)


def _extract_video_id(url: str) -> str:
    patterns = [
        r"(?:youtu\.be/)([a-zA-Z0-9_-]{11})",
        r"(?:youtube\.com/watch\?v=)([a-zA-Z0-9_-]{11})",
        r"(?:youtube\.com/embed/)([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    if re.match(r"^[a-zA-Z0-9_-]{11}$", url):
        return url
    raise ValueError(f"Cannot extract video ID from: {url}")


def _slugify(text: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[\s-]+", "_", slug).strip("_")
    return slug


class HumPipeline:
    """Orchestrates licensed-segment → melody hum → Orpheus + Seed-VC → cache."""

    def __init__(self, persona: str = "embry"):
        self.persona = persona
        self.cache = HumCache(persona=persona)
        self.orpheus_checkpoint = ORPHEUS_CHECKPOINTS / f"{persona}_orpheus_lora"

    def add(
        self,
        *,
        url: str | None = None,
        song: Path | None = None,
        title: Optional[str] = None,
        artist: Optional[str] = None,
        mood: Optional[list[str]] = None,
        bridges: Optional[list[str]] = None,
        persona_connection: str = "",
        start: str = "00:00:00",
        duration: str = "00:00:20",
        semi_tone_shift: int = 0,
        diffusion_steps: int = 45,
        melody_source: str | None = None,
        manual_midi: Path | None = None,
        manual_source_hum: Path | None = None,
        melody_audio: str = "auto",
        source_hum_renderer: str = DEFAULT_SOURCE_HUM_RENDERER,
        source_mode: str | None = None,
        force: bool = False,
        allow_diagnostic_cache: bool = False,
        orpheus_url: str | None = None,
        seedvc_dir: str | None = None,
    ) -> dict:
        from .melody import transcribe_to_midi
        from .midi_to_hum import synthesize_hum
        from .orpheus_client import health_ok, make_orpheus_ref
        from .seedvc import convert_hum, inference_script

        if not url and not song:
            return {"status": "error", "error": "Provide --song (licensed local file) or a YouTube URL"}

        if not self._has_orpheus_voice():
            return {
                "status": "error",
                "error": (
                    f"No Orpheus LoRA for {self.persona}. "
                    f"Run: skills/tts-voice/run.sh finish --speaker {self.persona} --job-dir <job>"
                ),
            }

        if not health_ok(orpheus_url):
            return {
                "status": "error",
                "error": "Orpheus infer service not healthy. Run: skills/tts-voice/run.sh docker-up",
            }

        try:
            inference_script(seedvc_dir)
        except FileNotFoundError as exc:
            return {"status": "error", "error": str(exc)}

        source_url = url or ""
        video_id = ""
        if url:
            video_id = _extract_video_id(url)

        with tempfile.TemporaryDirectory(prefix="hum_") as tmp:
            work = Path(tmp)

            console.print("[bold cyan]Step 1/7:[/bold cyan] Preparing song segment...")
            if song:
                segment = self._trim_segment(song, work / "song_segment.wav", start, duration)
                detected_title = song.stem
            else:
                download_result = self._download_audio(url, work)
                if not download_result:
                    return {"status": "error", "error": "Download failed"}
                audio_path, detected_title = download_result
                segment = self._trim_segment(audio_path, work / "song_segment.wav", start, duration)

            if not title:
                title = detected_title or video_id or segment.stem
            track_id = _slugify(title)

            console.print("[bold cyan]Step 2/7:[/bold cyan] Separating vocals...")
            vocals_path = self._separate_vocals(segment, work)
            if not vocals_path:
                return {"status": "error", "error": "Stem separation failed"}

            from .source_hum_gate import (
                IMPORT_RENDERERS,
                analyze_midi,
                normalize_renderer,
                renderer_requires_import,
                validate_midi_for_hum,
                validate_source_hum_wav,
            )

            renderer = normalize_renderer(source_hum_renderer)
            if source_mode:
                renderer = normalize_renderer(source_mode)

            segment_duration_s = self._get_duration(segment) or 20.0
            gate_metrics: dict = {}
            diagnostic_only = False

            if manual_source_hum:
                renderer = normalize_renderer(source_hum_renderer)
                source_hum = Path(manual_source_hum)
                if not source_hum.is_file():
                    return {"status": "error", "error": f"source hum not found: {source_hum}"}
                resolved_melody_source = renderer if renderer in IMPORT_RENDERERS else "real_hum"
            elif renderer_requires_import(renderer):
                hints = {
                    "ace": (
                        "Export closed-mouth hum from ACE Studio (MIDI + mmm/hm lyrics), "
                        "then pass --source-hum path/to/source_hum.wav"
                    ),
                    "suno_manual": (
                        "Generate a dry closed-mouth hum in Suno (Cover/Voice), export WAV, "
                        "then pass --source-hum path/to/source_hum.wav"
                    ),
                    "elevenlabs_manual": (
                        "Export MIDI/score to a simple audio reference, generate a dry closed-mouth hum "
                        "in ElevenLabs Music/Sound Effects, export WAV, then pass --source-hum path/to/source_hum.wav"
                    ),
                    "real_hum": "Record or provide a human hum WAV via --source-hum",
                }
                return {
                    "status": "error",
                    "error": f"Renderer '{renderer}' requires an imported neural/human guide hum.",
                    "hint": hints.get(renderer, "Pass --source-hum <wav>"),
                }
            elif renderer == "acestep_api":
                from .acestep_pixazo import generate_hum_guide

                console.print("[bold cyan]Step 3/7:[/bold cyan] ACE-Step hum via Pixazo API...")
                source_hum = generate_hum_guide(
                    work / "source_hum.wav",
                    duration_s=max(5, int(segment_duration_s)),
                    title=title or "",
                )
                resolved_melody_source = "acestep_pixazo"
                console.print(f"  Guide: {source_hum.name}")
            elif renderer == "vocal_stem":
                console.print("[bold cyan]Step 3/7:[/bold cyan] Using vocal stem as melody guide...")
                source_hum = vocals_path
                resolved_melody_source = "vocal_stem"
                console.print(f"  Guide: {source_hum.name}")
            elif renderer == "vocal_stem_diag":
                console.print("[bold yellow]Step 3/7:[/bold yellow] Diagnostic vocal-stem guide (not production)...")
                source_hum = vocals_path
                resolved_melody_source = "vocal_stem_diag"
                diagnostic_only = True
            elif renderer == "neural_hum":
                from .neural_hum import render_neural_hum

                melody_input = self._pick_melody_input(
                    segment, vocals_path, melody_audio, work, transcribe_to_midi,
                )
                console.print(f"  Melody input: {melody_input.name}")

                if manual_midi:
                    midi_path = Path(manual_midi)
                    resolved_melody_source = "manual_midi"
                else:
                    console.print("[bold cyan]Step 3/7:[/bold cyan] Transcribing melody (Basic Pitch)...")
                    midi_path = transcribe_to_midi(melody_input, work / "midi")
                    resolved_melody_source = melody_source or "basic_pitch_mix"
                    console.print(f"  MIDI: {midi_path.name}")

                midi_metrics = analyze_midi(midi_path, min_pitch=48)
                gate_metrics["midi"] = midi_metrics.to_dict()
                midi_errors = validate_midi_for_hum(midi_metrics, segment_duration_s)
                if midi_errors and not force:
                    return {
                        "status": "error",
                        "error": "Melody gate failed before neural hum",
                        "details": midi_errors,
                        "metrics": gate_metrics,
                        "hint": "Use --midi corrected.mid, --melody-audio mix, or import ACE/Suno hum via --source-hum",
                    }

                console.print("[bold cyan]Step 4/7:[/bold cyan] Rendering closed-mouth neural hum guide...")
                source_hum = render_neural_hum(vocals_path, midi_path, work / "source_hum.wav")
                resolved_melody_source = "neural_hum_local"
            elif renderer == "old_synth":
                melody_input = self._pick_melody_input(
                    segment, vocals_path, melody_audio, work, transcribe_to_midi,
                )
                console.print(f"  Melody input: {melody_input.name}")

                if manual_midi:
                    midi_path = Path(manual_midi)
                    resolved_melody_source = "manual_midi"
                else:
                    console.print("[bold cyan]Step 3/7:[/bold cyan] Transcribing melody (Basic Pitch)...")
                    midi_path = transcribe_to_midi(melody_input, work / "midi")
                    resolved_melody_source = melody_source or "basic_pitch"
                    console.print(f"  MIDI: {midi_path.name}")

                midi_metrics = analyze_midi(midi_path)
                gate_metrics["midi"] = midi_metrics.to_dict()
                midi_errors = validate_midi_for_hum(midi_metrics, segment_duration_s)
                if midi_errors and not force:
                    return {
                        "status": "error",
                        "error": "Melody gate failed before synth hum",
                        "details": midi_errors,
                        "metrics": gate_metrics,
                        "hint": "Use --midi corrected.mid, --melody-audio mix, or import ACE/Suno hum via --source-hum",
                    }

                console.print("[bold cyan]Step 4/7:[/bold cyan] Synthesizing oscillator guide hum (test renderer)...")
                source_hum = synthesize_hum(midi_path, work / "source_hum.wav")
            else:
                return {"status": "error", "error": f"Unknown source_hum_renderer: {renderer}"}

            hum_errors, hum_metrics = validate_source_hum_wav(source_hum)
            gate_metrics["source_hum"] = hum_metrics
            if hum_errors and not force:
                return {
                    "status": "error",
                    "error": "Source hum gate failed — guide must sound like a vocal performance",
                    "details": hum_errors,
                    "metrics": gate_metrics,
                }

            if diagnostic_only and not allow_diagnostic_cache:
                return {
                    "status": "error",
                    "error": "vocal_stem_diag is diagnostic-only and cannot be cached by default",
                    "hint": "Use --source-hum-renderer vocal_stem for vintage vocal sources, import an ACE/Suno/human guide with --source-hum, or pass --allow-diagnostic-cache to override.",
                }

            console.print("[bold cyan]Step 5/7:[/bold cyan] Generating Orpheus reference...")
            ref_path = self._ensure_orpheus_ref(work / "orpheus_ref.wav", orpheus_url=orpheus_url)

            console.print("[bold cyan]Step 6/7:[/bold cyan] Seed-VC conversion...")
            converted_path = convert_hum(
                source_hum,
                ref_path,
                work / "seedvc_out",
                seedvc_root=seedvc_dir,
                diffusion_steps=diffusion_steps,
                semi_tone_shift=semi_tone_shift,
            )
            console.print(f"  Converted: {converted_path.name}")

            console.print("[bold cyan]Step 7/7:[/bold cyan] Caching...")
            duration_s = self._get_duration(converted_path)

            track = HumTrack(
                id=track_id,
                title=title,
                artist=artist or "",
                source_url=source_url,
                source_video_id=video_id,
                bridge_attributes=bridges or [],
                mood=mood or [],
                persona_connection=persona_connection,
                duration_s=duration_s,
                pitch_shift=semi_tone_shift,
                f0_method="seedvc_f0",
                pipeline="orpheus_seedvc_v2",
                melody_source=resolved_melody_source,
                source_hum_renderer=renderer,
                diffusion_steps=diffusion_steps,
                created=datetime.now().isoformat(),
                forbidden=False,
            )

            cached_path = self.cache.add_track(track, converted_path)
            console.print(f"  Cached: {cached_path}")

        return {
            "status": "ok",
            "track_id": track_id,
            "audio_path": str(cached_path),
            "duration_s": duration_s,
            "pipeline": track.pipeline,
            "melody_source": track.melody_source,
            "source_hum_renderer": getattr(track, "source_hum_renderer", renderer),
            "gate_metrics": gate_metrics,
        }

    def train_voice(self, epochs: int = 200) -> dict:
        return {
            "status": "error",
            "error": (
                "RVC train is deprecated for /hum. "
                f"Train Orpheus voice via /tts-voice finish --speaker {self.persona}."
            ),
            "hint": "skills/tts-voice/run.sh finish --speaker {persona} --job-dir <job>".format(
                persona=self.persona
            ),
        }

    def _has_orpheus_voice(self) -> bool:
        lora = self.orpheus_checkpoint / "lora"
        receipt = self.orpheus_checkpoint / "inference_receipt.json"
        if lora.is_dir():
            return True
        if receipt.is_file():
            try:
                data = json.loads(receipt.read_text())
                return data.get("status") == "PASS"
            except json.JSONDecodeError:
                return False
        return False

    def _ensure_orpheus_ref(self, out_path: Path, *, orpheus_url: str | None) -> Path:
        from .orpheus_client import make_orpheus_ref
        from .orpheus_ref import build_multi_clip_ref

        cached_ref = self.cache.cache_dir / "orpheus_ref.wav"
        checkpoint_ref = ORPHEUS_CHECKPOINTS / f"{self.persona}_orpheus_lora" / "inference_smoke.wav"
        if os.environ.get("HUM_ORPHEUS_MULTI_CLIP", "0") == "1":
            multi = build_multi_clip_ref(
                self.cache.cache_dir / "orpheus_ref_multi_24k.wav",
                persona=self.persona,
            )
            if multi and multi.is_file():
                self._prepare_target_ref(multi, out_path)
                return out_path
        if checkpoint_ref.is_file():
            self._prepare_target_ref(checkpoint_ref, out_path)
            return out_path

        if cached_ref.is_file() and cached_ref.stat().st_size > 10_000:
            self._prepare_target_ref(cached_ref, out_path)
            return out_path

        make_orpheus_ref(out_path, speaker=self.persona, orpheus_url=orpheus_url)
        self.cache.ensure_dir()
        shutil.copy2(out_path, cached_ref)
        self._prepare_target_ref(out_path, out_path)
        return out_path

    def _prepare_target_ref(self, src: Path, dst: Path) -> None:
        """Resample persona target clip to 44.1kHz stereo for Seed-VC."""
        tmp = dst.with_name(dst.stem + "._prep.wav")
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(src),
                "-ac", "2", "-ar", "44100",
                str(tmp),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            shutil.move(str(tmp), str(dst))
        elif src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
        elif tmp.exists():
            tmp.unlink(missing_ok=True)

    def _trim_segment(self, src: Path, dst: Path, start: str, duration: str) -> Path:
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(src),
                "-ss", start,
                "-t", duration,
                "-ac", "2",
                "-ar", "44100",
                str(dst),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg trim failed: {(result.stderr or '')[-300:]}")
        return dst

    def _download_audio(self, url: str, out_dir: Path) -> Optional[tuple[Path, str]]:
        import sys as _sys

        _iy_dir = str(SKILLS_ROOT / "ingest-youtube")
        if _iy_dir not in _sys.path:
            _sys.path.insert(0, _iy_dir)

        from youtube_transcripts.downloader import download_audio, fetch_video_metadata

        video_id = _extract_video_id(url)
        audio_path, error = download_audio(video_id, out_dir)
        if error or audio_path is None:
            console.print(f"  [red]Download error:[/red] {error}")
            return None

        meta = fetch_video_metadata(video_id)
        title = meta.get("title") if meta else None
        return audio_path, title

    def _separate_vocals(self, audio_path: Path, out_dir: Path) -> Optional[Path]:
        stems_skill_dir = SKILLS_ROOT / "create-stems"
        stems_out = out_dir / "stems"

        stem_device = os.environ.get("HUM_DEMUCS_DEVICE", "cpu")
        result = subprocess.run(
            [
                "uv", "run", "python", "cli.py",
                "--mix", str(audio_path),
                "--out", str(stems_out),
                "--instrument", "vocals",
                "--device", stem_device,
            ],
            cwd=str(stems_skill_dir),
            capture_output=True,
            text=True,
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )

        if result.returncode != 0:
            console.print(f"  [red]Stem separation error:[/red] {result.stderr.strip()[:200]}")
            return None

        for vocals in stems_out.rglob("vocals.wav"):
            return vocals

        console.print("  [red]No vocals.wav found in stems output[/red]")
        return None

    def _pick_melody_input(
        self,
        segment: Path,
        vocals_path: Path,
        melody_audio: str,
        work: Path,
        transcribe_fn,
    ) -> Path:
        """Choose audio for Basic Pitch transcription."""
        choice = (melody_audio or "auto").lower()
        if choice == "mix":
            return segment
        if choice == "vocals":
            return vocals_path

        probe_dir = work / "melody_probe"
        probe_dir.mkdir(parents=True, exist_ok=True)
        try:
            midi_path = transcribe_fn(vocals_path, probe_dir)
            from .source_hum_gate import analyze_midi

            metrics = analyze_midi(midi_path)
            if metrics.note_count >= 12 and metrics.pitch_min >= 48:
                console.print("  [dim]auto: using vocal stem for melody[/dim]")
                return vocals_path
        except Exception:
            pass
        console.print("  [dim]auto: vocal melody weak — using full mix[/dim]")
        return segment


    def _get_duration(self, audio_path: Path) -> Optional[float]:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                str(audio_path),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return round(float(result.stdout.strip()), 1)
        return None
