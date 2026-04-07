#!/usr/bin/env python3
"""
CLI for review-music skill.

Commands:
- analyze: Full analysis pipeline (features + review)
- features: Extract specific audio features
- review: Generate HMT-mapped review
- batch: Process multiple files
"""
import typer
import json
import sys
from pathlib import Path
from typing import List, Optional

# Memory integration (graceful degradation)
_HAS_MEMORY_INTEGRATION = False
try:
    # memory_integration.py lives at review-music/ (one level up from src/)
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from memory_integration import recall_prior_analyses, learn_analysis
    _HAS_MEMORY_INTEGRATION = True
except ImportError:
    pass

app = typer.Typer(help="Audio feature extraction and HMT review generation")

# Default model for LLM routing (--model flag for `with <model>` routing)
_DEFAULT_MODEL = "deepseek-ai/DeepSeek-V3"


@app.command()
def analyze(
    source: str = typer.Argument(..., help="Audio file or YouTube URL"),
    title: Optional[str] = typer.Option(None, "-t", "--title", help="Track title"),
    artist: Optional[str] = typer.Option(None, "-a", "--artist", help="Artist name"),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="Output file"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Skip LLM analysis"),
    no_lyrics: bool = typer.Option(False, "--no-lyrics", help="Skip lyrics"),
    provider: str = typer.Option("anthropic", help="LLM provider"),
    model: str = typer.Option(_DEFAULT_MODEL, "--model", help="LLM model for routing"),
):
    """Full analysis pipeline."""
    from .features.aggregator import extract_all_features
    from .review.generator import generate_review, save_review

    # Pre-hook: Recall prior analyses for context
    if _HAS_MEMORY_INTEGRATION and (artist or title):
        prior = recall_prior_analyses(artist or title or "")
        if prior:
            print(f"[memory] Found prior analyses for {artist or title}")

    # Generate full review
    review = generate_review(
        source,
        title=title,
        artist=artist,
        use_llm=not no_llm,
        llm_provider=provider,
        include_lyrics=not no_lyrics,
    )

    # Post-hook: Learn analysis results to memory
    if _HAS_MEMORY_INTEGRATION:
        try:
            feat = getattr(review, "features", {})
            taxonomy = getattr(review, "bridge_attributes", [])
            learn_analysis(
                track_title=getattr(review, "title", title or ""),
                artist=getattr(review, "artist", artist or ""),
                bpm=feat.get("rhythm", {}).get("bpm"),
                key=feat.get("harmony", {}).get("key", feat.get("harmony", {}).get("scale", "")),
                features=feat,
                taxonomy_tags=taxonomy if isinstance(taxonomy, list) else [],
            )
        except Exception as e:
            print(f"[memory] Learn skipped: {e}", file=sys.stderr)

    if output:
        save_review(review, output)
        print(f"Review saved to: {output}")
    else:
        print(review.to_json())


@app.command()
def features(
    source: str = typer.Argument(..., help="Audio file or YouTube URL"),
    all: bool = typer.Option(False, "--all", help="Extract all features"),
    bpm: bool = typer.Option(False, "--bpm", help="Extract BPM"),
    key: bool = typer.Option(False, "--key", help="Extract key/mode"),
    chords: bool = typer.Option(False, "--chords", help="Extract chords"),
    timbre: bool = typer.Option(False, "--timbre", help="Extract timbre"),
    dynamics: bool = typer.Option(False, "--dynamics", help="Extract dynamics"),
    lyrics: bool = typer.Option(False, "--lyrics", help="Extract lyrics"),
    no_lyrics: bool = typer.Option(False, "--no-lyrics", help="Skip lyrics in --all"),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="Output file"),
):
    """Extract specific audio features."""
    from .features.aggregator import extract_all_features, extract_selected_features

    if all:
        feat = extract_all_features(
            source,
            include_lyrics=not no_lyrics,
        )
    else:
        feat = extract_selected_features(
            source,
            bpm=bpm,
            key=key,
            chords=chords,
            timbre=timbre,
            dynamics=dynamics,
            lyrics=lyrics,
        )

    if output:
        with open(output, "w") as f:
            json.dump(feat, f, indent=2, default=_json_serializer)
        print(f"Features saved to: {output}")
    else:
        print(json.dumps(feat, indent=2, default=_json_serializer))


@app.command()
def review(
    source: str = typer.Argument(..., help="Audio file or YouTube URL"),
    title: Optional[str] = typer.Option(None, "-t", "--title", help="Track title"),
    artist: Optional[str] = typer.Option(None, "-a", "--artist", help="Artist name"),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="Output file"),
    fmt: str = typer.Option("human", "-f", "--format", help="Output format (json, memory, human)"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Skip LLM analysis"),
    no_lyrics: bool = typer.Option(False, "--no-lyrics", help="Skip lyrics"),
    provider: str = typer.Option("anthropic", help="LLM provider"),
    sync_memory: bool = typer.Option(False, "--sync-memory", help="Sync to /memory"),
    model: str = typer.Option(_DEFAULT_MODEL, "--model", help="LLM model for routing"),
):
    """Generate HMT-mapped review."""
    from .review.generator import generate_review, save_review

    rev = generate_review(
        source,
        title=title,
        artist=artist,
        use_llm=not no_llm,
        llm_provider=provider,
        include_lyrics=not no_lyrics,
    )

    # Pre-hook: Recall prior analyses for context
    if _HAS_MEMORY_INTEGRATION and (artist or title):
        prior = recall_prior_analyses(artist or title or "")
        if prior:
            print(f"[memory] Found prior analyses for {artist or title}")

    # Output review
    if fmt == "json":
        out_text = rev.to_json()
    elif fmt == "memory":
        out_text = json.dumps(rev.to_memory_format(), indent=2)
    else:
        out_text = _format_human_readable(rev)

    if output:
        with open(output, "w") as f:
            f.write(out_text)
        print(f"Review saved to: {output}")
    else:
        print(out_text)

    # Post-hook: Learn analysis results to memory
    if _HAS_MEMORY_INTEGRATION:
        try:
            feat = getattr(rev, "features", {})
            taxonomy = getattr(rev, "bridge_attributes", [])
            learn_analysis(
                track_title=getattr(rev, "title", title or ""),
                artist=getattr(rev, "artist", artist or ""),
                bpm=feat.get("rhythm", {}).get("bpm"),
                key=feat.get("harmony", {}).get("key", feat.get("harmony", {}).get("scale", "")),
                features=feat,
                taxonomy_tags=taxonomy if isinstance(taxonomy, list) else [],
            )
        except Exception as e:
            print(f"[memory] Learn skipped: {e}", file=sys.stderr)

    # Sync to memory if requested (legacy path)
    if sync_memory:
        _sync_to_memory(rev)
        print(f"Synced to /memory: {rev.title}")


@app.command()
def batch(
    inputs: list[str] = typer.Argument(..., help="Files or directories"),
    output_dir: str = typer.Option("./reviews", "-o", "--output-dir", help="Output directory"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Skip LLM analysis"),
    no_lyrics: bool = typer.Option(False, "--no-lyrics", help="Skip lyrics"),
    provider: str = typer.Option("anthropic", help="LLM provider"),
    sync_memory: bool = typer.Option(False, "--sync-memory", help="Sync to /memory"),
):
    """Process multiple files."""
    from .review.generator import generate_review, save_review

    input_files = []

    # Collect files
    for inp in inputs:
        p = Path(inp)
        if p.is_dir():
            # Find audio files in directory
            for ext in ["*.mp3", "*.wav", "*.flac", "*.m4a", "*.ogg"]:
                input_files.extend(p.glob(ext))
        elif p.is_file():
            input_files.append(p)
        else:
            print(f"Warning: {inp} not found", file=sys.stderr)

    if not input_files:
        print("No audio files found", file=sys.stderr)
        raise typer.Exit(code=1)

    print(f"Processing {len(input_files)} files...")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    results = {"success": 0, "failed": 0, "reviews": []}

    for i, audio_file in enumerate(input_files, 1):
        print(f"[{i}/{len(input_files)}] {audio_file.name}...")

        try:
            rev = generate_review(
                audio_file,
                use_llm=not no_llm,
                llm_provider=provider,
                include_lyrics=not no_lyrics,
            )

            # Save individual review
            output_path = out_dir / f"{audio_file.stem}_review.json"
            save_review(rev, output_path)

            results["success"] += 1
            results["reviews"].append({
                "file": str(audio_file),
                "output": str(output_path),
                "bridges": rev.bridge_attributes,
            })

            if sync_memory:
                _sync_to_memory(rev)

        except Exception as e:
            print(f"  Error: {e}", file=sys.stderr)
            results["failed"] += 1

    # Save summary
    summary_path = out_dir / "_batch_summary.json"
    with open(summary_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nComplete: {results['success']} success, {results['failed']} failed")
    print(f"Summary: {summary_path}")


@app.command("help")
def help_cmd():
    """Show help."""
    print("""
review-music - Audio Feature Extraction and HMT Review Generation

Commands:
  analyze <file>     Full analysis (features + HMT review)
  features <file>    Extract audio features only
  review <file>      Generate HMT-mapped review
  batch <files...>   Process multiple files

Examples:
  ./run.sh analyze song.mp3
  ./run.sh features song.mp3 --bpm --key
  ./run.sh review song.mp3 --sync-memory
  ./run.sh batch ./music/*.mp3 -o ./reviews/

Options:
  --bpm          Extract BPM/tempo
  --key          Extract key/mode
  --chords       Extract chord features
  --timbre       Extract timbre features
  --dynamics     Extract dynamics
  --lyrics       Extract lyrics
  --no-llm       Skip LLM analysis (use rule-based)
  --no-lyrics    Skip lyrics transcription
  --sync-memory  Sync review to /memory skill
  --format       Output format (json, memory, human)
  -o, --output   Output file/directory
""")


def _json_serializer(obj):
    """Custom JSON serializer for numpy types."""
    import numpy as np
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.float32, np.float64)):
        return float(obj)
    if isinstance(obj, (np.int32, np.int64)):
        return int(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _format_human_readable(review) -> str:
    """Format review for human reading."""
    lines = [
        f"# {review.title}",
        f"Artist: {review.artist}" if review.artist else "",
        "",
        "## Summary",
        review.summary,
        "",
        "## HMT Taxonomy",
        f"Bridges: {', '.join(review.bridge_attributes)}",
        f"Domain: {', '.join(review.collection_tags.get('domain', []))}",
        f"Function: {review.collection_tags.get('function', 'N/A')}",
        f"Thematic: {review.collection_tags.get('thematic_weight', 'N/A')}",
        "",
        "## Emotional Arc",
        f"Mood: {review.emotional_arc.get('primary_mood', 'N/A')} ({review.emotional_arc.get('intensity', 'N/A')} intensity)",
        "",
        "## Use Cases",
    ]
    for uc in review.use_cases[:5]:
        lines.append(f"- {uc}")

    lines.extend([
        "",
        "## Audio Features",
        f"BPM: {review.features.get('rhythm', {}).get('bpm', 'N/A'):.0f}",
        f"Key: {review.features.get('harmony', {}).get('scale', 'N/A')}",
        f"Loudness: {review.features.get('dynamics', {}).get('loudness_integrated', 'N/A'):.1f} LUFS",
        "",
        f"Confidence: {review.confidence:.0%}",
        f"Analysis: {review.analysis_method}",
    ])

    return "\n".join(lines)


def _sync_to_memory(review):
    """Sync review to /memory skill."""
    # This would call the memory skill's learn command
    # For now, just save to a local file that can be synced later
    memory_dir = Path.home() / ".pi" / "memory" / "music"
    memory_dir.mkdir(parents=True, exist_ok=True)

    mem_format = review.to_memory_format()
    filename = f"{review.title.replace(' ', '_')[:50]}.json"

    with open(memory_dir / filename, "w") as f:
        json.dump(mem_format, f, indent=2)


def main():
    """Main CLI entry point."""
    app()


if __name__ == "__main__":
    app()
