"""PySide6 QObject bridge for voice-lab GUI.

Exposes D-Bus state, mic level monitoring, TTS A/B synthesis,
persona switching, and particle data to QML.
D-Bus runs in a background thread with its own asyncio loop.
"""
from __future__ import annotations

import asyncio
import json
import struct
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Optional

import httpx
import numpy as np
from loguru import logger
from PySide6.QtCore import (
    QMetaObject,
    QObject,
    QTimer,
    Qt,
    Property,
    Signal,
    Slot,
    Q_ARG,
)

from particles import (
    STATE_CONFIGS,
    STATE_RING_CONFIGS,
    STATE_COLORS,
    RING_EMERGE_MS,
    COLOR_TRANSITION_MS,
    sample_particles,
    load_stars,
    load_ring,
    load_font,
)


# ── D-Bus Thread ──────────────────────────────────────────────


class _DbusListener:
    """Runs dbus-fast in a background thread, marshals signals to Qt."""

    def __init__(self, bridge: "VoiceLabGuiBridge"):
        self._bridge = bridge
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name="dbus-listener")
        self._thread.start()

    def _run(self):
        try:
            asyncio.run(self._async_run())
        except Exception as e:
            logger.warning(f"D-Bus listener exited: {e}")

    async def _async_run(self):
        try:
            from dbus_fast.aio import MessageBus
            from dbus_fast import BusType
        except ImportError:
            logger.warning("dbus-fast not installed, D-Bus signals unavailable")
            return

        self._loop = asyncio.get_event_loop()
        try:
            bus = await MessageBus(bus_type=BusType.SESSION).connect()
        except Exception as e:
            logger.warning(f"Cannot connect to session bus: {e}")
            return

        # Subscribe to EmbryStateChanged
        await bus.call(
            bus.make_method_call(
                "org.freedesktop.DBus",
                "/org/freedesktop/DBus",
                "org.freedesktop.DBus",
                "AddMatch",
                "s",
                [
                    "type='signal',"
                    "interface='org.embry.State',"
                    "member='EmbryStateChanged'"
                ],
            )
        )

        # Subscribe to PersonaChanged
        await bus.call(
            bus.make_method_call(
                "org.freedesktop.DBus",
                "/org/freedesktop/DBus",
                "org.freedesktop.DBus",
                "AddMatch",
                "s",
                [
                    "type='signal',"
                    "interface='org.embry.State',"
                    "member='PersonaChanged'"
                ],
            )
        )

        def on_message(msg):
            if msg.member == "EmbryStateChanged" and msg.body:
                state = msg.body[0] if msg.body else "idle"
                QMetaObject.invokeMethod(
                    self._bridge,
                    "_onDbusStateChanged",
                    Qt.QueuedConnection,
                    Q_ARG(str, state),
                )
            elif msg.member == "PersonaChanged" and msg.body:
                persona = msg.body[0] if msg.body else ""
                QMetaObject.invokeMethod(
                    self._bridge,
                    "_onDbusPersonaChanged",
                    Qt.QueuedConnection,
                    Q_ARG(str, persona),
                )

        bus.on_message(on_message)

        # Keep alive
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
        finally:
            bus.disconnect()


# ── Audio Peak Computation ────────────────────────────────────


def compute_peaks(audio_path: Path, num_bins: int = 200) -> list[float]:
    """Compute interleaved [min, max] peaks from a WAV file."""
    import soundfile as sf

    data, _sr = sf.read(str(audio_path), dtype="float32")
    if data.ndim > 1:
        data = data[:, 0]

    samples_per_bin = max(1, len(data) // num_bins)
    peaks = []
    for i in range(num_bins):
        start = i * samples_per_bin
        end = min(start + samples_per_bin, len(data))
        if start >= len(data):
            peaks.extend([0.0, 0.0])
        else:
            chunk = data[start:end]
            peaks.append(float(np.min(chunk)))
            peaks.append(float(np.max(chunk)))
    return peaks


# ── Main Bridge ───────────────────────────────────────────────


class VoiceLabGuiBridge(QObject):
    """Bridge between QML GUI and system services."""

    # Signals for QML
    embryStateChanged = Signal()
    personaChanged = Signal()
    micLevelChanged = Signal()
    personaListChanged = Signal()

    # TTS signals
    ttsAReady = Signal()
    ttsBReady = Signal()
    ttsPeaksAChanged = Signal()
    ttsPeaksBChanged = Signal()
    ttsBusyChanged = Signal()

    # Particle data signal
    particleDataReady = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # State
        self._embry_state = "idle"
        self._persona = "embry"
        self._persona_list: list[str] = ["embry", "graham", "brandon"]
        self._mic_level = 0.0

        # TTS state
        self._tts_text = ""
        self._tts_peaks_a: list[float] = []
        self._tts_peaks_b: list[float] = []
        self._tts_busy = False
        self._tts_path_a: str = ""
        self._tts_path_b: str = ""

        # Playback
        self._play_proc: subprocess.Popen | None = None

        # Mic monitoring
        self._mic_monitor_proc: subprocess.Popen | None = None
        self._mic_monitor_thread: threading.Thread | None = None

        # Particle data (loaded lazily, sent to QML as JSON)
        self._particle_json = ""
        self._stars_json = ""
        self._ring_json = ""
        self._font_json = ""

        # D-Bus listener
        self._dbus = _DbusListener(self)

        # Tab registry (loaded from JSON file next to QML)
        self._tab_registry_json = ""
        try:
            registry_path = Path(__file__).parent / "qml" / "tab-registry.json"
            if registry_path.exists():
                self._tab_registry_json = registry_path.read_text()
        except Exception as e:
            logger.warning(f"Failed to load tab-registry.json: {e}")

        # State config JSON for QML Canvas2D
        self._state_configs_json = json.dumps(
            {k: {
                "radiusMul": v.radiusMul, "charge": v.charge,
                "breathHz": v.breathHz, "breathAmp": v.breathAmp,
                "sparkEvery": v.sparkEvery, "dualRing": v.dualRing,
                "pulseOut": v.pulseOut, "orbitSpeed": v.orbitSpeed,
                "converge": v.converge,
            } for k, v in STATE_CONFIGS.items()}
        )
        self._ring_configs_json = json.dumps(
            {k: ({
                "width": v.width, "alpha": v.alpha,
                "dashPattern": v.dashPattern,
                "pulseHz": v.pulseHz, "pulseAmp": v.pulseAmp,
                "rippleCount": v.rippleCount, "rotateSpeed": v.rotateSpeed,
            } if v else None) for k, v in STATE_RING_CONFIGS.items()}
        )
        self._state_colors_json = json.dumps(
            {k: {
                "particle": list(v.particle), "glow": list(v.glow),
                "glowAlpha": v.glowAlpha,
            } for k, v in STATE_COLORS.items()}
        )

    # ── Lifecycle ─────────────────────────────────────────────

    @Slot()
    def initialize(self):
        """Call from QML Component.onCompleted to start services."""
        self._load_particle_data()
        self._dbus.start()
        self._start_mic_monitor()

    @Slot()
    def shutdown(self):
        """Clean up resources."""
        self._stop_mic_monitor()
        self._stop_playback()

    # ── Particle Data ─────────────────────────────────────────

    def _load_particle_data(self):
        try:
            particles = sample_particles(256)
            stars = load_stars()
            ring = load_ring()
            font = load_font()
            self._particle_json = json.dumps(particles)
            self._stars_json = json.dumps(stars)
            self._ring_json = json.dumps(ring)
            self._font_json = json.dumps(font)
            self.particleDataReady.emit()
        except Exception as e:
            logger.error(f"Failed to load particle data: {e}")

    @Property(str, notify=particleDataReady)
    def particleDataJson(self):
        return self._particle_json

    @Property(str, notify=particleDataReady)
    def starsJson(self):
        return self._stars_json

    @Property(str, notify=particleDataReady)
    def ringJson(self):
        return self._ring_json

    @Property(str, notify=particleDataReady)
    def fontJson(self):
        return self._font_json

    @Property(str, constant=True)
    def stateConfigsJson(self):
        return self._state_configs_json

    @Property(str, constant=True)
    def ringConfigsJson(self):
        return self._ring_configs_json

    @Property(str, constant=True)
    def stateColorsJson(self):
        return self._state_colors_json

    @Property(str, constant=True)
    def tabRegistryJson(self):
        return self._tab_registry_json

    # ── Embry State ───────────────────────────────────────────

    @Property(str, notify=embryStateChanged)
    def embryState(self):
        return self._embry_state

    @embryState.setter
    def embryState(self, value: str):
        if self._embry_state != value:
            self._embry_state = value
            self.embryStateChanged.emit()

    @Slot(str)
    def _onDbusStateChanged(self, state: str):
        self.embryState = state

    @Slot(str)
    def setEmbryState(self, state: str):
        """Manual state override from QML (for testing)."""
        self.embryState = state

    # ── Persona ───────────────────────────────────────────────

    @Property(str, notify=personaChanged)
    def persona(self):
        return self._persona

    @persona.setter
    def persona(self, value: str):
        if self._persona != value:
            self._persona = value
            self.personaChanged.emit()

    @Property("QVariantList", notify=personaListChanged)
    def personaList(self):
        return self._persona_list

    @Slot(str)
    def _onDbusPersonaChanged(self, persona: str):
        self.persona = persona

    @Slot(str)
    def setPersona(self, name: str):
        """Switch active persona — calls D-Bus SetActivePersona."""
        self.persona = name
        # Fire-and-forget D-Bus call in background
        threading.Thread(
            target=self._call_set_persona, args=(name,), daemon=True
        ).start()

    def _call_set_persona(self, name: str):
        try:
            subprocess.run(
                ["busctl", "--user", "call", "org.embry.State",
                 "/org/embry/State", "org.embry.State",
                 "SetActivePersona", "s", name],
                capture_output=True, timeout=5,
            )
        except Exception as e:
            logger.warning(f"SetActivePersona failed: {e}")

    # ── Mic Level ─────────────────────────────────────────────

    @Property(float, notify=micLevelChanged)
    def micLevel(self):
        return self._mic_level

    def _start_mic_monitor(self):
        self._mic_monitor_thread = threading.Thread(
            target=self._mic_monitor_loop, daemon=True, name="mic-monitor"
        )
        self._mic_monitor_thread.start()

    def _stop_mic_monitor(self):
        if self._mic_monitor_proc:
            self._mic_monitor_proc.terminate()
            self._mic_monitor_proc = None

    def _mic_monitor_loop(self):
        """Read raw s16le from pw-record, compute RMS, emit micLevel."""
        try:
            self._mic_monitor_proc = subprocess.Popen(
                ["pw-record", "--rate", "48000", "--channels", "1",
                 "--format", "s16", "-"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            logger.warning("pw-record not found, mic monitor disabled")
            return

        chunk_size = 3200  # 1600 samples @ 48kHz = ~33ms
        while self._mic_monitor_proc and self._mic_monitor_proc.poll() is None:
            try:
                data = self._mic_monitor_proc.stdout.read(chunk_size)
                if not data:
                    break
                n_samples = len(data) // 2
                if n_samples == 0:
                    continue
                samples = struct.unpack(f"<{n_samples}h", data[:n_samples * 2])
                rms = (sum(s * s for s in samples) / n_samples) ** 0.5
                level = min(1.0, rms / 32768.0 * 4.0)
                self._mic_level = level
                self.micLevelChanged.emit()
            except Exception:
                break

    # ── TTS Synthesis ─────────────────────────────────────────

    @Property(bool, notify=ttsBusyChanged)
    def ttsBusy(self):
        return self._tts_busy

    @Property("QVariantList", notify=ttsPeaksAChanged)
    def ttsPeaksA(self):
        return self._tts_peaks_a

    @Property("QVariantList", notify=ttsPeaksBChanged)
    def ttsPeaksB(self):
        return self._tts_peaks_b

    @Property(str, notify=ttsAReady)
    def ttsPathA(self):
        return self._tts_path_a

    @Property(str, notify=ttsBReady)
    def ttsPathB(self):
        return self._tts_path_b

    @Slot(str)
    def synthesizeBoth(self, text: str):
        """Synthesize text with both Kokoro (A) and voice daemon (B)."""
        if self._tts_busy:
            return
        self._tts_busy = True
        self.ttsBusyChanged.emit()
        self._tts_text = text

        threading.Thread(
            target=self._synth_both, args=(text,), daemon=True
        ).start()

    def _synth_both(self, text: str):
        tmp_a = Path(tempfile.mktemp(suffix="_kokoro.wav"))
        tmp_b = Path(tempfile.mktemp(suffix="_voice.wav"))

        # Kokoro direct (localhost:8880)
        try:
            resp = httpx.post(
                "http://localhost:8880/v1/audio/speech",
                json={"input": text, "voice": "af_heart", "response_format": "wav"},
                timeout=30,
            )
            if resp.status_code == 200:
                tmp_a.write_bytes(resp.content)
                self._tts_path_a = str(tmp_a)
                self._tts_peaks_a = compute_peaks(tmp_a)
                self.ttsPeaksAChanged.emit()
                self.ttsAReady.emit()
        except Exception as e:
            logger.warning(f"Kokoro synthesis failed: {e}")

        # Voice daemon via Unix socket
        try:
            transport = httpx.HTTPTransport(uds="/run/user/1000/embry/voice.sock")
            client = httpx.Client(transport=transport, timeout=30)
            resp = client.post(
                "http://localhost/synthesize",
                json={"text": text, "persona": self._persona},
            )
            if resp.status_code == 200:
                tmp_b.write_bytes(resp.content)
                self._tts_path_b = str(tmp_b)
                self._tts_peaks_b = compute_peaks(tmp_b)
                self.ttsPeaksBChanged.emit()
                self.ttsBReady.emit()
            client.close()
        except Exception as e:
            logger.warning(f"Voice daemon synthesis failed: {e}")

        self._tts_busy = False
        self.ttsBusyChanged.emit()

    # ── Playback ──────────────────────────────────────────────

    @Slot(str)
    def play(self, path: str):
        """Play a WAV file via pw-play."""
        self._stop_playback()
        if not path or not Path(path).exists():
            return
        try:
            self._play_proc = subprocess.Popen(
                ["pw-play", path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            logger.warning("pw-play not found")

    @Slot()
    def stopPlayback(self):
        self._stop_playback()

    def _stop_playback(self):
        if self._play_proc:
            self._play_proc.terminate()
            self._play_proc = None
