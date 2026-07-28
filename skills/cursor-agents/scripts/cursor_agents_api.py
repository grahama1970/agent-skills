#!/usr/bin/env python3
from __future__ import annotations

import base64
import json as json_lib
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode

import requests
import typer
from dotenv import load_dotenv

app = typer.Typer(add_completion=False, help="Cursor Cloud Agents API wrapper.")
load_dotenv()

API_KEY_ENV_NAMES = (
    "CURSOR_API_KEY",
    "CURSOR_AGENTS_API_KEY",
    "CURSOR_SERVICE_ACCOUNT_API_KEY",
)
DEFAULT_BASE_URL = "https://api.cursor.com"
SCHEMA = "cursor_agents.receipt.v1"
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class CursorAgentsError(RuntimeError):
    pass


def _api_key() -> tuple[str, str]:
    for name in API_KEY_ENV_NAMES:
        value = os.environ.get(name)
        if value:
            return name, value
    names = ", ".join(API_KEY_ENV_NAMES)
    raise CursorAgentsError(f"Missing Cursor API key. Set one of: {names}.")


def _base_url() -> str:
    return os.environ.get("CURSOR_API_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _auth_headers(api_key: str, auth: str) -> dict[str, str]:
    if auth == "basic":
        token = base64.b64encode(f"{api_key}:".encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {token}"}
    if auth == "bearer":
        return {"Authorization": f"Bearer {api_key}"}
    raise CursorAgentsError("Invalid auth mode. Use 'basic' or 'bearer'.")


def _normalize_path(path: str) -> str:
    if not path.startswith("/"):
        path = f"/{path}"
    if not path.startswith("/v1/"):
        raise CursorAgentsError(
            f"Refusing endpoint '{path}'. Use a documented /v1/... Cursor API path."
        )
    return path


def _write_receipt(path: Optional[Path], receipt: dict[str, Any]) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_lib.dumps(receipt, indent=2, sort_keys=True) + "\n")


def _print_response(response_json: Any, json_output: bool) -> None:
    if json_output:
        typer.echo(json_lib.dumps(response_json, indent=2, sort_keys=True))
        return
    if isinstance(response_json, dict) and isinstance(response_json.get("items"), list):
        for item in response_json["items"]:
            if isinstance(item, dict):
                identifier = item.get("id") or item.get("name") or "<unknown>"
                display = item.get("displayName") or item.get("display_name") or ""
                typer.echo(f"{identifier}\t{display}".rstrip())
        return
    typer.echo(json_lib.dumps(response_json, indent=2, sort_keys=True))


def _request(
    command: str,
    method: str,
    path: str,
    *,
    params: Optional[dict[str, Any]] = None,
    data: Optional[dict[str, Any]] = None,
    auth: str = "basic",
    timeout: float = 30.0,
    receipt_path: Optional[Path] = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    env_name, api_key = _api_key()
    normalized_path = _normalize_path(path)
    headers = {
        "Accept": "application/json",
        "User-Agent": "agent-skills cursor-agents/0.1",
        **_auth_headers(api_key, auth),
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    url = f"{_base_url()}{normalized_path}"
    started = time.time()
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "command": command,
        "method": method.upper(),
        "path": normalized_path,
        "params": params or {},
        "auth_mode": auth,
        "credential_env": env_name,
        "base_url": _base_url(),
        "ok": False,
        "started_at_unix": started,
    }
    try:
        response = requests.request(
            method.upper(),
            url,
            params=params,
            json=data,
            headers=headers,
            timeout=timeout,
        )
        receipt["status_code"] = response.status_code
        receipt["elapsed_seconds"] = round(time.time() - started, 3)
        try:
            response_json = response.json()
        except ValueError:
            response_json = {"text": response.text[:2000]}
        receipt["response"] = response_json
        receipt["ok"] = 200 <= response.status_code < 300
        _write_receipt(receipt_path, receipt)
        if not receipt["ok"]:
            raise CursorAgentsError(
                f"Cursor API {method.upper()} {normalized_path} returned "
                f"HTTP {response.status_code}. Receipt: {receipt_path or '<not written>'}"
            )
        return response_json, receipt
    except requests.RequestException as exc:
        receipt["elapsed_seconds"] = round(time.time() - started, 3)
        receipt["error"] = {
            "type": exc.__class__.__name__,
            "message": str(exc)[:1000],
        }
        _write_receipt(receipt_path, receipt)
        raise CursorAgentsError(
            f"Cursor API request failed. Receipt: {receipt_path or '<not written>'}. {exc}"
        ) from exc


def _handle_error(exc: Exception) -> None:
    typer.echo(f"cursor-agents error: {exc}", err=True)
    raise typer.Exit(2)


@app.command()
def doctor(
    auth: str = typer.Option("basic", "--auth", help="Auth mode: basic or bearer."),
    receipt: Optional[Path] = typer.Option(None, "--receipt", help="Write receipt JSON."),
    offline: bool = typer.Option(False, "--offline", help="Check configuration only."),
) -> None:
    """Check local configuration and, unless offline, the live models endpoint."""
    try:
        env_name, _ = _api_key()
        if offline:
            output = {
                "schema": SCHEMA,
                "command": "doctor",
                "ok": True,
                "offline": True,
                "credential_env": env_name,
                "base_url": _base_url(),
                "auth_mode": auth,
            }
            _write_receipt(receipt, output)
            typer.echo(json_lib.dumps(output, indent=2, sort_keys=True))
            return
        response_json, live_receipt = _request(
            "doctor",
            "GET",
            "/v1/models",
            auth=auth,
            receipt_path=receipt,
        )
        items = response_json.get("items") if isinstance(response_json, dict) else None
        live_receipt["model_count"] = len(items) if isinstance(items, list) else None
        _write_receipt(receipt, live_receipt)
        typer.echo(json_lib.dumps(live_receipt, indent=2, sort_keys=True))
    except Exception as exc:  # noqa: BLE001 - Typer boundary
        _handle_error(exc)


@app.command()
def models(
    json_output: bool = typer.Option(False, "--json", help="Print raw JSON."),
    auth: str = typer.Option("basic", "--auth", help="Auth mode: basic or bearer."),
    receipt: Optional[Path] = typer.Option(None, "--receipt", help="Write receipt JSON."),
) -> None:
    """List Cursor model choices exposed by the Cloud Agents API."""
    try:
        response_json, _ = _request("models", "GET", "/v1/models", auth=auth, receipt_path=receipt)
        _print_response(response_json, json_output)
    except Exception as exc:  # noqa: BLE001 - Typer boundary
        _handle_error(exc)


@app.command("agent")
def agent_get(
    agent_id: str,
    json_output: bool = typer.Option(False, "--json", help="Print raw JSON."),
    auth: str = typer.Option("basic", "--auth", help="Auth mode: basic or bearer."),
    receipt: Optional[Path] = typer.Option(None, "--receipt", help="Write receipt JSON."),
) -> None:
    """Inspect one Cursor Cloud Agent."""
    try:
        response_json, _ = _request(
            "agent",
            "GET",
            f"/v1/agents/{agent_id}",
            auth=auth,
            receipt_path=receipt,
        )
        _print_response(response_json, json_output)
    except Exception as exc:  # noqa: BLE001 - Typer boundary
        _handle_error(exc)


@app.command()
def runs(
    agent_id: str,
    limit: int = typer.Option(20, "--limit", min=1, max=100),
    json_output: bool = typer.Option(False, "--json", help="Print raw JSON."),
    auth: str = typer.Option("basic", "--auth", help="Auth mode: basic or bearer."),
    receipt: Optional[Path] = typer.Option(None, "--receipt", help="Write receipt JSON."),
) -> None:
    """List recent runs for a Cursor Cloud Agent."""
    try:
        response_json, _ = _request(
            "runs",
            "GET",
            f"/v1/agents/{agent_id}/runs",
            params={"limit": limit},
            auth=auth,
            receipt_path=receipt,
        )
        _print_response(response_json, json_output)
    except Exception as exc:  # noqa: BLE001 - Typer boundary
        _handle_error(exc)


@app.command()
def usage(
    agent_id: str,
    run_id: Optional[str] = typer.Option(None, "--run-id"),
    json_output: bool = typer.Option(False, "--json", help="Print raw JSON."),
    auth: str = typer.Option("basic", "--auth", help="Auth mode: basic or bearer."),
    receipt: Optional[Path] = typer.Option(None, "--receipt", help="Write receipt JSON."),
) -> None:
    """Inspect usage for an agent, optionally scoped to one run."""
    try:
        params = {"runId": run_id} if run_id else None
        response_json, _ = _request(
            "usage",
            "GET",
            f"/v1/agents/{agent_id}/usage",
            params=params,
            auth=auth,
            receipt_path=receipt,
        )
        _print_response(response_json, json_output)
    except Exception as exc:  # noqa: BLE001 - Typer boundary
        _handle_error(exc)


@app.command()
def raw(
    method: str,
    path: str,
    data: Optional[str] = typer.Option(None, "--data", help="JSON request body."),
    yes: bool = typer.Option(False, "--yes", help="Allow mutating methods."),
    json_output: bool = typer.Option(False, "--json", help="Print raw JSON."),
    auth: str = typer.Option("basic", "--auth", help="Auth mode: basic or bearer."),
    receipt: Optional[Path] = typer.Option(None, "--receipt", help="Write receipt JSON."),
) -> None:
    """Call a documented /v1 Cursor API endpoint not yet wrapped."""
    try:
        upper = method.upper()
        if upper in MUTATING_METHODS and not yes:
            raise CursorAgentsError(
                f"{upper} is mutating and requires --yes. Get explicit human authorization "
                "before creating or changing Cursor agents."
            )
        payload = json_lib.loads(data) if data else None
        response_json, _ = _request(
            "raw",
            upper,
            path,
            data=payload,
            auth=auth,
            receipt_path=receipt,
        )
        _print_response(response_json, json_output)
    except json_lib.JSONDecodeError as exc:
        _handle_error(CursorAgentsError(f"--data must be valid JSON: {exc}"))
    except Exception as exc:  # noqa: BLE001 - Typer boundary
        _handle_error(exc)


if __name__ == "__main__":
    app()
