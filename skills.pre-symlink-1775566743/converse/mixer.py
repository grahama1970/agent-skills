"""Audio stream mixer with volume ducking.

Combines multiple named audio channels (speech, humming, background)
into a single output stream with per-channel volume control and
fade-based ducking.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from loguru import logger as log


@dataclass
class MixChannel:
    """A named audio channel in the mixer."""
    name: str
    volume: float = 1.0  # 0.0-1.0
    target_volume: float = 1.0
    fade_rate: float = 0.005  # volume change per sample at 48kHz
    buffer: Optional[np.ndarray] = None  # current audio chunk
    active: bool = False

    def write(self, audio: np.ndarray):
        self.buffer = audio
        self.active = True

    def clear(self):
        self.buffer = None
        self.active = False


# Ducking presets: who ducks when
DUCK_RULES = {
    "speech": {
        # When speech is active, duck these channels
        "humming": 0.0,
        "background": 0.10,
    },
    "humming": {
        "background": 0.30,
    },
    "barge_in": {
        # User speaking: duck everything
        "speech": 0.0,
        "humming": 0.0,
        "background": 0.0,
    },
}


class AudioMixer:
    """Mix multiple audio streams with ducking rules.

    Channels:
        speech    — PersonaPlex TTS output (highest priority)
        humming   — Persona idle humming / backchannels
        background — Ambient / background music
    """

    def __init__(self, sample_rate: int = 48000):
        self.sample_rate = sample_rate
        self.channels: dict[str, MixChannel] = {}
        self._duck_state: Optional[str] = None

    def add_channel(self, name: str, volume: float = 1.0) -> MixChannel:
        """Register a named audio channel."""
        ch = MixChannel(name=name, volume=volume, target_volume=volume)
        self.channels[name] = ch
        return ch

    def write(self, channel: str, audio: np.ndarray):
        """Write audio data to a channel."""
        if channel not in self.channels:
            self.add_channel(channel)
        self.channels[channel].write(audio)

    def clear(self, channel: str):
        """Clear a channel's buffer."""
        if channel in self.channels:
            self.channels[channel].clear()

    def duck(self, trigger: str, fade_ms: float = 200.0):
        """Apply ducking rules for a trigger event.

        Args:
            trigger: Event name from DUCK_RULES (speech, humming, barge_in)
            fade_ms: Fade duration in milliseconds
        """
        rules = DUCK_RULES.get(trigger, {})
        fade_rate = 1.0 / max(1, (self.sample_rate * fade_ms / 1000))
        self._duck_state = trigger

        for ch_name, target_vol in rules.items():
            if ch_name in self.channels:
                self.channels[ch_name].target_volume = target_vol
                self.channels[ch_name].fade_rate = fade_rate
                log.debug(f"Duck {ch_name} → {target_vol:.2f} (trigger={trigger})")

    def unduck(self, fade_ms: float = 300.0):
        """Restore all channels to their default volume."""
        fade_rate = 1.0 / max(1, (self.sample_rate * fade_ms / 1000))
        self._duck_state = None

        for ch in self.channels.values():
            ch.target_volume = 1.0
            ch.fade_rate = fade_rate

    def mix(self, num_samples: int) -> np.ndarray:
        """Mix all active channels into a single output buffer.

        Applies per-sample volume fading for smooth ducking transitions.
        """
        output = np.zeros(num_samples, dtype=np.float64)

        for ch in self.channels.values():
            if not ch.active or ch.buffer is None:
                continue

            # Get chunk from buffer (pad/trim to num_samples)
            chunk = ch.buffer[:num_samples].astype(np.float64)
            if len(chunk) < num_samples:
                chunk = np.pad(chunk, (0, num_samples - len(chunk)))

            # Apply per-sample volume fade
            for i in range(num_samples):
                if ch.volume < ch.target_volume:
                    ch.volume = min(ch.target_volume, ch.volume + ch.fade_rate)
                elif ch.volume > ch.target_volume:
                    ch.volume = max(ch.target_volume, ch.volume - ch.fade_rate)
                chunk[i] *= ch.volume

            output += chunk

            # Consume buffer
            if ch.buffer is not None and len(ch.buffer) > num_samples:
                ch.buffer = ch.buffer[num_samples:]
            else:
                ch.clear()

        # Clip to int16 range
        output = np.clip(output, -32768, 32767).astype(np.int16)
        return output

    def mix_fast(self, num_samples: int) -> np.ndarray:
        """Optimized mix without per-sample fading (block-level volume)."""
        output = np.zeros(num_samples, dtype=np.float64)

        for ch in self.channels.values():
            if not ch.active or ch.buffer is None:
                continue

            chunk = ch.buffer[:num_samples].astype(np.float64)
            if len(chunk) < num_samples:
                chunk = np.pad(chunk, (0, num_samples - len(chunk)))

            # Block-level volume (step toward target)
            step = (ch.target_volume - ch.volume) * 0.3
            ch.volume += step
            output += chunk * ch.volume

            if ch.buffer is not None and len(ch.buffer) > num_samples:
                ch.buffer = ch.buffer[num_samples:]
            else:
                ch.clear()

        return np.clip(output, -32768, 32767).astype(np.int16)

    @property
    def any_active(self) -> bool:
        return any(ch.active for ch in self.channels.values())

    def status(self) -> dict:
        return {
            "duck_state": self._duck_state,
            "channels": {
                name: {
                    "active": ch.active,
                    "volume": round(ch.volume, 3),
                    "target": round(ch.target_volume, 3),
                }
                for name, ch in self.channels.items()
            },
        }
