"""RealtimeSTT microphone and PipeWire adapters.

Live modes require an explicit consent acknowledgement. Audio chunks are fed to
RealtimeSTT and are not persisted. The module imports the optional heavy speech
stack only when a listener actually starts.
"""

from __future__ import annotations

import queue
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Callable

import httpx
from loguru import logger

from .config import InterviewProfile
from .models import Speaker, TranscriptEvent, TranscriptKind, TranscriptSource


class ListenMode(StrEnum):
    """Supported audio-ingress modes."""

    MICROPHONE = "microphone"
    PIPEWIRE = "pipewire"
    DUAL = "dual"


@dataclass(frozen=True, slots=True)
class ListenerOptions:
    """Validated runtime options for a live listener."""

    backend_url: str
    mode: ListenMode
    consent_confirmed: bool
    microphone_speaker: Speaker = Speaker.GRAHAM
    pipewire_speaker: Speaker = Speaker.INTERVIEWER
    pipewire_source: str | None = None
    model: str = "small.en"
    realtime_model: str = "tiny.en"
    device: str = "cuda"
    compute_type: str = "int8"
    input_device_index: int | None = None


class TranscriptPublisher:
    """Publish validated transcript events to the local API."""

    def __init__(self, backend_url: str, source: TranscriptSource, speaker: Speaker) -> None:
        self._client = httpx.Client(
            base_url=backend_url.rstrip("/"),
            timeout=httpx.Timeout(connect=2.0, read=5.0, write=5.0, pool=2.0),
            trust_env=False,
            verify=_verify_tls_for_url(backend_url),
        )
        self._source = source
        self._speaker = speaker
        self._sequence = 0
        self._last_interim = ""
        self._lock = threading.Lock()
        self._closed = False

    def interim(self, text: str) -> None:
        clean = " ".join(text.split())
        if not clean:
            return
        with self._lock:
            if self._closed or clean == self._last_interim:
                return
            self._last_interim = clean
            self._publish_locked(TranscriptKind.INTERIM, clean)

    def stabilized(self, text: str) -> None:
        clean = " ".join(text.split())
        if not clean:
            return
        with self._lock:
            if self._closed:
                return
            self._publish_locked(TranscriptKind.STABILIZED, clean)

    def final(self, text: str) -> None:
        clean = " ".join(text.split())
        if not clean:
            return
        with self._lock:
            if self._closed:
                return
            self._last_interim = ""
            self._publish_locked(TranscriptKind.FINAL, clean)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._client.close()

    def _publish_locked(self, kind: TranscriptKind, text: str) -> None:
        """Publish while holding the callback lock so sequence and close cannot race."""

        self._sequence += 1
        event = TranscriptEvent(
            speaker=self._speaker,
            kind=kind,
            source=self._source,
            text=text,
            sequence=self._sequence,
        )
        response = self._client.post("/api/transcript", json=event.model_dump(mode="json"))
        response.raise_for_status()


class LiveListener:
    """Coordinate one or two RealtimeSTT audio channels."""

    def __init__(self, options: ListenerOptions, profile: InterviewProfile) -> None:
        if not options.consent_confirmed:
            raise ValueError("live listening requires --consent-confirmed")
        if options.mode in {ListenMode.PIPEWIRE, ListenMode.DUAL} and not options.pipewire_source:
            raise ValueError("PipeWire and dual modes require --pipewire-source")
        self._options = options
        self._profile = profile
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._errors: queue.Queue[Exception] = queue.Queue()

    def run(self) -> None:
        """Start configured channels and block until interrupted."""

        _install_signal_handlers(self._stop)
        _start_backend_session(self._options.backend_url, self._options.consent_confirmed)
        if self._options.mode in {ListenMode.MICROPHONE, ListenMode.DUAL}:
            self._threads.append(
                threading.Thread(
                    target=self._guarded_channel,
                    args=(self._run_microphone,),
                    name="live-evidence-mic",
                    daemon=True,
                )
            )
        if self._options.mode in {ListenMode.PIPEWIRE, ListenMode.DUAL}:
            self._threads.append(
                threading.Thread(
                    target=self._guarded_channel,
                    args=(self._run_pipewire,),
                    name="live-evidence-pipewire",
                    daemon=True,
                )
            )
        if not self._threads:
            raise RuntimeError("no listener channels selected")
        for thread in self._threads:
            thread.start()
        logger.info("live listener started mode={}", self._options.mode.value)
        next_status_poll = time.monotonic()
        backend_failures = 0
        while not self._stop.wait(0.25):
            try:
                error = self._errors.get_nowait()
            except queue.Empty:
                error = None
            if error is not None:
                raise RuntimeError(f"listener channel failed: {error}") from error
            if not any(thread.is_alive() for thread in self._threads):
                raise RuntimeError("all listener channels stopped unexpectedly")
            if time.monotonic() >= next_status_poll:
                next_status_poll = time.monotonic() + 0.75
                status = _read_backend_session_status(self._options.backend_url)
                if status == "stopped":
                    logger.info("backend session stopped; ending audio capture")
                    self._stop.set()
                    break
                if status is None:
                    backend_failures += 1
                    if backend_failures >= 8:
                        raise RuntimeError("backend state monitor failed repeatedly")
                else:
                    backend_failures = 0
        for thread in self._threads:
            thread.join(timeout=5.0)
        if not self._errors.empty():
            error = self._errors.get_nowait()
            raise RuntimeError(f"listener channel failed: {error}") from error
        logger.info("live listener stopped")

    def _guarded_channel(self, target: Callable[[], None]) -> None:
        try:
            target()
        except Exception as exc:
            logger.error("listener channel failed: {}", type(exc).__name__)
            self._errors.put(exc)
            self._stop.set()

    def _run_microphone(self) -> None:
        recorder_cls = _load_recorder()
        publisher = TranscriptPublisher(
            self._options.backend_url,
            TranscriptSource.MICROPHONE,
            self._options.microphone_speaker,
        )
        recorder = recorder_cls(
            model=self._options.model,
            realtime_model_type=self._options.realtime_model,
            device=self._options.device,
            compute_type=self._options.compute_type,
            input_device_index=self._options.input_device_index,
            language="en",
            enable_realtime_transcription=True,
            **_stt_final_boundary_kwargs(),
            initial_prompt=", ".join(self._profile.stt_prompt_terms),
            initial_prompt_realtime=", ".join(self._profile.stt_prompt_terms),
            on_realtime_transcription_update=publisher.interim,
            on_realtime_transcription_stabilized=publisher.stabilized,
            start_callback_in_new_thread=True,
            spinner=False,
        )
        try:
            while not self._stop.is_set():
                recorder.text(publisher.final)
        finally:
            recorder.shutdown()
            publisher.close()

    def _run_pipewire(self) -> None:
        recorder_cls = _load_recorder()
        publisher = TranscriptPublisher(
            self._options.backend_url,
            TranscriptSource.PIPEWIRE,
            self._options.pipewire_speaker,
        )
        recorder = recorder_cls(
            use_microphone=False,
            model=self._options.model,
            realtime_model_type=self._options.realtime_model,
            device=self._options.device,
            compute_type=self._options.compute_type,
            language="en",
            enable_realtime_transcription=True,
            **_stt_final_boundary_kwargs(),
            initial_prompt=", ".join(self._profile.stt_prompt_terms),
            initial_prompt_realtime=", ".join(self._profile.stt_prompt_terms),
            on_realtime_transcription_update=publisher.interim,
            on_realtime_transcription_stabilized=publisher.stabilized,
            start_callback_in_new_thread=True,
            spinner=False,
        )
        transcription_errors: queue.Queue[Exception] = queue.Queue()
        transcription_thread = threading.Thread(
            target=_guarded_external_text_loop,
            args=(recorder, publisher.final, self._stop, transcription_errors),
            name="live-evidence-pipewire-transcribe",
            daemon=True,
        )
        transcription_thread.start()
        try:
            # Google-Meet-style live input level: RMS over ~1s windows,
            # announced to the backend so the HUD can render a level meter
            # and the human can verify the selected device actually hears.
            import audioop

            while not self._stop.is_set():
                resolved_source, resolve_reason = resolve_pipewire_source(
                    str(self._options.pipewire_source) if self._options.pipewire_source else None
                )
                logger.info("pipewire source resolved: {} ({})", resolved_source, resolve_reason)
                _announce_listener(self._options.backend_url, resolved_source, resolve_reason)
                process = subprocess.Popen(
                    _pipewire_record_command(resolved_source),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                try:
                    if process.stdout is None:
                        raise RuntimeError("pw-record stdout was not created")
                    level_window: list[int] = []
                    last_level_post = time.monotonic()
                    while not self._stop.is_set():
                        if not transcription_errors.empty():
                            error = transcription_errors.get_nowait()
                            _announce_listener(self._options.backend_url, resolved_source, "transcription_error", level=0)
                            raise RuntimeError(f"transcription worker failed: {error}") from error
                        if not transcription_thread.is_alive():
                            _announce_listener(self._options.backend_url, resolved_source, "transcription_error", level=0)
                            raise RuntimeError("transcription worker stopped")
                        chunk = process.stdout.read(4096)
                        if not chunk:
                            if process.poll() is not None:
                                error = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
                                logger.warning("pw-record exited {}; restarting: {}", process.returncode, error[:300])
                                _announce_listener(self._options.backend_url, resolved_source, "restarting", level=0)
                                time.sleep(1.0)
                                break
                            time.sleep(0.02)
                            continue
                        recorder.feed_audio(chunk, original_sample_rate=16000)
                        try:
                            level_window.append(audioop.rms(chunk, 2))
                        except Exception:
                            level_window.append(0)
                        now = time.monotonic()
                        if now - last_level_post >= 0.25 and level_window:
                            rms = max(level_window)
                            level_window.clear()
                            last_level_post = now
                            # 0-100 scale: 3000 RMS on s16 speech is already loud.
                            percent = min(100, int(rms / 30))
                            threading.Thread(
                                target=_announce_listener,
                                args=(self._options.backend_url, resolved_source, resolve_reason),
                                kwargs={"level": percent},
                                daemon=True,
                            ).start()
                finally:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=3.0)
                        except subprocess.TimeoutExpired:
                            process.kill()
        finally:
            recorder.shutdown()
            publisher.close()
            transcription_thread.join(timeout=3.0)


def _start_backend_session(backend_url: str, consent_confirmed: bool) -> None:
    """Start one backend session before any audio channel publishes turns."""

    timeout = httpx.Timeout(connect=2.0, read=5.0, write=5.0, pool=2.0)
    with _backend_client(backend_url, timeout=timeout) as client:
        response = client.post(
            "/api/session/start",
            json={"consent_confirmed": consent_confirmed},
        )
        response.raise_for_status()


def _read_backend_session_status(backend_url: str) -> str | None:
    """Read the operator session state so the UI Stop control ends capture."""

    timeout = httpx.Timeout(connect=1.0, read=2.0, write=1.0, pool=1.0)
    try:
        with _backend_client(backend_url, timeout=timeout) as client:
            response = client.get("/api/state")
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    session = payload.get("session")
    if not isinstance(session, dict):
        return None
    status = session.get("status")
    return status if isinstance(status, str) else None


def _backend_client(backend_url: str, *, timeout: httpx.Timeout) -> httpx.Client:
    """Create a loopback API client isolated from host proxy and CA env vars."""

    return httpx.Client(
        base_url=backend_url.rstrip("/"),
        timeout=timeout,
        trust_env=False,
        verify=_verify_tls_for_url(backend_url),
    )


def _verify_tls_for_url(url: str) -> bool:
    """Avoid host CA setup for local plain-HTTP API clients."""

    return not url.casefold().startswith("http://")


def _stt_final_boundary_kwargs() -> dict[str, object]:
    """Return STT settings required before final transcript events are trusted."""

    return {
        "faster_whisper_vad_filter": True,
        "ensure_sentence_ends_with_period": False,
    }


def _load_recorder() -> Any:
    """Import optional RealtimeSTT only at live-listener startup."""

    try:
        from RealtimeSTT import AudioToTextRecorder
    except ImportError as exc:
        raise RuntimeError(
            "RealtimeSTT is not installed. Run ./run.sh setup --with-stt."
        ) from exc
    return AudioToTextRecorder


def _announce_listener(backend_url: str, device: str, reason: str, level: int | None = None) -> None:
    """Tell the backend which device is captured and how loud it is (best effort)."""

    payload = {"device": device, "resolve_reason": reason, "mode": "pipewire"}
    if level is not None:
        payload["level"] = str(level)
    try:
        httpx.post(
            f"{backend_url.rstrip('/')}/api/listener/announce",
            json=payload,
            timeout=httpx.Timeout(connect=1.0, read=2.0, write=1.0, pool=1.0),
        )
    except httpx.HTTPError:
        logger.warning("listener announce failed; HUD will not show the device")


def resolve_pipewire_source(requested: str | None) -> tuple[str, str]:
    """Resolve the capture source, auto-switching when the named one is gone.

    The Jabra hops between USB (alsa_input.usb-0b0e_Jabra...) and Bluetooth
    (bluez_input.<MAC>) identities; a listener pinned to a stale name records
    silence forever (live incident 2026-09-03: 0 events while the room played
    audio). Order: exact name -> substring match -> RUNNING input -> bluez
    input -> USB/alsa input. Returns (source_name, reason).
    """

    try:
        sources_output = subprocess.run(
            ["pactl", "list", "short", "sources"],
            capture_output=True, text=True, timeout=5, check=False,
        ).stdout
        sinks_output = subprocess.run(
            ["pactl", "list", "short", "sinks"],
            capture_output=True, text=True, timeout=5, check=False,
        ).stdout
    except (OSError, subprocess.TimeoutExpired) as exc:
        if requested in {None, "auto"}:
            return "@DEFAULT_SOURCE@", "pactl_unavailable"
        raise RuntimeError(f"cannot resolve requested PipeWire source {requested!r}: {exc}") from exc
    rows = [line.split("\t") for line in sources_output.splitlines() if "\t" in line]
    names = [row[1] for row in rows if len(row) > 1]
    inputs = [n for n in names if not n.endswith(".monitor")]
    sink_names = [line.split("\t")[1] for line in sinks_output.splitlines() if "\t" in line and len(line.split("\t")) > 1]

    def jabra_inputs() -> list[str]:
        candidates = [n for n in inputs if n.startswith("bluez_input.")]
        candidates += [n for n in inputs if "jabra" in n.casefold() and n not in candidates]
        return candidates

    if requested == "auto:jabra-input":
        matches = jabra_inputs()
        if len(matches) == 1:
            return matches[0], "auto_jabra_input"
        available = ", ".join(inputs) or "none"
        if not matches:
            raise RuntimeError(f"auto:jabra-input found no Jabra input sources; available inputs: {available}")
        raise RuntimeError(f"auto:jabra-input found multiple candidates {matches}; choose one explicitly")
    if requested and requested.startswith("sink:"):
        sink = requested.split(":", 1)[1]
        if sink not in sink_names:
            available = ", ".join(sink_names) or "none"
            raise RuntimeError(f"requested sink {sink!r} is unavailable; available sinks: {available}")
        return requested, "exact_sink"
    if requested and requested in names:
        return requested, "exact"
    if requested and requested != "auto":
        for name in inputs:
            if requested.casefold() in name.casefold() or name.casefold() in requested.casefold():
                return name, "substring"
        available = ", ".join(inputs) or "none"
        raise RuntimeError(f"requested PipeWire source {requested!r} is unavailable; available inputs: {available}")
    running = [row[1] for row in rows if len(row) > 3 and row[-1].strip() == "RUNNING" and not row[1].endswith(".monitor")]
    for pool, reason in ((jabra_inputs(), "jabra_input"),
                         (running, "running_input"),
                         ([n for n in inputs if n.startswith("alsa_input.")], "usb_input")):
        if pool:
            return pool[0], reason
    return "@DEFAULT_SOURCE@", "no_candidates"


def _pipewire_record_command(target: str) -> list[str]:
    """Build a pw-record command for physical sources or sink monitors."""

    if target.startswith("sink:"):
        return [
            "pw-record",
            "-P",
            "{ stream.capture.sink=true }",
            "--target",
            target.split(":", 1)[1],
            "--rate",
            "16000",
            "--channels",
            "1",
            "--format",
            "s16",
            "-",
        ]
    return [
        "pw-record",
        "--target",
        target,
        "--rate",
        "16000",
        "--channels",
        "1",
        "--format",
        "s16",
        "-",
    ]


def _external_text_loop(recorder: Any, callback: Callable[[str], None], stop: threading.Event) -> None:
    while not stop.is_set():
        recorder.text(callback)


def _guarded_external_text_loop(
    recorder: Any, callback: Callable[[str], None], stop: threading.Event, errors: queue.Queue[Exception]
) -> None:
    try:
        _external_text_loop(recorder, callback, stop)
    except Exception as exc:
        errors.put(exc)
        stop.set()


def _install_signal_handlers(stop: threading.Event) -> None:
    def handle_signal(_signum: int, _frame: Any) -> None:
        stop.set()

    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)
