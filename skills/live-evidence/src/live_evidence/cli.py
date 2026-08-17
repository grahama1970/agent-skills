"""Typer command-line interface for Live Evidence."""

from __future__ import annotations

import importlib.util
import json
import shutil
import threading
import time
import webbrowser
from pathlib import Path
from typing import Annotated

import httpx
import typer
import uvicorn
from loguru import logger

from .api import create_app
from .config import AppSettings
from .listener import ListenMode, ListenerOptions, LiveListener
from .models import (
    DoctorCheck,
    DoctorReport,
    ManualSearchRequest,
    RetrievalLane,
    Speaker,
    TranscriptEvent,
)


app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Local-first realtime interview evidence copilot.",
)


@app.command()
def serve(
    host: Annotated[str, typer.Option(help="Bind host.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(min=1, max=65_535, help="Bind port.")] = 8765,
    open_browser: Annotated[bool, typer.Option("--open-browser/--no-browser")] = False,
) -> None:
    """Run the FastAPI service and built React UI."""

    settings = AppSettings.from_env(host=host, port=port)
    if host not in {"127.0.0.1", "localhost", "::1"} and not settings.allow_remote_bind:
        raise typer.BadParameter(
            "non-loopback binds require LIVE_EVIDENCE_ALLOW_REMOTE_BIND=true"
        )
    application = create_app(settings)
    if open_browser:
        threading.Thread(
            target=_open_browser_after_delay,
            args=(f"http://{host}:{port}",),
            daemon=True,
        ).start()
    uvicorn.run(application, host=host, port=port, log_level="info")


@app.command()
def listen(
    mode: Annotated[ListenMode, typer.Option(help="Audio ingress mode.")] = ListenMode.MICROPHONE,
    backend_url: Annotated[str, typer.Option(help="Running Live Evidence API.")] = "http://127.0.0.1:8765",
    consent_confirmed: Annotated[
        bool,
        typer.Option("--consent-confirmed", help="Acknowledge required recording consent/policy."),
    ] = False,
    pipewire_source: Annotated[str | None, typer.Option(help="PipeWire source name/id.")] = None,
    speaker: Annotated[
        Speaker | None,
        typer.Option(help="Override the default speaker label for a single-channel listener."),
    ] = None,
    model: Annotated[str, typer.Option(help="RealtimeSTT final model.")] = "small.en",
    realtime_model: Annotated[str, typer.Option(help="RealtimeSTT interim model.")] = "tiny.en",
    device: Annotated[str, typer.Option(help="cuda or cpu.")] = "cuda",
    compute_type: Annotated[str, typer.Option(help="CTranslate2 compute type.")] = "int8",
    input_device_index: Annotated[int | None, typer.Option(help="Optional PyAudio input index.")] = None,
) -> None:
    """Start consent-gated live transcription."""

    if not consent_confirmed:
        raise typer.BadParameter("live modes require --consent-confirmed")
    settings = AppSettings.from_env()
    profile = settings.load_profile()
    options = ListenerOptions(
        backend_url=backend_url,
        mode=mode,
        consent_confirmed=consent_confirmed,
        microphone_speaker=(speaker or Speaker.GRAHAM),
        pipewire_speaker=(speaker or Speaker.INTERVIEWER),
        pipewire_source=pipewire_source,
        model=model,
        realtime_model=realtime_model,
        device=device,
        compute_type=compute_type,
        input_device_index=input_device_index,
    )
    LiveListener(options, profile).run()


@app.command()
def replay(
    transcript_file: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    backend_url: Annotated[str, typer.Option(help="Running Live Evidence API.")] = "http://127.0.0.1:8765",
    delay_s: Annotated[float, typer.Option(min=0.0, max=30.0)] = 1.2,
) -> None:
    """Replay validated JSONL transcript events into the API."""

    timeout = httpx.Timeout(connect=2.0, read=10.0, write=5.0, pool=2.0)
    with httpx.Client(base_url=backend_url.rstrip("/"), timeout=timeout) as client:
        start = client.post("/api/session/start", json={"consent_confirmed": False})
        start.raise_for_status()
        for line_number, raw in enumerate(transcript_file.read_text(encoding="utf-8").splitlines(), start=1):
            if not raw.strip():
                continue
            try:
                event = TranscriptEvent.model_validate(json.loads(raw))
            except (json.JSONDecodeError, ValueError) as exc:
                raise typer.BadParameter(f"invalid event at line {line_number}: {exc}") from exc
            response = client.post("/api/transcript", json=event.model_dump(mode="json"))
            response.raise_for_status()
            typer.echo(f"{event.speaker.value}: {event.text}")
            if delay_s:
                time.sleep(delay_s)


@app.command()
def search(
    query: Annotated[str, typer.Argument(min=2, max=1_000)],
    lane: Annotated[RetrievalLane, typer.Option(help="Explicit retrieval lane.")] = RetrievalLane.MEMORY,
    backend_url: Annotated[str, typer.Option(help="Running Live Evidence API.")] = "http://127.0.0.1:8765",
) -> None:
    """Run one manual source-bound search."""

    request = ManualSearchRequest(query=query, lane=lane)
    with httpx.Client(base_url=backend_url.rstrip("/"), timeout=60.0) as client:
        response = client.post("/api/search", json=request.model_dump(mode="json"))
        response.raise_for_status()
        typer.echo(json.dumps(response.json(), indent=2))


@app.command()
def doctor() -> None:
    """Inspect prepared-host readiness without starting a listener."""

    settings = AppSettings.from_env()
    checks: dict[str, DoctorCheck] = {}
    try:
        profile = settings.load_profile()
        checks["profile"] = DoctorCheck(
            status="PASS",
            detail=f"{profile.name} · {len(profile.repo_priorities)} declared repositories",
        )
    except (OSError, ValueError) as exc:
        checks["profile"] = DoctorCheck(
            status="DEGRADED",
            detail=f"{type(exc).__name__}: {exc}",
        )

    checks["ripgrep"] = DoctorCheck(
        status="PASS" if shutil.which("rg") else "DEGRADED",
        detail=shutil.which("rg") or "rg is not installed",
    )
    checks["repository_allowlist"] = DoctorCheck(
        status="PASS" if settings.repo_roots else "NOT_CONFIGURED",
        detail=(
            f"{len(settings.repo_roots)} existing repository root(s)"
            if settings.repo_roots
            else "Set LIVE_EVIDENCE_REPOS for current-source fallback"
        ),
    )
    checks["memory_runner"] = DoctorCheck(
        status="PASS" if settings.memory_runner else "NOT_CONFIGURED",
        detail=str(settings.memory_runner or "Sibling memory/run.sh was not found"),
    )
    memory_live = _memory_health(settings.memory_url)
    checks["memory_service"] = DoctorCheck(
        status="PASS" if memory_live else "DEGRADED",
        detail=(settings.memory_url if memory_live else f"No healthy response from {settings.memory_url}"),
    )
    stt_available = importlib.util.find_spec("RealtimeSTT") is not None
    checks["realtimestt"] = DoctorCheck(
        status="PASS" if stt_available else "NOT_CONFIGURED",
        detail=(
            "RealtimeSTT import is available"
            if stt_available
            else "Run ./run.sh setup --with-stt for live audio"
        ),
    )
    checks["pipewire"] = DoctorCheck(
        status="PASS" if shutil.which("pw-record") else "NOT_CONFIGURED",
        detail=shutil.which("pw-record") or "pw-record is unavailable; microphone mode can still work",
    )
    ui_built = (settings.skill_root / "ui" / "dist" / "index.html").exists()
    checks["react_ui"] = DoctorCheck(
        status="PASS" if ui_built else "NOT_CONFIGURED",
        detail="ui/dist is built" if ui_built else "Run ./run.sh ui-build after setup",
    )

    retrieval_ready = bool(settings.repo_roots) or memory_live
    core_ready = (
        checks["profile"].status == "PASS"
        and checks["ripgrep"].status == "PASS"
        and retrieval_ready
    )
    status_value = (
        "READY_FOR_LIVE"
        if core_ready and stt_available
        else "READY_FOR_REPLAY"
        if core_ready
        else "NEEDS_SETUP"
    )
    report = DoctorReport(status=status_value, checks=checks)
    typer.echo(report.model_dump_json(indent=2))
    if status_value == "NEEDS_SETUP":
        raise typer.Exit(code=1)


@app.command()
def status(
    backend_url: Annotated[str, typer.Option(help="Running Live Evidence API.")] = "http://127.0.0.1:8765",
) -> None:
    """Read service health and current session state."""

    try:
        with httpx.Client(base_url=backend_url.rstrip("/"), timeout=3.0) as client:
            health = client.get("/api/health")
            health.raise_for_status()
            state = client.get("/api/state")
            state.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error("Live Evidence is unavailable: {}", exc)
        raise typer.Exit(code=2) from exc
    typer.echo(json.dumps({"health": health.json(), "state": state.json()}, indent=2))


def _memory_health(base_url: str) -> bool:
    timeout = httpx.Timeout(connect=0.6, read=1.0, write=1.0, pool=0.6)
    for path in ("/health", "/health/liveliness"):
        try:
            with httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout) as client:
                response = client.get(path)
            if response.status_code == 200:
                return True
        except httpx.HTTPError:
            continue
    return False


def _open_browser_after_delay(url: str) -> None:
    time.sleep(0.9)
    webbrowser.open(url)
