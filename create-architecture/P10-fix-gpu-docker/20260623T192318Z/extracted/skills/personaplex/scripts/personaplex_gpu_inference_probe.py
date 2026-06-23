#!/usr/bin/env python3
from __future__ import annotations
"""PersonaPlex P10 GPU inference proof probe via Docker container API.

This probe replaces the older local ``personaplex_golden_state_server.py`` /
``LMGen.step(...)`` import path.  PersonaPlex is expected to already be running
in Docker as ``personaplex-personaplex-1`` and serving HTTPS on
``https://127.0.0.1:8998``.

Proof boundary
--------------
``real_gpu_personaplex=true`` is written only when all of these are true:

1. ``docker ps`` shows the expected PersonaPlex container is running.
2. ``GET https://127.0.0.1:8998/`` returns a reachable web/API surface.
3. A bounded HTTP or WebSocket inference request to the container returns
   generated text, audio metadata, token ids, or equivalent generation output.

If any condition is missing, the probe writes a deterministic fallback receipt
with ``real_gpu_personaplex=false``.  Fallback receipts are useful for CI wiring
but must not be cited as live GPU proof.
"""

import argparse
import contextlib
import datetime as _dt
import hashlib
import json
import os
import re
import socket
import ssl
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

try:  # Keep compatibility with the existing PersonaPlex probe helpers.
    from personaplex_p3_p5_live_services import (  # type: ignore
        DEFAULT_SANITY_ROOT,
        body_excerpt,
        utc_now_iso,
        write_json,
    )
except Exception:  # pragma: no cover - used when this file is run standalone.
    DEFAULT_SANITY_ROOT = Path("artifacts/personaplex_sanity")

    def body_excerpt(value: object, limit: int = 4000) -> str:
        text = value if isinstance(value, str) else repr(value)
        text = text.replace("\x00", "")
        return text[:limit]

    def utc_now_iso() -> str:
        return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def write_json(path: str | Path, payload: Mapping[str, Any]) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return p


DEFAULT_CONTAINER_NAME = "personaplex-personaplex-1"
DEFAULT_BASE_URL = "https://127.0.0.1:8998"
DEFAULT_MODEL = "personaplex-7b-v1"
DEFAULT_PROMPT = (
    "You are Embry Lawson. Reply in one short sentence confirming the "
    "PersonaPlex GPU container generated this response."
)

DEFAULT_HTTP_ENDPOINTS = (
    "/api/chat",
    "/api/chat/completions",
    "/v1/chat/completions",
    "/api/v1/chat/completions",
    "/api/generate",
    "/api/completion",
    "/api/completions",
    "/api/personaplex/chat",
)
DEFAULT_WS_ENDPOINTS = (
    "/api/chat",
    "/ws",
    "/api/ws",
    "/api/chat/ws",
    "/api/chat/stream",
)
FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "p8_p9_p10" / "gpu_inference_fallback.json"

_GENERATED_TEXT_KEYS = {
    "answer",
    "audio",
    "audio_url",
    "completion",
    "content",
    "delta",
    "generated_text",
    "message",
    "output",
    "response",
    "text",
    "transcript",
}
_GENERATED_TOKEN_KEYS = {
    "generated_token_id",
    "generated_token_ids",
    "output_token_id",
    "output_token_ids",
    "token",
    "token_id",
    "token_ids",
    "tokens",
}


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _base_to_ws(base_url: str) -> str:
    parsed = urllib.parse.urlsplit(base_url.rstrip("/"))
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urllib.parse.urlunsplit((scheme, parsed.netloc, parsed.path, "", ""))


def _join_url(base_url: str, path_or_url: str) -> str:
    if path_or_url.startswith(("http://", "https://", "ws://", "wss://")):
        return path_or_url
    if not path_or_url.startswith("/"):
        path_or_url = "/" + path_or_url
    return base_url.rstrip("/") + path_or_url


def _json_from_text(text: str) -> Any | None:
    stripped = text.strip()
    if not stripped:
        return None
    with contextlib.suppress(json.JSONDecodeError):
        return json.loads(stripped)

    # Server-sent events / streaming JSON: data: {...}\n\n
    sse_objects: list[Any] = []
    for line in stripped.splitlines():
        line = line.strip()
        if not line or line == "data: [DONE]":
            continue
        if line.startswith("data:"):
            line = line[5:].strip()
        if line.startswith("{") or line.startswith("["):
            with contextlib.suppress(json.JSONDecodeError):
                sse_objects.append(json.loads(line))
    if sse_objects:
        return {"stream_events": sse_objects}

    # Accept the final JSON object printed after logs.
    start = stripped.rfind("{")
    if start >= 0:
        with contextlib.suppress(json.JSONDecodeError):
            return json.loads(stripped[start:])
    return None


def _redacted_headers(headers: Mapping[str, str]) -> dict[str, str]:
    redacted: dict[str, str] = {}
    for key, value in headers.items():
        lowered = key.lower()
        if lowered in {"authorization", "cookie", "set-cookie", "x-api-key"}:
            redacted[key] = "<redacted>"
        else:
            redacted[key] = value
    return redacted


def load_gpu_fixture() -> dict[str, Any]:
    if FIXTURE_PATH.exists():
        return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return {
        "schema": "personaplex.p10.gpu_inference_fallback.v1",
        "real_gpu_personaplex": False,
        "container_inference_observed": False,
        "claim_boundary": "Deterministic fallback is not live GPU PersonaPlex proof.",
    }


def _fallback_receipt(
    *,
    out_dir: Path,
    reason: str,
    attempted: bool,
    container_name: str,
    base_url: str,
    docker_status: Mapping[str, Any] | None = None,
    root_probe: Mapping[str, Any] | None = None,
    http_attempts: Sequence[Mapping[str, Any]] | None = None,
    websocket_attempts: Sequence[Mapping[str, Any]] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    fixture = load_gpu_fixture()
    fixture_path = write_json(out_dir / "p10-gpu-inference-fallback-used.json", fixture)
    receipt: dict[str, Any] = {
        "schema": "personaplex.p10.gpu_inference_probe_receipt.v2",
        "created_at_utc": utc_now_iso(),
        "attempted": attempted,
        "real_gpu_personaplex": False,
        "fallback_used": True,
        "unavailable_reason": reason,
        "container_name": container_name,
        "docker_container_running": bool(docker_status and docker_status.get("running")),
        "api_base_url": base_url,
        "container_inference_observed": False,
        "generated_audio_or_text_tokens": False,
        "direct_local_lmgen_step_called": False,
        "fixture_path": str(fixture_path),
        "claim_boundary": "Fallback receipt only; do not claim live PersonaPlex GPU proof from this run.",
    }
    if docker_status is not None:
        receipt["docker_status"] = dict(docker_status)
    if root_probe is not None:
        receipt["root_probe"] = dict(root_probe)
    if http_attempts is not None:
        receipt["http_inference_attempts"] = list(http_attempts)
    if websocket_attempts is not None:
        receipt["websocket_inference_attempts"] = list(websocket_attempts)
    if extra:
        receipt.update(dict(extra))
    write_json(out_dir / "p10-gpu-personaplex-receipt.json", receipt)
    return receipt


def _success_receipt(
    *,
    out_dir: Path,
    mode: str,
    container_name: str,
    base_url: str,
    docker_status: Mapping[str, Any],
    root_probe: Mapping[str, Any],
    winning_attempt: Mapping[str, Any],
    http_attempts: Sequence[Mapping[str, Any]],
    websocket_attempts: Sequence[Mapping[str, Any]],
    duration_ms: float,
) -> dict[str, Any]:
    outputs = list(winning_attempt.get("generated_outputs") or [])
    receipt = {
        "schema": "personaplex.p10.gpu_inference_probe_receipt.v2",
        "created_at_utc": utc_now_iso(),
        "attempted": True,
        "real_gpu_personaplex": True,
        "fallback_used": False,
        "probe_mode": mode,
        "container_name": container_name,
        "docker_container_running": True,
        "api_base_url": base_url,
        "container_inference_observed": True,
        "generated_audio_or_text_tokens": True,
        "direct_local_lmgen_step_called": False,
        "docker_status": dict(docker_status),
        "root_probe": dict(root_probe),
        "winning_attempt": dict(winning_attempt),
        "generated_outputs": outputs,
        "generated_output_count": len(outputs),
        "http_inference_attempts": list(http_attempts),
        "websocket_inference_attempts": list(websocket_attempts),
        "duration_ms": round(duration_ms, 3),
        "claim_boundary": (
            "Real P10 proof: docker ps showed the PersonaPlex container running, "
            "the HTTPS container surface responded, and a bounded container API "
            "inference request returned generated audio/text/tokens. This does not "
            "claim a local in-process LMGen import."
        ),
    }
    write_json(out_dir / "p10-gpu-personaplex-receipt.json", receipt)
    return receipt


def check_docker_container(container_name: str, timeout: float = 5.0) -> dict[str, Any]:
    cmd = [
        "docker",
        "ps",
        "--filter",
        f"name={container_name}",
        "--format",
        "{{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Ports}}",
    ]
    started = time.monotonic()
    try:
        proc = subprocess.run(  # noqa: S603 - fixed docker ps invocation, no shell.
            cmd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        return {
            "checked": True,
            "running": False,
            "error": "docker_binary_not_found",
            "detail": str(exc),
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "checked": True,
            "running": False,
            "error": "docker_ps_timeout",
            "detail": str(exc),
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
        }

    rows: list[dict[str, str]] = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t", 3)
        while len(parts) < 4:
            parts.append("")
        rows.append({"name": parts[0], "status": parts[1], "image": parts[2], "ports": parts[3]})
    running = any(row["name"] == container_name for row in rows)
    return {
        "checked": True,
        "running": running,
        "container_name": container_name,
        "matched_rows": rows,
        "returncode": proc.returncode,
        "stdout_excerpt": body_excerpt(proc.stdout, 4000),
        "stderr_excerpt": body_excerpt(proc.stderr, 4000),
        "duration_ms": round((time.monotonic() - started) * 1000, 3),
    }


def _ssl_context(verify_tls: bool) -> ssl.SSLContext | None:
    if verify_tls:
        return None
    return ssl._create_unverified_context()  # noqa: SLF001 - localhost self-signed appliance endpoint.


def http_request(
    *,
    method: str,
    url: str,
    payload: Mapping[str, Any] | None = None,
    timeout: float = 10.0,
    verify_tls: bool = False,
) -> dict[str, Any]:
    body: bytes | None = None
    headers = {
        "Accept": "application/json, text/event-stream, text/plain, */*",
        "User-Agent": "personaplex-p10-gpu-docker-probe/1.0",
    }
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context(verify_tls)) as resp:  # noqa: S310 - fixed local probe URL.
            raw = resp.read(2_000_000)
            status = int(resp.status)
            resp_headers = dict(resp.headers.items())
    except urllib.error.HTTPError as exc:
        raw = exc.read(200_000)
        status = int(exc.code)
        resp_headers = dict(exc.headers.items()) if exc.headers else {}
        text = raw.decode("utf-8", errors="replace")
        return {
            "ok": False,
            "url": url,
            "method": method.upper(),
            "status": status,
            "headers": _redacted_headers(resp_headers),
            "body_sha256": _sha256_bytes(raw),
            "body_excerpt": body_excerpt(text, 4000),
            "json": _json_from_text(text),
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
            "error": "http_error",
        }
    except (urllib.error.URLError, TimeoutError, socket.timeout, ssl.SSLError, OSError) as exc:
        return {
            "ok": False,
            "url": url,
            "method": method.upper(),
            "status": None,
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
            "error": f"{type(exc).__name__}:{exc}",
        }

    text = raw.decode("utf-8", errors="replace")
    parsed = _json_from_text(text)
    return {
        "ok": 200 <= status < 300,
        "url": url,
        "method": method.upper(),
        "status": status,
        "headers": _redacted_headers(resp_headers),
        "content_type": resp_headers.get("Content-Type") or resp_headers.get("content-type"),
        "body_sha256": _sha256_bytes(raw),
        "body_excerpt": body_excerpt(text, 4000),
        "json": parsed,
        "duration_ms": round((time.monotonic() - started) * 1000, 3),
    }


def discover_api_paths_from_html(html: str) -> tuple[list[str], list[str]]:
    http_paths: set[str] = set()
    ws_paths: set[str] = set()
    for match in re.findall(r"['\"]((?:/api/|/v1/|/ws)[^'\"\s<>]*)['\"]", html):
        cleaned = match.split("?", 1)[0]
        if cleaned.startswith("/api") or cleaned.startswith("/v1"):
            http_paths.add(cleaned)
        if "ws" in cleaned or "stream" in cleaned or "chat" in cleaned:
            ws_paths.add(cleaned)
    for match in re.findall(r"wss?://[^'\"\s<>]+", html):
        ws_paths.add(match)
    return sorted(http_paths), sorted(ws_paths)


def _prompt_payloads(prompt: str, model: str, max_tokens: int) -> list[dict[str, Any]]:
    messages = [
        {"role": "system", "content": "You are Embry Lawson. Keep the answer short."},
        {"role": "user", "content": prompt},
    ]
    return [
        {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0, "stream": False},
        {"messages": messages, "max_tokens": max_tokens, "temperature": 0, "stream": False},
        {"model": model, "prompt": prompt, "max_tokens": max_tokens, "temperature": 0, "stream": False},
        {"prompt": prompt, "max_new_tokens": max_tokens, "temperature": 0, "stream": False},
        {"message": prompt, "max_tokens": max_tokens, "temperature": 0, "stream": False},
        {"input": prompt, "max_tokens": max_tokens, "temperature": 0, "stream": False},
    ]


def _extract_generated_outputs(value: Any, *, prompt: str) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    prompt_norm = " ".join(prompt.lower().split())

    def add_text(path: str, text: str) -> None:
        cleaned = text.strip()
        if not cleaned:
            return
        lowered = " ".join(cleaned.lower().split())
        if lowered == prompt_norm:
            return
        if cleaned.startswith("<!doctype") or cleaned.startswith("<html"):
            return
        outputs.append(
            {
                "path": path,
                "kind": "text",
                "char_count": len(cleaned),
                "sha256": _sha256_text(cleaned),
                "excerpt": body_excerpt(cleaned, 500),
            }
        )

    def add_tokenish(path: str, obj: Any) -> None:
        if isinstance(obj, int):
            outputs.append({"path": path, "kind": "token", "token_count": 1, "sha256": _sha256_text(str(obj))})
        elif isinstance(obj, list) and obj and all(isinstance(item, int) for item in obj[:64]):
            text = json.dumps(obj[:256], separators=(",", ":"))
            outputs.append({"path": path, "kind": "tokens", "token_count": len(obj), "sha256": _sha256_text(text)})
        elif isinstance(obj, list) and obj and all(isinstance(item, str) for item in obj[:64]):
            joined = "".join(obj)
            add_text(path, joined)

    def visit(obj: Any, path: str = "$", key_hint: str | None = None) -> None:
        if isinstance(obj, Mapping):
            # OpenAI-compatible common case.
            choices = obj.get("choices")
            if isinstance(choices, list):
                for idx, choice in enumerate(choices):
                    if isinstance(choice, Mapping):
                        msg = choice.get("message")
                        if isinstance(msg, Mapping) and isinstance(msg.get("content"), str):
                            add_text(f"{path}.choices[{idx}].message.content", msg["content"])
                        delta = choice.get("delta")
                        if isinstance(delta, Mapping) and isinstance(delta.get("content"), str):
                            add_text(f"{path}.choices[{idx}].delta.content", delta["content"])
                        if isinstance(choice.get("text"), str):
                            add_text(f"{path}.choices[{idx}].text", choice["text"])
            for key, item in obj.items():
                lowered = str(key).lower()
                child_path = f"{path}.{key}"
                if lowered in _GENERATED_TEXT_KEYS and isinstance(item, str):
                    add_text(child_path, item)
                elif lowered in _GENERATED_TOKEN_KEYS:
                    add_tokenish(child_path, item)
                elif lowered in {"audio", "audio_data"} and isinstance(item, Mapping):
                    encoded = item.get("data") or item.get("url") or item.get("path")
                    if isinstance(encoded, str) and encoded.strip():
                        outputs.append(
                            {
                                "path": child_path,
                                "kind": "audio_metadata",
                                "char_count": len(encoded),
                                "sha256": _sha256_text(encoded),
                                "excerpt": body_excerpt(encoded, 200),
                            }
                        )
                visit(item, child_path, lowered)
        elif isinstance(obj, list):
            if key_hint in _GENERATED_TOKEN_KEYS:
                add_tokenish(path, obj)
            for idx, item in enumerate(obj[:128]):
                visit(item, f"{path}[{idx}]", key_hint)
        elif isinstance(obj, str) and key_hint in _GENERATED_TEXT_KEYS:
            add_text(path, obj)
        elif isinstance(obj, int) and key_hint in _GENERATED_TOKEN_KEYS:
            add_tokenish(path, obj)

    visit(value)
    # Deduplicate by kind+hash.
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for output in outputs:
        ident = (str(output.get("kind")), str(output.get("sha256")))
        if ident not in seen:
            seen.add(ident)
            deduped.append(output)
    return deduped


def _http_attempt_summary(result: Mapping[str, Any], payload_index: int, prompt: str) -> dict[str, Any]:
    parsed = result.get("json")
    generated_outputs = _extract_generated_outputs(parsed, prompt=prompt) if parsed is not None else []
    if not generated_outputs and result.get("ok") and isinstance(result.get("body_excerpt"), str):
        content_type = str(result.get("content_type") or "").lower()
        text = str(result.get("body_excerpt") or "").strip()
        if text and "html" not in content_type and not text.lower().startswith("<!doctype") and not text.lower().startswith("<html"):
            generated_outputs = _extract_generated_outputs({"response": text}, prompt=prompt)
    summary = {
        "url": result.get("url"),
        "method": result.get("method"),
        "status": result.get("status"),
        "ok": result.get("ok"),
        "payload_index": payload_index,
        "duration_ms": result.get("duration_ms"),
        "body_sha256": result.get("body_sha256"),
        "body_excerpt": body_excerpt(result.get("body_excerpt", ""), 1200),
        "error": result.get("error"),
        "generated_outputs": generated_outputs,
        "generated_output_count": len(generated_outputs),
    }
    return {key: value for key, value in summary.items() if value is not None}


def run_http_inference_attempts(
    *,
    base_url: str,
    endpoints: Iterable[str],
    prompt: str,
    model: str,
    max_tokens: int,
    timeout: float,
    verify_tls: bool,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    payloads = _prompt_payloads(prompt, model, max_tokens)
    for endpoint in endpoints:
        url = _join_url(base_url, endpoint)
        for idx, payload in enumerate(payloads):
            result = http_request(method="POST", url=url, payload=payload, timeout=timeout, verify_tls=verify_tls)
            summary = _http_attempt_summary(result, idx, prompt)
            attempts.append(summary)
            if summary.get("ok") and summary.get("generated_output_count", 0) > 0:
                return summary, attempts
            # If endpoint says 404/405, try next endpoint rather than all payload variants.
            if summary.get("status") in {404, 405}:
                break
    return None, attempts


def run_websocket_attempts(
    *,
    base_url: str,
    endpoints: Iterable[str],
    prompt: str,
    model: str,
    max_tokens: int,
    timeout: float,
    verify_tls: bool,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    try:
        import websocket  # type: ignore
    except Exception as exc:
        return None, [
            {
                "skipped": True,
                "reason": "websocket_client_not_importable",
                "error": f"{type(exc).__name__}:{exc}",
            }
        ]

    ws_base = _base_to_ws(base_url)
    payloads = _prompt_payloads(prompt, model, max_tokens)
    sslopt = None if verify_tls else {"cert_reqs": ssl.CERT_NONE}
    for endpoint in endpoints:
        url = _join_url(ws_base, endpoint)
        for idx, payload in enumerate(payloads[:3]):
            started = time.monotonic()
            received: list[str] = []
            generated_outputs: list[dict[str, Any]] = []
            error: str | None = None
            try:
                ws = websocket.create_connection(url, timeout=timeout, sslopt=sslopt)  # type: ignore[attr-defined]
                try:
                    ws.send(json.dumps(payload))
                    deadline = time.monotonic() + timeout
                    while time.monotonic() < deadline and len(received) < 8:
                        msg = ws.recv()
                        if isinstance(msg, bytes):
                            msg = msg.decode("utf-8", errors="replace")
                        received.append(str(msg))
                        parsed = _json_from_text(str(msg))
                        if parsed is None:
                            parsed = {"response": str(msg)}
                        generated_outputs = _extract_generated_outputs(parsed, prompt=prompt)
                        if generated_outputs:
                            break
                finally:
                    with contextlib.suppress(Exception):
                        ws.close()
            except Exception as exc:  # pragma: no cover - network dependent.
                error = f"{type(exc).__name__}:{exc}"
            summary = {
                "url": url,
                "payload_index": idx,
                "ok": bool(generated_outputs),
                "duration_ms": round((time.monotonic() - started) * 1000, 3),
                "received_count": len(received),
                "received_sha256": _sha256_text("\n".join(received)) if received else None,
                "received_excerpt": body_excerpt("\n".join(received), 1200),
                "generated_outputs": generated_outputs,
                "generated_output_count": len(generated_outputs),
                "error": error,
            }
            attempts.append({key: value for key, value in summary.items() if value is not None})
            if generated_outputs:
                return attempts[-1], attempts
    return None, attempts


def _merge_endpoint_lists(defaults: Sequence[str], explicit: Sequence[str] | None, discovered: Sequence[str]) -> list[str]:
    ordered: list[str] = []
    for source in (explicit or [], discovered, defaults):
        for item in source:
            if item and item not in ordered:
                ordered.append(item)
    return ordered


def run_gpu_personaplex_probe(
    *,
    out_dir: str | Path = DEFAULT_SANITY_ROOT,
    container_name: str = DEFAULT_CONTAINER_NAME,
    base_url: str = DEFAULT_BASE_URL,
    prompt: str = DEFAULT_PROMPT,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 48,
    timeout: float = 10.0,
    docker_timeout: float = 5.0,
    verify_tls: bool = False,
    http_endpoints: Sequence[str] | None = None,
    websocket_endpoints: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Run the Docker-backed PersonaPlex P10 inference probe.

    Returns the same receipt dict that is written to
    ``<out_dir>/p10-gpu-personaplex-receipt.json``.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()

    docker_status = check_docker_container(container_name, timeout=docker_timeout)
    write_json(out / "p10-docker-status.json", docker_status)
    if not docker_status.get("running"):
        return _fallback_receipt(
            out_dir=out,
            reason="personaplex_docker_container_not_running",
            attempted=False,
            container_name=container_name,
            base_url=base_url,
            docker_status=docker_status,
        )

    root_url = base_url.rstrip("/") + "/"
    root_probe_full = http_request(method="GET", url=root_url, timeout=timeout, verify_tls=verify_tls)
    root_probe = {
        "url": root_probe_full.get("url"),
        "ok": root_probe_full.get("ok"),
        "status": root_probe_full.get("status"),
        "content_type": root_probe_full.get("content_type"),
        "body_sha256": root_probe_full.get("body_sha256"),
        "body_excerpt": body_excerpt(root_probe_full.get("body_excerpt", ""), 1200),
        "duration_ms": root_probe_full.get("duration_ms"),
        "error": root_probe_full.get("error"),
    }
    root_probe = {key: value for key, value in root_probe.items() if value is not None}
    write_json(out / "p10-container-root-probe.json", root_probe)
    if not root_probe_full.get("ok"):
        return _fallback_receipt(
            out_dir=out,
            reason="personaplex_container_https_root_unavailable",
            attempted=True,
            container_name=container_name,
            base_url=base_url,
            docker_status=docker_status,
            root_probe=root_probe,
        )

    discovered_http, discovered_ws = discover_api_paths_from_html(str(root_probe_full.get("body_excerpt") or ""))
    env_http = [x.strip() for x in os.environ.get("PERSONAPLEX_GPU_HTTP_ENDPOINTS", "").split(",") if x.strip()]
    env_ws = [x.strip() for x in os.environ.get("PERSONAPLEX_GPU_WS_ENDPOINTS", "").split(",") if x.strip()]
    final_http_endpoints = _merge_endpoint_lists(DEFAULT_HTTP_ENDPOINTS, list(http_endpoints or []) + env_http, discovered_http)
    final_ws_endpoints = _merge_endpoint_lists(DEFAULT_WS_ENDPOINTS, list(websocket_endpoints or []) + env_ws, discovered_ws)

    http_winner, http_attempts = run_http_inference_attempts(
        base_url=base_url,
        endpoints=final_http_endpoints,
        prompt=prompt,
        model=model,
        max_tokens=max_tokens,
        timeout=timeout,
        verify_tls=verify_tls,
    )
    write_json(out / "p10-container-http-inference-attempts.json", {"attempts": http_attempts})
    if http_winner is not None:
        return _success_receipt(
            out_dir=out,
            mode="docker_container_api_http",
            container_name=container_name,
            base_url=base_url,
            docker_status=docker_status,
            root_probe=root_probe,
            winning_attempt=http_winner,
            http_attempts=http_attempts,
            websocket_attempts=[],
            duration_ms=(time.monotonic() - started) * 1000,
        )

    ws_winner, ws_attempts = run_websocket_attempts(
        base_url=base_url,
        endpoints=final_ws_endpoints,
        prompt=prompt,
        model=model,
        max_tokens=max_tokens,
        timeout=timeout,
        verify_tls=verify_tls,
    )
    write_json(out / "p10-container-websocket-inference-attempts.json", {"attempts": ws_attempts})
    if ws_winner is not None:
        return _success_receipt(
            out_dir=out,
            mode="docker_container_api_websocket",
            container_name=container_name,
            base_url=base_url,
            docker_status=docker_status,
            root_probe=root_probe,
            winning_attempt=ws_winner,
            http_attempts=http_attempts,
            websocket_attempts=ws_attempts,
            duration_ms=(time.monotonic() - started) * 1000,
        )

    return _fallback_receipt(
        out_dir=out,
        reason="personaplex_container_api_returned_no_generated_audio_text_or_tokens",
        attempted=True,
        container_name=container_name,
        base_url=base_url,
        docker_status=docker_status,
        root_probe=root_probe,
        http_attempts=http_attempts,
        websocket_attempts=ws_attempts,
        extra={
            "http_endpoints_tried": final_http_endpoints,
            "websocket_endpoints_tried": final_ws_endpoints,
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
        },
    )


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PersonaPlex P10 Docker GPU inference proof probe")
    parser.add_argument("--out-dir", default=str(DEFAULT_SANITY_ROOT))
    parser.add_argument("--container-name", default=os.environ.get("PERSONAPLEX_CONTAINER_NAME", DEFAULT_CONTAINER_NAME))
    parser.add_argument("--base-url", default=os.environ.get("PERSONAPLEX_GPU_BASE_URL", os.environ.get("PERSONAPLEX_BASE_URL", DEFAULT_BASE_URL)))
    parser.add_argument("--prompt", default=os.environ.get("PERSONAPLEX_GPU_PROBE_PROMPT", DEFAULT_PROMPT))
    parser.add_argument("--model", default=os.environ.get("PERSONAPLEX_GPU_MODEL", DEFAULT_MODEL))
    parser.add_argument("--max-tokens", type=int, default=int(os.environ.get("PERSONAPLEX_GPU_MAX_TOKENS", "48")))
    parser.add_argument("--timeout", type=float, default=float(os.environ.get("PERSONAPLEX_GPU_API_TIMEOUT", "10")))
    parser.add_argument("--docker-timeout", type=float, default=float(os.environ.get("PERSONAPLEX_GPU_DOCKER_TIMEOUT", "5")))
    parser.add_argument("--http-endpoints", default=None, help="Comma-separated endpoint paths/URLs to try before defaults.")
    parser.add_argument("--websocket-endpoints", default=None, help="Comma-separated WS endpoint paths/URLs to try before defaults.")
    parser.add_argument("--verify-tls", action="store_true", help="Verify TLS certificates. Default is disabled for localhost/self-signed HTTPS.")
    parser.add_argument("--require-real", action="store_true", help="Exit 2 unless real_gpu_personaplex=true.")
    args = parser.parse_args(argv)

    receipt = run_gpu_personaplex_probe(
        out_dir=args.out_dir,
        container_name=args.container_name,
        base_url=args.base_url,
        prompt=args.prompt,
        model=args.model,
        max_tokens=args.max_tokens,
        timeout=args.timeout,
        docker_timeout=args.docker_timeout,
        verify_tls=args.verify_tls,
        http_endpoints=_split_csv(args.http_endpoints),
        websocket_endpoints=_split_csv(args.websocket_endpoints),
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    if args.require_real and not receipt.get("real_gpu_personaplex"):
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
