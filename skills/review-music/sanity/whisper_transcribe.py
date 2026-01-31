#!/usr/bin/env python3
"""
Sanity script for Whisper audio transcription.

PURPOSE: Verify Whisper API works for lyrics/speech transcription
DOCUMENTATION: https://github.com/openai/whisper
LAST VERIFIED: 2026-01-30

Exit codes:
  0 = PASS
  1 = FAIL
  42 = CLARIFY (needs human)

NOTE: Uses faster-whisper (CTranslate2) for GPU acceleration.
      Falls back to openai-whisper if faster-whisper unavailable.
"""
import sys
from pathlib import Path

# Ensure fixtures exist
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
TEST_SPOKEN = FIXTURES_DIR / "test_spoken.wav"
TEST_AUDIO = FIXTURES_DIR / "test_audio.wav"


def check_dependencies():
    """Check if whisper is installed."""
    # Try faster-whisper first (preferred)
    try:
        from faster_whisper import WhisperModel
        print("Using: faster-whisper (CTranslate2, GPU-accelerated)")
        return "faster-whisper"
    except ImportError:
        pass

    # Fall back to openai-whisper
    try:
        import whisper
        print(f"Using: openai-whisper")
        return "openai-whisper"
    except ImportError:
        pass

    print("FAIL: No whisper implementation installed")
    print("Fix: pip install faster-whisper  # Recommended (GPU)")
    print("     or: pip install openai-whisper  # Fallback")
    return None


def ensure_test_audio():
    """Generate test audio if it doesn't exist."""
    if not TEST_SPOKEN.exists() or not TEST_AUDIO.exists():
        print(f"Generating test audio...")
        sys.path.insert(0, str(FIXTURES_DIR))
        from generate_test_audio import main as generate
        generate()

    if not TEST_SPOKEN.exists():
        print(f"FAIL: Could not create test audio at {TEST_SPOKEN}")
        return False
    return True


def test_faster_whisper(audio_path: Path):
    """Test transcription with faster-whisper."""
    from faster_whisper import WhisperModel

    print("Loading faster-whisper model (base)...")
    model = WhisperModel("base", device="auto", compute_type="auto")

    print(f"Transcribing: {audio_path}")
    segments, info = model.transcribe(
        str(audio_path),
        beam_size=5,
        language="en",
        word_timestamps=True,
    )

    # Collect results
    text_parts = []
    word_timestamps = []

    for segment in segments:
        text_parts.append(segment.text)
        if segment.words:
            for word in segment.words:
                word_timestamps.append({
                    "word": word.word,
                    "start": word.start,
                    "end": word.end,
                })

    full_text = " ".join(text_parts).strip()

    return {
        "text": full_text,
        "language": info.language,
        "language_probability": info.language_probability,
        "duration": info.duration,
        "word_timestamps": word_timestamps,
    }


def test_openai_whisper(audio_path: Path):
    """Test transcription with openai-whisper."""
    import whisper

    print("Loading openai-whisper model (base)...")
    model = whisper.load_model("base")

    print(f"Transcribing: {audio_path}")
    result = model.transcribe(
        str(audio_path),
        language="en",
        word_timestamps=True,
    )

    # Extract word timestamps
    word_timestamps = []
    for segment in result.get("segments", []):
        for word in segment.get("words", []):
            word_timestamps.append({
                "word": word["word"],
                "start": word["start"],
                "end": word["end"],
            })

    return {
        "text": result["text"].strip(),
        "language": result.get("language", "en"),
        "language_probability": 1.0,  # Not available in base whisper
        "duration": None,
        "word_timestamps": word_timestamps,
    }


def test_transcription(whisper_type: str):
    """Run transcription test with appropriate backend."""
    if whisper_type == "faster-whisper":
        result = test_faster_whisper(TEST_SPOKEN)
    else:
        result = test_openai_whisper(TEST_SPOKEN)

    print(f"\nTranscription result:")
    print(f"  Text: '{result['text'][:100]}...' ({len(result['text'])} chars)")
    print(f"  Language: {result['language']}")
    print(f"  Word timestamps: {len(result['word_timestamps'])} words")

    if result['word_timestamps']:
        print(f"  First 3 words: {result['word_timestamps'][:3]}")

    return result


def test_music_transcription(whisper_type: str):
    """Test transcription on music (should return minimal/no lyrics for instrumental)."""
    if whisper_type == "faster-whisper":
        result = test_faster_whisper(TEST_AUDIO)
    else:
        result = test_openai_whisper(TEST_AUDIO)

    print(f"\nMusic transcription (instrumental test):")
    print(f"  Text: '{result['text'][:100]}' ({len(result['text'])} chars)")

    # Instrumental should have minimal text (or just [Music])
    # This validates whisper handles music files without crashing
    return result


def main():
    print("=== Whisper Sanity Check ===\n")

    whisper_type = check_dependencies()
    if not whisper_type:
        return 1

    if not ensure_test_audio():
        return 1

    try:
        print("\n1. Speech Transcription")
        print("-" * 40)
        speech_result = test_transcription(whisper_type)
        print()

        print("2. Music Transcription (Instrumental)")
        print("-" * 40)
        music_result = test_music_transcription(whisper_type)
        print()

        print("=" * 40)
        print("PASS: Whisper transcription working")
        print(f"  - Backend: {whisper_type}")
        print(f"  - Speech text: {len(speech_result['text'])} chars")
        print(f"  - Word timestamps: {len(speech_result['word_timestamps'])}")
        print(f"  - Music handled: Yes (no crash)")
        return 0

    except Exception as e:
        print(f"\nFAIL: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
