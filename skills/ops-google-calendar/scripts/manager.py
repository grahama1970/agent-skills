"""Google Calendar read + propose-only scheduling over OAuth.

Thin Typer CLI over a few functions. `status`/`events` are read-only; `auth`
runs the interactive consent flow; `propose-reschedule`/`propose-create` emit a
proposal receipt and only touch the calendar when `--confirm` is passed AND a
valid token exists. Writes fail closed: no token or no `--confirm` means the
receipt says NOT_EXECUTED and the exit code reflects it, so nothing mutates a
real calendar by accident.

Auth uses google-auth-oauthlib for the one-time browser consent; every Calendar
REST call and the token refresh go through httpx with the access token, so the
runtime dependency surface stays small and the API layer is plain HTTP.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import typer
from dotenv import load_dotenv
from loguru import logger

load_dotenv(override=False)

app = typer.Typer(add_completion=False, help="Google Calendar read + propose-only scheduling")

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
TOKEN_URL = "https://oauth2.googleapis.com/token"
API_BASE = "https://www.googleapis.com/calendar/v3"
CONFIG_DIR = Path(os.environ.get("OPS_GCAL_CONFIG_DIR", "~/.config/ops-google-calendar")).expanduser()
CLIENT_SECRET = CONFIG_DIR / "client_secret.json"
TOKEN_FILE = CONFIG_DIR / "token.json"


def _emit(receipt: dict[str, Any], as_json: bool) -> None:
    """Print a receipt as JSON or a short human line; never print secrets."""

    if as_json:
        typer.echo(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        status = receipt.get("status", "?")
        typer.echo(f"{receipt.get('schema', 'receipt')}: {status}")


def _load_token() -> dict[str, Any] | None:
    if not TOKEN_FILE.is_file():
        return None
    try:
        return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        logger.warning("token unreadable: {}", exc)
        return None


def _save_token(token: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(token), encoding="utf-8")
    TOKEN_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600: never world-readable


def _access_token() -> str | None:
    """Return a fresh access token, refreshing via httpx when needed.

    Returns None when unauthenticated or the refresh fails, so every caller
    fails closed rather than proceeding without credentials.
    """

    token = _load_token()
    if not token or not token.get("refresh_token"):
        return None
    try:
        response = httpx.post(TOKEN_URL, data={
            "client_id": token["client_id"],
            "client_secret": token["client_secret"],
            "refresh_token": token["refresh_token"],
            "grant_type": "refresh_token",
        }, timeout=20.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("token refresh failed: {}", exc)
        return None
    return response.json().get("access_token")


def _api(method: str, path: str, access_token: str, *,
         params: dict | None = None, body: dict | None = None) -> httpx.Response:
    return httpx.request(
        method, f"{API_BASE}{path}",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params, json=body, timeout=30.0,
    )


@app.command()
def auth() -> None:
    """Run the one-time interactive OAuth consent flow (opens a browser)."""

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        typer.echo("google-auth-oauthlib not installed; run via ./run.sh", err=True)
        raise typer.Exit(2)
    if not CLIENT_SECRET.is_file():
        typer.echo(f"missing OAuth client at {CLIENT_SECRET} (see SKILL.md setup)", err=True)
        raise typer.Exit(2)
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
    creds = flow.run_local_server(port=0)
    _save_token({
        "refresh_token": creds.refresh_token,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
    })
    typer.echo(f"authorized; token stored at {TOKEN_FILE} (0600)")


@app.command()
def status(as_json: bool = typer.Option(True, "--json/--no-json")) -> None:
    """Read-only: is the skill authenticated and is the API reachable?"""

    token = _load_token()
    receipt: dict[str, Any] = {
        "schema": "ops_google_calendar.status.v1",
        "authenticated": bool(token and token.get("refresh_token")),
        "client_secret_present": CLIENT_SECRET.is_file(),
        "token_file": str(TOKEN_FILE),
        "reachable": None,
        "mocked": False,
    }
    if receipt["authenticated"]:
        access = _access_token()
        receipt["reachable"] = access is not None
        receipt["status"] = "READY" if access else "TOKEN_INVALID"
    else:
        receipt["status"] = "UNAUTHENTICATED"
    _emit(receipt, as_json)


@app.command()
def events(days: int = typer.Option(7, "--days"),
           as_json: bool = typer.Option(True, "--json/--no-json")) -> None:
    """Read-only: list upcoming events in the primary calendar."""

    access = _access_token()
    if access is None:
        _emit({"schema": "ops_google_calendar.events.v1", "status": "INFRA_BLOCKED",
               "reason": "unauthenticated"}, as_json)
        raise typer.Exit(0)
    now = datetime.now(timezone.utc)
    resp = _api("GET", "/calendars/primary/events", access, params={
        "timeMin": now.isoformat(), "timeMax": (now + timedelta(days=days)).isoformat(),
        "singleEvents": "true", "orderBy": "startTime", "maxResults": 50,
    })
    if resp.status_code != 200:
        _emit({"schema": "ops_google_calendar.events.v1", "status": "API_ERROR",
               "http": resp.status_code}, as_json)
        raise typer.Exit(1)
    items = [{"id": e.get("id"), "summary": e.get("summary"),
              "start": (e.get("start") or {}).get("dateTime")} for e in resp.json().get("items", [])]
    _emit({"schema": "ops_google_calendar.events.v1", "status": "OK",
           "count": len(items), "events": items}, as_json)


def _apply_or_propose(action: str, change: dict[str, Any], confirm: bool,
                      applier, as_json: bool) -> None:
    """Shared propose-only path: without --confirm (or without a token) emit a
    proposal and DO NOT touch the calendar; with both, apply and read back."""

    receipt: dict[str, Any] = {
        "schema": "ops_google_calendar.proposal.v1",
        "action": action, "change": change, "confirmed": confirm,
    }
    if not confirm:
        receipt["status"] = "NOT_EXECUTED"
        receipt["note"] = "proposal only; re-run with --confirm to apply"
        _emit(receipt, as_json)
        raise typer.Exit(0)
    access = _access_token()
    if access is None:
        receipt["status"] = "BLOCKED_UNAUTHENTICATED"
        _emit(receipt, as_json)
        raise typer.Exit(1)
    applied = applier(access)
    if applied is None:
        receipt["status"] = "API_ERROR"
        _emit(receipt, as_json)
        raise typer.Exit(1)
    receipt["status"] = "APPLIED"
    receipt["applied_event"] = applied
    _emit(receipt, as_json)


@app.command(name="propose-reschedule")
def propose_reschedule(
    event_id: str = typer.Option(..., "--event-id"),
    to: str = typer.Option(..., "--to", help="new start, ISO 8601 with offset"),
    duration_minutes: int = typer.Option(30, "--duration-minutes"),
    confirm: bool = typer.Option(False, "--confirm"),
    as_json: bool = typer.Option(True, "--json/--no-json"),
) -> None:
    """Propose moving an event to a new start time (propose-only unless --confirm)."""

    start = datetime.fromisoformat(to)
    end = (start + timedelta(minutes=duration_minutes)).isoformat()
    change = {"event_id": event_id, "new_start": start.isoformat(), "new_end": end}

    def apply(access: str) -> dict | None:
        resp = _api("PATCH", f"/calendars/primary/events/{event_id}", access, body={
            "start": {"dateTime": start.isoformat()}, "end": {"dateTime": end},
        })
        if resp.status_code != 200:
            return None
        ev = resp.json()
        return {"id": ev.get("id"), "start": (ev.get("start") or {}).get("dateTime")}

    _apply_or_propose("reschedule", change, confirm, apply, as_json)


@app.command(name="propose-create")
def propose_create(
    summary: str = typer.Option(..., "--summary"),
    start: str = typer.Option(..., "--start", help="ISO 8601 with offset"),
    end: str = typer.Option(..., "--end", help="ISO 8601 with offset"),
    confirm: bool = typer.Option(False, "--confirm"),
    as_json: bool = typer.Option(True, "--json/--no-json"),
) -> None:
    """Propose creating a new event (propose-only unless --confirm)."""

    change = {"summary": summary, "start": start, "end": end}

    def apply(access: str) -> dict | None:
        resp = _api("POST", "/calendars/primary/events", access, body={
            "summary": summary, "start": {"dateTime": start}, "end": {"dateTime": end},
        })
        if resp.status_code not in (200, 201):
            return None
        ev = resp.json()
        return {"id": ev.get("id"), "start": (ev.get("start") or {}).get("dateTime")}

    _apply_or_propose("create", change, confirm, apply, as_json)


if __name__ == "__main__":
    app()
