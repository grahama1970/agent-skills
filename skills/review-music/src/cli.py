#!/usr/bin/env python3
"""
CLI for review-music skill.

Commands:
- analyze: Full analysis pipeline (features + review)
- features: Extract specific audio features
- review: Generate HMT-mapped review
- batch: Process multiple files
"""
import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional


def cmd_analyze(args):
    """Full analysis pipeline."""
    from .features.aggregator import extract_all_features
    from .review.generator import generate_review, save_review

    source = args.source

    # Generate full review
    review = generate_review(
        source,
        title=args.title,
        artist=args.artist,
        use_llm=not args.no_llm,
        llm_provider=args.provider,
        include_lyrics=not args.no_lyrics,
    )

    if args.output:
        save_review(review, args.output)
        print(f"Review saved to: {args.output}")
    else:
        print(review.to_json())


def cmd_features(args):
    """Extract specific audio features."""
    from .features.aggregator import extract_all_features, extract_selected_features

    source = args.source

    if args.all:
        features = extract_all_features(
            source,
            include_lyrics=not args.no_lyrics,
        )
    else:
        features = extract_selected_features(
            source,
            bpm=args.bpm,
            key=args.key,
            chords=args.chords,
            timbre=args.timbre,
            dynamics=args.dynamics,
            lyrics=args.lyrics,
        )

    if args.output:
        with open(args.output, "w") as f:
            json.dump(features, f, indent=2, default=_json_serializer)
        print(f"Features saved to: {args.output}")
    else:
        print(json.dumps(features, indent=2, default=_json_serializer))


def cmd_review(args):
    """Generate HMT-mapped review."""
    from .review.generator import generate_review, save_review

    source = args.source

    review = generate_review(
        source,
        title=args.title,
        artist=args.artist,
        use_llm=not args.no_llm,
        llm_provider=args.provider,
        include_lyrics=not args.no_lyrics,
    )

    # Output review
    if args.format == "json":
        output = review.to_json()
    elif args.format == "memory":
        output = json.dumps(review.to_memory_format(), indent=2)
    else:
        output = _format_human_readable(review)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"Review saved to: {args.output}")
    else:
        print(output)

    # Sync to memory if requested
    if args.sync_memory:
        _sync_to_memory(review)
        print(f"Synced to /memory: {review.title}")


def cmd_batch(args):
    """Process multiple files."""
    from .review.generator import generate_review, save_review

    input_files = []

    # Collect files
    for path in args.inputs:
        p = Path(path)
        if p.is_dir():
            # Find audio files in directory
            for ext in ["*.mp3", "*.wav", "*.flac", "*.m4a", "*.ogg"]:
                input_files.extend(p.glob(ext))
        elif p.is_file():
            input_files.append(p)
        else:
            print(f"Warning: {path} not found", file=sys.stderr)

    if not input_files:
        print("No audio files found", file=sys.stderr)
        return 1

    print(f"Processing {len(input_files)} files...")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = {"success": 0, "failed": 0, "reviews": []}

    for i, audio_file in enumerate(input_files, 1):
        print(f"[{i}/{len(input_files)}] {audio_file.name}...")

        try:
            review = generate_review(
                audio_file,
                use_llm=not args.no_llm,
                llm_provider=args.provider,
                include_lyrics=not args.no_lyrics,
            )

            # Save individual review
            output_path = output_dir / f"{audio_file.stem}_review.json"
            save_review(review, output_path)

            results["success"] += 1
            results["reviews"].append({
                "file": str(audio_file),
                "output": str(output_path),
                "bridges": review.bridge_attributes,
            })

            if args.sync_memory:
                _sync_to_memory(review)

        except Exception as e:
            print(f"  Error: {e}", file=sys.stderr)
            results["failed"] += 1

    # Save summary
    summary_path = output_dir / "_batch_summary.json"
    with open(summary_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nComplete: {results['success']} success, {results['failed']} failed")
    print(f"Summary: {summary_path}")


def cmd_help(args):
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
    parser = argparse.ArgumentParser(
        description="Audio feature extraction and HMT review generation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # analyze command
    p_analyze = subparsers.add_parser("analyze", help="Full analysis pipeline")
    p_analyze.add_argument("source", help="Audio file or YouTube URL")
    p_analyze.add_argument("--title", "-t", help="Track title")
    p_analyze.add_argument("--artist", "-a", help="Artist name")
    p_analyze.add_argument("--output", "-o", help="Output file")
    p_analyze.add_argument("--no-llm", action="store_true", help="Skip LLM analysis")
    p_analyze.add_argument("--no-lyrics", action="store_true", help="Skip lyrics")
    p_analyze.add_argument("--provider", default="anthropic", help="LLM provider")
    p_analyze.set_defaults(func=cmd_analyze)

    # features command
    p_features = subparsers.add_parser("features", help="Extract audio features")
    p_features.add_argument("source", help="Audio file or YouTube URL")
    p_features.add_argument("--all", action="store_true", help="Extract all features")
    p_features.add_argument("--bpm", action="store_true", help="Extract BPM")
    p_features.add_argument("--key", action="store_true", help="Extract key/mode")
    p_features.add_argument("--chords", action="store_true", help="Extract chords")
    p_features.add_argument("--timbre", action="store_true", help="Extract timbre")
    p_features.add_argument("--dynamics", action="store_true", help="Extract dynamics")
    p_features.add_argument("--lyrics", action="store_true", help="Extract lyrics")
    p_features.add_argument("--no-lyrics", action="store_true", help="Skip lyrics in --all")
    p_features.add_argument("--output", "-o", help="Output file")
    p_features.set_defaults(func=cmd_features)

    # review command
    p_review = subparsers.add_parser("review", help="Generate HMT review")
    p_review.add_argument("source", help="Audio file or YouTube URL")
    p_review.add_argument("--title", "-t", help="Track title")
    p_review.add_argument("--artist", "-a", help="Artist name")
    p_review.add_argument("--output", "-o", help="Output file")
    p_review.add_argument("--format", "-f", choices=["json", "memory", "human"],
                          default="human", help="Output format")
    p_review.add_argument("--no-llm", action="store_true", help="Skip LLM analysis")
    p_review.add_argument("--no-lyrics", action="store_true", help="Skip lyrics")
    p_review.add_argument("--provider", default="anthropic", help="LLM provider")
    p_review.add_argument("--sync-memory", action="store_true", help="Sync to /memory")
    p_review.set_defaults(func=cmd_review)

    # batch command
    p_batch = subparsers.add_parser("batch", help="Process multiple files")
    p_batch.add_argument("inputs", nargs="+", help="Files or directories")
    p_batch.add_argument("--output-dir", "-o", default="./reviews", help="Output directory")
    p_batch.add_argument("--no-llm", action="store_true", help="Skip LLM analysis")
    p_batch.add_argument("--no-lyrics", action="store_true", help="Skip lyrics")
    p_batch.add_argument("--provider", default="anthropic", help="LLM provider")
    p_batch.add_argument("--sync-memory", action="store_true", help="Sync to /memory")
    p_batch.set_defaults(func=cmd_batch)

    # help command
    p_help = subparsers.add_parser("help", help="Show help")
    p_help.set_defaults(func=cmd_help)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main() or 0)
