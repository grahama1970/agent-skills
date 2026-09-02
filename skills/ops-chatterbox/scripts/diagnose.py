#!/usr/bin/env python3
"""diagnose - scripts.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

import typer


app = typer.Typer(no_args_is_help=True)
DEFAULT_HEALTH_URL = "http://127.0.0.1:8018/health"
DEFAULT_SYNTH_URL = "http://127.0.0.1:8018/synthesize-batch"
DEFAULT_CONTAINER = "chatterbox-fork-agent-server"
SECRET_RE = re.compile(r"(token|key|secret|password|credential)", re.I)


def now_ms() -> int:
    return int(time.time() * 1000)


def sha_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


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
        "skill": "ops-chatterbox",
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


def fetch_json(url: str, timeout: float) -> tuple[int | None, Any, str | None, float]:
    started = time.time()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            elapsed = round(time.time() - started, 3)
            try:
                return response.status, json.loads(body), None, elapsed
            except ValueError:
                return response.status, {"raw_text": body[:2000]}, None, elapsed
    except urllib.error.HTTPError as exc:
        elapsed = round(time.time() - started, 3)
        return exc.code, None, f"HTTPError:{exc.code}:{exc.reason}", elapsed
    except Exception as exc:  # noqa: BLE001 - diagnostic receipt must preserve failure class
        elapsed = round(time.time() - started, 3)
        return None, None, f"{type(exc).__name__}:{exc}", elapsed


def run_docker_json(args: list[str], timeout: float = 5.0) -> tuple[Any, str | None]:
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
    for item in env:
        key = item.split("=", 1)[0]
        if SECRET_RE.search(key):
            redacted.append(key)
        else:
            visible.append(key)
    return {"visible_env_keys": sorted(visible), "redacted_env_keys": sorted(redacted)}


@app.command()
def health(
    url: str = typer.Option(DEFAULT_HEALTH_URL, "--url"),
    timeout: float = typer.Option(3.0, "--timeout"),
    out: Optional[Path] = typer.Option(None, "--out"),
    strict: bool = typer.Option(False, "--strict"),
    as_json: bool = typer.Option(True, "--json/--no-json"),
) -> None:
    receipt = base_receipt("health", "ops_chatterbox.health_receipt.v1", live=True)
    receipt["target_url"] = url
    status_code, payload, error, elapsed = fetch_json(url, timeout)
    receipt["elapsed_seconds"] = elapsed
    receipt["http_status"] = status_code
    receipt["checks"]["http_get"] = error is None and status_code and 200 <= status_code < 300
    if payload is not None:
        receipt["payload"] = payload
        receipt["checks"]["payload_json"] = True
        receipt["checks"]["service_ok"] = bool(payload.get("ok") is True or payload.get("status") in {"ok", "healthy"})
        receipt["checks"]["model_loaded"] = payload.get("model_loaded")
        receipt["checks"]["has_tag_handling"] = isinstance(payload.get("tag_handling"), dict)
        receipt["checks"]["has_voice_delivery_effect"] = isinstance(payload.get("voice_delivery_effect"), dict)
        receipt["engine"] = payload.get("engine")
        receipt["device"] = payload.get("device")
    else:
        receipt["checks"]["payload_json"] = False
    if error:
        receipt["failures"].append(f"health_unreachable:{error}")
        receipt["next_actions"].append("Start or inspect the Chatterbox service, then rerun health.")
    elif not receipt["checks"].get("service_ok"):
        receipt["failures"].append("health_payload_not_ok")
        receipt["next_actions"].append("Inspect the service health payload and container logs.")
    else:
        receipt["status"] = "PASS_CHATTERBOX_HEALTH"
        receipt["ok"] = True
    if not receipt["ok"] and receipt["status"] == "NOT_ESTABLISHED":
        receipt["status"] = "NEEDS_ATTENTION"
    emit(receipt, out=out, strict=strict, as_json=as_json)


@app.command()
def container(
    name: str = typer.Option(DEFAULT_CONTAINER, "--name"),
    out: Optional[Path] = typer.Option(None, "--out"),
    strict: bool = typer.Option(False, "--strict"),
    as_json: bool = typer.Option(True, "--json/--no-json"),
) -> None:
    receipt = base_receipt("container", "ops_chatterbox.container_receipt.v1", live=True)
    receipt["container"] = name
    data, error = run_docker_json(["docker", "inspect", name])
    if error:
        receipt["status"] = "NEEDS_ATTENTION"
        receipt["failures"].append(f"docker_inspect_failed:{error}")
        receipt["next_actions"].append("Check docker availability and the configured Chatterbox container name.")
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
        receipt["status"] = "PASS_CHATTERBOX_CONTAINER"
        receipt["ok"] = True
    else:
        receipt["status"] = "NEEDS_ATTENTION"
        receipt["failures"].append("container_not_running")
        receipt["next_actions"].append("Start the Chatterbox container or update --name.")
    emit(receipt, out=out, strict=strict, as_json=as_json)


@app.command("render-smoke")
def render_smoke(
    live: bool = typer.Option(False, "--live"),
    url: str = typer.Option(DEFAULT_SYNTH_URL, "--url"),
    text: str = typer.Option("Chatterbox smoke test.", "--text"),
    timeout: float = typer.Option(120.0, "--timeout"),
    out: Optional[Path] = typer.Option(None, "--out"),
    strict: bool = typer.Option(False, "--strict"),
    as_json: bool = typer.Option(True, "--json/--no-json"),
) -> None:
    receipt = base_receipt("render-smoke", "ops_chatterbox.render_smoke_receipt.v1", live=live)
    receipt["target_url"] = url
    receipt["text_sha256"] = sha_text(text)
    if not live:
        receipt["status"] = "BLOCKED_LIVE_FLAG_REQUIRED"
        receipt["next_actions"].append("Rerun with --live to call the Chatterbox synth endpoint.")
        emit(receipt, out=out, strict=strict, as_json=as_json)
        return
    payload = {
        "answer_text": text,
        "label": "ops_chatterbox_smoke",
        "use_blessed_qra_cache": False,
        "asr_verify": False,
    }
    started = time.time()
    try:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            response_payload = json.loads(body)
        receipt["elapsed_seconds"] = round(time.time() - started, 3)
        receipt["request_sha256"] = sha_text(json.dumps(payload, sort_keys=True))
        receipt["response"] = response_payload
        audio_ref = response_payload.get("finished_response_audio") or response_payload.get("audio")
        receipt["checks"]["response_json"] = True
        receipt["checks"]["audio_reference_present"] = bool(audio_ref)
        receipt["checks"]["has_render_metadata"] = any(
            isinstance(response_payload.get(key), dict)
            for key in ("affect_effect", "pace_effect", "tag_handling")
        )
        if audio_ref:
            receipt["status"] = "PASS_CHATTERBOX_RENDER_SMOKE"
            receipt["ok"] = True
        else:
            receipt["status"] = "NEEDS_ATTENTION"
            receipt["failures"].append("render_response_missing_audio_reference")
            receipt["next_actions"].append("Inspect the Chatterbox response schema and synth endpoint.")
    except Exception as exc:  # noqa: BLE001
        receipt["elapsed_seconds"] = round(time.time() - started, 3)
        receipt["status"] = "NEEDS_ATTENTION"
        receipt["failures"].append(f"render_smoke_failed:{type(exc).__name__}:{exc}")
        receipt["next_actions"].append("Check endpoint, model load, GPU memory, and container logs.")
    emit(receipt, out=out, strict=strict, as_json=as_json)


@app.command()
def assess(
    path: Path,
    out: Optional[Path] = typer.Option(None, "--out"),
    strict: bool = typer.Option(False, "--strict"),
    as_json: bool = typer.Option(True, "--json/--no-json"),
) -> None:
    receipt = base_receipt("assess", "ops_chatterbox.assess_receipt.v1", live=False)
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
        ("tag_echo_as_proof", r"tags_interpreted", "warning", "Do not treat tag_handling.tags_interpreted alone as acoustic proof; require ASR or per-render effect evidence."),
        ("raw_paralinguistic_tag", r"\[(laugh|chuckle|sigh|gasp|whispering|clear throat|cough|groan|sniff|shush)\]", "warning", "Normalize and gate Chatterbox tags; do not pass raw user controls directly."),
    ]
    for name, pattern, severity, message in patterns:
        for match in re.finditer(pattern, text, re.I):
            line = text[: match.start()].count("\n") + 1
            issues.append({"line": line, "pattern": name, "severity": severity, "message": message})
    if "finished_response_audio" in text and "audio_sha256" not in text and "sha_file" not in text:
        line = text.lower().find("finished_response_audio")
        issues.append({
            "line": text[:line].count("\n") + 1 if line >= 0 else 1,
            "pattern": "audio_without_hash",
            "severity": "warning",
            "message": "Copy or hash rendered audio before using it as proof.",
        })
    if "voice_delivery" in text and not any(marker in text for marker in ("affect_effect", "pace_effect", "tag_handling", "transcript", "asr")):
        line = text.find("voice_delivery")
        issues.append({
            "line": text[:line].count("\n") + 1 if line >= 0 else 1,
            "pattern": "voice_delivery_without_effect_readback",
            "severity": "warning",
            "message": "Read back affect_effect, pace_effect, tag_handling, or transcript evidence for voice_delivery claims.",
        })
    if "answer_text" in text and "tts_render_text" not in text:
        issues.append({
            "line": 1,
            "pattern": "answer_text_without_tts_render_text",
            "severity": "warning",
            "message": "Keep canonical answer_text separate from tts_render_text when adding render-only cues.",
        })
    receipt["issues"] = issues
    receipt["checks"]["target_file_read"] = True
    receipt["checks"]["issue_count"] = len(issues)
    if issues:
        receipt["status"] = "NEEDS_ATTENTION"
        receipt["failures"].append("usage_assessment_found_issues")
        receipt["next_actions"].append("Review issues and add receipt-backed render/audio gates.")
    else:
        receipt["status"] = "PASS_CHATTERBOX_USAGE_ASSESSMENT"
        receipt["ok"] = True
    emit(receipt, out=out, strict=strict, as_json=as_json)


@app.command()
def doctor(
    health_url: str = typer.Option(DEFAULT_HEALTH_URL, "--health-url"),
    container_name: str = typer.Option(DEFAULT_CONTAINER, "--container"),
    timeout: float = typer.Option(3.0, "--timeout"),
    out: Optional[Path] = typer.Option(None, "--out"),
    strict: bool = typer.Option(False, "--strict"),
    as_json: bool = typer.Option(True, "--json/--no-json"),
) -> None:
    receipt = base_receipt("doctor", "ops_chatterbox.doctor_receipt.v1", live=True)
    status_code, payload, error, elapsed = fetch_json(health_url, timeout)
    receipt["health"] = {"url": health_url, "http_status": status_code, "elapsed_seconds": elapsed, "payload": payload, "error": error}
    receipt["checks"]["health_ok"] = error is None and isinstance(payload, dict) and bool(payload.get("ok") is True or payload.get("status") in {"ok", "healthy"})
    data, docker_error = run_docker_json(["docker", "inspect", container_name])
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
        receipt["status"] = "PASS_CHATTERBOX_DOCTOR"
        receipt["ok"] = True
    emit(receipt, out=out, strict=strict, as_json=as_json)


if __name__ == "__main__":
    app()
