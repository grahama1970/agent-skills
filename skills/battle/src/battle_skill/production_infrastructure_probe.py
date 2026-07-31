"""Live probe runner for Battle production infrastructure deployment receipts.

Inputs are explicit production frontend, backend health, and WebSocket URLs plus
release metadata. Outputs are fail-closed JSON receipts. Network failures,
private/local targets, bad TLS, bad HTTP status, or WebSocket handshake failure
produce a BLOCKED receipt rather than a readiness claim.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import socket
import ssl
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from websockets.exceptions import WebSocketException
from websockets.sync.client import connect as websocket_connect

from .packaged_deployment_smoke import _now_utc
from .production_infrastructure_contract import (
    EXPECTED_LIVE_MODE,
    EXPECTED_SCHEMA,
    validate_production_infrastructure_receipt,
)


def prove_production_infrastructure_deployment(
    *,
    out_dir: Path,
    frontend_url: str,
    backend_health_url: str,
    websocket_url: str,
    commit: str,
    release_id: str,
    secret_source: str,
    websocket_bearer_token: str | None = None,
    timeout_s: float = 5.0,
    allow_private_targets: bool = False,
) -> dict[str, Any]:
    """Probe production URLs and write a production infrastructure receipt."""
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    target = {
        "environment": "production",
        "frontend_url": frontend_url,
        "backend_health_url": backend_health_url,
        "websocket_url": websocket_url,
        "commit": commit,
        "release_id": release_id,
    }
    probe_errors: list[str] = []
    probe_errors.extend(
        _target_url_errors(
            urls=(frontend_url, backend_health_url, websocket_url),
            allow_private_targets=allow_private_targets,
        )
    )

    evidence = {
        "frontend_https_response": _probe_https(frontend_url, timeout_s=timeout_s),
        "backend_health_response": _probe_https(backend_health_url, timeout_s=timeout_s),
        "websocket_connectivity": _probe_websocket(
            websocket_url,
            bearer_token=websocket_bearer_token,
            timeout_s=timeout_s,
        ),
        "tls_certificate": _probe_tls_certificate(frontend_url, timeout_s=timeout_s),
        "dns_resolution": _resolve_dns(frontend_url, allow_private_targets=allow_private_targets),
        "ingress_route": {
            "status": "PASS"
            if _url_host(frontend_url) == _url_host(backend_health_url) == _url_host(websocket_url)
            else "BLOCKED",
            "frontend_host": _url_host(frontend_url),
            "backend_host": _url_host(backend_health_url),
            "websocket_host": _url_host(websocket_url),
        },
        "secret_configuration": {
            "source": secret_source,
            "websocket_authorization_header_present": websocket_bearer_token is not None,
        },
    }
    probe_errors.extend(_evidence_errors(evidence))

    provisional = {
        "schema": EXPECTED_SCHEMA,
        "status": "PASS" if not probe_errors else "BLOCKED",
        "mocked": False,
        "live": EXPECTED_LIVE_MODE,
        "target": target,
        "evidence": evidence,
    }
    contract_errors = validate_production_infrastructure_receipt(provisional)
    errors = _dedupe_errors([*probe_errors, *contract_errors])

    receipt = {
        **provisional,
        "status": "PASS" if not errors else "BLOCKED",
        "errors": errors,
        "claim_boundary": {
            "proves": _proves() if not errors else [],
            "does_not_prove": [
                "Battle exploit/defense loop quality.",
                "Production-scale fanout, autoscaling, or mathematically unbounded swarm behavior.",
                "Security posture beyond the checked frontend, health, TLS, DNS, ingress, secret-source, and WebSocket probes.",
            ],
        },
        "created_at": _now_utc(),
    }
    (out_dir / "production-infrastructure-deployment-proof.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


def _target_url_errors(*, urls: tuple[str, str, str], allow_private_targets: bool) -> list[str]:
    errors: list[str] = []
    for url in urls:
        parsed = urlparse(url)
        expected_scheme = "wss" if url == urls[2] else "https"
        if parsed.scheme != expected_scheme or not parsed.hostname:
            errors.append(f"production URL must be {expected_scheme} with a hostname: {url}")
            continue
        if not allow_private_targets:
            errors.extend(_public_host_errors(parsed.hostname))
    return errors


def _public_host_errors(host: str) -> list[str]:
    errors: list[str] = []
    if host.lower() in {"localhost"}:
        return [f"production target host must not be localhost: {host}"]
    try:
        parsed_ip = ipaddress.ip_address(host)
    except ValueError:
        return errors
    if not parsed_ip.is_global:
        errors.append(f"production target host must be globally routable: {host}")
    return errors


def _probe_https(url: str, *, timeout_s: float) -> dict[str, Any]:
    started = time.monotonic()
    try:
        with httpx.Client(
            timeout=httpx.Timeout(timeout_s, connect=min(timeout_s, 3.0)),
            follow_redirects=False,
        ) as client:
            response = client.get(url)
        body = response.content
        return {
            "status": "PASS" if response.status_code == 200 else "BLOCKED",
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type"),
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
            "body_sha256": hashlib.sha256(body).hexdigest(),
            "body_size": len(body),
        }
    except httpx.HTTPError as exc:
        return {
            "status": "BLOCKED",
            "status_code": None,
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
            "error": type(exc).__name__,
        }


def _probe_websocket(
    url: str,
    *,
    bearer_token: str | None,
    timeout_s: float,
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else None
    started = time.monotonic()
    try:
        with websocket_connect(
            url,
            additional_headers=headers,
            open_timeout=timeout_s,
            close_timeout=timeout_s,
            compression=None,
        ):
            return {
                "status": "PASS",
                "connected": True,
                "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                "authorization_header_present": bearer_token is not None,
            }
    except (OSError, WebSocketException, TimeoutError) as exc:
        return {
            "status": "BLOCKED",
            "connected": False,
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
            "authorization_header_present": bearer_token is not None,
            "error": type(exc).__name__,
        }


def _probe_tls_certificate(url: str, *, timeout_s: float) -> dict[str, Any]:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = parsed.port or 443
    started = time.monotonic()
    try:
        context = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=timeout_s) as raw_socket:
            with context.wrap_socket(raw_socket, server_hostname=host) as tls_socket:
                certificate = tls_socket.getpeercert()
                return {
                    "status": "PASS",
                    "valid": True,
                    "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                    "subject": certificate.get("subject"),
                    "issuer": certificate.get("issuer"),
                    "not_after": certificate.get("notAfter"),
                }
    except (OSError, ssl.SSLError) as exc:
        return {
            "status": "BLOCKED",
            "valid": False,
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
            "error": type(exc).__name__,
        }


def _resolve_dns(url: str, *, allow_private_targets: bool) -> dict[str, Any]:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    try:
        infos = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        return {"status": "BLOCKED", "resolves": False, "host": host, "error": type(exc).__name__}
    addresses = sorted({info[4][0] for info in infos})
    private_errors: list[str] = []
    if not allow_private_targets:
        for address in addresses:
            private_errors.extend(_public_host_errors(address))
    return {
        "status": "PASS" if addresses and not private_errors else "BLOCKED",
        "resolves": bool(addresses) and not private_errors,
        "host": host,
        "addresses": addresses,
        "errors": private_errors,
    }


def _evidence_errors(evidence: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in ("frontend_https_response", "backend_health_response"):
        if evidence[key].get("status_code") != 200:
            errors.append(f"production infrastructure {key}.status_code must be 200")
    if evidence["websocket_connectivity"].get("connected") is not True:
        errors.append("production infrastructure websocket_connectivity.connected must be true")
    if evidence["tls_certificate"].get("valid") is not True:
        errors.append("production infrastructure tls_certificate.valid must be true")
    if evidence["dns_resolution"].get("resolves") is not True:
        errors.append("production infrastructure dns_resolution.resolves must be true")
    if evidence["ingress_route"].get("status") != "PASS":
        errors.append("production infrastructure ingress_route.status must be PASS")
    if not evidence["secret_configuration"].get("source"):
        errors.append("production infrastructure secret_configuration.source missing")
    return errors


def _url_host(url: str) -> str | None:
    return urlparse(url).hostname


def _dedupe_errors(errors: list[str]) -> list[str]:
    return list(dict.fromkeys(errors))


def _proves() -> list[str]:
    return [
        "The supplied production frontend URL returned HTTPS 200 with validated TLS.",
        "The supplied production backend health URL returned HTTPS 200.",
        "The supplied production WebSocket URL completed a WSS handshake.",
        "DNS resolution, ingress host alignment, and secret-source metadata were recorded.",
    ]
