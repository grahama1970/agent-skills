"""Surface adapters for audio I/O across Discord, KDE PipeWire, and Horus WebRTC.

Each surface provides a consistent async interface for reading and writing
audio, abstracting transport-specific details (Opus encoding, PipeWire
routing, WebSocket framing).
"""

from __future__ import annotations

import asyncio
import struct
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

import numpy as np

from loguru import logger as log


class SurfaceAdapter(ABC):
    """Abstract audio I/O surface for conversation."""

    @staticmethod
    def create(name: str) -> SurfaceAdapter:
        adapters = {
            "discord": DiscordSurface,
            "kde": KDESurface,
            "horus": HorusSurface,
        }
        cls = adapters.get(name)
        if cls is None:
            raise ValueError(f"Unknown surface: {name!r} (available: {list(adapters)})")
        return cls()

    @abstractmethod
    @asynccontextmanager
    async def connect(self):
        """Context manager: connect to audio surface."""
        yield

    @abstractmethod
    async def read_audio(self) -> AsyncIterator[np.ndarray]:
        """Yield audio chunks from the surface (user's microphone)."""
        ...

    @abstractmethod
    async def write_audio(self, chunk: np.ndarray, sample_rate: int = 48000):
        """Write audio chunk to the surface (speaker output)."""
        ...

    @abstractmethod
    async def stop(self):
        """Clean shutdown."""
        ...


class DiscordSurface(SurfaceAdapter):
    """Opus 48kHz bidirectional audio via Discord voice channel.

    Uses discord_voice_client.py from horus overlay for Opus
    encoding/decoding and voice gateway connection.
    """

    def __init__(self):
        self._voice_client = None
        self._connected = False

    @asynccontextmanager
    async def connect(self):
        try:
            # Try loading Discord voice client from horus overlay
            import sys
            from pathlib import Path
            overlay_path = Path(__file__).resolve().parent.parent.parent.parent / "apps" / "kde-node" / "src"
            sys.path.insert(0, str(overlay_path))
            from discord_voice_client import DiscordVoiceClient
            self._voice_client = DiscordVoiceClient()
            await self._voice_client.connect()
            self._connected = True
            log.info("Connected to Discord voice")
            yield self
        except ImportError:
            log.warning("Discord voice client not available; using stub")
            self._connected = False
            yield self
        except Exception as e:
            log.error(f"Discord voice connection failed: {e}")
            self._connected = False
            yield self
        finally:
            await self.stop()

    async def read_audio(self) -> AsyncIterator[np.ndarray]:
        if not self._connected or not self._voice_client:
            return
        async for opus_frame in self._voice_client.receive():
            # Decode Opus to PCM
            pcm = self._voice_client.decode(opus_frame)
            yield np.frombuffer(pcm, dtype=np.int16)

    async def write_audio(self, chunk: np.ndarray, sample_rate: int = 48000):
        if not self._connected or not self._voice_client:
            return
        # Encode PCM to Opus and send
        pcm_bytes = chunk.astype(np.int16).tobytes()
        await self._voice_client.send(pcm_bytes)

    async def stop(self):
        if self._voice_client and self._connected:
            await self._voice_client.disconnect()
            self._connected = False


class KDESurface(SurfaceAdapter):
    """PipeWire local audio via pw-record/pw-play.

    Records from default microphone and plays to default speaker
    using PipeWire CLI tools. Suitable for KDE Plasma desktop.
    """

    SAMPLE_RATE = 48000
    CHANNELS = 1
    FRAME_SIZE = 960  # 20ms at 48kHz

    def __init__(self):
        self._record_proc: Optional[asyncio.subprocess.Process] = None
        self._play_proc: Optional[asyncio.subprocess.Process] = None

    @asynccontextmanager
    async def connect(self):
        try:
            # Start pw-record for continuous microphone capture
            self._record_proc = await asyncio.create_subprocess_exec(
                "pw-record", "--format", "s16", "--rate", str(self.SAMPLE_RATE),
                "--channels", str(self.CHANNELS), "-",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            # Start pw-play for continuous audio output
            self._play_proc = await asyncio.create_subprocess_exec(
                "pw-play", "--format", "s16", "--rate", str(self.SAMPLE_RATE),
                "--channels", str(self.CHANNELS), "-",
                stdin=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            log.info("Connected to KDE PipeWire audio")
            yield self
        except FileNotFoundError:
            log.error("PipeWire tools (pw-record/pw-play) not found")
            yield self
        except Exception as e:
            log.error(f"KDE PipeWire connection failed: {e}")
            yield self
        finally:
            await self.stop()

    async def read_audio(self) -> AsyncIterator[np.ndarray]:
        if not self._record_proc or not self._record_proc.stdout:
            return
        bytes_per_frame = self.FRAME_SIZE * 2  # 16-bit = 2 bytes per sample
        while True:
            try:
                raw = await self._record_proc.stdout.readexactly(bytes_per_frame)
                yield np.frombuffer(raw, dtype=np.int16)
            except asyncio.IncompleteReadError:
                break
            except Exception:
                break

    async def write_audio(self, chunk: np.ndarray, sample_rate: int = 48000):
        if not self._play_proc or not self._play_proc.stdin:
            return
        try:
            self._play_proc.stdin.write(chunk.astype(np.int16).tobytes())
            await self._play_proc.stdin.drain()
        except Exception as e:
            log.debug(f"PipeWire write error: {e}")

    async def stop(self):
        for proc in [self._record_proc, self._play_proc]:
            if proc:
                try:
                    proc.terminate()
                    await asyncio.wait_for(proc.wait(), timeout=2.0)
                except Exception:
                    proc.kill()
        self._record_proc = None
        self._play_proc = None


class HorusSurface(SurfaceAdapter):
    """WebSocket/WebRTC audio via Horus app.

    Connects to the Horus gateway's voice WebSocket endpoint
    for bidirectional audio streaming.
    """

    WS_URL = "ws://127.0.0.1:18789/voice"

    def __init__(self):
        self._ws = None
        self._connected = False

    @asynccontextmanager
    async def connect(self):
        try:
            import websockets
            self._ws = await websockets.connect(
                self.WS_URL,
                ping_interval=20,
                ping_timeout=10,
                max_size=2**20,
            )
            self._connected = True
            log.info(f"Connected to Horus voice gateway at {self.WS_URL}")
            yield self
        except ImportError:
            log.warning("websockets library not available for Horus surface")
            yield self
        except Exception as e:
            log.warning(f"Horus voice connection failed: {e}")
            yield self
        finally:
            await self.stop()

    async def read_audio(self) -> AsyncIterator[np.ndarray]:
        if not self._connected or not self._ws:
            return
        try:
            async for message in self._ws:
                if isinstance(message, bytes):
                    # Binary frames are raw PCM int16
                    yield np.frombuffer(message, dtype=np.int16)
        except Exception as e:
            log.debug(f"Horus read error: {e}")

    async def write_audio(self, chunk: np.ndarray, sample_rate: int = 48000):
        if not self._connected or not self._ws:
            return
        try:
            await self._ws.send(chunk.astype(np.int16).tobytes())
        except Exception as e:
            log.debug(f"Horus write error: {e}")

    async def stop(self):
        if self._ws:
            await self._ws.close()
            self._connected = False
