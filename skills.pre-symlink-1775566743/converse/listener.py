"""VAD + Whisper STT listener with barge-in detection.

Continuously processes audio from a surface adapter, detects speech
activity via WebRTC VAD, accumulates frames, and transcribes via
Whisper on end-of-turn silence.
"""

from __future__ import annotations

import asyncio
import struct
import subprocess
import tempfile
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Callable, Optional

import numpy as np

from loguru import logger as log

# VAD configuration
VAD_FRAME_MS = 30  # 30ms frames for WebRTC VAD
VAD_SAMPLE_RATE = 16000  # VAD operates at 16kHz
VAD_FRAME_SAMPLES = int(VAD_SAMPLE_RATE * VAD_FRAME_MS / 1000)

# Speech detection thresholds
SPEECH_START_FRAMES = 3  # consecutive speech frames to start
SPEECH_END_SILENCE_MS = 800  # silence ms to end utterance
BARGE_IN_MS = 300  # speech during playback to trigger barge-in

# Whisper configuration
WHISPER_MODEL = "large-v3"
WHISPER_LANGUAGE = "en"


@dataclass
class TranscriptionResult:
    """Result from Whisper transcription."""
    text: str
    language: str
    duration_ms: int
    audio: np.ndarray  # raw audio that was transcribed
    timestamp: float


class VADProcessor:
    """WebRTC VAD wrapper for speech activity detection.

    Falls back to energy-based detection if webrtcvad unavailable.
    """

    def __init__(self, aggressiveness: int = 2, sample_rate: int = VAD_SAMPLE_RATE):
        self.sample_rate = sample_rate
        self.aggressiveness = aggressiveness
        self._vad = None
        self._use_energy_fallback = False

        try:
            import webrtcvad
            self._vad = webrtcvad.Vad(aggressiveness)
        except ImportError:
            log.warning("webrtcvad not available, using energy-based VAD fallback")
            self._use_energy_fallback = True

    def is_speech(self, frame: bytes) -> bool:
        """Check if audio frame contains speech."""
        if self._use_energy_fallback:
            return self._energy_detect(frame)
        try:
            return self._vad.is_speech(frame, self.sample_rate)
        except Exception:
            return self._energy_detect(frame)

    def _energy_detect(self, frame: bytes, threshold: float = 500.0) -> bool:
        """Simple energy-based speech detection fallback."""
        if len(frame) < 2:
            return False
        samples = np.frombuffer(frame, dtype=np.int16)
        rms = np.sqrt(np.mean(samples.astype(np.float64) ** 2))
        return rms > threshold


class WhisperTranscriber:
    """Whisper STT via faster-whisper or CLI fallback."""

    def __init__(self, model: str = WHISPER_MODEL, language: str = WHISPER_LANGUAGE):
        self.model_name = model
        self.language = language
        self._model = None
        self._use_cli = False
        self._init_model()

    def _init_model(self):
        try:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                self.model_name,
                device="cuda",
                compute_type="float16",
            )
            log.info(f"Loaded faster-whisper model: {self.model_name}")
        except Exception as e:
            log.warning(f"faster-whisper unavailable ({e}), will use CLI fallback")
            self._use_cli = True

    def transcribe(self, audio: np.ndarray, sample_rate: int = VAD_SAMPLE_RATE) -> str:
        """Transcribe audio array to text."""
        if self._use_cli:
            return self._transcribe_cli(audio, sample_rate)
        return self._transcribe_native(audio)

    def _transcribe_native(self, audio: np.ndarray) -> str:
        audio_float = audio.astype(np.float32) / 32768.0
        segments, _ = self._model.transcribe(
            audio_float,
            language=self.language,
            beam_size=5,
            vad_filter=True,
        )
        return " ".join(seg.text.strip() for seg in segments).strip()

    def _transcribe_cli(self, audio: np.ndarray, sample_rate: int) -> str:
        """Fallback: write WAV to temp file, invoke whisper CLI."""
        import wave
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name
            with wave.open(f, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(audio.tobytes())

        try:
            result = subprocess.run(
                ["whisper", tmp_path, "--model", self.model_name,
                 "--language", self.language, "--output_format", "txt"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                txt_path = Path(tmp_path).with_suffix(".txt")
                if txt_path.exists():
                    text = txt_path.read_text().strip()
                    txt_path.unlink(missing_ok=True)
                    return text
            log.error(f"Whisper CLI failed: {result.stderr[:200]}")
            return ""
        except Exception as e:
            log.error(f"Whisper CLI error: {e}")
            return ""
        finally:
            Path(tmp_path).unlink(missing_ok=True)


class Listener:
    """Continuous audio listener with VAD-based speech detection and Whisper STT.

    Callbacks:
        on_speech(result: TranscriptionResult) — called when speech is transcribed
        on_barge_in() — called when user speaks during persona playback
    """

    def __init__(
        self,
        on_speech: Callable[[TranscriptionResult], None],
        on_barge_in: Callable[[], None],
        vad_aggressiveness: int = 2,
        whisper_model: str = WHISPER_MODEL,
    ):
        self.on_speech = on_speech
        self.on_barge_in = on_barge_in
        self.vad = VADProcessor(aggressiveness=vad_aggressiveness)
        self.transcriber = WhisperTranscriber(model=whisper_model)

        # State
        self._speech_frames: list[bytes] = []
        self._consecutive_speech = 0
        self._consecutive_silence = 0
        self._in_speech = False
        self._speech_start_time = 0.0
        self._is_playing = False  # set externally: persona is speaking

        # Ring buffer for pre-speech audio (captures onset)
        self._pre_buffer: deque[bytes] = deque(maxlen=5)

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    @is_playing.setter
    def is_playing(self, value: bool):
        self._is_playing = value

    async def listen(self, audio_stream: AsyncIterator[np.ndarray]):
        """Main listen loop. Processes audio frames from surface adapter."""
        async for chunk in audio_stream:
            # Resample to 16kHz mono int16 if needed
            frame_bytes = self._prepare_frame(chunk)
            if frame_bytes is None:
                continue

            is_speech = self.vad.is_speech(frame_bytes)

            if is_speech:
                self._consecutive_speech += 1
                self._consecutive_silence = 0

                # Barge-in: user speaks while persona is playing
                if self._is_playing and self._consecutive_speech >= (BARGE_IN_MS // VAD_FRAME_MS):
                    log.info("Barge-in detected")
                    self.on_barge_in()
                    self._is_playing = False

                if not self._in_speech and self._consecutive_speech >= SPEECH_START_FRAMES:
                    self._in_speech = True
                    self._speech_start_time = time.time()
                    # Include pre-buffer for speech onset
                    self._speech_frames = list(self._pre_buffer)
                    log.debug("Speech started")

                if self._in_speech:
                    self._speech_frames.append(frame_bytes)
            else:
                self._consecutive_silence += 1
                self._consecutive_speech = 0
                self._pre_buffer.append(frame_bytes)

                if self._in_speech:
                    self._speech_frames.append(frame_bytes)
                    silence_ms = self._consecutive_silence * VAD_FRAME_MS
                    if silence_ms >= SPEECH_END_SILENCE_MS:
                        await self._end_of_turn()

    async def _end_of_turn(self):
        """End of speech turn: transcribe accumulated audio."""
        if not self._speech_frames:
            self._reset()
            return

        # Combine frames into single array
        raw = b"".join(self._speech_frames)
        audio = np.frombuffer(raw, dtype=np.int16)
        duration_ms = int(len(audio) / VAD_SAMPLE_RATE * 1000)

        # Skip very short utterances (< 200ms, likely noise)
        if duration_ms < 200:
            self._reset()
            return

        log.info(f"Transcribing {duration_ms}ms of speech")
        # Run transcription in thread pool to avoid blocking event loop
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, self.transcriber.transcribe, audio)

        if text:
            result = TranscriptionResult(
                text=text,
                language=WHISPER_LANGUAGE,
                duration_ms=duration_ms,
                audio=audio,
                timestamp=time.time(),
            )
            self.on_speech(result)
        else:
            log.debug("Transcription returned empty text")

        self._reset()

    def _reset(self):
        self._speech_frames.clear()
        self._consecutive_speech = 0
        self._consecutive_silence = 0
        self._in_speech = False

    def _prepare_frame(self, chunk: np.ndarray) -> Optional[bytes]:
        """Convert audio chunk to 16kHz mono int16 bytes for VAD."""
        if chunk.size == 0:
            return None
        # Ensure int16
        if chunk.dtype == np.float32 or chunk.dtype == np.float64:
            chunk = (chunk * 32767).astype(np.int16)
        elif chunk.dtype != np.int16:
            chunk = chunk.astype(np.int16)
        # Mono downmix if stereo
        if chunk.ndim > 1:
            chunk = chunk.mean(axis=1).astype(np.int16)
        # Pad/trim to VAD frame size
        if len(chunk) < VAD_FRAME_SAMPLES:
            chunk = np.pad(chunk, (0, VAD_FRAME_SAMPLES - len(chunk)))
        elif len(chunk) > VAD_FRAME_SAMPLES:
            chunk = chunk[:VAD_FRAME_SAMPLES]
        return chunk.tobytes()

    async def test(self, duration: float = 3.0):
        """Test: record from default mic for duration seconds, transcribe."""
        log.info(f"Recording {duration}s from default microphone...")
        try:
            proc = await asyncio.create_subprocess_exec(
                "pw-record", "--format", "s16", "--rate", str(VAD_SAMPLE_RATE),
                "--channels", "1", "-", "--timeout", str(int(duration)),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            raw, _ = await proc.communicate()
            audio = np.frombuffer(raw, dtype=np.int16)
            log.info(f"Recorded {len(audio)} samples, transcribing...")
            text = self.transcriber.transcribe(audio)
            log.info(f"Transcription: {text}")
            return text
        except FileNotFoundError:
            log.error("pw-record not found. Install pipewire-utils.")
            return ""
