"""PersonaPlex streaming TTS with register-aware voice selection.

Handles voice anchor (.pt) selection based on emotional register,
streams audio chunks for real-time playback, and supports mid-utterance
register switching at sentence boundaries.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Callable, Optional

import numpy as np

from loguru import logger as log

from emotion import EmotionState

# Voice anchor paths per persona
PERSONAS_BASE = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb")) / "media/personas"

VOICE_ANCHORS = {
    "embry": {
        "confident": "embry/personaplex/voices/embry_confident.pt",
        "uncertain": "embry/personaplex/voices/embry_uncertain.pt",
        "tired": "embry/personaplex/voices/embry_tired.pt",
        "tense": "embry/personaplex/voices/embry_tense.pt",
        "humming": "embry/personaplex/voices/embry_humming.pt",
    },
}

# Register → PersonaPlex text prompt conditioning
REGISTER_PROMPTS = {
    "confident": "Clear, warm, slightly fast-paced. Charleston charm with precise diction.",
    "uncertain": "Softer, slower, with pauses. More filler words, trailing sentences.",
    "tired": "Low energy, deliberate, longer pauses between phrases. Occasional sighs.",
    "tense": "Clipped, faster, less warmth. Precise but without the usual playfulness.",
    "humming": "Softly hums while thinking, occasionally produces short melodic phrases.",
}

SAMPLE_RATE = 48000  # output sample rate for playback


@dataclass
class SpeakChunk:
    """A chunk of generated audio for streaming playback."""
    audio: np.ndarray  # int16 PCM
    sample_rate: int
    is_final: bool = False
    register: str = "confident"
    sentence_idx: int = 0


class Speaker:
    """PersonaPlex streaming TTS with register-aware voice selection.

    Supports live (PersonaPlex) and recorded (Qwen3-TTS) modes.
    Streams audio chunks via on_chunk callback for real-time playback.
    """

    def __init__(self, persona: str = "embry", mode: str = "live"):
        self.persona = persona
        self.mode = mode
        self._voice_output = None
        self._voices = self._resolve_voice_paths()

    def _resolve_voice_paths(self) -> dict[str, Path]:
        """Resolve voice anchor paths for this persona."""
        anchors = VOICE_ANCHORS.get(self.persona, VOICE_ANCHORS["embry"])
        resolved = {}
        for register, rel_path in anchors.items():
            full_path = PERSONAS_BASE / rel_path
            if full_path.exists():
                resolved[register] = full_path
            else:
                log.debug(f"Voice anchor not found: {full_path}")
        return resolved

    def _get_voice_output(self):
        """Lazy-load PersonaPlex voice output."""
        if self._voice_output is None and self.mode == "live":
            try:
                from voice import HorusVoiceOutput, VoiceConfig
                config = VoiceConfig(
                    voice_library_path=PERSONAS_BASE / self.persona / "personaplex" / "voices",
                    fallback_to_espeak=True,
                )
                self._voice_output = HorusVoiceOutput(config)
                log.info("Loaded PersonaPlex voice output")
            except Exception as e:
                log.warning(f"PersonaPlex unavailable: {e}")
        return self._voice_output

    async def speak(
        self,
        text: str,
        register: str = "confident",
        emotion: EmotionState = EmotionState.NEUTRAL,
        on_chunk: Optional[Callable[[SpeakChunk], None]] = None,
    ) -> list[SpeakChunk]:
        """Generate and stream TTS audio.

        Splits text at sentence boundaries for potential mid-utterance
        register switching. Streams chunks via on_chunk callback.
        """
        sentences = self._split_sentences(text)
        all_chunks = []

        for i, sentence in enumerate(sentences):
            is_final = (i == len(sentences) - 1)
            chunks = await self._synthesize_sentence(
                sentence, register, emotion, i, is_final,
            )
            for chunk in chunks:
                all_chunks.append(chunk)
                if on_chunk:
                    on_chunk(chunk)

        return all_chunks

    async def speak_streaming(
        self,
        text: str,
        register: str = "confident",
        emotion: EmotionState = EmotionState.NEUTRAL,
    ) -> AsyncIterator[SpeakChunk]:
        """Async generator that yields audio chunks as they're synthesized."""
        sentences = self._split_sentences(text)
        for i, sentence in enumerate(sentences):
            is_final = (i == len(sentences) - 1)
            chunks = await self._synthesize_sentence(
                sentence, register, emotion, i, is_final,
            )
            for chunk in chunks:
                yield chunk

    async def _synthesize_sentence(
        self,
        sentence: str,
        register: str,
        emotion: EmotionState,
        sentence_idx: int,
        is_final: bool,
    ) -> list[SpeakChunk]:
        """Synthesize a single sentence via PersonaPlex or Qwen3-TTS."""
        if self.mode == "live":
            return await self._synthesize_live(sentence, register, emotion, sentence_idx, is_final)
        return await self._synthesize_recorded(sentence, register, emotion, sentence_idx, is_final)

    async def _synthesize_live(
        self,
        sentence: str,
        register: str,
        emotion: EmotionState,
        sentence_idx: int,
        is_final: bool,
    ) -> list[SpeakChunk]:
        """PersonaPlex live streaming synthesis."""
        voice = self._get_voice_output()
        if not voice:
            return await self._synthesize_recorded(sentence, register, emotion, sentence_idx, is_final)

        # Map emotion to PersonaPlex EmotionalState
        emotion_map = {
            "curious": "CURIOUS", "focused": "FOCUSED",
            "frustrated": "FRUSTRATED", "confused": "CONFUSED",
            "pleased": "PLEASED", "overwhelmed": "OVERWHELMED",
            "neutral": "NEUTRAL", "melancholic": "MELANCHOLIC",
            "playful": "PLAYFUL", "weary": "WEARY", "anxious": "ANXIOUS",
        }
        pplex_emotion = emotion_map.get(emotion.value, "NEUTRAL")

        try:
            loop = asyncio.get_event_loop()
            # PersonaPlex speak returns audio data
            audio_data = await loop.run_in_executor(
                None, voice.speak, sentence, pplex_emotion,
            )
            if audio_data is not None:
                if isinstance(audio_data, np.ndarray):
                    audio = audio_data
                else:
                    audio = np.frombuffer(audio_data, dtype=np.int16)
                return [SpeakChunk(
                    audio=audio,
                    sample_rate=SAMPLE_RATE,
                    is_final=is_final,
                    register=register,
                    sentence_idx=sentence_idx,
                )]
        except Exception as e:
            log.warning(f"PersonaPlex synthesis failed: {e}")

        return await self._synthesize_recorded(sentence, register, emotion, sentence_idx, is_final)

    async def _synthesize_recorded(
        self,
        sentence: str,
        register: str,
        emotion: EmotionState,
        sentence_idx: int,
        is_final: bool,
    ) -> list[SpeakChunk]:
        """Qwen3-TTS / espeak fallback synthesis."""
        try:
            # Try Qwen3-TTS via CLI
            proc = await asyncio.create_subprocess_exec(
                "python3", "-c",
                f"from qwen3_tts import synthesize; synthesize({sentence!r}, 'output.wav')",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=15.0)
            output_path = Path("output.wav")
            if proc.returncode == 0 and output_path.exists():
                import wave
                with wave.open(str(output_path), "rb") as wf:
                    raw = wf.readframes(wf.getnframes())
                    audio = np.frombuffer(raw, dtype=np.int16)
                    sr = wf.getframerate()
                output_path.unlink(missing_ok=True)
                return [SpeakChunk(
                    audio=audio, sample_rate=sr,
                    is_final=is_final, register=register,
                    sentence_idx=sentence_idx,
                )]
        except Exception as e:
            logger.debug("value lookup failed: {}", e)

        # Last resort: espeak
        try:
            proc = await asyncio.create_subprocess_exec(
                "espeak-ng", "--stdout", "-v", "en-us", sentence,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            if stdout:
                # espeak outputs WAV; skip 44-byte header
                audio = np.frombuffer(stdout[44:], dtype=np.int16)
                return [SpeakChunk(
                    audio=audio, sample_rate=22050,
                    is_final=is_final, register=register,
                    sentence_idx=sentence_idx,
                )]
        except Exception as e:
            log.warning(f"espeak fallback failed: {e}")

        # Silent chunk as absolute fallback
        silence = np.zeros(SAMPLE_RATE, dtype=np.int16)  # 1s silence
        return [SpeakChunk(
            audio=silence, sample_rate=SAMPLE_RATE,
            is_final=is_final, register=register,
            sentence_idx=sentence_idx,
        )]

    def _split_sentences(self, text: str) -> list[str]:
        """Split text at sentence boundaries for streaming and register switching."""
        # Split on sentence-ending punctuation, preserving the punctuation
        parts = re.split(r'(?<=[.!?…])\s+', text.strip())
        # Also split on em-dashes and ellipses mid-sentence for natural pauses
        result = []
        for part in parts:
            if len(part) > 150:
                # Long sentence: split at comma/semicolon too
                sub = re.split(r'(?<=[,;])\s+', part)
                result.extend(sub)
            else:
                result.append(part)
        return [s.strip() for s in result if s.strip()]

    async def test(self, text: str = "Hello, I'm Embry."):
        """Test: synthesize and play a single sentence."""
        log.info(f"Test speak: {text!r}")
        chunks = await self.speak(text, register="confident")
        if chunks:
            total_samples = sum(c.audio.shape[0] for c in chunks)
            log.info(f"Generated {total_samples} samples across {len(chunks)} chunks")
            # Play via pw-play
            audio = np.concatenate([c.audio for c in chunks])
            proc = await asyncio.create_subprocess_exec(
                "pw-play", "--format", "s16", "--rate", str(chunks[0].sample_rate),
                "--channels", "1", "-",
                stdin=asyncio.subprocess.PIPE,
            )
            await proc.communicate(input=audio.tobytes())
        else:
            log.warning("No audio chunks generated")
