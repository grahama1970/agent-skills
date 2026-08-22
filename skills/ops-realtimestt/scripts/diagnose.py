#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

import typer


app = typer.Typer(no_args_is_help=True)
DEFAULT_URL = "http://127.0.0.1:9000"
DEFAULT_CONTAINER = "whisper"
SECRET_RE = re.compile(r"(token|key|secret|password|credential|authorization)", re.I)


def now_ms() -> int:
    return int(time.time() * 1000)


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def emit(receipt: dict[str, Any], *, out: Optional[Path], strict: bool, as_json: bool) -> None:
    text = json.dumps(receipt, indent=2, sort_keys=True)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    if as_json or not out:
        typer.echo(text)
    if strict and not receipt.get("ok"):
        raise typer.Exit(1)


def base_receipt(command: str, schema: str, *, live: bool) -> dict[str, Any]:
    return {
        "schema": schema,
        "skill": "ops-realtimestt",
        "command": command,
        "status": "NOT_ESTABLISHED",
        "ok": False,
        "live": live,
        "mocked": False,
        "checks": {},
        "failures": [],
        "next_actions": [],
        "created_at_ms": now_ms(),
    }


def fetch_json(url: str, timeout: float, headers: Optional[dict[str, str]] = None) -> tuple[int | None, Any, str | None, float]:
    started = time.time()
    try:
        request = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            elapsed = round(time.time() - started, 3)
            try:
                return response.status, json.loads(body), None, elapsed
            except ValueError:
                return response.status, {"raw_text": body[:2000]}, None, elapsed
    except urllib.error.HTTPError as exc:
        elapsed = round(time.time() - started, 3)
        body = exc.read().decode("utf-8", errors="replace")[:1000] if hasattr(exc, "read") else ""
        return exc.code, {"raw_text": body}, f"HTTPError:{exc.code}:{exc.reason}", elapsed
    except Exception as exc:  # noqa: BLE001
        elapsed = round(time.time() - started, 3)
        return None, None, f"{type(exc).__name__}:{exc}", elapsed


def run_json(args: list[str], timeout: float = 5.0) -> tuple[Any, str | None]:
    try:
        done = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}:{exc}"
    if done.returncode != 0:
        return None, (done.stderr or done.stdout).strip()[:1000]
    try:
        return json.loads(done.stdout), None
    except ValueError as exc:
        return None, f"json_parse_error:{exc}"


def redact_env(env: list[str]) -> dict[str, Any]:
    visible: list[str] = []
    redacted: list[str] = []
    selected_values: dict[str, str] = {}
    allowed_values = {"CUDA_VERSION", "NV_CUDNN_VERSION", "WHISPER_MODEL", "WHISPER_DEVICE", "WHISPER_COMPUTE_TYPE"}
    for item in env:
        key, _, value = item.partition("=")
        if SECRET_RE.search(key):
            redacted.append(key)
        else:
            visible.append(key)
            if key in allowed_values:
                selected_values[key] = value
    return {"visible_env_keys": sorted(visible), "redacted_env_keys": sorted(redacted), "selected_values": selected_values}


def classify_service(health_payload: Any, openapi_payload: Any) -> str:
    if isinstance(health_payload, dict) and str(health_payload.get("schema", "")).startswith("embry.realtimestt"):
        return "embry_realtimestt_runtime"
    if isinstance(openapi_payload, dict):
        paths = set((openapi_payload.get("paths") or {}).keys())
        title = str((openapi_payload.get("info") or {}).get("title") or "").lower()
        if "/v1/audio/transcriptions" in paths or "whisper" in title:
            return "whisper_openai_compatible"
    if isinstance(health_payload, dict) and health_payload.get("model") and health_payload.get("status") == "ok":
        return "whisper_openai_compatible"
    return "unknown_stt_service"


@app.command()
def health(
    url: str = typer.Option(DEFAULT_URL, "--url"),
    timeout: float = typer.Option(3.0, "--timeout"),
    out: Optional[Path] = typer.Option(None, "--out"),
    strict: bool = typer.Option(False, "--strict"),
    as_json: bool = typer.Option(True, "--json/--no-json"),
) -> None:
    receipt = base_receipt("health", "ops_realtimestt.health_receipt.v1", live=True)
    base = url.rstrip("/")
    receipt["base_url"] = base
    health_status, health_payload, health_error, health_elapsed = fetch_json(f"{base}/health", timeout)
    readiness_status, readiness_payload, readiness_error, readiness_elapsed = fetch_json(f"{base}/readiness", timeout)
    openapi_status, openapi_payload, openapi_error, openapi_elapsed = fetch_json(f"{base}/openapi.json", timeout)
    models_status, _models_payload, models_error, models_elapsed = fetch_json(f"{base}/v1/models", timeout)
    receipt["probes"] = {
        "health": {"status": health_status, "payload": health_payload, "error": health_error, "elapsed_seconds": health_elapsed},
        "readiness": {"status": readiness_status, "payload": readiness_payload, "error": readiness_error, "elapsed_seconds": readiness_elapsed},
        "openapi": {"status": openapi_status, "payload": openapi_payload, "error": openapi_error, "elapsed_seconds": openapi_elapsed},
        "models_auth_probe": {"status": models_status, "error": models_error, "elapsed_seconds": models_elapsed},
    }
    service_kind = classify_service(health_payload, openapi_payload)
    receipt["service_kind"] = service_kind
    receipt["checks"]["health_public_ok"] = health_error is None and health_status and 200 <= health_status < 300
    receipt["checks"]["readiness_ok"] = readiness_error is None and readiness_status and 200 <= readiness_status < 300
    receipt["checks"]["openapi_transcription_path"] = isinstance(openapi_payload, dict) and "/v1/audio/transcriptions" in set((openapi_payload.get("paths") or {}).keys())
    receipt["checks"]["models_endpoint_auth_required"] = models_status in {401, 403}
    if not receipt["checks"]["health_public_ok"]:
        receipt["failures"].append("health_endpoint_not_ok")
    if service_kind == "embry_realtimestt_runtime" and not receipt["checks"]["readiness_ok"]:
        receipt["failures"].append("embry_readiness_not_ok")
    if service_kind == "unknown_stt_service":
        receipt["failures"].append("unknown_stt_service_shape")
    if receipt["failures"]:
        receipt["status"] = "NEEDS_ATTENTION"
        receipt["next_actions"].append("Inspect STT service URL, readiness endpoint, auth requirements, and container logs.")
    else:
        receipt["status"] = "PASS_STT_HEALTH"
        receipt["ok"] = True
    emit(receipt, out=out, strict=strict, as_json=as_json)


@app.command()
def container(
    name: str = typer.Option(DEFAULT_CONTAINER, "--name"),
    out: Optional[Path] = typer.Option(None, "--out"),
    strict: bool = typer.Option(False, "--strict"),
    as_json: bool = typer.Option(True, "--json/--no-json"),
) -> None:
    receipt = base_receipt("container", "ops_realtimestt.container_receipt.v1", live=True)
    receipt["container"] = name
    data, error = run_json(["docker", "inspect", name])
    if error:
        receipt["status"] = "NEEDS_ATTENTION"
        receipt["failures"].append(f"docker_inspect_failed:{error}")
        receipt["next_actions"].append("Check docker availability and the configured STT container name.")
        emit(receipt, out=out, strict=strict, as_json=as_json)
        return
    item = data[0]
    state = item.get("State") or {}
    config = item.get("Config") or {}
    receipt["image"] = config.get("Image")
    receipt["state"] = {
        "status": state.get("Status"),
        "running": state.get("Running"),
        "health": state.get("Health", {}).get("Status") if isinstance(state.get("Health"), dict) else None,
    }
    receipt["ports"] = (item.get("HostConfig") or {}).get("PortBindings")
    receipt["env"] = redact_env(config.get("Env") or [])
    receipt["checks"]["docker_inspect"] = True
    receipt["checks"]["running"] = bool(state.get("Running"))
    if state.get("Running"):
        receipt["status"] = "PASS_STT_CONTAINER"
        receipt["ok"] = True
    else:
        receipt["status"] = "NEEDS_ATTENTION"
        receipt["failures"].append("container_not_running")
        receipt["next_actions"].append("Start the STT container or update --name.")
    emit(receipt, out=out, strict=strict, as_json=as_json)


@app.command()
def cuda(
    name: str = typer.Option(DEFAULT_CONTAINER, "--name"),
    out: Optional[Path] = typer.Option(None, "--out"),
    strict: bool = typer.Option(False, "--strict"),
    as_json: bool = typer.Option(True, "--json/--no-json"),
) -> None:
    receipt = base_receipt("cuda", "ops_realtimestt.cuda_receipt.v1", live=True)
    data, error = run_json(["docker", "inspect", name])
    receipt["container"] = name
    if error:
        receipt["status"] = "NEEDS_ATTENTION"
        receipt["failures"].append(f"docker_inspect_failed:{error}")
        receipt["next_actions"].append("Check docker availability and the configured STT container name.")
        emit(receipt, out=out, strict=strict, as_json=as_json)
        return
    env = redact_env((data[0].get("Config") or {}).get("Env") or [])
    receipt["env"] = env
    selected = env.get("selected_values") or {}
    receipt["checks"]["cuda_version_declared"] = bool(selected.get("CUDA_VERSION"))
    receipt["checks"]["cudnn_version_declared"] = bool(selected.get("NV_CUDNN_VERSION"))
    receipt["checks"]["whisper_device_cuda"] = selected.get("WHISPER_DEVICE") == "cuda"
    smi = subprocess.run(["docker", "exec", name, "nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"], capture_output=True, text=True, timeout=10, check=False)
    receipt["nvidia_smi"] = {"exit_code": smi.returncode, "stdout": smi.stdout.strip()[:1000], "stderr": smi.stderr.strip()[:1000]}
    receipt["checks"]["nvidia_smi_ok"] = smi.returncode == 0
    if all(receipt["checks"].values()):
        receipt["status"] = "PASS_STT_CUDA_ENV"
        receipt["ok"] = True
    else:
        receipt["status"] = "NEEDS_ATTENTION"
        receipt["failures"] = [name for name, passed in receipt["checks"].items() if not passed]
        receipt["next_actions"].append("Inspect CUDA/cuDNN package compatibility, GPU visibility, and STT container logs.")
    emit(receipt, out=out, strict=strict, as_json=as_json)


@app.command("websocket-probe")
def websocket_probe(
    live: bool = typer.Option(False, "--live"),
    control: str = typer.Option("ws://127.0.0.1:8011", "--control"),
    data: str = typer.Option("ws://127.0.0.1:8012", "--data"),
    timeout: float = typer.Option(2.0, "--timeout"),
    out: Optional[Path] = typer.Option(None, "--out"),
    strict: bool = typer.Option(False, "--strict"),
    as_json: bool = typer.Option(True, "--json/--no-json"),
) -> None:
    receipt = base_receipt("websocket-probe", "ops_realtimestt.websocket_probe_receipt.v1", live=live)
    receipt["targets"] = {"control": control, "data": data}
    if not live:
        receipt["status"] = "BLOCKED_LIVE_FLAG_REQUIRED"
        receipt["next_actions"].append("Rerun with --live to open TCP probes to the configured WebSocket ports.")
        emit(receipt, out=out, strict=strict, as_json=as_json)
        return
    failures: list[str] = []
    for key, target in (("control", control), ("data", data)):
        match = re.match(r"wss?://([^/:]+):(\d+)", target)
        if not match:
            receipt["checks"][f"{key}_target_parse"] = False
            failures.append(f"{key}_target_parse")
            continue
        host, port = match.group(1), int(match.group(2))
        try:
            with socket.create_connection((host, port), timeout=timeout):
                receipt["checks"][f"{key}_tcp_open"] = True
        except OSError as exc:
            receipt["checks"][f"{key}_tcp_open"] = False
            failures.append(f"{key}_tcp_open:{type(exc).__name__}:{exc}")
    if failures:
        receipt["status"] = "NEEDS_ATTENTION"
        receipt["failures"] = failures
        receipt["next_actions"].append("Start the legacy RealtimeSTT WebSocket server or correct control/data ports.")
    else:
        receipt["status"] = "PASS_STT_WEBSOCKET_PORTS"
        receipt["ok"] = True
    emit(receipt, out=out, strict=strict, as_json=as_json)


@app.command("transcribe-smoke")
def transcribe_smoke(
    live: bool = typer.Option(False, "--live"),
    url: str = typer.Option(f"{DEFAULT_URL}/v1/audio/transcriptions", "--url"),
    audio: Path = typer.Option(..., "--audio"),
    api_key_env: str = typer.Option("WHISPER_API_KEY", "--api-key-env"),
    timeout: float = typer.Option(120.0, "--timeout"),
    out: Optional[Path] = typer.Option(None, "--out"),
    strict: bool = typer.Option(False, "--strict"),
    as_json: bool = typer.Option(True, "--json/--no-json"),
) -> None:
    receipt = base_receipt("transcribe-smoke", "ops_realtimestt.transcribe_smoke_receipt.v1", live=live)
    receipt["target_url"] = url
    receipt["audio"] = str(audio)
    if not live:
        receipt["status"] = "BLOCKED_LIVE_FLAG_REQUIRED"
        receipt["next_actions"].append("Rerun with --live and a known WAV to call the ASR endpoint.")
        emit(receipt, out=out, strict=strict, as_json=as_json)
        return
    if not audio.is_file():
        receipt["status"] = "NEEDS_ATTENTION"
        receipt["failures"].append("audio_file_missing")
        receipt["next_actions"].append("Pass a readable WAV file to --audio.")
        emit(receipt, out=out, strict=strict, as_json=as_json)
        return
    api_key = os.environ.get(api_key_env)
    if not api_key:
        receipt["status"] = "BLOCKED_API_KEY_REQUIRED"
        receipt["audio_sha256"] = sha_file(audio)
        receipt["next_actions"].append(f"Set {api_key_env} or choose another explicit API key env var.")
        emit(receipt, out=out, strict=strict, as_json=as_json)
        return
    cmd = [
        "curl",
        "-fsS",
        "--max-time",
        str(int(timeout)),
        "-H",
        f"Authorization: Bearer {api_key}",
        "-F",
        f"file=@{audio}",
        "-F",
        "model=base",
        url,
    ]
    started = time.time()
    done = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5, check=False)
    receipt["elapsed_seconds"] = round(time.time() - started, 3)
    receipt["audio_sha256"] = sha_file(audio)
    receipt["curl_exit_code"] = done.returncode
    if done.returncode != 0:
        receipt["status"] = "NEEDS_ATTENTION"
        receipt["failures"].append(f"transcription_request_failed:{done.stderr.strip()[:500]}")
        receipt["next_actions"].append("Check ASR endpoint auth, model load, CUDA logs, and audio format.")
    else:
        try:
            payload = json.loads(done.stdout)
        except ValueError:
            payload = {"raw_text": done.stdout[:1000]}
        receipt["response"] = payload
        transcript = str(payload.get("text") or payload.get("transcript") or "")
        receipt["checks"]["transcript_non_empty"] = bool(transcript.strip())
        if transcript.strip():
            receipt["status"] = "PASS_STT_TRANSCRIBE_SMOKE"
            receipt["ok"] = True
        else:
            receipt["status"] = "NEEDS_ATTENTION"
            receipt["failures"].append("transcript_empty")
            receipt["next_actions"].append("Inspect ASR response schema and audio content.")
    emit(receipt, out=out, strict=strict, as_json=as_json)


@app.command()
def assess(
    path: Path,
    out: Optional[Path] = typer.Option(None, "--out"),
    strict: bool = typer.Option(False, "--strict"),
    as_json: bool = typer.Option(True, "--json/--no-json"),
) -> None:
    receipt = base_receipt("assess", "ops_realtimestt.assess_receipt.v1", live=False)
    receipt["target_file"] = str(path)
    if not path.is_file():
        receipt["status"] = "NEEDS_ATTENTION"
        receipt["failures"].append("target_file_missing")
        receipt["next_actions"].append("Pass a readable source file to assess.")
        emit(receipt, out=out, strict=strict, as_json=as_json)
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    issues: list[dict[str, Any]] = []
    patterns = [
        ("models_without_auth", r"/v1/models", "warning", "The models endpoint may require Authorization even when /health is public."),
        ("transcript_as_identity", r"(speaker|user)\s*=\s*(transcript|transcript_text|asr_text)", "error", "ASR transcript text is not speaker identity; use speaker-resolution evidence."),
        ("health_without_readiness", r"/health", "warning", "For Embry RealtimeSTT runtime, check /readiness before claiming listener readiness."),
        ("live_transcription_without_hash", r"/v1/audio/transcriptions", "warning", "Preserve audio hash, request, response, and transcript readback for live ASR claims."),
    ]
    for name, pattern, severity, message in patterns:
        for match in re.finditer(pattern, text, re.I):
            line = text[: match.start()].count("\n") + 1
            issues.append({"line": line, "pattern": name, "severity": severity, "message": message})
    if re.search(r"whisper", text, re.I) and re.search(r"RealtimeSTT", text) and "service_kind" not in text:
        issues.append({
            "line": 1,
            "pattern": "whisper_realtimestt_conflation",
            "severity": "warning",
            "message": "Classify Whisper-compatible ASR separately from Embry RealtimeSTT listener readiness.",
        })
    receipt["issues"] = issues
    receipt["checks"]["target_file_read"] = True
    receipt["checks"]["issue_count"] = len(issues)
    if any(issue["severity"] == "error" for issue in issues):
        receipt["status"] = "NEEDS_ATTENTION"
        receipt["failures"].append("usage_assessment_found_errors")
        receipt["next_actions"].append("Fix error-severity STT misuse before relying on this caller.")
    elif issues:
        receipt["status"] = "NEEDS_ATTENTION"
        receipt["failures"].append("usage_assessment_found_warnings")
        receipt["next_actions"].append("Review warnings and add readiness/auth/hash gates where applicable.")
    else:
        receipt["status"] = "PASS_STT_USAGE_ASSESSMENT"
        receipt["ok"] = True
    emit(receipt, out=out, strict=strict, as_json=as_json)


@app.command()
def doctor(
    url: str = typer.Option(DEFAULT_URL, "--url"),
    container_name: str = typer.Option(DEFAULT_CONTAINER, "--container"),
    timeout: float = typer.Option(3.0, "--timeout"),
    out: Optional[Path] = typer.Option(None, "--out"),
    strict: bool = typer.Option(False, "--strict"),
    as_json: bool = typer.Option(True, "--json/--no-json"),
) -> None:
    receipt = base_receipt("doctor", "ops_realtimestt.doctor_receipt.v1", live=True)
    base = url.rstrip("/")
    health_status, health_payload, health_error, health_elapsed = fetch_json(f"{base}/health", timeout)
    openapi_status, openapi_payload, openapi_error, openapi_elapsed = fetch_json(f"{base}/openapi.json", timeout)
    receipt["health"] = {"status": health_status, "payload": health_payload, "error": health_error, "elapsed_seconds": health_elapsed}
    receipt["openapi"] = {"status": openapi_status, "payload": openapi_payload, "error": openapi_error, "elapsed_seconds": openapi_elapsed}
    receipt["service_kind"] = classify_service(health_payload, openapi_payload)
    receipt["checks"]["health_ok"] = health_error is None and health_status and 200 <= health_status < 300
    data, docker_error = run_json(["docker", "inspect", container_name])
    if docker_error:
        receipt["container"] = {"name": container_name, "error": docker_error}
        receipt["checks"]["container_running"] = False
    else:
        item = data[0]
        state = item.get("State") or {}
        config = item.get("Config") or {}
        receipt["container"] = {
            "name": container_name,
            "image": config.get("Image"),
            "state": {"status": state.get("Status"), "running": state.get("Running")},
            "env": redact_env(config.get("Env") or []),
        }
        receipt["checks"]["container_running"] = bool(state.get("Running"))
    if not receipt["checks"]["health_ok"]:
        receipt["failures"].append("health_not_ok")
    if not receipt["checks"]["container_running"]:
        receipt["failures"].append("container_not_running_or_unavailable")
    if receipt["failures"]:
        receipt["status"] = "NEEDS_ATTENTION"
        receipt["next_actions"].append("Repair the failing health or container check, then rerun doctor.")
    else:
        receipt["status"] = "PASS_STT_DOCTOR"
        receipt["ok"] = True
    emit(receipt, out=out, strict=strict, as_json=as_json)


if __name__ == "__main__":
    app()
