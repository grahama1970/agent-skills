#!/usr/bin/env python3
"""
Generate test audio fixtures for review-music sanity scripts.

Creates simple audio files with known characteristics for testing:
- test_audio.wav: 10 seconds, 120 BPM sine wave beats with melody
- test_spoken.wav: 10 seconds with a simple speech-like tone pattern
"""
import numpy as np
from scipy.io import wavfile
from pathlib import Path

SAMPLE_RATE = 44100
DURATION = 10  # seconds


def generate_beat_audio(bpm: int = 120) -> np.ndarray:
    """Generate audio with clear beat at specified BPM."""
    samples = int(SAMPLE_RATE * DURATION)
    t = np.linspace(0, DURATION, samples)

    # Beat timing
    beat_interval = 60.0 / bpm

    # Create kick drum sounds at each beat
    audio = np.zeros(samples)
    for beat_time in np.arange(0, DURATION, beat_interval):
        beat_sample = int(beat_time * SAMPLE_RATE)
        if beat_sample < samples:
            # Short sine burst for kick
            kick_duration = 0.1
            kick_samples = int(kick_duration * SAMPLE_RATE)
            kick_t = np.linspace(0, kick_duration, kick_samples)
            kick = np.sin(2 * np.pi * 60 * kick_t) * np.exp(-kick_t * 20)
            end_sample = min(beat_sample + kick_samples, samples)
            audio[beat_sample:end_sample] += kick[:end_sample - beat_sample]

    # Add melody in C major (C4 = 261.63 Hz)
    melody_notes = [261.63, 293.66, 329.63, 349.23, 392.00, 349.23, 329.63, 293.66]  # C D E F G F E D
    note_duration = DURATION / len(melody_notes)
    for i, freq in enumerate(melody_notes):
        start = int(i * note_duration * SAMPLE_RATE)
        end = int((i + 1) * note_duration * SAMPLE_RATE)
        note_t = np.linspace(0, note_duration, end - start)
        envelope = np.exp(-note_t * 2) * 0.3
        audio[start:end] += np.sin(2 * np.pi * freq * note_t) * envelope

    # Normalize
    audio = audio / np.max(np.abs(audio)) * 0.8
    return (audio * 32767).astype(np.int16)


def generate_speech_like_audio() -> np.ndarray:
    """Generate audio with speech-like frequency patterns."""
    samples = int(SAMPLE_RATE * DURATION)
    t = np.linspace(0, DURATION, samples)

    # Speech fundamentals typically 100-300 Hz with formants
    fundamental = 150

    # Create vowel-like sounds with formants
    audio = np.zeros(samples)

    # Formant frequencies for vowels
    formants = [
        (730, 1090, 2440),  # 'a'
        (270, 2290, 3010),  # 'i'
        (300, 870, 2240),   # 'u'
    ]

    # Create alternating vowel-like sounds
    segment_duration = DURATION / 6
    for i in range(6):
        start = int(i * segment_duration * SAMPLE_RATE)
        end = int((i + 1) * segment_duration * SAMPLE_RATE)
        seg_t = np.linspace(0, segment_duration, end - start)

        formant = formants[i % 3]
        envelope = np.sin(np.pi * seg_t / segment_duration) * 0.5

        segment = np.sin(2 * np.pi * fundamental * seg_t)
        for f in formant:
            segment += 0.3 * np.sin(2 * np.pi * f * seg_t)

        audio[start:end] = segment * envelope

    # Normalize
    audio = audio / np.max(np.abs(audio)) * 0.8
    return (audio * 32767).astype(np.int16)


def main():
    fixtures_dir = Path(__file__).parent

    # Generate beat audio (120 BPM, C major melody)
    beat_audio = generate_beat_audio(bpm=120)
    wavfile.write(fixtures_dir / "test_audio.wav", SAMPLE_RATE, beat_audio)
    print(f"Created: test_audio.wav (120 BPM, C major, {DURATION}s)")

    # Generate speech-like audio
    speech_audio = generate_speech_like_audio()
    wavfile.write(fixtures_dir / "test_spoken.wav", SAMPLE_RATE, speech_audio)
    print(f"Created: test_spoken.wav (speech-like, {DURATION}s)")


if __name__ == "__main__":
    main()
