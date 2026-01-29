#!/usr/bin/env python3
"""
Sanity check for faster-whisper transcription.
Tests various scenarios to identify hanging issues.
"""

import subprocess
import sys
import time
from pathlib import Path


def validate_audio(path: Path) -> dict | None:
    """Validate audio file with ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", str(path)],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            import json
            return json.loads(result.stdout)
    except Exception as e:
        print(f"Validation error: {e}")
    return None


def test_short_transcription(model, audio_path: str, max_segments: int = 10):
    """Test transcription with limited segments."""
    print(f"\n[Test 1] Short transcription ({max_segments} segments)...")
    start = time.time()

    segments, info = model.transcribe(
        audio_path,
        language="en",
        beam_size=5,
        vad_filter=True,
    )

    print(f"  Duration: {info.duration:.0f}s ({info.duration/3600:.1f}h)")

    count = 0
    for seg in segments:
        count += 1
        if count <= 3:
            print(f"  [{seg.start:.1f}-{seg.end:.1f}] {seg.text[:60]}...")
        if count >= max_segments:
            break

    elapsed = time.time() - start
    print(f"  Processed {count} segments in {elapsed:.1f}s")
    return True


def test_full_transcription(model, audio_path: str, output_path: str):
    """Test full transcription with progress."""
    print(f"\n[Test 2] Full transcription with progress...")
    start = time.time()

    segments, info = model.transcribe(
        audio_path,
        language="en",
        beam_size=5,
        vad_filter=True,
    )

    duration = info.duration
    print(f"  Duration: {duration:.0f}s ({duration/3600:.1f}h)")

    count = 0
    last_report = 0
    with open(output_path, "w") as f:
        for seg in segments:
            f.write(f"{seg.text}\n")
            count += 1

            # Progress every 10%
            progress = (seg.end / duration) * 100 if duration > 0 else 0
            if progress - last_report >= 10:
                elapsed = time.time() - start
                speed = seg.end / elapsed if elapsed > 0 else 0
                print(f"  {progress:.0f}% ({count} segments, {speed:.1f}x realtime)")
                last_report = progress

    elapsed = time.time() - start
    speed = duration / elapsed if elapsed > 0 else 0
    print(f"  DONE: {count} segments in {elapsed:.1f}s ({speed:.1f}x realtime)")
    return True


def main():
    from faster_whisper import WhisperModel

    # Find a test file
    library = Path.home() / "clawd" / "library" / "books"
    test_files = list(library.glob("*/audio.m4b"))

    if not test_files:
        print("No audio files found")
        return 1

    # Use shortest file for testing
    test_file = None
    shortest_duration = float('inf')

    print("Scanning for shortest test file...")
    for f in test_files[:5]:  # Check first 5 files
        info = validate_audio(f)
        if info and "format" in info:
            duration = float(info["format"].get("duration", 999999))
            print(f"  {f.parent.name}: {duration/3600:.1f}h")
            if duration < shortest_duration:
                shortest_duration = duration
                test_file = f

    if not test_file:
        print("No valid audio file found")
        return 1

    print(f"\nUsing: {test_file.parent.name} ({shortest_duration/3600:.1f}h)")

    # Validate
    print("\n[Validation] Checking audio file...")
    info = validate_audio(test_file)
    if not info:
        print("  FAILED: Could not validate audio")
        return 1
    print("  OK: Audio file valid")

    # Load model
    print("\n[Model] Loading faster-whisper turbo model...")
    start = time.time()
    model = WhisperModel("turbo", device="cuda", compute_type="float16")
    print(f"  Loaded in {time.time()-start:.1f}s")

    # Run tests
    try:
        test_short_transcription(model, str(test_file), max_segments=20)
        test_full_transcription(model, str(test_file), "/tmp/sanity_transcript.txt")
        print("\n[SUCCESS] All tests passed!")
        return 0
    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Test cancelled")
        return 1
    except Exception as e:
        print(f"\n[FAILED] Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
