"""ops-obs protocol layer: obs-websocket v5 client, typed models, local config, health.

Inputs: OBS config files, environment (OBS_WS_HOST/PORT/PASSWORD), a
websocket connection to OBS.
Outputs: ObsClient (request/response as validated dicts), typed failure
envelopes (TypedFailure), health findings.
Failure modes: TypedFailure with a FailureCode — callers render it; never
swallow, never a bare generic error.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import websocket
from dotenv import load_dotenv
from loguru import logger
from pydantic import BaseModel, ConfigDict, ValidationError

load_dotenv()

# ---------------------------------------------------------------- constants

FLATPAK_ROOT = Path.home() / ".var/app/com.obsproject.Studio/config/obs-studio"
NATIVE_ROOT = Path.home() / ".config/obs-studio"
DEFAULT_PORT = 4455

# Health thresholds (fractions of total frames).
RENDER_SKIP_WARN, RENDER_SKIP_CRIT = 0.05, 0.10
OUTPUT_SKIP_WARN, OUTPUT_SKIP_CRIT = 0.01, 0.05
CONGESTION_WARN = 0.05
DISK_WARN_GB, DISK_CRIT_GB = 5.0, 1.0

HINTS = {
    "render_lag": "Reduce composite complexity (fewer sources/filters); on X11 prefer Wayland + PipeWire capture over XSHM.",
    "encode_lag": "Encoding lag: lower output resolution/fps or bitrate, or switch to a hardware encoder (NVENC on NVIDIA, VAAPI on AMD/Intel).",
    "congestion": "Network congestion: stream bitrate exceeds available upload; lower bitrate or fix the network path.",
    "disk_low": "Free disk space is low for recordings; move or clean the recording target.",
    "encoder_stalled": "Active output reports 0 fps; encoder may have stalled — check `ops-obs doctor` GPU and log checks.",
    "reconnecting": "Stream is reconnecting; check network stability.",
}

# Fixed protocol regression vector (password/salt/challenge -> auth string).
AUTH_VECTOR = {
    "password": "testpass",
    "salt": "testsalt",
    "challenge": "testchallenge",
    "expected": "DH8rJzw8w3csbWfcnTbO18+zOu0c+LSevHghwA2BbW0=",
}


class FailureCode(StrEnum):
    CONNECTION_REFUSED = "obs_ws_connection_refused"
    TIMEOUT = "obs_ws_timeout"
    AUTH_REQUIRED = "obs_ws_password_required"
    AUTH_FAILED = "obs_ws_auth_failed"
    SERVER_DISABLED = "obs_ws_server_disabled"
    REQUEST_FAILED = "obs_ws_request_failed"
    PROTOCOL = "obs_ws_protocol_error"


class TypedFailure(Exception):
    """Typed failure envelope raised at any seam; main() renders it, never a traceback."""

    def __init__(self, code: FailureCode, cause: str, next_command: str):
        self.code = code
        self.cause = cause
        self.next_command = next_command
        super().__init__(f"{code.value}: {cause}")


def fail(code: FailureCode, cause: str, next_command: str) -> None:
    """Raise a typed failure; main() emits {ok, code, cause, next_command} and exits 1."""
    raise TypedFailure(code, cause, next_command)


def render_failure(exc: TypedFailure) -> None:
    logger.error("ops-obs failure {}: {}", exc.code.value, exc.cause)
    emit(
        {
            "ok": False,
            "code": exc.code.value,
            "cause": exc.cause,
            "next_command": exc.next_command,
            "ts": datetime.now(UTC).isoformat(),
        }
    )


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, default=str))


# ------------------------------------------------------------ typed seams
# Every websocket message and every subprocess/config read is validated
# through a pydantic model at this boundary before business logic sees it.


class Authentication(BaseModel):
    challenge: str
    salt: str


class HelloData(BaseModel):
    model_config = ConfigDict(extra="allow")
    obsWebSocketVersion: str
    rpcVersion: int
    authentication: Authentication | None = None


class WsInbound(BaseModel):
    op: int
    d: dict[str, Any] = {}


class RequestStatusM(BaseModel):
    result: bool
    code: int
    comment: str | None = None


class RequestResponseD(BaseModel):
    requestType: str
    requestId: str
    requestStatus: RequestStatusM
    responseData: dict[str, Any] = {}


class VersionData(BaseModel):
    model_config = ConfigDict(extra="allow")
    obsVersion: str
    obsWebSocketVersion: str
    rpcVersion: int
    platform: str | None = None
    platformDescription: str | None = None


class StatsData(BaseModel):
    model_config = ConfigDict(extra="allow")
    cpuUsage: float
    memoryUsage: float
    availableDiskSpace: float
    activeFps: float
    averageFrameRenderTime: float
    renderSkippedFrames: int
    renderTotalFrames: int
    outputSkippedFrames: int
    outputTotalFrames: int


class OutputStatusData(BaseModel):
    model_config = ConfigDict(extra="allow")
    outputActive: bool
    outputReconnecting: bool | None = None
    outputTimecode: str | None = None
    outputDuration: float | None = None
    outputCongestion: float | None = None
    outputBytes: int | None = None
    outputSkippedFrames: int | None = None
    outputTotalFrames: int | None = None


class RecordStatusData(BaseModel):
    model_config = ConfigDict(extra="allow")
    outputActive: bool
    outputPaused: bool
    outputTimecode: str | None = None
    outputDuration: float | None = None
    outputBytes: int | None = None


class SceneEntry(BaseModel):
    sceneName: str
    sceneUuid: str | None = None


class SceneListData(BaseModel):
    model_config = ConfigDict(extra="allow")
    currentProgramSceneName: str
    scenes: list[SceneEntry]


class WsConfig(BaseModel):
    """Parsed plugin_config/obs-websocket/basic.json (server_password never surfaced)."""

    model_config = ConfigDict(extra="allow")
    server_enabled: bool | None = None
    server_port: int | None = None
    auth_required: bool | None = None
    server_password: str | None = None


class ObsRequestError(Exception):
    """A RequestResponse with result=false. Callers decide fail vs tolerate."""

    def __init__(self, request_type: str, code: int, comment: str | None):
        self.request_type = request_type
        self.code = code
        self.comment = comment
        super().__init__(f"{request_type} failed: code={code} comment={comment}")


# ------------------------------------------------------------ local config


def detect_config_root() -> tuple[str | None, Path | None]:
    if (FLATPAK_ROOT / "basic").is_dir():
        return "flatpak", FLATPAK_ROOT
    if (NATIVE_ROOT / "basic").is_dir():
        return "native", NATIVE_ROOT
    return None, None


def read_ws_config() -> WsConfig | None:
    _, root = detect_config_root()
    if root is None:
        return None
    path = root / "plugin_config" / "obs-websocket" / "config.json"
    if not path.is_file():
        path = root / "plugin_config" / "obs-websocket" / "basic.json"
    if not path.is_file():
        return None
    try:
        return WsConfig.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        logger.error("could not parse obs-websocket config {}: {}", path, exc)
        return None


def auth_string(password: str, salt: str, challenge: str) -> str:
    """obs-websocket v5 auth: b64(sha256(b64(sha256(password+salt))+challenge))."""
    secret = base64.b64encode(hashlib.sha256((password + salt).encode()).digest()).decode()
    return base64.b64encode(
        hashlib.sha256((secret + challenge).encode()).digest()
    ).decode()


def resolve_conn(
    host: str | None, port: int | None, password: str | None, timeout: float
) -> tuple[str, int, str | None, float]:
    cfg = read_ws_config()
    host = host or os.environ.get("OBS_WS_HOST", "127.0.0.1")
    if port is None:
        port = int(os.environ.get("OBS_WS_PORT", "0")) or (cfg.server_port if cfg and cfg.server_port else DEFAULT_PORT)
    password = password or os.environ.get("OBS_WS_PASSWORD")
    if not password and cfg and cfg.server_password:
        password = cfg.server_password  # OBS stores it here in plaintext already
    return host, port, password, timeout


# --------------------------------------------------------------- client


class ObsClient:
    """Minimal obs-websocket v5 client: handshake + fire-one request."""

    def __init__(self, host: str, port: int, password: str | None, timeout: float):
        self.url = f"ws://{host}:{port}"
        self.password = password
        self.timeout = timeout
        self.ws: Any = None

    def connect(self) -> None:
        cfg = read_ws_config()
        localhost = self.url.startswith("ws://127.0.0.1") or self.url.startswith("ws://localhost")
        configured_port = cfg.server_port if cfg else None
        try:
            self.ws = websocket.create_connection(self.url, timeout=self.timeout)
        except (ConnectionRefusedError, OSError) as exc:
            refused = getattr(exc, "errno", None) in (None, 111) or isinstance(exc, ConnectionRefusedError)
            if (
                refused
                and localhost
                and cfg is not None
                and cfg.server_enabled is False
                and configured_port
                and int(self.url.rsplit(":", 1)[1]) == configured_port
            ):
                fail(
                    FailureCode.SERVER_DISABLED,
                    "obs-websocket server is disabled in OBS config while OBS port is not listening",
                    "In OBS: Tools -> WebSocket Server Settings -> Enable, then rerun ops-obs status",
                )
            if refused:
                fail(
                    FailureCode.CONNECTION_REFUSED,
                    f"no obs-websocket server at {self.url}",
                    "start OBS and enable Tools -> WebSocket Server Settings, or pass --host/--port",
                )
            fail(FailureCode.PROTOCOL, f"cannot connect to {self.url}: {exc}", "check host/port and network")
        except websocket.WebSocketTimeoutException:
            fail(FailureCode.TIMEOUT, f"connect timeout to {self.url}", "is OBS running? increase --timeout")
        self._handshake()

    def _handshake(self) -> None:
        authed = False
        try:
            hello = WsInbound.model_validate_json(self.ws.recv())
            if hello.op != 0:
                fail(FailureCode.PROTOCOL, f"expected Hello (op 0), got op {hello.op}", "check obs-websocket version >= 5.0")
            hello_d = HelloData.model_validate(hello.d)
            identify: dict[str, Any] = {"rpcVersion": 1, "eventSubscriptions": 0}
            if hello_d.authentication is not None:
                if not self.password:
                    fail(
                        FailureCode.AUTH_REQUIRED,
                        "server requires a websocket password and none was found",
                        "set OBS_WS_PASSWORD, pass --password, or store it in OBS WebSocket Server Settings",
                    )
                authed = True
                identify["authentication"] = auth_string(
                    self.password, hello_d.authentication.salt, hello_d.authentication.challenge
                )
            self.ws.send(json.dumps({"op": 1, "d": identify}))
            while True:
                msg = WsInbound.model_validate_json(self.ws.recv())
                if msg.op == 2:
                    break
                if msg.op == 5:
                    continue
                fail(FailureCode.PROTOCOL, f"unexpected op {msg.op} during handshake", "check obs-websocket version >= 5.0")
        except websocket.WebSocketTimeoutException:
            fail(FailureCode.TIMEOUT, "timeout during websocket handshake", "increase --timeout or restart OBS")
        except (websocket.WebSocketException, OSError) as exc:
            if authed:
                fail(FailureCode.AUTH_FAILED, f"handshake rejected: {exc}", "verify the websocket password in OBS WebSocket Server Settings")
            fail(FailureCode.PROTOCOL, f"handshake error: {exc}", "check obs-websocket version >= 5.0")
        except ValidationError as exc:
            fail(FailureCode.PROTOCOL, f"malformed handshake message: {exc.error_count()} errors", "check obs-websocket version >= 5.0")

    def request(self, request_type: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        rid = uuid.uuid4().hex[:8]
        payload: dict[str, Any] = {"op": 6, "d": {"requestType": request_type, "requestId": rid}}
        if data is not None:
            payload["d"]["requestData"] = data
        try:
            self.ws.send(json.dumps(payload))
            while True:
                msg = WsInbound.model_validate_json(self.ws.recv())
                if msg.op != 7:
                    continue
                rd = RequestResponseD.model_validate(msg.d)
                if rd.requestId != rid:
                    continue
                if not rd.requestStatus.result:
                    raise ObsRequestError(request_type, rd.requestStatus.code, rd.requestStatus.comment)
                return rd.responseData
        except websocket.WebSocketTimeoutException:
            fail(FailureCode.TIMEOUT, f"timeout waiting for {request_type}", "increase --timeout or restart OBS")
        except (websocket.WebSocketException, OSError) as exc:
            fail(FailureCode.PROTOCOL, f"connection error during {request_type}: {exc}", "reconnect: rerun the command")

    def close(self) -> None:
        if self.ws is not None:
            try:
                self.ws.close()
            except (websocket.WebSocketException, OSError) as exc:
                logger.error("error closing websocket: {}", exc)


# --------------------------------------------------------------- health


def _ratio(num: int | None, den: int | None) -> float:
    if not num or not den:
        return 0.0
    return num / den


def evaluate_health(
    stats: StatsData, stream: OutputStatusData | None, record: RecordStatusData | None
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    def add(name: str, sev: str, detail: str, hint: str | None = None) -> None:
        findings.append({"check": name, "status": sev, "detail": detail, "hint": hint})

    rs = _ratio(stats.renderSkippedFrames, stats.renderTotalFrames)
    sev = "crit" if rs >= RENDER_SKIP_CRIT else "warn" if rs >= RENDER_SKIP_WARN else "ok"
    add("render_lag", sev, f"render skipped {rs:.1%} ({stats.renderSkippedFrames}/{stats.renderTotalFrames})", HINTS["render_lag"] if sev != "ok" else None)

    osk = _ratio(stats.outputSkippedFrames, stats.outputTotalFrames)
    sev = "crit" if osk >= OUTPUT_SKIP_CRIT else "warn" if osk >= OUTPUT_SKIP_WARN else "ok"
    add("encode_lag", sev, f"output skipped {osk:.1%} ({stats.outputSkippedFrames}/{stats.outputTotalFrames})", HINTS["encode_lag"] if sev != "ok" else None)

    cong = stream.outputCongestion if stream else None
    sev = "warn" if (cong or 0) >= CONGESTION_WARN else "ok"
    add("congestion", sev, f"stream congestion {cong if cong is not None else 'n/a'}", HINTS["congestion"] if sev != "ok" else None)

    if (stats.availableDiskSpace or 0) < DISK_CRIT_GB:
        add("disk_low", "crit", f"{stats.availableDiskSpace:.1f} GB free", HINTS["disk_low"])
    elif (stats.availableDiskSpace or 0) < DISK_WARN_GB:
        add("disk_low", "warn", f"{stats.availableDiskSpace:.1f} GB free", HINTS["disk_low"])
    else:
        add("disk_low", "ok", f"{stats.availableDiskSpace:.1f} GB free")

    output_active = (stream and stream.outputActive) or (record and record.outputActive)
    if output_active and stats.activeFps <= 0:
        add("encoder_stalled", "crit", "active output but 0 fps", HINTS["encoder_stalled"])
    else:
        add("encoder_stalled", "ok", f"active fps {stats.activeFps}")

    if stream and stream.outputReconnecting:
        add("reconnecting", "warn", "stream reconnecting", HINTS["reconnecting"])
    return findings
