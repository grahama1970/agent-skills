#!/usr/bin/env python3
"""Continuously transcribe the human and stream utterances to the walkthrough.

This is the voice input for the conversational walkthrough. It runs RealtimeSTT
continuous voice-activity detection and, for every utterance the human speaks:

  1. touches the stop flag -- so if Embry is talking she is cut off the moment
     the human starts speaking (barge-in), and
  2. prints ``HEARD: <transcript>`` to stdout so the walkthrough can use that
     utterance as the spoken command or followup question.

So the human interrupts Embry by simply speaking, and what they said becomes the
next turn -- a stop word just pauses her, anything else is asked (via /ask).

RealtimeSTT lives in the live-evidence venv (on the SSD, NOT the orphaned copy
on the 12TB disk). Launch with that interpreter:

    ~/.cache/live-evidence/venv/bin/python \
        scripts/barge_in_listener.py /tmp/debugger-embry-stop.flag

Prints BARGE-IN-LISTENING once warm. Ctrl-C to stop.

NOTE ON ECHO: the mic will also hear Embry's own voice. Use headphones (or a
directional mic) so only the human triggers the barge-in; otherwise her speech
can interrupt itself.
"""

from __future__ import annotations

import os
import sys
import wave
from pathlib import Path

STOP_WORDS = ("stop", "pause", "quiet", "enough", "hold on", "hold up", "wait", "shush")


def _load_wav_16k_f32(wav_path: Path):
    """Read a 16-bit PCM wav as float32 mono at 16kHz, normalized to [-1, 1].

    This is exactly the audio shape faster-whisper wants. Used by wav-feed mode
    so the barge-in transcription is exercised with the REAL RealtimeSTT recorder
    on REAL audio, deterministically and with no microphone.
    """
    import numpy as np
    from scipy.signal import resample
    with wave.open(str(wav_path), "rb") as w:
        rate, chans, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if width != 2:
        raise ValueError(f"expected 16-bit PCM wav, got sampwidth={width}")
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    if chans == 2:
        audio = audio.reshape(-1, 2).mean(axis=1)
    audio /= 32768.0
    if rate != 16000:
        audio = resample(audio, int(len(audio) * 16000 / rate))
    return audio.astype(np.float32)


def main() -> int:
    stop_flag = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/debugger-embry-stop.flag")

    # Deterministic wav-feed mode (for the voice eval): transcribe one utterance
    # from a file through the real recorder, then exit. Default is live mic. The
    # wav-existence check runs BEFORE importing RealtimeSTT so a missing input
    # fails closed fast, with no torch/CUDA dependency.
    wav = os.environ.get("DEBUGGER_STT_WAV", "").strip()
    if wav and not Path(wav).is_file():
        print(f"BARGE-IN-UNAVAILABLE wav not found: {wav}", file=sys.stderr)
        return 3

    try:
        from RealtimeSTT import AudioToTextRecorder
    except Exception as exc:  # pragma: no cover - environment dependent
        print(f"BARGE-IN-UNAVAILABLE RealtimeSTT import failed: {exc}", file=sys.stderr)
        return 3

    if wav:
        wav_path = Path(wav)
        audio = _load_wav_16k_f32(wav_path)
        recorder = AudioToTextRecorder(
            model="tiny.en", language="en", spinner=False,
            use_microphone=False, post_speech_silence_duration=0.5,
        )
        print("BARGE-IN-LISTENING", flush=True)
        # perform_final_transcription runs faster-whisper directly on the samples
        # (no VAD streaming), so it is deterministic and returns promptly.
        heard = (recorder.perform_final_transcription(audio_bytes=audio) or "").strip()
        recorder.shutdown()
        if not heard:
            print("BARGE-IN-NOTHING-HEARD", file=sys.stderr)
            return 4
        stop_flag.touch()
        print(f"HEARD: {heard}", flush=True)
        # A continuous listener supplies an utterance at every pause. When looping
        # (DEBUGGER_STT_WAV_LOOP), re-emit the transcript so a multi-stop
        # walkthrough gets one spoken command per stop; the parent kills us on exit.
        if os.environ.get("DEBUGGER_STT_WAV_LOOP", "").strip():
            import time
            interval = float(os.environ.get("DEBUGGER_STT_WAV_LOOP_INTERVAL", "2"))
            while True:
                time.sleep(interval)
                stop_flag.touch()
                print(f"HEARD: {heard}", flush=True)
        return 0

    recorder = AudioToTextRecorder(
        model="tiny.en",
        language="en",
        spinner=False,
        post_speech_silence_duration=0.5,
    )
    print("BARGE-IN-LISTENING", flush=True)
    try:
        while True:
            heard = (recorder.text() or "").strip()
            if not heard:
                continue
            # Any speech interrupts Embry immediately (barge-in), then the
            # utterance is handed to the walkthrough as the next turn.
            stop_flag.touch()
            print(f"HEARD: {heard}", flush=True)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
