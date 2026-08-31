"""ops-wiim: WiiM Amp local-network diagnostics for low sound output triage.

Read-mostly CLI over the LinkPlay HTTP API (https://<ip>/httpapi.asp?command=...,
plain-HTTP fallback). Mutating commands (volume, EQ) are gated behind --execute.

Exit codes: 0 ok, 2 amp unreachable, 3 mutation without --execute.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
from typing import Any

import httpx
import typer
from dotenv import load_dotenv

load_dotenv()  # repo-root/skill .env (WIIM_IP); run.sh also sources repo .env

app = typer.Typer(add_completion=False, help=__doc__)

SCHEMA_STATUS = "ops_wiim.status.v1"
SCHEMA_DIAG = "ops_wiim.diagnosis.v1"
TIMEOUT = 5.0


def _resolve_ip(ip: str | None) -> str:
    ip = ip or os.environ.get("WIIM_IP", "")
    if ip:
        return ip
    # mDNS auto-discovery: prefer the Amp among advertised LinkPlay devices
    try:
        import subprocess

        out = subprocess.run(
            ["avahi-browse", "-artp", "-t"], capture_output=True, text=True, timeout=10
        ).stdout
        cands = []
        for line in out.splitlines():
            if not line.startswith("=") or "_linkplay._tcp" not in line:
                continue
            f = line.split(";")
            name, addr = f[3].replace("\\032", " "), f[7]
            if "wiim" in name.lower():
                cands.append(("amp" in name.lower(), addr))
        if cands:
            cands.sort(reverse=True)
            return cands[0][1]
    except Exception:  # noqa: BLE001 - discovery is best-effort, fail closed below
        pass
    typer.echo(
        "error: no IP. Pass --ip, set WIIM_IP, run `discover`, or make the amp "
        "visible via mDNS (avahi-browse -art | grep -i linkplay).",
        err=True,
    )
    raise typer.Exit(2)


def _api(ip: str, command: str) -> tuple[bool, Any]:
    """Call httpapi.asp. Returns (reachable, parsed-or-text)."""
    last_err: Exception | None = None
    for base in (f"https://{ip}", f"http://{ip}"):
        try:
            r = httpx.get(
                f"{base}/httpapi.asp",
                params={"command": command},
                timeout=TIMEOUT,
                verify=False,
            )
            text = r.text.strip()
            try:
                return True, json.loads(text)
            except ValueError:
                return True, text
        except Exception as exc:  # noqa: BLE001 - network probe, fail closed below
            last_err = exc
    return False, str(last_err)


def _snapshot(ip: str) -> dict[str, Any]:
    """Collect the read-only state relevant to low-volume triage."""
    reachable, status_ex = _api(ip, "getStatusEx")
    if not reachable:
        return {"reachable": False, "error": status_ex}
    snap: dict[str, Any] = {"reachable": True, "status_ex": status_ex}
    for key, cmd in [
        ("player", "getPlayerStatus"),
        ("eq_stat", "EQGetStat"),
        ("output_mode", "getNewAudioOutputHardwareMode"),
    ]:
        ok, val = _api(ip, cmd)
        if not ok or (isinstance(val, str) and "unknown command" in val.lower()):
            snap[key] = {"not_supported": True, "raw": val if ok else None}
        else:
            snap[key] = val
    return snap


def _emit(payload: dict, as_json: bool) -> None:
    if as_json:
        typer.echo(json.dumps(payload, indent=2, default=str))
    else:
        typer.echo(json.dumps(payload, indent=2, default=str))


@app.command("resolve")
def resolve(json_out: bool = typer.Option(False, "--json")) -> None:
    """Find LinkPlay/WiiM devices on the LAN via mDNS (no IP needed)."""
    import subprocess

    out = subprocess.run(
        ["avahi-browse", "-artp", "-t"], capture_output=True, text=True, timeout=10
    ).stdout
    devices: dict[str, dict] = {}
    for line in out.splitlines():
        if not line.startswith("=") or "_linkplay._tcp" not in line:
            continue
        f = line.split(";")
        if f[2] != "IPv4":
            continue
        name = f[3].replace("\\032", " ")
        mac = ""
        for part in f[8:]:
            if part.startswith('"MAC='):
                mac = part.strip('"').split("=", 1)[1]
        devices[name] = {"name": name, "ip": f[7], "mac": mac}
    result = {"schema": "ops_wiim.resolve.v1", "devices": sorted(devices.values(), key=lambda d: d["name"])}
    _emit(result, json_out)


@app.command()
def discover(json_out: bool = typer.Option(False, "--json"), seconds: float = 3.0) -> None:
    """SSDP M-SEARCH for LinkPlay/MediaRenderer devices on the LAN."""
    msg = (
        "M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n"
        'MAN: "ssdp:discover"\r\nMX: 2\r\nST: urn:schemas-upnp-org:device:MediaRenderer:1\r\n\r\n'
    ).encode()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(seconds)
    sock.sendto(msg, ("239.255.255.250", 1900))
    found: dict[str, dict] = {}
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            data, addr = sock.recvfrom(4096)
        except socket.timeout:
            break
        headers = {}
        for line in data.decode(errors="replace").split("\r\n")[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()
        found[addr[0]] = {"ip": addr[0], "server": headers.get("server", ""), "location": headers.get("location", "")}
    sock.close()
    devices = list(found.values())
    _emit({"schema": "ops_wiim.discovery.v1", "devices": devices, "count": len(devices)}, json_out)


@app.command()
def status(ip: str = typer.Option(None, "--ip"), json_out: bool = typer.Option(False, "--json")) -> None:
    """Raw state snapshot: getStatusEx, getPlayerStatus, EQ, output mode."""
    ip = _resolve_ip(ip)
    snap = _snapshot(ip)
    payload = {"schema": SCHEMA_STATUS, "ip": ip, **snap}
    _emit(payload, json_out)
    if not snap["reachable"]:
        raise typer.Exit(2)


def _findings(snap: dict[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    player = snap.get("player") or {}
    if isinstance(player, dict) and not player.get("not_supported"):
        vol = player.get("vol")
        mute = player.get("mute")
        mode = player.get("mode")
        try:
            if vol is not None and int(vol) < 30:
                findings.append({"finding": "low_reported_volume",
                                 "detail": f"reported volume is {vol}/100",
                                 "next": "raise volume via app or `set-volume 60 --execute` and retest"})
        except (TypeError, ValueError):
            pass
        if str(mute) == "1":
            findings.append({"finding": "muted", "detail": "device reports mute=1",
                             "next": "unmute and retest"})
        if mode is not None:
            findings.append({"finding": "active_source", "detail": f"playback mode/source code: {mode}",
                             "next": "repeat diagnose on each source (streaming vs HDMI ARC vs Line In) and compare"})
    eq = snap.get("eq_stat")
    if isinstance(eq, dict) and not eq.get("not_supported"):
        if str(eq.get("EQStat", eq.get("status", ""))).lower() in {"on", "1"}:
            findings.append({"finding": "eq_enabled",
                             "detail": f"EQ engaged: {eq}",
                             "next": "run `set-eq-off --execute` to rule out band cuts"})
    out = snap.get("output_mode")
    if isinstance(out, dict) and not out.get("not_supported"):
        findings.append({"finding": "output_mode", "detail": str(out),
                         "next": "verify speaker-out (not fixed line-out) mode is expected"})
    if not findings:
        findings.append({"finding": "no_config_cause_observed",
                         "detail": "no mute/low-volume/EQ cause visible in reported state",
                         "next": "suspect upstream gain-staging (TV PCM output level, passthrough) or hardware; API cannot observe power-stage health"})
    return findings


@app.command()
def diagnose(ip: str = typer.Option(None, "--ip"), json_out: bool = typer.Option(False, "--json")) -> None:
    """Low-volume triage report (ops_wiim.diagnosis.v1) with heuristic findings."""
    ip = _resolve_ip(ip)
    snap = _snapshot(ip)
    if not snap["reachable"]:
        _emit({"schema": SCHEMA_DIAG, "ip": ip, "status": "down", "reachable": False,
               "error": snap.get("error"), "findings": []}, json_out)
        raise typer.Exit(2)
    payload = {
        "schema": SCHEMA_DIAG,
        "ip": ip,
        "status": "up",
        "reachable": True,
        "findings": _findings(snap),
        "snapshot": snap,
        "not_observable": [
            "power delivered to speaker terminals", "clipping/protection events",
            "HDMI PCM bit depth/sample rate", "TV-side digital attenuation",
            "amplifier temperature", "speaker impedance", "hardware faults",
        ],
    }
    _emit(payload, json_out)


@app.command()
def monitor(ip: str = typer.Option(None, "--ip"), seconds: int = 60, interval: float = 2.0) -> None:
    """Poll getPlayerStatus and print NDJSON deltas while a fault is reproduced."""
    ip = _resolve_ip(ip)
    prev: dict | None = None
    deadline = time.time() + seconds
    while time.time() < deadline:
        ok, player = _api(ip, "getPlayerStatus")
        if not ok:
            typer.echo(json.dumps({"ts": time.time(), "event": "unreachable", "error": player}))
        elif isinstance(player, dict):
            delta = {k: v for k, v in player.items() if prev is None or prev.get(k) != v}
            if delta:
                typer.echo(json.dumps({"ts": time.time(), "delta": delta}))
            prev = player
        time.sleep(interval)


def _mutate(ip: str | None, command: str, execute: bool, label: str) -> None:
    ip = _resolve_ip(ip)
    if not execute:
        typer.echo(json.dumps({"refused": True, "reason": f"{label} is a mutation; pass --execute"}), err=True)
        raise typer.Exit(3)
    ok, resp = _api(ip, command)
    if not ok:
        typer.echo(json.dumps({"status": "down", "error": resp}), err=True)
        raise typer.Exit(2)
    # Read back to verify effect rather than trusting the command response.
    _, player = _api(ip, "getPlayerStatus")
    typer.echo(json.dumps({"command": command, "response": resp, "readback": player}, default=str))


@app.command("set-volume")
def set_volume(level: int = typer.Argument(..., min=0, max=100),
               ip: str = typer.Option(None, "--ip"),
               execute: bool = typer.Option(False, "--execute")) -> None:
    """Set volume 0-100 (gated behind --execute; read back afterwards)."""
    _mutate(ip, f"setPlayerCmd:vol:{level}", execute, "set-volume")


@app.command("play-url")
def play_url(url: str = typer.Argument(..., help="http(s) audio URL the amp will fetch"),
             ip: str = typer.Option(None, "--ip"),
             execute: bool = typer.Option(False, "--execute")) -> None:
    """Play an audio URL on the amp for reference/tone tests (gated behind --execute)."""
    _mutate(ip, f"setPlayerCmd:play:{url}", execute, "play-url")


@app.command("set-eq-off")
def set_eq_off(ip: str = typer.Option(None, "--ip"),
               execute: bool = typer.Option(False, "--execute")) -> None:
    """Disable EQ to rule out band cuts (gated behind --execute)."""
    _mutate(ip, "EQOff", execute, "set-eq-off")


if __name__ == "__main__":
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(130)
