"""ops-obs CLI: Typer commands over the obs_protocol layer.

Inputs: CLI flags and the environment (OBS_WS_HOST, OBS_WS_PORT, OBS_WS_PASSWORD).
Outputs: JSON on stdout; typed failure envelope + exit 1 on failure; exit 2
for usage errors.
Failure modes: TypedFailure is caught once in main() and rendered — never a
traceback on stdout.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer
from dotenv import load_dotenv
from loguru import logger

load_dotenv()
from obs_protocol import (
    AUTH_VECTOR,
    BRIDGE_CLI,
    DEFAULT_PORT,
    DISK_CRIT_GB,
    DISK_WARN_GB,
    FailureCode,
    ObsClient,
    ObsRequestError,
    OutputStatusData,
    RecordStatusData,
    SceneListData,
    StatsData,
    TypedFailure,
    VersionData,
    auth_string,
    detect_config_root,
    emit,
    evaluate_health,
    fail,
    read_ws_config,
    render_failure,
    resolve_conn,
)

# --------------------------------------------------------------- commands

app = typer.Typer(help="Monitor and optimize OBS Studio (obs-websocket v5 + local diagnostics).", no_args_is_help=True)
stream_app = typer.Typer(help="Stream output control.", no_args_is_help=True)
record_app = typer.Typer(help="Record output control.", no_args_is_help=True)
scene_app = typer.Typer(help="Scene inspection and switching.", no_args_is_help=True)
app.add_typer(stream_app, name="stream")
app.add_typer(record_app, name="record")
app.add_typer(scene_app, name="scene")
deck_app = typer.Typer(help="Stream Deck integration: bindings + widget state token.", no_args_is_help=True)
app.add_typer(deck_app, name="streamdeck")


@dataclass(frozen=True, slots=True)
class Conn:
    """Raw connection target from CLI/env; _client() resolves defaults (config, env)."""

    host: str | None
    port: int | None
    password: str | None
    timeout: float


HostOpt = Annotated[str | None, typer.Option("--host", help="obs-websocket host (default OBS_WS_HOST or 127.0.0.1)")]
PortOpt = Annotated[int | None, typer.Option("--port", help="obs-websocket port (default OBS_WS_PORT, OBS config, or 4455)")]
PasswordOpt = Annotated[str | None, typer.Option("--password", help="websocket password (default OBS_WS_PASSWORD or OBS config)")]
TimeoutOpt = Annotated[float, typer.Option("--timeout", min=0.1, help="websocket timeout seconds")]


def _client(conn: Conn) -> ObsClient:
    host, port, password, timeout = resolve_conn(conn.host, conn.port, conn.password, conn.timeout)
    client = ObsClient(host, port, password, timeout)
    client.connect()
    return client


def _gather(client: ObsClient) -> dict[str, Any]:
    version = VersionData.model_validate(client.request("GetVersion"))
    stats = StatsData.model_validate(client.request("GetStats"))
    stream = record = None
    try:
        stream = OutputStatusData.model_validate(client.request("GetStreamStatus"))
    except ObsRequestError as exc:
        logger.warning("GetStreamStatus unavailable: {}", exc)
    try:
        record = RecordStatusData.model_validate(client.request("GetRecordStatus"))
    except ObsRequestError as exc:
        logger.warning("GetRecordStatus unavailable: {}", exc)
    return {
        "version": version.model_dump(),
        "stats": stats.model_dump(),
        "stream": stream.model_dump() if stream else None,
        "record": record.model_dump() if record else None,
        "health": evaluate_health(stats, stream, record),
    }


@app.command()
def status(
    host: HostOpt = None,
    port: PortOpt = None,
    password: PasswordOpt = None,
    timeout: TimeoutOpt = 5.0,
) -> None:
    """One-shot snapshot: version, stats, stream/record state, health findings."""
    client = _client(Conn(host, port, password, timeout))
    try:
        emit({"ok": True, **_gather(client)})
    finally:
        client.close()


@app.command()
def watch(
    interval: float = typer.Option(5.0, "--interval", min=0.1, help="seconds between samples"),
    notify_tab: str | None = typer.Option(None, "--notify-tab", help="Herdr tab label to message on crit findings (via ops-herdr bridge)"),
    host: HostOpt = None,
    port: PortOpt = None,
    password: PasswordOpt = None,
    timeout: TimeoutOpt = 5.0,
) -> None:
    """Continuous monitoring: one NDJSON status line per interval. Ctrl+C to stop."""
    client = _client(Conn(host, port, password, timeout))
    try:
        while True:
            snapshot = {"ok": True, "ts": datetime.now(UTC).isoformat(), **_gather(client)}
            print(json.dumps(snapshot, default=str), flush=True)
            if notify_tab:
                crits = [f["check"] for f in snapshot["health"] if f["status"] == "crit"]
                if crits:
                    _bridge_send(notify_tab, f"ops-obs CRIT: {', '.join(crits)} (fps={snapshot['stats']['activeFps']})")
            time.sleep(interval)
    except KeyboardInterrupt:
        logger.info("watch stopped")
        raise typer.Exit(0) from None
    finally:
        client.close()


@stream_app.command("status")
def stream_status(
    host: HostOpt = None,
    port: PortOpt = None,
    password: PasswordOpt = None,
    timeout: TimeoutOpt = 5.0,
) -> None:
    """Get stream output status."""
    client = _client(Conn(host, port, password, timeout))
    try:
        emit({"ok": True, "stream": OutputStatusData.model_validate(client.request("GetStreamStatus")).model_dump()})
    finally:
        client.close()


def _stream_action(conn: Conn, kind: str) -> None:
    req = {"start": "StartStream", "stop": "StopStream", "toggle": "ToggleStream"}[kind]
    expected_note = {"start": ("500", "already running"), "stop": ("501", "not running")}.get(kind)
    client = _client(conn)
    try:
        result: dict[str, Any] = {}
        try:
            result = client.request(req)
        except ObsRequestError as exc:
            if expected_note and str(exc).startswith(f"{req} failed: code={expected_note[0]}"):
                emit({"ok": True, "action": kind, "note": expected_note[1]})
                return
            fail(FailureCode.REQUEST_FAILED, str(exc), "run 'ops-obs stream status' to inspect state")
        emit({"ok": True, "action": kind, "result": result})
    finally:
        client.close()


@stream_app.command("start")
def stream_start(
    host: HostOpt = None,
    port: PortOpt = None,
    password: PasswordOpt = None,
    timeout: TimeoutOpt = 5.0,
) -> None:
    """Start streaming (tolerates already-running)."""
    _stream_action(Conn(host, port, password, timeout), "start")


@stream_app.command("stop")
def stream_stop(
    host: HostOpt = None,
    port: PortOpt = None,
    password: PasswordOpt = None,
    timeout: TimeoutOpt = 5.0,
) -> None:
    """Stop streaming (tolerates not-running)."""
    _stream_action(Conn(host, port, password, timeout), "stop")


@stream_app.command("toggle")
def stream_toggle(
    host: HostOpt = None,
    port: PortOpt = None,
    password: PasswordOpt = None,
    timeout: TimeoutOpt = 5.0,
) -> None:
    """Toggle streaming."""
    _stream_action(Conn(host, port, password, timeout), "toggle")


@record_app.command("status")
def record_status(
    host: HostOpt = None,
    port: PortOpt = None,
    password: PasswordOpt = None,
    timeout: TimeoutOpt = 5.0,
) -> None:
    """Get record output status."""
    client = _client(Conn(host, port, password, timeout))
    try:
        emit({"ok": True, "record": RecordStatusData.model_validate(client.request("GetRecordStatus")).model_dump()})
    finally:
        client.close()


def _record_action(conn: Conn, kind: str) -> None:
    req = {"start": "StartRecord", "stop": "StopRecord", "toggle": "ToggleRecord"}[kind]
    expected_note = {"start": ("500", "already recording"), "stop": ("501", "not recording")}.get(kind)
    client = _client(conn)
    try:
        result: dict[str, Any] = {}
        try:
            result = client.request(req)
        except ObsRequestError as exc:
            if expected_note and str(exc).startswith(f"{req} failed: code={expected_note[0]}"):
                emit({"ok": True, "action": kind, "note": expected_note[1]})
                return
            fail(FailureCode.REQUEST_FAILED, str(exc), "run 'ops-obs record status' to inspect state")
        if kind == "stop" and result:
            emit({"ok": True, "action": kind, "output_path": result.get("outputPath")})
            return
        emit({"ok": True, "action": kind, "result": result})
    finally:
        client.close()


@record_app.command("start")
def record_start(
    host: HostOpt = None,
    port: PortOpt = None,
    password: PasswordOpt = None,
    timeout: TimeoutOpt = 5.0,
) -> None:
    """Start recording (tolerates already-recording)."""
    _record_action(Conn(host, port, password, timeout), "start")


@record_app.command("stop")
def record_stop(
    host: HostOpt = None,
    port: PortOpt = None,
    password: PasswordOpt = None,
    timeout: TimeoutOpt = 5.0,
) -> None:
    """Stop recording; prints the output path."""
    _record_action(Conn(host, port, password, timeout), "stop")


@record_app.command("toggle")
def record_toggle(
    host: HostOpt = None,
    port: PortOpt = None,
    password: PasswordOpt = None,
    timeout: TimeoutOpt = 5.0,
) -> None:
    """Toggle recording."""
    _record_action(Conn(host, port, password, timeout), "toggle")


@scene_app.command("list")
def scene_list(
    host: HostOpt = None,
    port: PortOpt = None,
    password: PasswordOpt = None,
    timeout: TimeoutOpt = 5.0,
) -> None:
    """List scenes and the current program scene."""
    client = _client(Conn(host, port, password, timeout))
    try:
        data = SceneListData.model_validate(client.request("GetSceneList"))
        emit({"ok": True, "current": data.currentProgramSceneName, "scenes": [s.sceneName for s in data.scenes]})
    finally:
        client.close()


@scene_app.command("set")
def scene_set(
    name: str = typer.Argument(..., help="scene to switch to"),
    host: HostOpt = None,
    port: PortOpt = None,
    password: PasswordOpt = None,
    timeout: TimeoutOpt = 5.0,
) -> None:
    """Switch the current program scene."""
    client = _client(Conn(host, port, password, timeout))
    try:
        client.request("SetCurrentProgramScene", {"sceneName": name})
        data = SceneListData.model_validate(client.request("GetSceneList"))
        emit({"ok": True, "current": data.currentProgramSceneName})
    except ObsRequestError as exc:
        if exc.code == 600:
            fail(FailureCode.REQUEST_FAILED, f"scene not found: {name}", "run 'ops-obs scene list' for valid names")
        fail(FailureCode.REQUEST_FAILED, str(exc), "run 'ops-obs scene list'")
    finally:
        client.close()


@app.command()
def paths() -> None:
    """Resolve local OBS paths (config root, logs, websocket config)."""
    kind, root = detect_config_root()
    cfg = read_ws_config()
    emit(
        {
            "ok": True,
            "install_kind": kind,
            "config_root": str(root) if root else None,
            "logs_dir": str(root / "logs") if root else None,
            "ws_config": str(root / "plugin_config/obs-websocket/basic.json") if root else None,
            "ws_server_enabled": cfg.server_enabled if cfg else None,
        }
    )


def _run(cmd: list[str], timeout: float = 10.0) -> str | None:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.error("command {} failed: {}", cmd[0], exc)
        return None


def _obs_version(kind: str | None) -> str | None:
    if kind == "flatpak":
        out = _run(["flatpak", "info", "com.obsproject.Studio"])
        if out:
            for line in out.splitlines():
                if line.strip().startswith("Version:"):
                    return line.split(":", 1)[1].strip()
    elif kind == "native" and shutil.which("obs"):
        out = _run(["obs", "--version"])
        if out:
            return out.splitlines()[0].strip()
    return None


def _log_scan(logs_dir: Path | None) -> dict[str, Any]:
    if logs_dir is None or not logs_dir.is_dir():
        return {"log": None, "note": "no logs dir"}
    logs = sorted(logs_dir.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not logs:
        return {"log": None, "note": "no log files"}
    newest = logs[0]
    try:
        text = newest.read_bytes()[-262144:].decode("utf-8", errors="replace")
    except OSError as exc:
        logger.error("cannot read {}: {}", newest, exc)
        return {"log": str(newest), "note": "unreadable"}
    low = text.lower()
    last_error = next((ln.strip() for ln in reversed(text.splitlines()) if "error" in ln.lower()), None)
    return {
        "log": str(newest),
        "modified": datetime.fromtimestamp(newest.stat().st_mtime, UTC).isoformat(),
        "encoding_lag_hits": low.count("encoding lag"),
        "dropped_frame_hits": low.count("dropped frames"),
        "nvenc_hits": low.count("nvenc"),
        "error_hits": low.count("error"),
        "last_error_line": last_error,
    }


def _runsh() -> Path:
    """Absolute run.sh path, validated runnable before it is emitted in any command."""
    p = Path(__file__).resolve().parents[1] / "run.sh"
    if not (p.is_file() and os.access(p, os.X_OK)):
        fail(FailureCode.PROTOCOL, f"run.sh not runnable at {p}", "restore it or chmod +x")
    return p


@deck_app.command("bindings")
def deck_bindings() -> None:
    """Emit Stream Deck button definitions whose commands invoke this CLI (for ops-streamdeck daemon config)."""
    rs = str(_runsh())
    buttons = [
        {"id": "obs-stream-toggle", "name": "OBS Stream", "command": f"{rs} stream toggle"},
        {"id": "obs-record-toggle", "name": "OBS Record", "command": f"{rs} record toggle"},
        {"id": "obs-deck-state", "name": "OBS State", "command": f"{rs} streamdeck status"},
    ]
    emit(
        {
            "ok": True,
            "schema": "ops-obs.streamdeck_bindings.v1",
            "target": "~/.streamdeck/daemon.json buttons (merge via ops-streamdeck; never edit ~/.streamdeck_ui.json while streamdeck.service runs)",
            "buttons": buttons,
            "status_probe": {
                "tokens": ["OFFLINE", "LIVE", "REC", "LIVE+REC", "ERR:<failure_code>"],
                "note": "exit 0 with state token on stdout; exit 1 with ERR:<code> for icon renderers",
            },
        }
    )


@deck_app.command("status")
def deck_status(
    host: HostOpt = None,
    port: PortOpt = None,
    password: PasswordOpt = None,
    timeout: TimeoutOpt = 5.0,
) -> None:
    """One-token deck state for icon renderers: OFFLINE, LIVE, REC, LIVE+REC, or ERR:<code>."""
    try:
        client = _client(Conn(host, port, password, timeout))
    except TypedFailure as e:
        print(f"ERR:{e.code.value}")
        raise typer.Exit(1) from None
    try:
        live = bool(OutputStatusData.model_validate(client.request("GetStreamStatus")).outputActive)
        rec = bool(RecordStatusData.model_validate(client.request("GetRecordStatus")).outputActive)
    except (TypedFailure, ObsRequestError) as e:
        code = e.code.value if isinstance(e, TypedFailure) else FailureCode.REQUEST_FAILED.value
        print(f"ERR:{code}")
        raise typer.Exit(1) from None
    finally:
        client.close()
    if live and rec:
        token = "LIVE+REC"
    elif rec:
        token = "REC"
    elif live:
        token = "LIVE"
    else:
        token = "OFFLINE"
    print(token)


def _bridge_send(tab: str, text: str) -> None:
    """Send text to a Herdr tab through the ops-herdr bridge; typed failures only."""
    if not BRIDGE_CLI.is_file() or shutil.which("node") is None:
        fail(
            FailureCode.NOTIFY_BRIDGE_UNAVAILABLE,
            f"ops-herdr bridge CLI or node runtime missing ({BRIDGE_CLI})",
            "verify skills/ops-herdr/pi-herdr-bridge/bridge-cli.mjs and the node runtime",
        )
    try:
        r = subprocess.run(
            ["node", str(BRIDGE_CLI), "send", "--to", tab, "--text", text],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as err:
        logger.error("bridge send failed: {}", err)
        fail(FailureCode.NOTIFY_FAILED, f"bridge send error: {err}", "list tabs with bridge-cli.mjs list and retry")
    if r.returncode != 0:
        detail = (r.stderr.strip() or r.stdout.strip())[:200]
        fail(
            FailureCode.NOTIFY_FAILED,
            f"bridge send to tab '{tab}' rejected: {detail}",
            "list tabs with bridge-cli.mjs list and use the exact tab label",
        )


@app.command()
def notify(
    text: str = typer.Argument(..., help="message text"),
    tab: str = typer.Option(..., "--tab", help="Herdr tab label to message via the ops-herdr bridge"),
) -> None:
    """Send a message to a Herdr tab through the ops-herdr pi-herdr bridge."""
    _bridge_send(tab, text)
    emit({"ok": True, "tab": tab, "sent": text})


@app.command()
def doctor() -> None:
    """Local (no websocket needed) diagnostics: install, ws server, GPU, logs, disk."""
    checks: list[dict[str, Any]] = []
    kind, root = detect_config_root()
    version = _obs_version(kind)
    checks.append({"check": "obs_install", "status": "ok" if kind else "fail",
                   "detail": f"{kind or 'not found'}{f' {version}' if version else ''}",
                   **({} if kind else {"next_command": "install OBS (flatpak install flathub com.obsproject.Studio) or apt install obs-studio"})})

    running = False
    try:
        r = subprocess.run(["pgrep", "-x", "obs"], capture_output=True, text=True, timeout=5, check=False)
        running = r.returncode == 0
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.error("pgrep failed: {}", exc)
    checks.append({"check": "obs_running", "status": "ok" if running else "warn",
                   "detail": "obs process running" if running else "obs not running (local-only checks below still valid)"})

    cfg = read_ws_config()
    ws_port = cfg.server_port if cfg and cfg.server_port else DEFAULT_PORT
    if cfg is None:
        checks.append({"check": "ws_server", "status": "warn", "detail": "no obs-websocket config found",
                       "next_command": "open OBS once, then Tools -> WebSocket Server Settings"})
    else:
        enabled = bool(cfg.server_enabled)
        checks.append({"check": "ws_server", "status": "ok" if enabled else "warn",
                       "detail": f"enabled={enabled} port={ws_port} auth_required={bool(cfg.auth_required)} password_set={bool(cfg.server_password)}",
                       **({} if enabled else {"next_command": "Tools -> WebSocket Server Settings -> Enable, then rerun 'ops-obs status'"})})
        reachable = False
        try:
            with socket.create_connection(("127.0.0.1", ws_port), timeout=2):
                reachable = True
        except OSError:
            reachable = False
        if enabled:
            checks.append({"check": "ws_reachable", "status": "ok" if reachable else "fail",
                           "detail": f"127.0.0.1:{ws_port} {'listening' if reachable else 'not listening'}",
                           **({} if reachable else {"next_command": "restart OBS after enabling the websocket server"})})

    gpu = _run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"], timeout=5)
    vaapi = shutil.which("vainfo")
    if gpu:
        checks.append({"check": "gpu_encoder", "status": "ok", "detail": f"NVIDIA: {gpu} — NVENC available"})
    elif vaapi:
        checks.append({"check": "gpu_encoder", "status": "ok", "detail": "vainfo present — VAAPI encoders available"})
    else:
        checks.append({"check": "gpu_encoder", "status": "warn",
                       "detail": "no nvidia-smi, no vainfo; software x264 encoding only",
                       "next_command": "for NVIDIA: install the proprietary driver; for AMD/Intel: install libva-utils and mesa-va-drivers"})

    session = os.environ.get("XDG_SESSION_TYPE", "unknown")
    capture_hint = {"wayland": "use Screen Capture (PipeWire)", "x11": "XSHM is slow; prefer Wayland + PipeWire if possible"}.get(session)
    checks.append({"check": "session_capture", "status": "ok" if session == "wayland" else "warn",
                   "detail": f"XDG_SESSION_TYPE={session}; {capture_hint or 'unknown session'}"})

    target = root or Path.home()
    free_gb = shutil.disk_usage(target).free / 2**30
    checks.append({"check": "disk_free", "status": "crit" if free_gb < DISK_CRIT_GB else "warn" if free_gb < DISK_WARN_GB else "ok",
                   "detail": f"{free_gb:.1f} GB free at {target}"})

    checks.append({"check": "log_scan", "status": "info", "detail": _log_scan(root / "logs" if root else None)})

    findings = [c for c in checks if c["status"] not in ("ok", "info")]
    emit({"ok": True, "ts": datetime.now(UTC).isoformat(), "checks": checks, "findings": len(findings)})


@app.command()
def selftest() -> None:
    """Deterministic protocol regression check: auth vector against the documented algorithm."""
    computed = auth_string(AUTH_VECTOR["password"], AUTH_VECTOR["salt"], AUTH_VECTOR["challenge"])
    match = computed == AUTH_VECTOR["expected"]
    emit({"ok": match, "computed": computed, "expected": AUTH_VECTOR["expected"]})
    if not match:
        raise typer.Exit(1)


def main() -> None:
    """Single failure choke point: typed failures render as JSON, never as a traceback."""
    try:
        app()
    except TypedFailure as e:
        render_failure(e)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
