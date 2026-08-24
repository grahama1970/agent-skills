"""Calendly API operations for grahama.co.

Inputs come from the Calendly API, fixture JSON files, CLI flags, and the local
environment. Outputs are redacted JSON receipts and public static-site metadata.
Failures are explicit: missing credentials, malformed provider payloads, unsafe
capacity-hold requests, and subprocess failures exit non-zero without printing
secrets.
"""

from __future__ import annotations

import json
import os
import subprocess
from urllib.parse import quote
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Annotated, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
import typer
from dotenv import load_dotenv
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError

load_dotenv(override=False)

app = typer.Typer(add_completion=False, help="Calendly ops for grahama.co")
capacity_holds_app = typer.Typer(add_completion=False, help="Plan real capacity holds")
app.add_typer(capacity_holds_app, name="capacity-holds")

API_BASE = "https://api.calendly.com"
GCAL_API_BASE = "https://www.googleapis.com/calendar/v3"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GCAL_CONFIG_DIR = Path(os.environ.get("OPS_GCAL_CONFIG_DIR", "~/.config/ops-google-calendar")).expanduser()
GCAL_TOKEN_FILE = GCAL_CONFIG_DIR / "token.json"
RECEIPT_DIR = Path(
    os.environ.get("OPS_CALENDLY_RECEIPT_DIR", "/mnt/storage12tb/skills/ops-calendly/receipts")
).expanduser()
USER_AGENT = "ops-calendly/0.1"
MAX_HOLD_RATIO = 0.45
ALLOWED_HOLD_REASONS = {"focus", "delivery", "admin", "travel"}


class CalendlyUser(BaseModel):
    """Validated subset of Calendly /users/me resource."""

    model_config = ConfigDict(extra="ignore")

    uri: str = Field(min_length=1)
    name: str | None = None
    slug: str | None = None
    timezone: str | None = None
    scheduling_url: HttpUrl | None = None


class CalendlyEventType(BaseModel):
    """Validated subset of Calendly event type resources used by the site."""

    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    slug: str | None = None
    active: bool = False
    duration: int | None = None
    kind: str | None = None
    scheduling_url: HttpUrl | None = None


class PublicMetadata(BaseModel):
    """Validated public metadata emitted to grahama.co."""

    generator: str
    source: str = "calendly_api_v2"
    generatedFromApi: bool
    asOf: str
    user: dict[str, str | None]
    primarySchedulingUrl: str | None
    eventTypes: list[dict[str, Any]]
    seam_validation: dict[str, str]


class GoogleOAuthToken(BaseModel):
    """Validated local Google OAuth token produced by ops-google-calendar."""

    model_config = ConfigDict(extra="ignore")

    refresh_token: str = Field(min_length=1)
    client_id: str = Field(min_length=1)
    client_secret: str = Field(min_length=1)


class CalendarEventRecord(BaseModel):
    """Validated calendar event identity stored in capacity-hold receipts."""

    id: str = Field(min_length=1)
    htmlLink: str | None = None
    status: str | None = None
    calendarId: str = Field(default="primary", min_length=1)
    summary: str
    start: str
    end: str
    reason: str


class CapacityHoldsWriteReceipt(BaseModel):
    """Validated receipt used by release to reverse created capacity holds."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    schema_: str = Field(alias="schema")
    status: str
    calendarId: str
    writesCalendar: bool
    createdEvents: list[CalendarEventRecord] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class HoldSlot:
    """One planned real capacity hold."""

    start: datetime
    end: datetime
    reason: str
    index: int = 0

    def to_json(self) -> dict[str, str]:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "reason": self.reason,
            "index": str(self.index),
        }


@dataclass(frozen=True, slots=True)
class CapacityPlan:
    """Internal capacity-hold plan shared by plan and execute commands."""

    monday: date
    slots: list[HoldSlot] = field(default_factory=list)
    holds: list[HoldSlot] = field(default_factory=list)

    def to_receipt_fields(self, target_ratio: float, slot_minutes: int) -> dict[str, Any]:
        return {
            "targetRatio": target_ratio,
            "maxTargetRatio": MAX_HOLD_RATIO,
            "weekStart": self.monday.isoformat(),
            "slotMinutes": slot_minutes,
            "candidateSlotCount": len(self.slots),
            "plannedHoldCount": len(self.holds),
            "plannedHoldRatio": round(len(self.holds) / len(self.slots), 4) if self.slots else 0,
            "holds": [hold.to_json() for hold in self.holds],
        }


def _token() -> str | None:
    token = os.environ.get("CALENDLY_PAT", "").strip()
    return token or None


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _emit(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    status = payload.get("status") or payload.get("readiness") or "OK"
    typer.echo(f"{payload.get('schema', 'ops_calendly.receipt.v1')}: {status}")


def _api_get(path: str, token: str, params: dict[str, str] | None = None) -> dict[str, Any]:
    timeout = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    with httpx.Client(base_url=API_BASE, headers=headers, timeout=timeout) as client:
        response = client.get(path, params=params)
        response.raise_for_status()
        return response.json()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("failed to load JSON fixture {}: {}", path, exc)
        raise typer.BadParameter(f"invalid JSON fixture: {path}") from exc


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _default_receipt_path(prefix: str) -> Path:
    stamp = _utc_now().strftime("%Y%m%dT%H%M%SZ")
    return RECEIPT_DIR / f"{prefix}-{stamp}.json"


def _validated_me(payload: dict[str, Any]) -> CalendlyUser:
    resource = payload.get("resource")
    if not isinstance(resource, dict):
        raise ValueError("Calendly /users/me response missing resource object")
    return CalendlyUser.model_validate(resource)


def _validated_event_types(payload: dict[str, Any]) -> list[CalendlyEventType]:
    collection = payload.get("collection")
    if not isinstance(collection, list):
        raise ValueError("Calendly /event_types response missing collection list")
    return [CalendlyEventType.model_validate(item) for item in collection]


def _public_event_type(event_type: CalendlyEventType) -> dict[str, Any]:
    return {
        "name": event_type.name,
        "slug": event_type.slug,
        "active": event_type.active,
        "duration": event_type.duration,
        "kind": event_type.kind,
        "schedulingUrl": str(event_type.scheduling_url) if event_type.scheduling_url else None,
    }


def _build_metadata(
    user: CalendlyUser,
    event_types: list[CalendlyEventType],
    *,
    generated_from_api: bool,
    generator: str,
) -> PublicMetadata:
    public_events = [_public_event_type(item) for item in event_types]
    active_events = [
        item for item in public_events
        if item["active"] is True and item["schedulingUrl"]
    ]
    primary_url = active_events[0]["schedulingUrl"] if active_events else (
        str(user.scheduling_url) if user.scheduling_url else None
    )
    metadata = PublicMetadata(
        generator=generator,
        generatedFromApi=generated_from_api,
        asOf=_utc_now().isoformat().replace("+00:00", "Z"),
        user={
            "name": user.name,
            "slug": user.slug,
            "timezone": user.timezone,
            "schedulingUrl": str(user.scheduling_url) if user.scheduling_url else None,
        },
        primarySchedulingUrl=primary_url,
        eventTypes=public_events,
        seam_validation={"kind": "ops_calendly.public_metadata.v1", "status": "PASS"},
    )
    return metadata


def _read_calendly(token: str) -> tuple[CalendlyUser, list[CalendlyEventType]]:
    me = _validated_me(_api_get("/users/me", token))
    event_types = _validated_event_types(_api_get("/event_types", token, {"user": me.uri}))
    return me, event_types


def _load_google_token() -> GoogleOAuthToken | None:
    if not GCAL_TOKEN_FILE.is_file():
        return None
    try:
        return GoogleOAuthToken.model_validate(_load_json(GCAL_TOKEN_FILE))
    except (ValidationError, typer.BadParameter) as exc:
        logger.error("Google OAuth token is unreadable or invalid: {}", exc)
        return None


def _google_access_token() -> str | None:
    token = _load_google_token()
    if token is None:
        return None
    timeout = httpx.Timeout(connect=5.0, read=20.0, write=10.0, pool=5.0)
    try:
        response = httpx.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": token.client_id,
                "client_secret": token.client_secret,
                "refresh_token": token.refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=timeout,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error("Google OAuth token refresh failed: {}", exc)
        return None
    access_token = response.json().get("access_token")
    return access_token if isinstance(access_token, str) and access_token else None


def _google_api(
    method: str,
    path: str,
    access_token: str,
    *,
    params: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> httpx.Response:
    timeout = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)
    with httpx.Client(base_url=GCAL_API_BASE, timeout=timeout) as client:
        return client.request(
            method,
            path,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
            params=params,
            json=body,
        )


def _parse_today(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter("--today must be YYYY-MM-DD") from exc


def _week_start(value: str, today_value: str | None) -> date:
    base = _parse_today(today_value) or datetime.now(UTC).date()
    if value == "current":
        return base - timedelta(days=base.weekday())
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter("--week must be 'current' or YYYY-MM-DD") from exc
    return parsed - timedelta(days=parsed.weekday())


def _timezone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise typer.BadParameter(f"unknown timezone: {value}") from exc


def _common_slots(week_start: date, slot_minutes: int, timezone_name: str, reason: str) -> list[HoldSlot]:
    tz = _timezone(timezone_name)
    common_hours = [9, 10, 11, 13, 14, 15, 16]
    slots: list[HoldSlot] = []
    index = 0
    for day_offset in range(5):
        day = week_start + timedelta(days=day_offset)
        for hour in common_hours:
            start = datetime.combine(day, time(hour=hour), tzinfo=tz)
            end = start + timedelta(minutes=slot_minutes)
            slots.append(HoldSlot(start=start, end=end, reason=reason, index=index))
            index += 1
    return slots


def _select_holds(slots: list[HoldSlot], ratio: float) -> list[HoldSlot]:
    target = int(len(slots) * ratio)
    if target < 1 and slots:
        target = 1
    ranked = sorted(slots, key=lambda slot: (slot.start.hour not in {10, 11, 14, 15}, slot.start.weekday(), slot.start.hour))
    return sorted(ranked[:target], key=lambda slot: slot.start)


def _capacity_plan(
    week: str,
    target_ratio: float,
    slot_minutes: int,
    timezone_name: str,
    today: str | None,
    reason: str,
) -> CapacityPlan:
    if target_ratio > MAX_HOLD_RATIO:
        raise typer.BadParameter(f"--target-ratio cannot exceed {MAX_HOLD_RATIO}")
    if reason not in ALLOWED_HOLD_REASONS:
        allowed = ", ".join(sorted(ALLOWED_HOLD_REASONS))
        raise typer.BadParameter(f"--reason must be one of: {allowed}")
    monday = _week_start(week, today)
    slots = _common_slots(monday, slot_minutes, timezone_name, reason)
    holds = _select_holds(slots, target_ratio)
    return CapacityPlan(monday=monday, slots=slots, holds=holds)


def _calendar_event_body(hold: HoldSlot, summary: str, timezone_name: str) -> dict[str, Any]:
    return {
        "summary": summary,
        "description": (
            "Real capacity hold created by ops-calendly. "
            f"Reason: {hold.reason}. Policy: real_capacity_holds_only."
        ),
        "start": {"dateTime": hold.start.isoformat(), "timeZone": timezone_name},
        "end": {"dateTime": hold.end.isoformat(), "timeZone": timezone_name},
        "transparency": "opaque",
        "visibility": "private",
        "extendedProperties": {
            "private": {
                "ops_calendly": "capacity_hold",
                "reason": hold.reason,
                "policy": "real_capacity_holds_only",
                "slot_index": str(hold.index),
            }
        },
    }


def _created_event_record(raw: dict[str, Any], hold: HoldSlot, calendar_id: str, summary: str) -> CalendarEventRecord:
    start = raw.get("start") if isinstance(raw.get("start"), dict) else {}
    end = raw.get("end") if isinstance(raw.get("end"), dict) else {}
    return CalendarEventRecord(
        id=str(raw.get("id") or ""),
        htmlLink=raw.get("htmlLink") if isinstance(raw.get("htmlLink"), str) else None,
        status=raw.get("status") if isinstance(raw.get("status"), str) else None,
        calendarId=calendar_id,
        summary=summary,
        start=str(start.get("dateTime") or hold.start.isoformat()),
        end=str(end.get("dateTime") or hold.end.isoformat()),
        reason=hold.reason,
    )


@app.command()
def doctor(as_json: Annotated[bool, typer.Option("--json/--no-json")] = True) -> None:
    """Check CALENDLY_PAT presence and live Calendly API reachability."""

    token = _token()
    receipt: dict[str, Any] = {
        "schema": "ops_calendly.doctor.v1",
        "tokenPresent": token is not None,
        "mocked": False,
        "live": False,
        "status": "MISSING_TOKEN",
    }
    if token is None:
        _emit(receipt, as_json)
        raise typer.Exit(1)
    try:
        user, event_types = _read_calendly(token)
    except (httpx.HTTPError, ValidationError, ValueError) as exc:
        logger.error("Calendly API doctor failed: {}", exc)
        receipt["status"] = "API_ERROR"
        _emit(receipt, as_json)
        raise typer.Exit(1)
    receipt.update({
        "status": "READY",
        "live": True,
        "user": {
            "name": user.name,
            "slug": user.slug,
            "timezone": user.timezone,
            "schedulingUrl": str(user.scheduling_url) if user.scheduling_url else None,
        },
        "eventTypeCount": len(event_types),
    })
    _emit(receipt, as_json)


@app.command(name="event-types")
def event_types(as_json: Annotated[bool, typer.Option("--json/--no-json")] = True) -> None:
    """List public Calendly event type metadata."""

    token = _token()
    if token is None:
        _emit({"schema": "ops_calendly.event_types.v1", "status": "MISSING_TOKEN", "tokenPresent": False}, as_json)
        raise typer.Exit(1)
    try:
        _, items = _read_calendly(token)
    except (httpx.HTTPError, ValidationError, ValueError) as exc:
        logger.error("Calendly event type read failed: {}", exc)
        _emit({"schema": "ops_calendly.event_types.v1", "status": "API_ERROR"}, as_json)
        raise typer.Exit(1)
    public_items = [_public_event_type(item) for item in items]
    _emit({
        "schema": "ops_calendly.event_types.v1",
        "status": "OK",
        "mocked": False,
        "live": True,
        "count": len(public_items),
        "eventTypes": public_items,
    }, as_json)


@app.command(name="generate-site-metadata")
def generate_site_metadata(
    out: Annotated[Path, typer.Option("--out", help="Output calendly.json path")],
    fixture_me: Annotated[Path | None, typer.Option("--fixture-me")] = None,
    fixture_event_types: Annotated[Path | None, typer.Option("--fixture-event-types")] = None,
    preserve_existing: Annotated[bool, typer.Option("--preserve-existing/--fail-missing-token")] = True,
    as_json: Annotated[bool, typer.Option("--json/--no-json")] = True,
) -> None:
    """Generate safe public scheduling metadata for the static site."""

    fixture_mode = fixture_me is not None or fixture_event_types is not None
    if fixture_mode and not (fixture_me and fixture_event_types):
        raise typer.BadParameter("pass both --fixture-me and --fixture-event-types")

    try:
        if fixture_mode:
            user = _validated_me(_load_json(fixture_me))
            items = _validated_event_types(_load_json(fixture_event_types))
            metadata = _build_metadata(
                user,
                items,
                generated_from_api=False,
                generator="skills/ops-calendly/scripts/ops_calendly.py",
            )
        else:
            token = _token()
            if token is None:
                if preserve_existing and out.exists():
                    _emit({
                        "schema": "ops_calendly.generate_site_metadata.v1",
                        "status": "PRESERVED_EXISTING",
                        "out": str(out),
                        "tokenPresent": False,
                        "mocked": False,
                        "live": False,
                    }, as_json)
                    return
                raise RuntimeError("CALENDLY_PAT missing and output does not exist")
            user, items = _read_calendly(token)
            metadata = _build_metadata(
                user,
                items,
                generated_from_api=True,
                generator="skills/ops-calendly/scripts/ops_calendly.py",
            )
    except (httpx.HTTPError, ValidationError, ValueError, RuntimeError) as exc:
        logger.error("metadata generation failed: {}", exc)
        _emit({"schema": "ops_calendly.generate_site_metadata.v1", "status": "FAILED", "reason": str(exc)}, as_json)
        raise typer.Exit(1)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(metadata.model_dump_json(indent=2) + "\n", encoding="utf-8")
    _emit({
        "schema": "ops_calendly.generate_site_metadata.v1",
        "status": "WROTE",
        "out": str(out),
        "eventTypeCount": len(metadata.eventTypes),
        "primarySchedulingUrl": metadata.primarySchedulingUrl,
        "generatedFromApi": metadata.generatedFromApi,
        "mocked": False,
        "live": metadata.generatedFromApi,
        "seam_validation": metadata.seam_validation,
    }, as_json)


@app.command(name="github-secret")
def github_secret(
    repo: Annotated[str, typer.Option("--repo")],
    execute: Annotated[bool, typer.Option("--execute")] = False,
    as_json: Annotated[bool, typer.Option("--json/--no-json")] = True,
) -> None:
    """Set CALENDLY_PAT as a GitHub Actions secret, or dry-run the action."""

    token = _token()
    receipt: dict[str, Any] = {
        "schema": "ops_calendly.github_secret.v1",
        "secret": "CALENDLY_PAT",
        "repo": repo,
        "execute": execute,
        "tokenPresent": token is not None,
        "status": "DRY_RUN",
    }
    if not execute:
        _emit(receipt, as_json)
        return
    if token is None:
        receipt["status"] = "MISSING_TOKEN"
        _emit(receipt, as_json)
        raise typer.Exit(1)
    try:
        subprocess.run(
            ["gh", "secret", "set", "CALENDLY_PAT", "--repo", repo],
            input=f"{token}\n",
            text=True,
            capture_output=True,
            check=True,
            timeout=30,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        logger.error("gh secret set failed: {}", exc)
        receipt["status"] = "FAILED"
        _emit(receipt, as_json)
        raise typer.Exit(1)
    receipt["status"] = "SET"
    _emit(receipt, as_json)


@capacity_holds_app.command(name="plan")
def capacity_holds_plan(
    week: Annotated[str, typer.Option("--week")] = "current",
    target_ratio: Annotated[float, typer.Option("--target-ratio", min=0.0, max=MAX_HOLD_RATIO)] = MAX_HOLD_RATIO,
    slot_minutes: Annotated[int, typer.Option("--slot-minutes", min=15, max=120)] = 30,
    timezone_name: Annotated[str, typer.Option("--timezone")] = "America/New_York",
    reason: Annotated[str, typer.Option("--reason")] = "focus",
    today: Annotated[str | None, typer.Option("--today", help="YYYY-MM-DD, for deterministic tests")] = None,
    as_json: Annotated[bool, typer.Option("--json/--no-json")] = True,
) -> None:
    """Plan real capacity holds for common current-week slots without writing calendars."""

    plan = _capacity_plan(week, target_ratio, slot_minutes, timezone_name, today, reason)
    receipt = {
        "schema": "ops_calendly.capacity_holds.plan.v1",
        "status": "PLANNED",
        "mode": "dry_run",
        "policy": "real_capacity_holds_only",
        "disallowedUse": "fake_scarcity",
        "writesCalendar": False,
        "requiresExecuteForWrites": True,
        "timezone": timezone_name,
        "mocked": False,
        "live": False,
        "seam_validation": {"kind": "ops_calendly.capacity_holds.plan.v1", "status": "PASS"},
    }
    receipt.update(plan.to_receipt_fields(target_ratio, slot_minutes))
    _emit(receipt, as_json)


@capacity_holds_app.command(name="execute")
def capacity_holds_execute(
    week: Annotated[str, typer.Option("--week")] = "current",
    target_ratio: Annotated[float, typer.Option("--target-ratio", min=0.0, max=MAX_HOLD_RATIO)] = MAX_HOLD_RATIO,
    slot_minutes: Annotated[int, typer.Option("--slot-minutes", min=15, max=120)] = 30,
    timezone_name: Annotated[str, typer.Option("--timezone")] = "America/New_York",
    reason: Annotated[str, typer.Option("--reason")] = "focus",
    summary: Annotated[str, typer.Option("--summary")] = "Capacity hold",
    calendar_id: Annotated[str, typer.Option("--calendar-id")] = "primary",
    today: Annotated[str | None, typer.Option("--today", help="YYYY-MM-DD, for deterministic tests")] = None,
    execute: Annotated[bool, typer.Option("--execute")] = False,
    receipt_out: Annotated[Path | None, typer.Option("--receipt-out")] = None,
    as_json: Annotated[bool, typer.Option("--json/--no-json")] = True,
) -> None:
    """Create real Google Calendar Busy holds; dry-run unless --execute is present."""

    plan = _capacity_plan(week, target_ratio, slot_minutes, timezone_name, today, reason)
    out = receipt_out or _default_receipt_path("capacity-holds")
    receipt: dict[str, Any] = {
        "schema": "ops_calendly.capacity_holds.write.v1",
        "status": "NOT_EXECUTED",
        "mode": "write_requires_execute",
        "policy": "real_capacity_holds_only",
        "disallowedUse": "fake_scarcity",
        "writesCalendar": False,
        "execute": execute,
        "calendarId": calendar_id,
        "summary": summary,
        "timezone": timezone_name,
        "receiptPath": str(out),
        "createdEvents": [],
        "releaseCommand": f"./run.sh capacity-holds release --receipt {out} --execute",
        "mocked": False,
        "live": False,
        "seam_validation": {"kind": "ops_calendly.capacity_holds.write.v1", "status": "PASS"},
    }
    receipt.update(plan.to_receipt_fields(target_ratio, slot_minutes))
    if not execute:
        _emit(receipt, as_json)
        return

    access = _google_access_token()
    if access is None:
        receipt.update({
            "status": "BLOCKED_UNAUTHENTICATED",
            "reason": f"missing or invalid Google OAuth token at {GCAL_TOKEN_FILE}",
        })
        _emit(receipt, as_json)
        raise typer.Exit(1)

    created: list[CalendarEventRecord] = []
    failures: list[dict[str, Any]] = []
    encoded_calendar = quote(calendar_id, safe="")
    for hold in plan.holds:
        response = _google_api(
            "POST",
            f"/calendars/{encoded_calendar}/events",
            access,
            body=_calendar_event_body(hold, summary, timezone_name),
        )
        if response.status_code not in (200, 201):
            failures.append({"start": hold.start.isoformat(), "statusCode": response.status_code})
            logger.error("Google Calendar hold create failed: {}", response.status_code)
            continue
        try:
            created.append(_created_event_record(response.json(), hold, calendar_id, summary))
        except (ValueError, ValidationError) as exc:
            failures.append({"start": hold.start.isoformat(), "error": str(exc)})
            logger.error("Google Calendar create response invalid: {}", exc)

    created_json = [event.model_dump() for event in created]
    receipt.update({
        "status": "APPLIED" if not failures and len(created) == len(plan.holds) else "PARTIAL",
        "writesCalendar": bool(created),
        "live": True,
        "createdEvents": created_json,
        "createdEventCount": len(created),
        "failures": failures,
    })
    CapacityHoldsWriteReceipt.model_validate(receipt)
    _write_json(out, receipt)
    _emit(receipt, as_json)
    if failures:
        raise typer.Exit(1)


@capacity_holds_app.command(name="release")
def capacity_holds_release(
    receipt: Annotated[Path, typer.Option("--receipt")],
    calendar_id: Annotated[str | None, typer.Option("--calendar-id")] = None,
    execute: Annotated[bool, typer.Option("--execute")] = False,
    receipt_out: Annotated[Path | None, typer.Option("--receipt-out")] = None,
    as_json: Annotated[bool, typer.Option("--json/--no-json")] = True,
) -> None:
    """Release capacity holds by deleting events recorded in a write receipt."""

    try:
        write_receipt = CapacityHoldsWriteReceipt.model_validate(_load_json(receipt))
    except (ValidationError, typer.BadParameter) as exc:
        logger.error("invalid capacity-holds receipt {}: {}", receipt, exc)
        _emit({"schema": "ops_calendly.capacity_holds.release.v1", "status": "INVALID_RECEIPT"}, as_json)
        raise typer.Exit(1)

    target_calendar = calendar_id or write_receipt.calendarId
    out = receipt_out or _default_receipt_path("capacity-holds-release")
    release_receipt: dict[str, Any] = {
        "schema": "ops_calendly.capacity_holds.release.v1",
        "status": "NOT_EXECUTED",
        "execute": execute,
        "sourceReceipt": str(receipt),
        "calendarId": target_calendar,
        "wouldDeleteCount": len(write_receipt.createdEvents),
        "releasedEvents": [],
        "missingEvents": [],
        "failures": [],
        "writesCalendar": False,
        "mocked": False,
        "live": False,
        "receiptPath": str(out),
        "seam_validation": {"kind": "ops_calendly.capacity_holds.release.v1", "status": "PASS"},
    }
    if not execute:
        _emit(release_receipt, as_json)
        return

    access = _google_access_token()
    if access is None:
        release_receipt.update({
            "status": "BLOCKED_UNAUTHENTICATED",
            "reason": f"missing or invalid Google OAuth token at {GCAL_TOKEN_FILE}",
        })
        _emit(release_receipt, as_json)
        raise typer.Exit(1)

    encoded_calendar = quote(target_calendar, safe="")
    for event in write_receipt.createdEvents:
        encoded_event = quote(event.id, safe="")
        response = _google_api("DELETE", f"/calendars/{encoded_calendar}/events/{encoded_event}", access)
        if response.status_code == 204:
            release_receipt["releasedEvents"].append({"id": event.id, "start": event.start})
        elif response.status_code in (404, 410):
            release_receipt["missingEvents"].append({"id": event.id, "statusCode": response.status_code})
        else:
            release_receipt["failures"].append({"id": event.id, "statusCode": response.status_code})
            logger.error("Google Calendar hold release failed: {}", response.status_code)

    release_receipt.update({
        "status": "RELEASED" if not release_receipt["failures"] else "PARTIAL",
        "writesCalendar": bool(release_receipt["releasedEvents"]),
        "live": True,
    })
    _write_json(out, release_receipt)
    _emit(release_receipt, as_json)
    if release_receipt["failures"]:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
