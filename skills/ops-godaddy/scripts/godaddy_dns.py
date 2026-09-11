#!/usr/bin/env python3
"""GoDaddy DNS operations CLI.

Encodes the live 2026-09-11 grahama.co mail-auth fix:
- Auth: personal access token (developer.godaddy.com), Bearer header.
- API quirks (each cost a live failure to learn):
  * Zone-wide PUT requires >= 2 NS records in the body (422 otherwise).
  * PATCH /records APPENDS (duplicate records -> 422), it does not replace.
  * PUT [] on a type/name does NOT delete; DELETE returns 409
    CONFLICTING_STATUS on some accounts. Deletion works via zone-wide PUT
    that omits the record.
  * dns:update-scoped tokens cannot read (401) but can write.
- Verification: always dig the authoritative NS (instant, no TTL wait).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Literal, Optional

import pydantic
import typer

API = "https://api.godaddy.com"
app = typer.Typer(help=__doc__)

RecordType = Literal["A", "AAAA", "CNAME", "MX", "TXT", "NS", "SRV", "CAA", "PTR"]


class Record(pydantic.BaseModel):
    """One DNS record at the GoDaddy API boundary (extra=forbid: trust boundary)."""

    model_config = pydantic.ConfigDict(extra="forbid")

    name: str = pydantic.Field(min_length=1)
    data: str = pydantic.Field(min_length=1)
    ttl: int = pydantic.Field(default=3600, ge=60, le=86400)
    type: RecordType
    priority: Optional[int] = pydantic.Field(default=None, ge=0, le=65535)
    port: Optional[int] = None
    protocol: Optional[str] = None
    service: Optional[str] = None
    weight: Optional[int] = None


class Zone(pydantic.BaseModel):
    """A zone-wide replacement set. Enforces the >=2 NS API rule at the producer."""

    records: list[Record]

    @pydantic.model_validator(mode="after")
    def require_two_ns(self) -> "Zone":
        ns = [r for r in self.records if r.type == "NS"]
        if len(ns) < 2:
            raise ValueError(
                "GoDaddy zone-wide PUT requires at least 2 NS records in the body "
                f"(got {len(ns)}); otherwise the API returns 422 MISSING_NAME_SERVER."
            )
        return self


def _load_dotenv() -> None:
    env = Path(__file__).resolve().parents[1] / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def _token() -> str:
    _load_dotenv()
    tok = os.environ.get("GODADDY_PAT") or ""
    if not tok and os.path.exists(".env"):
        for line in open(".env"):
            if line.startswith("GODADDY_PAT="):
                tok = line.split("=", 1)[1].strip()
    if not tok:
        typer.echo(
            json.dumps(
                {
                    "ok": False,
                    "error_type": "missing_token",
                    "fix": "Generate at https://developer.godaddy.com/keys (personal access token, scope domains.dns:update, 30d), then export GODADDY_PAT=gd_pat_... or put it in .env",
                }
            )
        )
        raise typer.Exit(code=2)
    return tok


def _curl(method: str, path: str, body: Optional[str] = None) -> tuple[int, str]:
    cmd = ["curl", "-s", "-m", "20", "-X", method, f"{API}{path}",
           "-H", f"Authorization: Bearer {_token()}",
           "-H", "Content-Type: application/json",
           "-w", "\n%{http_code}"]
    if body is not None:
        cmd += ["-d", body]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    lines = out.strip().rsplit("\n", 1)
    return int(lines[-1]), lines[0] if len(lines) > 1 else ""


def put_record(
    domain: str = typer.Option(...),
    rtype: RecordType = typer.Option(...),
    name: str = typer.Option(...),
    data: str = typer.Option(...),
    ttl: int = typer.Option(3600),
    priority: Optional[int] = typer.Option(None),
) -> None:
    """PUT a single type/name record set (replaces all records of that type/name)."""
    rec = Record(name=name, data=data, ttl=ttl, type=rtype, priority=priority)
    code, body = _curl("PUT", f"/v1/domains/{domain}/records/{rtype}/{name}",
                       json.dumps([rec.model_dump(exclude_none=True)]))
    typer.echo(json.dumps({"ok": code == 200, "http": code, "body": body[:200]}))
    raise typer.Exit(code=0 if code == 200 else 1)


def put_zone(
    domain: str = typer.Option(...),
    zone_file: str = typer.Option(..., help="JSON array of records; must include >=2 NS"),
) -> None:
    """Replace the ENTIRE zone. Records omitted from the file are deleted (the only reliable deletion path)."""
    raw = json.loads(Path(zone_file).read_text())
    zone = Zone(records=[Record(**r) for r in raw])  # producer-side typed gate
    code, body = _curl("PUT", f"/v1/domains/{domain}/records",
                       json.dumps([r.model_dump(exclude_none=True) for r in zone.records]))
    typer.echo(json.dumps({"ok": code == 200, "http": code, "records": len(zone.records), "body": body[:200]}))
    raise typer.Exit(code=0 if code == 200 else 1)


def diagnose(domain: str = typer.Option(...)) -> None:
    """Mail-auth diagnostic: SPF, delegate includes, DKIM selectors, DMARC, MX — the dig sequence."""
    def dig(*args: str) -> str:
        return subprocess.run(["dig", "+short", *args], capture_output=True, text=True).stdout.strip()

    ns = (dig(f"NS", domain) or "").split("\n")[0]
    result = {
        "schema": "ops_godaddy.diagnose.v1",
        "domain": domain,
        "authoritative_ns": ns,
        "mx": dig(f"@{ns}", "MX", domain).split("\n"),
        "spf": [t for t in dig(f"@{ns}", "TXT", domain).split("\n") if "spf1" in t],
        "dmarc": dig(f"@{ns}", "TXT", f"_dmarc.{domain}"),
        "dkim_google": dig(f"@{ns}", "TXT", f"google._domainkey.{domain}") or "ABSENT (enable in Workspace admin: Apps>Gmail>Authenticate email)",
    }
    result["verdict"] = (
        "google_workspace_send_ok" if "_spf.google.com" in "".join(result["spf"])
        else "spf_does_not_authorize_gmail"
    )
    typer.echo(json.dumps(result, indent=2))


for c in (put_record, put_zone, diagnose):
    app.command()(c)

if __name__ == "__main__":
    app()
