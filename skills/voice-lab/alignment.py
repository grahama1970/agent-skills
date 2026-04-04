"""SRT-aligned audio segmentation and comparison.

Parse SRT files, segment audio by timestamps, and compute per-segment
similarity scores between Graham's recording and original vocals.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf
from loguru import logger
from rich.console import Console
from rich.table import Table

console = Console()


@dataclass
class SRTSegment:
    """A single SRT subtitle entry."""

    index: int
    start_ms: int
    end_ms: int
    text: str

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


@dataclass
class AlignedSegment:
    """A segment with alignment and quality data."""

    index: int
    start_ms: int
    end_ms: int
    text: str
    graham_segment: Optional[str] = None
    original_segment: Optional[str] = None
    similarity: float = 0.0
    quality: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "text": self.text,
            "graham_segment": self.graham_segment,
            "original_segment": self.original_segment,
            "similarity": round(self.similarity, 3),
            "quality": self.quality or {},
        }


def parse_srt(srt_path: Path) -> list[SRTSegment]:
    """Parse an SRT file into segments."""
    content = srt_path.read_text(encoding="utf-8", errors="replace")
    segments = []

    # Split on blank lines to get blocks
    blocks = re.split(r"\n\s*\n", content.strip())

    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue

        # First line: index
        try:
            index = int(lines[0].strip())
        except ValueError:
            continue

        # Second line: timestamps
        time_match = re.match(
            r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})",
            lines[1].strip(),
        )
        if not time_match:
            continue

        g = time_match.groups()
        start_ms = (
            int(g[0]) * 3600000 + int(g[1]) * 60000 + int(g[2]) * 1000 + int(g[3])
        )
        end_ms = (
            int(g[4]) * 3600000 + int(g[5]) * 60000 + int(g[6]) * 1000 + int(g[7])
        )

        # Remaining lines: text
        text = " ".join(lines[2:]).strip()

        segments.append(SRTSegment(
            index=index,
            start_ms=start_ms,
            end_ms=end_ms,
            text=text,
        ))

    return segments


def _ms_to_samples(ms: int, sr: int) -> int:
    """Convert milliseconds to sample index."""
    return int(ms * sr / 1000)


def segment_audio(
    audio_path: Path,
    segments: list[SRTSegment],
    output_dir: Path,
    prefix: str = "segment",
) -> list[Path]:
    """Segment an audio file by SRT timestamps.

    Returns list of output paths (one per segment).
    """
    audio, sr = sf.read(str(audio_path), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []

    for seg in segments:
        start_sample = _ms_to_samples(seg.start_ms, sr)
        end_sample = _ms_to_samples(seg.end_ms, sr)

        # Clamp to audio bounds
        start_sample = max(0, min(start_sample, len(audio)))
        end_sample = max(start_sample, min(end_sample, len(audio)))

        segment_audio = audio[start_sample:end_sample]
        if len(segment_audio) == 0:
            logger.warning(f"Empty segment {seg.index}: {seg.start_ms}-{seg.end_ms}ms")
            paths.append(None)
            continue

        out_path = output_dir / f"{prefix}_{seg.index:03d}.wav"
        sf.write(str(out_path), segment_audio, sr)
        paths.append(out_path)

    return paths


def _compute_similarity(audio_a: np.ndarray, audio_b: np.ndarray, sr: int) -> float:
    """Compute cosine similarity between two audio segments using MFCC."""
    from scipy import signal as sig
    from scipy.fft import dct
    from scipy.spatial.distance import cosine

    n_fft = 2048
    hop = 512
    n_mels = 40
    n_mfcc = 13

    def _mfcc(audio: np.ndarray) -> np.ndarray:
        # Guard against short audio: nperseg must be <= len(audio), noverlap < nperseg
        actual_nfft = min(n_fft, len(audio))
        actual_hop = min(hop, max(1, actual_nfft - 1))
        actual_noverlap = actual_nfft - actual_hop
        if actual_nfft < 4:
            return np.zeros((1, n_mfcc))
        _, _, Zxx = sig.stft(audio, fs=sr, nperseg=actual_nfft, noverlap=actual_noverlap)
        power = np.abs(Zxx) ** 2

        # Simple mel filterbank
        fmax = sr / 2.0
        mel_max = 2595.0 * np.log10(1.0 + fmax / 700.0)
        mel_points = np.linspace(0, mel_max, n_mels + 2)
        hz_points = 700.0 * (10.0 ** (mel_points / 2595.0) - 1.0)
        n_bins = actual_nfft // 2 + 1
        fft_freqs = np.linspace(0, fmax, n_bins)

        fb = np.zeros((n_mels, n_bins))
        for i in range(n_mels):
            lo, center, hi = hz_points[i], hz_points[i + 1], hz_points[i + 2]
            up = (fft_freqs - lo) / max(center - lo, 1e-10)
            down = (hi - fft_freqs) / max(hi - center, 1e-10)
            fb[i] = np.maximum(0, np.minimum(up, down))

        mel_spec = fb @ power
        log_mel = np.log(mel_spec + 1e-10)
        mfcc = dct(log_mel, type=2, axis=0, norm="ortho")[:n_mfcc]
        return mfcc.T  # (n_frames, n_mfcc)

    mfcc_a = _mfcc(audio_a)
    mfcc_b = _mfcc(audio_b)

    if len(mfcc_a) == 0 or len(mfcc_b) == 0:
        return 0.0

    mean_a = mfcc_a.mean(axis=0)
    mean_b = mfcc_b.mean(axis=0)

    sim = 1.0 - cosine(mean_a, mean_b)
    return float(np.clip(sim, 0.0, 1.0))


def _check_segment_quality(audio: np.ndarray, sr: int) -> dict:
    """Check basic quality metrics for a segment."""
    if len(audio) == 0:
        return {"noise": 1.0, "clipping": True, "duration_match": 0.0}

    rms = float(np.sqrt(np.mean(audio**2)))
    peak = float(np.max(np.abs(audio)))
    clipping = peak >= 0.99
    noise_floor = rms < 0.01  # Very quiet = possibly noise only

    return {
        "rms_db": round(20 * np.log10(rms + 1e-10), 1),
        "peak_db": round(20 * np.log10(peak + 1e-10), 1),
        "clipping": clipping,
        "too_quiet": noise_floor,
    }


def align_recordings(
    graham_path: Path,
    original_path: Path,
    srt_path: Path,
    output_dir: Path,
) -> list[AlignedSegment]:
    """Align Graham's recording against original vocals using SRT timestamps.

    Returns list of AlignedSegments with per-segment similarity and quality.
    """
    segments = parse_srt(srt_path)
    if not segments:
        logger.warning(f"No segments found in {srt_path}")
        return []

    # Filter out very short or very long segments (Horus Qwen3-TTS: 2-12s)
    valid_segments = [
        s for s in segments
        if 2000 <= s.duration_ms <= 12000
    ]
    if len(valid_segments) < len(segments):
        logger.info(
            f"Filtered {len(segments) - len(valid_segments)} segments "
            f"outside 2-12s range"
        )
    # Merge adjacent segments with gaps < 500ms
    merged = _merge_short_gaps(valid_segments)

    # Segment both recordings
    graham_segments_dir = output_dir / "segments" / "graham"
    original_segments_dir = output_dir / "segments" / "original"

    graham_paths = segment_audio(graham_path, merged, graham_segments_dir, "graham")
    original_paths = segment_audio(original_path, merged, original_segments_dir, "original")

    # Compare each segment
    results = []
    for i, seg in enumerate(merged):
        g_path = graham_paths[i] if i < len(graham_paths) else None
        o_path = original_paths[i] if i < len(original_paths) else None

        aligned = AlignedSegment(
            index=seg.index,
            start_ms=seg.start_ms,
            end_ms=seg.end_ms,
            text=seg.text,
        )

        if g_path and o_path and g_path.exists() and o_path.exists():
            g_audio, g_sr = sf.read(str(g_path), dtype="float32")
            o_audio, o_sr = sf.read(str(o_path), dtype="float32")

            if g_audio.ndim > 1:
                g_audio = g_audio.mean(axis=1)
            if o_audio.ndim > 1:
                o_audio = o_audio.mean(axis=1)

            # Compute similarity
            sr = min(g_sr, o_sr)
            aligned.similarity = _compute_similarity(g_audio, o_audio, sr)
            aligned.graham_segment = str(g_path)
            aligned.original_segment = str(o_path)

            # Quality check Graham's recording
            quality = _check_segment_quality(g_audio, g_sr)
            # Duration match
            if len(o_audio) > 0:
                quality["duration_match"] = round(
                    min(len(g_audio), len(o_audio)) / max(len(g_audio), len(o_audio)),
                    3,
                )
            aligned.quality = quality

        results.append(aligned)

    return results


def _merge_short_gaps(segments: list[SRTSegment]) -> list[SRTSegment]:
    """Merge adjacent segments when gap < 500ms."""
    if not segments:
        return []

    merged = [segments[0]]
    for seg in segments[1:]:
        prev = merged[-1]
        gap = seg.start_ms - prev.end_ms
        if gap < 500:
            # Merge: extend previous segment
            merged[-1] = SRTSegment(
                index=prev.index,
                start_ms=prev.start_ms,
                end_ms=seg.end_ms,
                text=f"{prev.text} {seg.text}",
            )
        else:
            merged.append(seg)

    return merged


def load_alignment(path: Path) -> list[AlignedSegment]:
    """Load alignment results from JSON."""
    data = json.loads(path.read_text())
    results = []
    for d in data:
        results.append(AlignedSegment(
            index=d["index"],
            start_ms=d["start_ms"],
            end_ms=d["end_ms"],
            text=d["text"],
            graham_segment=d.get("graham_segment"),
            original_segment=d.get("original_segment"),
            similarity=d.get("similarity", 0.0),
            quality=d.get("quality"),
        ))
    return results


def save_alignment(results: list[AlignedSegment], output_path: Path) -> None:
    """Save alignment results to JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = [r.to_dict() for r in results]
    output_path.write_text(json.dumps(data, indent=2))
    logger.info(f"Saved alignment: {output_path}")


def print_alignment(results: list[AlignedSegment]) -> None:
    """Display alignment results in a table."""
    if not results:
        console.print("[yellow]No alignment results[/yellow]")
        return

    table = Table(title="Alignment Results")
    table.add_column("#", justify="right", width=4)
    table.add_column("Time", width=13)
    table.add_column("Text", max_width=40)
    table.add_column("Similarity", justify="right")
    table.add_column("Quality", justify="center")

    for r in results:
        start_s = r.start_ms / 1000
        end_s = r.end_ms / 1000
        time_str = f"{start_s:.1f}-{end_s:.1f}s"

        sim_color = "green" if r.similarity >= 0.7 else "yellow" if r.similarity >= 0.5 else "red"
        sim_str = f"[{sim_color}]{r.similarity:.3f}[/{sim_color}]"

        quality_str = "[green]OK[/green]"
        if r.quality:
            if r.quality.get("clipping"):
                quality_str = "[red]CLIP[/red]"
            elif r.quality.get("too_quiet"):
                quality_str = "[yellow]QUIET[/yellow]"

        text_short = r.text[:40] + "..." if len(r.text) > 40 else r.text

        table.add_row(str(r.index), time_str, text_short, sim_str, quality_str)

    console.print(table)

    # Summary
    sims = [r.similarity for r in results if r.similarity > 0]
    if sims:
        avg_sim = sum(sims) / len(sims)
        console.print(f"\nAverage similarity: {avg_sim:.3f}")
        console.print(f"Segments: {len(results)} total, {len(sims)} scored")
