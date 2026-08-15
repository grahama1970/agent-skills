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
        try:
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
        finally:
            _stop_backend_session(self._options.backend_url)

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
        transcription_thread = threading.Thread(
            target=_external_text_loop,
            args=(recorder, publisher.final, self._stop),
            name="live-evidence-pipewire-transcribe",
            daemon=True,
        )
        transcription_thread.start()
        command = _pipewire_record_command(str(self._options.pipewire_source))
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            if process.stdout is None:
                raise RuntimeError("pw-record stdout was not created")
            while not self._stop.is_set():
                chunk = process.stdout.read(4096)
                if not chunk:
                    if process.poll() is not None:
                        error = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
                        raise RuntimeError(f"pw-record exited {process.returncode}: {error[:300]}")
                    time.sleep(0.02)
                    continue
                recorder.feed_audio(chunk, original_sample_rate=16000)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3.0)
                except subprocess.TimeoutExpired:
                    process.kill()
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


def _stop_backend_session(backend_url: str) -> None:
    """Stop the backend session when the local listener exits."""

    timeout = httpx.Timeout(connect=1.0, read=2.0, write=1.0, pool=1.0)
    try:
        with _backend_client(backend_url, timeout=timeout) as client:
            response = client.post("/api/session/stop")
            response.raise_for_status()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("could not stop backend session after listener shutdown: {}", exc)


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


def _install_signal_handlers(stop: threading.Event) -> None:
    def handle_signal(_signum: int, _frame: Any) -> None:
        stop.set()

    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)
