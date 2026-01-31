"""
Lyrics Transcription using faster-whisper.

Extracts: Lyrics text, language, word timestamps.
"""
from pathlib import Path
from typing import Dict, List, Optional, Union
import tempfile

import numpy as np
from scipy.io import wavfile


def extract_lyrics(
    source: Union[str, Path, np.ndarray],
    sr: int = 44100,
    language: str = "en",
    model_size: str = "base",
) -> Dict:
    """
    Extract lyrics from audio using Whisper.

    Args:
        source: File path or numpy audio array
        sr: Sample rate (only needed if source is numpy array)
        language: Language code (e.g., "en", "es", "de")
        model_size: Whisper model size ("tiny", "base", "small", "medium", "large")

    Returns:
        Dictionary with:
        - text: Full transcribed text
        - language: Detected language
        - language_probability: Confidence in language detection
        - word_timestamps: List of {word, start, end} dicts
        - is_instrumental: True if likely instrumental (no lyrics)
        - segments: List of segment dicts with text and timing
    """
    try:
        from faster_whisper import WhisperModel

        # Load model
        model = WhisperModel(model_size, device="auto", compute_type="auto")

        # Handle numpy array input
        if isinstance(source, np.ndarray):
            # Write to temporary file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                temp_path = f.name
                # Ensure audio is in correct format
                audio_int16 = (source * 32767).astype(np.int16)
                wavfile.write(temp_path, sr, audio_int16)
                source = temp_path

        # Transcribe
        segments, info = model.transcribe(
            str(source),
            beam_size=5,
            language=language if language != "auto" else None,
            word_timestamps=True,
            vad_filter=True,  # Voice activity detection
        )

        # Collect results
        text_parts = []
        word_timestamps = []
        segment_list = []

        for segment in segments:
            text_parts.append(segment.text)
            segment_list.append({
                "text": segment.text,
                "start": segment.start,
                "end": segment.end,
            })

            if segment.words:
                for word in segment.words:
                    word_timestamps.append({
                        "word": word.word,
                        "start": word.start,
                        "end": word.end,
                    })

        full_text = " ".join(text_parts).strip()

        # Determine if instrumental (no or very few words)
        is_instrumental = len(word_timestamps) < 5 or len(full_text) < 20

        return {
            "text": full_text,
            "language": info.language,
            "language_probability": info.language_probability,
            "duration": info.duration,
            "word_timestamps": word_timestamps,
            "segments": segment_list,
            "is_instrumental": is_instrumental,
        }

    except ImportError:
        # Fall back to openai-whisper if faster-whisper not available
        return _extract_lyrics_openai(source, language, model_size)


def _extract_lyrics_openai(
    source: Union[str, Path],
    language: str = "en",
    model_size: str = "base",
) -> Dict:
    """Fallback to openai-whisper."""
    import whisper

    model = whisper.load_model(model_size)

    result = model.transcribe(
        str(source),
        language=language if language != "auto" else None,
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

    full_text = result["text"].strip()
    is_instrumental = len(word_timestamps) < 5 or len(full_text) < 20

    return {
        "text": full_text,
        "language": result.get("language", language),
        "language_probability": 1.0,
        "duration": None,
        "word_timestamps": word_timestamps,
        "segments": result.get("segments", []),
        "is_instrumental": is_instrumental,
    }


def analyze_lyrics_content(lyrics_text: str) -> Dict:
    """
    Analyze lyrics content for themes and characteristics.

    This is a simple keyword-based analysis. For deeper analysis,
    use an LLM.
    """
    text_lower = lyrics_text.lower()

    # Theme keywords
    theme_keywords = {
        "love": ["love", "heart", "kiss", "romance", "together", "forever"],
        "loss": ["lost", "gone", "miss", "cry", "tears", "goodbye"],
        "anger": ["hate", "angry", "rage", "fight", "destroy", "burn"],
        "hope": ["hope", "dream", "believe", "tomorrow", "future", "light"],
        "darkness": ["dark", "night", "shadow", "death", "pain", "suffer"],
        "nature": ["sun", "moon", "stars", "rain", "wind", "sea", "mountain"],
        "rebellion": ["fight", "free", "revolution", "break", "rise", "stand"],
    }

    # Count theme matches
    theme_scores = {}
    for theme, keywords in theme_keywords.items():
        count = sum(1 for kw in keywords if kw in text_lower)
        if count > 0:
            theme_scores[theme] = count

    # Sort themes by score
    top_themes = sorted(theme_scores.keys(), key=lambda t: theme_scores[t], reverse=True)[:3]

    # Estimate emotional tone
    positive_words = ["love", "hope", "joy", "happy", "light", "dream", "peace"]
    negative_words = ["hate", "pain", "dark", "death", "cry", "lost", "fear"]

    positive_count = sum(1 for w in positive_words if w in text_lower)
    negative_count = sum(1 for w in negative_words if w in text_lower)

    if positive_count > negative_count:
        emotional_tone = "positive"
    elif negative_count > positive_count:
        emotional_tone = "negative"
    else:
        emotional_tone = "neutral"

    return {
        "themes": top_themes,
        "theme_scores": theme_scores,
        "emotional_tone": emotional_tone,
        "word_count": len(lyrics_text.split()),
    }
